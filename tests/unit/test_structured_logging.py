# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for structured JSON logging and intent-vs-outcome capture."""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types
from opentelemetry.sdk.trace import TracerProvider

from blob.agent import app
from blob.app_utils.intent_logging import IntentOutcomeLoggingPlugin, classify_intent
from blob.app_utils.structured_logging import (
    _build_handler,
    configure_structured_logging,
    log_event,
)

# ---------------------------------------------------------------- JSON logging


def _json_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    buf = io.StringIO()
    handler = _build_handler("json")
    handler.setStream(buf)
    lg = logging.getLogger(name)
    lg.handlers = [handler]
    lg.propagate = False
    lg.setLevel(logging.INFO)
    return lg, buf


def test_log_event_emits_parseable_json_with_fields() -> None:
    lg, buf = _json_logger("blob.test.json")

    log_event(lg, "tool.outcome", tool="recall_knowledge", status="success", skip=None)

    entry = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert entry["message"] == "tool.outcome"
    assert entry["event"] == "tool.outcome"
    assert entry["tool"] == "recall_knowledge"
    assert entry["status"] == "success"
    assert entry["severity"] == "INFO"
    assert "skip" not in entry


def test_json_logs_are_correlated_with_otel_trace() -> None:
    lg, buf = _json_logger("blob.test.trace")
    tracer = TracerProvider().get_tracer(__name__)

    with tracer.start_as_current_span("unit") as span:
        log_event(lg, "correlated")
        ctx = span.get_span_context()

    entry = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert entry["logging.googleapis.com/trace"].endswith(f"{ctx.trace_id:032x}")
    assert entry["logging.googleapis.com/spanId"] == f"{ctx.span_id:016x}"


def test_configure_structured_logging_is_idempotent() -> None:
    first = configure_structured_logging()
    second = configure_structured_logging()
    assert first is second
    marked = [
        h
        for h in logging.getLogger().handlers
        if getattr(h, "_blob_structured_handler", False)
    ]
    assert len(marked) == 1


# ------------------------------------------------------- intent classification


@pytest.mark.parametrize(
    ("text", "category", "tool"),
    [
        (
            "Remember that we chose Firestore for storage.",
            "remember",
            "remember_episode",
        ),
        ("What do we know about BigQuery telemetry?", "recall", "recall_knowledge"),
        ("Please curate the pending episodes", "curate", "wiki_curator"),
        ("Reorganize the cluster colors", "cluster", "cluster_analyst"),
        ("Delete the old onboarding page", "forget", "delete_wiki_page"),
        ("Highlight the auth nodes", "navigate", "ui_highlight_graph_nodes"),
    ],
)
def test_classify_intent(text: str, category: str, tool: str) -> None:
    got, _, expected = classify_intent(text)
    assert got == category
    assert tool in expected


def test_classify_intent_ignores_viewport_context() -> None:
    text = "thanks!\n[Active Viewport Context]\nselected_cluster_id: c1"
    category, _, expected = classify_intent(text)
    assert category == "conversation"
    assert expected == frozenset()


def test_plugin_registered_before_guardrails() -> None:
    assert isinstance(app.plugins[0], IntentOutcomeLoggingPlugin)


# --------------------------------------------------------- plugin intent/outcome


def _ctx(inv: Any, agent: str = "blob", call_id: str = "fc-1") -> Any:
    return SimpleNamespace(
        _invocation_context=inv, agent_name=agent, function_call_id=call_id
    )


