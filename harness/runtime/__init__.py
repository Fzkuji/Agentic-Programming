"""
Runtime — the execution environment for Functions.

Like Python's interpreter: it runs Functions and returns typed results.

Two context modes (set per-Function via function.scope):

    isolated    Fresh Session each time. No prior context. Clean slate.
                Like calling a pure function — no side effects visible.

    chained     Shares a Session with prior chained calls in the same sequence.
                Each Function sees the call stack (who called whom) and
                prior Functions' I/O summaries (not their full reasoning).
                Like sequential statements in a function body — earlier
                results are visible, but internals are not.

How chained mode preserves KV cache:
    The Session is reused across chained calls. Prior Function results
    are appended (not inserted/modified), so the prefix stays intact
    and KV cache hits are maximized. When a chained sequence ends,
    the Session is discarded and only I/O summaries survive.
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable, TypeVar, Optional
from pydantic import BaseModel

from harness.function import Function
from harness.session import Session

T = TypeVar("T", bound=BaseModel)


class Runtime:
    """
    The execution environment for Functions.

    Args:
        session_factory:  Creates a new Session for each isolated execution
                          (or for each new chained sequence).
    """

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Single execution
    # ------------------------------------------------------------------

    def execute(self, function: Function, context: dict) -> T:
        """
        Execute a single Function. Always uses a fresh Session (isolated).
        """
        session = self._session_factory()
        return function.call(session=session, context=context)

    # ------------------------------------------------------------------
    # Chained execution
    # ------------------------------------------------------------------

    def execute_chain(
        self,
        functions: list[Function],
        context: dict,
    ) -> list:
        """
        Execute a sequence of Functions with shared context.

        For each Function in the chain:
            - If scope == "isolated": new Session, only sees its own params
            - If scope == "chained": reuses the chain Session, sees prior I/O

        After the entire chain completes, the shared Session is discarded.
        Only the structured I/O summaries survive in the returned results.

        This maximizes KV cache hits within a chain (prefix-append only)
        while keeping the overall context bounded.

        Args:
            functions:  Ordered list of Functions to execute
            context:    Initial context

        Returns:
            List of results (Pydantic models) in order.
            If a Function fails, returns FunctionError for that position
            and stops the chain.
        """
        from harness.function import FunctionError

        chain_session = None  # lazy-created for chained Functions
        chain_history = []    # I/O summaries for chained Functions
        results = []

        for fn in functions:
            if fn.scope == Function.SCOPE_CHAINED:
                # Chained: reuse Session, append prior I/O
                if chain_session is None:
                    chain_session = self._session_factory()

                # Build context with call stack info + prior I/O summaries
                chain_context = dict(context)
                if chain_history:
                    chain_context["_prior_results"] = chain_history

                try:
                    result = fn.call(session=chain_session, context=chain_context)
                    result_dict = result.model_dump()

                    # Record I/O summary for next chained Function
                    chain_history.append({
                        "function": fn.name,
                        "input_params": fn.params,
                        "output": result_dict,
                    })

                    # Also store in main context
                    context[fn.name] = result_dict
                    results.append(result)

                except FunctionError as e:
                    results.append(e)
                    break

            else:
                # Isolated: fresh Session, no shared state
                try:
                    result = self.execute(fn, context)
                    context[fn.name] = result.model_dump()
                    results.append(result)
                except FunctionError as e:
                    results.append(e)
                    break

        # Chain ends → shared Session discarded (GC)
        # Only context[fn.name] (structured results) survive
        return results

    # ------------------------------------------------------------------
    # Async
    # ------------------------------------------------------------------

    async def execute_async(self, function: Function, context: dict) -> T:
        """Async version of execute()."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, function, context)

    async def execute_parallel(self, calls: list[tuple[Function, dict]]) -> list:
        """
        Execute multiple Functions concurrently, each in its own Session.

        Like multiprocessing — each call is fully isolated.
        """
        tasks = [self.execute_async(fn, ctx) for fn, ctx in calls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @staticmethod
    def from_session_class(session_class: type, **kwargs) -> "Runtime":
        """Create a Runtime from a Session class and constructor args."""
        return Runtime(session_factory=lambda: session_class(**kwargs))
