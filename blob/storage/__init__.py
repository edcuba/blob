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

"""Storage engine, Markdown parser, 768-d embeddings, and seed data for Blob."""

from blob.storage.base import (
    EventBus,
    KnowledgeStore,
    get_event_bus,
    get_knowledge_store,
    set_knowledge_store,
)
from blob.storage.embeddings import (
    EMBEDDING_DIMENSION,
    DeterministicHashEmbedder,
    Embedder,
    GenAIEmbedder,
    compute_clusters_and_layout,
    cosine_similarity,
    get_embedder,
    set_embedder,
)
from blob.storage.firestore_store import FirestoreKnowledgeStore
from blob.storage.markdown_parser import (
    extract_summary,
    extract_wikilinks,
    parse_wiki_markdown,
    serialize_wiki_page,
    slugify,
    title_from_slug,
)
from blob.storage.memory_store import InMemoryKnowledgeStore
from blob.storage.models import (
    VALID_RELATION_TYPES,
    Cluster,
    CurationSuggestion,
    Episode,
    EpisodeSource,
    GraphEdge,
    GraphNode,
    GraphRelation,
    GraphSnapshot,
    UIActionEvent,
    WikiPage,
    utc_now_iso,
)
from blob.storage.seed import seed_knowledge_store

__all__ = [
    "EMBEDDING_DIMENSION",
    "VALID_RELATION_TYPES",
    "Cluster",
    "CurationSuggestion",
    "DeterministicHashEmbedder",
    "Embedder",
    "Episode",
    "EpisodeSource",
    "EventBus",
    "FirestoreKnowledgeStore",
    "GenAIEmbedder",
    "GraphEdge",
    "GraphNode",
    "GraphRelation",
    "GraphSnapshot",
    "InMemoryKnowledgeStore",
    "KnowledgeStore",
    "UIActionEvent",
    "WikiPage",
    "compute_clusters_and_layout",
    "cosine_similarity",
    "extract_summary",
    "extract_wikilinks",
    "get_embedder",
    "get_event_bus",
    "get_knowledge_store",
    "parse_wiki_markdown",
    "seed_knowledge_store",
    "serialize_wiki_page",
    "set_embedder",
    "set_knowledge_store",
    "slugify",
    "title_from_slug",
    "utc_now_iso",
]