def _events(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [
        r.json_fields
        for r in caplog.records
        if r.name == "blob.intent" and hasattr(r, "json_fields")
    ]


@pytest.mark.asyncio
async def test_plugin_logs_intent_versus_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="blob.intent")
    plugin = IntentOutcomeLoggingPlugin()
    inv = SimpleNamespace(
        invocation_id="inv-1",
        session=SimpleNamespace(id="s-1", user_id="u-1", app_name="blob"),
        agent=SimpleNamespace(name="blob"),
    )
    tool = SimpleNamespace(name="recall_knowledge", description="Hybrid recall.\nMore")
    ctx = _ctx(inv)

    await plugin.on_user_message_callback(
        invocation_context=inv,
        user_message=types.Content(
            role="user", parts=[types.Part(text="What do we know about my-secret?")]
        ),
    )
    await plugin.before_agent_callback(
        agent=SimpleNamespace(name="blob"), callback_context=ctx
    )
    await plugin.after_model_callback(
        callback_context=ctx,
        llm_response=SimpleNamespace(
            partial=False,
            error_code=None,
            finish_reason=None,
            usage_metadata=SimpleNamespace(
                prompt_token_count=100, candidates_token_count=10
            ),
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="recall_knowledge", args={"query": "x"}
                        )
                    )
                ],
            ),
        ),
    )
    await plugin.before_tool_callback(
        tool=tool, tool_args={"query": "my-secret"}, tool_context=ctx
    )
    await plugin.after_tool_callback(
        tool=tool,
        tool_args={"query": "my-secret"},
        tool_context=ctx,
        result={"status": "ok", "matches": []},
    )
    await plugin.on_event_callback(
        invocation_context=inv,
        event=SimpleNamespace(
            is_final_response=lambda: True,
            content=types.Content(role="model", parts=[types.Part(text="Answer")]),
        ),
    )
    await plugin.after_run_callback(invocation_context=inv)

    events = _events(caplog)
    names = [e["event"] for e in events]
    assert names == [
        "invocation.intent",
        "agent.decision",
        "tool.intent",
        "tool.outcome",
        "invocation.outcome",
    ]
    intent, decision, tool_intent, tool_outcome, outcome = events
    assert intent["intent"] == "recall"
    assert "recall_knowledge" in intent["expected_tools"]
    assert decision["decision"] == "call_tools"
    assert decision["planned_tools"] == ["recall_knowledge"]
    assert tool_intent["arg_names"] == ["query"]
    assert tool_intent["expected_for_intent"] is True
    assert tool_outcome["status"] == "success"
    assert outcome["status"] == "success"
    assert outcome["intent_fulfilled"] is True
    assert outcome["tools_succeeded"] == ["recall_knowledge"]
    assert outcome["input_tokens"] == 100
    assert outcome["session_id"] == "s-1"
    # Raw user/tool content is never logged.
    assert "my-secret" not in json.dumps(events)


@pytest.mark.asyncio
async def test_plugin_flags_unfulfilled_intent_on_tool_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="blob.intent")
    plugin = IntentOutcomeLoggingPlugin()
    inv = SimpleNamespace(
        invocation_id="inv-2",
        session=SimpleNamespace(id="s-2", user_id="u", app_name="blob"),
        agent=SimpleNamespace(name="blob"),
    )
    tool = SimpleNamespace(name="remember_episode", description="Store.")
    ctx = _ctx(inv)

    await plugin.on_user_message_callback(
        invocation_context=inv,
        user_message=types.Content(
            role="user", parts=[types.Part(text="Remember I like tea")]
        ),
    )
    await plugin.before_tool_callback(tool=tool, tool_args={}, tool_context=ctx)
    await plugin.on_tool_error_callback(
        tool=tool, tool_args={}, tool_context=ctx, error=TimeoutError()
    )
    await plugin.after_run_callback(invocation_context=inv)

    outcome = _events(caplog)[-1]
    assert outcome["event"] == "invocation.outcome"
    assert outcome["intent"] == "remember"
    assert outcome["status"] == "partial"
    assert outcome["intent_fulfilled"] is False
    assert outcome["tools_failed"] == ["remember_episode"]


@pytest.mark.asyncio
async def test_plugin_callbacks_never_raise() -> None:
    plugin = IntentOutcomeLoggingPlugin()
    # Malformed context must not break the agent turn.
    assert (
        await plugin.on_user_message_callback(
            invocation_context=object(), user_message=None
        )
        is None
    )
