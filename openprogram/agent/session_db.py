"""SQLite-backed session + message store.

One-stop persistence for chat conversations across every transport
(TUI / web / wechat / telegram / discord / slack). Replaces the
per-conv ``meta.json`` + ``messages.json`` layout — that path was
fine at MVP scale but was rewriting the whole messages file every
turn, walking the filesystem on every ``list_conversations`` call,
and offering no way to grep history.

Schema:

  sessions      — one row per conv. Indexed on (agent_id, updated_at)
                  so /resume picker is O(log n). Channel-bound rows
                  carry source/channel/peer fields; local rows leave
                  them NULL.

  messages      — append-only DAG (parent_id → message). Cheap to
                  add a row, indexed on (session_id, timestamp) for
                  history loads. ON DELETE CASCADE so dropping a
                  session sweeps its messages.

  messages_fts  — FTS5 mirror of messages.content. Triggers keep it
                  in sync; ``search_messages`` queries it for full-
                  text recall (e.g. /search 北京天气).

Concurrency: WAL mode + ``timeout=15`` so multiple processes
(channel workers, webui, future replicas) can read while one writes
without "database is locked" errors. WAL also gives us crash safety
without manual fsync.

The ``context_tree`` and ``extra_meta`` columns are JSON text — both
are sparse / structurally varied (different webui execution states,
per-channel custom fields) and SQLite doesn't have a column type
for them. Read with ``json.loads(row["extra_meta"] or "{}")``.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  title TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  source TEXT,
  channel TEXT,
  account_id TEXT,
  peer_kind TEXT,
  peer_id TEXT,
  peer_display TEXT,
  head_id TEXT,
  provider_name TEXT,
  model TEXT,
  context_tree TEXT,
  extra_meta TEXT,
  last_prompt_tokens INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_agent_updated
  ON sessions(agent_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_source
  ON sessions(source);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  parent_id TEXT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  timestamp REAL NOT NULL,
  source TEXT,
  peer_display TEXT,
  peer_id TEXT,
  display TEXT,
  function TEXT,
  extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session_ts
  ON messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_parent
  ON messages(parent_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  content,
  session_id UNINDEXED,
  content=messages,
  content_rowid=rowid
);
"""

# FTS5 sync triggers — separate from CREATE TABLE since the trigger
# body references the messages table that must already exist.
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content, session_id)
    VALUES (new.rowid, new.content, new.session_id);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, session_id)
    VALUES ('delete', old.rowid, old.content, old.session_id);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, session_id)
    VALUES ('delete', old.rowid, old.content, old.session_id);
  INSERT INTO messages_fts(rowid, content, session_id)
    VALUES (new.rowid, new.content, new.session_id);
