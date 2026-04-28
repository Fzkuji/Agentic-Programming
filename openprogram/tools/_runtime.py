"""@tool decorator + runtime layer.

Single-format tool definitions. Authors write:

    from openprogram.tools import tool

    @tool
    async def bash(command: str, timeout: int = 30) -> str:
        '''Run a shell command. Returns combined stdout/stderr/exit_code.

        Args:
            command: Shell command to execute.
            timeout: Max seconds before kill.
        '''
        ...

The decorator returns an ``AgentTool`` instance compatible with
``openprogram.agent.agent_loop`` and registers it into a global
registry. Everything else (schema generation from type hints,
docstring parsing, char cap, persist-to-disk, sync→async, error
wrap, cancel/on_update injection, approval gating, caching) is
handled by this module so tool authors stay focused on business
logic.

Strategy chosen after reading hermes/openclaw/claude-code:
  - char-based caps, NOT token caps (token estimation is expensive
    and three references all use chars)
  - head+tail truncate with marker; no auto-summarize (lossy +
    extra LLM round-trip). LLM re-pages itself if needed
  - persist-full-to-disk (Claude Code mode) so the LLM can lazy-load
    the complete result via the read tool when the truncated view
    isn't enough
  - dynamic ceiling = min(per-tool max_result_chars,
    30% × context_window) so a single tool can't dominate context
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import re
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union, get_args, get_origin

from openprogram.agent.types import AgentTool, AgentToolResult
from openprogram.providers.types import ImageContent, TextContent


# ---------------------------------------------------------------------------
# Result type — ergonomic wrapper around AgentToolResult
# ---------------------------------------------------------------------------

@dataclass
class ToolReturn:
    """Optional structured return value. Tools can also return a plain
    str (auto-wrapped as TextContent) or an AgentToolResult directly.

    Use this when a tool needs to return text + images + structured
    JSON together, or to mark itself as an error result without
    raising an exception (for "the LLM should see this as a tool
    error" semantics).
    """
    text: Optional[str] = None
    images: list[Union[bytes, str]] = field(default_factory=list)
    json_data: Any = None
    is_error: bool = False


# ---------------------------------------------------------------------------
# Defaults — match references' values for sanity
# ---------------------------------------------------------------------------

DEFAULT_MAX_RESULT_CHARS = 30_000     # Bash tool default in Claude Code
MIN_KEEP_CHARS = 2_000                 # OpenClaw safety floor
DEFAULT_HEAD_RATIO = 0.7               # 70% head + 30% tail
TOOL_RESULTS_DIRNAME = "tool_results"  # for persist_full mode


def _tool_results_dir() -> Path:
    from openprogram.paths import get_state_dir
    p = get_state_dir() / TOOL_RESULTS_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, AgentTool] = {}
_toolset_membership: dict[str, set[str]] = {}      # tool_name → set of toolsets
_unsafe_in_channel: dict[str, set[str]] = {}       # tool_name → set of unsafe-in channels


def register(tool: AgentTool, *, toolsets: list[str] = (),
             unsafe_in: list[str] = ()) -> AgentTool:
    """Register a tool. Same name → overwrite (last import wins).

    `toolsets` lists the named groups this tool belongs to (e.g.
    ["core", "research"]). `unsafe_in` lists channel sources where
    the tool should be hidden by default (e.g. ["wechat"]).
    """
    _registry[tool.name] = tool
    if toolsets:
        _toolset_membership.setdefault(tool.name, set()).update(toolsets)
    if unsafe_in:
        _unsafe_in_channel.setdefault(tool.name, set()).update(unsafe_in)
    return tool


def get(name: str) -> Optional[AgentTool]:
    return _registry.get(name)


def all_tools() -> list[AgentTool]:
    return list(_registry.values())


def filter_for(*, names: Optional[list[str]] = None,
               toolset: Optional[str] = None,
               source: Optional[str] = None) -> list[AgentTool]:
    """Pick tools by name list, toolset name, or both. Excludes any
    tool flagged unsafe in `source`.
    """
    if names is not None:
        candidates = [t for t in (_registry.get(n) for n in names) if t is not None]
    elif toolset is not None:
        candidates = [t for t in _registry.values()
                      if toolset in _toolset_membership.get(t.name, ())]
    else:
        candidates = list(_registry.values())
    if source:
        candidates = [t for t in candidates
                      if source not in _unsafe_in_channel.get(t.name, ())]
    return candidates


def reset_registry() -> None:
    """Test-only — wipe registered tools so test imports are repeatable."""
    _registry.clear()
    _toolset_membership.clear()
    _unsafe_in_channel.clear()


# ---------------------------------------------------------------------------
# Schema generation from type hints + docstring
# ---------------------------------------------------------------------------

_DOC_ARG_RE = re.compile(r"^\s*(\w+)\s*:\s*(.+)$")

def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Returns (description, {arg_name: arg_doc}).

    Description = first paragraph. Arg docs from a Google-style
    "Args:" section. Other sections (Returns, Raises) ignored.
    """
    if not doc:
        return "", {}
    lines = inspect.cleandoc(doc).split("\n")
    desc_lines: list[str] = []
    args: dict[str, str] = {}
    in_args = False
    desc_done = False  # flips after first blank line — preserves rest
    current_arg: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args = True
            current_arg = None
            desc_done = True
            continue
        if in_args and stripped.lower() in ("returns:", "return:", "raises:",
                                              "yields:", "examples:"):
            in_args = False
            current_arg = None
            continue
        if in_args:
            m = _DOC_ARG_RE.match(line)
            if m:
                current_arg = m.group(1)
                args[current_arg] = m.group(2).strip()
            elif current_arg and stripped:
                args[current_arg] += " " + stripped
            continue
        if desc_done:
            continue
        if stripped:
            desc_lines.append(stripped)
        elif desc_lines:
            # First blank line ends the short-description paragraph
            # but we KEEP scanning (Args: may come later).
            desc_done = True
    return " ".join(desc_lines).strip(), args


_PRIMITIVE_TYPES = {
    str: "string", int: "integer", float: "number", bool: "boolean",
}


def _python_type_to_json_schema(tp: Any) -> dict[str, Any]:
    """Best-effort conversion. Handles primitives, Optional, list[X],
    dict, Literal[...], Union[A, B] (becomes {"oneOf": [...]}).
    Anything exotic falls back to {} (LLM gets a free-form value)."""
    if tp is None or tp is type(None):
        return {"type": "null"}
    if tp in _PRIMITIVE_TYPES:
        return {"type": _PRIMITIVE_TYPES[tp]}

    origin = get_origin(tp)
    args = get_args(tp)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Optional[X] → schema of X (caller marks it optional via
            # absence from required list).
            return _python_type_to_json_schema(non_none[0])
        return {"oneOf": [_python_type_to_json_schema(a) for a in non_none]}

    if origin in (list, tuple):
        if args:
            return {"type": "array", "items": _python_type_to_json_schema(args[0])}
        return {"type": "array"}

    if origin is dict:
        return {"type": "object"}

    # Literal[...]
    if hasattr(tp, "__class__") and tp.__class__.__name__ == "_LiteralGenericAlias":
        return {"enum": list(args)}

    return {}


def _build_parameters_schema(fn: Callable) -> dict[str, Any]:
    """Inspect fn's signature + docstring → JSON schema for `parameters`.

    Uses ``typing.get_type_hints`` so string annotations from
    ``from __future__ import annotations`` resolve to real types.
    Falls back gracefully when a hint references something the
    runtime can't resolve (returns {} for that arg's schema).
    """
    import typing
    sig = inspect.signature(fn)
    _, arg_docs = _parse_docstring(fn.__doc__ or "")
    try:
        resolved_hints = typing.get_type_hints(fn)
    except Exception:
        resolved_hints = {}

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        # Framework-injected kwargs — never exposed to the LLM
        if name in {"on_update", "cancel", "ctx", "context"}:
            continue
        # *args / **kwargs unsupported
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                           inspect.Parameter.VAR_KEYWORD):
            continue

        ann = resolved_hints.get(name)
        if ann is None and param.annotation is not inspect.Parameter.empty:
            ann = param.annotation  # last-resort raw annotation
        schema = _python_type_to_json_schema(ann) if ann is not None else {}
        if name in arg_docs:
            schema["description"] = arg_docs[name]
        properties[name] = schema
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        **({"required": required} if required else {}),
    }


