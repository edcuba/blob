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

"""Pydantic data models for the Blob memory fabric storage layer."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VALID_RELATION_TYPES = ("part_of", "depends_on", "contradicts", "relates_to")


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class EpisodeSource(BaseModel):
    """Provenance link connecting a synthesized WikiPage back to an Episode."""

    episode_id: str
    source_agent: str = "external"
    interaction_id: str | None = None
    timestamp: str = Field(default_factory=utc_now_iso)


class GraphRelation(BaseModel):
    """Typed directional edge declared in a WikiPage's frontmatter."""

    type: str = "relates_to"
    target: str


class Episode(BaseModel):
    """Raw episodic memory captured during agent interactions."""

    id: str
    namespace: str = "default"
    content: str
    source_agent: str = "external"
    interaction_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: Literal["pending_curation", "synthesized", "archived"] = "pending_curation"
    synthesized_into: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class WikiPage(BaseModel):
    """Synthesized Markdown Wiki page and graph node."""

    slug: str
    title: str
    namespace: str = "default"
    status: Literal["active", "ghost", "archived"] = "active"
    markdown_body: str = ""
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    out_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    relations: list[GraphRelation] = Field(default_factory=list)
    sources: list[EpisodeSource] = Field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    embedding: list[float] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


class Cluster(BaseModel):
    """High-level semantic cluster grouping related WikiPages."""

    id: str
    namespace: str = "default"
    title: str
    summary: str = ""
    color: str = "#6366f1"
    page_slugs: list[str] = Field(default_factory=list)
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    updated_at: str = Field(default_factory=utc_now_iso)


class CurationSuggestion(BaseModel):
    """Co-curation suggestion surfaced on a WikiPage for 1-click resolution."""

    id: str
    namespace: str = "default"
    target_slug: str
    kind: str = "unmerged_episodes"
    title: str
    description: str = ""
    episode_ids: list[str] = Field(default_factory=list)
    proposed_markdown: str | None = None
    status: Literal["open", "applied", "dismissed"] = "open"
    created_at: str = Field(default_factory=utc_now_iso)


class GraphNode(BaseModel):
    """Visual node projection for the 2D Force Graph canvas."""

    slug: str
    title: str
    status: str
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    summary: str = ""
    backlink_count: int = 0
    out_link_count: int = 0
    open_suggestions: int = 0


class GraphEdge(BaseModel):
    """Directional edge between two GraphNodes."""

    source: str
    target: str
    type: str = "wikilink"


class GraphSnapshot(BaseModel):
    """Complete graph snapshot for a namespace or local ego-graph traversal."""

    namespace: str = "default"
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    clusters: list[Cluster] = Field(default_factory=list)


class UIActionEvent(BaseModel):
    """Real-time event emitted to the Insider View UI via SSE and chat turns."""

    id: str
    type: str
    namespace: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)
