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

"""REST and Server-Sent Events (SSE) routes for the Insider View workspace."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import Runner
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel, Field

from blob.agent import app as adk_app
from blob.agent import run_curation_pipeline
from blob.app_utils import services
from blob.app_utils.guardrails import build_guardrail_plugins
from blob.app_utils.model_router import gemini_for_agent
from blob.mcp_server import (
    get_page as mcp_get_page,
)
from blob.mcp_server import (
    list_clusters as mcp_list_clusters,
)
from blob.mcp_server import (
    recall as mcp_recall,
)
from blob.mcp_server import (
    remember as mcp_remember,
)
from blob.mcp_server import (
    traverse_graph as mcp_traverse_graph,
)
from blob.storage import (
    KnowledgeStore,
    WikiPage,
    extract_summary,
    get_event_bus,
    get_knowledge_store,
    seed_knowledge_store,
    serialize_wiki_page,
    slugify,
    title_from_slug,
    utc_now_iso,
)
from blob.tools.ui_tools import (
    ui_focus_cluster,
    ui_highlight_graph_nodes,
    ui_navigate_to_page,
)

tracer = trace.get_tracer(__name__)

explorer_router = APIRouter(prefix="/api", tags=["explorer"])

_background_tasks: set[asyncio.Task[Any]] = set()


def _schedule_background_curation(namespace: str) -> bool:
    """Schedule background curation if an asyncio loop is active."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    task = loop.create_task(run_curation_pipeline(namespace=namespace))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


class PageUpsertRequest(BaseModel):
    """Payload for creating or updating a WikiPage via `PUT /api/pages/{slug}`."""

    title: str | None = None
    markdown_body: str | None = None
    raw_markdown: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    cluster_id: str | None = None
    relations: list[dict[str, Any]] | None = None
    source_episode_ids: list[str] | None = None
    source_agent: str = "human"
    namespace: str = "default"


class EpisodeCreateRequest(BaseModel):
    """Payload for recording a raw Episode via `POST /api/episodes`."""

    content: str
    source_agent: str = "insider-ui"
    tags: list[str] = Field(default_factory=list)
    namespace: str = "default"
    interaction_id: str | None = None
    auto_curate: bool = False


class CurateRequest(BaseModel):
    """Payload for triggering synchronous curation via `POST /api/curate`."""

    namespace: str = "default"
    focus_slug: str | None = None


class SeedRequest(BaseModel):
    """Payload for seeding the knowledge store via `POST /api/seed`."""

    namespace: str = "default"
    force: bool = False


class SuggestionActionRequest(BaseModel):
    """Optional payload for applying or dismissing a CurationSuggestion."""

    namespace: str = "default"


class ChatRequest(BaseModel):
    """Payload for interactive co-curation chat via `POST /api/chat`."""

    message: str
    session_id: str | None = None
    user_id: str = "insider-user"
    namespace: str = "default"
    view_context: dict[str, Any] | None = None


class AssistantChatRequest(BaseModel):
    """Payload for chatting with the MCP-connected demo assistant via `POST /api/assistant/chat`."""

    message: str
    session_id: str | None = None
    user_id: str = "insider-user"
    namespace: str = "default"


