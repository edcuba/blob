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

"""ADK memory fabric tools backed by the Blob KnowledgeStore."""

from __future__ import annotations

from typing import Any, Literal

from opentelemetry import trace

from blob.storage import (
    get_knowledge_store,
    serialize_wiki_page,
    slugify,
)

tracer = trace.get_tracer(__name__)


def _strip_embeddings_from_recall(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove raw 768-d float vectors from recall results to keep tool output compact."""
    cleaned = dict(payload)
    for key in ("matches", "wiki_pages"):
        items = cleaned.get(key)
        if isinstance(items, list):
            new_items: list[dict[str, Any]] = []
            for item in items:
                if isinstance(item, dict):
                    item_copy = dict(item)
                    if isinstance(item_copy.get("page"), dict):
                        page_copy = dict(item_copy["page"])
                        page_copy.pop("embedding", None)
                        item_copy["page"] = page_copy
                    new_items.append(item_copy)
            cleaned[key] = new_items

    for key in ("episodes", "pending_episodes"):
        items = cleaned.get(key)
        if isinstance(items, list):
            new_eps: list[dict[str, Any]] = []
            for item in items:
                if isinstance(item, dict):
                    item_copy = dict(item)
                    if isinstance(item_copy.get("episode"), dict):
                        ep_copy = dict(item_copy["episode"])
                        ep_copy.pop("embedding", None)
                        item_copy["episode"] = ep_copy
                    new_eps.append(item_copy)
            cleaned[key] = new_eps

    return cleaned


def remember_episode(
    content: str,
    source_agent: str = "blob",
    tags: list[str] | None = None,
    namespace: str = "default",
    interaction_id: str = "",
) -> dict[str, Any]:
    """Record a raw episodic memory in the Blob knowledge store for immediate recall and curation.

    Args:
        content: The observation, user preference, architectural decision, or interaction note to store.
        source_agent: Identifier of the agent or surface recording the memory (defaults to "blob").
        tags: Optional list of topical tags (e.g., ["architecture", "firestore"]).
        namespace: Memory namespace scope (defaults to "default").
        interaction_id: Optional session or turn identifier for provenance tracking.

    Returns:
        A structured dictionary containing the created episode ID, status, and metadata.
    """
    with tracer.start_as_current_span("blob.tool.remember_episode") as span:
        span.set_attribute("blob.namespace", namespace)
        span.set_attribute("blob.source_agent", source_agent)

        cleaned_content = (content or "").strip()
        if not cleaned_content:
            return {
                "status": "error",
                "message": "Episode content cannot be empty.",
            }

        store = get_knowledge_store()
        episode = store.create_episode(
            content=cleaned_content,
            source_agent=(source_agent or "blob").strip() or "blob",
            tags=tags,
            namespace=namespace or "default",
            interaction_id=interaction_id.strip() or None,
        )
        return {
            "status": "ok",
            "episode_id": episode.id,
            "namespace": episode.namespace,
            "episode": episode.model_dump(exclude={"embedding"}),
        }


def recall_knowledge(
    query: str,
    namespace: str = "default",
    top_k: int = 5,
    include_episodes: bool = True,
) -> dict[str, Any]:
    """Perform hybrid vector, keyword, and 1-hop graph recall across Wiki pages and pending episodes.

    Args:
        query: Natural-language search query or concept to retrieve from memory.
        namespace: Memory namespace scope (defaults to "default").
        top_k: Maximum number of synthesized Wiki pages to return (defaults to 5).
        include_episodes: Whether to also search unmerged pending episodes (defaults to True).

    Returns:
        A structured dictionary with matched Wiki pages, 1-hop graph neighbors, and pending episodes.
    """
    with tracer.start_as_current_span("blob.tool.recall_knowledge") as span:
        span.set_attribute("blob.namespace", namespace)
        span.set_attribute("blob.top_k", top_k)

        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return {
                "status": "error",
                "message": "Recall query cannot be empty.",
            }

        store = get_knowledge_store()
        result = store.recall(
            query=cleaned_query,
            namespace=namespace or "default",
            top_k=max(1, top_k),
            include_episodes=include_episodes,
        )
        cleaned = _strip_embeddings_from_recall(result)
        return {
            "status": "ok",
            **cleaned,
        }


def get_wiki_page(
    slug_or_title: str,
    namespace: str = "default",
) -> dict[str, Any]:
    """Fetch a WikiPage by slug or title, including serialized Markdown, backlinks, provenance, and suggestions.

    Args:
        slug_or_title: The kebab-case slug (e.g. "blob-storage-architecture") or title of the page.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary with the full page content, YAML frontmatter + Markdown, links,
        provenance sources, and open curation suggestions.
    """
    with tracer.start_as_current_span("blob.tool.get_wiki_page") as span:
        span.set_attribute("blob.namespace", namespace)
        span.set_attribute("blob.slug_or_title", slug_or_title)

        store = get_knowledge_store()
        ns = namespace or "default"
        page = store.get_wiki_page(slug_or_title, namespace=ns)
        if page is None:
            return {
                "status": "error",
                "namespace": ns,
                "message": f"WikiPage '{slug_or_title}' not found in namespace '{ns}'.",
            }

        serialized_md = serialize_wiki_page(page)
        suggestions = store.list_suggestions(
            namespace=ns, target_slug=page.slug, status="open"
        )
        source_episodes = [
            ep.model_dump(exclude={"embedding"})
            for src in page.sources
            if (ep := store.get_episode(src.episode_id, namespace=ns)) is not None
        ]

        return {
            "status": "ok",
            "namespace": ns,
            "slug": page.slug,
            "title": page.title,
            "page_status": page.status,
            "cluster_id": page.cluster_id,
            "tags": list(page.tags),
            "markdown_body": page.markdown_body,
            "serialized_markdown": serialized_md,
            "out_links": list(page.out_links),
            "backlinks": list(page.backlinks),
            "relations": [r.model_dump() for r in page.relations],
            "sources": [s.model_dump() for s in page.sources],
            "source_episodes": source_episodes,
            "open_suggestions": [s.model_dump() for s in suggestions],
            "page": page.model_dump(exclude={"embedding"}),
        }


def upsert_wiki_page(
    title: str,
    markdown_body: str,
    slug: str = "",
    namespace: str = "default",
    cluster_id: str = "",
    tags: list[str] | None = None,
    source_episode_ids: list[str] | None = None,
    source_agent: str = "blob",
) -> dict[str, Any]:
    """Create or update a Markdown WikiPage, automatically parsing [[Wiki Links]], creating ghost nodes, and updating backlinks.

    Args:
        title: Human-readable title of the Wiki page.
        markdown_body: Markdown content (use Obsidian-style [[Page Title]] or [[slug|Display]] for graph links).
        slug: Optional URL-safe slug (automatically derived from title if omitted).
        namespace: Memory namespace scope (defaults to "default").
        cluster_id: Optional semantic cluster ID to assign the page to.
        tags: Optional list of topical tags.
        source_episode_ids: Optional list of episode IDs synthesized into this page for provenance tracking.
        source_agent: Agent identifier performing the synthesis or edit (defaults to "blob").

    Returns:
        A structured dictionary containing the upserted WikiPage metadata, parsed outbound links, and backlinks.
    """
    with tracer.start_as_current_span("blob.tool.upsert_wiki_page") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.title", title)

        if not (title or "").strip() and not (slug or "").strip():
            return {
                "status": "error",
                "message": "Either title or slug must be provided to upsert a WikiPage.",
            }

        store = get_knowledge_store()
        page = store.upsert_wiki_page(
            title=title.strip() if title else "",
            markdown_body=markdown_body or "",
            slug=slug.strip() or None,
            namespace=ns,
            status="active",
            cluster_id=cluster_id.strip() or None,
            tags=tags,
            source_episode_ids=source_episode_ids,
            source_agent=(source_agent or "blob").strip() or "blob",
        )
        span.set_attribute("blob.page.slug", page.slug)

        return {
            "status": "ok",
            "namespace": ns,
            "slug": page.slug,
            "title": page.title,
            "page_status": page.status,
            "cluster_id": page.cluster_id,
            "out_links": list(page.out_links),
            "backlinks": list(page.backlinks),
            "sources": [s.model_dump() for s in page.sources],
            "page": page.model_dump(exclude={"embedding"}),
        }


def delete_wiki_page(
    slug: str,
    namespace: str = "default",
) -> dict[str, Any]:
    """Delete a WikiPage by slug and recompute bidirectional backlinks in the namespace.

    Args:
        slug: The slug of the WikiPage to remove.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary indicating whether the page was deleted.
    """
    with tracer.start_as_current_span("blob.tool.delete_wiki_page") as span:
        ns = namespace or "default"
        norm_slug = slugify(slug)
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.page.slug", norm_slug)

        store = get_knowledge_store()
        deleted = store.delete_wiki_page(slug=slug, namespace=ns)
        if not deleted:
            return {
                "status": "error",
                "deleted": False,
                "slug": norm_slug,
                "namespace": ns,
                "message": f"WikiPage '{slug}' not found in namespace '{ns}'.",
            }
        return {
            "status": "ok",
            "deleted": True,
            "slug": norm_slug,
            "namespace": ns,
        }


def list_pending_episodes(
    namespace: str = "default",
    limit: int = 25,
) -> dict[str, Any]:
    """List raw episodes with status='pending_curation' awaiting synthesis into Wiki pages.

    Args:
        namespace: Memory namespace scope (defaults to "default").
        limit: Maximum number of pending episodes to return (defaults to 25).

    Returns:
        A structured dictionary with the count and list of pending episodes.
    """
    with tracer.start_as_current_span("blob.tool.list_pending_episodes") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.limit", limit)

        store = get_knowledge_store()
        episodes = store.list_episodes(
            namespace=ns, status="pending_curation", limit=max(1, limit)
        )
        return {
            "status": "ok",
            "namespace": ns,
            "count": len(episodes),
            "episodes": [ep.model_dump(exclude={"embedding"}) for ep in episodes],
        }


def mark_episodes_synthesized(
    episode_ids: list[str],
    target_slug: str,
    namespace: str = "default",
) -> dict[str, Any]:
    """Mark one or more pending episodes as synthesized into a target WikiPage slug.

    Args:
        episode_ids: List of episode IDs that have been merged into the Wiki page.
        target_slug: The slug of the WikiPage where the episodes were synthesized.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary listing the updated episodes and target page slug.
    """
    with tracer.start_as_current_span("blob.tool.mark_episodes_synthesized") as span:
        ns = namespace or "default"
        norm_slug = slugify(target_slug)
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.target_slug", norm_slug)

        store = get_knowledge_store()
        updated = store.mark_episodes_synthesized(
            episode_ids=episode_ids or [],
            target_slug=norm_slug,
            namespace=ns,
        )
        return {
            "status": "ok",
            "namespace": ns,
            "target_slug": norm_slug,
            "updated_count": len(updated),
            "episode_ids": [ep.id for ep in updated],
            "episodes": [ep.model_dump(exclude={"embedding"}) for ep in updated],
        }


def get_graph_neighborhood(
    seed_slug: str,
    depth: int = 2,
    namespace: str = "default",
) -> dict[str, Any]:
    """Traverse the local ego-graph around a seed WikiPage up to `depth` hops.

    Args:
        seed_slug: Slug or title of the starting WikiPage node.
        depth: Number of link hops to traverse (defaults to 2).
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary containing nodes (including ghost nodes), typed edges, and clusters.
    """
    with tracer.start_as_current_span("blob.tool.get_graph_neighborhood") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.seed_slug", seed_slug)
        span.set_attribute("blob.depth", depth)

        store = get_knowledge_store()
        snapshot = store.traverse_graph(
            seed_slug=seed_slug,
            depth=max(1, depth),
            namespace=ns,
        )
        return {
            "status": "ok",
            "namespace": ns,
            "seed_slug": slugify(seed_slug),
            "depth": depth,
            "nodes": [n.model_dump() for n in snapshot.nodes],
            "edges": [e.model_dump() for e in snapshot.edges],
            "clusters": [c.model_dump() for c in snapshot.clusters],
        }


def list_semantic_clusters(
    namespace: str = "default",
) -> dict[str, Any]:
    """List all semantic clusters and their member WikiPage slugs in a namespace.

    Args:
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary containing all semantic clusters and their summaries.
    """
    with tracer.start_as_current_span("blob.tool.list_semantic_clusters") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)

        store = get_knowledge_store()
        clusters = store.list_clusters(namespace=ns)
        return {
            "status": "ok",
            "namespace": ns,
            "count": len(clusters),
            "clusters": [c.model_dump() for c in clusters],
        }


def recompute_semantic_clusters(
    namespace: str = "default",
    max_clusters: int = 4,
) -> dict[str, Any]:
    """Re-cluster WikiPages using 768-d vector similarity and update 2D force-graph coordinates.

    Args:
        namespace: Memory namespace scope (defaults to "default").
        max_clusters: Target maximum number of semantic clusters (defaults to 4).

    Returns:
        A structured dictionary with the recomputed semantic clusters and member slugs.
    """
    with tracer.start_as_current_span("blob.tool.recompute_semantic_clusters") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.max_clusters", max_clusters)

        store = get_knowledge_store()
        clusters = store.recompute_clusters(
            namespace=ns, max_clusters=max(1, max_clusters)
        )
        return {
            "status": "ok",
            "namespace": ns,
            "count": len(clusters),
            "clusters": [c.model_dump() for c in clusters],
        }


def update_cluster_metadata(
    cluster_id: str,
    title: str = "",
    summary: str = "",
    color: str = "",
    namespace: str = "default",
) -> dict[str, Any]:
    """Update the human-readable title, summary, or hex color of a semantic cluster.

    Args:
        cluster_id: Identifier of the cluster to update (e.g. "cluster-system-architecture").
        title: Optional new human-readable cluster title.
        summary: Optional new Map-of-Content summary describing the cluster.
        color: Optional hex color code (e.g. "#6366f1").
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary with the updated Cluster metadata.
    """
    with tracer.start_as_current_span("blob.tool.update_cluster_metadata") as span:
        ns = namespace or "default"
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.cluster_id", cluster_id)

        store = get_knowledge_store()
        updated = store.update_cluster_metadata(
            cluster_id=cluster_id,
            title=title.strip() if title and title.strip() else None,
            summary=summary.strip() if summary and summary.strip() else None,
            color=color.strip() if color and color.strip() else None,
            namespace=ns,
        )
        if updated is None:
            return {
                "status": "error",
                "namespace": ns,
                "cluster_id": cluster_id,
                "message": f"Cluster '{cluster_id}' not found in namespace '{ns}'.",
            }
        return {
            "status": "ok",
            "namespace": ns,
            "cluster": updated.model_dump(),
        }


def create_curation_suggestion(
    target_slug: str,
    title: str,
    description: str,
    kind: str = "unmerged_episodes",
    episode_ids: list[str] | None = None,
    proposed_markdown: str = "",
    namespace: str = "default",
) -> dict[str, Any]:
    """Create a 1-click co-curation suggestion surfaced on a WikiPage in the Insider View UI.

    Args:
        target_slug: Slug of the WikiPage (or ghost node) this suggestion targets.
        title: Concise headline for the suggestion banner.
        description: Explanation of why this synthesis or update is recommended.
        kind: Category of suggestion ("unmerged_episodes", "expand_ghost", or "contradiction").
        episode_ids: Optional list of pending episode IDs associated with this suggestion.
        proposed_markdown: Optional full replacement/synthesized Markdown body for 1-click apply.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary containing the newly created CurationSuggestion.
    """
    with tracer.start_as_current_span("blob.tool.create_curation_suggestion") as span:
        ns = namespace or "default"
        norm_slug = slugify(target_slug)
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.target_slug", norm_slug)

        store = get_knowledge_store()
        suggestion = store.create_suggestion(
            target_slug=norm_slug,
            title=title.strip() or f"Update {norm_slug}",
            description=description.strip(),
            kind=kind.strip() or "unmerged_episodes",
            episode_ids=episode_ids,
            proposed_markdown=proposed_markdown.strip() or None,
            namespace=ns,
        )
        return {
            "status": "ok",
            "namespace": ns,
            "suggestion_id": suggestion.id,
            "suggestion": suggestion.model_dump(),
        }


def resolve_curation_suggestion(
    suggestion_id: str,
    action: str = "apply",
    namespace: str = "default",
) -> dict[str, Any]:
    """Apply or dismiss an open co-curation suggestion by ID.

    Args:
        suggestion_id: Identifier of the CurationSuggestion to resolve.
        action: Resolution action, either "apply" (merges content into target page) or "dismiss".
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary containing the resolved suggestion and updated WikiPage.
    """
    with tracer.start_as_current_span("blob.tool.resolve_curation_suggestion") as span:
        ns = namespace or "default"
        norm_action: Literal["apply", "dismiss"] = (
            "dismiss"
            if (action or "").strip().lower() in ("dismiss", "dismissed", "reject")
            else "apply"
        )
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.suggestion_id", suggestion_id)
        span.set_attribute("blob.action", norm_action)

        store = get_knowledge_store()
        result = store.resolve_suggestion(
            suggestion_id=suggestion_id,
            action=norm_action,
            namespace=ns,
        )
        if isinstance(result.get("page"), dict):
            page_copy = dict(result["page"])
            page_copy.pop("embedding", None)
            result = {**result, "page": page_copy}
        return result


MEMORY_TOOLS = [
    remember_episode,
    recall_knowledge,
    get_wiki_page,
    upsert_wiki_page,
    delete_wiki_page,
    list_pending_episodes,
    mark_episodes_synthesized,
    get_graph_neighborhood,
    list_semantic_clusters,
    recompute_semantic_clusters,
    update_cluster_metadata,
    create_curation_suggestion,
    resolve_curation_suggestion,
]

CURATOR_TOOLS = [
    list_pending_episodes,
    recall_knowledge,
    get_wiki_page,
    upsert_wiki_page,
    mark_episodes_synthesized,
    get_graph_neighborhood,
    create_curation_suggestion,
    resolve_curation_suggestion,
]

CLUSTER_TOOLS = [
    list_semantic_clusters,
    recompute_semantic_clusters,
    update_cluster_metadata,
    get_wiki_page,
    upsert_wiki_page,
    get_graph_neighborhood,
]
