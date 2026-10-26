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

"""Abstract KnowledgeStore interface, EventBus, and singleton factory."""

from __future__ import annotations

import asyncio
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any, Literal

from blob.storage.markdown_parser import serialize_wiki_page
from blob.storage.models import (
    Cluster,
    CurationSuggestion,
    Episode,
    EpisodeSource,
    GraphRelation,
    GraphSnapshot,
    UIActionEvent,
    WikiPage,
    utc_now_iso,
)


class EventBus:
    """In-process pub/sub bus for SSE live updates and turn-scoped UI actions."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[UIActionEvent]] = set()
        self._turn_collectors: dict[str, list[UIActionEvent]] = {}
        self._recent_events: list[UIActionEvent] = []

    def subscribe(self) -> asyncio.Queue[UIActionEvent]:
        """Register an async queue for SSE streaming."""
        queue: asyncio.Queue[UIActionEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[UIActionEvent]) -> None:
        """Unregister an SSE subscriber queue."""
        self._subscribers.discard(queue)

    def start_turn_collector(self, turn_id: str = "default") -> str:
        """Start collecting UIActionEvents for an interactive chat turn."""
        self._turn_collectors[turn_id] = []
        return turn_id

    def record_turn_action(
        self, event: UIActionEvent, turn_id: str | None = None
    ) -> None:
        """Record a UIActionEvent into active turn collector(s) without duplicates."""
        if turn_id is not None:
            bucket = self._turn_collectors.setdefault(turn_id, [])
            if all(existing.id != event.id for existing in bucket):
                bucket.append(event)
            return

        for bucket in self._turn_collectors.values():
            if all(existing.id != event.id for existing in bucket):
                bucket.append(event)

    def pop_turn_actions(self, turn_id: str = "default") -> list[UIActionEvent]:
        """Pop and return all UIActionEvents recorded during a chat turn."""
        return self._turn_collectors.pop(turn_id, [])

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> UIActionEvent:
        """Publish an event to all SSE subscribers and active turn collectors."""
        event = UIActionEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            type=event_type,
            namespace=namespace,
            payload=payload or {},
            timestamp=utc_now_iso(),
        )
        self._recent_events.append(event)
        if len(self._recent_events) > 100:
            self._recent_events = self._recent_events[-100:]

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        # Automatically record UI command events into active turn collectors
        if event_type.startswith("ui_") or event_type in (
            "navigate_to_page",
            "highlight_nodes",
            "focus_cluster",
            "refresh_page",
        ):
            self.record_turn_action(event)

        return event


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


class KnowledgeStore(ABC):
    """Unified storage interface for episodes, Markdown wiki pages, graph, and clusters."""

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    @abstractmethod
    def create_episode(
        self,
        content: str,
        source_agent: str = "external",
        tags: list[str] | None = None,
        namespace: str = "default",
        interaction_id: str | None = None,
        episode_id: str | None = None,
    ) -> Episode:
        """Embed and persist a new episodic memory."""

    @abstractmethod
    def get_episode(
        self, episode_id: str, namespace: str = "default"
    ) -> Episode | None:
        """Retrieve a single Episode by ID."""

    @abstractmethod
    def list_episodes(
        self,
        namespace: str = "default",
        status: str | None = None,
        limit: int = 50,
    ) -> list[Episode]:
        """List episodes in a namespace, optionally filtered by status."""

    @abstractmethod
    def mark_episodes_synthesized(
        self,
        episode_ids: list[str],
        target_slug: str,
        namespace: str = "default",
    ) -> list[Episode]:
        """Mark one or more episodes as synthesized into `target_slug`."""

    # ------------------------------------------------------------------
    # Wiki Pages
    # ------------------------------------------------------------------

    @abstractmethod
    def get_wiki_page(
        self, slug_or_title: str, namespace: str = "default"
    ) -> WikiPage | None:
        """Retrieve a WikiPage by slug or title."""

    def get_page(
        self, slug_or_title: str, namespace: str = "default"
    ) -> WikiPage | None:
        """Alias for `get_wiki_page`."""
        return self.get_wiki_page(slug_or_title, namespace=namespace)

    @abstractmethod
    def list_wiki_pages(
        self,
        namespace: str = "default",
        include_ghosts: bool = True,
        status: str | None = None,
        cluster_id: str | None = None,
        query: str | None = None,
    ) -> list[WikiPage]:
        """List WikiPages in a namespace with optional filtering."""

    def list_pages(
        self,
        namespace: str = "default",
        include_ghosts: bool = True,
        status: str | None = None,
        cluster_id: str | None = None,
        query: str | None = None,
    ) -> list[WikiPage]:
        """Alias for `list_wiki_pages`."""
        return self.list_wiki_pages(
            namespace=namespace,
            include_ghosts=include_ghosts,
            status=status,
            cluster_id=cluster_id,
            query=query,
        )

    @abstractmethod
    def upsert_wiki_page(
        self,
        title: str,
        markdown_body: str,
        slug: str | None = None,
        namespace: str = "default",
        status: Literal["active", "ghost", "archived"] = "active",
        cluster_id: str | None = None,
        tags: list[str] | None = None,
        relations: list[GraphRelation | dict[str, Any]] | None = None,
        sources: list[EpisodeSource | dict[str, Any]] | None = None,
        source_episode_ids: list[str] | None = None,
        source_agent: str = "blob",
        x: float | None = None,
        y: float | None = None,
    ) -> WikiPage:
        """Create or update a WikiPage, parse [[wikilinks]], create ghost nodes, and update backlinks."""

    @abstractmethod
    def upsert_wiki_page_from_markdown(
        self,
        raw_markdown: str,
        slug: str | None = None,
        title: str | None = None,
        namespace: str = "default",
        source_agent: str = "human",
    ) -> WikiPage:
        """Create or update a WikiPage from raw Markdown (with optional YAML frontmatter)."""

    @abstractmethod
    def delete_wiki_page(self, slug: str, namespace: str = "default") -> bool:
        """Delete a WikiPage and update backlinks across the namespace."""

    def serialize_page(
        self, slug_or_page: str | WikiPage, namespace: str = "default"
    ) -> str | None:
        """Serialize a WikiPage into YAML frontmatter + Markdown body."""
        page = (
            slug_or_page
            if isinstance(slug_or_page, WikiPage)
            else self.get_wiki_page(slug_or_page, namespace=namespace)
        )
        if page is None:
            return None
        return serialize_wiki_page(page)

    # ------------------------------------------------------------------
    # Hybrid Recall & Graph Traversal
    # ------------------------------------------------------------------

    @abstractmethod
    def recall(
        self,
        query: str,
        namespace: str = "default",
        top_k: int = 5,
        include_episodes: bool = True,
    ) -> dict[str, Any]:
        """Hybrid vector + keyword + 1-hop graph recall across WikiPages and pending Episodes."""

    @abstractmethod
    def traverse_graph(
        self,
        seed_slug: str,
        depth: int = 2,
        namespace: str = "default",
    ) -> GraphSnapshot:
        """Return the local ego-graph around `seed_slug` up to `depth` hops."""

    @abstractmethod
    def get_graph_snapshot(self, namespace: str = "default") -> GraphSnapshot:
        """Return the complete node, edge, and cluster graph snapshot for a namespace."""

    # ------------------------------------------------------------------
    # Semantic Clusters
    # ------------------------------------------------------------------

    @abstractmethod
    def list_clusters(self, namespace: str = "default") -> list[Cluster]:
        """Return all semantic clusters in a namespace."""

    @abstractmethod
    def get_cluster(
        self, cluster_id: str, namespace: str = "default"
    ) -> Cluster | None:
        """Return a single Cluster by ID."""

    @abstractmethod
    def recompute_clusters(
        self, namespace: str = "default", max_clusters: int = 4
    ) -> list[Cluster]:
        """Re-cluster WikiPages by vector similarity and update 2D coordinates."""

    @abstractmethod
    def update_cluster_metadata(
        self,
        cluster_id: str,
        title: str | None = None,
        summary: str | None = None,
        color: str | None = None,
        namespace: str = "default",
    ) -> Cluster | None:
        """Update human-readable title, summary, or color of a semantic Cluster."""

    def save_cluster(self, cluster: Cluster) -> Cluster:
        """Persist a Cluster directly (used during store seeding)."""
        return cluster

    def clear(self, namespace: str | None = None) -> None:
        """Clear stored entities in `namespace` (or all namespaces when None)."""
        return None

    # ------------------------------------------------------------------
    # Curation Suggestions
    # ------------------------------------------------------------------

    @abstractmethod
    def create_suggestion(
        self,
        target_slug: str,
        title: str,
        description: str = "",
        kind: str = "unmerged_episodes",
        episode_ids: list[str] | None = None,
        proposed_markdown: str | None = None,
        namespace: str = "default",
        suggestion_id: str | None = None,
    ) -> CurationSuggestion:
        """Create a co-curation suggestion targeting a WikiPage."""

    def create_curation_suggestion(
        self,
        target_slug: str,
        title: str,
        description: str = "",
        kind: str = "unmerged_episodes",
        episode_ids: list[str] | None = None,
        proposed_markdown: str | None = None,
        namespace: str = "default",
        suggestion_id: str | None = None,
    ) -> CurationSuggestion:
        """Alias for `create_suggestion`."""
        return self.create_suggestion(
            target_slug=target_slug,
            title=title,
            description=description,
            kind=kind,
            episode_ids=episode_ids,
            proposed_markdown=proposed_markdown,
            namespace=namespace,
            suggestion_id=suggestion_id,
        )

    @abstractmethod
    def list_suggestions(
        self,
        namespace: str = "default",
        target_slug: str | None = None,
        status: str | None = "open",
    ) -> list[CurationSuggestion]:
        """List curation suggestions in a namespace."""

    @abstractmethod
    def get_suggestion(
        self, suggestion_id: str, namespace: str = "default"
    ) -> CurationSuggestion | None:
        """Retrieve a single CurationSuggestion by ID."""

    @abstractmethod
    def resolve_suggestion(
        self,
        suggestion_id: str,
        action: Literal["apply", "dismiss"] = "apply",
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Apply or dismiss a CurationSuggestion."""

    def resolve_curation_suggestion(
        self,
        suggestion_id: str,
        action: Literal["apply", "dismiss"] = "apply",
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Alias for `resolve_suggestion`."""
        return self.resolve_suggestion(
            suggestion_id=suggestion_id,
            action=action,
            namespace=namespace,
        )


_knowledge_store: KnowledgeStore | None = None


def set_knowledge_store(store: KnowledgeStore | None) -> None:
    """Explicitly set or reset the singleton KnowledgeStore instance."""
    global _knowledge_store
    _knowledge_store = store


def get_knowledge_store() -> KnowledgeStore:
    """Return the singleton KnowledgeStore configured by BLOB_STORAGE_BACKEND.

    Backend selection rules:
    - `INTEGRATION_TEST=TRUE` or `BLOB_STORAGE_BACKEND=memory` -> `InMemoryKnowledgeStore`
    - `BLOB_STORAGE_BACKEND=firestore` or (`BLOB_STORAGE_BACKEND=auto` with
      `GOOGLE_CLOUD_AGENT_ENGINE_ID` set) -> `FirestoreKnowledgeStore`
    - Defaults to `InMemoryKnowledgeStore` locally.
    - When `BLOB_AUTO_SEED=true` and using `InMemoryKnowledgeStore`, populates the
      demo seed dataset on initialization; otherwise starts empty by default.
    """
    global _knowledge_store
    if _knowledge_store is not None:
        return _knowledge_store

    backend = os.environ.get("BLOB_STORAGE_BACKEND", "auto").strip().lower()
    is_integration_test = os.environ.get("INTEGRATION_TEST", "").strip().lower() in (
        "true",
        "1",
    )
    on_agent_runtime = bool(os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"))

    if not is_integration_test and (
        backend == "firestore" or (backend == "auto" and on_agent_runtime)
    ):
        from blob.storage.firestore_store import FirestoreKnowledgeStore

        _knowledge_store = FirestoreKnowledgeStore()
    else:
        from blob.storage.memory_store import InMemoryKnowledgeStore

        _knowledge_store = InMemoryKnowledgeStore()
        auto_seed = os.environ.get("BLOB_AUTO_SEED", "").strip().lower() in (
            "true",
            "1",
        )
        if auto_seed:
            from blob.storage.seed import seed_knowledge_store

            seed_knowledge_store(_knowledge_store)

    return _knowledge_store
