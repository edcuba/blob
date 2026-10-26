# Blob — Detailed Implementation Plan

> **Status:** Implemented & Verified
> **Companion to:** [`spec/README.md`](README.md) and [`spec/architecture-and-deployment.md`](architecture-and-deployment.md)

This plan translates the architecture in [`spec/README.md`](README.md) and [`spec/architecture-and-deployment.md`](architecture-and-deployment.md) into sequential, testable phases covering all five core engineering pillars.

> [!IMPORTANT]
> **Code Preservation & Operational Rules**
> - Preserve `root_agent.name = "blob"` and `MODEL = "gemini-3.8-flash"` in [`app/agent.py`](../app/agent.py) so `agents-cli` telemetry and [`agents-cli-manifest.yaml`](../agents-cli-manifest.yaml) stay in sync.
> - Keep existing ADK (`/`, `/run_sse`), A2A (`/a2a/app`), and Reasoning Engine (`/api/reasoning_engine`, `/api/stream_reasoning_engine`) routes in [`app/fast_api_app.py`](../app/fast_api_app.py) intact while mounting `/mcp`, `/api/*`, and `/insider`.
> - **Fail-Fast Embeddings in Production**: `app/storage/embeddings.py` raises an explicit error if the GenAI embedder (`output_dimensionality=768`, `GOOGLE_CLOUD_EMBEDDING_LOCATION=us-east1`) is missing or fails in production/runtime. The deterministic 768-dim hash embedder is strictly opt-in for unit tests (`BLOB_EMBEDDING_BACKEND=hash` or explicit fixture injection).

---

## Five-Pillar Design Coverage

