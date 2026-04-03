"""
@agentic_function — decorator that records function execution into the Context tree.

This is the only thing users need to add to their code. Everything else
(tree management, context injection, LLM recording) happens automatically.

Three settings, all optional:

    render      How others see my results when they call summarize().
                Default: "summary" (one-liner with output and duration).

    summarize   What context I see when I call the LLM via runtime.exec().
                Default: None → see all ancestors + all same-level siblings.
                Pass a dict to customize: {"depth": 1, "siblings": 3}

    compress    After I finish, hide my children from summarize().
                Default: False → children are visible if requested via branch=.
                Set True for high-level functions whose internal steps
                are irrelevant to the outside world.

Usage:

    from agentic import agentic_function

    # Simplest: just decorate. All defaults.
    @agentic_function
    def observe(task):
        ...

    # Customized: detailed rendering, limited context, compressed output.
    @agentic_function(render="detail", summarize={"depth": 1, "siblings": 3}, compress=True)
    def navigate(target):
        ...
"""

from __future__ import annotations

import functools
import inspect
import time
from typing import Callable, Optional

from agentic.context import Context, _current_ctx


def agentic_function(
    fn: Optional[Callable] = None,
    *,
    render: str = "summary",
    summarize: Optional[dict] = None,
    compress: bool = False,
):
    """
    Decorator: marks a function as an Agentic Function.

    Every decorated function is unconditionally recorded into the Context tree.
    There is no opt-out — if you decorate it, it gets recorded. If you don't
    want recording, don't decorate it.

    Args:
        render:     How others see my results via summarize().

                    "trace"   — everything: prompt, I/O, raw LLM reply, error
                    "detail"  — name(params) → status | input | output
                    "summary" — name: output_snippet duration  (DEFAULT)
                    "result"  — return value only (JSON)
                    "silent"  — not shown

                    This is a default. Callers can override per-query:
                    ctx.summarize(level="detail") overrides all nodes' render.

        summarize:  What context I see when runtime.exec() auto-injects context.

                    Dict of keyword arguments passed to ctx.summarize().
                    Example: {"depth": 1, "siblings": 3}

                    If None (default), runtime.exec() calls ctx.summarize()
                    with no arguments → all ancestors + all siblings.

                    Common patterns:
                      {"depth": 0, "siblings": 0}    — isolated, see nothing
                      {"depth": 1, "siblings": 1}    — parent + last sibling
                      {"siblings": 3}                 — all ancestors + last 3

        compress:   After this function completes, hide children from summarize().

                    When True, other functions calling summarize() see only this
                    node's own rendered result — the children (sub-calls) are NOT
                    expanded, even if branch= is used.

                    The children are still fully recorded in the tree. tree() and
                    save() always show everything. compress only affects summarize().

                    Default: False.
    """
    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Capture call arguments
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            params = dict(bound.arguments)

            # Find or create parent node
            parent = _current_ctx.get(None)
            if parent is None:
                # First decorated call in this thread → create root
                parent = Context(
                    name="root",
                    start_time=time.time(),
                    status="running",
                )
                _current_ctx.set(parent)

            # Create this call's node
            ctx = Context(
                name=fn.__name__,
                prompt=fn.__doc__ or "",
                params=params,
                parent=parent,
                render=render,
                compress=compress,
                start_time=time.time(),
                _summarize_kwargs=summarize,
            )
            parent.children.append(ctx)

            # Set as current context for the duration of the call
            token = _current_ctx.set(ctx)
            try:
                result = fn(*args, **kwargs)
                ctx.output = result
                ctx.status = "success"
                return result
            except Exception as e:
                ctx.error = str(e)
                ctx.status = "error"
                raise
            finally:
                ctx.end_time = time.time()
                _current_ctx.reset(token)

        # Mark for introspection
        wrapper._is_agentic = True
        return wrapper

    # Support both @agentic_function and @agentic_function(...)
    if fn is not None:
        return decorator(fn)
    return decorator
