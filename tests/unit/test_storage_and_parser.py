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

"""Unit tests for Phase 1: Storage Engine, Markdown Parser, Embeddings & Seed Data."""

from __future__ import annotations

import pytest

from blob.storage import (
    EMBEDDING_DIMENSION,
    DeterministicHashEmbedder,
    EventBus,
    GenAIEmbedder,
    GraphRelation,
    InMemoryKnowledgeStore,
    cosine_similarity,
    extract_wikilinks,
    get_embedder,
    get_knowledge_store,
    parse_wiki_markdown,
    seed_knowledge_store,
    serialize_wiki_page,
    set_embedder,
    set_knowledge_store,
    slugify,
    title_from_slug,
)


@pytest.fixture(autouse=True)
def _reset_storage_singletons(monkeypatch: pytest.MonkeyPatch):
    """Ensure clean storage and embedder state around every unit test."""
    monkeypatch.setenv("BLOB_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("BLOB_STORAGE_BACKEND", "memory")
    monkeypatch.delenv("BLOB_AUTO_SEED", raising=False)
    set_embedder(None)
    set_knowledge_store(None)
    yield
    set_embedder(None)
    set_knowledge_store(None)


def test_slugify_and_title_from_slug() -> None:
    assert slugify("Blob Storage Architecture") == "blob-storage-architecture"
    assert slugify("  MCP Memory Interface!! ") == "mcp-memory-interface"
    assert slugify("") == "untitled"
    assert title_from_slug("blob-storage-architecture") == "Blob Storage Architecture"
    assert title_from_slug("mcp-memory-interface") == "MCP Memory Interface"


def test_extract_wikilinks_ignores_code_blocks_and_parses_aliases() -> None:
    markdown = """
# Architecture Overview

Blob connects [[Blob System Design]] to the [[mcp-memory-interface|MCP Memory Interface]].
Duplicate links like [[Blob System Design]] are deduplicated.

Inline code `[[Ignored Inline Link]]` should not be extracted.

```python
# Fenced code block should also be ignored
link = "[[Ignored Fenced Link]]"
```
"""
    links = extract_wikilinks(markdown)
    assert links == [
        ("blob-system-design", "Blob System Design"),
        ("mcp-memory-interface", "MCP Memory Interface"),
    ]


def test_parse_and_serialize_wiki_page_round_trip() -> None:
    raw = """---
slug: "blob-storage-architecture"
title: "Blob Storage Architecture"
namespace: "default"
status: "active"
cluster_id: "cluster-system-architecture"
tags:
  - architecture
  - firestore
relations:
  - type: "part_of"
    target: "blob-system-design"
sources:
  - episode_id: "ep-20261026-8f3a"
    source_agent: "claude-code"
    timestamp: "2026-10-26T10:40:00Z"
updated_at: "2026-10-26T10:42:00Z"
---

# Blob Storage Architecture

Uses Cloud Firestore as part of [[Blob System Design]] and feeds [[MCP Memory Interface]].
"""
    parsed = parse_wiki_markdown(raw)
    assert parsed["slug"] == "blob-storage-architecture"
    assert parsed["title"] == "Blob Storage Architecture"
    assert parsed["cluster_id"] == "cluster-system-architecture"
    assert parsed["tags"] == ["architecture", "firestore"]
    assert parsed["out_links"] == ["blob-system-design", "mcp-memory-interface"]
    assert len(parsed["relations"]) == 1
    assert parsed["relations"][0].type == "part_of"
    assert parsed["relations"][0].target == "blob-system-design"
    assert len(parsed["sources"]) == 1
    assert parsed["sources"][0].episode_id == "ep-20261026-8f3a"

    store = InMemoryKnowledgeStore(embedder=DeterministicHashEmbedder())
    page = store.upsert_wiki_page_from_markdown(raw)
    serialized = serialize_wiki_page(page)
    reparsed = parse_wiki_markdown(serialized)

    assert reparsed["slug"] == page.slug
    assert reparsed["title"] == page.title
    assert reparsed["tags"] == page.tags
    assert reparsed["out_links"] == page.out_links
    assert reparsed["relations"] == page.relations
    assert "[[MCP Memory Interface]]" in reparsed["markdown_body"]


def test_genai_embedder_fails_fast_without_credentials_or_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BLOB_EMBEDDING_BACKEND", "genai")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)

    embedder = get_embedder()
    assert isinstance(embedder, GenAIEmbedder)
    assert embedder.model == "gemini-embedding-001"
    assert embedder.location == "us-east1"

    with pytest.raises(RuntimeError, match="GenAIEmbedder requires"):
        embedder.embed_text("Should fail fast and never fall back to hash")

    class _FailingModels:
        def embed_content(self, **_kwargs):
            raise ValueError("Simulated Vertex AI 403 PermissionDenied")

    class _FailingClient:
        models = _FailingModels()

    failing_embedder = GenAIEmbedder(client=_FailingClient())
    with pytest.raises(RuntimeError, match="GenAI embedding call failed"):
        failing_embedder.embed_text("Simulated API failure")


def test_deterministic_hash_embedder_dimension_and_similarity() -> None:
    embedder = DeterministicHashEmbedder()
    vec_a = embedder.embed_text(
        "Firestore native vector search with 768 dimensions for wiki pages"
    )
    vec_b = embedder.embed_text(
        "Cloud Firestore vector search index storing 768-d embeddings for wiki pages"
    )
    vec_c = embedder.embed_text(
        " Chocolate croissant recipe with butter and almond paste "
    )

    assert len(vec_a) == EMBEDDING_DIMENSION
    assert len(vec_b) == EMBEDDING_DIMENSION
    assert len(vec_c) == EMBEDDING_DIMENSION

    sim_related = cosine_similarity(vec_a, vec_b)
    sim_unrelated = cosine_similarity(vec_a, vec_c)
    assert sim_related > 0.35
    assert sim_related > sim_unrelated + 0.25


def test_in_memory_store_starts_empty_by_default() -> None:
    store = get_knowledge_store()
    assert isinstance(store, InMemoryKnowledgeStore)
    assert store.list_wiki_pages() == []
    assert store.list_episodes() == []
    assert store.list_clusters() == []


def test_ghost_node_creation_promotion_backlinks_and_deletion() -> None:
    store = InMemoryKnowledgeStore(embedder=DeterministicHashEmbedder())

    page_a = store.upsert_wiki_page(
        title="Blob System Design",
        markdown_body=(
            "# Blob System Design\n\n"
            "Depends on [[Blob Storage Architecture]] and future [[Agent Gateway Federation]]."
        ),
        tags=["architecture"],
        relations=[
            GraphRelation(type="depends_on", target="Blob Storage Architecture")
        ],
    )
    assert page_a.slug == "blob-system-design"
    assert set(page_a.out_links) == {
        "blob-storage-architecture",
        "agent-gateway-federation",
    }

    # Both linked targets should now exist as ghost nodes with backlinks to page_a
    ghost_storage = store.get_wiki_page("blob-storage-architecture")
    ghost_gateway = store.get_wiki_page("agent-gateway-federation")
    assert ghost_storage is not None
    assert ghost_storage.status == "ghost"
    assert ghost_storage.backlinks == ["blob-system-design"]

    assert ghost_gateway is not None
    assert ghost_gateway.status == "ghost"
    assert ghost_gateway.title == "Agent Gateway Federation"
    assert ghost_gateway.backlinks == ["blob-system-design"]

    # Upserting content into ghost_storage promotes it from "ghost" -> "active"
    promoted_storage = store.upsert_wiki_page(
        title="Blob Storage Architecture",
        markdown_body=(
            "# Blob Storage Architecture\n\n"
            "Part of [[Blob System Design]] and connects to [[Agent Gateway Federation]]."
        ),
        tags=["firestore"],
    )
    assert promoted_storage.status == "active"
    assert promoted_storage.backlinks == ["blob-system-design"]

    # Page A should now have a backlink from Blob Storage Architecture
    refreshed_a = store.get_wiki_page("blob-system-design")
    assert refreshed_a is not None
    assert "blob-storage-architecture" in refreshed_a.backlinks

    # Ghost gateway should now have backlinks from both pages
    refreshed_gateway = store.get_wiki_page("agent-gateway-federation")
    assert refreshed_gateway is not None
    assert refreshed_gateway.backlinks == [
        "blob-storage-architecture",
        "blob-system-design",
    ]

    # Deleting Blob Storage Architecture removes its backlinks from other pages
    deleted = store.delete_wiki_page("blob-storage-architecture")
    assert deleted is True
    assert store.get_wiki_page("blob-storage-architecture") is None
    after_delete_gw = store.get_wiki_page("agent-gateway-federation")
    assert after_delete_gw is not None
    assert after_delete_gw.backlinks == ["blob-system-design"]


def test_hybrid_recall_and_ego_graph_traversal() -> None:
    store = InMemoryKnowledgeStore(embedder=DeterministicHashEmbedder())
    ep = store.create_episode(
        content="Firestore vector search requires 768-d composite indexes in us-east1.",
        source_agent="claude-code",
        tags=["firestore", "vector"],
    )
    store.upsert_wiki_page(
        title="Blob Storage Architecture",
        markdown_body=(
            "# Blob Storage Architecture\n\n"
            "Uses Cloud Firestore native vector search and links to [[MCP Memory Interface]]."
        ),
        tags=["firestore", "storage"],
    )

    recall_res = store.recall("Firestore vector search", top_k=3, include_episodes=True)
    assert len(recall_res["matches"]) >= 1
    assert recall_res["matches"][0]["slug"] == "blob-storage-architecture"
    # 1-hop neighbor [[MCP Memory Interface]] should be surfaced in neighbors
    neighbor_slugs = [n["slug"] for n in recall_res["neighbors"]]
    assert "mcp-memory-interface" in neighbor_slugs
    # Pending episode should be surfaced in episodes
    ep_ids = [e["id"] for e in recall_res["episodes"]]
    assert ep.id in ep_ids

    # Traverse 1-hop ego-graph
    ego = store.traverse_graph("blob-storage-architecture", depth=1)
    ego_slugs = {n.slug for n in ego.nodes}
    assert ego_slugs == {"blob-storage-architecture", "mcp-memory-interface"}
    assert len(ego.edges) == 1
    assert ego.edges[0].source == "blob-storage-architecture"
    assert ego.edges[0].target == "mcp-memory-interface"


def test_clusters_curation_suggestions_and_event_bus() -> None:
    store = InMemoryKnowledgeStore(embedder=DeterministicHashEmbedder())
    bus = EventBus()
    turn_id = bus.start_turn_collector("turn-42")
    bus.publish("ui_highlight_nodes", {"slugs": ["blob-system-design"]})
    actions = bus.pop_turn_actions(turn_id)
    assert len(actions) == 1
    assert actions[0].type == "ui_highlight_nodes"

    ep1 = store.create_episode(
        content="Add composite index for episodes collection.",
        source_agent="gemini-cli",
        tags=["firestore"],
    )
    store.upsert_wiki_page(
        title="Blob Storage Architecture",
        markdown_body="# Blob Storage Architecture\n\nInitial storage overview.",
        tags=["firestore", "storage"],
    )
    store.upsert_wiki_page(
        title="MCP Memory Interface",
        markdown_body="# MCP Memory Interface\n\nFastMCP tools and resources.",
        tags=["mcp", "tools"],
    )

    clusters = store.recompute_clusters(max_clusters=2)
    assert len(clusters) == 2
    updated_c = store.update_cluster_metadata(
        clusters[0].id,
        title="Core Storage & Protocols",
        summary="Updated summary",
        color="#10b981",
    )
    assert updated_c is not None
    assert updated_c.title == "Core Storage & Protocols"

    # Create and apply a curation suggestion
    sug_apply = store.create_suggestion(
        target_slug="blob-storage-architecture",
        title="Merge index note",
        description="Include episodes composite index details.",
        episode_ids=[ep1.id],
    )
    res_apply = store.resolve_suggestion(sug_apply.id, action="apply")
    assert res_apply["status"] == "ok"
    assert res_apply["suggestion"]["status"] == "applied"

    updated_page = store.get_wiki_page("blob-storage-architecture")
    assert updated_page is not None
    assert "composite index" in updated_page.markdown_body
    assert any(s.episode_id == ep1.id for s in updated_page.sources)

    refreshed_ep = store.get_episode(ep1.id)
    assert refreshed_ep is not None
    assert refreshed_ep.status == "synthesized"
    assert "blob-storage-architecture" in refreshed_ep.synthesized_into

    # Create and dismiss a curation suggestion
    sug_dismiss = store.create_suggestion(
        target_slug="mcp-memory-interface",
        title="Optional formatting tweak",
    )
    res_dismiss = store.resolve_suggestion(sug_dismiss.id, action="dismiss")
    assert res_dismiss["status"] == "ok"
    assert res_dismiss["suggestion"]["status"] == "dismissed"


def test_seed_knowledge_store_populates_four_clusters_and_ghost_nodes() -> None:
    store = InMemoryKnowledgeStore(embedder=DeterministicHashEmbedder())
    summary = seed_knowledge_store(store)

    assert summary["status"] == "seeded"
    assert summary["clusters_count"] == 4
    assert summary["active_pages_count"] == 8
    assert summary["ghost_pages_count"] == 2
    assert summary["pending_episodes_count"] == 3
    assert summary["suggestions_count"] == 2

    ghost_gw = store.get_wiki_page("agent-gateway-federation")
    ghost_bq = store.get_wiki_page("bigquery-telemetry-views")
    assert ghost_gw is not None and ghost_gw.status == "ghost"
    assert ghost_bq is not None and ghost_bq.status == "ghost"
    assert len(ghost_gw.backlinks) >= 2

    # Calling seed again without force=True is idempotent
    repeat = seed_knowledge_store(store, force=False)
    assert repeat["status"] == "already_seeded"