def _build_page_detail_payload(
    store: KnowledgeStore,
    page: WikiPage,
    namespace: str,
) -> dict[str, Any]:
    """Build an enriched detail payload for a single WikiPage."""
    raw_md = serialize_wiki_page(page)

    enriched_backlinks = [
        {
            "slug": b_slug,
            "title": (
                bp.title
                if (bp := store.get_wiki_page(b_slug, namespace=namespace)) is not None
                else title_from_slug(b_slug)
            ),
            "status": bp.status if bp is not None else "ghost",
            "cluster_id": bp.cluster_id if bp is not None else None,
        }
        for b_slug in page.backlinks
    ]

    enriched_out_links = [
        {
            "slug": o_slug,
            "title": (
                op.title
                if (op := store.get_wiki_page(o_slug, namespace=namespace)) is not None
                else title_from_slug(o_slug)
            ),
            "status": op.status if op is not None else "ghost",
            "cluster_id": op.cluster_id if op is not None else None,
        }
        for o_slug in page.out_links
    ]

    open_suggestions = [
        s.model_dump()
        for s in store.list_suggestions(
            namespace=namespace, target_slug=page.slug, status="open"
        )
    ]

    source_episodes = [
        ep.model_dump(exclude={"embedding"})
        for src in page.sources
        if (ep := store.get_episode(src.episode_id, namespace=namespace)) is not None
    ]

    return {
        "status": "ok",
        "namespace": namespace,
        "slug": page.slug,
        "title": page.title,
        "page_status": page.status,
        "cluster_id": page.cluster_id,
        "tags": list(page.tags),
        "markdown_body": page.markdown_body,
        "raw_markdown": raw_md,
        "serialized_markdown": raw_md,
        "backlinks": enriched_backlinks,
        "out_links": enriched_out_links,
        "relations": [r.model_dump() for r in page.relations],
        "sources": [s.model_dump() for s in page.sources],
        "source_episodes": source_episodes,
        "suggestions": open_suggestions,
        "open_suggestions": open_suggestions,
        "updated_at": page.updated_at,
        "page": page.model_dump(exclude={"embedding"}),
    }


@explorer_router.get("/graph")
def get_graph(namespace: str = Query("default")) -> dict[str, Any]:
    """Return the full graph snapshot (`nodes`, `edges`, `clusters`, and `stats`)."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    snapshot = store.get_graph_snapshot(namespace=ns)
    pending_episodes = store.list_episodes(
        namespace=ns, status="pending_curation", limit=200
    )
    open_suggestions = store.list_suggestions(namespace=ns, status="open")

    active_count = sum(1 for n in snapshot.nodes if n.status == "active")
    ghost_count = sum(1 for n in snapshot.nodes if n.status == "ghost")

    return {
        "status": "ok",
        "namespace": ns,
        "nodes": [n.model_dump() for n in snapshot.nodes],
        "edges": [e.model_dump() for e in snapshot.edges],
        "clusters": [c.model_dump() for c in snapshot.clusters],
        "stats": {
            "total_pages": len(snapshot.nodes),
            "active_pages": active_count,
            "ghost_pages": ghost_count,
            "total_edges": len(snapshot.edges),
            "edges_count": len(snapshot.edges),
            "total_clusters": len(snapshot.clusters),
            "clusters_count": len(snapshot.clusters),
            "pending_episodes": len(pending_episodes),
            "open_suggestions": len(open_suggestions),
        },
    }


@explorer_router.get("/pages")
def list_pages(
    namespace: str = Query("default"),
    status: str | None = Query(None),
    cluster_id: str | None = Query(None),
    q: str | None = Query(None),
    include_ghosts: bool = Query(True),
) -> dict[str, Any]:
    """List or search Wiki pages in a namespace."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    pages = store.list_wiki_pages(
        namespace=ns,
        include_ghosts=include_ghosts,
        status=status,
        cluster_id=cluster_id,
        query=q,
    )
    return {
        "status": "ok",
        "namespace": ns,
        "count": len(pages),
        "pages": [
            {
                **p.model_dump(exclude={"embedding"}),
                "summary": extract_summary(p.markdown_body),
            }
            for p in pages
        ],
    }


