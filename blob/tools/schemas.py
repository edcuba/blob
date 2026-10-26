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

"""Explicit Pydantic output schemas for Blob ADK and MCP tools.

Every tool returns a subclass of :class:`ToolResult`. Success and error
responses share one flat object schema: ``status`` discriminates the outcome
and ``message`` carries a recovery hint for the LLM when ``status == "error"``.
Payload fields default to empty values so an error response validates against
the same schema as a success response.

View models (``EpisodeView``, ``WikiPageView``) mirror the storage models but
omit the raw 768-d ``embedding`` vectors so tool output stays compact.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from blob.storage.models import (
    Cluster,
    CurationSuggestion,
    EpisodeSource,
    GraphEdge,
    GraphNode,
    GraphRelation,
    UIActionEvent,
)

ToolStatus = Literal["ok", "error"]


# ---------------------------------------------------------------------------
# Embedding-free views of storage models
# ---------------------------------------------------------------------------


class _View(BaseModel):
    """Base for read-only projections that silently drop unknown storage fields."""

    model_config = ConfigDict(extra="ignore")


class EpisodeView(_View):
    """Raw episodic memory as exposed to tools (without its embedding vector)."""

    id: str
    namespace: str = "default"
    content: str
    source_agent: str = "external"
    interaction_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: Literal["pending_curation", "synthesized", "archived"] = "pending_curation"
    synthesized_into: list[str] = Field(default_factory=list)
    created_at: str = ""

    @classmethod
    def from_model(cls, model: BaseModel) -> Self:
        """Project a storage ``Episode`` into an embedding-free view."""
        return cls.model_validate(model.model_dump(exclude={"embedding"}))


class WikiPageView(_View):
    """Synthesized WikiPage as exposed to tools (without its embedding vector)."""

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
    updated_at: str = ""

    @classmethod
    def from_model(cls, model: BaseModel) -> Self:
        """Project a storage ``WikiPage`` into an embedding-free view."""
        return cls.model_validate(model.model_dump(exclude={"embedding"}))


# ---------------------------------------------------------------------------
# Common result envelope
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Common envelope shared by every Blob tool response."""

    status: ToolStatus = Field(
        description="'ok' on success, 'error' when the call failed."
    )
    message: str | None = Field(
        default=None,
        description="Human-readable error or recovery hint; set when status is 'error'.",
    )
    namespace: str = Field(default="default", description="Memory namespace scope.")

    @classmethod
    def error(cls, message: str, **fields: Any) -> Self:
        """Build an error response carrying a recovery hint for the LLM."""
        return cls(status="error", message=message, **fields)


# ---------------------------------------------------------------------------
# Memory tool results
# ---------------------------------------------------------------------------


class RememberEpisodeResult(ToolResult):
    """Result of ``remember_episode``."""

    episode_id: str | None = None
    episode: EpisodeView | None = None


class RecallPageMatch(_View):
    """A WikiPage matched by hybrid vector + keyword recall."""

    slug: str
    title: str
    status: str
    score: float
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    markdown_body: str = ""
    out_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    sources: list[EpisodeSource] = Field(default_factory=list)
    page: WikiPageView | None = None


class RecallNeighbor(_View):
    """A 1-hop graph neighbor of a matched WikiPage."""

    slug: str
    title: str
    status: str
    cluster_id: str | None = None
    summary: str = ""


class RecallEpisodeMatch(_View):
    """A pending episode matched by hybrid recall."""

    id: str
    content: str
    source_agent: str = "external"
    tags: list[str] = Field(default_factory=list)
    status: str = "pending_curation"
    score: float = 0.0
    created_at: str = ""
    episode: EpisodeView | None = None


class RecallKnowledgeResult(ToolResult):
    """Result of ``recall_knowledge``."""

    query: str = ""
    matches: list[RecallPageMatch] = Field(default_factory=list)
    wiki_pages: list[RecallPageMatch] = Field(
        default_factory=list, description="Alias of `matches`."
    )
    neighbors: list[RecallNeighbor] = Field(default_factory=list)
    episodes: list[RecallEpisodeMatch] = Field(default_factory=list)
    pending_episodes: list[RecallEpisodeMatch] = Field(
        default_factory=list, description="Alias of `episodes`."
    )


