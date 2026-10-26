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

"""Unit tests for explicit Pydantic tool output schemas."""

from __future__ import annotations

import asyncio
import typing
from unittest.mock import MagicMock

import pytest
from google.adk.tools._automatic_function_calling_util import (
    build_function_declaration,
)
from google.adk.utils.variant_utils import GoogleLLMVariant
from pydantic import BaseModel

from blob.storage import (
    DeterministicHashEmbedder,
    InMemoryKnowledgeStore,
    set_embedder,
    set_knowledge_store,
)
from blob.tools import MEMORY_TOOLS, UI_TOOLS
from blob.tools.schemas import RecallKnowledgeResult, ToolResult
from blob.tools.structured_tool import StructuredFunctionTool


@pytest.fixture(autouse=True)
def _isolated_memory_store():
    embedder = DeterministicHashEmbedder()
    set_embedder(embedder)
    set_knowledge_store(InMemoryKnowledgeStore(embedder=embedder))
    yield
    set_embedder(None)
    set_knowledge_store(None)


@pytest.mark.parametrize("tool", [*MEMORY_TOOLS, *UI_TOOLS], ids=lambda t: t.name)
def test_every_tool_declares_a_pydantic_output_schema(
    tool: StructuredFunctionTool,
) -> None:
    assert isinstance(tool, StructuredFunctionTool)
    return_type = typing.get_type_hints(tool.func)["return"]
    assert issubclass(return_type, ToolResult)
    schema = return_type.model_json_schema()
    assert schema["type"] == "object"
    assert {"status", "message", "namespace"} <= set(schema["properties"])


def test_structured_tool_serializes_models_to_plain_dicts() -> None:
    recall_tool = next(t for t in MEMORY_TOOLS if t.name == "recall_knowledge")

    ok = asyncio.run(
        recall_tool.run_async(args={"query": "firestore"}, tool_context=MagicMock())
    )
    assert isinstance(ok, dict)
    assert ok["status"] == "ok"
    assert RecallKnowledgeResult.model_validate(ok).status == "ok"

    err = asyncio.run(
        recall_tool.run_async(args={"query": "   "}, tool_context=MagicMock())
    )
    assert err == RecallKnowledgeResult.error(
        "Recall query cannot be empty."
    ).model_dump(mode="json")


def test_tool_outputs_never_leak_embeddings() -> None:
    remember = next(t for t in MEMORY_TOOLS if t.name == "remember_episode")
    out = asyncio.run(
        remember.run_async(
            args={"content": "Embeddings stay internal."}, tool_context=MagicMock()
        )
    )
    assert "embedding" not in out["episode"]


def test_function_declaration_carries_response_schema() -> None:
    # ADK only attaches response schemas for the Vertex AI variant.
    for tool in [*MEMORY_TOOLS, *UI_TOOLS]:
        decl = build_function_declaration(
            tool.func, ["tool_context", "input_stream"], GoogleLLMVariant.VERTEX_AI
        )
        has_schema = decl.response is not None or decl.response_json_schema is not None
        assert has_schema, f"{tool.name} has no response schema"
        assert issubclass(typing.get_type_hints(tool.func)["return"], BaseModel)