@explorer_router.get("/pages/{slug}")
def get_page_detail(
    slug: str,
    namespace: str = Query("default"),
) -> dict[str, Any]:
    """Return a single WikiPage with enriched links, suggestions, and provenance."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    page = store.get_wiki_page(slug, namespace=ns)
    if page is None:
        raise HTTPException(
            status_code=404,
            detail=f"WikiPage '{slug}' not found in namespace '{ns}'.",
        )
    return _build_page_detail_payload(store, page, ns)


@explorer_router.put("/pages/{slug}")
def put_page(
    slug: str,
    payload: PageUpsertRequest,
    namespace: str | None = Query(None),
) -> dict[str, Any]:
    """Create or update a WikiPage from human Markdown or structured fields."""
    ns = (namespace or payload.namespace or "default").strip() or "default"
    store = get_knowledge_store()

    raw_text = (
        payload.raw_markdown
        if payload.raw_markdown is not None
        else (
            payload.markdown_body
            if payload.markdown_body is not None
            else (payload.content or "")
        )
    )

    if (
        payload.raw_markdown is not None
        and payload.title is None
        and payload.tags is None
    ):
        page = store.upsert_wiki_page_from_markdown(
            raw_markdown=raw_text,
            slug=slug,
            namespace=ns,
            source_agent=payload.source_agent or "human",
        )
    else:
        existing = store.get_wiki_page(slug, namespace=ns)
        effective_title = (
            payload.title.strip()
            if payload.title and payload.title.strip()
            else (existing.title if existing is not None else title_from_slug(slug))
        )
        page = store.upsert_wiki_page(
            title=effective_title,
            markdown_body=raw_text,
            slug=slug,
            namespace=ns,
            status="active",
            cluster_id=payload.cluster_id,
            tags=payload.tags,
            relations=payload.relations,
            source_episode_ids=payload.source_episode_ids,
            source_agent=payload.source_agent or "human",
        )
        if payload.tags is not None:
            page.tags = [str(t).strip() for t in payload.tags if str(t).strip()]

    return _build_page_detail_payload(store, page, ns)


@explorer_router.delete("/pages/{slug}")
def delete_page(
    slug: str,
    namespace: str = Query("default"),
) -> dict[str, Any]:
    """Delete a WikiPage and recompute bidirectional backlinks."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    deleted = store.delete_wiki_page(slug=slug, namespace=ns)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"WikiPage '{slug}' not found in namespace '{ns}'.",
        )
    return {
        "status": "ok",
        "deleted": True,
        "slug": slugify(slug),
        "namespace": ns,
    }


