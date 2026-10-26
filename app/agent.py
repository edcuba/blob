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

"""Blob multi-agent memory fabric hierarchy and curation pipeline."""

from __future__ import annotations

import re
from typing import Any

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.genai import types
from opentelemetry import trace

from app.storage import (
    Episode,
    WikiPage,
    get_event_bus,
    get_knowledge_store,
    slugify,
    title_from_slug,
)
from app.tools import (
    CLUSTER_TOOLS,
    CURATOR_TOOLS,
    MEMORY_TOOLS,
    UI_TOOLS,
)

MODEL = "gemini-3.8-flash"

tracer = trace.get_tracer(__name__)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


wiki_curator = Agent(
    name="wiki_curator",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Synthesizes pending episodic memories into structured Markdown Wiki pages "
        "with Obsidian-style [[Wiki Links]], materializes ghost nodes, maintains "
        "episode provenance, and creates co-curation suggestions."
    ),
    instruction=(
        "You are `wiki_curator`, the episodic synthesis and link-hygiene specialist "
        "for the Blob visual memory fabric.\n\n"
        "### Responsibilities\n"
        "1. Inspect unmerged episodes via `list_pending_episodes` and retrieve related "
        "context with `recall_knowledge` and `get_wiki_page`.\n"
        "2. Synthesize raw episodic notes into clean, well-structured Markdown Wiki "
        "articles via `upsert_wiki_page`, always passing `source_episode_ids` so "
        "provenance is preserved.\n"
        "3. Use Obsidian-style `[[Page Title]]` or `[[slug|Display Name]]` links to "
        "connect related concepts across the knowledge graph.\n"
        "4. Materialize ghost nodes (`status='ghost'`) into full active Wiki pages "
        "when supporting episodes or connected pages provide sufficient context.\n"
        "5. Surface 1-click co-curation suggestions via `create_curation_suggestion` "
        "when human review or contradiction resolution is helpful."
    ),
    tools=CURATOR_TOOLS,
)


cluster_analyst = Agent(
    name="cluster_analyst",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Groups Wiki pages into semantic clusters using 768-d vector similarity, "
        "computes 2D force-graph layout coordinates, and curates cluster titles, "
        "summaries, and colors."
    ),
    instruction=(
        "You are `cluster_analyst`, the semantic clustering and Map-of-Content (MOC) "
        "architect for the Blob visual memory fabric.\n\n"
        "### Responsibilities\n"
        "1. Run `recompute_semantic_clusters` to group Wiki pages by 768-dimensional "
        "embedding similarity and update 2D graph layout coordinates.\n"
        "2. Inspect cluster membership via `list_semantic_clusters` and `get_wiki_page`.\n"
        "3. Refine cluster titles, concise Map-of-Content summaries, and distinct hex "
        "colors via `update_cluster_metadata` so the human user can visually navigate "
        "high-level knowledge themes."
    ),
    tools=CLUSTER_TOOLS,
)


root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml:
    # telemetry reports this name as gen_ai.agent.name, and agents-cli reports the
    # manifest's value. Renaming the agent only here makes the two disagree, and
    # anything selecting traces by name stops finding this agent's.
    name="blob",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Blob is a visual memory fabric agent that organizes knowledge and memories "
        "from past agent interactions into an interactive Markdown Wiki graph and "
        "semantic clusters."
    ),
    instruction=(
        "You are **Blob**, a visual memory fabric agent organizing the knowledge and "
        "memories of past interactions into an interconnected Obsidian-style Markdown "
        "Wiki and 2D semantic graph.\n\n"
        "### How You Operate\n"
        "1. **Memory Ingestion (`remember_episode`)**: When the user or an agent shares "
        "new facts, preferences, architectural decisions, or notes, store them with "
        "`remember_episode` and appropriate topical tags. When asked to curate or "
        "synthesize immediately, also update or create the corresponding Wiki page "
        "via `upsert_wiki_page` (or delegate to `wiki_curator`).\n"
        "2. **Hybrid Recall & Provenance (`recall_knowledge`, `get_wiki_page`, "
        "`get_graph_neighborhood`)**: Always ground your answers in the knowledge "
        "store. Cite the Wiki pages (`[[Page Title]]`) and provenance sources "
        "(`episode_id`, `source_agent`) that support your answer.\n"
        "3. **Sub-Agent Coordination (`wiki_curator`, `cluster_analyst`)**: Delegate "
        "multi-episode synthesis to `wiki_curator` and semantic cluster reorganization "
        "to `cluster_analyst`. Because they are wrapped as `AgentTool`s, you retain "
        "turn control afterward.\n"
        "4. **Bidirectional UI Actions (`ui_navigate_to_page`, "
        "`ui_highlight_graph_nodes`, `ui_focus_cluster`)**: Whenever you reference, "
        "explain, or update specific Wiki pages or clusters, proactively emit UI "
        "actions (`ui_highlight_graph_nodes`, `ui_navigate_to_page`, or "
        "`ui_focus_cluster`) so the human user's Insider View canvas animates in sync "
        "with your explanation.\n"
        "5. **Viewport Context Awareness**: If a message includes `[Active Viewport "
        "Context]`, use the `active_page_slug`, `selected_cluster_id`, and "
        "`visible_neighbors` to resolve pronouns like 'this page' or 'this cluster'."
    ),
    tools=[
        *MEMORY_TOOLS,
        *UI_TOOLS,
        AgentTool(agent=wiki_curator),
        AgentTool(agent=cluster_analyst),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)


