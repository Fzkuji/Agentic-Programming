"""
Tests for the Runtime class.
"""

import pytest
from pydantic import BaseModel
from harness.function import Function
from harness.session import Session
from harness.runtime import Runtime


class MockSession(Session):
    def __init__(self, reply: str):
        self._reply = reply

    def send(self, message: str) -> str:
        return self._reply


class SimpleResult(BaseModel):
    status: str
    value: str


def test_runtime_executes_function_in_isolation():
    """Runtime creates a fresh session for each execution."""
    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        return MockSession('{"status": "ok", "value": "done"}')

    runtime = Runtime(session_factory=factory)
    fn = Function("test", "A test", "Do it", SimpleResult)

    runtime.execute(fn, {"task": "t1"})
    runtime.execute(fn, {"task": "t2"})

    # Factory was called twice — two separate sessions
    assert call_count["n"] == 2


def test_runtime_returns_typed_result():
    """Runtime returns a validated Pydantic model."""
    runtime = Runtime(
        session_factory=lambda: MockSession('{"status": "ok", "value": "hello"}')
    )
    fn = Function("test", "A test", "Do it", SimpleResult)
    result = runtime.execute(fn, {"task": "test"})

    assert isinstance(result, SimpleResult)
    assert result.status == "ok"
    assert result.value == "hello"


def test_runtime_from_session_class():
    """Runtime.from_session_class is a convenience constructor."""
    runtime = Runtime.from_session_class(MockSession, reply='{"status": "ok", "value": "x"}')
    fn = Function("test", "A test", "Do it", SimpleResult)
    result = runtime.execute(fn, {"task": "test"})
    assert result.status == "ok"
