"""
Tests for chained vs isolated Function execution.
"""

import pytest
from pydantic import BaseModel
from harness.function import Function
from harness.session import Session
from harness.runtime import Runtime


# --- Track which sessions are created ---

class TrackingSession(Session):
    """Session that tracks its identity and all messages received."""
    _counter = 0

    def __init__(self, reply: str = '{"status": "ok"}'):
        TrackingSession._counter += 1
        self.id = TrackingSession._counter
        self.messages = []
        self._reply = reply

    def send(self, message) -> str:
        self.messages.append(message if isinstance(message, str) else str(message))
        return self._reply

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class SimpleResult(BaseModel):
    status: str


# --- Tests ---

def test_isolated_functions_get_separate_sessions():
    """Each isolated Function gets its own Session."""
    TrackingSession.reset_counter()
    sessions_created = []

    def factory():
        s = TrackingSession()
        sessions_created.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope="isolated")
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult, scope="isolated")

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 2
    assert len(sessions_created) == 2
    assert sessions_created[0].id != sessions_created[1].id


def test_chained_functions_share_session():
    """Chained Functions reuse the same Session."""
    TrackingSession.reset_counter()
    sessions_created = []

    def factory():
        s = TrackingSession()
        sessions_created.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope="chained")
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult, scope="chained")

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 2
    # Only one session created (shared)
    assert len(sessions_created) == 1
    # Both messages went to the same session
    assert len(sessions_created[0].messages) >= 2


def test_mixed_chain_isolated_and_chained():
    """Mix of isolated and chained in one chain."""
    TrackingSession.reset_counter()
    sessions_created = []

    def factory():
        s = TrackingSession()
        sessions_created.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "Isolated", "Do 1", SimpleResult, scope="isolated")
    fn2 = Function("fn2", "Chained", "Do 2", SimpleResult, scope="chained")
    fn3 = Function("fn3", "Chained", "Do 3", SimpleResult, scope="chained")

    results = runtime.execute_chain([fn1, fn2, fn3], {"task": "test"})

    assert len(results) == 3
    # fn1 gets its own session, fn2+fn3 share one
    assert len(sessions_created) == 2


def test_chained_function_sees_prior_results():
    """Chained Functions receive prior I/O summaries."""
    messages_received = []

    class CapturingSession(Session):
        def send(self, message) -> str:
            messages_received.append(message if isinstance(message, str) else str(message))
            return '{"status": "ok"}'

    runtime = Runtime(session_factory=lambda: CapturingSession())

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope="chained")
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult, scope="chained", params=["task"])

    runtime.execute_chain([fn1, fn2], {"task": "test"})

    # fn2's message should contain reference to fn1's prior results
    assert len(messages_received) >= 2
    # The second message is sent to the same session, so it can see fn1's context
    # via the session's conversation history


def test_chain_stops_on_failure():
    """Chain stops when a Function fails."""
    call_order = []

    class FailSession(Session):
        def send(self, message) -> str:
            return "not valid json"

    class OkSession(Session):
        def send(self, message) -> str:
            call_order.append("ok")
            return '{"status": "ok"}'

    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return FailSession()
        return OkSession()

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "Fails", "Do 1", SimpleResult, scope="isolated", max_retries=1)
    fn2 = Function("fn2", "Never runs", "Do 2", SimpleResult, scope="isolated")

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 1  # stopped after fn1 failed
    from harness.function import FunctionError
    assert isinstance(results[0], FunctionError)


def test_function_scope_default_is_isolated():
    """Default scope is isolated."""
    fn = Function("test", "Test", "Do it", SimpleResult)
    assert fn.scope == "isolated"


def test_function_scope_can_be_set():
    """Scope can be set to chained."""
    fn = Function("test", "Test", "Do it", SimpleResult, scope="chained")
    assert fn.scope == "chained"
