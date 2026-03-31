"""
Runtime — the execution environment for Functions.

In traditional programming:
    - You write a function in Python
    - The Python interpreter (runtime) executes it
    - The runtime doesn't decide what to run — it just runs what it's given

In Agentic Programming:
    - You define a Function (name, body, return_type)
    - The Runtime (an LLM Session) executes it
    - The Runtime doesn't decide what to run — it just runs what it's given

Runtimes are ephemeral by default: created for one Function call, then destroyed.
This is how context isolation works — each Function execution starts with a clean slate.

Usage:
    runtime = Runtime(session_factory=lambda: AnthropicSession(model="claude-haiku"))
    result = runtime.execute(observe_fn, context={"task": "click login"})
    # The Session was created, used, and destroyed. Context is gone.
"""

from __future__ import annotations

from typing import Callable, TypeVar
from pydantic import BaseModel

from harness.function import Function
from harness.session import Session

T = TypeVar("T", bound=BaseModel)


class Runtime:
    """
    The execution environment for Functions.

    Like a Python interpreter — it runs Functions and returns typed results.
    Each execution gets a fresh Session (context isolation).

    Args:
        session_factory:  A callable that creates a new Session each time.
                          This ensures each Function execution is isolated.
    """

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def execute(self, function: Function, context: dict) -> T:
        """
        Execute a Function in an isolated Session.

        Creates a new Session, runs the Function, returns the result,
        and discards the Session (context gone).

        Args:
            function:  The Function to execute
            context:   Input context (params are extracted by the Function)

        Returns:
            A validated instance of the Function's return_type

        Raises:
            FunctionError: if the Function cannot produce valid output
        """
        session = self._session_factory()
        return function.call(session=session, context=context)

    @staticmethod
    def from_session_class(session_class: type, **kwargs) -> "Runtime":
        """
        Convenience: create a Runtime from a Session class and its constructor args.

        Example:
            runtime = Runtime.from_session_class(AnthropicSession, model="claude-haiku")
        """
        return Runtime(session_factory=lambda: session_class(**kwargs))
