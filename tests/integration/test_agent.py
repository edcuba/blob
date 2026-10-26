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

import asyncio

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.genai import types

from blob.agent import MODEL, root_agent, run_curation_pipeline
from blob.storage import (
    DeterministicHashEmbedder,
    InMemoryKnowledgeStore,
    seed_knowledge_store,
    set_embedder,
    set_knowledge_store,
)
from blob.tools import (
    MEMORY_TOOLS,
    UI_TOOLS,
    recall_knowledge,
    remember_episode,
)


def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """

    session_service = InMemorySessionService()

    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Why is the sky blue?")]
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one message"

    has_text_content = False
    for event in events:
        if (
            event.content
            and event.content.parts
            and any(part.text for part in event.content.parts)
        ):
            has_text_content = True
            break
    assert has_text_content, "Expected at least one message with text content"


def test_agent_memory_and_curation_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify `root_agent` tool registration and `run_curation_pipeline` integration."""
    monkeypatch.setenv("BLOB_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("BLOB_STORAGE_BACKEND", "memory")
    embedder = DeterministicHashEmbedder()
    store = InMemoryKnowledgeStore(embedder=embedder)
    set_embedder(embedder)
    set_knowledge_store(store)

    try:
        assert root_agent.name == "blob"
        assert MODEL == "gemini-3.8-flash"

        # Verify all 13 memory tools, 3 UI tools, and 2 AgentTool sub-agents are registered
        registered_tools = list(root_agent.tools)
        for mem_tool in MEMORY_TOOLS:
            assert mem_tool in registered_tools
        for ui_tool in UI_TOOLS:
            assert ui_tool in registered_tools

        agent_tool_names = {
            t.agent.name for t in registered_tools if isinstance(t, AgentTool)
        }
        assert {"wiki_curator", "cluster_analyst"}.issubset(agent_tool_names)

        # Seed store, ingest a new episode, and run the curation pipeline
        seed_res = seed_knowledge_store(store=store, namespace="default", force=True)
        assert seed_res["status"] == "seeded"
        assert seed_res["clusters_count"] == 4

        ep_res = remember_episode(
            content=(
                "BigQuery Telemetry Views join NDJSON completions from GCS with "
                "Cloud Logging spans by trace_id."
            ),
            source_agent="claude-code",
            tags=["bigquery", "telemetry", "observability"],
            namespace="default",
        )
        assert ep_res.status == "ok"

        curation_res = asyncio.run(run_curation_pipeline(namespace="default"))
        assert curation_res["status"] == "ok"
        assert ep_res.episode_id in curation_res["synthesized_episodes"]
        assert len(curation_res["updated_pages"]) >= 1
        assert len(curation_res["clusters"]) == 4

        recall_res = recall_knowledge(
            query="BigQuery Telemetry Views trace_id",
            namespace="default",
            top_k=3,
        )
        assert recall_res.status == "ok"
        assert len(recall_res.matches) >= 1
    finally:
        set_embedder(None)
        set_knowledge_store(None)