# ---------------------------------------------------------------------------
# Result truncation
# ---------------------------------------------------------------------------

def _cap_result_text(text: str, max_chars: int,
                     *, head_ratio: float = DEFAULT_HEAD_RATIO) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(max_chars, MIN_KEEP_CHARS)
    head = int(keep * head_ratio)
    tail = keep - head
    elided = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n[... {elided:,} chars elided of {len(text):,} total —"
        f" call again with narrower scope or check the persisted file ...]\n\n"
        + text[-tail:]
    )


def _persist_full_result(call_id: str, text: str) -> Path:
    p = _tool_results_dir() / f"{call_id}.txt"
    p.write_text(text, encoding="utf-8")
    return p


def _normalize_result(raw: Any, *, call_id: str, max_chars: int,
                      persist_full: bool, head_ratio: float) -> AgentToolResult:
    """Convert tool's raw return value into an AgentToolResult.

    Accepted shapes:
      - str → TextContent
      - dict / list → JSON-serialized as TextContent
      - ToolReturn → text + images + json
      - AgentToolResult → passthrough

    Then applies char cap with optional persist-to-disk for the full
    version (so the LLM can lazy-load via a read tool when needed).
    """
    if isinstance(raw, AgentToolResult):
        return raw

    images: list[ImageContent] = []
    is_error = False
    json_payload: Any = None
    text_part: Optional[str] = None

    if isinstance(raw, ToolReturn):
        text_part = raw.text
        is_error = raw.is_error
        json_payload = raw.json_data
        for img in raw.images:
            if isinstance(img, bytes):
                import base64
                b64 = base64.b64encode(img).decode("ascii")
                images.append(ImageContent(data=b64, media_type="image/png"))
            elif isinstance(img, str):
                # Assume already-base64 or URL — let the provider sort it out
                images.append(ImageContent(data=img, media_type="image/png"))
    elif isinstance(raw, str):
        text_part = raw
    elif raw is None:
        text_part = ""
    else:
        try:
            text_part = json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            text_part = repr(raw)

    if text_part is None:
        text_part = ""

    if json_payload is not None and not text_part:
        try:
            text_part = json.dumps(json_payload, ensure_ascii=False, default=str)
        except Exception:
            pass

    # Apply cap; optionally persist full version.
    full_text = text_part
    if len(full_text) > max_chars:
        if persist_full:
            try:
                p = _persist_full_result(call_id, full_text)
                marker = f"\n\n[Full result ({len(full_text):,} chars) saved at {p} — read tool can fetch it]"
            except Exception:
                marker = ""
            text_part = _cap_result_text(full_text, max_chars,
                                          head_ratio=head_ratio) + marker
        else:
            text_part = _cap_result_text(full_text, max_chars,
                                          head_ratio=head_ratio)

    content: list[Any] = []
    if text_part:
        content.append(TextContent(text=text_part))
    content.extend(images)
    if not content:
        content.append(TextContent(text=""))

    details: dict[str, Any] = {}
    if is_error:
        details["is_error"] = True
    if json_payload is not None:
        details["json"] = json_payload

    return AgentToolResult(content=content, details=details or None)