@explorer_router.get("/episodes")
def list_episodes(
    namespace: str = Query("default"),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """List raw or synthesized episodic memories in a namespace."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    episodes = store.list_episodes(namespace=ns, status=status, limit=limit)
    return {
        "status": "ok",
        "namespace": ns,
        "count": len(episodes),
        "episodes": [ep.model_dump(exclude={"embedding"}) for ep in episodes],
    }


@explorer_router.post("/episodes")
def create_episode(payload: EpisodeCreateRequest) -> dict[str, Any]:
    """Create a new episodic memory from the UI or REST client."""
    ns = (payload.namespace or "default").strip() or "default"
    cleaned_content = (payload.content or "").strip()
    if not cleaned_content:
        raise HTTPException(
            status_code=400,
            detail="Episode content cannot be empty.",
        )

    store = get_knowledge_store()
    episode = store.create_episode(
        content=cleaned_content,
        source_agent=(payload.source_agent or "insider-ui").strip() or "insider-ui",
        tags=payload.tags,
        namespace=ns,
        interaction_id=payload.interaction_id,
    )

    curation_scheduled = False
    if payload.auto_curate:
        curation_scheduled = _schedule_background_curation(ns)

    return {
        "status": "ok",
        "episode_id": episode.id,
        "namespace": ns,
        "curation_scheduled": curation_scheduled,
        "episode": episode.model_dump(exclude={"embedding"}),
    }


@explorer_router.get("/clusters")
def list_clusters(namespace: str = Query("default")) -> dict[str, Any]:
    """List semantic clusters in a namespace."""
    ns = (namespace or "default").strip() or "default"
    store = get_knowledge_store()
    clusters = store.list_clusters(namespace=ns)
    return {
        "status": "ok",
        "namespace": ns,
        "count": len(clusters),
        "clusters": [c.model_dump() for c in clusters],
    }


@explorer_router.post("/curate")
async def trigger_curation(
    payload: CurateRequest | None = None,
    namespace: str = Query("default"),
    focus_slug: str | None = Query(None),
) -> dict[str, Any]:
    """Run the curation and clustering pipeline synchronously and return the result."""
    ns = (
        (payload.namespace if payload and payload.namespace else namespace) or "default"
    ).strip() or "default"
    target_focus = (
        payload.focus_slug if payload and payload.focus_slug is not None else focus_slug
    )
    return await run_curation_pipeline(namespace=ns, focus_slug=target_focus)


@explorer_router.get("/suggestions")
def list_suggestions(
    namespace: str = Query("default"),
    target_slug: str | None = Query(None),
    status: str | None = Query("open"),
) -> dict[str, Any]:
    """List co-curation suggestions in a namespace."""
    ns = (namespace or "default").strip() or "default"
    effective_status = None if status == "all" else status
    store = get_knowledge_store()
    suggestions = store.list_suggestions(
        namespace=ns, target_slug=target_slug, status=effective_status
    )
    return {
        "status": "ok",
        "namespace": ns,
        "count": len(suggestions),
        "suggestions": [s.model_dump() for s in suggestions],
    }


@explorer_router.post("/suggestions/{suggestion_id}/apply")
def apply_suggestion(
    suggestion_id: str,
    payload: SuggestionActionRequest | None = None,
    namespace: str = Query("default"),
) -> dict[str, Any]:
    """Apply a co-curation suggestion by ID."""
    ns = (
        (payload.namespace if payload and payload.namespace else namespace) or "default"
    ).strip() or "default"
    store = get_knowledge_store()
    res = store.resolve_suggestion(
        suggestion_id=suggestion_id, action="apply", namespace=ns
    )
    if res.get("status") == "error":
        raise HTTPException(
            status_code=404,
            detail=res.get("message", f"Suggestion '{suggestion_id}' not found."),
        )
    if isinstance(res.get("page"), dict):
        page_copy = dict(res["page"])
        page_copy.pop("embedding", None)
        res = {**res, "page": page_copy}
    return res


@explorer_router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(
    suggestion_id: str,
    payload: SuggestionActionRequest | None = None,
    namespace: str = Query("default"),
) -> dict[str, Any]:
    """Dismiss a co-curation suggestion by ID."""
    ns = (
        (payload.namespace if payload and payload.namespace else namespace) or "default"
    ).strip() or "default"
    store = get_knowledge_store()
    res = store.resolve_suggestion(
        suggestion_id=suggestion_id, action="dismiss", namespace=ns
    )
    if res.get("status") == "error":
        raise HTTPException(
            status_code=404,
            detail=res.get("message", f"Suggestion '{suggestion_id}' not found."),
        )
    if isinstance(res.get("page"), dict):
        page_copy = dict(res["page"])
        page_copy.pop("embedding", None)
        res = {**res, "page": page_copy}
    return res


@explorer_router.post("/seed")
def seed_store_endpoint(
    payload: SeedRequest | None = None,
    namespace: str = Query("default"),
    force: bool = Query(False),
) -> dict[str, Any]:
    """Populate the 4-cluster demo dataset in the knowledge store."""
    ns = (
        (payload.namespace if payload and payload.namespace else namespace) or "default"
    ).strip() or "default"
    effective_force = bool(payload.force if payload is not None else force)
    return seed_knowledge_store(namespace=ns, force=effective_force)


def _normalize_view_context(
    raw_ctx: dict[str, Any] | None,
    default_namespace: str,
) -> dict[str, Any]:
    """Normalize incoming viewport context fields."""
    ctx = raw_ctx or {}
    active_page = (
        ctx.get("active_page_slug") or ctx.get("active_page") or ctx.get("slug") or None
    )
    selected_cluster = (
        ctx.get("selected_cluster_id")
        or ctx.get("cluster_id")
        or ctx.get("cluster")
        or None
    )
    raw_neighbors = ctx.get("visible_neighbors") or ctx.get("neighbors") or []
    neighbors = (
        [slugify(str(n)) for n in raw_neighbors if str(n).strip()]
        if isinstance(raw_neighbors, list)
        else []
    )
    ns = (
        str(ctx.get("namespace") or default_namespace or "default").strip() or "default"
    )
    return {
        "namespace": ns,
        "active_page_slug": slugify(str(active_page)) if active_page else None,
        "selected_cluster_id": str(selected_cluster).strip()
        if selected_cluster
        else None,
        "visible_neighbors": neighbors,
    }


def _offline_chat_fallback(
    message: str,
    namespace: str,
    view_context: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Provide a grounded local knowledge-store response when LLM credentials are unavailable."""
    store = get_knowledge_store()
    tool_calls: list[dict[str, Any]] = []
    active_slug = view_context.get("active_page_slug")
    selected_cluster = view_context.get("selected_cluster_id")

    if active_slug:
        page = store.get_wiki_page(active_slug, namespace=namespace)
        if page is not None:
            neighbors = list(dict.fromkeys([*page.out_links, *page.backlinks]))
            highlight_targets = [page.slug, *neighbors[:4]]
            ui_highlight_graph_nodes(
                slugs=highlight_targets,
                reason=f"Highlighting [[{page.title}]] and its connected graph neighborhood.",
                namespace=namespace,
            )
            tool_calls.append(
                {
                    "name": "ui_highlight_graph_nodes",
                    "args": {"slugs": highlight_targets, "namespace": namespace},
                }
            )
            sources_str = (
                ", ".join(f"`{s.episode_id}` ({s.source_agent})" for s in page.sources)
                if page.sources
                else "direct wiki synthesis"
            )
            links_str = (
                ", ".join(f"[[{title_from_slug(s)}]]" for s in neighbors[:5])
                if neighbors
                else "no linked pages yet"
            )
            reply = (
                f"**[[{page.title}]]** (`{page.slug}`) is in cluster "
                f"`{page.cluster_id or 'unclustered'}`.\n\n"
                f"- **Connected Nodes**: {links_str}\n"
                f"- **Provenance**: {sources_str}\n\n"
                f"{extract_summary(page.markdown_body, max_chars=280)}"
            )
            return reply, tool_calls

    if selected_cluster:
        cluster = store.get_cluster(selected_cluster, namespace=namespace)
        if cluster is not None:
            ui_focus_cluster(
                cluster_id=cluster.id,
                reason=f"Focusing semantic cluster '{cluster.title}'.",
                namespace=namespace,
            )
            tool_calls.append(
                {
                    "name": "ui_focus_cluster",
                    "args": {"cluster_id": cluster.id, "namespace": namespace},
                }
            )
            member_links = ", ".join(
                f"[[{title_from_slug(s)}]]" for s in cluster.page_slugs
            )
            return (
                f"Focused cluster **{cluster.title}** (`{cluster.id}`): "
                f"{cluster.summary}\n\nMember pages: {member_links}.",
                tool_calls,
            )

    recall_res = store.recall(
        query=message, namespace=namespace, top_k=3, include_episodes=True
    )
    matches = recall_res.get("matches", [])
    if matches:
        top = matches[0]
        matched_slugs = [m["slug"] for m in matches]
        ui_navigate_to_page(
            slug=top["slug"],
            reason=f"Top memory match for '{message}'.",
            namespace=namespace,
        )
        ui_highlight_graph_nodes(
            slugs=matched_slugs,
            reason="Matched Wiki pages from hybrid recall.",
            namespace=namespace,
        )
        tool_calls.extend(
            [
                {
                    "name": "ui_navigate_to_page",
                    "args": {"slug": top["slug"], "namespace": namespace},
                },
                {
                    "name": "ui_highlight_graph_nodes",
                    "args": {"slugs": matched_slugs, "namespace": namespace},
                },
            ]
        )
        lines = [
            f"- **[[{m['title']}]]** (`{m['slug']}`): {m['summary']}" for m in matches
        ]
        return (
            "Here is what I found in the Blob memory fabric:\n\n" + "\n".join(lines),
            tool_calls,
        )

    return (
        "No matching Wiki pages were found in the current namespace yet. "
        "You can seed the demo dataset or record new episodic memories.",
        tool_calls,
    )


@explorer_router.post("/chat")
async def chat_with_blob(
    payload: ChatRequest,
    request: Request,
) -> dict[str, Any]:
    """Run an interactive chat turn with `blob`, injecting active viewport context and collecting UI actions."""
    cleaned_message = (payload.message or "").strip()
    if not cleaned_message:
        raise HTTPException(status_code=400, detail="Chat message cannot be empty.")

    ns = (payload.namespace or "default").strip() or "default"
    normalized_ctx = _normalize_view_context(payload.view_context, ns)
    ns = normalized_ctx["namespace"]

    session_id = (payload.session_id or "").strip() or f"sess-{uuid.uuid4().hex[:10]}"
    user_id = (payload.user_id or "insider-user").strip() or "insider-user"
    app_name = getattr(request.app.state, "agent_app_name", adk_app.name)

    # Store view_context in session.state["view_context"]
    session_service = services.get_session_service()
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:
        session = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state={"view_context": normalized_ctx, "namespace": ns},
        )
    else:
        session.state["view_context"] = normalized_ctx
        session.state["namespace"] = ns

    # Format active viewport context header
    neighbors_str = (
        ", ".join(normalized_ctx["visible_neighbors"])
        if normalized_ctx["visible_neighbors"]
        else "none"
    )
    context_header = (
        "[Active Viewport Context]\n"
        f"namespace: {ns}\n"
        f"active_page_slug: {normalized_ctx['active_page_slug'] or 'none'}\n"
        f"selected_cluster_id: {normalized_ctx['selected_cluster_id'] or 'none'}\n"
        f"visible_neighbors: {neighbors_str}\n"
        "[/Active Viewport Context]\n\n"
    )
    augmented_message = f"{context_header}{cleaned_message}"

    bus = get_event_bus()
    turn_id = f"turn-{uuid.uuid4().hex[:10]}"
    bus.start_turn_collector(turn_id)

    reply_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    try:
        runner: Runner | None = getattr(request.app.state, "runner", None)
        if runner is None:
            runner = Runner(
                app=adk_app,
                session_service=session_service,
                artifact_service=services.get_artifact_service(),
                auto_create_session=True,
            )
            request.app.state.runner = runner

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=augmented_message)],
        )
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "function_call", None) is not None:
                        fc = part.function_call
                        tool_calls.append(
                            {
                                "name": getattr(fc, "name", ""),
                                "args": dict(getattr(fc, "args", {}) or {}),
                            }
                        )
                    elif getattr(part, "text", None) and not getattr(
                        part, "thought", False
                    ):
                        reply_parts.append(part.text)
    except Exception:
        fallback_reply, fallback_calls = _offline_chat_fallback(
            message=cleaned_message,
            namespace=ns,
            view_context=normalized_ctx,
        )
        reply_parts = [fallback_reply]
        tool_calls.extend(fallback_calls)

    reply_text = "\n".join(p.strip() for p in reply_parts if p and p.strip()).strip()
    if not reply_text:
        fallback_reply, fallback_calls = _offline_chat_fallback(
            message=cleaned_message,
            namespace=ns,
            view_context=normalized_ctx,
        )
        reply_text = fallback_reply
        tool_calls.extend(fallback_calls)

    ui_actions = [ev.model_dump() for ev in bus.pop_turn_actions(turn_id)]

    return {
        "status": "ok",
        "session_id": session_id,
        "user_id": user_id,
        "namespace": ns,
        "view_context": normalized_ctx,
        "reply": reply_text,
        "ui_actions": ui_actions,
        "tool_calls": tool_calls,
    }