END;
"""


# Columns we model explicitly on `sessions` — anything else lands in
# extra_meta JSON. Used by create/update to pick the right path for
# each field the caller passes in.
_SESSION_COLS = {
    "id", "agent_id", "title", "created_at", "updated_at",
    "source", "channel", "account_id", "peer_kind", "peer_id",
    "peer_display", "head_id", "provider_name", "model",
    "context_tree", "extra_meta", "last_prompt_tokens",
}

_MESSAGE_COLS = {
    "id", "session_id", "parent_id", "role", "content", "timestamp",
    "source", "peer_display", "peer_id", "display", "function", "extra",
}


def _default_db_path() -> Path:
    from openprogram.paths import get_state_dir
    return get_state_dir() / "sessions.sqlite"


class SessionDB:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: webui's asyncio loop and channel
        # threads share the connection. The lock below serializes
        # writes; SQLite WAL handles reader concurrency.
        self.conn = sqlite3.connect(
            self.db_path,
            timeout=15,
            isolation_level=None,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._write_lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self._write_lock:
            self.conn.executescript(SCHEMA)
            self.conn.executescript(TRIGGERS)

    # -- session CRUD ------------------------------------------------------

    def create_session(self, session_id: str, agent_id: str,
                       **fields: Any) -> None:
        """Insert a new session. Caller controls created_at / updated_at
        if they want; otherwise both default to now()."""
        now = time.time()
        row: dict[str, Any] = {
            "id": session_id,
            "agent_id": agent_id,
            "created_at": fields.pop("created_at", now),
            "updated_at": fields.pop("updated_at", now),
        }
        extra: dict[str, Any] = {}
        for k, v in fields.items():
            if k in _SESSION_COLS:
                row[k] = v
            else:
                extra[k] = v
        if extra:
            existing_extra = json.loads(row.get("extra_meta") or "{}")
            existing_extra.update(extra)
            row["extra_meta"] = json.dumps(existing_extra, default=str)
        if "context_tree" in row and not isinstance(row["context_tree"], str):
            row["context_tree"] = json.dumps(row["context_tree"], default=str)

        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        with self._write_lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO sessions ({','.join(cols)}) "
                f"VALUES ({placeholders})",
                [row[c] for c in cols],
            )

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        # Pull current extra_meta so unknown keys merge instead of replace.
        cur = self.get_session(session_id)
        if cur is None:
            # Caller asked to update a missing session — be permissive,
            # create a stub so the channel path's "ingest into possibly
            # missing session" works without ordering ceremony.
            self.create_session(session_id, fields.pop("agent_id", "main"),
                                **fields)
            return
        sets: dict[str, Any] = {}
        # Copy — cur["extra_meta"] is a live dict reference; mutating
        # it would also mutate the comparison target on the next line
        # and the change-detection always returns equal.
        extra = dict(cur.get("extra_meta") or {})
        original_extra = dict(extra)
        for k, v in fields.items():
            if k in _SESSION_COLS:
                sets[k] = v
            else:
                extra[k] = v
        if extra != original_extra:
            sets["extra_meta"] = json.dumps(extra, default=str)
        if "context_tree" in sets and not isinstance(sets["context_tree"], str):
            sets["context_tree"] = json.dumps(sets["context_tree"], default=str)
        sets.setdefault("updated_at", time.time())
        cols = list(sets.keys())
        with self._write_lock:
            self.conn.execute(
                f"UPDATE sessions SET {','.join(c + '=?' for c in cols)} "
                f"WHERE id=?",
                [sets[c] for c in cols] + [session_id],
            )

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        return _row_to_session(row) if row else None

    def list_sessions(self, *, agent_id: Optional[str] = None,
                      source: Optional[str] = None,
                      limit: int = 200,
                      offset: int = 0) -> list[dict[str, Any]]:
        clauses, args = [], []
        if agent_id is not None:
            clauses.append("agent_id=?")
            args.append(agent_id)
        if source is not None:
            clauses.append("source=?")
            args.append(source)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cur = self.conn.execute(
            f"SELECT * FROM sessions{where} "
            f"ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        )
        return [_row_to_session(r) for r in cur.fetchall()]

    def delete_session(self, session_id: str) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM sessions WHERE id=?",
                              (session_id,))

    # -- message CRUD ------------------------------------------------------

    def append_message(self, session_id: str, msg: dict[str, Any]) -> None:
        row: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": msg.get("timestamp") or time.time(),
        }
        extra: dict[str, Any] = {}
        for k, v in msg.items():
            if k in _MESSAGE_COLS:
                row[k] = v
            else:
                extra[k] = v
        if extra:
            row["extra"] = json.dumps(extra, default=str)
        # Required columns
        if "id" not in row or "role" not in row or "content" not in row:
            raise ValueError(
                "append_message requires id, role, content; got: "
                + ",".join(sorted(msg.keys())))
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        with self._write_lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO messages ({','.join(cols)}) "
                f"VALUES ({placeholders})",
                [row[c] for c in cols],
            )
            # Bump session.updated_at so /resume picker re-sorts.
            self.conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (row["timestamp"], session_id),
            )

    def get_messages(self, session_id: str, *,
                     limit: Optional[int] = None) -> list[dict[str, Any]]:
        sql = ("SELECT * FROM messages WHERE session_id=? "
               "ORDER BY timestamp ASC")
        args: list[Any] = [session_id]
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        cur = self.conn.execute(sql, args)
        return [_row_to_message(r) for r in cur.fetchall()]

    def search_messages(self, query: str, *,
                        agent_id: Optional[str] = None,
                        limit: int = 50) -> list[dict[str, Any]]:
        """FTS5 full-text search across message content. Returns matched
        messages joined with their session info (so /search can show
        which conv each hit came from)."""
        # FTS5 wraps the query in a MATCH clause; quote arbitrary input
        # so it's safe (FTS5 has its own syntax — quoted strings are
        # treated as a phrase search, no operator parsing).
        safe_query = '"' + query.replace('"', '""') + '"'
        if agent_id is not None:
            cur = self.conn.execute(
                "SELECT m.*, s.title AS session_title, s.source AS session_source "
                "FROM messages_fts f "
                "JOIN messages m ON m.rowid = f.rowid "
                "JOIN sessions s ON s.id = m.session_id "
                "WHERE messages_fts MATCH ? AND s.agent_id=? "
                "ORDER BY m.timestamp DESC LIMIT ?",
                (safe_query, agent_id, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT m.*, s.title AS session_title, s.source AS session_source "
                "FROM messages_fts f "
                "JOIN messages m ON m.rowid = f.rowid "
                "JOIN sessions s ON s.id = m.session_id "
                "WHERE messages_fts MATCH ? "
                "ORDER BY m.timestamp DESC LIMIT ?",
                (safe_query, limit),
            )
        out = []
        for r in cur.fetchall():
            d = _row_to_message(r)
            d["session_title"] = r["session_title"]
            d["session_source"] = r["session_source"]
            out.append(d)
        return out

    # -- bulk helpers ------------------------------------------------------

    def append_messages(self, session_id: str,
                        msgs: Iterable[dict[str, Any]]) -> None:
        """Atomic append of a list of messages (single transaction).
        Used during session imports / replays."""
        msgs = list(msgs)
        if not msgs:
            return
        with self._write_lock:
            self.conn.execute("BEGIN")
            try:
                for m in msgs:
                    row: dict[str, Any] = {
                        "session_id": session_id,
                        "timestamp": m.get("timestamp") or time.time(),
                    }
                    extra: dict[str, Any] = {}
                    for k, v in m.items():
                        if k in _MESSAGE_COLS:
                            row[k] = v
                        else:
                            extra[k] = v
                    if extra:
                        row["extra"] = json.dumps(extra, default=str)
                    if "id" not in row or "role" not in row or "content" not in row:
                        continue
                    cols = list(row.keys())
                    self.conn.execute(
                        f"INSERT OR REPLACE INTO messages ({','.join(cols)}) "
                        f"VALUES ({','.join('?' for _ in cols)})",
                        [row[c] for c in cols],
                    )
                self.conn.execute(
                    "UPDATE sessions SET updated_at=? WHERE id=?",
                    (msgs[-1].get("timestamp") or time.time(), session_id),
                )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


# -- row → dict conversion ---------------------------------------------

def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    extra = d.pop("extra_meta", None)
    if extra:
        try:
            extra_obj = json.loads(extra)
        except Exception:
            extra_obj = {}
    else:
        extra_obj = {}
    ct = d.get("context_tree")
    if ct:
        try:
            d["context_tree"] = json.loads(ct)
        except Exception:
            pass
    # Hoist extra_meta keys to top level so callers see one flat dict.
    for k, v in extra_obj.items():
        d.setdefault(k, v)
    d["extra_meta"] = extra_obj
    return d


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    extra = d.pop("extra", None)
    if extra:
        try:
            extra_obj = json.loads(extra)
        except Exception:
            extra_obj = {}
        for k, v in extra_obj.items():
            d.setdefault(k, v)
    return d


# -- module-level singleton -------------------------------------------

_default: Optional[SessionDB] = None
_default_lock = threading.Lock()


def default_db() -> SessionDB:
    """Process-wide singleton. Channels worker + webui server share
    this instance; SessionDB itself is thread-safe."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = SessionDB()
    return _default
