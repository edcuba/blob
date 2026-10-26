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

"""ADK plugin that logs what the agent meant to do next to what actually happened.

Each invocation produces a chain of structured JSON events (see
:mod:`blob.app_utils.structured_logging`), all sharing ``invocation_id`` and
the OpenTelemetry trace id:

``invocation.intent``
    The user's inferred goal, e.g. ``remember``, ``recall`` or ``curate``,
    plus the tools that are expected to carry it out.
``agent.decision``
    What the model chose to do on each LLM turn: which tools to call, or a
    final answer. This is the agent's own intent.
``tool.intent`` / ``tool.outcome``
    One pair per tool call, with the tool's purpose, the argument names (never
    the values), the result status, the error type and the duration.
``invocation.outcome``
    The result of the whole run: ``success`` / ``partial`` / ``error``, the
    tools that ran, LLM token usage, latency, and ``intent_fulfilled``, which
    compares the expected tools with the ones that actually succeeded.

The plugin never logs raw prompt, response, or tool-argument content. Only
categories, names, counts, and statuses are recorded, which keeps it
consistent with the Model Armor PII guardrails and the ``NO_CONTENT``
telemetry setting.

The plugin is observe-only: every callback returns ``None``, and an internal
error is logged and swallowed rather than allowed to break the agent turn.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from google.adk.plugins.base_plugin import BasePlugin
from opentelemetry import trace

from blob.app_utils.structured_logging import log_event

logger = logging.getLogger("blob.intent")

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])

_VIEWPORT_MARKER = "[Active Viewport Context]"

# Ordered: the first matching category wins. Each entry maps a user intent to
# the keywords that signal it and the tools/sub-agents expected to fulfil it.
INTENT_RULES: tuple[tuple[str, tuple[str, ...], frozenset[str]], ...] = (
    (
        "forget",
        ("delete", "remove", "forget", "erase", "drop"),
        frozenset({"delete_wiki_page"}),
    ),
    (
        "curate",
        ("curate", "synthesize", "synthesise", "consolidate", "merge", "materialize"),
        frozenset(
            {
                "wiki_curator",
                "upsert_wiki_page",
                "create_curation_suggestion",
                "resolve_curation_suggestion",
                "mark_episodes_synthesized",
            }
        ),
    ),
    (
        "cluster",
        ("cluster", "regroup", "reorganize", "reorganise", "map of content", "moc"),
        frozenset(
            {
                "cluster_analyst",
                "recompute_semantic_clusters",
                "update_cluster_metadata",
                "list_semantic_clusters",
            }
        ),
    ),
    (
        "remember",
        (
            "remember",
            "note that",
            "store",
            "save",
            "record",
            "keep in mind",
            "log this",
        ),
        frozenset({"remember_episode", "upsert_wiki_page"}),
    ),
    (
        "navigate",
        ("navigate", "open", "show me", "highlight", "focus", "go to"),
        frozenset(
            {"ui_navigate_to_page", "ui_highlight_graph_nodes", "ui_focus_cluster"}
        ),
    ),
    (
        "recall",
        (
            "what",
            "who",
            "why",
            "how",
            "when",
            "which",
            "recall",
            "find",
            "search",
            "tell me",
            "explain",
            "summarize",
            "summarise",
            "?",
        ),
        frozenset({"recall_knowledge", "get_wiki_page", "get_graph_neighborhood"}),
    ),
)

_DEFAULT_INTENT = "conversation"
_MAX_TRACKED_INVOCATIONS = 1000


def classify_intent(text: str) -> tuple[str, str | None, frozenset[str]]:
    """Infer the user's intent category from a request.

    Returns:
        ``(category, matched_keyword, expected_tools)``. ``expected_tools`` is
        empty for plain conversation, which needs no tool.
    """
    body = text.split(_VIEWPORT_MARKER, 1)[0].lower()
    for category, keywords, tools in INTENT_RULES:
        for kw in keywords:
            if kw == "?":
                if "?" in body:
                    return category, kw, tools
            elif re.search(rf"\b{re.escape(kw)}\b", body):
                return category, kw, tools
    return _DEFAULT_INTENT, None, frozenset()


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(p, "text", None) or "" for p in parts)


def _tool_purpose(tool: Any) -> str | None:
    desc = (getattr(tool, "description", None) or "").strip()
    return desc.splitlines()[0][:200] if desc else None


def _set_span_attrs(**attrs: Any) -> None:
    span = trace.get_current_span()
    if not span.is_recording():
        return
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set | frozenset):
            value = [str(v) for v in value]
        span.set_attribute(key, value)


def _never_raise(fn: _F) -> _F:
    """Ensure observability failures never break an agent turn."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            await fn(*args, **kwargs)
        except Exception:
            logger.warning(
                "intent logging callback failed",
                exc_info=True,
                extra={
                    "json_fields": {
                        "event": "intent_logger.error",
                        "callback": fn.__name__,
                    }
                },
            )
        return None

    return wrapper  # type: ignore[return-value]


