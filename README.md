# Blob

> **Blob is a memory fabric agent organizing the knowledge and memories of past interactions in a visual way.**

Modern AI agents accumulate context, preferences, facts, and episodic memories across interactions—yet to the user, what an agent actually "knows" is usually an opaque black box. **Blob** bridges the gap between agent knowledge and human understanding, turning raw agent memories into a living, interconnected, visual knowledge base that both agents and humans can navigate and curate together.

---

## ✨ Core Concepts

- **📖 LLM-Wiki Synthesis**: Instead of storing disconnected chat logs or raw vector chunks, Blob synthesizes memories into structured, readable, Markdown-first wiki pages with rich metadata and provenance.
- **🕸️ Obsidian-Style Knowledge Graph**: Concepts, entities, projects, and episodic memories are explicitly linked (`[[wikilinks]]`, typed edges, backlinks) so relationships across interactions emerge naturally.
- **🧭 High-Level Semantic Clustering**: Memories are automatically grouped into semantic neighborhoods and topic clusters, allowing users to zoom out to the big picture or drill down into specific details.
- **🌱 Agentic Curation**: The Blob ADK agent continuously gardens the knowledge base—deduplicating facts, resolving contradictions, merging related notes, summarizing stale threads, and maintaining link hygiene.
- **🔌 Universal MCP Memory Layer**: Any external agent can connect to Blob via the **Model Context Protocol (MCP)** to store new interaction memories, query synthesized knowledge, or traverse the memory graph.
- **🔍 Interactive "Insider View" UI**: A dynamic wiki and graph explorer with the Blob agent in the loop. Users can visually inspect what their agents know, ask Blob why a memory exists, directly edit wiki nodes, or instruct Blob to reorganize and prune knowledge.

---

## 🏗️ High-Level Architecture

```
┌──────────────────────┐       ┌───────────────────────────────────────────────┐
│   External Agents    │       │              Human User ("Insider View")      │
│ (IDEs, Assistants,   │       │  • Visual Knowledge Graph & Cluster Map       │
│  Custom Workflows)   │       │  • Dynamic Wiki Reader / Editor               │
└──────────┬───────────┘       │  • Agent-in-the-Loop Co-Curation Chat         │
           │                   └───────────────────────┬───────────────────────┘
           │ MCP (Tools & Resources)                   │ Web / A2A / FastAPI
           ▼                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                                 Blob Service                                 │
│  ┌─────────────────────────────┐          ┌───────────────────────────────┐  │
│  │      MCP Memory Server      │          │     Blob ADK Curator Agent    │  │
│  │  • remember / ingest        │◄────────►│  • Wiki synthesis & gardening │  │
│  │  • recall / semantic search │          │  • Link & cluster discovery   │  │
│  │  • graph traversal tools    │          │  • Interactive user Q&A/edits │  │
│  └──────────────┬──────────────┘          └───────────────┬───────────────┘  │
└─────────────────┼─────────────────────────────────────────┼──────────────────┘
                  ▼                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Cloud Knowledge Base (Hybrid)                         │
│  • Markdown-first Wiki Documents (frontmatter, [[wikilinks]], provenance)    │
│  • Graph Index (nodes, backlinks, typed edges) & Vector Embeddings           │
│  • Raw Episodic / Interaction Logs                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

📄 **Specification Draft**: See [`spec/README.md`](spec/README.md) for the evolving architecture and design specification.

---

## 📁 Project Structure

```text
blob/
├── app/                       # Core ADK agent, MCP server, storage & FastAPI backend
│   ├── agent.py               # Blob root_agent, wiki_curator, cluster_analyst & curation pipeline
│   ├── fast_api_app.py        # Unified FastAPI server (ADK, A2A, /mcp, /api/*, /insider)
│   ├── mcp_server.py          # Universal FastMCP server (/mcp & stdio)
│   ├── api/                   # Explorer REST & SSE endpoints (/api/*)
│   ├── storage/               # KnowledgeStore (Firestore & InMemory), parser, 768-d embeddings & seed
│   ├── tools/                 # 13 ADK memory tools & 3 bidirectional UI tools
│   └── app_utils/             # Shared session/artifact services, A2A & Reasoning Engine adapters
├── frontend/                  # Vite + React + TypeScript "Insider View" UI (Graph, Wiki, Sidebar)
├── spec/                      # Architecture, deployment & implementation specifications
│   ├── README.md              # Architecture & design specification
│   ├── architecture-and-deployment.md # Sequence flows, ER diagrams & GCP topology
│   └── implementation-plan.md # 6-phase implementation plan & verification status
├── tests/                     # Unit, integration, and evaluation suites
├── deployment/                # Single-project Terraform infrastructure (Agent Runtime + Firestore)
├── Dockerfile                 # Multi-stage build (Node 22 frontend + Python 3.12 backend)
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies and tooling config
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites

- **uv**: Python package manager — [Install](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js (v22+)**: For building the `frontend/` Insider View SPA
- **agents-cli**: Google Agents CLI — Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services — [Install](https://cloud.google.com/sdk/docs/install)

### Setup & Run

1. Configure your local environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY
   ```

2. Install dependencies:
   ```bash
   agents-cli install
   ```

3. Launch the interactive ADK Dev UI playground:
   ```bash
   BLOB_AUTO_SEED=true agents-cli playground
   ```

4. Or launch the full unified server (serving **ADK Dev UI**, **Insider View** at `/insider`, **Explorer API** at `/api/*`, and **MCP** at `/mcp`):
   ```bash
   BLOB_AUTO_SEED=true uv run uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8000
   # Open http://127.0.0.1:8000/insider for the 2D Force Graph + Wiki + Co-Curation UI
   ```

---

## 🛠️ Development Commands

| Command | Description |
| --- | --- |
| `agents-cli install` | Install dependencies using `uv` |
| `agents-cli playground` | Launch local development environment (auto-reloads on save) |
| `agents-cli lint` | Run code quality checks (`ruff`, `ty`, `codespell`) |
| `agents-cli eval` | Evaluate agent behavior (`run`, `generate`, `grade`, `analyze`, `compare`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli deploy` | Deploy agent to Agent Runtime |
| `agents-cli publish gemini` | Register deployed agent with Gemini |

### Deployment Configuration

Before running Terraform or deploying to GCP, copy the example Terraform variables file and set your project ID:

```bash
cp deployment/terraform/single-project/vars/env.tfvars.example \
   deployment/terraform/single-project/vars/env.tfvars
```

---

## 🔭 Observability & Interoperability

- **Observability**: Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.
- **A2A Protocol**: Supports the [A2A Protocol](https://a2a-protocol.org/) for multi-agent interoperability (testable via [A2A Inspector](https://github.com/a2aproject/a2a-inspector)).