_assistant_agent = Agent(
    name="assistant",
    # Fast tier: low-latency user-facing chat.
    model=gemini_for_agent("assistant", retry_attempts=2),
    description=(
        "A helpful personal and engineering assistant connected to the Blob "
        "memory fabric via MCP."
    ),
    instruction=(
        "You are a helpful, concise personal and software engineering assistant.\n\n"
        "You are connected to **Blob** (a shared memory fabric) via MCP tools:\n"
        "- Before answering questions about the user's projects, architecture, "
        "preferences, or past decisions, use `recall` (and `get_page` / "
        "`traverse_graph` when helpful) to ground your answer in stored memories.\n"
        "- When the user shares new facts, architectural decisions, conventions, "
        "or preferences—or asks you to remember something—call `remember` with "
        "`source_agent='assistant'`, relevant `tags`, and `auto_curate=True` so "
        "the Blob memory fabric ingests and curates it in the background.\n"
        "- Always use the active `namespace` provided in the user prompt context.\n"
        "- Speak naturally as a helpful assistant to the user (do not act as the "
        "internal graph curator)."
    ),
    tools=[
        mcp_remember,
        mcp_recall,
        mcp_get_page,
        mcp_traverse_graph,
        mcp_list_clusters,
    ],
)

_assistant_app = App(
    root_agent=_assistant_agent,
    name="assistant",
    plugins=build_guardrail_plugins(),
)


