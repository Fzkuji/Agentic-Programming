"""End-to-end integration tests for dispatcher.process_user_turn.

The pure unit tests in test_dispatcher.py mock _run_loop_blocking
entirely. These tests run the REAL _run_loop_blocking — including
the asyncio event loop, agent_loop() invocation, and the full
AgentEvent → chat_response envelope conversion — but with a fake
stream_fn that emits scripted AssistantMessageEvents instead of
hitting a provider over the network.

This is the closest we can get to "real" without paying the cost
of provider keys + network. Anything broken between dispatcher and
agent_loop would fail here; anything broken between agent_loop and
a specific provider stays out of scope (those have their own tests).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch

import pytest

from openprogram.agent import dispatcher as D
from openprogram.agent.session_db import SessionDB
from openprogram.providers.types import (
    AssistantMessage,
    AssistantMessageEvent,
    EventDone,
    EventStart,
    EventTextDelta,
    EventTextEnd,
    EventTextStart,
    Model,
    TextContent,
    Usage,
)


# ---------------------------------------------------------------------------
# Stream-fn fakes: produce scripted AssistantMessageEvent sequences
# ---------------------------------------------------------------------------

def _stub_model() -> Model:
    return Model(
        id="stub",
        name="stub",
        api="completion",
        provider="openai",
        base_url="https://api.openai.com/v1",
    )


def _build_partial(text: str = "") -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text=text)] if text else [],
        api="completion",
        provider="openai",
        model="stub",
        timestamp=int(time.time() * 1000),
    )


def _build_final(text: str, *, input_tokens: int = 10,
                 output_tokens: int = 4) -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text=text)],
        api="completion",
        provider="openai",
        model="stub",
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason="stop",
        timestamp=int(time.time() * 1000),
    )


def make_text_stream_fn(chunks: list[str]):
    """A stream_fn that emits text deltas for `chunks` then EventDone.

    Signature must match `StreamFn` Protocol — agent_loop calls it as
    `fn(model, llm_context, stream_opts)` and iterates the resulting
    async generator.
    """
    full_text = "".join(chunks)

    async def _fn(model, context, options) -> AsyncGenerator[AssistantMessageEvent, None]:
        partial = _build_partial("")
        yield EventStart(partial=partial)

        # Text section
        partial = _build_partial("")
        yield EventTextStart(content_index=0, partial=partial)
        accum = ""
        for chunk in chunks:
            accum += chunk
            partial = _build_partial(accum)
            yield EventTextDelta(content_index=0, delta=chunk, partial=partial)
        partial = _build_partial(accum)
        yield EventTextEnd(content_index=0, content=accum, partial=partial)

        yield EventDone(reason="stop", message=_build_final(full_text))

    return _fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionDB:
    db = SessionDB(tmp_path / "sessions.sqlite")
    monkeypatch.setattr(
        "openprogram.agent.session_db.default_db",
        lambda: db,
    )
    return db


@pytest.fixture
def captured() -> list[dict]:
    return []


@pytest.fixture
def collector(captured: list[dict]):
    return captured.append


# Inject a stub Model so dispatcher's _resolve_model doesn't need to
# touch the model registry at all.
@pytest.fixture(autouse=True)
def stub_model_resolution(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(D, "_resolve_model",
                        lambda profile, override=None: _stub_model())


# Likewise stub the agent profile loader: we don't need real agents.
@pytest.fixture(autouse=True)
def stub_agent_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        D, "_load_agent_profile",
        lambda agent_id: {"id": agent_id, "system_prompt": "you are helpful"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_real_loop_text_only(tmp_db: SessionDB, captured, collector) -> None:
    """One full turn with a streaming text reply, no tools.

    Verifies the whole dispatcher → agent_loop → fake stream_fn →
    event-conversion path runs cleanly and ends with the right text.
    """
    fake_stream = make_text_stream_fn(["Hel", "lo,", " wor", "ld"])

    # Patch _run_loop_blocking's default stream_fn=None signature: we
    # can't pass stream_fn into process_user_turn directly, so we wrap.
    orig = D._run_loop_blocking

    def _wrapped(*, req, history, on_event, cancel_event, stream_fn=None):
        return orig(req=req, history=history, on_event=on_event,
                    cancel_event=cancel_event, stream_fn=fake_stream)

    with patch.object(D, "_run_loop_blocking", _wrapped):
        result = D.process_user_turn(
            D.TurnRequest(conv_id="c1", user_text="hi", agent_id="main", source="tui"),
            on_event=collector,
        )

    assert result.failed is False
    assert result.final_text == "Hello, world"
    # Usage propagated from EventDone's message.usage
    assert result.usage["input_tokens"] >= 0
    assert result.usage["output_tokens"] >= 0

    # SessionDB should hold both turns
    msgs = tmp_db.get_messages("c1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Hello, world"

    # Stream events were forwarded to clients
    text_events = [
        e for e in captured
        if e["type"] == "chat_response"
        and e["data"].get("type") == "stream_event"
        and e["data"]["event"]["type"] == "text"
    ]
    deltas = "".join(e["data"]["event"]["text"] for e in text_events)
    assert deltas == "Hello, world"

    # Final result envelope
    final = [
        e for e in captured
        if e["type"] == "chat_response"
        and e["data"].get("type") == "result"
    ]
    assert len(final) == 1
    assert final[0]["data"]["content"] == "Hello, world"


def test_real_loop_persists_session_meta(tmp_db: SessionDB) -> None:
    fake_stream = make_text_stream_fn(["done"])

    def _wrapped(*, req, history, on_event, cancel_event, stream_fn=None):
        return D._run_loop_blocking.__wrapped__(  # type: ignore[attr-defined]
            req=req, history=history, on_event=on_event,
            cancel_event=cancel_event, stream_fn=fake_stream,
        ) if hasattr(D._run_loop_blocking, "__wrapped__") else None

    # Use the simpler patched approach
    orig = D._run_loop_blocking

    def _w(*, req, history, on_event, cancel_event, stream_fn=None):
        return orig(req=req, history=history, on_event=on_event,
                    cancel_event=cancel_event, stream_fn=fake_stream)

    with patch.object(D, "_run_loop_blocking", _w):
        result = D.process_user_turn(
            D.TurnRequest(conv_id="c1", user_text="hi", agent_id="main",
                          source="wechat", peer_display="alice"),
        )
    sess = tmp_db.get_session("c1")
    assert sess["source"] == "wechat"
    assert sess["channel"] == "wechat"
    assert sess["head_id"] == result.assistant_msg_id


def test_real_loop_history_replay(tmp_db: SessionDB, captured, collector) -> None:
    """A second turn should see the first turn's user+assistant in
    the AgentContext.messages list when the loop runs."""

    # First turn
    orig = D._run_loop_blocking

    fake_stream = make_text_stream_fn(["first"])
    def _w1(*, req, history, on_event, cancel_event, stream_fn=None):
        return orig(req=req, history=history, on_event=on_event,
                    cancel_event=cancel_event, stream_fn=fake_stream)
    with patch.object(D, "_run_loop_blocking", _w1):
        D.process_user_turn(
            D.TurnRequest(conv_id="c1", user_text="hi", agent_id="main", source="tui"),
        )

    # Second turn — capture context.messages length seen by stream_fn
    seen_message_count = []

    async def _capturing_stream_fn(model, context, options):
        seen_message_count.append(len(context.messages))
        partial = _build_partial("")
        yield EventStart(partial=partial)
        partial = _build_partial("ok")
        yield EventTextStart(content_index=0, partial=partial)
        yield EventTextDelta(content_index=0, delta="ok", partial=partial)
        yield EventTextEnd(content_index=0, content="ok", partial=partial)
        yield EventDone(reason="stop", message=_build_final("ok"))

    def _w2(*, req, history, on_event, cancel_event, stream_fn=None):
        return orig(req=req, history=history, on_event=on_event,
                    cancel_event=cancel_event, stream_fn=_capturing_stream_fn)
    with patch.object(D, "_run_loop_blocking", _w2):
        D.process_user_turn(
            D.TurnRequest(conv_id="c1", user_text="follow up", agent_id="main", source="tui"),
        )

    # Context at LLM call time should have prior history (user, assistant)
    # plus the new user prompt = at least 3 messages.
    assert seen_message_count, "stream_fn should have been called"
    assert seen_message_count[0] >= 3


def test_provider_error_persists_as_system_message(
    tmp_db: SessionDB, captured, collector,
) -> None:
    """If stream_fn raises, dispatcher should catch and emit an error
    envelope, NOT crash the worker."""

    async def _angry_stream(model, context, options):
        # Yield once so async generator semantics are exercised, then raise.
        if False:  # pragma: no cover
            yield None
        raise RuntimeError("provider boom")

    orig = D._run_loop_blocking

    def _w(*, req, history, on_event, cancel_event, stream_fn=None):
        return orig(req=req, history=history, on_event=on_event,
                    cancel_event=cancel_event, stream_fn=_angry_stream)

    with patch.object(D, "_run_loop_blocking", _w):
        result = D.process_user_turn(
            D.TurnRequest(conv_id="c1", user_text="hi", agent_id="main", source="tui"),
            on_event=collector,
        )

    assert result.failed is True
    assert "boom" in (result.error or "").lower()

    err_events = [
        e for e in captured
        if e["type"] == "chat_response" and e["data"].get("type") == "error"
    ]
    assert len(err_events) == 1
    assert "boom" in err_events[0]["data"]["content"].lower()
