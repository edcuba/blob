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

"""Universal MCP Server (`blob-memory`) exposing tools and `blob://` resources."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

from blob.agent import run_curation_pipeline
from blob.storage import (
    get_knowledge_store,
    serialize_wiki_page,
    slugify,
    title_from_slug,
)
from blob.tools.memory_tools import (
    get_graph_neighborhood,
    get_wiki_page,
    list_semantic_clusters,
    recall_knowledge,
)

tracer = trace.get_tracer(__name__)

mcp = FastMCP("blob-memory")

_background_tasks: set[asyncio.Task[Any]] = set()


def _schedule_background_curation(namespace: str) -> bool:
    """Schedule `run_curation_pipeline` asynchronously if an event loop is running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    task = loop.create_task(run_curation_pipeline(namespace=namespace))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


@mcp.tool()
def remember(
    content: str,
    source_agent: str = "external",
    tags: list[str] | None = None,
    namespace: str = "default",
    auto_curate: bool = True,
) -> dict[str, Any]:
    """Store an episodic memory in the Blob knowledge fabric and optionally trigger background curation.

    Args:
        content: Raw observation, user preference, architectural decision, or interaction note.
        source_agent: Identifier of the calling agent (defaults to "external").
        tags: Optional list of topical tags.
        namespace: Memory namespace scope (defaults to "default").
        auto_curate: When True, schedules asynchronous wiki synthesis in the background.

    Returns:
        Structured dictionary with `status`, `episode_id`, `namespace`, and stored episode metadata.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.remember") as span:
        span.set_attribute("mcp.tool.name", "remember")
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.source_agent", source_agent or "external")
        span.set_attribute("blob.auto_curate", bool(auto_curate))

        cleaned_content = (content or "").strip()
        if not cleaned_content:
            return {
                "status": "error",
                "namespace": ns,
                "message": "Episode content cannot be empty.",
            }

        store = get_knowledge_store()
        episode = store.create_episode(
            content=cleaned_content,
            source_agent=(source_agent or "external").strip() or "external",
            tags=tags,
            namespace=ns,
        )
        span.set_attribute("blob.episode.id", episode.id)

        curation_scheduled = False
        if auto_curate:
            curation_scheduled = _schedule_background_curation(ns)

        return {
            "status": "stored",
            "episode_id": episode.id,
            "namespace": episode.namespace,
            "auto_curate": auto_curate,
            "curation_scheduled": curation_scheduled,
            "episode": episode.model_dump(exclude={"embedding"}),
        }


@mcp.tool()
def recall(
    query: str,
    namespace: str = "default",
    top_k: int = 5,
    include_episodes: bool = True,
) -> dict[str, Any]:
    """Hybrid search across synthesized Wiki pages, 1-hop graph neighbors, and pending episodes.

    Args:
        query: Natural-language search query or concept name.
        namespace: Memory namespace scope (defaults to "default").
        top_k: Maximum number of synthesized Wiki pages to return (defaults to 5).
        include_episodes: Whether to also search unmerged pending episodes (defaults to True).

    Returns:
        Structured dictionary containing matched Wiki pages, 1-hop neighbors, and pending episodes.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.recall") as span:
        span.set_attribute("mcp.tool.name", "recall")
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.top_k", top_k)

        return recall_knowledge(
            query=query,
            namespace=ns,
            top_k=top_k,
            include_episodes=include_episodes,
        )


@mcp.tool()
def get_page(
    slug_or_title: str,
    namespace: str = "default",
) -> dict[str, Any]:
    """Retrieve a Wiki page by slug or title, including Markdown, frontmatter, links, and provenance.

    Args:
        slug_or_title: Kebab-case slug or human-readable title of the Wiki page.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        Structured dictionary with full Markdown + YAML frontmatter, backlinks, outbound links, and provenance.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.get_page") as span:
        span.set_attribute("mcp.tool.name", "get_page")
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.slug_or_title", slug_or_title)

        res = get_wiki_page(slug_or_title=slug_or_title, namespace=ns)
        if res.get("status") == "ok":
            res["raw_markdown"] = res.get("serialized_markdown", "")
            res["suggestions"] = res.get("open_suggestions", [])
        return res


@mcp.tool()
def traverse_graph(
    seed_slug: str,
    depth: int = 2,
    namespace: str = "default",
) -> dict[str, Any]:
    """Traverse the local ego-graph around a seed Wiki page up to `depth` hops.

    Args:
        seed_slug: Starting Wiki page slug or title.
        depth: Maximum number of link hops to traverse (defaults to 2).
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        Structured dictionary with `nodes` (including ghost nodes), typed `edges`, and `clusters`.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.traverse_graph") as span:
        span.set_attribute("mcp.tool.name", "traverse_graph")
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.seed_slug", seed_slug)
        span.set_attribute("blob.depth", depth)

        return get_graph_neighborhood(
            seed_slug=seed_slug,
            depth=depth,
            namespace=ns,
        )


@mcp.tool()
def list_clusters(
    namespace: str = "default",
) -> dict[str, Any]:
    """Return high-level semantic clusters and their member Wiki page slugs in `namespace`.

    Args:
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        Structured dictionary with cluster count and list of semantic clusters.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.list_clusters") as span:
        span.set_attribute("mcp.tool.name", "list_clusters")
        span.set_attribute("blob.namespace", ns)

        return list_semantic_clusters(namespace=ns)


@mcp.tool()
async def curate(
    namespace: str = "default",
    focus_slug: str | None = None,
) -> dict[str, Any]:
    """Run the agentic curation and clustering pipeline synchronously on pending episodes.

    Args:
        namespace: Memory namespace scope (defaults to "default").
        focus_slug: Optional page or ghost node slug to prioritize during synthesis.

    Returns:
        Structured dictionary with synthesized episode IDs, updated page slugs, and recomputed clusters.
    """
    ns = (namespace or "default").strip() or "default"
    with tracer.start_as_current_span("mcp.tool.curate") as span:
        span.set_attribute("mcp.tool.name", "curate")
        span.set_attribute("blob.namespace", ns)
        if focus_slug:
            span.set_attribute("blob.focus_slug", focus_slug)

        return await run_curation_pipeline(
            namespace=ns,
            focus_slug=focus_slug,
        )


@mcp.resource("blob://wiki/{namespace}/{slug}")
def read_wiki_resource(namespace: str, slug: str) -> str:
    """Return the serialized YAML frontmatter + Markdown body of a Wiki page."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    page = store.get_wiki_page(slug, namespace=ns)
    if page is None:
        norm_slug = slugify(slug)
        title = title_from_slug(norm_slug)
        return (
            "---\n"
            f"slug: {norm_slug}\n"
            f"title: {title}\n"
            f"namespace: {ns}\n"
            "status: not_found\n"
            "---\n\n"
            f"# {title}\n\n"
            f"Wiki page `{norm_slug}` was not found in namespace `{ns}`.\n"
        )
    return serialize_wiki_page(page)


@mcp.resource("blob://clusters/{namespace}")
def read_clusters_resource(namespace: str) -> str:
    """Return a JSON map of semantic clusters in `namespace`."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    clusters = store.list_clusters(namespace=ns)
    return json.dumps(
        {
            "namespace": ns,
            "count": len(clusters),
            "clusters": [c.model_dump() for c in clusters],
        },
        indent=2,
    )


@mcp.resource("blob://graph/{namespace}")
def read_graph_resource(namespace: str) -> str:
    """Return a JSON snapshot of the full node, edge, and cluster graph in `namespace`."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    snapshot = store.get_graph_snapshot(namespace=ns)
    return json.dumps(snapshot.model_dump(), indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
