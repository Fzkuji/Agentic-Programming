"""Coverage for openprogram.agent.session_db.SessionDB.

Each test gets a fresh in-memory-style db file under a tmp_path so
state never leaks between tests. We don't use ``:memory:`` because
the production SessionDB hardcodes WAL mode + multi-thread access,
and SQLite ``:memory:`` doesn't support WAL.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from openprogram.agent.session_db import SessionDB


@pytest.fixture
def db(tmp_path: Path) -> SessionDB:
    return SessionDB(tmp_path / "sessions.sqlite")


def test_create_and_get_session(db: SessionDB) -> None:
    db.create_session("c1", "main", title="hello", source="wechat",
                      peer_display="alice")
    s = db.get_session("c1")
    assert s is not None
    assert s["id"] == "c1"
    assert s["agent_id"] == "main"
    assert s["title"] == "hello"
    assert s["source"] == "wechat"
    assert s["peer_display"] == "alice"
    assert s["created_at"] > 0
    assert s["updated_at"] > 0


def test_create_session_extra_meta_overflow(db: SessionDB) -> None:
    """Unknown keys land in extra_meta JSON column and are hoisted on read."""
    db.create_session("c1", "main", custom_field="hi", another=42)
    s = db.get_session("c1")
    assert s["custom_field"] == "hi"
    assert s["another"] == 42
    assert s["extra_meta"]["custom_field"] == "hi"


def test_update_session_merges_extra_meta(db: SessionDB) -> None:
    db.create_session("c1", "main", x=1)
    db.update_session("c1", y=2, title="updated")
    s = db.get_session("c1")
    assert s["title"] == "updated"
    assert s["x"] == 1   # preserved from create
    assert s["y"] == 2   # added by update


def test_update_missing_session_creates_stub(db: SessionDB) -> None:
    db.update_session("ghost", agent_id="main", title="materialized")
    s = db.get_session("ghost")
    assert s is not None
    assert s["title"] == "materialized"


def test_list_sessions_orders_by_updated_desc(db: SessionDB) -> None:
    db.create_session("a", "main", created_at=1.0, updated_at=1.0)
    db.create_session("b", "main", created_at=2.0, updated_at=2.0)
    db.create_session("c", "other", created_at=3.0, updated_at=3.0)
    rows = db.list_sessions()
    assert [r["id"] for r in rows] == ["c", "b", "a"]


def test_list_sessions_filter_by_agent(db: SessionDB) -> None:
    db.create_session("a", "main")
    db.create_session("b", "other")
    rows = db.list_sessions(agent_id="main")
    assert {r["id"] for r in rows} == {"a"}


def test_list_sessions_filter_by_source(db: SessionDB) -> None:
    db.create_session("a", "main", source="wechat")
    db.create_session("b", "main", source="telegram")
    db.create_session("c", "main")  # source=None
    rows = db.list_sessions(source="wechat")
    assert {r["id"] for r in rows} == {"a"}


def test_append_message_basic(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.append_message("c1", {
        "id": "m1", "role": "user", "content": "hi",
        "timestamp": 100.0,
    })
    msgs = db.get_messages("c1")
    assert len(msgs) == 1
    assert msgs[0]["id"] == "m1"
    assert msgs[0]["content"] == "hi"
    # appending should bump session.updated_at
    s = db.get_session("c1")
    assert s["updated_at"] == 100.0


def test_append_message_extra_overflow(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.append_message("c1", {
        "id": "m1", "role": "user", "content": "hi",
        "tool_calls": [{"name": "bash"}],
        "custom": "x",
    })
    [m] = db.get_messages("c1")
    assert m["tool_calls"] == [{"name": "bash"}]
    assert m["custom"] == "x"


def test_append_message_missing_required(db: SessionDB) -> None:
    db.create_session("c1", "main")
    with pytest.raises(ValueError):
        db.append_message("c1", {"id": "x"})


def test_append_messages_atomic(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.append_messages("c1", [
        {"id": "m1", "role": "user", "content": "a", "timestamp": 1.0},
        {"id": "m2", "role": "assistant", "content": "b", "timestamp": 2.0},
        {"id": "m3", "role": "user", "content": "c", "timestamp": 3.0},
    ])
    msgs = db.get_messages("c1")
    assert [m["id"] for m in msgs] == ["m1", "m2", "m3"]
    assert db.get_session("c1")["updated_at"] == 3.0


def test_messages_ordered_by_timestamp(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.append_message("c1", {"id": "b", "role": "user", "content": "second", "timestamp": 2.0})
    db.append_message("c1", {"id": "a", "role": "user", "content": "first", "timestamp": 1.0})
    db.append_message("c1", {"id": "c", "role": "user", "content": "third", "timestamp": 3.0})
    msgs = db.get_messages("c1")
    assert [m["id"] for m in msgs] == ["a", "b", "c"]


def test_search_messages_fts(db: SessionDB) -> None:
    db.create_session("c1", "main", title="weather chat")
    db.append_message("c1", {"id": "m1", "role": "user", "content": "what is the weather", "timestamp": 1.0})
    db.append_message("c1", {"id": "m2", "role": "user", "content": "tell me a joke", "timestamp": 2.0})
    db.create_session("c2", "main", title="other")
    db.append_message("c2", {"id": "m3", "role": "user", "content": "weather is cold", "timestamp": 3.0})

    hits = db.search_messages("weather")
    ids = {h["id"] for h in hits}
    assert ids == {"m1", "m3"}
    # verify joined session metadata
    by_id = {h["id"]: h for h in hits}
    assert by_id["m1"]["session_title"] == "weather chat"
    assert by_id["m3"]["session_title"] == "other"


def test_search_messages_filter_by_agent(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.create_session("c2", "other")
    db.append_message("c1", {"id": "m1", "role": "user", "content": "weather", "timestamp": 1.0})
    db.append_message("c2", {"id": "m2", "role": "user", "content": "weather", "timestamp": 2.0})
    hits = db.search_messages("weather", agent_id="main")
    assert {h["id"] for h in hits} == {"m1"}


def test_delete_session_cascades_messages(db: SessionDB) -> None:
    db.create_session("c1", "main")
    db.append_message("c1", {"id": "m1", "role": "user", "content": "x", "timestamp": 1.0})
    db.delete_session("c1")
    assert db.get_session("c1") is None
    assert db.get_messages("c1") == []
    # FTS should be cleaned via trigger too
    assert db.search_messages("x") == []


def test_context_tree_round_trip(db: SessionDB) -> None:
    tree = {"node_type": "function", "name": "root", "attempts": []}
    db.create_session("c1", "main", context_tree=tree)
    s = db.get_session("c1")
    assert s["context_tree"] == tree


def test_persists_across_instances(tmp_path: Path) -> None:
    """Two SessionDB instances on the same file see the same data."""
    db1 = SessionDB(tmp_path / "sessions.sqlite")
    db1.create_session("c1", "main", title="persist")
    db1.append_message("c1", {"id": "m1", "role": "user", "content": "hi", "timestamp": 1.0})
    db1.close()
    db2 = SessionDB(tmp_path / "sessions.sqlite")
    s = db2.get_session("c1")
    assert s is not None
    assert s["title"] == "persist"
    assert len(db2.get_messages("c1")) == 1
    db2.close()
