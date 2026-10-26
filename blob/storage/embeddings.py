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

"""768-dimensional embedding engine, cosine similarity, and 2D cluster layout."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any, Protocol, runtime_checkable

import numpy as np
from google import genai
from google.genai import types
from opentelemetry import trace

from blob.storage.markdown_parser import slugify, title_from_slug
from blob.storage.models import Cluster, WikiPage, utc_now_iso

EMBEDDING_DIMENSION = 768

CLUSTER_COLORS = (
    "#6366f1",  # Indigo
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#06b6d4",  # Cyan
    "#8b5cf6",  # Violet
)

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "all",
        "any",
        "our",
        "use",
        "used",
        "using",
        "via",
        "how",
        "why",
        "what",
        "when",
        "where",
        "who",
    }
)

tracer = trace.get_tracer(__name__)


@runtime_checkable
class Embedder(Protocol):
    """Protocol for 768-d text embedding backends."""

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string into a 768-dimensional float vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings into 768-dimensional float vectors."""
        ...


def _l2_normalize(vec: list[float] | np.ndarray) -> list[float]:
    arr = np.asarray(vec, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm > 1e-12:
        arr = arr / norm
    return [round(float(x), 6) for x in arr.tolist()]


class GenAIEmbedder:
    """Production 768-d embedder powered by Google GenAI (`gemini-embedding-001`).

    Fail-fast: raises RuntimeError if credentials are missing or the API call fails.
    Never silently falls back to hash embeddings.
    """

    def __init__(
        self,
        model: str | None = None,
        location: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.environ.get(
            "BLOB_EMBEDDING_MODEL", "gemini-embedding-001"
        )
        self.location = location or os.environ.get(
            "GOOGLE_CLOUD_EMBEDDING_LOCATION", "us-east1"
        )
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in (
            "true",
            "1",
        )
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "GCP_PROJECT"
        )

        try:
            if api_key and not use_vertex:
                self._client = genai.Client(api_key=api_key)
            elif project:
                self._client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=self.location,
                )
            else:
                raise RuntimeError(
                    "GenAIEmbedder requires either GOOGLE_CLOUD_PROJECT (for Vertex AI "
                    f"in location '{self.location}') or GOOGLE_API_KEY / GEMINI_API_KEY. "
                    "For unit tests without credentials, explicitly set "
                    "BLOB_EMBEDDING_BACKEND=hash."
                )
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(
                f"Failed to initialize google.genai.Client for model '{self.model}' "
                f"in location '{self.location}': {exc}"
            ) from exc

        return self._client

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string into a 768-dimensional vector."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts using `google.genai` with output_dimensionality=768."""
        if not texts:
            return []

        cleaned_texts = [(t or "").strip() or " " for t in texts]
        with tracer.start_as_current_span("blob.embed") as span:
            span.set_attribute("blob.embed.model", self.model)
            span.set_attribute("blob.embed.dimension", EMBEDDING_DIMENSION)
            span.set_attribute("blob.embed.location", self.location)
            span.set_attribute("blob.embed.batch_size", len(cleaned_texts))

            try:
                client = self._get_client()
                response = client.models.embed_content(
                    model=self.model,
                    contents=cleaned_texts,
                    config=types.EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIMENSION,
                    ),
                )
                embeddings = getattr(response, "embeddings", None)
                if not embeddings or len(embeddings) != len(cleaned_texts):
                    raise RuntimeError(
                        f"GenAI embed_content returned invalid embeddings payload "
                        f"for model '{self.model}'."
                    )

                vectors: list[list[float]] = []
                for emb in embeddings:
                    values = list(getattr(emb, "values", None) or [])
                    if len(values) != EMBEDDING_DIMENSION:
                        raise RuntimeError(
                            f"Expected {EMBEDDING_DIMENSION}-d embedding from "
                            f"'{self.model}', got {len(values)} dimensions."
                        )
                    vectors.append(_l2_normalize(values))
                return vectors
            except Exception as exc:
                span.record_exception(exc)
                if isinstance(exc, RuntimeError):
                    raise
                raise RuntimeError(
                    f"GenAI embedding call failed for model '{self.model}' "
                    f"in location '{self.location}': {exc}"
                ) from exc


