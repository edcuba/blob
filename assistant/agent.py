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

"""Simple user-facing demo assistant that connects to Blob over MCP."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.genai import types

MODEL = "gemini-3.8-flash"

BLOB_MCP_SSE_URL = os.environ.get("BLOB_MCP_SSE_URL", "http://127.0.0.1:8000/mcp/sse")

blob_mcp_tools = McpToolset(
    connection_params=SseConnectionParams(url=BLOB_MCP_SSE_URL),
    tool_filter=[
        "remember",
        "recall",
        "get_page",
        "traverse_graph",
        "list_clusters",
    ],
)

root_agent = Agent(
    name="assistant",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "A helpful personal and engineering assistant connected to the Blob "
        "memory fabric via MCP."
    ),
    instruction=(
        "You are a helpful, concise personal and software engineering assistant.\n\n"
        "You are connected to **Blob** (a shared memory fabric) via MCP tools:\n"
        "- Before answering questions about the user's projects, architecture, "
        "preferences, or past decisions, use `recall` (and `get_page` / "
        "`traverse_graph` when helpful) to ground your answer in stored memories.\n"
        "- When the user shares new facts, architectural decisions, conventions, "
        "or preferences—or asks you to remember something—call `remember` with "
        "`source_agent='assistant'`, relevant `tags`, and `auto_curate=True` so "
        "the Blob memory fabric ingests and curates it in the background.\n"
        "- Speak naturally as a helpful assistant to the user (do not act as the "
        "internal graph curator)."
    ),
    tools=[blob_mcp_tools],
)

app = App(
    root_agent=root_agent,
    name="assistant",
)
