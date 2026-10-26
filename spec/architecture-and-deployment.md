# Blob — Detailed System Architecture & GCP Deployment Plan

> **Companion to:** [`spec/README.md`](README.md)
> **Scope:** End-to-end runtime topology, sequence flows (MCP ingestion, agentic curation, bidirectional UI loop), data & state diagrams, and GCP Terraform/deployment architecture.

---

## 1. End-to-End Runtime Topology

Blob runs as a unified Python FastAPI application (`app/fast_api_app.py`) exposing **four distinct serving surfaces** over a shared ADK `Runner` and a pluggable `KnowledgeStore` backend:

1. **Universal MCP Server (`/mcp` HTTP/SSE & `stdio`)**: Connects external agents (IDE assistants, CLI tools, custom workflows) to the shared memory fabric.
2. **Explorer REST & SSE API (`/api/*`)**: Powers the visual graph canvas, Markdown wiki CRUD, 1-click curation suggestions, and real-time UI event streaming.
3. **ADK & A2A Agent Endpoints (`/run_sse`, `/a2a/app`, `/api/reasoning_engine`)**: Serves the conversational `blob` agent and multi-agent A2A protocol.
4. **"Insider View" Static SPA (`/`)**: Serves the compiled React + TypeScript (Vite) frontend bundle (`frontend/dist`).

```mermaid
flowchart TB
    subgraph Consumers["1. External Consumers & Clients"]
        ExtMCP["External Agents (IDEs, CLIs, Workflows)"]
        HumanUI["Human User ('Insider View' React SPA)"]
        A2ACaller["Gemini Platform / A2A Clients"]
    end

    subgraph FastAPI["2. Unified FastAPI Server (app/fast_api_app.py)"]
        MCPEndpoint["/mcp (FastMCP Streamable HTTP/SSE & stdio)"]
        ExplorerREST["/api/pages, /api/graph, /api/episodes, /api/curate"]
        EventStream["/api/events (SSE Real-Time Event Bus)"]
        ADKEndpoint["/run_sse, /a2a/app, /api/stream_reasoning_engine"]
        StaticAssets["/ (Compiled React/Vite Bundle)"]
    end

    subgraph ADKHierarchy["3. Google ADK Agent Hierarchy (app/agent.py)"]
        RootBlob["root_agent ('blob' - gemini-3.8-flash)"]
        SubCurator["wiki_curator (Synthesis & Link Hygiene)"]
        SubCluster["cluster_analyst (Vector Clustering & MOCs)"]
        MemTools["Shared Memory Toolset (app/tools/memory_tools.py)"]
        UITools["UI Action Toolset (app/tools/ui_tools.py)"]

        RootBlob -->|"Delegates synthesis"| SubCurator
        RootBlob -->|"Delegates clustering"| SubCluster
        RootBlob --> MemTools
        RootBlob --> UITools
        SubCurator --> MemTools
        SubCluster --> MemTools
    end

    subgraph StorageEngine["4. Storage & Graph Engine (app/storage/)"]
        Parser["Markdown & [[Wikilink]] Parser"]
        Embedder["Embedding & 2D Projection Engine (google-genai)"]
        StoreProto["KnowledgeStore Protocol (app/storage/base.py)"]
        FirestoreImpl[("FirestoreKnowledgeStore (Cloud Single Source of Truth)")]
        MemoryImpl[("InMemoryKnowledgeStore (Local Dev / CI / Seed)")]

        MemTools --> StoreProto
        StoreProto --> Parser
        StoreProto --> Embedder
        StoreProto --> FirestoreImpl
        StoreProto -.->|"Fallback / Tests"| MemoryImpl
    end

    ExtMCP <-->|"MCP Tools & blob:// Resources"| MCPEndpoint
    HumanUI <-->|"REST CRUD"| ExplorerREST
    EventStream -->|"SSE Live Graph/Wiki & UI Actions"| HumanUI
    HumanUI <-->|"Chat + Active View Context"| ADKEndpoint
    HumanUI -->|"Loads SPA"| StaticAssets
    A2ACaller <-->|"A2A JSON-RPC / ADK Stream"| ADKEndpoint

    MCPEndpoint --> StoreProto
    MCPEndpoint -.->|"Async Curation Trigger"| SubCurator
    ExplorerREST --> StoreProto
    ExplorerREST -.->|"Manual Curation Trigger"| SubCurator
    ADKEndpoint --> RootBlob
    UITools -.->|"Emits UIActionEvent"| EventStream
    StoreProto -.->|"Emits DataChangeEvent"| EventStream
```

