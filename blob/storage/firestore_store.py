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

"""Cloud Firestore KnowledgeStore implementation with Native Vector Search."""

from __future__ import annotations

import os
import uuid
from collections import deque
from typing import Any, Literal

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from opentelemetry import trace

from blob.storage.base import KnowledgeStore, get_event_bus
from blob.storage.embeddings import (
    Embedder,
    compute_clusters_and_layout,
    cosine_similarity,
    get_embedder,
)
from blob.storage.markdown_parser import (
    extract_summary,
    parse_wiki_markdown,
    slugify,
    title_from_slug,
)
from blob.storage.memory_store import _keyword_boost
from blob.storage.models import (
    Cluster,
    CurationSuggestion,
    Episode,
    EpisodeSource,
    GraphEdge,
    GraphNode,
    GraphRelation,
    GraphSnapshot,
    WikiPage,
    utc_now_iso,
)

tracer = trace.get_tracer(__name__)


def _vector_to_list(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, Vector):
        return [float(x) for x in raw.to_map_value().get("value", [])]
    if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes, dict)):
        return [float(x) for x in raw]
    return []


class FirestoreKnowledgeStore(KnowledgeStore):
    """Cloud Firestore single-source-of-truth implementation of KnowledgeStore."""

    EPISODES_COLLECTION = "episodes"
    WIKI_PAGES_COLLECTION = "wiki_pages"
    CLUSTERS_COLLECTION = "clusters"
    SUGGESTIONS_COLLECTION = "curation_suggestions"

    def __init__(
        self,
        project_id: str | None = None,
        database: str = "(default)",
        embedder: Embedder | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._project_id = (
            project_id
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("GCP_PROJECT")
        )
        self._database = os.environ.get("FIRESTORE_DATABASE", database)
        self._embedder = embedder
        self._client = client

    @property
    def client(self) -> firestore.Client:
        if self._client is None:
            self._client = firestore.Client(
                project=self._project_id,
                database=self._database,
            )
        return self._client

    @property
    def embedder(self) -> Embedder:
        return self._embedder if self._embedder is not None else get_embedder()

    @staticmethod
    def _doc_key(namespace: str, key: str) -> str:
        return key if namespace == "default" else f"{namespace}__{key}"

    @staticmethod
    def _episode_from_dict(data: dict[str, Any]) -> Episode:
        payload = dict(data)
        payload["embedding"] = _vector_to_list(payload.get("embedding"))
        return Episode.model_validate(payload)

    @staticmethod
    def _page_from_dict(data: dict[str, Any]) -> WikiPage:
        payload = dict(data)
        payload["embedding"] = _vector_to_list(payload.get("embedding"))
        return WikiPage.model_validate(payload)

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def create_episode(
        self,
        content: str,
        source_agent: str = "external",
        tags: list[str] | None = None,
        namespace: str = "default",
        interaction_id: str | None = None,
        episode_id: str | None = None,
    ) -> Episode:
        with tracer.start_as_current_span("blob.store.create_episode") as span:
            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.backend", "firestore")

            ep_id = episode_id or f"ep-{uuid.uuid4().hex[:8]}"
            clean_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
            embed_input = (
                f"{content}\nTags: {', '.join(clean_tags)}" if clean_tags else content
            )
            embedding = self.embedder.embed_text(embed_input)

            episode = Episode(
                id=ep_id,
                namespace=namespace,
                content=content,
                source_agent=source_agent,
                interaction_id=interaction_id,
                tags=clean_tags,
                status="pending_curation",
                synthesized_into=[],
                embedding=embedding,
                created_at=utc_now_iso(),
            )
            doc_data = episode.model_dump()
            if embedding:
                doc_data["embedding"] = Vector(embedding)

            self.client.collection(self.EPISODES_COLLECTION).document(ep_id).set(
                doc_data
            )
            get_event_bus().publish(
                "episode_created",
                {"id": episode.id, "source_agent": source_agent, "tags": clean_tags},
                namespace=namespace,
            )
            return episode

    def get_episode(
        self, episode_id: str, namespace: str = "default"
    ) -> Episode | None:
        snap = (
            self.client.collection(self.EPISODES_COLLECTION).document(episode_id).get()
        )
        if not snap.exists:
            return None
        ep = self._episode_from_dict(snap.to_dict() or {})
        return ep if ep.namespace == namespace else None

    def list_episodes(
        self,
        namespace: str = "default",
        status: str | None = None,
        limit: int = 50,
    ) -> list[Episode]:
        query = self.client.collection(self.EPISODES_COLLECTION).where(
            filter=FieldFilter("namespace", "==", namespace)
        )
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        docs = query.stream()
        episodes = [self._episode_from_dict(d.to_dict() or {}) for d in docs]
        episodes.sort(key=lambda ep: (ep.created_at, ep.id), reverse=True)
        return episodes[: max(1, limit)]

    def mark_episodes_synthesized(
        self,
        episode_ids: list[str],
        target_slug: str,
        namespace: str = "default",
    ) -> list[Episode]:
        norm_slug = slugify(target_slug)
        updated: list[Episode] = []
        col = self.client.collection(self.EPISODES_COLLECTION)
        for ep_id in episode_ids:
            ep = self.get_episode(ep_id, namespace=namespace)
            if ep is None:
                continue
            ep.status = "synthesized"
            if norm_slug not in ep.synthesized_into:
                ep.synthesized_into.append(norm_slug)
            col.document(ep_id).update(
                {
                    "status": "synthesized",
                    "synthesized_into": ep.synthesized_into,
                }
            )
            updated.append(ep)
        return updated

    # ------------------------------------------------------------------
    # Wiki Pages
    # ------------------------------------------------------------------

    def _recompute_backlinks(self, namespace: str) -> None:
        pages = self.list_wiki_pages(namespace=namespace, include_ghosts=True)
        page_map = {p.slug: p for p in pages}
        inbound: dict[str, set[str]] = {slug: set() for slug in page_map}

        for src_slug, page in page_map.items():
            if page.status == "archived":
                continue
            targets = set(page.out_links) | {r.target for r in page.relations}
            for t_slug in targets:
                if t_slug != src_slug and t_slug in inbound:
                    inbound[t_slug].add(src_slug)

        col = self.client.collection(self.WIKI_PAGES_COLLECTION)
        for slug, page in page_map.items():
            new_backlinks = sorted(inbound.get(slug, set()))
            if new_backlinks != page.backlinks:
                page.backlinks = new_backlinks
                col.document(self._doc_key(namespace, slug)).update(
                    {"backlinks": new_backlinks}
                )

    def get_wiki_page(
        self, slug_or_title: str, namespace: str = "default"
    ) -> WikiPage | None:
        col = self.client.collection(self.WIKI_PAGES_COLLECTION)
        for candidate in (slug_or_title, slugify(slug_or_title)):
            snap = col.document(self._doc_key(namespace, candidate)).get()
            if snap.exists:
                return self._page_from_dict(snap.to_dict() or {})

        lower_query = (slug_or_title or "").strip().lower()
        for page in self.list_wiki_pages(namespace=namespace, include_ghosts=True):
            if page.title.lower() == lower_query:
                return page
        return None

    def list_wiki_pages(
        self,
        namespace: str = "default",
        include_ghosts: bool = True,
        status: str | None = None,
        cluster_id: str | None = None,
        query: str | None = None,
    ) -> list[WikiPage]:
        fs_query = self.client.collection(self.WIKI_PAGES_COLLECTION).where(
            filter=FieldFilter("namespace", "==", namespace)
        )
        if status is not None:
            fs_query = fs_query.where(filter=FieldFilter("status", "==", status))

        pages = [self._page_from_dict(d.to_dict() or {}) for d in fs_query.stream()]
        if status is None:
            pages = [p for p in pages if p.status != "archived"]
            if not include_ghosts:
                pages = [p for p in pages if p.status != "ghost"]

        if cluster_id is not None:
            pages = [p for p in pages if p.cluster_id == cluster_id]

        if query:
            q_lower = query.strip().lower()
            pages = [
                p
                for p in pages
                if q_lower in p.title.lower()
                or q_lower in p.slug.lower()
                or q_lower in p.markdown_body.lower()
                or any(q_lower in t.lower() for t in p.tags)
            ]

        pages.sort(key=lambda p: (p.status == "ghost", p.title.lower()))
        return pages

    def _save_wiki_page_doc(self, page: WikiPage) -> None:
        doc_data = page.model_dump()
        if page.embedding:
            doc_data["embedding"] = Vector(page.embedding)
        self.client.collection(self.WIKI_PAGES_COLLECTION).document(
            self._doc_key(page.namespace, page.slug)
        ).set(doc_data)

    def upsert_wiki_page(
        self,
        title: str,
        markdown_body: str,
        slug: str | None = None,
        namespace: str = "default",
        status: Literal["active", "ghost", "archived"] = "active",
        cluster_id: str | None = None,
        tags: list[str] | None = None,
        relations: list[GraphRelation | dict[str, Any]] | None = None,
        sources: list[EpisodeSource | dict[str, Any]] | None = None,
        source_episode_ids: list[str] | None = None,
        source_agent: str = "blob",
        x: float | None = None,
        y: float | None = None,
    ) -> WikiPage:
        with tracer.start_as_current_span("blob.store.upsert_wiki_page") as span:
            parsed = parse_wiki_markdown(
                markdown_body or "",
                fallback_slug=slug,
                fallback_title=title,
                namespace=namespace,
            )
            page_slug = slugify(slug or parsed["slug"] or title)
            page_title = (
                title or parsed["title"] or title_from_slug(page_slug)
            ).strip()
            clean_body = parsed["markdown_body"]

            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.page.slug", page_slug)
            span.set_attribute("blob.backend", "firestore")

            existing = self.get_wiki_page(page_slug, namespace=namespace)

            effective_status: Literal["active", "ghost", "archived"] = status
            if (
                existing is not None
                and existing.status == "ghost"
                and clean_body.strip()
                and status != "archived"
            ):
                effective_status = "active"

            merged_tags: list[str] = []
            for t in [
                *(existing.tags if existing else []),
                *parsed["tags"],
                *(tags or []),
            ]:
                t_clean = str(t).strip()
                if t_clean and t_clean not in merged_tags:
                    merged_tags.append(t_clean)

            merged_relations: list[GraphRelation] = []
            seen_rel: set[tuple[str, str]] = set()
            raw_rel_items: list[GraphRelation | dict[str, Any]] = [
                *parsed["relations"],
                *(relations or []),
            ]
            if not raw_rel_items and existing:
                raw_rel_items = list(existing.relations)

            for item in raw_rel_items:
                if isinstance(item, GraphRelation):
                    r_type, r_target = item.type, slugify(item.target)
                elif isinstance(item, dict) and item.get("target"):
                    r_type = str(item.get("type") or "relates_to")
                    r_target = slugify(str(item["target"]))
                else:
                    continue
                if r_target and r_target != page_slug:
                    key = (r_type, r_target)
                    if key not in seen_rel:
                        seen_rel.add(key)
                        merged_relations.append(
                            GraphRelation(type=r_type, target=r_target)
                        )

            wikilink_titles: dict[str, str] = parsed["wikilink_titles"]
            out_links: list[str] = []
            for candidate in [
                *parsed["out_links"],
                *(r.target for r in merged_relations),
            ]:
                if not candidate:
                    continue
                resolved_target = candidate
                display_title = wikilink_titles.get(
                    candidate, title_from_slug(candidate)
                )
                existing_target = self.get_wiki_page(
                    resolved_target, namespace=namespace
                ) or self.get_wiki_page(display_title, namespace=namespace)
                if existing_target is not None:
                    resolved_target = existing_target.slug
                if resolved_target != page_slug and resolved_target not in out_links:
                    out_links.append(resolved_target)

            merged_sources: list[EpisodeSource] = []
            seen_ep_ids: set[str] = set()
            for src in [
                *(existing.sources if existing else []),
                *parsed["sources"],
                *(sources or []),
            ]:
                if isinstance(src, EpisodeSource):
                    s_obj = src
                elif isinstance(src, dict) and src.get("episode_id"):
                    s_obj = EpisodeSource(
                        episode_id=str(src["episode_id"]),
                        source_agent=str(src.get("source_agent") or source_agent),
                        interaction_id=src.get("interaction_id"),
                        timestamp=str(src.get("timestamp") or utc_now_iso()),
                    )
                else:
                    continue
                if s_obj.episode_id not in seen_ep_ids:
                    seen_ep_ids.add(s_obj.episode_id)
                    merged_sources.append(s_obj)

            if source_episode_ids:
                synthesized_eps = self.mark_episodes_synthesized(
                    source_episode_ids, page_slug, namespace=namespace
                )
                ep_map = {ep.id: ep for ep in synthesized_eps}
                for ep_id in source_episode_ids:
                    if ep_id not in seen_ep_ids:
                        seen_ep_ids.add(ep_id)
                        ep_obj = ep_map.get(ep_id)
                        merged_sources.append(
                            EpisodeSource(
                                episode_id=ep_id,
                                source_agent=(
                                    ep_obj.source_agent if ep_obj else source_agent
                                ),
                                interaction_id=(
                                    ep_obj.interaction_id if ep_obj else None
                                ),
                                timestamp=(
                                    ep_obj.created_at if ep_obj else utc_now_iso()
                                ),
                            )
                        )

            resolved_cluster_id = (
                cluster_id
                or parsed["cluster_id"]
                or (existing.cluster_id if existing else None)
            )
            resolved_x = (
                x if x is not None else (existing.x if existing is not None else 0.0)
            )
            resolved_y = (
                y if y is not None else (existing.y if existing is not None else 0.0)
            )

            embed_text_input = (
                f"{page_title}\nTags: {', '.join(merged_tags)}\n\n{clean_body}"
                if clean_body.strip()
                else page_title
            )
            embedding = self.embedder.embed_text(embed_text_input)

            page = WikiPage(
                slug=page_slug,
                title=page_title,
                namespace=namespace,
                status=effective_status,
                markdown_body=clean_body,
                cluster_id=resolved_cluster_id,
                tags=merged_tags,
                out_links=out_links,
                backlinks=existing.backlinks if existing else [],
                relations=merged_relations,
                sources=merged_sources,
                x=resolved_x,
                y=resolved_y,
                embedding=embedding,
                updated_at=utc_now_iso(),
            )
            self._save_wiki_page_doc(page)

            for idx, target_slug in enumerate(out_links):
                if self.get_wiki_page(target_slug, namespace=namespace) is None:
                    ghost_title = wikilink_titles.get(
                        target_slug, title_from_slug(target_slug)
                    )
                    ghost_embedding = self.embedder.embed_text(ghost_title)
                    offset = 0.12 * ((idx % 4) + 1)
                    ghost_page = WikiPage(
                        slug=target_slug,
                        title=ghost_title,
                        namespace=namespace,
                        status="ghost",
                        markdown_body="",
                        cluster_id=resolved_cluster_id,
                        tags=[],
                        out_links=[],
                        backlinks=[page_slug],
                        relations=[],
                        sources=[],
                        x=round(resolved_x + offset, 4),
                        y=round(resolved_y - offset, 4),
                        embedding=ghost_embedding,
                        updated_at=utc_now_iso(),
                    )
                    self._save_wiki_page_doc(ghost_page)

            self._recompute_backlinks(namespace)
            refreshed = self.get_wiki_page(page_slug, namespace=namespace) or page
            get_event_bus().publish(
                "page_upserted",
                {
                    "slug": refreshed.slug,
                    "title": refreshed.title,
                    "status": refreshed.status,
                    "out_links": refreshed.out_links,
                },
                namespace=namespace,
            )
            return refreshed

    def upsert_wiki_page_from_markdown(
        self,
        raw_markdown: str,
        slug: str | None = None,
        title: str | None = None,
        namespace: str = "default",
        source_agent: str = "human",
    ) -> WikiPage:
        parsed = parse_wiki_markdown(
            raw_markdown,
            fallback_slug=slug,
            fallback_title=title,
            namespace=namespace,
        )
        effective_status: Literal["active", "ghost", "archived"] = (
            "active"
            if parsed["markdown_body"].strip() and parsed["status"] == "ghost"
            else parsed["status"]
        )
        return self.upsert_wiki_page(
            title=title or parsed["title"],
            markdown_body=raw_markdown,
            slug=slug or parsed["slug"],
            namespace=parsed["namespace"],
            status=effective_status,
            cluster_id=parsed["cluster_id"],
            tags=parsed["tags"],
            relations=parsed["relations"],
            sources=parsed["sources"],
            source_agent=source_agent,
        )

    def delete_wiki_page(self, slug: str, namespace: str = "default") -> bool:
        with tracer.start_as_current_span("blob.store.delete_wiki_page") as span:
            existing = self.get_wiki_page(slug, namespace=namespace)
            if existing is None:
                return False

            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.page.slug", existing.slug)
            self.client.collection(self.WIKI_PAGES_COLLECTION).document(
                self._doc_key(namespace, existing.slug)
            ).delete()
            self._recompute_backlinks(namespace)
            get_event_bus().publish(
                "page_deleted", {"slug": existing.slug}, namespace=namespace
            )
            return True

    # ------------------------------------------------------------------
    # Hybrid Recall & Graph Traversal
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        namespace: str = "default",
        top_k: int = 5,
        include_episodes: bool = True,
    ) -> dict[str, Any]:
        with tracer.start_as_current_span("blob.store.recall") as span:
            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.top_k", top_k)
            span.set_attribute("blob.backend", "firestore")

            query_vec = self.embedder.embed_text(query)

            # Query candidate WikiPages via Firestore Native Vector Search (find_nearest)
            pages_col = self.client.collection(self.WIKI_PAGES_COLLECTION).where(
                filter=FieldFilter("namespace", "==", namespace)
            )
            try:
                v_query = pages_col.find_nearest(
                    vector_field="embedding",
                    query_vector=Vector(query_vec),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=max(top_k * 2, 10),
                )
                candidate_pages = [
                    self._page_from_dict(d.to_dict() or {}) for d in v_query.stream()
                ]
            except Exception:
                candidate_pages = self.list_wiki_pages(
                    namespace=namespace, include_ghosts=True
                )

            scored_pages: list[tuple[WikiPage, float]] = []
            for page in candidate_pages:
                if page.status != "active":
                    continue
                vec_sim = cosine_similarity(query_vec, page.embedding)
                kw_boost = _keyword_boost(
                    query,
                    f"{page.title} {' '.join(page.tags)} {page.markdown_body}",
                )
                status_adj = 0.0 if page.status == "active" else -0.15
                scored_pages.append((page, vec_sim + kw_boost + status_adj))

            scored_pages.sort(key=lambda item: item[1], reverse=True)
            top_pages = scored_pages[: max(1, top_k)]
            matched_slugs = {p.slug for p, _ in top_pages}

            # 1-hop graph neighborhood
            neighbor_pages: list[WikiPage] = []
            seen_neighbors: set[str] = set()
            for page, _ in top_pages:
                for linked_slug in [
                    *page.out_links,
                    *page.backlinks,
                    *(r.target for r in page.relations),
                ]:
                    if (
                        linked_slug not in matched_slugs
                        and linked_slug not in seen_neighbors
                    ):
                        n_page = self.get_wiki_page(linked_slug, namespace=namespace)
                        if n_page is not None and n_page.status != "archived":
                            seen_neighbors.add(linked_slug)
                            neighbor_pages.append(n_page)

            matched_episodes: list[tuple[Episode, float]] = []
            if include_episodes:
                ep_col = (
                    self.client.collection(self.EPISODES_COLLECTION)
                    .where(filter=FieldFilter("namespace", "==", namespace))
                    .where(filter=FieldFilter("status", "==", "pending_curation"))
                )
                try:
                    ep_vquery = ep_col.find_nearest(
                        vector_field="embedding",
                        query_vector=Vector(query_vec),
                        distance_measure=DistanceMeasure.COSINE,
                        limit=max(1, min(top_k, 5)),
                    )
                    candidate_eps = [
                        self._episode_from_dict(d.to_dict() or {})
                        for d in ep_vquery.stream()
                    ]
                except Exception:
                    candidate_eps = self.list_episodes(
                        namespace=namespace, status="pending_curation"
                    )

                for ep in candidate_eps:
                    vec_sim = cosine_similarity(query_vec, ep.embedding)
                    kw_boost = _keyword_boost(
                        query, f"{ep.content} {' '.join(ep.tags)}"
                    )
                    matched_episodes.append((ep, vec_sim + kw_boost))
                matched_episodes.sort(key=lambda item: item[1], reverse=True)
                matched_episodes = matched_episodes[: max(1, min(top_k, 5))]

            matches_payload = [
                {
                    "page": page.model_dump(),
                    "slug": page.slug,
                    "title": page.title,
                    "status": page.status,
                    "score": round(score, 4),
                    "cluster_id": page.cluster_id,
                    "tags": list(page.tags),
                    "summary": extract_summary(page.markdown_body),
                    "markdown_body": page.markdown_body,
                    "out_links": list(page.out_links),
                    "backlinks": list(page.backlinks),
                    "sources": [s.model_dump() for s in page.sources],
                }
                for page, score in top_pages
            ]

            neighbors_payload = [
                {
                    "slug": n.slug,
                    "title": n.title,
                    "status": n.status,
                    "cluster_id": n.cluster_id,
                    "summary": extract_summary(n.markdown_body),
                }
                for n in neighbor_pages
            ]

            episodes_payload = [
                {
                    "episode": ep.model_dump(),
                    "id": ep.id,
                    "content": ep.content,
                    "source_agent": ep.source_agent,
                    "tags": list(ep.tags),
                    "status": ep.status,
                    "score": round(ep_score, 4),
                    "created_at": ep.created_at,
                }
                for ep, ep_score in matched_episodes
            ]

            return {
                "query": query,
                "namespace": namespace,
                "matches": matches_payload,
                "wiki_pages": matches_payload,
                "neighbors": neighbors_payload,
                "episodes": episodes_payload,
                "pending_episodes": episodes_payload,
            }

    def _build_snapshot(self, pages: list[WikiPage], namespace: str) -> GraphSnapshot:
        page_slugs = {p.slug for p in pages}
        open_sugs = self.list_suggestions(namespace=namespace, status="open")
        sug_counts: dict[str, int] = {}
        for sug in open_sugs:
            sug_counts[sug.target_slug] = sug_counts.get(sug.target_slug, 0) + 1

        nodes = [
            GraphNode(
                slug=p.slug,
                title=p.title,
                status=p.status,
                cluster_id=p.cluster_id,
                tags=list(p.tags),
                x=p.x,
                y=p.y,
                summary=extract_summary(p.markdown_body),
                backlink_count=len(p.backlinks),
                out_link_count=len(p.out_links),
                open_suggestions=sug_counts.get(p.slug, 0),
            )
            for p in pages
        ]

        edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for p in pages:
            typed_targets: set[str] = set()
            for rel in p.relations:
                if rel.target in page_slugs:
                    typed_targets.add(rel.target)
                    key = (p.slug, rel.target, rel.type)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(
                            GraphEdge(source=p.slug, target=rel.target, type=rel.type)
                        )
            for out_target in p.out_links:
                if out_target in page_slugs and out_target not in typed_targets:
                    key = (p.slug, out_target, "wikilink")
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(
                            GraphEdge(source=p.slug, target=out_target, type="wikilink")
                        )

        clusters = self.list_clusters(namespace=namespace)
        return GraphSnapshot(
            namespace=namespace, nodes=nodes, edges=edges, clusters=clusters
        )

    def traverse_graph(
        self,
        seed_slug: str,
        depth: int = 2,
        namespace: str = "default",
    ) -> GraphSnapshot:
        with tracer.start_as_current_span("blob.store.traverse_graph") as span:
            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.seed_slug", seed_slug)

            all_pages = {
                p.slug: p
                for p in self.list_wiki_pages(namespace=namespace, include_ghosts=True)
            }
            seed_key = seed_slug if seed_slug in all_pages else slugify(seed_slug)
            if seed_key not in all_pages:
                return GraphSnapshot(
                    namespace=namespace, nodes=[], edges=[], clusters=[]
                )

            max_depth = max(0, depth)
            visited: dict[str, int] = {seed_key: 0}
            queue: deque[tuple[str, int]] = deque([(seed_key, 0)])

            while queue:
                curr_slug, curr_depth = queue.popleft()
                if curr_depth >= max_depth:
                    continue
                curr_page = all_pages.get(curr_slug)
                if curr_page is None:
                    continue
                neighbors = {
                    *curr_page.out_links,
                    *curr_page.backlinks,
                    *(r.target for r in curr_page.relations),
                }
                for n_slug in sorted(neighbors):
                    if n_slug in all_pages and n_slug not in visited:
                        visited[n_slug] = curr_depth + 1
                        queue.append((n_slug, curr_depth + 1))

            sub_pages = [all_pages[s] for s in visited if s in all_pages]
            return self._build_snapshot(sub_pages, namespace)

    def get_graph_snapshot(self, namespace: str = "default") -> GraphSnapshot:
        pages = self.list_wiki_pages(namespace=namespace, include_ghosts=True)
        return self._build_snapshot(pages, namespace)

    # ------------------------------------------------------------------
    # Semantic Clusters
    # ------------------------------------------------------------------

    def save_cluster(self, cluster: Cluster) -> Cluster:
        self.client.collection(self.CLUSTERS_COLLECTION).document(
            self._doc_key(cluster.namespace, cluster.id)
        ).set(cluster.model_dump())
        return cluster

    def list_clusters(self, namespace: str = "default") -> list[Cluster]:
        docs = (
            self.client.collection(self.CLUSTERS_COLLECTION)
            .where(filter=FieldFilter("namespace", "==", namespace))
            .stream()
        )
        clusters = [Cluster.model_validate(d.to_dict() or {}) for d in docs]
        clusters.sort(key=lambda c: c.title.lower())
        return clusters

    def get_cluster(
        self, cluster_id: str, namespace: str = "default"
    ) -> Cluster | None:
        snap = (
            self.client.collection(self.CLUSTERS_COLLECTION)
            .document(self._doc_key(namespace, cluster_id))
            .get()
        )
        if not snap.exists:
            return None
        return Cluster.model_validate(snap.to_dict() or {})

    def recompute_clusters(
        self, namespace: str = "default", max_clusters: int = 4
    ) -> list[Cluster]:
        with tracer.start_as_current_span("blob.store.recompute_clusters") as span:
            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.backend", "firestore")

            pages = self.list_wiki_pages(namespace=namespace, include_ghosts=True)
            existing = self.list_clusters(namespace=namespace)

            clusters, layout_map = compute_clusters_and_layout(
                pages=pages,
                existing_clusters=existing,
                max_clusters=max_clusters,
                namespace=namespace,
            )

            c_col = self.client.collection(self.CLUSTERS_COLLECTION)
            for old_c in existing:
                c_col.document(self._doc_key(namespace, old_c.id)).delete()
            for new_c in clusters:
                c_col.document(self._doc_key(namespace, new_c.id)).set(
                    new_c.model_dump()
                )

            p_col = self.client.collection(self.WIKI_PAGES_COLLECTION)
            for slug, (px, py, c_id) in layout_map.items():
                p_col.document(self._doc_key(namespace, slug)).update(
                    {"x": px, "y": py, "cluster_id": c_id}
                )

            get_event_bus().publish(
                "graph_updated",
                {
                    "updated_slugs": list(layout_map.keys()),
                    "clusters": [c.id for c in clusters],
                },
                namespace=namespace,
            )
            return clusters

    def update_cluster_metadata(
        self,
        cluster_id: str,
        title: str | None = None,
        summary: str | None = None,
        color: str | None = None,
        namespace: str = "default",
    ) -> Cluster | None:
        cluster = self.get_cluster(cluster_id, namespace=namespace)
        if cluster is None:
            return None
        if title is not None and title.strip():
            cluster.title = title.strip()
        if summary is not None:
            cluster.summary = summary.strip()
        if color is not None and color.strip():
            cluster.color = color.strip()
        cluster.updated_at = utc_now_iso()
        self.save_cluster(cluster)
        get_event_bus().publish(
            "cluster_updated",
            {"cluster_id": cluster.id, "title": cluster.title},
            namespace=namespace,
        )
        return cluster

    # ------------------------------------------------------------------
    # Curation Suggestions
    # ------------------------------------------------------------------

    def create_suggestion(
        self,
        target_slug: str,
        title: str,
        description: str = "",
        kind: str = "unmerged_episodes",
        episode_ids: list[str] | None = None,
        proposed_markdown: str | None = None,
        namespace: str = "default",
        suggestion_id: str | None = None,
    ) -> CurationSuggestion:
        sug_id = suggestion_id or f"sug-{uuid.uuid4().hex[:8]}"
        norm_target = slugify(target_slug)
        suggestion = CurationSuggestion(
            id=sug_id,
            namespace=namespace,
            target_slug=norm_target,
            kind=kind,
            title=title,
            description=description,
            episode_ids=list(episode_ids or []),
            proposed_markdown=proposed_markdown,
            status="open",
            created_at=utc_now_iso(),
        )
        self.client.collection(self.SUGGESTIONS_COLLECTION).document(sug_id).set(
            suggestion.model_dump()
        )
        get_event_bus().publish(
            "suggestion_created",
            {
                "id": suggestion.id,
                "target_slug": suggestion.target_slug,
                "title": suggestion.title,
            },
            namespace=namespace,
        )
        return suggestion

    def list_suggestions(
        self,
        namespace: str = "default",
        target_slug: str | None = None,
        status: str | None = "open",
    ) -> list[CurationSuggestion]:
        query = self.client.collection(self.SUGGESTIONS_COLLECTION).where(
            filter=FieldFilter("namespace", "==", namespace)
        )
        if target_slug is not None:
            query = query.where(
                filter=FieldFilter("target_slug", "==", slugify(target_slug))
            )
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))

        suggestions = [
            CurationSuggestion.model_validate(d.to_dict() or {}) for d in query.stream()
        ]
        suggestions.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return suggestions

    def get_suggestion(
        self, suggestion_id: str, namespace: str = "default"
    ) -> CurationSuggestion | None:
        snap = (
            self.client.collection(self.SUGGESTIONS_COLLECTION)
            .document(suggestion_id)
            .get()
        )
        if not snap.exists:
            return None
        sug = CurationSuggestion.model_validate(snap.to_dict() or {})
        return sug if sug.namespace == namespace else None

    def resolve_suggestion(
        self,
        suggestion_id: str,
        action: Literal["apply", "dismiss"] = "apply",
        namespace: str = "default",
    ) -> dict[str, Any]:
        with tracer.start_as_current_span("blob.store.resolve_suggestion") as span:
            span.set_attribute("blob.namespace", namespace)
            span.set_attribute("blob.suggestion.id", suggestion_id)
            span.set_attribute("blob.suggestion.action", action)

            suggestion = self.get_suggestion(suggestion_id, namespace=namespace)
            if suggestion is None:
                return {
                    "status": "error",
                    "message": f"CurationSuggestion '{suggestion_id}' not found.",
                }

            target_page = self.get_wiki_page(
                suggestion.target_slug, namespace=namespace
            )
            col = self.client.collection(self.SUGGESTIONS_COLLECTION)

            if action == "dismiss":
                suggestion.status = "dismissed"
                col.document(suggestion.id).update({"status": "dismissed"})
                get_event_bus().publish(
                    "suggestion_resolved",
                    {
                        "id": suggestion.id,
                        "action": "dismiss",
                        "target_slug": suggestion.target_slug,
                    },
                    namespace=namespace,
                )
                return {
                    "status": "ok",
                    "action": "dismiss",
                    "suggestion": suggestion.model_dump(),
                    "page": target_page.model_dump() if target_page else None,
                }

            linked_episodes = [
                ep
                for ep_id in suggestion.episode_ids
                if (ep := self.get_episode(ep_id, namespace=namespace)) is not None
            ]

            if suggestion.proposed_markdown:
                new_body = suggestion.proposed_markdown
            else:
                base_body = (
                    target_page.markdown_body.strip()
                    if target_page and target_page.markdown_body.strip()
                    else f"# {target_page.title if target_page else title_from_slug(suggestion.target_slug)}"
                )
                bullet_lines = [
                    f"- {ep.content} *(source: `{ep.source_agent}`)*"
                    for ep in linked_episodes
                ]
                if not bullet_lines and suggestion.description:
                    bullet_lines = [f"- {suggestion.description}"]
                addition = "\n".join(bullet_lines)
                new_body = f"{base_body}\n\n## Synthesized Updates ({suggestion.title})\n\n{addition}"

            updated_page = self.upsert_wiki_page(
                title=(
                    target_page.title
                    if target_page
                    else title_from_slug(suggestion.target_slug)
                ),
                markdown_body=new_body,
                slug=suggestion.target_slug,
                namespace=namespace,
                status="active",
                source_episode_ids=suggestion.episode_ids,
                source_agent="wiki_curator",
            )
            suggestion.status = "applied"
            col.document(suggestion.id).update({"status": "applied"})
            get_event_bus().publish(
                "suggestion_resolved",
                {
                    "id": suggestion.id,
                    "action": "apply",
                    "target_slug": suggestion.target_slug,
                },
                namespace=namespace,
            )
            return {
                "status": "ok",
                "action": "apply",
                "suggestion": suggestion.model_dump(),
                "page": updated_page.model_dump(),
            }
