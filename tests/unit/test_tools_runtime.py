"""Coverage for the @tool decorator + runtime layer.

Verifies the parts that govern how every future tool will behave:
schema generation, sync/async wrap, error wrap, char cap + persist,
approval gate evaluation, cache, cancel/on_update injection, and
registry filtering.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import pytest

from openprogram.tools import _runtime as R
from openprogram.tools._runtime import (
    DEFAULT_HEAD_RATIO,
    DEFAULT_MAX_RESULT_CHARS,
    MIN_KEEP_CHARS,
    ToolReturn,
    _build_parameters_schema,
    _cap_result_text,
    _evaluate_approval,
    _parse_docstring,
    all_tools,
    filter_for,
    get,
    register,
    reset_registry,
    to_dict_tool,
    tool,
    tool_requires_approval,
    wrap_legacy_tool,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Each test gets a fresh registry so @tool registrations don't leak."""
    R._cache.clear()
    reset_registry()
    yield
    reset_registry()
    R._cache.clear()


def _run(coro):
    """Run a coroutine to completion in a fresh event loop.

    Each test gets an isolated loop — using ``asyncio.get_event_loop``
    is deprecated in 3.10+ when no loop is running, and hits
    "Event loop is closed" once a previous test's loop got cleaned up.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Docstring parsing
# ---------------------------------------------------------------------------

def test_parse_docstring_description_and_args() -> None:
    doc = """Run a shell command.

    Returns combined stdout/stderr/exit_code.

    Args:
        command: Shell command to execute.
        timeout: Max seconds before kill.
    """
    desc, args = _parse_docstring(doc)
    assert desc == "Run a shell command."
    assert args["command"] == "Shell command to execute."
    assert args["timeout"] == "Max seconds before kill."


def test_parse_docstring_no_args_section() -> None:
    desc, args = _parse_docstring("Just a sentence.")
    assert desc == "Just a sentence."
    assert args == {}


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------

def test_schema_basic_types() -> None:
    def fn(name: str, count: int = 5, enabled: bool = True) -> str:
        """Demo.

        Args:
            name: The name.
            count: How many.
            enabled: Whether on.
        """
        return ""
    schema = _build_parameters_schema(fn)
    assert schema["type"] == "object"
    assert schema["properties"]["name"] == {"type": "string", "description": "The name."}
    assert schema["properties"]["count"] == {"type": "integer", "description": "How many."}
    assert schema["properties"]["enabled"] == {"type": "boolean", "description": "Whether on."}
    assert schema["required"] == ["name"]


def test_schema_optional_strips_none() -> None:
    def fn(x: Optional[int] = None) -> str:
        return ""
    schema = _build_parameters_schema(fn)
    assert schema["properties"]["x"] == {"type": "integer"}
    assert "required" not in schema or "x" not in schema["required"]


def test_schema_skips_framework_kwargs() -> None:
    def fn(query: str, *, on_update=None, cancel=None) -> str:
        return ""
    schema = _build_parameters_schema(fn)
    assert set(schema["properties"].keys()) == {"query"}


# ---------------------------------------------------------------------------
# Result truncation
# ---------------------------------------------------------------------------

def test_cap_short_text_unchanged() -> None:
    assert _cap_result_text("hi", 100) == "hi"


def test_cap_long_text_head_tail() -> None:
    text = "A" * 500 + "B" * 500
    capped = _cap_result_text(text, max_chars=200, head_ratio=0.5)
    # MIN_KEEP_CHARS = 2000 enforces a floor; we asked for 200 but get 2000+
    assert len(capped) >= 2000
    assert "elided" in capped


def test_cap_respects_min_floor() -> None:
    text = "X" * 10_000
    capped = _cap_result_text(text, max_chars=100)
    assert len(capped) >= MIN_KEEP_CHARS
    assert "elided" in capped
    assert capped.startswith("X")
    assert capped.endswith("X")


# ---------------------------------------------------------------------------
# Decorator: schema + name + description
# ---------------------------------------------------------------------------

def test_decorator_extracts_name_description_schema() -> None:
    @tool
    def echo(message: str, repeat: int = 1) -> str:
        """Repeat `message` `repeat` times.

        Args:
            message: The text to echo.
            repeat: Number of repetitions.
        """
        return message * repeat

    assert echo.name == "echo"
    assert "Repeat" in echo.description
    assert echo.parameters["properties"]["message"]["description"] == "The text to echo."
    assert "message" in echo.parameters["required"]
    assert get("echo") is echo


def test_decorator_with_overrides() -> None:
    @tool(name="custom", description="overridden", toolset=["core"])
    def fn(x: int) -> str:
        return str(x)
    assert fn.name == "custom"
    assert fn.description == "overridden"
    # Toolset filter sees it
    assert fn in filter_for(toolset="core")


# ---------------------------------------------------------------------------
# Sync vs async + error wrap
# ---------------------------------------------------------------------------

def test_sync_function_invoked_correctly() -> None:
    @tool
    def add(a: int, b: int) -> str:
        """Add two ints."""
        return str(a + b)

    result = _run(add.execute("call_1", {"a": 2, "b": 3}, None, None))
    assert result.content[0].text == "5"


def test_async_function_invoked_correctly() -> None:
    @tool
    async def slow_add(a: int, b: int) -> str:
        """Add two ints, async."""
        await asyncio.sleep(0)
        return str(a + b)

    result = _run(slow_add.execute("call_1", {"a": 7, "b": 8}, None, None))
    assert result.content[0].text == "15"


def test_exception_caught_and_wrapped() -> None:
    @tool
    def bad(x: int) -> str:
        """Fails."""
        raise RuntimeError("boom")

    result = _run(bad.execute("call_1", {"x": 1}, None, None))
    assert result.details and result.details.get("is_error")
    assert "boom" in result.content[0].text


# ---------------------------------------------------------------------------
# Char cap + persist-to-disk
# ---------------------------------------------------------------------------

def test_long_result_truncates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "_tool_results_dir", lambda: tmp_path)

    @tool(max_result_chars=200, persist_full=False)
    def big() -> str:
        """Huge."""
        return "Z" * 50_000

    result = _run(big.execute("c1", {}, None, None))
    text = result.content[0].text
    assert len(text) >= MIN_KEEP_CHARS
    assert "elided" in text


def test_persist_full_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "_tool_results_dir", lambda: tmp_path)

    @tool(max_result_chars=100, persist_full=True)
    def big() -> str:
        """Persist everything."""
        return "Q" * 50_000

    result = _run(big.execute("c123", {}, None, None))
    text = result.content[0].text
    assert "saved at" in text
    persisted = tmp_path / "c123.txt"
    assert persisted.exists()
    assert persisted.read_text() == "Q" * 50_000


# ---------------------------------------------------------------------------
# ToolReturn structured output
# ---------------------------------------------------------------------------

def test_tool_return_struct() -> None:
    @tool
    def info() -> ToolReturn:
        """Returns mixed content."""
        return ToolReturn(text="hello", json_data={"x": 1})

    result = _run(info.execute("c1", {}, None, None))
    assert result.content[0].text == "hello"
    assert result.details["json"] == {"x": 1}


def test_tool_return_error_flag() -> None:
    @tool
    def failing() -> ToolReturn:
        """Marks itself as error without raising."""
        return ToolReturn(text="oops", is_error=True)

    result = _run(failing.execute("c1", {}, None, None))
    assert result.details["is_error"] is True


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

def test_approval_static_true() -> None:
    @tool(requires_approval=True)
    def dangerous() -> str:
        """Always asks."""
        return "ok"

    needs, reason = tool_requires_approval(dangerous, {})
    assert needs is True
    assert reason is None


def test_approval_callable_returns_string_reason() -> None:
    def gate(command: str) -> Optional[str]:
        if "rm" in command:
            return f"Destructive: {command}"
        return None

    @tool(requires_approval=gate)
    def shell(command: str) -> str:
        """Run cmd."""
        return ""

    needs, reason = tool_requires_approval(shell, {"command": "ls"})
    assert needs is False
    needs, reason = tool_requires_approval(shell, {"command": "rm -rf /"})
    assert needs is True
    assert "Destructive" in reason


def test_approval_callable_exception_defaults_to_require() -> None:
    def angry_gate(**_):
        raise ValueError("oops")

    @tool(requires_approval=angry_gate)
    def stuff() -> str:
        return ""

    needs, reason = tool_requires_approval(stuff, {})
    assert needs is True


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_hits() -> None:
    counter = {"n": 0}

    @tool(cache=True, cache_ttl=60)
    def expensive(x: int) -> str:
        """Counts calls."""
        counter["n"] += 1
        return str(x * 2)

    _run(expensive.execute("c1", {"x": 5}, None, None))
    _run(expensive.execute("c2", {"x": 5}, None, None))
    _run(expensive.execute("c3", {"x": 6}, None, None))
    # 5 hit, 5 hit again (cache), 6 fresh = 2 actual invocations
    assert counter["n"] == 2


def test_cache_skips_errors() -> None:
    counter = {"n": 0}

    @tool(cache=True, cache_ttl=60)
    def maybe_fails(x: int) -> str:
        """Fails on x=1."""
        counter["n"] += 1
        if x == 1:
            raise RuntimeError("nope")
        return "ok"

    _run(maybe_fails.execute("c1", {"x": 1}, None, None))
    _run(maybe_fails.execute("c2", {"x": 1}, None, None))
    # Both calls invoke fn (errors not cached)
    assert counter["n"] == 2


# ---------------------------------------------------------------------------
# Cancel + on_update injection
# ---------------------------------------------------------------------------

def test_on_update_callback_received() -> None:
    seen = []

    @tool
    def chatty(msg: str, *, on_update=None) -> str:
        """Emits progress."""
        on_update(f"working on {msg}")
        return "done"

    _run(chatty.execute(
        "c1", {"msg": "hi"}, None, lambda t: seen.append(t)))
    assert seen == ["working on hi"]


def test_cancel_event_threaded_in() -> None:
    @tool
    def watcher(*, cancel=None) -> str:
        """Reads cancel flag."""
        return f"set={cancel.is_set()}" if cancel else "no_cancel"

    ev = asyncio.Event()
    ev.set()
    result = _run(watcher.execute("c1", {}, ev, None))
    assert result.content[0].text == "set=True"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

def test_timeout_kills_long_tool() -> None:
    @tool(timeout=0.05)
    async def slow() -> str:
        """Hangs."""
        await asyncio.sleep(5)
        return "never"

    result = _run(slow.execute("c1", {}, None, None))
    assert result.details and result.details.get("timeout")


# ---------------------------------------------------------------------------
# Registry + toolset + unsafe_in
# ---------------------------------------------------------------------------

def test_registry_filter_by_toolset_and_source() -> None:
    @tool(toolset=["core"])
    def safe() -> str:
        """OK in any channel."""
        return ""

    @tool(toolset=["core"], unsafe_in=["wechat"])
    def bash_like() -> str:
        """Hidden in wechat."""
        return ""

    core = filter_for(toolset="core")
    assert {t.name for t in core} == {"safe", "bash_like"}

    in_wechat = filter_for(toolset="core", source="wechat")
    assert {t.name for t in in_wechat} == {"safe"}


def test_registry_filter_by_explicit_names() -> None:
    @tool
    def a() -> str:
        return ""

    @tool
    def b() -> str:
        return ""

    @tool
    def c() -> str:
        return ""

    picked = filter_for(names=["a", "c", "missing"])
    assert {t.name for t in picked} == {"a", "c"}


# ---------------------------------------------------------------------------
# Backward-compat: to_dict_tool
# ---------------------------------------------------------------------------

def test_to_dict_tool_round_trip() -> None:
    @tool
    def shout(text: str) -> str:
        """Uppercase."""
        return text.upper()

    legacy = to_dict_tool(shout)
    assert legacy["spec"]["name"] == "shout"
    assert legacy["spec"]["parameters"]["properties"]["text"]["type"] == "string"
    # execute is a sync callable returning a plain string
    assert legacy["execute"](text="hi") == "HI"


# ---------------------------------------------------------------------------
# wrap_legacy_tool — adapter for non-migrated dict tools
# ---------------------------------------------------------------------------

def test_wrap_legacy_tool_sync() -> None:
    record = {
        "spec": {
            "name": "echo",
            "description": "Echo input",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
        "execute": lambda text: f">> {text}",
    }
    t = wrap_legacy_tool(record, toolsets=["core"])
    assert get("echo") is t
    assert t.description == "Echo input"
    out = _run(t.execute("call-1", {"text": "hi"}, None, None))
    assert out.content[0].text == ">> hi"


def test_wrap_legacy_tool_async() -> None:
    async def runner(text: str) -> str:
        await asyncio.sleep(0)
        return text[::-1]

    record = {
        "spec": {
            "name": "rev",
            "description": "Reverse",
            "parameters": {"type": "object", "properties": {}},
        },
        "execute": runner,
    }
    t = wrap_legacy_tool(record)
    out = _run(t.execute("c", {"text": "abc"}, None, None))
    assert out.content[0].text == "cba"


def test_wrap_legacy_tool_error_wraps() -> None:
    def boom(**_):
        raise RuntimeError("kaboom")

    record = {
        "spec": {"name": "boom", "description": "x", "parameters": {}},
        "execute": boom,
    }
    t = wrap_legacy_tool(record)
    out = _run(t.execute("c", {}, None, None))
    assert out.details and out.details.get("is_error") is True
    assert "kaboom" in out.content[0].text


def test_wrap_legacy_tool_idempotent() -> None:
    record = {
        "spec": {"name": "dup", "description": "x", "parameters": {}},
        "execute": lambda **_: "ok",
    }
    a = wrap_legacy_tool(record)
    b = wrap_legacy_tool(record)
    assert a is b      # second call short-circuits when already registered


def test_wrap_legacy_tool_rejects_bad_record() -> None:
    with pytest.raises(ValueError):
        wrap_legacy_tool({"spec": {}, "execute": lambda: None})
    with pytest.raises(ValueError):
        wrap_legacy_tool({"spec": {"name": "x"}, "execute": "not callable"})


def test_wrap_legacy_tool_unsafe_in_filters() -> None:
    record = {
        "spec": {"name": "unsafe", "description": "x", "parameters": {}},
        "execute": lambda **_: "ok",
    }
    wrap_legacy_tool(record, toolsets=["core"], unsafe_in=["wechat"])
    assert "unsafe" in [t.name for t in filter_for(toolset="core")]
    assert "unsafe" not in [t.name for t in filter_for(toolset="core", source="wechat")]


def test_registry_mirror_covers_every_legacy_tool() -> None:
    """After importing openprogram.tools, every name in ALL_TOOLS must
    have a mirror in the AgentTool registry. This is the migration
    contract — break it and dispatcher silently loses tools."""
    # Re-import so the autoload runs against a fresh registry
    reset_registry()
    import importlib
    import openprogram.tools as t_mod
    importlib.reload(t_mod)
    missing = [n for n in t_mod.ALL_TOOLS if t_mod.get_agent_tool(n) is None]
    assert missing == [], f"AgentTool registry missing: {missing}"