class DeterministicHashEmbedder:
    """Test-only 768-d deterministic feature-hashing embedder.

    Uses word unigrams, word bigrams, and character n-grams hashed into a 768-d
    vector space so texts sharing domain terms exhibit meaningful cosine similarity.
    Strictly opt-in via `BLOB_EMBEDDING_BACKEND=hash` or explicit fixture injection.
    """

    model = "deterministic-hash-768"

    def embed_text(self, text: str) -> list[float]:
        """Deterministically embed a single text into a 768-d unit vector."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Deterministically embed a batch of texts into 768-d unit vectors."""
        if not texts:
            return []

        with tracer.start_as_current_span("blob.embed") as span:
            span.set_attribute("blob.embed.model", self.model)
            span.set_attribute("blob.embed.dimension", EMBEDDING_DIMENSION)
            span.set_attribute("blob.embed.batch_size", len(texts))

            return [self._hash_single(t) for t in texts]

    def _hash_single(self, text: str) -> list[float]:
        vec = np.zeros(EMBEDDING_DIMENSION, dtype=np.float64)
        normalized = (text or "").lower().strip()
        tokens = [tok for tok in _TOKEN_RE.findall(normalized) if tok not in _STOPWORDS]

        if not tokens:
            tokens = [normalized or "empty"]

        features: list[tuple[str, float]] = []
        # Word unigrams (highest weight) + prefix stems
        for tok in tokens:
            features.append((f"w:{tok}", 2.5))
            if len(tok) >= 4:
                features.append((f"stem4:{tok[:4]}", 1.2))
            if len(tok) >= 5:
                features.append((f"stem5:{tok[:5]}", 1.4))
            # Character 3-grams within words
            for idx in range(max(0, len(tok) - 2)):
                features.append((f"c3:{tok[idx : idx + 3]}", 0.35))

        # Word bigrams
        for idx in range(len(tokens) - 1):
            features.append((f"bg:{tokens[idx]}_{tokens[idx + 1]}", 1.8))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=16).digest()
            idx1 = int.from_bytes(digest[0:4], "little") % EMBEDDING_DIMENSION
            sign1 = 1.0 if (digest[4] & 1) == 0 else -1.0
            idx2 = int.from_bytes(digest[8:12], "little") % EMBEDDING_DIMENSION
            sign2 = 1.0 if (digest[12] & 1) == 0 else -1.0
            vec[idx1] += sign1 * weight
            vec[idx2] += sign2 * (weight * 0.5)

        return _l2_normalize(vec)


_custom_embedder: Embedder | None = None


def set_embedder(embedder: Embedder | None) -> None:
    """Explicitly override or reset the process-wide embedder (for tests)."""
    global _custom_embedder
    _custom_embedder = embedder