---

## 2. Detailed Sequence Flows

### 2.1 Two-Stage Memory Ingestion & Agentic Curation Flow

When an external agent stores a memory via MCP, Blob separates **fast ingestion** from **agentic synthesis** so calling agents never block on multi-step LLM curation:

- **Stage 1 (Synchronous, `<200ms`)**: Embeds the raw observation and writes an `Episode` (`status="pending_curation"`) to Firestore. Because `episodes` has a vector index, the memory is immediately retrievable via `recall()`.
- **Stage 2 (Asynchronous Background Pass)**: `wiki_curator` synthesizes pending episodes into Markdown `WikiPage` documents, parses inline `[[Wiki Links]]`, creates **Ghost Nodes** for referenced-but-unwritten pages, recalculates bidirectional backlinks, and triggers `cluster_analyst` to update semantic clusters.

```mermaid
sequenceDiagram
    autonumber
    actor ExtAgent as External Agent (MCP Client)
    participant MCP as FastMCP Server (/mcp)
    participant Store as KnowledgeStore (Firestore)
    participant Embed as GenAI Embeddings
    participant Curator as ADK wiki_curator
    participant Cluster as ADK cluster_analyst
    participant SSE as SSE Event Bus (/api/events)
    actor UI as Insider View UI

    rect rgb(235, 245, 255)
        Note over ExtAgent,Embed: Stage 1: Fast Episodic Ingest (<200ms)
        ExtAgent->>MCP: tool: remember(content, source_agent, tags, namespace)
        MCP->>Embed: embed_text(content)
        Embed-->>MCP: Vector[768]
        MCP->>Store: create_episode(status="pending_curation", embedding)
        Store-->>MCP: Episode(id="ep-001")
        MCP->>SSE: publish("episode_created", {id: "ep-001"})
        SSE-->>UI: Live Inbox Badge (+1 pending episode)
        MCP-->>ExtAgent: {status: "stored", episode_id: "ep-001"}
    end

    rect rgb(240, 255, 240)
        Note over MCP,UI: Stage 2: Asynchronous Agentic Curation & Clustering
        MCP-)Curator: trigger background curation (namespace)
        Curator->>Store: list_pending_episodes(namespace)
        Store-->>Curator: [Episode("ep-001")]
        Curator->>Store: recall_knowledge(query, top_k=5)
        Store-->>Curator: Related WikiPages + Graph Neighbors
        Curator->>Store: upsert_wiki_page(slug, title, markdown_with_wikilinks, sources)
        Note right of Store: 1. Parses YAML & [[Wiki Links]]<br/>2. Upserts Ghost Nodes for new [[links]]<br/>3. Updates bidirectional backlinks<br/>4. Embeds page via GenAI
        Curator->>Store: mark_episodes_synthesized(["ep-001"], target_slug)
        Curator->>Cluster: delegate cluster refresh
        Cluster->>Store: recompute_semantic_clusters(namespace)
        Note right of Store: Groups page vectors + computes 2D (x, y) coords
        Cluster->>Store: update_cluster_metadata(id, title, summary, color)
        Store->>SSE: publish("graph_updated", {updated_slugs, clusters})
        SSE-->>UI: Live Graph & Wiki Refresh
    end
```

---

### 2.2 Hybrid Recall Flow (External Agent Query)

When an external agent calls `recall(query)`, Blob combines **vector similarity across Wiki pages**, **1-hop graph neighborhood expansion**, and **recent unmerged episodes**:

```mermaid
sequenceDiagram
    autonumber
    actor ExtAgent as External Agent (MCP Client)
    participant MCP as FastMCP Server (/mcp)
    participant Store as KnowledgeStore (Firestore)
    participant Embed as GenAI Embeddings

    ExtAgent->>MCP: tool: recall(query, namespace="default", top_k=5)
    MCP->>Embed: embed_text(query)
    Embed-->>MCP: query_vector[768]
    par Vector Search on Wiki Pages
        MCP->>Store: find_nearest_wiki_pages(query_vector, top_k=5)
        Store-->>MCP: Top-K Active WikiPages
    and Vector Search on Pending Episodes
        MCP->>Store: find_nearest_episodes(query_vector, status="pending_curation", top_k=3)
        Store-->>MCP: Matching Unmerged Episodes
    end
    MCP->>Store: expand_1hop_neighbors(matched_page_slugs)
    Store-->>MCP: Linked Neighbor Summaries & Cluster Context
    MCP-->>ExtAgent: Synthesized Markdown Pages + 1-Hop Graph Links + Pending Episodes
```