class WikiPageResult(ToolResult):
    """Result of ``get_wiki_page``."""

    slug: str | None = None
    title: str | None = None
    page_status: Literal["active", "ghost", "archived"] | None = None
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    markdown_body: str = ""
    serialized_markdown: str = ""
    out_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    relations: list[GraphRelation] = Field(default_factory=list)
    sources: list[EpisodeSource] = Field(default_factory=list)
    source_episodes: list[EpisodeView] = Field(default_factory=list)
    open_suggestions: list[CurationSuggestion] = Field(default_factory=list)
    page: WikiPageView | None = None


class UpsertWikiPageResult(ToolResult):
    """Result of ``upsert_wiki_page``."""

    slug: str | None = None
    title: str | None = None
    page_status: Literal["active", "ghost", "archived"] | None = None
    cluster_id: str | None = None
    out_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    sources: list[EpisodeSource] = Field(default_factory=list)
    page: WikiPageView | None = None


class DeleteWikiPageResult(ToolResult):
    """Result of ``delete_wiki_page``."""

    deleted: bool = False
    slug: str = ""


class EpisodeListResult(ToolResult):
    """Result of ``list_pending_episodes``."""

    count: int = 0
    episodes: list[EpisodeView] = Field(default_factory=list)


class MarkEpisodesSynthesizedResult(ToolResult):
    """Result of ``mark_episodes_synthesized``."""

    target_slug: str = ""
    updated_count: int = 0
    episode_ids: list[str] = Field(default_factory=list)
    episodes: list[EpisodeView] = Field(default_factory=list)


class GraphNeighborhoodResult(ToolResult):
    """Result of ``get_graph_neighborhood``."""

    seed_slug: str = ""
    depth: int = 0
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    clusters: list[Cluster] = Field(default_factory=list)


class ClusterListResult(ToolResult):
    """Result of ``list_semantic_clusters`` and ``recompute_semantic_clusters``."""

    count: int = 0
    clusters: list[Cluster] = Field(default_factory=list)


class ClusterResult(ToolResult):
    """Result of ``update_cluster_metadata``."""

    cluster_id: str | None = None
    cluster: Cluster | None = None


class CurationSuggestionResult(ToolResult):
    """Result of ``create_curation_suggestion``."""

    suggestion_id: str | None = None
    suggestion: CurationSuggestion | None = None


class ResolveSuggestionResult(ToolResult):
    """Result of ``resolve_curation_suggestion``."""

    action: Literal["apply", "dismiss"] | None = None
    suggestion: CurationSuggestion | None = None
    page: WikiPageView | None = None


# ---------------------------------------------------------------------------
# UI action tool results
# ---------------------------------------------------------------------------


class UIActionResult(ToolResult):
    """Result of the bidirectional Insider View UI action tools."""

    action: Literal["ui_navigate_to_page", "ui_highlight_nodes", "ui_focus_cluster"]
    reason: str = ""
    slug: str | None = None
    slugs: list[str] | None = None
    cluster_id: str | None = None
    event: UIActionEvent | None = None


# ---------------------------------------------------------------------------
# MCP-only results
# ---------------------------------------------------------------------------


class MCPRememberResult(BaseModel):
    """Result of the MCP ``remember`` tool."""

    status: Literal["stored", "error"]
    message: str | None = None
    namespace: str = "default"
    episode_id: str | None = None
    auto_curate: bool = False
    curation_scheduled: bool = False
    episode: EpisodeView | None = None


class MCPPageResult(WikiPageResult):
    """Result of the MCP ``get_page`` tool (adds MCP-facing aliases)."""

    raw_markdown: str = Field(default="", description="Alias of `serialized_markdown`.")
    suggestions: list[CurationSuggestion] = Field(
        default_factory=list, description="Alias of `open_suggestions`."
    )
