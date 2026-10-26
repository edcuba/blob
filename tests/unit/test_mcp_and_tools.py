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

"""Unit tests for Phase 2 & Phase 3: ADK Tools, Curation Pipeline, MCP Server & Explorer API."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.agent import MODEL, root_agent
from app.fast_api_app import app
from app.mcp_server import (
    curate,
    get_page,
    list_clusters,
    read_clusters_resource,
    read_graph_resource,
    read_wiki_resource,
    recall,
    remember,
    traverse_graph,
)
from app.storage import (
    DeterministicHashEmbedder,
    InMemoryKnowledgeStore,
    get_event_bus,
    set_embedder,
    set_knowledge_store,
)
from app.tools import (
    MEMORY_TOOLS,
    UI_TOOLS,
    create_curation_suggestion,
    delete_wiki_page,
    get_graph_neighborhood,
    get_wiki_page,
    list_pending_episodes,
    list_semantic_clusters,
    mark_episodes_synthesized,
    recall_knowledge,
    recompute_semantic_clusters,
    remember_episode,
    resolve_curation_suggestion,
    ui_focus_cluster,
    ui_highlight_graph_nodes,
    ui_navigate_to_page,
    update_cluster_metadata,
    upsert_wiki_page,
)


@pytest.fixture(autouse=True)
def _isolated_memory_store(monkeypatch: pytest.MonkeyPatch):
    """Inject a fresh InMemoryKnowledgeStore with DeterministicHashEmbedder for every test."""
    monkeypatch.setenv("BLOB_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("BLOB_STORAGE_BACKEND", "memory")
    monkeypatch.delenv("BLOB_AUTO_SEED", raising=False)
    embedder = DeterministicHashEmbedder()
    store = InMemoryKnowledgeStore(embedder=embedder)
    set_embedder(embedder)
    set_knowledge_store(store)
    yield store
    set_embedder(None)
    set_knowledge_store(None)


def test_agent_hierarchy_and_preserved_invariants() -> None:
    assert MODEL == "gemini-3.8-flash"
    assert root_agent.name == "blob"
    assert len(MEMORY_TOOLS) == 13
    assert len(UI_TOOLS) == 3


def test_all_13_adk_memory_tools_lifecycle() -> None:
    # 1. remember_episode
    ep1 = remember_episode(
        content="Firestore native vector search stores 768-dimensional embeddings.",
        source_agent="claude-code",
        tags=["firestore", "architecture"],
        interaction_id="turn-001",
    )
    assert ep1["status"] == "ok"
    ep1_id = ep1["episode_id"]

    ep2 = remember_episode(
        content="Agent Gateway Federation connects departmental agents over A2A.",
        source_agent="gemini-cli",
        tags=["gateway", "federation"],
    )
    assert ep2["status"] == "ok"
    ep2_id = ep2["episode_id"]

    # 2. list_pending_episodes
    pending = list_pending_episodes()
    assert pending["status"] == "ok"
    assert pending["count"] == 2

    # 3. upsert_wiki_page (creates active page + ghost node from [[wikilink]])
    upserted = upsert_wiki_page(
        title="Blob Storage Architecture",
        markdown_body=(
            "# Blob Storage Architecture\n\n"
            "Uses Cloud Firestore 768-d vectors and connects to [[Agent Gateway Federation]]."
        ),
        tags=["firestore", "storage"],
        source_episode_ids=[ep1_id],
        source_agent="blob",
    )
    assert upserted["status"] == "ok"
    assert upserted["slug"] == "blob-storage-architecture"
    assert "agent-gateway-federation" in upserted["out_links"]

    # 4. get_wiki_page (verify active page and auto-created ghost page)
    fetched = get_wiki_page("blob-storage-architecture")
    assert fetched["status"] == "ok"
    assert len(fetched["source_episodes"]) == 1
    assert fetched["source_episodes"][0]["id"] == ep1_id
    assert "---" in fetched["serialized_markdown"]

    ghost_fetched = get_wiki_page("Agent Gateway Federation")
    assert ghost_fetched["status"] == "ok"
    assert ghost_fetched["page_status"] == "ghost"
    assert "blob-storage-architecture" in ghost_fetched["backlinks"]

    # 5. recall_knowledge
    recalled = recall_knowledge(
        "Firestore 768-d vectors", top_k=3, include_episodes=True
    )
    assert recalled["status"] == "ok"
    assert any(m["slug"] == "blob-storage-architecture" for m in recalled["matches"])
    assert any(n["slug"] == "agent-gateway-federation" for n in recalled["neighbors"])

    # 6. get_graph_neighborhood
    ego = get_graph_neighborhood("blob-storage-architecture", depth=1)
    assert ego["status"] == "ok"
    ego_slugs = {n["slug"] for n in ego["nodes"]}
    assert ego_slugs == {"blob-storage-architecture", "agent-gateway-federation"}

    # 7. mark_episodes_synthesized
    marked = mark_episodes_synthesized(
        episode_ids=[ep2_id], target_slug="agent-gateway-federation"
    )
    assert marked["status"] == "ok"
    assert marked["updated_count"] == 1
    assert list_pending_episodes()["count"] == 0

    # 8. recompute_semantic_clusters, 9. list_semantic_clusters, 10. update_cluster_metadata
    recomputed = recompute_semantic_clusters(max_clusters=2)
    assert recomputed["status"] == "ok"
    assert recomputed["count"] >= 1
    cluster_id = recomputed["clusters"][0]["id"]

    listed_clusters = list_semantic_clusters()
    assert listed_clusters["status"] == "ok"
    assert listed_clusters["count"] == recomputed["count"]

    updated_cluster = update_cluster_metadata(
        cluster_id=cluster_id,
        title="Storage & Federation",
        summary="Synthesized storage and gateway cluster.",
        color="#10b981",
    )
    assert updated_cluster["status"] == "ok"
    assert updated_cluster["cluster"]["title"] == "Storage & Federation"

    # 11. create_curation_suggestion & 12. resolve_curation_suggestion
    sug = create_curation_suggestion(
        target_slug="agent-gateway-federation",
        title="Expand Agent Gateway Federation",
        description="Materialize ghost node with A2A federation details.",
        kind="expand_ghost",
        episode_ids=[ep2_id],
        proposed_markdown=(
            "# Agent Gateway Federation\n\n"
            "Connects departmental agents back to [[Blob Storage Architecture]]."
        ),
    )
    assert sug["status"] == "ok"
    sug_id = sug["suggestion_id"]

    resolved = resolve_curation_suggestion(suggestion_id=sug_id, action="apply")
    assert resolved["status"] == "ok"
    assert resolved["page"]["status"] == "active"

    # 13. delete_wiki_page
    deleted = delete_wiki_page("agent-gateway-federation")
    assert deleted["status"] == "ok"
    assert deleted["deleted"] is True


def test_adk_ui_tools_and_event_bus_turn_collector() -> None:
    bus = get_event_bus()
    turn_id = bus.start_turn_collector("turn-ui-test")

    nav = ui_navigate_to_page(
        "Blob Storage Architecture", reason="Inspect storage schema"
    )
    hl = ui_highlight_graph_nodes(
        ["Blob Storage Architecture", "MCP Memory Interface"],
        reason="Show connected protocol nodes",
    )
    focus = ui_focus_cluster(
        "cluster-system-architecture", reason="Zoom into architecture cluster"
    )

    assert nav["status"] == "ok"
    assert nav["slug"] == "blob-storage-architecture"
    assert hl["status"] == "ok"
    assert hl["slugs"] == ["blob-storage-architecture", "mcp-memory-interface"]
    assert focus["status"] == "ok"

    collected = bus.pop_turn_actions(turn_id)
    assert [e.type for e in collected] == [
        "ui_navigate_to_page",
        "ui_highlight_nodes",
        "ui_focus_cluster",
    ]
    assert bus.pop_turn_actions(turn_id) == []


def test_mcp_tools_and_resources_end_to_end() -> None:
    # 1. MCP remember (without running loop when called synchronously, or with auto_curate=False)
    rem_res = remember(
        content="Cloud Firestore composite vector indexes require 768 dimensions.",
        source_agent="cursor",
        tags=["firestore", "vector-search"],
        auto_curate=False,
    )
    assert rem_res["status"] == "stored"
    ep_id = rem_res["episode_id"]

    # 2. MCP curate (synchronously awaits run_curation_pipeline)
    curate_res = asyncio.run(curate(namespace="default"))
    assert curate_res["status"] == "ok"
    assert ep_id in curate_res["synthesized_episodes"]
    assert len(curate_res["updated_pages"]) >= 1
    created_slug = curate_res["updated_pages"][0]

    # 3. MCP get_page
    page_res = get_page(created_slug)
    assert page_res["status"] == "ok"
    assert page_res["slug"] == created_slug
    assert "768 dimensions" in page_res["markdown_body"]

    # 4. MCP recall
    recall_res = recall("Firestore composite vector indexes", top_k=3)
    assert recall_res["status"] == "ok"
    assert any(m["slug"] == created_slug for m in recall_res["matches"])

    # 5. MCP traverse_graph
    graph_res = traverse_graph(created_slug, depth=1)
    assert graph_res["status"] == "ok"
    assert any(n["slug"] == created_slug for n in graph_res["nodes"])

    # 6. MCP list_clusters
    clusters_res = list_clusters()
    assert clusters_res["status"] == "ok"
    assert clusters_res["count"] >= 1

    # 7. MCP Resources (blob://wiki, blob://clusters, blob://graph)
    wiki_md = read_wiki_resource("default", created_slug)
    assert f"slug: {created_slug}" in wiki_md
    assert "768 dimensions" in wiki_md

    clusters_json = json.loads(read_clusters_resource("default"))
    assert clusters_json["namespace"] == "default"
    assert len(clusters_json["clusters"]) >= 1

    graph_json = json.loads(read_graph_resource("default"))
    assert graph_json["namespace"] == "default"
    assert any(n["slug"] == created_slug for n in graph_json["nodes"])


def test_explorer_api_routes_and_insider_spa() -> None:
    client = TestClient(app)

    # 1. Seed the 4-cluster demo dataset
    seed_resp = client.post("/api/seed", json={"namespace": "default", "force": True})
    assert seed_resp.status_code == 200
    seed_data = seed_resp.json()
    assert seed_data["status"] == "seeded"
    assert seed_data["clusters_count"] == 4
    assert seed_data["active_pages_count"] == 8
    assert seed_data["ghost_pages_count"] == 2

    # 2. GET /api/graph
    graph_resp = client.get("/api/graph")
    assert graph_resp.status_code == 200
    graph_data = graph_resp.json()
    assert graph_data["stats"]["total_pages"] == 10
    assert graph_data["stats"]["active_pages"] == 8
    assert graph_data["stats"]["ghost_pages"] == 2
    assert len(graph_data["clusters"]) == 4

    # 3. GET /api/pages/{slug}
    page_resp = client.get("/api/pages/blob-storage-architecture")
    assert page_resp.status_code == 200
    page_data = page_resp.json()
    assert page_data["slug"] == "blob-storage-architecture"
    assert "---" in page_data["raw_markdown"]
    assert len(page_data["backlinks"]) >= 1
    assert len(page_data["source_episodes"]) >= 1
    assert len(page_data["suggestions"]) >= 1

    # 4. PUT /api/pages/{slug} (edit markdown & add a new [[Wiki Link]] ghost node)
    put_resp = client.put(
        "/api/pages/blob-storage-architecture",
        json={
            "title": "Blob Storage Architecture",
            "markdown_body": (
                "# Blob Storage Architecture\n\n"
                "Updated documentation linking to [[Blob System Design]] and "
                "new concept [[Cloud Run Service Mesh]]."
            ),
            "tags": ["architecture", "firestore", "mesh"],
        },
    )
    assert put_resp.status_code == 200
    updated_page = put_resp.json()
    out_slugs = [link["slug"] for link in updated_page["out_links"]]
    assert "cloud-run-service-mesh" in out_slugs

    # Verify new ghost node exists
    ghost_resp = client.get("/api/pages/cloud-run-service-mesh")
    assert ghost_resp.status_code == 200
    assert ghost_resp.json()["page_status"] == "ghost"

    # 5. POST & GET /api/episodes
    ep_post = client.post(
        "/api/episodes",
        json={
            "content": "Cloud Run Service Mesh enables mTLS across regional MCP gateways.",
            "source_agent": "claude-code",
            "tags": ["mesh", "security"],
        },
    )
    assert ep_post.status_code == 200
    ep_list = client.get("/api/episodes", params={"status": "pending_curation"})
    assert ep_list.status_code == 200
    assert ep_list.json()["count"] >= 4

    # 6. POST /api/suggestions/{id}/apply & dismiss
    sugs = client.get("/api/suggestions").json()["suggestions"]
    assert len(sugs) >= 2
    apply_resp = client.post(f"/api/suggestions/{sugs[0]['id']}/apply")
    assert apply_resp.status_code == 200
    assert apply_resp.json()["suggestion"]["status"] == "applied"

    dismiss_resp = client.post(f"/api/suggestions/{sugs[1]['id']}/dismiss")
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["suggestion"]["status"] == "dismissed"

    # 7. POST /api/curate (materialize ghost node via focus_slug)
    curate_resp = client.post(
        "/api/curate",
        json={"namespace": "default", "focus_slug": "bigquery-telemetry-views"},
    )
    assert curate_resp.status_code == 200
    curate_data = curate_resp.json()
    assert "bigquery-telemetry-views" in curate_data["updated_pages"]
    bq_page = client.get("/api/pages/bigquery-telemetry-views").json()
    assert bq_page["page_status"] == "active"

    # 8. POST /api/chat (verifies active viewport context injection + UI action collection)
    chat_resp = client.post(
        "/api/chat",
        json={
            "message": "What connects to this page?",
            "view_context": {
                "active_page_slug": "blob-storage-architecture",
                "selected_cluster_id": "cluster-system-architecture",
                "visible_neighbors": ["blob-system-design"],
            },
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["status"] == "ok"
    assert chat_data["reply"]
    assert chat_data["view_context"]["active_page_slug"] == "blob-storage-architecture"
    assert len(chat_data["ui_actions"]) >= 1

    # 9. GET /api/events?once=true (SSE connection frame)
    events_resp = client.get("/api/events", params={"once": "true"})
    assert events_resp.status_code == 200
    assert "text/event-stream" in events_resp.headers["content-type"]
    assert '"type": "connected"' in events_resp.text

    # 10. DELETE /api/pages/{slug}
    del_resp = client.delete("/api/pages/cloud-run-service-mesh")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 11. GET /insider SPA route
    insider_resp = client.get("/insider")
    assert insider_resp.status_code == 200
    assert "text/html" in insider_resp.headers["content-type"]