---

### 2.3 Bidirectional "Agent-in-the-Loop" UI Exploration Flow

In the **Insider View**, the human user and the `blob` ADK agent share a live feedback loop:
1. **UI $\rightarrow$ Agent Context**: Every user message automatically attaches the current view state (`active_page_slug`, `selected_cluster_id`, `visible_neighbors`).
2. **Agent $\rightarrow$ UI Control**: `blob` can invoke UI action tools (`ui_highlight_graph_nodes`, `ui_navigate_to_page`, `ui_focus_cluster`) and memory mutation tools (`upsert_wiki_page`), which stream over `/api/events` to animate the React graph and update the Markdown editor in real time.

```mermaid
sequenceDiagram
    autonumber
    actor User as Human User
    participant GraphUI as React Graph & Wiki UI
    participant API as FastAPI (/api/chat & /api/events)
    participant Blob as ADK root_agent ("blob")
    participant Store as KnowledgeStore (Firestore)

    User->>GraphUI: Clicks node [[Blob Storage Architecture]]
    GraphUI->>API: GET /api/pages/blob-storage-architecture
    API->>Store: get_page("blob-storage-architecture")
    Store-->>GraphUI: Markdown + Frontmatter + Backlinks + Provenance + Suggestions

    User->>GraphUI: Asks in Sidebar: "What else connects to this and why?"
    GraphUI->>API: POST /api/chat {message, view_context: {active_page: "blob-storage-architecture", cluster: "cluster-arch"}}
    API->>Blob: Runner.run_async(message + injected view_context)
    Blob->>Store: get_graph_neighborhood("blob-storage-architecture", depth=2)
    Store-->>Blob: Connected nodes, ghost nodes, & episode provenance
    Blob->>API: tool: ui_highlight_graph_nodes(["mcp-memory-interface", "firestore-vector-index"], reason="Direct architectural dependencies")
    API-->>GraphUI: SSE Event: {type: "ui_highlight_nodes", slugs: [...]}
    Note over GraphUI: Graph canvas zooms & pulses highlighted nodes
    Blob-->>API: Streamed Markdown explanation with provenance citations
    API-->>GraphUI: Render assistant response in Sidebar
```

---

## 3. Data Model & Knowledge Lifecycle

### 3.1 Firestore Entity-Relationship Diagram

All persistent state lives in **four Firestore collections** (`episodes`, `wiki_pages`, `clusters`, `curation_suggestions`) scoped by `namespace` (defaulting to `"default"`):

```mermaid
erDiagram
    CLUSTER ||--o{ WIKI_PAGE : "groups (cluster_id)"
    WIKI_PAGE ||--o{ WIKI_PAGE : "links to (out_links / backlinks / relations)"
    EPISODE }o--o{ WIKI_PAGE : "synthesized into (sources)"
    WIKI_PAGE ||--o{ CURATION_SUGGESTION : "has pending (target_slug)"
    EPISODE }o--o{ CURATION_SUGGESTION : "triggers (episode_ids)"

    EPISODE {
        string id PK
        string namespace
        string content
        string source_agent
        string interaction_id
        string_array tags
        string status "pending_curation | synthesized | archived"
        string_array synthesized_into
        vector_768 embedding
        timestamp created_at
    }

    WIKI_PAGE {
        string slug PK
        string namespace
        string title
        string status "active | ghost | archived"
        string markdown_body
        string cluster_id FK
        string_array tags
        string_array out_links "Parsed from [[wikilinks]]"
        string_array backlinks "Computed reverse index"
        json_array relations "Typed edges (part_of, depends_on, etc.)"
        json_array sources "Provenance (episode_id, source_agent, timestamp)"
        float x "2D layout coordinate"
        float y "2D layout coordinate"
        vector_768 embedding
        timestamp updated_at
    }

    CLUSTER {
        string id PK
        string namespace
        string title
        string summary
        string color
        string_array page_slugs
        float centroid_x
        float centroid_y
        timestamp updated_at
    }

    CURATION_SUGGESTION {
        string id PK
        string namespace
        string target_slug FK
        string kind "unmerged_episodes | contradiction | expand_ghost"
        string title
        string description
        string_array episode_ids
        string status "open | applied | dismissed"
        timestamp created_at
    }
```