def get_embedder() -> Embedder:
    """Return the configured Embedder instance.

    Defaults to `GenAIEmbedder` (fail-fast in production).
    Returns `DeterministicHashEmbedder` ONLY when `BLOB_EMBEDDING_BACKEND=hash`
    or when explicitly injected via `set_embedder(...)`.
    """
    if _custom_embedder is not None:
        return _custom_embedder

    backend = os.environ.get("BLOB_EMBEDDING_BACKEND", "genai").strip().lower()
    if backend == "hash":
        return DeterministicHashEmbedder()
    return GenAIEmbedder()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors in [-1.0, 1.0]."""
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    sim = float(np.dot(va, vb) / (norm_a * norm_b))
    return max(-1.0, min(1.0, sim))


def _derive_cluster_title_and_summary(
    member_pages: list[WikiPage], index: int
) -> tuple[str, str]:
    """Generate a readable cluster title and summary from member pages' tags and titles."""
    tag_counts: dict[str, int] = {}
    for page in member_pages:
        for tag in page.tags:
            t_clean = tag.strip().lower()
            if t_clean:
                tag_counts[t_clean] = tag_counts.get(t_clean, 0) + 1

    sorted_tags = [
        t for t, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    if len(sorted_tags) >= 2:
        title = f"{title_from_slug(sorted_tags[0])} & {title_from_slug(sorted_tags[1])}"
    elif len(sorted_tags) == 1:
        title = f"{title_from_slug(sorted_tags[0])} Knowledge"
    elif member_pages:
        title = member_pages[0].title
    else:
        title = f"Knowledge Cluster {index + 1}"

    titles_preview = ", ".join(p.title for p in member_pages[:4])
    summary = f"Semantic cluster grouping {len(member_pages)} related pages ({titles_preview})."
    return title, summary


def compute_clusters_and_layout(
    pages: list[WikiPage],
    existing_clusters: list[Cluster] | None = None,
    max_clusters: int = 4,
    namespace: str = "default",
) -> tuple[list[Cluster], dict[str, tuple[float, float, str]]]:
    """Group WikiPages into semantic clusters and compute 2D (x, y) layout coordinates.

    Returns:
        Tuple of (clusters, layout_map) where layout_map maps
        `page.slug -> (x, y, cluster_id)`.
    """
    visible_pages = [p for p in pages if p.status != "archived"]
    if not visible_pages:
        return [], {}

    active_pages = [p for p in visible_pages if p.status == "active"]
    ghost_pages = [p for p in visible_pages if p.status == "ghost"]

    # If there are only ghost pages, treat all visible pages as clusterable
    seed_pages = active_pages if active_pages else visible_pages
    num_clusters = min(max(1, max_clusters), len(seed_pages))

    existing_by_id: dict[str, Cluster] = {c.id: c for c in (existing_clusters or [])}

    # Prepare normalized embedding matrix for seed_pages
    fallback_hash = DeterministicHashEmbedder()
    vectors: list[np.ndarray] = []
    for p in seed_pages:
        if p.embedding and len(p.embedding) == EMBEDDING_DIMENSION:
            arr = np.asarray(p.embedding, dtype=np.float64)
        else:
            arr = np.asarray(
                fallback_hash.embed_text(
                    f"{p.title} {' '.join(p.tags)} {p.markdown_body}"
                ),
                dtype=np.float64,
            )
        norm = float(np.linalg.norm(arr))
        if norm > 1e-12:
            arr = arr / norm
        vectors.append(arr)

    mat = np.vstack(vectors)  # shape (N, 768)

    # Deterministic farthest-first initialization for K-means
    centroid_indices: list[int] = [0]
    for _ in range(1, num_clusters):
        sims = mat @ mat[centroid_indices].T  # (N, len(centroid_indices))
        max_sims = np.max(sims, axis=1)
        # Pick the item with minimum similarity to existing centroids
        for idx in centroid_indices:
            max_sims[idx] = 2.0
        next_idx = int(np.argmin(max_sims))
        centroid_indices.append(next_idx)

    centroids = mat[centroid_indices].copy()
    assignments = np.zeros(len(seed_pages), dtype=int)

    for _ in range(12):
        sims = mat @ centroids.T  # (N, K)
        new_assignments = np.argmax(sims, axis=1)
        if np.array_equal(new_assignments, assignments) and _ > 0:
            break
        assignments = new_assignments
        for k in range(num_clusters):
            member_mask = assignments == k
            if np.any(member_mask):
                mean_vec = np.mean(mat[member_mask], axis=0)
                norm = float(np.linalg.norm(mean_vec))
                if norm > 1e-12:
                    centroids[k] = mean_vec / norm

    # Group pages by cluster index
    grouped_pages: dict[int, list[WikiPage]] = {k: [] for k in range(num_clusters)}
    for idx, page in enumerate(seed_pages):
        grouped_pages[int(assignments[idx])].append(page)

    # Remove any empty buckets
    non_empty_groups = [grp for grp in grouped_pages.values() if grp]

    clusters: list[Cluster] = []
    layout_map: dict[str, tuple[float, float, str]] = {}
    used_cluster_ids: set[str] = set()

    total_k = len(non_empty_groups)
    for k_idx, member_pages in enumerate(non_empty_groups):
        # Place cluster centroid on a circle of radius 0.48 (or 0.0 if only 1 cluster)
        angle = (2.0 * math.pi * k_idx) / max(1, total_k)
        radius = 0.0 if total_k == 1 else 0.48
        cx = round(radius * math.cos(angle), 4)
        cy = round(radius * math.sin(angle), 4)

        # Check if member pages share a known existing cluster_id
        matched_existing: Cluster | None = None
        candidate_counts: dict[str, int] = {}
        for mp in member_pages:
            if mp.cluster_id and mp.cluster_id in existing_by_id:
                candidate_counts[mp.cluster_id] = (
                    candidate_counts.get(mp.cluster_id, 0) + 1
                )
        if candidate_counts:
            best_cid = max(candidate_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if best_cid not in used_cluster_ids:
                matched_existing = existing_by_id[best_cid]

        if matched_existing is not None:
            c_id = matched_existing.id
            c_title = matched_existing.title
            c_summary = matched_existing.summary
            c_color = matched_existing.color
        else:
            c_title, c_summary = _derive_cluster_title_and_summary(member_pages, k_idx)
            base_id = f"cluster-{slugify(c_title)}"
            c_id = (
                base_id if base_id not in used_cluster_ids else f"{base_id}-{k_idx + 1}"
            )
            c_color = CLUSTER_COLORS[k_idx % len(CLUSTER_COLORS)]

        used_cluster_ids.add(c_id)

        # Position member pages around the cluster centroid
        m_count = len(member_pages)
        member_slugs: list[str] = []
        for m_idx, mp in enumerate(member_pages):
            member_slugs.append(mp.slug)
            if m_count == 1:
                px, py = cx, cy
            else:
                sub_angle = angle + (2.0 * math.pi * m_idx) / m_count
                sub_radius = 0.18
                px = round(cx + sub_radius * math.cos(sub_angle), 4)
                py = round(cy + sub_radius * math.sin(sub_angle), 4)
            layout_map[mp.slug] = (px, py, c_id)

        clusters.append(
            Cluster(
                id=c_id,
                namespace=namespace,
                title=c_title,
                summary=c_summary,
                color=c_color,
                page_slugs=member_slugs,
                centroid_x=cx,
                centroid_y=cy,
                updated_at=utc_now_iso(),
            )
        )

    # Assign ghost pages near the active page that links to them (or first cluster)
    cluster_by_id = {c.id: c for c in clusters}
    for g_idx, g_page in enumerate(ghost_pages):
        if g_page.slug in layout_map:
            continue
        anchor_slug = g_page.backlinks[0] if g_page.backlinks else None
        if anchor_slug and anchor_slug in layout_map:
            ax, ay, a_cid = layout_map[anchor_slug]
        else:
            first_c = clusters[0]
            ax, ay, a_cid = first_c.centroid_x, first_c.centroid_y, first_c.id

        g_angle = (2.0 * math.pi * (g_idx + 1)) / max(3, len(ghost_pages) + 2)
        gx = round(ax + 0.14 * math.cos(g_angle), 4)
        gy = round(ay + 0.14 * math.sin(g_angle), 4)
        layout_map[g_page.slug] = (gx, gy, a_cid)
        if (
            a_cid in cluster_by_id
            and g_page.slug not in cluster_by_id[a_cid].page_slugs
        ):
            cluster_by_id[a_cid].page_slugs.append(g_page.slug)

    return clusters, layout_map
