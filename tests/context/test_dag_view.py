"""dag_view: turn a Graph into the tree dicts the WebUI viewer expects.
Pure-function tests — no SQLite, no HTTP.

Filter rule under test:
  keep = role∈{llm, user}  ∪  {code Calls whose subtree contains llm}
  pure-code (no llm anywhere underneath) is dropped; its children get
  promoted to the nearest surviving ancestor (or root).
"""

from __future__ import annotations

import pytest

from openprogram.context.dag_view import call_to_dict, dag_to_tree_dicts
from openprogram.context.nodes import Call, Graph, ROLE_CODE, ROLE_LLM, ROLE_USER


# ── call_to_dict ──────────────────────────────────────────────────


def test_call_to_dict_llm_node_type():
    c = Call(role=ROLE_LLM, name="gpt-x", output="hi", created_at=100.0,
             metadata={"duration_seconds": 0.5})
    d = call_to_dict(c)
    assert d["node_type"] == "llm_call"
    assert d["name"] == "gpt-x"
    assert d["output"] == "hi"
    assert d["start_time"] == 100.0
    assert d["end_time"] == 100.5
    assert d["duration_ms"] == 500
    assert d["status"] == "success"


def test_call_to_dict_user_message_no_input():
    c = Call(role=ROLE_USER, output="hello there")
    d = call_to_dict(c)
    assert d["node_type"] == "user_message"
    assert d["name"] == "user_message"
    assert d["output"] == "hello there"


def test_call_to_dict_user_ask_user_has_question():
    c = Call(role=ROLE_USER, input={"question": "still there?"},
             output="yes", metadata={"status": "answered"})
    d = call_to_dict(c)
    assert d["node_type"] == "user_message"
    assert d["name"] == "ask_user"
    assert d["params"] == {"question": "still there?"}
    assert d["status"] == "answered"


def test_call_to_dict_code_node_basic_fields():
    c = Call(role=ROLE_CODE, name="my_fn", input={"x": 1}, output="ok",
             created_at=100.0,
             metadata={"status": "success", "duration_seconds": 0.5})
    d = call_to_dict(c)
    assert d["node_type"] == "function"
    assert d["name"] == "my_fn"
    assert d["params"] == {"x": 1}
    assert d["output"] == "ok"


def test_call_to_dict_error_extracts_message():
    c = Call(role=ROLE_CODE, name="boom",
             output={"error": "boom!"},
             metadata={"status": "error", "duration_seconds": 0.1})
    d = call_to_dict(c)
    assert d["status"] == "error"
    assert d["error"] == "boom!"


def test_call_to_dict_running_node_has_no_end_time():
    c = Call(role=ROLE_CODE, name="slow", output=None, created_at=200.0,
             metadata={"status": "running"})
    d = call_to_dict(c)
    assert d["status"] == "running"
    assert d["end_time"] is None
    assert d["duration_ms"] is None


# ── dag_to_tree_dicts ────────────────────────────────────────────


def test_empty_graph_yields_no_trees():
    assert dag_to_tree_dicts(Graph()) == []


def test_plain_chat_user_and_llm_become_roots():
    """user + llm + user + llm (no called_by) → four roots in seq order."""
    g = Graph()
    g.add(Call(id="u1", role=ROLE_USER, output="q1"))
    g.add(Call(id="l1", role=ROLE_LLM, output="a1"))
    g.add(Call(id="u2", role=ROLE_USER, output="q2"))
    g.add(Call(id="l2", role=ROLE_LLM, output="a2"))
    trees = dag_to_tree_dicts(g)
    assert [t["path"] for t in trees] == ["u1", "l1", "u2", "l2"]
    assert [t["node_type"] for t in trees] == [
        "user_message", "llm_call", "user_message", "llm_call",
    ]
    assert all(t["children"] == [] for t in trees)