### 3.2 Wiki Node & Episode State Machine

```mermaid
stateDiagram-v2
    [*] --> EpisodePending: MCP remember() or UI Note
    EpisodePending: Episode (pending_curation)
    EpisodeSynthesized: Episode (synthesized)

    state "WikiPage Lifecycle" as WikiLifecycle {
        GhostNode: Ghost Node (status = "ghost")
        ActivePage: Active Wiki Page (status = "active")
        FlaggedPage: Active Page + Open CurationSuggestion
        ArchivedPage: Archived Page (status = "archived")

        [*] --> GhostNode: Referenced via [[Wiki Link]] in another page
        GhostNode --> ActivePage: Synthesized by wiki_curator or Human edit
        ActivePage --> ActivePage: Updated by Agent or Human co-curation
        ActivePage --> FlaggedPage: New related Episode or conflict detected
        FlaggedPage --> ActivePage: 1-Click Suggestion Applied / Dismissed
        ActivePage --> ArchivedPage: Pruned / Merged into another page
    }

    EpisodePending --> ActivePage: wiki_curator synthesizes Markdown & links
    EpisodePending --> EpisodeSynthesized: Provenance recorded in WikiPage.sources
```

---

## 4. GCP Infrastructure & Deployment Architecture

### 4.1 Terraform Resource Topology (`deployment/terraform/single-project/`)

All GCP resources are managed declaratively in `deployment/terraform/single-project/`:

```mermaid
flowchart TB
    subgraph GCPProject["GCP Project (var.project_id)"]
        subgraph APIs["Enabled APIs (apis.tf)"]
            API_AI["aiplatform.googleapis.com"]
            API_FS["firestore.googleapis.com (New)"]
            API_BQ["bigquery.googleapis.com"]
            API_Run["run.googleapis.com"]
            API_Log["logging & cloudtrace.googleapis.com"]
        end

        subgraph Identity["IAM & Identities (iam.tf & variables.tf)"]
            AgentID["Agent Runtime Effective Identity\n(AGENT_IDENTITY)"]
            VertexSA["Vertex AI Service Agent\n(vertex_sa)"]
        end

        subgraph Compute["Compute Runtime (service.tf)"]
            ReasoningEngine["Vertex AI Agent Runtime\n(google_vertex_ai_reasoning_engine.app)\nRuns Dockerfile on port 8080"]
        end

        subgraph Database["Knowledge Store (firestore.tf - New)"]
            FirestoreDB[("Cloud Firestore (default)\nFIRESTORE_NATIVE")]
            IdxWiki["Vector Index: wiki_pages\n(namespace + embedding[768])"]
            IdxEp["Vector Index: episodes\n(namespace + status + embedding[768])"]
            FirestoreDB --- IdxWiki
            FirestoreDB --- IdxEp
        end

        subgraph Telemetry["Observability Pipeline (storage.tf & telemetry.tf)"]
            GCSLogs[("GCS Bucket\n{project_id}-{project_name}-logs")]
            LogSink["Cloud Logging Sink\n(genai_logs_to_bq)"]
            BQDataset[("BigQuery Dataset\nblob_telemetry\n• completions external table\n• completions_view")]
            GCSLogs --> BQDataset
            LogSink --> BQDataset
        end
    end

    ReasoningEngine -->|"Uses identity"| AgentID
    ReasoningEngine -->|"Uses service agent"| VertexSA
    AgentID & VertexSA -->|"roles/datastore.user (New)"| FirestoreDB
    AgentID & VertexSA -->|"roles/aiplatform.user"| API_AI
    AgentID & VertexSA -->|"roles/storage.objectAdmin"| GCSLogs
    ReasoningEngine -->|"OTel Traces & Completions"| GCSLogs
    ReasoningEngine -->|"Structured stdout"| LogSink
```

### 4.2 Planned Terraform Changes (`deployment/terraform/single-project/`)

1. **`apis.tf`**:
   - Add `"firestore.googleapis.com"` to `local.services`.