# ---------------------------------------------------------------------------
# Approval gate evaluator
# ---------------------------------------------------------------------------

def _evaluate_approval(
    requires_approval: Union[bool, Callable[..., Any], None],
    args: dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """Returns (needs_approval, reason).

    - True → always require approval (reason=None)
    - callable → invoke with **args; bool result, or string reason
      (truthy str = require, return the reason for the UI prompt)
    """
    if requires_approval is None or requires_approval is False:
        return False, None
    if requires_approval is True:
        return True, None
    try:
        verdict = requires_approval(**args)
    except Exception:
        # Conservative: if the gate function blows up, require approval
        return True, "approval gate raised; defaulting to require"
    if verdict is True:
        return True, None
    if verdict is False or verdict is None:
        return False, None
    if isinstance(verdict, str):
        return True, verdict
    return bool(verdict), None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    value: AgentToolResult
    expires_at: float


_cache: dict[str, _CacheEntry] = {}


def _cache_key(name: str, args: dict[str, Any]) -> str:
    payload = json.dumps({"name": name, "args": args},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_get(key: str) -> Optional[AgentToolResult]:
    e = _cache.get(key)
    if e is None:
        return None
    if e.expires_at < time.time():
        _cache.pop(key, None)
        return None
    return e.value


def _cache_set(key: str, value: AgentToolResult, ttl: float) -> None:
    _cache[key] = _CacheEntry(value=value, expires_at=time.time() + ttl)


# ---------------------------------------------------------------------------
# The decorator
# ---------------------------------------------------------------------------

def tool(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    label: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS,
    persist_full: bool = False,
    head_ratio: float = DEFAULT_HEAD_RATIO,
    requires_approval: Union[bool, Callable[..., Any], None] = None,
    cache: bool = False,
    cache_ttl: float = 300.0,
    timeout: Optional[float] = None,
    toolset: list[str] = (),
    unsafe_in: list[str] = (),
    register_globally: bool = True,
):
    """Wrap a plain function as a registered AgentTool.

    Author writes a normal sync/async Python function with type
    hints and a Google-style docstring. The decorator extracts:

      - name: from override or fn.__name__
      - description: from override or first docstring paragraph
      - parameters JSON schema: from override or fn signature +
        docstring "Args:" section

    Runtime extras (declarative kwargs):

      max_result_chars: cap for textual output. Beyond this we
        head+tail truncate with a marker.
      persist_full: when True, oversized results are also saved
        whole to ~/.agentic/tool_results/<call_id>.txt and the
        marker mentions the path. The read tool can fetch it.
      requires_approval: True | False | callable(**args) → bool | str.
        Returning a str triggers approval AND uses the str as the
        reason shown to the user.
      cache + cache_ttl: memoize results keyed on (name, args).
      timeout: hard kill after N seconds (asyncio.wait_for).
      toolset / unsafe_in: registry-side metadata.

    Framework injects two optional kwargs into the wrapped fn if it
    declares them in its signature:

      cancel: asyncio.Event — set when the user aborts. Long-running
        tools should poll cancel.is_set() periodically.
      on_update: callable(text) — call with progress strings; surfaces
        as tool_execution_update events to clients.
    """
    if fn is None:
        # Used as @tool(...) — return the actual decorator
        def _inner(f):
            return tool(
                f, name=name, description=description, label=label,
                parameters=parameters,
                max_result_chars=max_result_chars,
                persist_full=persist_full, head_ratio=head_ratio,
                requires_approval=requires_approval,
                cache=cache, cache_ttl=cache_ttl, timeout=timeout,
                toolset=toolset, unsafe_in=unsafe_in,
                register_globally=register_globally,
            )
        return _inner

    actual_name = name or fn.__name__
    sig = inspect.signature(fn)
    doc_desc, _ = _parse_docstring(fn.__doc__ or "")
    actual_description = description or doc_desc or fn.__name__
    actual_parameters = parameters or _build_parameters_schema(fn)
    is_async_fn = inspect.iscoroutinefunction(fn)
    accepts_cancel = "cancel" in sig.parameters
    accepts_on_update = "on_update" in sig.parameters

    async def _execute(call_id: str,
                        args: dict[str, Any],
                        cancel_event,        # asyncio.Event | None
                        on_update_cb) -> AgentToolResult:        # callable | None
        # Validate args against signature so the tool fn doesn't
        # silently see a typo'd kwarg the LLM made up.
        passable_kwargs = dict(args)
        if accepts_cancel:
            passable_kwargs["cancel"] = cancel_event
        if accepts_on_update:
            def _on_update(text: str) -> None:
                if on_update_cb is not None:
                    try:
                        on_update_cb(text)
                    except Exception:
                        pass
            passable_kwargs["on_update"] = _on_update

        # Cache check
        if cache:
            key = _cache_key(actual_name, args)
            hit = _cache_get(key)
            if hit is not None:
                return hit

        async def _invoke():
            if is_async_fn:
                return await fn(**passable_kwargs)
            # sync fn: run in default executor so we don't block the
            # asyncio loop. Use get_running_loop (we know one exists,
            # we're inside an async function); get_event_loop is
            # deprecated when no loop is running.
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(**passable_kwargs))

        try:
            if timeout is not None:
                raw = await asyncio.wait_for(_invoke(), timeout=timeout)
            else:
                raw = await _invoke()
        except asyncio.TimeoutError:
            return AgentToolResult(
                content=[TextContent(text=f"[error] tool {actual_name} timed out after {timeout}s")],
                details={"is_error": True, "timeout": True},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(text=f"[error] {type(e).__name__}: {e}")],
                details={"is_error": True,
                          "trace": traceback.format_exc()[:2000]},
            )

        result = _normalize_result(
            raw, call_id=call_id,
            max_chars=max_result_chars,
            persist_full=persist_full,
            head_ratio=head_ratio,
        )

        if cache and not (result.details and result.details.get("is_error")):
            _cache_set(_cache_key(actual_name, args), result, cache_ttl)

        return result

    # Attach approval gate as a sidecar attribute — dispatcher reads
    # this before invoking the tool, decides whether to fire an
    # approval_request envelope.
    agent_tool = AgentTool(
        name=actual_name,
        description=actual_description,
        parameters=actual_parameters,
        label=label or actual_name,
        execute=_execute,
    )
    setattr(agent_tool, "_requires_approval", requires_approval)

    if register_globally:
        register(agent_tool, toolsets=list(toolset), unsafe_in=list(unsafe_in))

    return agent_tool