def test_function_with_llm_nests_under_caller():
    """user → code(my_fn) → llm inside fn → ... should produce a tree
    where the llm hangs under the code Call."""
    g = Graph()
    g.add(Call(id="u1", role=ROLE_USER, output="q"))
    g.add(Call(id="fn1", role=ROLE_CODE, name="my_fn",
               metadata={"status": "success"}))
    g.add(Call(id="ll1", role=ROLE_LLM, name="opus",
               called_by="fn1", output="reply"))
    trees = dag_to_tree_dicts(g)
    # u1 is a root, fn1 is a root, ll1 is fn1's child.
    assert [t["path"] for t in trees] == ["u1", "fn1"]
    assert trees[1]["node_type"] == "function"
    assert [c["path"] for c in trees[1]["children"]] == ["ll1"]


def test_pure_code_without_llm_is_dropped():
    """A code Call with no llm descendant disappears from the forest."""
    g = Graph()
    g.add(Call(id="u1", role=ROLE_USER, output="hi"))
    g.add(Call(id="util", role=ROLE_CODE, name="pure_helper",
               metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert [t["path"] for t in trees] == ["u1"]


def test_pruned_code_promotes_children_to_ancestor():
    """Tree: kept_code → util_code(pruned) → llm
    After pruning util_code, llm should hang directly under kept_code."""
    g = Graph()
    g.add(Call(id="outer", role=ROLE_CODE, name="outer",
               metadata={"status": "success"}))
    g.add(Call(id="util", role=ROLE_CODE, name="util",
               called_by="outer", metadata={"status": "success"}))
    g.add(Call(id="llmcall", role=ROLE_LLM, name="opus",
               called_by="util", output="reply"))
    trees = dag_to_tree_dicts(g)
    # outer is kept (descendant llmcall exists).
    # util has no own llm child immediately, but its descendant llmcall
    # is kept → util survives too. The pruning rule only drops a code
    # node when *no* descendant survives.
    assert [t["path"] for t in trees] == ["outer"]
    util = trees[0]["children"][0]
    assert util["path"] == "util"
    assert util["children"][0]["path"] == "llmcall"


def test_dropped_code_with_grandchild_llm_through_dropped_path():
    """Edge case: pure helper inside a pure helper, no llm at any
    level → both dropped, no node remains."""
    g = Graph()
    g.add(Call(id="outer", role=ROLE_CODE, name="outer",
               metadata={"status": "success"}))
    g.add(Call(id="inner", role=ROLE_CODE, name="inner",
               called_by="outer", metadata={"status": "success"}))
    g.add(Call(id="leaf", role=ROLE_CODE, name="leaf",
               called_by="inner", metadata={"status": "success"}))
    trees = dag_to_tree_dicts(g)
    assert trees == []


def test_orphan_called_by_falls_back_to_root():
    """A kept Call whose called_by points at an id that doesn't exist
    in the graph (foreign reference) becomes a root anyway."""
    g = Graph()
    g.add(Call(id="ll1", role=ROLE_LLM, name="opus",
               called_by="nonexistent_id", output="reply"))
    trees = dag_to_tree_dicts(g)
    assert [t["path"] for t in trees] == ["ll1"]


def test_children_sorted_by_seq():
    g = Graph()
    g.add(Call(id="outer", role=ROLE_CODE, name="outer",
               metadata={"status": "success"}))
    # Children added out of order
    g.add(Call(id="ll_c", seq=8, role=ROLE_LLM, called_by="outer",
               output="c"))
    g.add(Call(id="ll_a", seq=3, role=ROLE_LLM, called_by="outer",
               output="a"))
    g.add(Call(id="ll_b", seq=5, role=ROLE_LLM, called_by="outer",
               output="b"))
    trees = dag_to_tree_dicts(g)
    assert [c["path"] for c in trees[0]["children"]] == ["ll_a", "ll_b", "ll_c"]


def test_root_siblings_sorted_by_seq():
    g = Graph()
    g.add(Call(id="u_c", seq=4, role=ROLE_USER, output="c"))
    g.add(Call(id="u_a", seq=1, role=ROLE_USER, output="a"))
    g.add(Call(id="u_b", seq=2, role=ROLE_USER, output="b"))
    trees = dag_to_tree_dicts(g)
    assert [t["path"] for t in trees] == ["u_a", "u_b", "u_c"]
