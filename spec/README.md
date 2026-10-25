# Blob — Design Specification (Draft)

> **Status:** Early Draft / Living Document
> **Mission:** *"Blob is a memory fabric agent organizing the knowledge and memories of past interactions in a visual way."*

---

## 1. Problem Statement & Vision

As users rely on AI agents across more workflows, those agents accumulate knowledge: user preferences, project architectures, past decisions, domain facts, and episodic interaction history. Today, this memory layer suffers from three major gaps:

1. **Opacity to the User**: Users cannot easily see, audit, or understand what an agent actually "knows" or believes to be true.
2. **Fragmentation**: Memories are often stored as flat vector chunks or isolated key-value strings lacking structure, hierarchy, and cross-references.
3. **Lack of Collaborative Curation**: When an agent learns something outdated or noisy, users lack an intuitive interface to explore the context and co-curate the knowledge with the agent.

**Blob** solves this by acting as a **visual memory fabric** between agents and humans:
- For **external agents**, Blob exposes a unified **MCP (Model Context Protocol)** server to ingest interactions and retrieve structured, high-signal knowledge.
- For **humans**, Blob provides an **"Insider View"**—an interactive, Obsidian-inspired knowledge graph and LLM-synthesized wiki where the user and the Blob agent explore, question, and curate memories together.

---

## 2. Core Pillars

### 2.1 LLM-Wiki Style Writeups
Raw interaction snippets and facts are synthesized into living, human-readable **Wiki Pages** (Markdown documents with structured YAML frontmatter):
- Each page represents a coherent concept, entity, project, preference, or episodic summary.
- Pages maintain **provenance** (which agent interaction or user edit contributed the information, and when).
- Writeups favor clarity, synthesis, and high signal-to-noise over raw transcript dumps.

### 2.2 Obsidian-Like Knowledge Graph
Knowledge is explicitly interconnected:
- **Wikilinks (`[[Page Name]]`)**: Inline semantic links between wiki pages.
- **Typed Edges & Backlinks**: Bidirectional relationships (e.g., `relates_to`, `part_of`, `decided_in`, `contradicts`, `derived_from`).
- **Orphan & Hub Detection**: Surfacing isolated memories that need linking or central hub concepts that anchor a domain.

### 2.3 High-Level Semantic Clustering
Beyond explicit links, Blob computes embeddings across wiki pages and memory fragments to form **semantic clusters**:
- Provides a bird's-eye "map" of what the agent knows (e.g., clusters for *Work Projects*, *Coding Preferences*, *Travel Plans*, *Team Context*).
- Enables multi-resolution exploration: zoom from high-level topic continents down to individual wiki notes and source interactions.

### 2.4 Agentic Curation ("Memory Gardening")
The Blob ADK agent actively tends the knowledge base, operating both on-ingest and during background curation passes:
- **Synthesis & Merging**: Consolidating repetitive episodic facts into canonical wiki articles.
- **Conflict Resolution**: Detecting when new information supersedes or contradicts older knowledge (archiving outdated claims while keeping history).
- **Link & Cluster Hygiene**: Suggesting or creating missing `[[wikilinks]]`, splitting overly broad pages, and summarizing emerging clusters.

### 2.5 Interactive "Insider View" (Human + Agent in the Loop)
The web interface gives the user transparent access to the memory fabric:
- **Dynamic Wiki & Graph Explorer**: Browse articles, inspect backlinks, and navigate the 2D/3D force-directed graph and semantic cluster map.
- **Agent-in-the-Loop Exploration**: As the user browses a node or cluster, the Blob agent is aware of their current view—answering questions like *"Where did you learn this?"*, *"What else relates to Project X?"*, or *"Summarize everything you know about our deployment setup."*
- **Interactive Co-Curation**: Users can directly edit Markdown pages or instruct Blob in natural language to merge, refactor, pin, or forget specific memories.

---

## 3. System Architecture

### 3.1 Component Overview

1. **MCP Memory Interface (External Agent Facing)**
   - Exposes MCP **Tools** and **Resources** so any MCP-compatible client (IDE agents, CLI assistants, custom pipelines) can read and write to Blob.
   - Proposed core tools:
     - `memory_ingest` / `remember`: Record a new interaction, observation, or fact.
     - `memory_query` / `recall`: Hybrid search (semantic + graph neighborhood + keyword) returning synthesized wiki context.
     - `memory_get_page`: Read a specific wiki page and its immediate graph links.
     - `memory_list_clusters`: Retrieve the high-level map of known domains/topics.

2. **Blob ADK Agent (Curator & Interactive Guide)**
   - Built with Google ADK (`app/agent.py`).
   - **Curator Role**: Processes incoming memory events from the MCP queue/log, updates or creates Markdown wiki pages, maintains `[[wikilinks]]`, and refreshes cluster summaries.
   - **Guide Role**: Powers the conversational assistant inside the "Insider View" UI, grounded in the user's currently active wiki page / graph selection.

3. **Hybrid Cloud Knowledge Base**
   - **Document Store (Markdown-First)**: Cloud-persisted Markdown files (e.g., GCS / Firestore document blobs) containing YAML frontmatter (`id`, `title`, `tags`, `cluster_id`, `updated_at`, `sources`) and Markdown body with `[[wikilinks]]`.
   - **Graph & Metadata Index**: Tracks nodes, explicit edges, backlinks, and provenance for fast graph queries and UI rendering.
   - **Vector & Clustering Index**: Stores embeddings for semantic search and periodic cluster calculation (e.g., UMAP/HDBSCAN or hierarchical LLM clustering).

4. **"Insider View" Frontend & API**
   - FastAPI backend (`app/fast_api_app.py`) serving REST/SSE/WebSocket endpoints for the graph, wiki CRUD, and ADK/A2A agent streaming.
   - Web UI combining a Graph/Cluster canvas, a Markdown Wiki viewer/editor, and a contextual chat sidebar with Blob.

---

## 4. Data Model Sketch (Draft)

### Wiki Node (`*.md`)
```markdown
---
id: "mem-node-python-tooling"
title: "Python Tooling Preferences"
cluster: "engineering-workflow"
tags: ["python", "tooling", "preferences"]
confidence: 0.95
sources:
  - interaction_id: "evt-2026-10-25-001"
    agent: "coding-assistant"
    timestamp: "2026-10-25T18:00:00Z"
updated_at: "2026-10-25T18:10:00Z"
---

# Python Tooling Preferences

The user standardizes on `uv` for Python dependency management and virtual environments across all projects, including [[Blob Architecture]].

## Key Conventions
- Always run Python scripts via `uv run python ...`.
- Linting and type-checking use `ruff` and `ty` (configured in `pyproject.toml`).
- Related to [[Google ADK Development Workflow]].
```

---

## 5. Open Questions & Next Steps (To Be Defined)

- [ ] **Ingestion Pipeline**: Should `memory_ingest` update the wiki synchronously, or write to an episodic inbox that the Blob Curator Agent processes asynchronously?
- [ ] **Storage Backend Selection**: Exact GCP storage pairing for the Markdown vault + graph/vector index (e.g., GCS + Firestore/Cloud SQL pgvector vs. Vertex AI / BigQuery).
- [ ] **Clustering Algorithm**: Balance between embedding-based spatial clustering (for 2D visual maps) and LLM-generated hierarchical topic taxonomies.
- [ ] **Frontend Stack**: Choice of web framework and graph visualization library (e.g., React/Next.js or Vite + Cytoscape.js / D3 / Sigma.js) for the "Insider View".
- [ ] **Multi-Tenancy & Scoping**: Namespace isolation per user, per project, or shared team memory spaces.