def _derive_title_from_episode(episode: Episode) -> str:
    """Derive a clean, human-readable WikiPage title from a raw Episode."""
    if episode.tags:
        primary_tags = [title_from_slug(t) for t in episode.tags[:2] if t.strip()]
        if primary_tags:
            return " & ".join(primary_tags) + " Notes"

    first_sentence = re.split(r"[.!?\n]", episode.content.strip(), maxsplit=1)[0]
    words = [w for w in re.split(r"\s+", first_sentence) if w][:6]
    if not words:
        return f"Memory {episode.id}"
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-/]", "", " ".join(words)).strip()
    return title_from_slug(slugify(cleaned)) if cleaned else f"Memory {episode.id}"


def _lexical_overlap_score(episode: Episode, page: WikiPage) -> float:
    """Compute lexical + tag overlap score between an Episode and a WikiPage."""
    ep_tokens = set(
        _TOKEN_RE.findall(f"{episode.content} {' '.join(episode.tags)}".lower())
    )
    if not ep_tokens:
        return 0.0
    page_tokens = set(
        _TOKEN_RE.findall(
            f"{page.title} {page.slug.replace('-', ' ')} {' '.join(page.tags)} {page.markdown_body}".lower()
        )
    )
    if not page_tokens:
        return 0.0

    tag_overlap = len(
        {t.lower() for t in episode.tags} & {t.lower() for t in page.tags}
    )
    title_tokens = set(
        _TOKEN_RE.findall(f"{page.title} {page.slug.replace('-', ' ')}".lower())
    )
    title_hits = len(ep_tokens & title_tokens)
    token_overlap = len(ep_tokens & page_tokens) / max(1, len(ep_tokens))
    return round(token_overlap + (0.35 * tag_overlap) + (0.25 * title_hits), 4)