2. **`variables.tf`**:
   - Add `"roles/datastore.user"` to both `var.app_sa_roles` and `var.agent_identity_roles` so the runtime container can read/write Firestore documents and execute vector similarity queries.
3. **`firestore.tf` (New File)**:
   - `google_firestore_database.default`: Provisions the `(default)` Firestore database in `FIRESTORE_NATIVE` mode in `var.region`.
   - `google_firestore_index.wiki_pages_vector`: Composite vector index on collection `wiki_pages` (`namespace` ASC + `embedding` vector `dimension = 768`, `flat`).
   - `google_firestore_index.episodes_vector`: Composite vector index on collection `episodes` (`namespace` ASC + `status` ASC + `embedding` vector `dimension = 768`, `flat`).

---

### 4.3 Serving Topologies on GCP: Agent Runtime vs. Cloud Run

Because the container (`Dockerfile` running `uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8080`) packages the **ADK Agent**, **A2A Server**, **MCP Server (`/mcp`)**, **Explorer API (`/api/*`)**, and **React UI (`frontend/dist`)** into a single image, it can be deployed in two ways depending on how you want to access the Web UI:

```mermaid
flowchart LR
    subgraph OptionA["Option A: Agent Runtime Only (Current Scaffold Default)"]
        direction TB
        CLI_A["MCP / A2A / ADK Client\n(with GCP IAM Bearer Token)"] -->|"HTTPS + OAuth Header"| AR_Pass["Vertex AI /api Passthrough\n.../reasoningEngines/{id}/api/*"]
        LocalUI_A["Local Browser UI\n(localhost:8000 or Vite)"] -->|"Connects to same Firestore"| FS_A[("Cloud Firestore")]
        AR_Pass --> AR_Container["Agent Runtime Container\n(fast_api_app.py)"]
        AR_Container --> FS_A
    end

    subgraph OptionB["Option B: Cloud Run Target (Direct Browser UI + IAP + MCP)"]
        direction TB
        Browser_B["Human Browser\n('Insider View' UI)"] -->|"HTTPS (Cloud IAP / Auth)"| CRun["Cloud Run Service\nhttps://blob-{hash}.run.app"]
        MCP_B["External MCP / A2A Clients"] -->|"HTTPS /mcp & /a2a/app"| CRun
        CRun --> FS_B[("Cloud Firestore")]
    end
```

- **Option A — Agent Runtime (`deployment_target: "agent_runtime"`, current default)**:
  - Managed Vertex AI Reasoning Engine deployment via `agents-cli deploy`.
  - Exposes all FastAPI routes under `https://{region}-aiplatform.googleapis.com/reasoningEngines/v1/projects/{project}/locations/{region}/reasoningEngines/{id}/api/{route}` (authenticated via Google Cloud IAM Bearer tokens).
  - Ideal for Gemini platform registration (`agents-cli publish gemini`), A2A calls, and IAM-authenticated MCP clients, while the React UI can be run locally (`agents-cli playground` / `uvicorn`) connected to the same Cloud Firestore database or hosted as a decoupled Cloud Run UI.
- **Option B — Cloud Run (`agents-cli scaffold enhance . --deployment-target cloud_run`)**:
  - Deploys the exact same `Dockerfile` to Cloud Run with a direct `https://blob-....run.app` URL.
  - Allows opening the **"Insider View" React UI** directly in any browser (optionally protected with Google sign-in via `--iap`).

---

## 5. Step-by-Step Deployment & Verification Runbook

1. **Local Development & Interactive Testing**:
   ```bash
   # Uses InMemoryKnowledgeStore by default, or Firestore when GOOGLE_CLOUD_PROJECT is set
   agents-cli install
   agents-cli playground
   ```

2. **Pre-Deployment Automated Checks**:
   ```bash
   # Unit & integration test suites
   uv run pytest tests/unit tests/integration

   # Code quality & type checks
   agents-cli lint

   # Agent evaluation suite
   agents-cli eval run
   ```

3. **Provision Single-Project GCP Infrastructure (Terraform)**:
   ```bash
   # Ensure deployment/terraform/single-project/vars/env.tfvars has your project_id
   agents-cli infra single-project --apply
   ```

4. **Deploy to GCP (Requires Explicit Human Approval)**:
   ```bash
   # Deploy container to configured target
   agents-cli deploy
   ```