def _offline_assistant_fallback(
    message: str,
    namespace: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Provide an MCP-tool-backed assistant response when LLM credentials are unavailable."""
    tool_calls: list[dict[str, Any]] = []
    lower_msg = message.lower().strip()
    remember_triggers = (
        "remember",
        "note that",
        "we decided",
        "prefer",
        "record",
        "save",
    )

    if any(phrase in lower_msg for phrase in remember_triggers):
        rem_res = mcp_remember(
            content=message,
            source_agent="assistant",
            tags=["assistant", "mcp"],
            namespace=namespace,
            auto_curate=True,
        )
        tool_calls.append(
            {
                "name": "remember",
                "args": {
                    "content": message,
                    "source_agent": "assistant",
                    "tags": ["assistant", "mcp"],
                    "namespace": namespace,
                    "auto_curate": True,
                },
            }
        )
        ep_id = rem_res.get("episode_id", "ep-unknown")
        scheduled = bool(rem_res.get("curation_scheduled", False))
        curation_note = (
            "Background wiki curation has been scheduled automatically."
            if scheduled
            else "It is queued in pending episodes for the next curation pass."
        )
        reply = (
            "Got it — I've saved that to your Blob memory fabric via MCP `remember` "
            f"(episode `{ep_id}` in namespace `{namespace}`). {curation_note}"
        )
        return reply, tool_calls

    recall_res = mcp_recall(
        query=message,
        namespace=namespace,
        top_k=3,
        include_episodes=True,
    )
    tool_calls.append(
        {
            "name": "recall",
            "args": {
                "query": message,
                "namespace": namespace,
                "top_k": 3,
                "include_episodes": True,
            },
        }
    )

    matches = recall_res.get("matches", [])
    pending_eps = recall_res.get("pending_episodes", [])
    sections: list[str] = []

    if matches:
        page_lines = [
            f"- **[[{m['title']}]]** (`{m['slug']}`): {m['summary']}" for m in matches
        ]
        sections.append(
            "Here is what I found in your Blob Wiki memory via MCP `recall`:\n\n"
            + "\n".join(page_lines)
        )

    if pending_eps:
        ep_lines = [
            f"- `{ep['id']}` ({ep.get('source_agent', 'agent')}): {ep['content']}"
            for ep in pending_eps[:3]
        ]
        sections.append("**Recent Pending Episodes:**\n" + "\n".join(ep_lines))

    if sections:
        return "\n\n".join(sections), tool_calls

    return (
        "I checked your Blob memory via MCP `recall`, but no matching Wiki pages "
        "or episodes were found in this namespace yet. Tell me something to "
        'remember (for example, *"Remember that we decided to use Firestore vector search"*) '
        "and I'll store it for you!",
        tool_calls,
    )


@explorer_router.post("/assistant/chat")
async def chat_with_assistant(
    payload: AssistantChatRequest,
    request: Request,
) -> dict[str, Any]:
    """Run an interactive chat turn with the demo `assistant` agent connected via MCP tools."""
    cleaned_message = (payload.message or "").strip()
    if not cleaned_message:
        raise HTTPException(
            status_code=400, detail="Assistant message cannot be empty."
        )

    ns = (payload.namespace or "default").strip() or "default"
    session_id = (payload.session_id or "").strip() or f"asst-{uuid.uuid4().hex[:10]}"
    user_id = (payload.user_id or "insider-user").strip() or "insider-user"
    app_name = _assistant_app.name

    session_service = services.get_session_service()
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state={"namespace": ns},
        )
    else:
        session.state["namespace"] = ns

    augmented_message = f"[Active Namespace: {ns}]\n\n{cleaned_message}"

    reply_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    try:
        runner: Runner | None = getattr(request.app.state, "assistant_runner", None)
        if runner is None:
            runner = Runner(
                app=_assistant_app,
                session_service=session_service,
                artifact_service=services.get_artifact_service(),
                auto_create_session=True,
            )
            request.app.state.assistant_runner = runner

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=augmented_message)],
        )
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "function_call", None) is not None:
                        fc = part.function_call
                        tool_calls.append(
                            {
                                "name": getattr(fc, "name", ""),
                                "args": dict(getattr(fc, "args", {}) or {}),
                            }
                        )
                    elif getattr(part, "text", None) and not getattr(
                        part, "thought", False
                    ):
                        reply_parts.append(part.text)
    except Exception:
        fallback_reply, fallback_calls = _offline_assistant_fallback(
            message=cleaned_message,
            namespace=ns,
        )
        reply_parts = [fallback_reply]
        tool_calls.extend(fallback_calls)

    reply_text = "\n".join(p.strip() for p in reply_parts if p and p.strip()).strip()
    if not reply_text:
        fallback_reply, fallback_calls = _offline_assistant_fallback(
            message=cleaned_message,
            namespace=ns,
        )
        reply_text = fallback_reply
        tool_calls.extend(fallback_calls)

    return {
        "status": "ok",
        "session_id": session_id,
        "user_id": user_id,
        "namespace": ns,
        "reply": reply_text,
        "tool_calls": tool_calls,
    }


@explorer_router.get("/events")
async def stream_events(
    request: Request,
    namespace: str = Query("default"),
    once: bool = Query(False),
) -> StreamingResponse:
    """Server-Sent Events (SSE) stream of live graph updates and agent UI actions."""
    ns = (namespace or "default").strip() or "default"
    bus = get_event_bus()
    queue = bus.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            connected_payload = json.dumps(
                {
                    "id": f"evt-{uuid.uuid4().hex[:8]}",
                    "type": "connected",
                    "namespace": ns,
                    "payload": {"status": "subscribed"},
                    "timestamp": utc_now_iso(),
                }
            )
            yield f"data: {connected_payload}\n\n"
            if once:
                while not queue.empty():
                    ev = queue.get_nowait()
                    if ev.namespace in (ns, "*"):
                        yield f"data: {json.dumps(ev.model_dump())}\n\n"
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if event.namespace in (ns, "*"):
                        yield f"data: {json.dumps(event.model_dump())}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