| Pillar | Architectural Design & Implementation Coverage |
| :--- | :--- |
| **1. Tool & Interface Design** | • **MCP Surface (`app/mcp_server.py` at `/mcp` & `stdio`)**: 6 typed tools (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`, `curate`) and 3 `blob://` resources (`wiki`, `clusters`, `graph`).<br>• **ADK Memory Tools (`app/tools/memory_tools.py`)**: 13 idempotent tools with structured `{"status": "ok"\|"error", ...}` payloads and detailed docstrings.<br>• **ADK UI Tools (`app/tools/ui_tools.py`)**: `ui_navigate_to_page`, `ui_highlight_graph_nodes`, `ui_focus_cluster`.<br>• **Explorer REST & SSE (`app/api/explorer_routes.py` at `/api/*`)**: Graph/Wiki CRUD, episodic inbox, 1-click suggestions, `/api/chat`, and `/api/events` SSE.<br>• **ADK / A2A / SPA (`app/fast_api_app.py`)**: Native ADK Web (`/`), A2A v1.0 + v0.3 compat (`/a2a/app`), Reasoning Engine proxy, and React SPA (`/insider`). |
| **2. Context & Memory** | • **Short-Term Session & Artifact State (`app/app_utils/services.py`)**: Shared `shared://session` (`VertexAiSessionService` on Agent Runtime, `InMemorySessionService` locally) and `shared://artifact` (`GcsArtifactService` / `InMemoryArtifactService`).<br>• **Long-Term Knowledge Fabric (`app/storage/`)**: `KnowledgeStore` protocol with `FirestoreKnowledgeStore` and `InMemoryKnowledgeStore` toggled via `BLOB_STORAGE_BACKEND` (`memory` \| `firestore` \| `auto`).<br>• **Active Viewport Context Injection**: `POST /api/chat` stores `view_context` (`active_page_slug`, `selected_cluster_id`, `visible_neighbors`, `namespace`) in `session.state` and injects it into each turn.<br>• **Scoping & Provenance**: Shared `namespace="default"` (or custom namespace) with episode-level provenance (`episode_id`, `source_agent`, `interaction_id`, `timestamp`). |
| **3. Orchestration & Logic** | • **`AgentTool` Coordinator Pattern (`app/agent.py`)**: `root_agent` (`"blob"`) wraps `wiki_curator` and `cluster_analyst` via `google.adk.tools.AgentTool` so `blob` retains turn control after sub-agent execution to invoke UI tools (`ui_highlight_graph_nodes`, etc.).<br>• **Two-Stage Async Curation**: Fast synchronous ingest (`<200ms` to `episodes` with 768-d vector) decoupled from background/on-demand `run_curation_pipeline(namespace, focus_slug)` (`wiki_curator` $\rightarrow$ `cluster_analyst`).<br>• **Dual UI Action Bus**: `ui_*` tools publish `UIActionEvent` objects to both `GET /api/events` (SSE) and the `POST /api/chat` response payload. |
| **4. Observability & Tracing** | • **Cloud Trace (OpenTelemetry)**: Wired via `get_fast_api_app(otel_to_cloud=otel_to_cloud)` in `fast_api_app.py` (`gen_ai.agent.name="blob"`), plus custom OTel spans on MCP tools (`mcp.tool.*`), embedding calls (`blob.embed`), and store curation (`blob.store.*`).<br>• **Prompt-Response Logging (`telemetry.tf` & `service.tf`)**: Full completions uploaded to `gs://{project_id}-blob-logs/completions` (`OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`) and joined in BigQuery (`blob_telemetry.completions_view`), while trace spans enforce `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT` and `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`.<br>• **Structured Logging & Eval**: Cloud Logging sink `genai_logs_to_bq` exports to BigQuery; `agents-cli eval run` grades behavior via `tests/eval/eval_config.yaml`. |
| **5. Infrastructure & Deployment** | • **Single-Project Terraform (`deployment/terraform/single-project/`)**: Enables `firestore.googleapis.com` (`apis.tf`), grants `roles/datastore.user` to `vertex_sa` and `AGENT_IDENTITY` (`variables.tf`, `iam.tf`), and provisions Cloud Firestore `(default)` + 768-d composite vector indexes (`firestore.tf`) alongside Vertex AI Agent Runtime (`service.tf`) and BigQuery/GCS telemetry (`telemetry.tf`, `storage.tf`).<br>• **Multi-Stage `Dockerfile`**: Compiles `frontend/` (`node:22-slim`) and packages `app/` + `frontend/dist` (`python:3.12-slim`).<br>• **Single-Project Agent Runtime Workflow**: Verified via `agents-cli lint`, `uv run pytest tests/unit tests/integration`, and `agents-cli eval run`, provisioned via `agents-cli infra single-project --apply`, and deployed via `agents-cli deploy`. |

---

## Phase 1: Storage Engine, Markdown Parser & Seed Data (`app/storage/`)

Build the data layer using Firestore (with Native Vector Search, `dimension=768`) as the single cloud source of truth and an `InMemoryKnowledgeStore` for local development and automated tests.

### Files to Create / Modify
- **[`pyproject.toml`](../pyproject.toml)** *(Applied)*:
  - Added `mcp>=1.6.0,<2.0.0`, `google-cloud-firestore>=2.19.0,<3.0.0`, `pyyaml>=6.0.2,<7.0.0`, `numpy>=2.0.0,<3.0.0` and configured `packages = ["app"]`.
- **`app/storage/models.py`**:
  - Pydantic models for `Episode`, `WikiPage`, `GraphRelation`, `GraphNode`, `GraphEdge`, `Cluster`, `CurationSuggestion`, and `UIActionEvent`.
- **`app/storage/markdown_parser.py`**:
  - Parse and serialize YAML frontmatter + Markdown body on the fly.
  - Extract inline Obsidian-style `[[Page Name]]` and `[[slug|Display Name]]` links, normalize slugs, and merge with frontmatter `relations`.
- **`app/storage/embeddings.py`**:
  - Production `GenAIEmbedder` using `google-genai` (defaulting to `gemini-embedding-001`, configurable via `BLOB_EMBEDDING_MODEL`) with explicit `output_dimensionality=768`, `GOOGLE_CLOUD_EMBEDDING_LOCATION` (defaulting to `us-east1`), and OpenTelemetry span attributes (`blob.embed.model`, `blob.embed.dimension=768`). Raises an explicit error if credentials or embedding calls fail in production/runtime (no silent fallback).
  - Test-only `DeterministicHashEmbedder` (768-dim) used **only** when explicitly injected in unit tests or when `BLOB_EMBEDDING_BACKEND=hash` is explicitly set.
  - Lightweight cosine-similarity clustering + 2D projection helper (`compute_clusters_and_layout`) for grouping page vectors into semantic clusters and computing `(x, y)` coordinates.
- **`app/storage/base.py`**:
  - Abstract `KnowledgeStore` protocol, `EventBus` for SSE/UI events, and `get_knowledge_store()` singleton factory controlled by `BLOB_STORAGE_BACKEND` (`memory` | `firestore` | `auto`).
- **`app/storage/memory_store.py`**:
  - `InMemoryKnowledgeStore` implementation with in-memory cosine similarity search and full graph/ghost-node management. Starts empty by default (populates seed data via `POST /api/seed` or when `BLOB_AUTO_SEED=true`). Resolves `[[Wiki Links]]` against existing pages by slug or case-insensitive `title` before creating ghost nodes, and restricts primary `recall()` matches to `status="active"` pages while surfacing connected active and ghost nodes in 1-hop `neighbors`.
- **`app/storage/firestore_store.py`**:
  - `FirestoreKnowledgeStore` using `google-cloud-firestore` (`Vector` + `find_nearest`) as the single source of truth for `episodes`, `wiki_pages`, `clusters`, and `curation_suggestions`.
- **`app/storage/seed.py`**:
  - Rich multi-cluster seed dataset (*System Architecture*, *Developer Preferences*, *Project Roadmap*, *Agent Workflows* with interconnected `[[wikilinks]]`, ghost nodes, and pending episodes).

---

## Phase 2: ADK Agent Hierarchy & Bidirectional UI Tools (`app/`)

Upgrade [`app/agent.py`](../app/agent.py) into the **Blob** multi-agent memory system while preserving `MODEL = "gemini-3.8-flash"` and `name="blob"`.

### Files to Create / Modify
- **`app/tools/memory_tools.py`**:
  - 13 shared ADK tools (`remember_episode`, `recall_knowledge`, `get_wiki_page`, `upsert_wiki_page`, `delete_wiki_page`, `list_pending_episodes`, `mark_episodes_synthesized`, `get_graph_neighborhood`, `list_semantic_clusters`, `recompute_semantic_clusters`, `update_cluster_metadata`, `create_curation_suggestion`, `resolve_curation_suggestion`) with OpenTelemetry span attributes and structured return payloads.
- **`app/tools/ui_tools.py`**:
  - Bidirectional **Agent-in-the-Loop** tools (`ui_navigate_to_page`, `ui_highlight_graph_nodes`, `ui_focus_cluster`) emitting `UIActionEvent` payloads to both the SSE `EventBus` (`GET /api/events`) and the active turn's action collector (`POST /api/chat`).
- **[`app/agent.py`](../app/agent.py)**:
  - `wiki_curator` (`Agent`): Synthesizes pending episodes into structured Markdown Wiki pages with `[[wikilinks]]`, resolves contradictions, turns ghost nodes into full articles, and creates curation suggestions.
  - `cluster_analyst` (`Agent`): Runs embedding clustering and generates human-readable cluster titles, summaries, colors, and Map-of-Content (`MOC`) pages.
  - `root_agent` (`name="blob"`): Primary interactive guide and co-curator wrapping `wiki_curator` and `cluster_analyst` via `AgentTool(agent=...)` and exposing `run_curation_pipeline(namespace, focus_slug)` for background/API curation runs.

---

## Phase 3: Universal MCP Server, Observability Spans & Explorer API (`app/`)

Expose the MCP interface for external agents and the REST + SSE API for the "Insider View" frontend.

### Files to Create / Modify
- **`app/mcp_server.py`**:
  - Built with `mcp.server.fastmcp.FastMCP("blob-memory")` with OpenTelemetry tracing spans on tool invocations.
  - **MCP Tools**: `remember` (triggers background curation when `auto_curate=True`), `recall`, `get_page`, `traverse_graph`, `list_clusters`, `curate` (awaits `run_curation_pipeline` synchronously).
  - **MCP Resources**: `blob://wiki/{namespace}/{slug}`, `blob://clusters/{namespace}`, `blob://graph/{namespace}`.
  - Includes `__main__` entrypoint for `stdio` transport (`uv run python -m app.mcp_server`) and mounts onto FastAPI at `/mcp`.
- **`app/api/explorer_routes.py`**:
  - FastAPI router mounted at `/api` (`GET /api/graph`, `GET/PUT/DELETE /api/pages/{slug}`, `GET/POST /api/episodes`, `POST /api/curate` [awaits `run_curation_pipeline` synchronously], `POST /api/suggestions/{id}/apply|dismiss`, `POST /api/seed`, `POST /api/chat`, `GET /api/events`).
- **[`app/fast_api_app.py`](../app/fast_api_app.py)**:
  - Attach `explorer_routes` (`/api`), mount the MCP server (`/mcp`), and serve the compiled `frontend/dist` SPA at `/insider` while preserving all existing ADK (`/`, `/run_sse`), A2A (`/a2a/app`), Reasoning Engine (`/api/reasoning_engine`, `/api/stream_reasoning_engine`), and Cloud Trace (`otel_to_cloud`) configurations.

---

## Phase 4: "Insider View" React + TypeScript Frontend (`frontend/`)

Build the visual exploration and co-curation workspace in `frontend/` (`frontend/src` compiled via Vite `npm run build` into `frontend/dist`) and serve it at `/insider`.

### Components to Create
- **`frontend/` (Vite + React + TypeScript + Tailwind/Lucide)**:
  - **`GraphCanvas.tsx`**: 2D force-directed graph rendering semantic cluster hulls/halos, active Wiki nodes, dashed **Ghost Nodes**, directional/typed edges, search/filtering, and animated pulsing highlights triggered by `blob`.
  - **`WikiPane.tsx`**: Markdown reader/live editor with clickable `[[Wiki Links]]` (1-click synthesis on ghost links), YAML metadata tags, **Backlinks** panel, **Provenance / Source Episodes** drawer, and **1-Click Curation Suggestions** banner.
  - **`AgentSidebar.tsx`**: Live active-context badge (`active_page_slug`, `selected_cluster_id`), quick action chips, streaming chat with `blob`, and automatic execution of UI actions from `POST /api/chat` and `GET /api/events`.
- **[`Dockerfile`](../Dockerfile)**:
  - Multi-stage build (`FROM node:22-slim AS frontend-build` $\rightarrow$ `FROM python:3.12-slim`) compiling `./frontend` into `frontend/dist` inside Docker.

---

## Phase 5: Single-Project Terraform Infrastructure (`deployment/terraform/single-project/`)

Update the single-project Terraform configuration to provision Firestore and required IAM permissions alongside the existing Vertex AI Agent Runtime and BigQuery/GCS telemetry stack.

### Files to Modify / Create
- **[`deployment/terraform/single-project/apis.tf`](../deployment/terraform/single-project/apis.tf)**:
  - Add `"firestore.googleapis.com"` to `local.services`.
- **[`deployment/terraform/single-project/variables.tf`](../deployment/terraform/single-project/variables.tf)**:
  - Append `"roles/datastore.user"` to `app_sa_roles` and `agent_identity_roles` (preserving the order of the first six roles in `agent_identity_roles`).
- **`deployment/terraform/single-project/firestore.tf`**:
  - Provision the Firestore `(default)` database (`FIRESTORE_NATIVE`) and `google_firestore_index` composite vector indexes (`dimension = 768`) for `wiki_pages` and `episodes`.

---

## Phase 6: Unit Tests, Integration Tests & Evaluation Dataset (`tests/`)

Verify all components and update the evaluation suite for the new memory fabric behavior.

### Files to Modify / Create
- **`tests/unit/test_storage_and_parser.py`**:
  - Test `[[wikilink]]` parsing, ghost node creation, backlink resolution, frontmatter serialization, `InMemoryKnowledgeStore` CRUD, hybrid recall, clustering, and verify that `GenAIEmbedder` raises on missing credentials rather than silently falling back (while unit tests explicitly inject `DeterministicHashEmbedder`).
- **`tests/unit/test_mcp_and_tools.py`**:
  - Test MCP tools (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`) and ADK agent tools.
- **[`tests/integration/test_agent.py`](../tests/integration/test_agent.py) & [`tests/integration/test_server_e2e.py`](../tests/integration/test_server_e2e.py)**:
  - Test the `blob` ADK agent and FastAPI `/api/*` + `/mcp` endpoints end-to-end.
- **[`tests/eval/datasets/basic-dataset.json`](../tests/eval/datasets/basic-dataset.json)** & **[`tests/eval/eval_config.yaml`](../tests/eval/eval_config.yaml)**:
  - Update eval scenarios to test memory ingestion, recall, wiki synthesis, and provenance explanation (`custom_response_quality` and `memory_tool_trajectory`).

---

## Verification Summary

| Quality Gate | Command | Result |
| :--- | :--- | :--- |
| **Lint, Format, Spelling & Type Check** | `agents-cli lint` (`ruff check`, `ruff format --check`, `codespell`, `ty check`) | **Passed** (0 errors) |
| **Unit Test Suite** | `uv run pytest tests/unit` (`test_storage_and_parser.py`, `test_mcp_and_tools.py`) | **Passed** (`16 passed`) |
| **Integration & E2E Server Suite** | `uv run pytest tests/integration` (`test_agent.py`, `test_server_e2e.py`) | **Passed** |
| **Frontend Vite Build** | `cd frontend && npm run build` | **Passed** (`frontend/dist` compiled for `/insider`) |
| **Agent Evaluation (`agents-cli eval run`)** | `BLOB_AUTO_SEED=true agents-cli eval run` (4 cases in `basic-dataset.json`) | **Passed** (`custom_response_quality`: **5.0000 / 5.0**, `memory_tool_trajectory`: **1.0000 / 1.0**) |