async def run_curation_pipeline(
    namespace: str = "default",
    focus_slug: str | None = None,
) -> dict[str, Any]:
    """Synthesize pending episodes into WikiPages, materialize ghost nodes, and recompute clusters.

    This pipeline powers synchronous `POST /api/curate` and MCP `curate` calls as well as
    background `remember(auto_curate=True)` tasks.
    """
    with tracer.start_as_current_span("blob.curation.run_pipeline") as span:
        ns = namespace or "default"
        norm_focus = slugify(focus_slug) if focus_slug and focus_slug.strip() else None
        span.set_attribute("blob.namespace", ns)
        if norm_focus:
            span.set_attribute("blob.focus_slug", norm_focus)

        store = get_knowledge_store()
        synthesized_episodes: list[str] = []
        updated_pages: list[str] = []

        def _record_synthesis(ep_ids: list[str], page_slug: str) -> None:
            for eid in ep_ids:
                if eid and eid not in synthesized_episodes:
                    synthesized_episodes.append(eid)
            if page_slug and page_slug not in updated_pages:
                updated_pages.append(page_slug)

        # 1. If a specific focus_slug is targeted, apply open suggestions for it first
        if norm_focus:
            open_focus_suggestions = store.list_suggestions(
                namespace=ns, target_slug=norm_focus, status="open"
            )
            for sug in open_focus_suggestions:
                res = store.resolve_suggestion(sug.id, action="apply", namespace=ns)
                if res.get("status") == "ok":
                    _record_synthesis(sug.episode_ids, norm_focus)

        # 2. Apply open expand_ghost suggestions when their episodes are still pending
        open_suggestions = store.list_suggestions(namespace=ns, status="open")
        for sug in open_suggestions:
            if norm_focus and sug.target_slug != norm_focus:
                continue
            if sug.kind == "expand_ghost" or sug.proposed_markdown:
                res = store.resolve_suggestion(sug.id, action="apply", namespace=ns)
                if res.get("status") == "ok":
                    _record_synthesis(sug.episode_ids, sug.target_slug)

        # 3. Synthesize remaining pending episodes
        pending = store.list_episodes(namespace=ns, status="pending_curation", limit=50)
        all_pages = store.list_wiki_pages(namespace=ns, include_ghosts=True)
        ghost_pages = [p for p in all_pages if p.status == "ghost"]
        active_pages = [p for p in all_pages if p.status == "active"]

        for ep in pending:
            if ep.id in synthesized_episodes:
                continue

            # Check if an open suggestion links this episode to a specific target page
            matching_sug = next(
                (
                    s
                    for s in store.list_suggestions(namespace=ns, status="open")
                    if ep.id in s.episode_ids
                    and (not norm_focus or s.target_slug == norm_focus)
                ),
                None,
            )
            if matching_sug is not None:
                res = store.resolve_suggestion(
                    matching_sug.id, action="apply", namespace=ns
                )
                if res.get("status") == "ok":
                    _record_synthesis(
                        matching_sug.episode_ids or [ep.id],
                        matching_sug.target_slug,
                    )
                    continue

            # Check if episode matches a ghost node that can be materialized
            best_ghost: WikiPage | None = None
            best_ghost_score = 0.0
            for ghost in ghost_pages:
                if norm_focus and ghost.slug != norm_focus:
                    continue
                g_score = _lexical_overlap_score(ep, ghost)
                if g_score > best_ghost_score:
                    best_ghost_score = g_score
                    best_ghost = ghost

            if best_ghost is not None and best_ghost_score >= 0.35:
                backlink_titles = [
                    (
                        bp.title
                        if (bp := store.get_wiki_page(b_slug, namespace=ns))
                        else title_from_slug(b_slug)
                    )
                    for b_slug in best_ghost.backlinks[:4]
                ]
                links_line = (
                    "\n\n## Connected Concepts\n"
                    + "\n".join(f"- [[{t}]]" for t in backlink_titles)
                    if backlink_titles
                    else ""
                )
                ghost_md = (
                    f"# {best_ghost.title}\n\n"
                    f"{ep.content}\n\n"
                    "## Synthesized Context\n"
                    f"- Synthesized from `{ep.source_agent}` episode `{ep.id}`."
                    f"{links_line}"
                )
                page = store.upsert_wiki_page(
                    title=best_ghost.title,
                    markdown_body=ghost_md,
                    slug=best_ghost.slug,
                    namespace=ns,
                    status="active",
                    cluster_id=best_ghost.cluster_id,
                    tags=ep.tags,
                    source_episode_ids=[ep.id],
                    source_agent="wiki_curator",
                )
                _record_synthesis([ep.id], page.slug)
                ghost_pages = [g for g in ghost_pages if g.slug != page.slug]
                active_pages.append(page)
                continue

            # If focus_slug is explicitly provided and exists, merge relevant episode into it
            target_page: WikiPage | None = None
            if norm_focus:
                focus_candidate = store.get_wiki_page(norm_focus, namespace=ns)
                if (
                    focus_candidate is not None
                    and _lexical_overlap_score(ep, focus_candidate) >= 0.2
                ):
                    target_page = focus_candidate

            # Otherwise find the best matching active WikiPage via lexical + recall score
            if target_page is None and active_pages:
                scored_candidates: list[tuple[WikiPage, float]] = []
                recall_res = store.recall(
                    ep.content,
                    namespace=ns,
                    top_k=3,
                    include_episodes=False,
                )
                recall_scores = {
                    m["slug"]: float(m.get("score", 0.0))
                    for m in recall_res.get("matches", [])
                }
                for candidate in active_pages:
                    if norm_focus and candidate.slug != norm_focus:
                        continue
                    combined = _lexical_overlap_score(ep, candidate) + (
                        0.5 * recall_scores.get(candidate.slug, 0.0)
                    )
                    scored_candidates.append((candidate, combined))

                scored_candidates.sort(key=lambda item: item[1], reverse=True)
                if scored_candidates and scored_candidates[0][1] >= 0.45:
                    target_page = scored_candidates[0][0]

            if target_page is not None:
                refreshed = store.get_wiki_page(target_page.slug, namespace=ns)
                base_md = (
                    refreshed.markdown_body.strip()
                    if refreshed and refreshed.markdown_body.strip()
                    else f"# {target_page.title}"
                )
                bullet = f"- {ep.content} *(source: `{ep.source_agent}`, `{ep.id}`)*"
                if ep.content not in base_md:
                    if "## Synthesized Memory Updates" in base_md:
                        new_md = f"{base_md}\n{bullet}"
                    else:
                        new_md = (
                            f"{base_md}\n\n## Synthesized Memory Updates\n\n{bullet}"
                        )
                else:
                    new_md = base_md

                updated = store.upsert_wiki_page(
                    title=target_page.title,
                    markdown_body=new_md,
                    slug=target_page.slug,
                    namespace=ns,
                    status="active",
                    cluster_id=target_page.cluster_id,
                    tags=ep.tags,
                    source_episode_ids=[ep.id],
                    source_agent="wiki_curator",
                )
                _record_synthesis([ep.id], updated.slug)
            elif not norm_focus:
                # Create a new active WikiPage from the episode
                new_title = _derive_title_from_episode(ep)
                new_slug = slugify(new_title)
                related_links = [
                    f"[[{p.title}]]" for p in active_pages[:2] if p.slug != new_slug
                ]
                see_also = (
                    "\n\n## Related Pages\n- " + "\n- ".join(related_links)
                    if related_links
                    else ""
                )
                new_md = (
                    f"# {new_title}\n\n"
                    f"{ep.content}\n\n"
                    "## Provenance\n"
                    f"- Captured by `{ep.source_agent}` (`{ep.id}`)."
                    f"{see_also}"
                )
                created = store.upsert_wiki_page(
                    title=new_title,
                    markdown_body=new_md,
                    slug=new_slug,
                    namespace=ns,
                    status="active",
                    tags=ep.tags,
                    source_episode_ids=[ep.id],
                    source_agent="wiki_curator",
                )
                active_pages.append(created)
                _record_synthesis([ep.id], created.slug)

        # 4. If focus_slug was explicitly requested on a ghost node that is still a ghost,
        #    materialize it using its backlink neighborhood context.
        if norm_focus:
            focus_page = store.get_wiki_page(norm_focus, namespace=ns)
            if focus_page is not None and focus_page.status == "ghost":
                backlink_pages = [
                    bp
                    for b_slug in focus_page.backlinks
                    if (bp := store.get_wiki_page(b_slug, namespace=ns)) is not None
                ]
                backlink_refs = [f"[[{bp.title}]]" for bp in backlink_pages]
                context_text = (
                    f"Referenced across {', '.join(backlink_refs)}."
                    if backlink_refs
                    else "Synthesized concept node in the Blob knowledge fabric."
                )
                materialized_md = (
                    f"# {focus_page.title}\n\n"
                    f"**{focus_page.title}** is an active concept in the Blob memory fabric. "
                    f"{context_text}\n\n"
                    "## Connected Architecture & Workflows\n"
                    + (
                        "\n".join(
                            f"- Connected to [[{bp.title}]] (`{bp.slug}`)"
                            for bp in backlink_pages
                        )
                        if backlink_pages
                        else "- Standalone concept node."
                    )
                )
                materialized = store.upsert_wiki_page(
                    title=focus_page.title,
                    markdown_body=materialized_md,
                    slug=focus_page.slug,
                    namespace=ns,
                    status="active",
                    cluster_id=focus_page.cluster_id,
                    tags=focus_page.tags or ["synthesized"],
                    source_agent="wiki_curator",
                )
                if materialized.slug not in updated_pages:
                    updated_pages.append(materialized.slug)

        # 5. Recompute semantic clusters & 2D coordinates and publish graph_updated
        clusters = store.recompute_clusters(namespace=ns, max_clusters=4)
        get_event_bus().publish(
            "graph_updated",
            {
                "updated_slugs": updated_pages,
                "synthesized_episodes": synthesized_episodes,
                "clusters": [c.id for c in clusters],
            },
            namespace=ns,
        )

        return {
            "status": "ok",
            "namespace": ns,
            "focus_slug": norm_focus,
            "synthesized_episodes": synthesized_episodes,
            "updated_pages": updated_pages,
            "clusters": [c.model_dump() for c in clusters],
        }
