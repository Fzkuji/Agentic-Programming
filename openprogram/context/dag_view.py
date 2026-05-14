"""dag_view — render a DAG snapshot as the tree-shaped dicts the WebUI
viewer consumes.

A Call enters the visible forest when it has anything to do with an
LLM exchange:

  * ``role=llm``   — the LLM call itself
  * ``role=user``  — message into / out of an LLM exchange
                     (dispatcher's user input, or ask_user's prompt+answer)
  * ``role=code``  — only when at least one descendant (via ``called_by``)
                     is an ``llm`` node. A code Call that wraps no LLM
                     traffic (e.g. ``@traced`` over a pure utility) is
                     dropped from the view; its children, if any, are
                     promoted to its parent's position.

Tree edges are ``called_by``: a Call sits under the Call that triggered
it. Roots are Calls whose ``called_by`` is empty (or points at a Call
that itself got pruned).

Pure functions only — no I/O, no SQLite, no FastAPI. The WebUI route
opens a GraphStore and passes its in-memory ``Graph`` here; tests and
CLI dumpers can do the same with a synthetic Graph.
"""

from __future__ import annotations

from typing import Any, Optional

from openprogram.context.nodes import Call, Graph


def call_to_dict(call: Call) -> dict[str, Any]:
    """Serialize one Call into the field shape the existing tree
    renderer reads.

    ``node_type`` is one of:
      "user_message" / "llm_call" / "function"
    so the renderer can style the bubble differently if desired.

    Field map:
      path         <- call.id
      name         <- a human label per role:
                       llm  → ``call.name`` (the model id) or "llm_call"
                       user → "ask_user" when input has "question",
                              else "user_message"
                       code → ``call.name`` (the function name)
      params       <- call.input  (sanitized args / question / system prompt)
      output       <- call.output (LLM text / user answer / fn return)
      status       <- call.metadata["status"] (defaults to "success")
      error        <- output["error"] if status == "error"
      start_time   <- call.created_at
      end_time     <- start + duration_seconds (if known)
      duration_ms  <- duration_seconds * 1000 (if known)
      raw_reply    <- ""  (legacy field, kept for renderer compat)
      children     <- []  (filled by ``dag_to_tree_dicts``)
    """
    meta = call.metadata or {}
    status = meta.get("status") or "success"
    duration_seconds = meta.get("duration_seconds")
    start = call.created_at
    end = (
        start + duration_seconds
        if (duration_seconds is not None and start is not None)
        else None
    )
    duration_ms = (
        int(duration_seconds * 1000)
        if duration_seconds is not None else None
    )

    output = call.output
    error_text: Optional[str] = None
    if status == "error" and isinstance(output, dict):
        error_text = str(output.get("error") or "")

    if call.is_llm():
        node_type = "llm_call"
        name = call.name or "llm_call"
    elif call.is_user():
        node_type = "user_message"
        if isinstance(call.input, dict) and "question" in call.input:
            name = "ask_user"
        else:
            name = "user_message"
    else:
        node_type = "function"
        name = call.name or "function"

    return {
        "path": call.id,
        "name": name,
        "node_type": node_type,
        "params": call.input or {},
        "output": output,
        "status": status,
        "error": error_text or "",
        "start_time": start,
        "end_time": end,
        "duration_ms": duration_ms,
        "raw_reply": "",
        "children": [],
    }


def _keepers(graph: Graph) -> set[str]:
    """Pick the Call ids that survive the LLM-relevance filter.

    A node survives when it's ``llm``, ``user``, or a ``code`` Call
    that has at least one ``llm`` descendant through the ``called_by``
    chain. The descendant test is iterative — repeatedly promote
    "node leads to an llm" upward via ``called_by`` until no more
    code nodes change.
    """
    # parent (called_by) -> [children]
    children_of: dict[str, list[Call]] = {}
    for n in graph:
        parent = n.called_by or ""
        children_of.setdefault(parent, []).append(n)

    keep: set[str] = set()
    for n in graph:
        if n.is_llm() or n.is_user():
            keep.add(n.id)

    # Promote: any code Call with a kept descendant joins the keep set.
    changed = True
    while changed:
        changed = False
        for n in graph:
            if not n.is_code() or n.id in keep:
                continue
            for child in children_of.get(n.id, []):
                if child.id in keep:
                    keep.add(n.id)
                    changed = True
                    break
    return keep


def dag_to_tree_dicts(graph: Graph) -> list[dict[str, Any]]:
    """Return the LLM-relevant Calls in ``graph`` as a tree forest.

    Roots are Calls whose ``called_by`` is empty, points outside the
    graph, or points at a Call that the filter dropped. A pruned
    ``code`` Call hands its children up to its closest surviving
    ancestor (or to the root list when no such ancestor exists),
    which preserves visible nesting even when an intermediate
    "pure-code" wrapper is removed.
    """
    keep = _keepers(graph)
    by_id: dict[str, Call] = {n.id: n for n in graph}

    def _nearest_kept_ancestor(node: Call) -> Optional[str]:
        cursor = node.called_by or ""
        while cursor:
            if cursor in keep:
                return cursor
            parent_node = by_id.get(cursor)
            if parent_node is None:
                return None
            cursor = parent_node.called_by or ""
        return None

    # parent_id -> children (sorted by seq later)
    by_parent: dict[str, list[Call]] = {}
    roots: list[Call] = []
    for node in graph:
        if node.id not in keep:
            continue
        parent = _nearest_kept_ancestor(node)
        if parent is None:
            roots.append(node)
        else:
            by_parent.setdefault(parent, []).append(node)

    roots.sort(key=lambda n: n.seq)
    for siblings in by_parent.values():
        siblings.sort(key=lambda n: n.seq)

    def _build(node: Call) -> dict[str, Any]:
        d = call_to_dict(node)
        d["children"] = [_build(c) for c in by_parent.get(node.id, [])]
        return d

    return [_build(r) for r in roots]


__all__ = ["call_to_dict", "dag_to_tree_dicts"]
