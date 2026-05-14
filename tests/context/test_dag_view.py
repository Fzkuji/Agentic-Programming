"""dag_view: turn a Graph into the tree dicts the legacy WebUI viewer
expects. Pure-function tests — no SQLite, no HTTP."""

from __future__ import annotations

import pytest

from openprogram.context.dag_view import call_to_dict, dag_to_tree_dicts
from openprogram.context.nodes import Call, Graph, ROLE_CODE, ROLE_LLM, ROLE_USER


# ── call_to_dict ──────────────────────────────────────────────────


def test_call_to_dict_basic_fields():
    c = Call(
        id="abc123",
        role=ROLE_CODE,
        name="my_fn",
        input={"x": 1},
        output="ok",
        created_at=100.0,
        metadata={"status": "success", "duration_seconds": 0.5},
    )
    d = call_to_dict(c)
    assert d["path"] == "abc123"
    assert d["name"] == "my_fn"
    assert d["node_type"] == "function"
    assert d["params"] == {"x": 1}
    assert d["output"] == "ok"
    assert d["status"] == "success"
    assert d["start_time"] == 100.0
    assert d["end_time"] == 100.5
    assert d["duration_ms"] == 500
    assert d["children"] == []
    assert d["error"] == ""


def test_call_to_dict_error_extracts_message():
    c = Call(
        id="x",
        role=ROLE_CODE,
        name="boom",
        output={"error": "boom!"},
        metadata={"status": "error", "duration_seconds": 0.1},
    )
    d = call_to_dict(c)
    assert d["status"] == "error"
    assert d["error"] == "boom!"


def test_call_to_dict_running_node_has_no_end_time():
    c = Call(
        id="x",
        role=ROLE_CODE,
        name="slow",
        output=None,
        created_at=200.0,
        metadata={"status": "running"},
    )
    d = call_to_dict(c)
    assert d["status"] == "running"
    assert d["end_time"] is None
    assert d["duration_ms"] is None


def test_call_to_dict_missing_metadata_defaults_to_success():
    c = Call(id="x", role=ROLE_CODE, name="plain", output=42)
    d = call_to_dict(c)
    assert d["status"] == "success"


# ── dag_to_tree_dicts ────────────────────────────────────────────


def test_dag_to_tree_dicts_empty_graph():
    assert dag_to_tree_dicts(Graph()) == []


def test_dag_to_tree_dicts_skips_non_code_calls():
    g = Graph()
    g.add(Call(role=ROLE_USER, output="hi"))
    g.add(Call(role=ROLE_LLM, output="hello"))
    assert dag_to_tree_dicts(g) == []


def test_dag_to_tree_dicts_single_root():
    g = Graph()
    g.add(Call(id="f1", role=ROLE_CODE, name="alpha",
               metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert len(trees) == 1
    assert trees[0]["name"] == "alpha"
    assert trees[0]["children"] == []


def test_dag_to_tree_dicts_nests_by_called_by():
    g = Graph()
    g.add(Call(id="outer", role=ROLE_CODE, name="outer",
               metadata={"status": "success"}))
    g.add(Call(id="inner1", role=ROLE_CODE, name="inner",
               called_by="outer", metadata={"status": "success"}))
    g.add(Call(id="inner2", role=ROLE_CODE, name="inner",
               called_by="outer", metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert len(trees) == 1
    assert trees[0]["name"] == "outer"
    children = trees[0]["children"]
    assert [c["name"] for c in children] == ["inner", "inner"]


def test_dag_to_tree_dicts_orphan_called_by_becomes_root():
    """A code Call whose called_by points outside the code-only
    subgraph (e.g. it was called from the dispatcher's user message)
    should appear as a root, not be silently dropped."""
    g = Graph()
    g.add(Call(role=ROLE_USER, output="hi", id="u1"))
    g.add(Call(id="f1", role=ROLE_CODE, name="alpha",
               called_by="u1", metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert len(trees) == 1
    assert trees[0]["path"] == "f1"


def test_dag_to_tree_dicts_children_sorted_by_seq():
    """Same parent → children sort by seq, mirroring chronological
    execution order."""
    g = Graph()
    g.add(Call(id="outer", role=ROLE_CODE, name="outer",
               metadata={"status": "success"}))
    # Note: explicit seq to lock order
    g.add(Call(id="a", role=ROLE_CODE, name="a", seq=5,
               called_by="outer", metadata={"status": "success"}))
    g.add(Call(id="b", role=ROLE_CODE, name="b", seq=3,
               called_by="outer", metadata={"status": "success"}))
    g.add(Call(id="c", role=ROLE_CODE, name="c", seq=8,
               called_by="outer", metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert [c["name"] for c in trees[0]["children"]] == ["b", "a", "c"]


def test_dag_to_tree_dicts_multi_level_chain():
    g = Graph()
    g.add(Call(id="lvl1", role=ROLE_CODE, name="l1",
               metadata={"status": "success"}))
    g.add(Call(id="lvl2", role=ROLE_CODE, name="l2",
               called_by="lvl1", metadata={"status": "success"}))
    g.add(Call(id="lvl3", role=ROLE_CODE, name="l3",
               called_by="lvl2", metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert trees[0]["name"] == "l1"
    assert trees[0]["children"][0]["name"] == "l2"
    assert trees[0]["children"][0]["children"][0]["name"] == "l3"
    assert trees[0]["children"][0]["children"][0]["children"] == []
