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

"""Strategic model routing for the Blob agent hierarchy.

Routing is role-based and resolved once at agent construction:

* ``fast`` tier (``gemini-3.8-flash``) — low-latency, user-facing turns and simple,
  well-scoped tasks: the ``blob`` coordinator, the ``assistant`` chat agent, and
  ``cluster_analyst`` (labels clusters that are already computed numerically).
* ``complex`` tier (``gemini-4-argon``) — multi-step reasoning: ``wiki_curator``
  merges many episodes into one page, resolves contradictions, and keeps
  provenance and link hygiene intact.

The fast coordinator does the per-request routing itself: it delegates heavy
synthesis to ``wiki_curator`` through ``AgentTool``, so only that delegated work
runs on the complex model while the user-facing turn stays on the fast one.

Both models can be overridden per environment with ``BLOB_FAST_MODEL`` and
``BLOB_COMPLEX_MODEL``.
"""

from __future__ import annotations

import os
from typing import Literal

from google.adk.models import Gemini
from google.genai import types

ModelTier = Literal["fast", "complex"]

FAST_MODEL = os.environ.get("BLOB_FAST_MODEL", "gemini-3.8-flash")
COMPLEX_MODEL = os.environ.get("BLOB_COMPLEX_MODEL", "gemini-4-argon")

AGENT_MODEL_TIERS: dict[str, ModelTier] = {
    "blob": "fast",
    "assistant": "fast",
    "cluster_analyst": "fast",
    "wiki_curator": "complex",
}


def model_name_for_tier(tier: ModelTier) -> str:
    """Return the Gemini model name configured for a routing tier."""
    return COMPLEX_MODEL if tier == "complex" else FAST_MODEL


def tier_for_agent(agent_name: str) -> ModelTier:
    """Return the routing tier for an agent, defaulting unknown agents to ``fast``."""
    return AGENT_MODEL_TIERS.get(agent_name, "fast")


def model_name_for_agent(agent_name: str) -> str:
    """Return the Gemini model name an agent is routed to."""
    return model_name_for_tier(tier_for_agent(agent_name))


def gemini_for_agent(agent_name: str, *, retry_attempts: int = 3) -> Gemini:
    """Build the ADK ``Gemini`` model instance an agent is routed to."""
    return Gemini(
        model=model_name_for_agent(agent_name),
        retry_options=types.HttpRetryOptions(attempts=retry_attempts),
    )
