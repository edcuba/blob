# Blob — Architecture & Design Specification

> **Status:** Implemented & Verified
> **Mission:** *"Blob is a memory fabric agent organizing the knowledge and memories of past interactions in a visual way."*
> **Deep-Dive Companions:**
> - [`spec/architecture-and-deployment.md`](architecture-and-deployment.md) — Detailed sequence diagrams, state machines, ER diagrams, and GCP Terraform/deployment architecture.

---

## 1. Problem Statement & Vision

AI agents accumulate rich context across interactions—user preferences, architectural decisions, domain knowledge, and episodic history. Yet this memory layer typically suffers from three gaps:

1. **Opacity**: Users cannot easily inspect, audit, or visually explore what their agents actually know.
2. **Fragmentation**: Memories are trapped in flat vector chunks or isolated chat transcripts without synthesis, hierarchy, or relational links.
3. **No Co-Curation Loop**: When memories become stale, noisy, or contradictory, humans lack an interactive environment to reorganize knowledge alongside the agent.

**Blob** bridges agent knowledge and human understanding through:
- **Universal MCP Memory Server**: Any external agent connects via MCP (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`, `curate`) and `blob://` resources.
- **LLM-Wiki Synthesis & Obsidian Graph**: Memories are curated into Markdown-first Wiki pages with YAML frontmatter, inline `[[Wiki Links]]` (including "ghost nodes" for referenced-but-unwritten concepts), typed relations, and bidirectional backlinks.
- **Hybrid Semantic Clustering**: Vector embeddings group related pages into high-level semantic clusters, while the ADK Curator generates human-readable Cluster names and Map-of-Content (`MOC`) summaries.
- **Interactive "Insider View" UI**: A React + TypeScript (Vite) workspace combining a 2D Force-Directed Graph & Cluster Map, a live Markdown Wiki reader/editor, 1-click curation suggestions, and a bidirectional **Agent-in-the-Loop** chat sidebar.

---

## 2. System Architecture

```mermaid
flowchart TB
    subgraph External["External Agents (IDEs, CLIs, Workflows)"]
        EA["MCP Clients"]
    end

    subgraph Human["Human User ('Insider View' Web UI)"]
        UI_Graph["2D Force Graph & Cluster Canvas"]
        UI_Wiki["Markdown Wiki Viewer / Editor"]
        UI_Chat["Bidirectional Agent-in-the-Loop Sidebar"]
    end

    subgraph Service["Blob Unified Service (FastAPI + ADK + FastMCP)"]
        MCP["MCP Server (/mcp HTTP/SSE & stdio)"]
        API["REST & SSE Explorer API (/api/*)"]
        subgraph Agents["Google ADK Agent Hierarchy (blob/agent.py)"]
            RootAgent["root_agent ('blob')\nInteractive Guide & Co-Curator"]
            CuratorAgent["wiki_curator\nEpisodic Synthesis & Link Hygiene"]
            ClusterAgent["cluster_analyst\nEmbedding Clustering & MOC Naming"]
            RootAgent --> CuratorAgent
            RootAgent --> ClusterAgent
        end
        Store["KnowledgeStore Abstraction (blob/storage/)"]
    end

    subgraph GCP["Cloud Persistence (GCP / Local Fallback)"]
        FS[("Firestore (Single Source of Truth)\n• episodes (Vector)\n• wiki_pages (Markdown + Vector + Graph)\n• clusters\n• curation_suggestions")]
        Mem[("InMemoryKnowledgeStore\n(Local Dev / CI / Demo Seed)")]
    end

    EA <-->|"MCP Tools & blob:// Resources"| MCP
    UI_Graph & UI_Wiki <-->|"REST + SSE Live Events"| API
    UI_Chat <-->|"ADK Run + Active View Context + UI Action Events"| RootAgent
    MCP --> Store
    MCP -.->|"Async Curation Trigger"| CuratorAgent
    API --> Store
    RootAgent & CuratorAgent & ClusterAgent --> Store
    Store --> FS
    Store -.->|"Fallback / Tests"| Mem
```

---

## 3. Core Architectural Decisions

| Area | Decision | Details |
| :--- | :--- | :--- |
| **1. Cloud Storage** | **Firestore Single Source of Truth** | Firestore stores `episodes`, `wiki_pages` (Markdown body + metadata + graph edges), `clusters`, and `curation_suggestions` with Firestore Native Vector Search (`VectorValue` / `find_nearest`, `dimension=768`). YAML frontmatter + Markdown is serialized on the fly when needed. |
| **2. Local & Test Abstraction** | **`KnowledgeStore` Interface + `BLOB_STORAGE_BACKEND`** | `blob/storage/` defines a unified `KnowledgeStore` protocol with `FirestoreKnowledgeStore` and `InMemoryKnowledgeStore`. Controlled by `BLOB_STORAGE_BACKEND` (`memory` \| `firestore` \| `auto`): defaults to `memory` in local dev and when `INTEGRATION_TEST=TRUE`, and selects `firestore` when `BLOB_STORAGE_BACKEND=firestore` or on Agent Runtime (`GOOGLE_CLOUD_AGENT_ENGINE_ID` set). |
| **3. Ingestion & Curation** | **Two-Stage Async Pipeline** | 1. **Fast Ingest**: `remember` writes a raw `Episode` with its embedding to Firestore (`status="pending_curation"`) so it is immediately searchable (`<200ms`).<br>2. **Agentic Curation**: Background task (or explicit `curate` call) runs `wiki_curator` to synthesize pending episodes into Markdown `wiki_pages`, extract `[[wikilinks]]`, and resolve contradictions. |
| **4. Graph & Ghost Nodes** | **Obsidian-Faithful `[[Wiki Links]]` + Frontmatter Relations** | Inline `[[Page Title]]` or `[[slug\|Display]]` links are parsed on save, resolving against existing pages by slug or case-insensitive `title` before creating lightweight **Ghost Nodes** (`status="ghost"`) for referenced-but-unwritten pages (and deduplicating ghosts when a page is later created with a custom slug). Primary `recall()` matches return `status="active"` pages while surfacing connected active and ghost nodes in 1-hop `neighbors`. YAML frontmatter also supports typed `relations` (`part_of`, `depends_on`, `contradicts`, `relates_to`). |
| **5. Embeddings & Clustering** | **Fail-Fast 768-d Embeddings + Hybrid Clustering** | Uses `google-genai` (`gemini-embedding-001` / `text-embedding-005`) with explicit `output_dimensionality=768` and `GOOGLE_CLOUD_EMBEDDING_LOCATION` (defaulting to `us-east1`). Missing or failing embedders in production raise an explicit error (no silent fallback; deterministic hash embeddings are strictly opt-in for unit tests via `BLOB_EMBEDDING_BACKEND=hash`). `cluster_analyst` generates human-readable cluster titles, summaries, colors, and Map-of-Content (`MOC`) overview pages. |
| **6. MCP Surface** | **FastAPI `/mcp` + `stdio` Entrypoint** | Built with the `mcp` SDK (`FastMCP`), mounted at `/mcp` on FastAPI and runnable via `uv run python -m blob.mcp_server`. Exposes Tools (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`, `curate`) and Resources (`blob://wiki/{namespace}/{slug}`, `blob://clusters/{namespace}`, `blob://graph/{namespace}`). |
| **7. Scoping & Provenance** | **Unified Graph + Optional `namespace`** | Defaults to `namespace="default"` so memories cross-pollinate across external agents, while supporting custom namespaces and recording `source_agent`, `interaction_id`, and timestamps on every episode and wiki revision. |
| **8. ADK Agent Hierarchy** | **Root `blob` + `AgentTool` Sub-Agents** | `root_agent` (`name="blob"`) acts as the interactive guide and co-curator, invoking `wiki_curator` and `cluster_analyst` via `AgentTool` so `blob` retains turn control to emit UI actions afterward (while `wiki_curator` and `cluster_analyst` are also directly invocable for background `/api/curate` and MCP `curate` runs). |
| **9. Frontend Stack** | **React + TypeScript (Vite) at `/insider`** | Split-pane Obsidian-inspired UI (2D Force Graph/Cluster Canvas + Markdown Wiki Reader/Editor + Agent Sidebar) in `frontend/`. Built static assets (`frontend/dist`) are served by FastAPI at `/insider` alongside ADK's Dev UI (`/`), and built via a multi-stage `Dockerfile`. |
| **10. Agent-in-the-Loop UX** | **Bidirectional Context & Dual UI Action Delivery** | The UI sends active view state (`active_page_slug`, `selected_cluster_id`, `visible_neighbors`) with every chat turn. `blob` emits structured UI commands (`navigate_to_page`, `highlight_nodes`, `focus_cluster`, `refresh_page`) delivered over both `GET /api/events` (SSE) and the `POST /api/chat` response payload, and surfaces 1-click curation suggestions on pages. |

---

## 4. Data Models

### 4.1 `Episode` (Firestore `episodes` collection)
```json
{
  "id": "ep-20261026-8f3a",
  "namespace": "default",
  "content": "User decided to use Firestore native vector search as the single source of truth for Blob.",
  "source_agent": "claude-code",
  "interaction_id": "sess-912",
  "tags": ["architecture", "storage", "gcp"],
  "status": "pending_curation",
  "synthesized_into": ["blob-storage-architecture"],
  "embedding": "<Vector[768]>",
  "created_at": "2026-10-26T10:40:00Z"
}
```

### 4.2 `WikiPage` (Firestore `wiki_pages` collection, serialized as Markdown + Frontmatter)
```markdown
---
slug: "blob-storage-architecture"
title: "Blob Storage Architecture"
namespace: "default"
status: "active" # "active" | "ghost" | "archived"
cluster_id: "cluster-system-architecture"
tags: ["architecture", "firestore"]
relations:
  - type: "part_of"
    target: "blob-system-design"
  - type: "relates_to"
    target: "mcp-memory-interface"
sources:
  - episode_id: "ep-20261026-8f3a"
    source_agent: "claude-code"
    timestamp: "2026-10-26T10:40:00Z"
updated_at: "2026-10-26T10:42:00Z"
---

# Blob Storage Architecture

Blob uses **Cloud Firestore** as its single source of truth for documents, graph edges, and embeddings as part of the [[Blob System Design]].

## Key Responsibilities
- **Firestore**: Unified store for `wiki_pages` (Markdown body, frontmatter metadata, graph links, and native vector search embeddings), `episodes`, and `clusters`.
- **Local Fallback**: Uses `InMemoryKnowledgeStore` for offline development and automated test suites, feeding into the [[MCP Memory Interface]].
```

### 4.3 `Cluster` (Firestore `clusters` collection)
```json
{
  "id": "cluster-system-architecture",
  "namespace": "default",
  "title": "System Architecture & Cloud Storage",
  "summary": "Core architectural decisions covering Firestore vector storage, graph indexing, and MCP service topology.",
  "color": "#6366f1",
  "page_slugs": ["blob-storage-architecture", "blob-system-design", "mcp-memory-interface"],
  "centroid_x": 0.42,
  "centroid_y": -0.18,
  "updated_at": "2026-10-26T10:45:00Z"
}
```

### 4.4 `CurationSuggestion` (Firestore `curation_suggestions` collection)
```json
{
  "id": "sug-001",
  "namespace": "default",
  "target_slug": "blob-storage-architecture",
  "kind": "unmerged_episodes",
  "title": "2 new episodes mention storage indexing",
  "description": "Merge recent interaction notes regarding composite vector indexes into this page.",
  "episode_ids": ["ep-20261026-9b1c"],
  "status": "open"
}
```

---

## 5. API & Protocol Specifications

### 5.1 MCP Server (`/mcp` & `stdio`)
- **Tools**:
  - `remember(content: str, source_agent: str = "external", tags: list[str] = [], namespace: str = "default", auto_curate: bool = True) -> dict`: Stores an episodic memory and queues background curation.
  - `recall(query: str, namespace: str = "default", top_k: int = 5, include_episodes: bool = True) -> dict`: Hybrid search across synthesized Wiki pages (vector + keyword + 1-hop graph neighbors) and recent unmerged episodes.
  - `get_page(slug_or_title: str, namespace: str = "default") -> dict`: Returns full Markdown, frontmatter, backlinks, outbound links, and provenance.
  - `traverse_graph(seed_slug: str, depth: int = 2, namespace: str = "default") -> dict`: Returns the local ego-graph (nodes, ghost nodes, typed edges, clusters) around a concept.
  - `list_clusters(namespace: str = "default") -> dict`: Returns the high-level semantic clusters and their member pages.
  - `curate(namespace: str = "default", focus_slug: str | None = None) -> dict`: Triggers the ADK `wiki_curator` and `cluster_analyst` pipeline on pending episodes.
- **Resources**:
  - `blob://wiki/{namespace}/{slug}` — Raw Markdown + frontmatter of a Wiki page.
  - `blob://clusters/{namespace}` — JSON map of semantic clusters.
  - `blob://graph/{namespace}` — Full node/edge graph snapshot.

### 5.2 "Insider View" REST & SSE Endpoints (`/api/*`)
- `GET /api/graph?namespace=default`: Full graph payload (`nodes` including ghost nodes + 2D coordinates, `edges` with types, `clusters`).
- `GET /api/pages?namespace=default`: List/search wiki pages.
- `GET /api/pages/{slug}?namespace=default`: Get single page + backlinks + open curation suggestions + source episodes.
- `PUT /api/pages/{slug}`: Create/update page from human Markdown edit (automatically re-parses `[[wikilinks]]`, updates ghost nodes, and re-embeds in Firestore).
- `DELETE /api/pages/{slug}`: Delete/archive a wiki page.
- `POST /api/episodes`: Add a memory or note directly from the UI.
- `GET /api/episodes?namespace=default&status=pending_curation`: Inspect the raw episodic inbox.
- `POST /api/curate`: Trigger ADK curation & clustering pass (`wiki_curator` + `cluster_analyst`).
- `POST /api/suggestions/{id}/apply` & `POST /api/suggestions/{id}/dismiss`: 1-click co-curation actions.
- `POST /api/seed`: Populate the store with a rich multi-cluster demo dataset for interactive exploration.
- `GET /api/events`: Server-Sent Events (SSE) stream notifying the frontend of live page edits, graph updates, and agent UI commands (`highlight_nodes`, `navigate_to_page`, `focus_cluster`).

---

## 6. Five-Pillar Design Matrix

To ensure complete end-to-end engineering coverage, the architecture is organized around five core design pillars (detailed in [`spec/architecture-and-deployment.md`](architecture-and-deployment.md)):

### 6.1 Tool & Interface Design
- **Four Serving Surfaces on One FastAPI Process (`blob/fast_api_app.py`)**:
  1. **Universal MCP Surface (`blob/mcp_server.py` at `/mcp` & `stdio`)**: 6 typed tools (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`, `curate`) + 3 `blob://` resources (`wiki`, `clusters`, `graph`).
  2. **ADK Agent Toolsets (`blob/tools/`)**:
     - `memory_tools.py` (13 tools for episode ingestion, hybrid recall, wiki CRUD, link/backlink indexing, cluster recomputation, and curation suggestions).
     - `ui_tools.py` (3 tools: `ui_navigate_to_page`, `ui_highlight_graph_nodes`, `ui_focus_cluster`).
     - All tools return structured dictionaries (`{"status": "ok" | "error", ...}`) with rich docstrings for deterministic LLM schema generation and graceful error recovery.
  3. **Explorer REST & SSE API (`blob/api/explorer_routes.py` at `/api/*`)**: Powers the React graph canvas, Markdown editor, 1-click curation suggestions, contextual chat (`POST /api/chat`), and real-time SSE event stream (`GET /api/events`).
  4. **ADK, A2A & Static UI Surface**: Preserves `/`, `/run_sse`, `/a2a/blob` (A2A v1.0 + v0.3 compat), and `/api/stream_reasoning_engine`, while mounting the compiled React SPA (`frontend/dist`) at `/insider`.

### 6.2 Context & Memory
- **Two-Tier Memory Architecture**:
  1. **Short-Term Session & Artifact State (`blob/app_utils/services.py`)**: Process-wide `shared://session` (`VertexAiSessionService` on Agent Runtime, `InMemorySessionService` locally) and `shared://artifact` (`GcsArtifactService` when `LOGS_BUCKET_NAME` is set, else `InMemoryArtifactService`) shared across ADK Web, A2A, Reasoning Engine, and `/api/chat`.
  2. **Long-Term Knowledge Fabric (`blob/storage/`)**:
     - **Episodic Store (`episodes`)**: Raw interaction notes embedded immediately via `GenAIEmbedder` (`output_dimensionality=768`, `GOOGLE_CLOUD_EMBEDDING_LOCATION=us-east1`, fail-fast in production; `DeterministicHashEmbedder` restricted strictly to unit tests via `BLOB_EMBEDDING_BACKEND=hash`).
     - **Semantic Wiki & Graph (`wiki_pages`)**: Markdown + YAML frontmatter, parsed `[[Wiki Links]]`, automatic **Ghost Nodes** (`status="ghost"`), bidirectional `backlinks`, and typed `relations`.
     - **Semantic Clusters (`clusters`) & Co-Curation Queue (`curation_suggestions`)**.
- **Active Viewport Context Injection**: Every turn sent via `POST /api/chat` injects `view_context` (`active_page_slug`, `selected_cluster_id`, `visible_neighbors`, `namespace`) into `session.state` and the prompt context so `blob` has live situational awareness of what the human is inspecting.
- **Namespace Scoping & Provenance**: Shared `namespace="default"` by default (with custom namespace isolation) and full provenance (`episode_id`, `source_agent`, `interaction_id`, `timestamp`) on every synthesized page.

### 6.3 Orchestration & Logic
- **`AgentTool` Coordinator Pattern (`blob/agent.py`)**:
  - `root_agent` (`name="blob"`, `model="gemini-3.8-flash"`) acts as the stateful coordinator and wraps `wiki_curator` and `cluster_analyst` using `google.adk.tools.AgentTool`.
  - **Strategic model routing** (`blob/app_utils/model_router.py`): `gemini-3.8-flash` for low-latency, user-facing and simple agents (`blob`, `assistant`, `cluster_analyst`); `gemini-4-argon` for `wiki_curator`'s multi-episode synthesis and contradiction resolution. Overridable via `BLOB_FAST_MODEL` / `BLOB_COMPLEX_MODEL`.
  - Using `AgentTool` (rather than full turn transfer via `sub_agents`) ensures `blob` retains turn control after sub-agent synthesis/clustering so it can immediately invoke UI tools (`ui_highlight_graph_nodes`, `ui_navigate_to_page`, `ui_focus_cluster`) and summarize changes in a single turn.
- **Two-Stage Async Curation Pipeline**:
  - **Stage 1 (Sync `<200ms`)**: `remember` embeds and writes `Episode(status="pending_curation")` and emits an `episode_created` SSE event.
  - **Stage 2 (Async / On-Demand)**: `run_curation_pipeline(namespace, focus_slug)` runs `wiki_curator` to synthesize episodes into linked Markdown pages and materialize ghost nodes, then triggers `cluster_analyst` to recompute 2D cluster coordinates and summaries, emitting a `graph_updated` SSE event.
- **Dual UI Action Delivery**: `ui_*` tools publish `UIActionEvent` payloads simultaneously to the SSE `EventBus` (`GET /api/events`) and the turn-scoped action list returned in `POST /api/chat`.

### 6.4 Observability & Tracing
- **Cloud Trace (OpenTelemetry)**:
  - Enabled via `get_fast_api_app(..., otel_to_cloud=otel_to_cloud)` in `blob/fast_api_app.py` and gated on `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY` in Agent Runtime.
  - Captures ADK span hierarchy (`invoke_workflow` $\rightarrow$ `invoke_agent` $\rightarrow$ `call_llm` / `generate_content` & `execute_tool`) with `gen_ai.agent.name="blob"`, supplemented by custom spans for MCP tool calls, 768-d embedding requests, and `KnowledgeStore` curation passes.
- **Prompt-Response Logging & Privacy Controls (`telemetry.tf` & `service.tf`)**:
  - Full GenAI completions are exported as NDJSON to GCS (`gs://{project_id}-blob-logs/completions`) via `OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload` and surfaced in BigQuery (`blob_telemetry.completions` external table + `blob_telemetry.completions_view`).
  - Trace spans keep message bodies off (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT`, `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`) to prevent PII/payload bloat in Cloud Trace.
- **PII Redaction (Model Armor + Sensitive Data Protection)**:
  - `blob/app_utils/guardrails.py` registers ADK's `ModelArmorPlugin` on every `App` when `BLOB_MODEL_ARMOR_TEMPLATE` is set; it screens prompts, responses, and tool outputs, de-identifies PII to info-type tokens, blocks prompt injection, and fails closed.
  - `deployment/terraform/single-project/model_armor.tf` provisions the SDP inspect/de-identify templates (info types in `var.pii_info_types`) and the Model Armor template, with `log_sanitize_operations` auditing.
- **Structured Logging & Continuous Evaluation**:
  - Cloud Logging sink (`genai_logs_to_bq`) routes inference logs to partitioned BigQuery table `aiplatform_googleapis_com_reasoning_engine_stdout`.
  - Pre-deployment quality gates run `agents-cli eval run` (`custom_response_quality` LLM-as-judge + `agent_turn_count` in `tests/eval/eval_config.yaml`).

### 6.5 Infrastructure & Single-Project Deployment
- **Declarative Single-Project Terraform (`deployment/terraform/single-project/`)**:
  - Provisions required APIs (`apis.tf` including `firestore.googleapis.com`), IAM roles (`iam.tf` & `variables.tf` granting `roles/datastore.user` to `vertex_sa` and `AGENT_IDENTITY`), Cloud Firestore `(default)` database + 768-dim composite vector indexes (`firestore.tf`), Vertex AI Agent Runtime (`service.tf`), and GCS/BigQuery telemetry pipeline (`storage.tf`, `telemetry.tf`).
- **Multi-Stage Container Build (`Dockerfile`)**:
  - Stage 1 (`node:22-slim`) compiles `frontend/` into `frontend/dist`; Stage 2 (`python:3.12-slim` + `uv sync --frozen`) packages `blob/`, `assistant/`, and `frontend/dist` into a unified image serving port `8080`.
- **Single-Project Deployment Workflow (`agents-cli`)**:
  - Verified locally with `agents-cli lint`, `uv run pytest tests/unit tests/integration`, and `agents-cli eval run`, then provisioned via `agents-cli infra single-project --apply` and deployed to Vertex AI Agent Runtime via `agents-cli deploy`.
