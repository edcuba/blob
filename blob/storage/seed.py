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

"""Rich 4-cluster seed dataset for interactive exploration and evaluation."""

from __future__ import annotations

from typing import Any

from blob.storage.base import KnowledgeStore, get_event_bus, get_knowledge_store
from blob.storage.models import Cluster, GraphRelation, utc_now_iso


def seed_knowledge_store(
    store: KnowledgeStore | None = None,
    namespace: str = "default",
    force: bool = False,
) -> dict[str, Any]:
    """Populate `store` with a 4-cluster demo dataset, ghost nodes, and pending episodes."""
    target_store = store if store is not None else get_knowledge_store()

    existing_active = target_store.list_wiki_pages(
        namespace=namespace, include_ghosts=False
    )
    if existing_active and not force:
        all_pages = target_store.list_wiki_pages(
            namespace=namespace, include_ghosts=True
        )
        ghosts = [p for p in all_pages if p.status == "ghost"]
        episodes = target_store.list_episodes(namespace=namespace, limit=200)
        pending = [ep for ep in episodes if ep.status == "pending_curation"]
        clusters = target_store.list_clusters(namespace=namespace)
        suggestions = target_store.list_suggestions(namespace=namespace, status="open")
        return {
            "status": "already_seeded",
            "namespace": namespace,
            "pages_count": len(all_pages),
            "active_pages_count": len(existing_active),
            "ghost_pages_count": len(ghosts),
            "episodes_count": len(episodes),
            "pending_episodes_count": len(pending),
            "clusters_count": len(clusters),
            "suggestions_count": len(suggestions),
        }

    if force:
        target_store.clear(namespace=namespace)

    # 1. Create foundational episodes that will be linked as provenance sources
    ep_arch_1 = target_store.create_episode(
        episode_id="ep-20261026-arch01",
        namespace=namespace,
        source_agent="claude-code",
        interaction_id="sess-101",
        tags=["architecture", "firestore", "gcp"],
        content=(
            "We standardized on Cloud Firestore as the single source of truth for "
            "Blob's episodic memory, Markdown wiki pages, semantic clusters, and "
            "768-dimensional native vector search."
        ),
    )
    ep_arch_2 = target_store.create_episode(
        episode_id="ep-20261026-arch02",
        namespace=namespace,
        source_agent="gemini-cli",
        interaction_id="sess-102",
        tags=["architecture", "adk", "mcp"],
        content=(
            "Blob runs as a unified FastAPI service exposing four surfaces: "
            "Universal MCP (/mcp), Explorer REST & SSE (/api/*), ADK/A2A agent "
            "endpoints, and the Insider View React SPA (/insider)."
        ),
    )
    ep_dev_1 = target_store.create_episode(
        episode_id="ep-20261026-dev01",
        namespace=namespace,
        source_agent="cursor",
        interaction_id="sess-201",
        tags=["preferences", "python", "adk"],
        content=(
            "Developer conventions require Python 3.11+, uv package management, "
            "Pydantic v2 schemas, ruff linting, and preserving root_agent.name='blob' "
            "with role-based model routing: gemini-3.8-flash for user-facing and simple "
            "agents, gemini-4-argon for wiki_curator synthesis."
        ),
    )
    ep_dev_2 = target_store.create_episode(
        episode_id="ep-20261026-dev02",
        namespace=namespace,
        source_agent="claude-code",
        interaction_id="sess-202",
        tags=["testing", "evaluation", "embeddings"],
        content=(
            "Production embeddings must fail fast using gemini-embedding-001 "
            "(output_dimensionality=768, us-east1). DeterministicHashEmbedder is "
            "strictly opt-in for unit tests via BLOB_EMBEDDING_BACKEND=hash."
        ),
    )
    ep_road_1 = target_store.create_episode(
        episode_id="ep-20261026-road01",
        namespace=namespace,
        source_agent="insider-ui",
        interaction_id="sess-301",
        tags=["roadmap", "frontend", "ux"],
        content=(
            "The Insider View workspace combines a 2D force-directed graph canvas "
            "with cluster hulls, a live Markdown Wiki editor with clickable "
            "[[Wiki Links]], and an Agent-in-the-Loop sidebar."
        ),
    )
    ep_road_2 = target_store.create_episode(
        episode_id="ep-20261026-road02",
        namespace=namespace,
        source_agent="gemini-cli",
        interaction_id="sess-302",
        tags=["roadmap", "terraform", "deployment"],
        content=(
            "Single-project Terraform provisions Vertex AI Agent Runtime, Cloud "
            "Firestore with 768-d composite vector indexes, and GCS/BigQuery "
            "completion telemetry."
        ),
    )
    ep_wf_1 = target_store.create_episode(
        episode_id="ep-20261026-wf01",
        namespace=namespace,
        source_agent="claude-code",
        interaction_id="sess-401",
        tags=["workflows", "mcp", "recall"],
        content=(
            "External agents connect to Blob over MCP using 6 core tools "
            "(remember, recall, get_page, traverse_graph, list_clusters, curate) "
            "and 3 blob:// resources."
        ),
    )
    ep_wf_2 = target_store.create_episode(
        episode_id="ep-20261026-wf02",
        namespace=namespace,
        source_agent="blob-curator",
        interaction_id="sess-402",
        tags=["workflows", "curation", "adk"],
        content=(
            "Blob uses a two-stage ingestion pipeline: synchronous <200ms episodic "
            "ingest followed by asynchronous wiki_curator synthesis and "
            "cluster_analyst reorganization."
        ),
    )

    # 2. Define the 4 canonical clusters
    clusters_spec = [
        Cluster(
            id="cluster-system-architecture",
            namespace=namespace,
            title="System Architecture",
            summary=(
                "Core architectural decisions covering the unified FastAPI + ADK + "
                "FastMCP topology and Cloud Firestore 768-d vector storage."
            ),
            color="#6366f1",
            page_slugs=[
                "blob-system-design",
                "blob-storage-architecture",
                "agent-gateway-federation",
                "bigquery-telemetry-views",
            ],
            centroid_x=-0.45,
            centroid_y=-0.35,
            updated_at=utc_now_iso(),
        ),
        Cluster(
            id="cluster-developer-preferences",
            namespace=namespace,
            title="Developer Preferences",
            summary=(
                "Engineering standards for Python 3.11+, ADK tool contracts, "
                "fail-fast 768-d embeddings, and automated quality gates."
            ),
            color="#10b981",
            page_slugs=[
                "python-and-adk-conventions",
                "testing-and-evaluation-standards",
            ],
            centroid_x=0.45,
            centroid_y=-0.35,
            updated_at=utc_now_iso(),
        ),
        Cluster(
            id="cluster-project-roadmap",
            namespace=namespace,
            title="Project Roadmap",
            summary=(
                "Visual co-curation UX in the Insider View SPA and declarative "
                "single-project GCP deployment on Vertex AI Agent Runtime."
            ),
            color="#f59e0b",
            page_slugs=[
                "insider-view-workspace",
                "gcp-single-project-deployment",
            ],
            centroid_x=-0.45,
            centroid_y=0.35,
            updated_at=utc_now_iso(),
        ),
        Cluster(
            id="cluster-agent-workflows",
            namespace=namespace,
            title="Agent Workflows",
            summary=(
                "Universal MCP memory protocol, hybrid graph + vector recall, and "
                "two-stage agentic synthesis via wiki_curator and cluster_analyst."
            ),
            color="#ec4899",
            page_slugs=[
                "mcp-memory-interface",
                "agentic-curation-workflow",
            ],
            centroid_x=0.45,
            centroid_y=0.35,
            updated_at=utc_now_iso(),
        ),
    ]

    for c_obj in clusters_spec:
        target_store.save_cluster(c_obj)

    # 3. Upsert the 8 active WikiPages (which also automatically materializes
    #    the 2 ghost nodes: [[Agent Gateway Federation]] & [[BigQuery Telemetry Views]])
    target_store.upsert_wiki_page(
        slug="blob-system-design",
        title="Blob System Design",
        namespace=namespace,
        cluster_id="cluster-system-architecture",
        tags=["architecture", "adk", "fastapi", "mcp"],
        relations=[
            GraphRelation(type="depends_on", target="blob-storage-architecture"),
            GraphRelation(type="relates_to", target="mcp-memory-interface"),
        ],
        source_episode_ids=[ep_arch_2.id],
        source_agent="gemini-cli",
        x=-0.55,
        y=-0.42,
        markdown_body=(
            "# Blob System Design\n\n"
            "**Blob** is a visual memory fabric agent that organizes knowledge and "
            "memories from past agent interactions into an Obsidian-style Markdown graph.\n\n"
            "## Four Serving Surfaces\n"
            "1. **Universal MCP Surface**: Exposes memory tools and `blob://` resources via [[MCP Memory Interface]].\n"
            "2. **Explorer REST & SSE API**: Powers real-time graph exploration in the [[insider-view-workspace|Insider View Visual Workspace]].\n"
            "3. **ADK & A2A Coordinator**: Runs `blob` (`gemini-3.8-flash`) with `AgentTool`-wrapped sub-agents (`wiki_curator` on `gemini-4-argon`, `cluster_analyst` on `gemini-3.8-flash`) following [[python-and-adk-conventions|Python & ADK Engineering Conventions]].\n"
            "4. **Future Mesh Integration**: Planned cross-project discovery via [[Agent Gateway Federation]].\n\n"
            "All persistence is backed by [[Blob Storage Architecture]] and curated via [[Agentic Curation Workflow]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="blob-storage-architecture",
        title="Blob Storage Architecture",
        namespace=namespace,
        cluster_id="cluster-system-architecture",
        tags=["architecture", "firestore", "vector-search", "storage"],
        relations=[
            GraphRelation(type="part_of", target="blob-system-design"),
            GraphRelation(type="relates_to", target="mcp-memory-interface"),
        ],
        source_episode_ids=[ep_arch_1.id],
        source_agent="claude-code",
        x=-0.34,
        y=-0.28,
        markdown_body=(
            "# Blob Storage Architecture\n\n"
            "Blob uses **Cloud Firestore** as its single source of truth for documents, "
            "graph edges, and 768-dimensional embeddings as part of the [[Blob System Design]].\n\n"
            "## Core Collections\n"
            "- **`episodes`**: Raw interaction notes with `Vector[768]` embeddings for immediate recall.\n"
            "- **`wiki_pages`**: Synthesized Markdown articles, inline `[[wikilinks]]`, ghost nodes, and bidirectional `backlinks`.\n"
            "- **`clusters`**: Semantic groupings with 2D centroids.\n"
            "- **`curation_suggestions`**: 1-click co-curation actions surfaced in the [[insider-view-workspace|Insider View Visual Workspace]].\n\n"
            "Production deployments provision composite vector indexes via [[GCP Single-Project Deployment]] and export trace analytics to [[BigQuery Telemetry Views]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="python-and-adk-conventions",
        title="Python & ADK Engineering Conventions",
        namespace=namespace,
        cluster_id="cluster-developer-preferences",
        tags=["preferences", "python", "adk", "conventions"],
        relations=[
            GraphRelation(type="relates_to", target="blob-system-design"),
            GraphRelation(type="relates_to", target="testing-and-evaluation-standards"),
        ],
        source_episode_ids=[ep_dev_1.id],
        source_agent="cursor",
        x=0.38,
        y=-0.42,
        markdown_body=(
            "# Python & ADK Engineering Conventions\n\n"
            "All backend and agent code in [[Blob System Design]] adheres to strict "
            "Google ADK and Python 3.11+ engineering standards.\n\n"
            "## Non-Negotiable Rules\n"
            '- **Model & Agent Identity**: Keep `root_agent.name = "blob"` in sync with `agents-cli-manifest.yaml`; assign models per role in `blob/app_utils/model_router.py` (`gemini-3.8-flash` fast tier, `gemini-4-argon` complex tier).\n'
            "- **`AgentTool` Orchestration**: Wrap `wiki_curator` and `cluster_analyst` using `AgentTool` so `blob` retains turn control to emit UI actions during [[Agentic Curation Workflow]].\n"
            "- **Verification**: Enforce `ruff`, `ty`, and automated suites defined in [[testing-and-evaluation-standards|Testing & Evaluation Standards]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="testing-and-evaluation-standards",
        title="Testing & Evaluation Standards",
        namespace=namespace,
        cluster_id="cluster-developer-preferences",
        tags=["testing", "evaluation", "embeddings", "quality"],
        relations=[
            GraphRelation(type="depends_on", target="python-and-adk-conventions"),
            GraphRelation(type="relates_to", target="agentic-curation-workflow"),
        ],
        source_episode_ids=[ep_dev_2.id],
        source_agent="claude-code",
        x=0.54,
        y=-0.26,
        markdown_body=(
            "# Testing & Evaluation Standards\n\n"
            "Quality gates validate every layer of [[Blob Storage Architecture]] and "
            "[[python-and-adk-conventions|Python & ADK Engineering Conventions]] prior to deployment.\n\n"
            "## Embedding Policy\n"
            "- **Fail-Fast Production Embeddings**: `GenAIEmbedder` (`gemini-embedding-001`, `output_dimensionality=768`, `us-east1`) raises an explicit `RuntimeError` if credentials or API calls fail.\n"
            "- **Opt-In Unit Test Hashing**: `DeterministicHashEmbedder` is restricted strictly to unit tests via `BLOB_EMBEDDING_BACKEND=hash`.\n"
            "- **Quality Flywheel**: Multi-turn agent behavior is graded with `agents-cli eval run`."
        ),
    )

    target_store.upsert_wiki_page(
        slug="insider-view-workspace",
        title="Insider View Visual Workspace",
        namespace=namespace,
        cluster_id="cluster-project-roadmap",
        tags=["roadmap", "frontend", "react", "graph"],
        relations=[
            GraphRelation(type="part_of", target="blob-system-design"),
            GraphRelation(type="relates_to", target="agentic-curation-workflow"),
        ],
        source_episode_ids=[ep_road_1.id],
        source_agent="insider-ui",
        x=-0.52,
        y=0.28,
        markdown_body=(
            "# Insider View Visual Workspace\n\n"
            "The **Insider View** (`/insider`) is a React + TypeScript workspace for "
            "inspecting and co-curating the memory fabric in [[Blob System Design]].\n\n"
            "## Key Capabilities\n"
            "- **2D Force Graph & Cluster Hulls**: Renders active Wiki pages, dashed **Ghost Nodes** (such as [[Agent Gateway Federation]]), and typed edges.\n"
            "- **Live Markdown Wiki Editor**: Supports inline `[[Wiki Links]]`, backlink navigation, episode provenance drawers, and 1-click curation suggestions.\n"
            "- **Bidirectional Agent Sidebar**: Streams active viewport context to `blob` and animates graph highlights emitted during [[Agentic Curation Workflow]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="gcp-single-project-deployment",
        title="GCP Single-Project Deployment",
        namespace=namespace,
        cluster_id="cluster-project-roadmap",
        tags=["roadmap", "gcp", "terraform", "deployment"],
        relations=[
            GraphRelation(type="depends_on", target="blob-storage-architecture"),
            GraphRelation(type="relates_to", target="bigquery-telemetry-views"),
        ],
        source_episode_ids=[ep_road_2.id],
        source_agent="gemini-cli",
        x=-0.35,
        y=0.44,
        markdown_body=(
            "# GCP Single-Project Deployment\n\n"
            "Blob deploys as a unified multi-stage container to **Vertex AI Agent Runtime** "
            "provisioned declaratively via Terraform.\n\n"
            "## Infrastructure Components\n"
            "- **Cloud Firestore (`firestore.tf`)**: Provisions `(default)` database in `FIRESTORE_NATIVE` mode with 768-d composite vector indexes for [[Blob Storage Architecture]].\n"
            "- **IAM & Identity**: Grants `roles/datastore.user` to both `vertex_sa` and `AGENT_IDENTITY`.\n"
            "- **Observability Pipeline**: Exports OpenTelemetry traces to Cloud Trace and NDJSON completions to GCS and [[BigQuery Telemetry Views]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="mcp-memory-interface",
        title="MCP Memory Interface",
        namespace=namespace,
        cluster_id="cluster-agent-workflows",
        tags=["workflows", "mcp", "tools", "resources"],
        relations=[
            GraphRelation(type="depends_on", target="blob-storage-architecture"),
            GraphRelation(type="relates_to", target="agentic-curation-workflow"),
        ],
        source_episode_ids=[ep_wf_1.id],
        source_agent="claude-code",
        x=0.36,
        y=0.28,
        markdown_body=(
            "# MCP Memory Interface\n\n"
            "External IDE agents, CLIs, and workflows connect to Blob via FastMCP over "
            "Streamable HTTP (`/mcp`) or `stdio` (`uv run python -m blob.mcp_server`).\n\n"
            "## Exposed Surface\n"
            "- **Tools**: `remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`, and `curate`.\n"
            "- **Resources**: `blob://wiki/{namespace}/{slug}`, `blob://clusters/{namespace}`, and `blob://graph/{namespace}`.\n\n"
            "Memories ingested via `remember` are stored in [[Blob Storage Architecture]] and synthesized by [[Agentic Curation Workflow]]."
        ),
    )

    target_store.upsert_wiki_page(
        slug="agentic-curation-workflow",
        title="Agentic Curation Workflow",
        namespace=namespace,
        cluster_id="cluster-agent-workflows",
        tags=["workflows", "curation", "synthesis", "clusters"],
        relations=[
            GraphRelation(type="depends_on", target="mcp-memory-interface"),
            GraphRelation(type="relates_to", target="insider-view-workspace"),
        ],
        source_episode_ids=[ep_wf_2.id],
        source_agent="blob-curator",
        x=0.54,
        y=0.44,
        markdown_body=(
            "# Agentic Curation Workflow\n\n"
            "Blob decouples fast episodic ingestion from deep LLM wiki synthesis so "
            "calling agents on the [[MCP Memory Interface]] never block.\n\n"
            "## Two-Stage Pipeline\n"
            '1. **Stage 1 — Fast Ingest (`<200ms`)**: Embeds raw observations into `episodes` (`status="pending_curation"`).\n'
            "2. **Stage 2 — Agentic Synthesis**: `wiki_curator` merges pending episodes into structured Markdown pages, materializes ghost nodes, and `cluster_analyst` updates semantic clusters for the [[insider-view-workspace|Insider View Visual Workspace]]."
        ),
    )

    # Position the two automatically created ghost nodes cleanly near their clusters
    ghost_gw = target_store.get_wiki_page(
        "agent-gateway-federation", namespace=namespace
    )
    if ghost_gw is not None:
        target_store.upsert_wiki_page(
            slug=ghost_gw.slug,
            title=ghost_gw.title,
            markdown_body="",
            namespace=namespace,
            status="ghost",
            cluster_id="cluster-system-architecture",
            x=-0.64,
            y=-0.12,
        )

    ghost_bq = target_store.get_wiki_page(
        "bigquery-telemetry-views", namespace=namespace
    )
    if ghost_bq is not None:
        target_store.upsert_wiki_page(
            slug=ghost_bq.slug,
            title=ghost_bq.title,
            markdown_body="",
            namespace=namespace,
            status="ghost",
            cluster_id="cluster-system-architecture",
            x=-0.18,
            y=0.14,
        )

    # 4. Create 3 pending episodes in the inbox for live curation & recall demos
    ep_pending_1 = target_store.create_episode(
        episode_id="ep-20261026-pend01",
        namespace=namespace,
        source_agent="claude-code",
        interaction_id="sess-501",
        tags=["firestore", "vector-search", "indexing"],
        content=(
            "Composite Firestore vector indexes on `wiki_pages` (namespace ASC + "
            "embedding[768] FLAT) and `episodes` (namespace ASC + status ASC + "
            "embedding[768] FLAT) reduce hybrid recall latency below 45ms."
        ),
    )
    ep_pending_2 = target_store.create_episode(
        episode_id="ep-20261026-pend02",
        namespace=namespace,
        source_agent="gemini-cli",
        interaction_id="sess-502",
        tags=["gateway", "a2a", "federation"],
        content=(
            "Agent Gateway Federation will allow multiple departmental ADK agents "
            "to share a federated `default` memory namespace while isolating "
            "team-specific private namespaces."
        ),
    )
    target_store.create_episode(
        episode_id="ep-20261026-pend03",
        namespace=namespace,
        source_agent="insider-ui",
        interaction_id="sess-503",
        tags=["frontend", "ux", "graph"],
        content=(
            "Clicking a dashed Ghost Node in the Insider View graph canvas opens "
            "a 1-click synthesis prompt so the user or wiki_curator can turn the "
            "concept into a full Wiki page."
        ),
    )

    # 5. Create 2 open CurationSuggestions for 1-click co-curation in the UI
    target_store.create_suggestion(
        suggestion_id="sug-storage-index-01",
        namespace=namespace,
        target_slug="blob-storage-architecture",
        kind="unmerged_episodes",
        title="Merge composite vector index benchmarks",
        description=(
            "1 new episode from claude-code documents composite Firestore vector "
            "index fields and <45ms hybrid recall latency."
        ),
        episode_ids=[ep_pending_1.id],
    )
    target_store.create_suggestion(
        suggestion_id="sug-ghost-gateway-02",
        namespace=namespace,
        target_slug="agent-gateway-federation",
        kind="expand_ghost",
        title="Synthesize ghost node: Agent Gateway Federation",
        description=(
            "Materialize [[Agent Gateway Federation]] from recent A2A federation "
            "architecture notes."
        ),
        episode_ids=[ep_pending_2.id],
        proposed_markdown=(
            "# Agent Gateway Federation\n\n"
            "**Agent Gateway Federation** connects departmental ADK and A2A agents "
            "to the shared [[Blob System Design]] memory fabric via [[MCP Memory Interface]].\n\n"
            "## Namespace Isolation\n"
            '- **Shared Fabric (`namespace="default"`)**: Cross-pollinates architectural knowledge across agents.\n'
            "- **Team Namespaces**: Isolates sensitive domain episodes while preserving graph schema compatibility with [[Blob Storage Architecture]]."
        ),
    )

    all_pages = target_store.list_wiki_pages(namespace=namespace, include_ghosts=True)
    active_pages = [p for p in all_pages if p.status == "active"]
    ghost_pages = [p for p in all_pages if p.status == "ghost"]
    episodes = target_store.list_episodes(namespace=namespace, limit=200)
    pending_episodes = [ep for ep in episodes if ep.status == "pending_curation"]
    clusters = target_store.list_clusters(namespace=namespace)
    suggestions = target_store.list_suggestions(namespace=namespace, status="open")

    get_event_bus().publish(
        "store_seeded",
        {
            "pages_count": len(all_pages),
            "clusters_count": len(clusters),
            "pending_episodes_count": len(pending_episodes),
        },
        namespace=namespace,
    )

    return {
        "status": "seeded",
        "namespace": namespace,
        "pages_count": len(all_pages),
        "active_pages_count": len(active_pages),
        "ghost_pages_count": len(ghost_pages),
        "episodes_count": len(episodes),
        "pending_episodes_count": len(pending_episodes),
        "clusters_count": len(clusters),
        "suggestions_count": len(suggestions),
    }