# ---------------------------------------------------------------------------
# Dispatcher hook — read approval policy off a tool
# ---------------------------------------------------------------------------

def tool_requires_approval(t: AgentTool, args: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Resolve a tool's approval policy for these args. Used by the
    dispatcher right before executing the tool."""
    policy = getattr(t, "_requires_approval", None)
    return _evaluate_approval(policy, args)


# ---------------------------------------------------------------------------
# Backward compat — let legacy callers still consume the old dict shape
# ---------------------------------------------------------------------------

def wrap_legacy_tool(record: dict[str, Any], *,
                     toolsets: list[str] = (),
                     unsafe_in: list[str] = (),
                     max_result_chars: int = DEFAULT_MAX_RESULT_CHARS,
                     persist_full: bool = False) -> AgentTool:
    """Adapt a legacy ``{"spec": {...}, "execute": fn}`` dict tool into an
    AgentTool, register it. Lets us pick up tools that haven't yet been
    rewritten with the @tool decorator without losing them from the
    chat-side registry.

    Idempotent on the same record; can be called from registry module
    init multiple times safely.
    """
    spec = record.get("spec") or {}
    execute_fn = record.get("execute")
    if not spec.get("name") or not callable(execute_fn):
        raise ValueError(
            f"wrap_legacy_tool: record missing spec.name or execute (got {list(record.keys())})"
        )

    # If the wrapped fn is already an AgentTool's execute (e.g. round-
    # trip through to_dict_tool), prefer the original AgentTool from
    # the registry to avoid double-wrap chains.
    existing = _registry.get(spec["name"])
    if existing is not None:
        return existing

    is_async = inspect.iscoroutinefunction(execute_fn)

    async def _execute(call_id, args, cancel, on_update):
        try:
            if is_async:
                raw = await execute_fn(**args)
            else:
                loop = asyncio.get_running_loop()
                raw = await loop.run_in_executor(None, lambda: execute_fn(**args))
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(text=f"[error] {type(e).__name__}: {e}")],
                details={"is_error": True,
                          "trace": traceback.format_exc()[:2000]},
            )
        return _normalize_result(
            raw, call_id=call_id,
            max_chars=max_result_chars,
            persist_full=persist_full,
            head_ratio=DEFAULT_HEAD_RATIO,
        )

    agent_tool = AgentTool(
        name=spec["name"],
        description=spec.get("description") or spec["name"],
        parameters=spec.get("parameters") or {"type": "object", "properties": {}},
        label=spec["name"],
        execute=_execute,
    )
    return register(agent_tool, toolsets=list(toolsets), unsafe_in=list(unsafe_in))


def to_dict_tool(t: AgentTool) -> dict[str, Any]:
    """Adapter for the legacy `runtime.exec(tools=[dict, ...])` path.

    Wraps an AgentTool back into the {"spec": {...}, "execute": fn}
    dict the old code expects. The synchronous execute() runs the
    AgentTool.execute coroutine via a private event loop — slow if
    called inside an async context, but the legacy path is sync
    anyway.
    """
    def _exec(**kwargs) -> str:
        coro = t.execute(uuid.uuid4().hex[:12], kwargs, None, None)
        # Always run in a fresh loop on a worker thread so we don't
        # care whether the caller already has one running. Slow but
        # the legacy path is sync anyway.
        import threading
        box: dict[str, Any] = {}
        def _runner():
            sub = asyncio.new_event_loop()
            try:
                box["res"] = sub.run_until_complete(coro)
            finally:
                sub.close()
        th = threading.Thread(target=_runner)
        th.start()
        th.join()
        result = box.get("res")
        # Flatten content list to a plain string.
        if result is None:
            return ""
        parts = []
        for c in (result.content or []):
            if hasattr(c, "text"):
                parts.append(c.text)
        return "".join(parts)

    return {
        "spec": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
        "execute": _exec,
    }