@dataclass
class _ToolCall:
    tool: str
    agent: str
    started: float


@dataclass
class _InvocationState:
    invocation_id: str
    session_id: str | None
    user_id: str | None
    app_name: str | None
    agent: str | None
    started: float = field(default_factory=time.monotonic)
    intent: str = _DEFAULT_INTENT
    expected_tools: frozenset[str] = frozenset()
    request_chars: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tools_succeeded: list[str] = field(default_factory=list)
    tools_failed: list[str] = field(default_factory=list)
    agents_involved: list[str] = field(default_factory=list)
    final_response_chars: int = 0
    error: str | None = None
    pending_tools: dict[str, _ToolCall] = field(default_factory=dict)


class IntentOutcomeLoggingPlugin(BasePlugin):
    """Logs agent intent versus outcome as structured JSON events."""

    def __init__(self, name: str = "intent_outcome_logging") -> None:
        super().__init__(name=name)
        self._states: dict[str, _InvocationState] = {}

    # ---- helpers -------------------------------------------------------

    def _state_for(self, invocation_context: Any) -> _InvocationState:
        inv_id = invocation_context.invocation_id
        state = self._states.get(inv_id)
        if state is None:
            session = getattr(invocation_context, "session", None)
            agent = getattr(invocation_context, "agent", None)
            state = _InvocationState(
                invocation_id=inv_id,
                session_id=getattr(session, "id", None),
                user_id=getattr(session, "user_id", None)
                or getattr(invocation_context, "user_id", None),
                app_name=getattr(session, "app_name", None)
                or getattr(invocation_context, "app_name", None),
                agent=getattr(agent, "name", None),
            )
            self._states[inv_id] = state
            # Runs that are cancelled never reach after_run; evict the oldest
            # entries so abandoned state cannot accumulate without bound.
            while len(self._states) > _MAX_TRACKED_INVOCATIONS:
                self._states.pop(next(iter(self._states)))
        return state

    def _state_from_callback(self, ctx: Any) -> _InvocationState | None:
        inv_ctx = getattr(ctx, "_invocation_context", None)
        if inv_ctx is None:
            return None
        return self._state_for(inv_ctx)

    @staticmethod
    def _base_fields(state: _InvocationState) -> dict[str, Any]:
        return {
            "invocation_id": state.invocation_id,
            "session_id": state.session_id,
            "user_id": state.user_id,
            "app_name": state.app_name,
            "root_agent": state.agent,
        }

    # ---- invocation level ---------------------------------------------

    @_never_raise
    async def on_user_message_callback(self, *, invocation_context, user_message):
        state = self._state_for(invocation_context)
        text = _content_text(user_message)
        category, keyword, expected = classify_intent(text)
        state.intent = category
        state.expected_tools = expected
        state.request_chars = len(text)
        _set_span_attrs(**{"blob.intent.category": category})
        log_event(
            logger,
            "invocation.intent",
            **self._base_fields(state),
            intent=category,
            intent_signal=keyword,
            expected_tools=sorted(expected),
            request_chars=len(text),
            has_viewport_context=_VIEWPORT_MARKER in text,
        )

    @_never_raise
    async def before_run_callback(self, *, invocation_context):
        self._state_for(invocation_context)

    @_never_raise
    async def on_event_callback(self, *, invocation_context, event):
        state = self._state_for(invocation_context)
        if event.is_final_response() and event.content is not None:
            state.final_response_chars += len(_content_text(event.content))

    @_never_raise
    async def on_run_error_callback(self, *, invocation_context, error):
        state = self._state_for(invocation_context)
        state.error = type(error).__name__
        await self._emit_outcome(state)

    @_never_raise
    async def after_run_callback(self, *, invocation_context):
        state = self._states.get(invocation_context.invocation_id)
        if state is not None:
            await self._emit_outcome(state)

    async def _emit_outcome(self, state: _InvocationState) -> None:
        self._states.pop(state.invocation_id, None)
        succeeded = set(state.tools_succeeded)
        if state.expected_tools:
            fulfilled = bool(succeeded & state.expected_tools)
        else:
            fulfilled = state.final_response_chars > 0 or bool(succeeded)
        if state.error:
            status = "error"
            fulfilled = False
        elif state.tools_failed:
            status = "partial"
        else:
            status = "success"

        duration_ms = round((time.monotonic() - state.started) * 1000, 1)
        _set_span_attrs(
            **{
                "blob.outcome.status": status,
                "blob.outcome.intent_fulfilled": fulfilled,
            }
        )
        log_event(
            logger,
            "invocation.outcome",
            level=logging.WARNING
            if status == "error" or not fulfilled
            else logging.INFO,
            **self._base_fields(state),
            intent=state.intent,
            expected_tools=sorted(state.expected_tools),
            status=status,
            intent_fulfilled=fulfilled,
            tools_succeeded=state.tools_succeeded,
            tools_failed=state.tools_failed,
            unexpected_tools=sorted(succeeded - state.expected_tools)
            if state.expected_tools
            else None,
            agents_involved=state.agents_involved,
            llm_calls=state.llm_calls,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            final_response_chars=state.final_response_chars,
            error_type=state.error,
            duration_ms=duration_ms,
        )

    # ---- agent / model level ------------------------------------------

    @_never_raise
    async def before_agent_callback(self, *, agent, callback_context):
        state = self._state_from_callback(callback_context)
        if state is not None and agent.name not in state.agents_involved:
            state.agents_involved.append(agent.name)

    @_never_raise
    async def on_agent_error_callback(self, *, agent, callback_context, error):
        state = self._state_from_callback(callback_context)
        if state is None:
            return
        log_event(
            logger,
            "agent.outcome",
            level=logging.ERROR,
            **self._base_fields(state),
            agent=agent.name,
            status="error",
            error_type=type(error).__name__,
        )

    @_never_raise
    async def after_model_callback(self, *, callback_context, llm_response):
        state = self._state_from_callback(callback_context)
        if state is None:
            return
        state.llm_calls += 1
        usage = getattr(llm_response, "usage_metadata", None)
        if usage is not None:
            state.input_tokens += usage.prompt_token_count or 0
            state.output_tokens += usage.candidates_token_count or 0
        if getattr(llm_response, "partial", False):
            return

        parts = getattr(llm_response.content, "parts", None) or []
        planned = [
            p.function_call.name for p in parts if getattr(p, "function_call", None)
        ]
        has_text = any(getattr(p, "text", None) for p in parts)
        if planned:
            decision = "call_tools"
        elif has_text:
            decision = "respond"
        elif llm_response.error_code:
            decision = "model_error"
        else:
            decision = "no_action"
        finish = getattr(llm_response, "finish_reason", None)
        log_event(
            logger,
            "agent.decision",
            level=logging.WARNING if decision == "model_error" else logging.INFO,
            **self._base_fields(state),
            agent=callback_context.agent_name,
            intent=state.intent,
            decision=decision,
            planned_tools=planned or None,
            finish_reason=getattr(finish, "name", finish),
            error_code=llm_response.error_code,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )

    @_never_raise
    async def on_model_error_callback(self, *, callback_context, llm_request, error):
        state = self._state_from_callback(callback_context)
        if state is None:
            return
        log_event(
            logger,
            "agent.decision",
            level=logging.ERROR,
            **self._base_fields(state),
            agent=callback_context.agent_name,
            intent=state.intent,
            decision="model_error",
            model=getattr(llm_request, "model", None),
            error_type=type(error).__name__,
        )

    # ---- tool level ----------------------------------------------------

    @staticmethod
    def _call_key(tool: Any, tool_context: Any) -> str:
        return getattr(tool_context, "function_call_id", None) or tool.name

    @_never_raise
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        state = self._state_from_callback(tool_context)
        if state is None:
            return
        agent = tool_context.agent_name
        state.pending_tools[self._call_key(tool, tool_context)] = _ToolCall(
            tool=tool.name, agent=agent, started=time.monotonic()
        )
        log_event(
            logger,
            "tool.intent",
            **self._base_fields(state),
            agent=agent,
            tool=tool.name,
            tool_purpose=_tool_purpose(tool),
            is_delegation=tool.__class__.__name__ == "AgentTool",
            arg_names=sorted(tool_args or {}),
            expected_for_intent=tool.name in state.expected_tools,
        )

    def _finish_tool(
        self,
        state: _InvocationState,
        tool: Any,
        tool_context: Any,
        *,
        status: str,
        level: int,
        **extra: Any,
    ) -> None:
        call = state.pending_tools.pop(self._call_key(tool, tool_context), None)
        duration_ms = (
            round((time.monotonic() - call.started) * 1000, 1) if call else None
        )
        (state.tools_succeeded if status == "success" else state.tools_failed).append(
            tool.name
        )
        log_event(
            logger,
            "tool.outcome",
            level=level,
            **self._base_fields(state),
            agent=tool_context.agent_name,
            tool=tool.name,
            status=status,
            duration_ms=duration_ms,
            **extra,
        )

    @_never_raise
    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        state = self._state_from_callback(tool_context)
        if state is None:
            return
        result_status = None
        result_keys = None
        error_message_present = False
        if isinstance(result, dict):
            result_status = result.get("status")
            result_keys = sorted(result)[:20]
            error_message_present = "error" in result or "error_message" in result
        failed = error_message_present or (
            isinstance(result_status, str)
            and result_status.lower() in {"error", "failed", "not_found", "rejected"}
        )
        self._finish_tool(
            state,
            tool,
            tool_context,
            status="failure" if failed else "success",
            level=logging.WARNING if failed else logging.INFO,
            result_status=result_status,
            result_keys=result_keys,
        )

    @_never_raise
    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        state = self._state_from_callback(tool_context)
        if state is None:
            return
        self._finish_tool(
            state,
            tool,
            tool_context,
            status="error",
            level=logging.ERROR,
            error_type=type(error).__name__,
        )
