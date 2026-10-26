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

"""Markdown + YAML frontmatter parser and [[WikiLink]] extractor for Blob."""

from __future__ import annotations

import re
from typing import Any

import yaml

from app.storage.models import EpisodeSource, GraphRelation, WikiPage, utc_now_iso

_FRONTMATTER_RE = re.compile(
    r"\A\s*---\r?\n(?P<yaml>.*?)\r?\n---\r?\n?(?P<body>.*)\Z",
    re.DOTALL,
)
_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_ACRONYM_MAP = {
    "mcp": "MCP",
    "adk": "ADK",
    "gcp": "GCP",
    "api": "API",
    "sse": "SSE",
    "ui": "UI",
    "ux": "UX",
    "llm": "LLM",
    "moc": "MOC",
    "a2a": "A2A",
    "iam": "IAM",
    "gcs": "GCS",
    "bq": "BQ",
    "ci": "CI",
    "cd": "CD",
    "id": "ID",
    "2d": "2D",
}


def slugify(text: str) -> str:
    """Normalize a page title or identifier into a URL-safe kebab-case slug."""
    cleaned = _SLUG_CLEAN_RE.sub("-", (text or "").strip().lower()).strip("-")
    return cleaned or "untitled"


def title_from_slug(slug: str) -> str:
    """Convert a kebab-case slug into a human-readable title."""
    parts = [p for p in re.split(r"[-_\s]+", (slug or "").strip()) if p]
    if not parts:
        return "Untitled"
    words = [_ACRONYM_MAP.get(p.lower(), p.capitalize()) for p in parts]
    return " ".join(words)


def extract_wikilinks(markdown_text: str) -> list[tuple[str, str]]:
    """Extract Obsidian-style [[Page Name]] and [[slug|Display Name]] links.

    Ignores fenced code blocks and inline code spans.

    Returns:
        Deduplicated list of (slug, display_title) tuples in appearance order.
    """
    if not markdown_text:
        return []

    without_fenced = _FENCED_CODE_RE.sub("", markdown_text)
    without_code = _INLINE_CODE_RE.sub("", without_fenced)

    results: list[tuple[str, str]] = []
    seen_slugs: set[str] = set()

    for match in _WIKILINK_RE.finditer(without_code):
        raw_inner = match.group(1).strip()
        if not raw_inner:
            continue

        if "|" in raw_inner:
            raw_target, raw_display = raw_inner.split("|", 1)
            link_slug = slugify(raw_target)
            display_title = raw_display.strip() or title_from_slug(link_slug)
        else:
            # Strip optional heading anchor [[Page#Section]] while keeping page target
            raw_target = raw_inner.split("#", 1)[0].strip()
            if not raw_target:
                continue
            link_slug = slugify(raw_target)
            display_title = raw_target

        if link_slug not in seen_slugs:
            seen_slugs.add(link_slug)
            results.append((link_slug, display_title))

    return results


def extract_summary(markdown_text: str, max_chars: int = 200) -> str:
    """Extract a clean plain-text summary from a Markdown body."""
    if not markdown_text:
        return ""

    # Strip frontmatter if present
    fm_match = _FRONTMATTER_RE.match(markdown_text)
    text = fm_match.group("body") if fm_match else markdown_text

    # Remove fenced code blocks and headings
    text = _FENCED_CODE_RE.sub("", text)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Remove bullet markers
        stripped = re.sub(r"^[-*+]\s+", "", stripped)
        lines.append(stripped)

    joined = " ".join(lines)
    # Replace [[slug|Display]] -> Display and [[Page]] -> Page
    joined = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", joined)
    joined = re.sub(r"\[\[([^\]]+)\]\]", r"\1", joined)
    # Strip bold/italic/code markers
    joined = re.sub(r"[*_`]+", "", joined)
    joined = re.sub(r"\s+", " ", joined).strip()

    if len(joined) <= max_chars:
        return joined
    return joined[: max_chars - 1].rstrip() + "…"


def parse_wiki_markdown(
    raw_markdown: str,
    fallback_slug: str | None = None,
    fallback_title: str | None = None,
    namespace: str = "default",
) -> dict[str, Any]:
    """Parse optional YAML frontmatter + Markdown body into WikiPage fields."""
    text = raw_markdown or ""
    frontmatter: dict[str, Any] = {}
    body = text

    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        yaml_block = fm_match.group("yaml")
        body = fm_match.group("body")
        try:
            loaded = yaml.safe_load(yaml_block)
            if isinstance(loaded, dict):
                frontmatter = loaded
        except yaml.YAMLError:
            frontmatter = {}

    body_stripped = body.strip()

    # Determine title
    heading_match = _HEADING_RE.search(body_stripped)
    first_heading = heading_match.group(1).strip() if heading_match else None

    raw_title = (
        frontmatter.get("title")
        or fallback_title
        or first_heading
        or (title_from_slug(fallback_slug) if fallback_slug else None)
    )

    # Determine slug
    raw_slug = frontmatter.get("slug") or fallback_slug or raw_title or "untitled"
    page_slug = slugify(str(raw_slug))
    page_title = str(raw_title).strip() if raw_title else title_from_slug(page_slug)

    # Parse inline [[wikilinks]]
    wikilinks = extract_wikilinks(body_stripped)
    wikilink_titles = dict(wikilinks)

    # Parse frontmatter relations
    relations: list[GraphRelation] = []
    seen_relations: set[tuple[str, str]] = set()
    raw_relations = frontmatter.get("relations") or []
    if isinstance(raw_relations, list):
        for item in raw_relations:
            if isinstance(item, GraphRelation):
                rel_type = item.type or "relates_to"
                rel_target = slugify(item.target)
            elif isinstance(item, dict) and item.get("target"):
                rel_type = str(item.get("type") or "relates_to")
                rel_target = slugify(str(item["target"]))
            else:
                continue
            if rel_target and rel_target != page_slug:
                key = (rel_type, rel_target)
                if key not in seen_relations:
                    seen_relations.add(key)
                    relations.append(GraphRelation(type=rel_type, target=rel_target))

    # Merge out_links from frontmatter, inline wikilinks, and relations
    out_links: list[str] = []
    seen_out: set[str] = set()

    raw_out_links = frontmatter.get("out_links") or []
    candidates: list[str] = []
    if isinstance(raw_out_links, list):
        candidates.extend(slugify(str(x)) for x in raw_out_links if x)
    candidates.extend(link_slug for link_slug, _ in wikilinks)
    candidates.extend(rel.target for rel in relations)

    for candidate in candidates:
        if candidate and candidate != page_slug and candidate not in seen_out:
            seen_out.add(candidate)
            out_links.append(candidate)

    # Parse backlinks if present
    raw_backlinks = frontmatter.get("backlinks") or []
    backlinks: list[str] = []
    if isinstance(raw_backlinks, list):
        for item in raw_backlinks:
            b_slug = slugify(str(item))
            if b_slug and b_slug != page_slug and b_slug not in backlinks:
                backlinks.append(b_slug)

    # Parse sources
    sources: list[EpisodeSource] = []
    raw_sources = frontmatter.get("sources") or []
    if isinstance(raw_sources, list):
        for src in raw_sources:
            if isinstance(src, EpisodeSource):
                sources.append(src)
            elif isinstance(src, dict) and src.get("episode_id"):
                sources.append(
                    EpisodeSource(
                        episode_id=str(src["episode_id"]),
                        source_agent=str(src.get("source_agent") or "external"),
                        interaction_id=(
                            str(src["interaction_id"])
                            if src.get("interaction_id")
                            else None
                        ),
                        timestamp=str(src.get("timestamp") or utc_now_iso()),
                    )
                )

    # Parse tags
    raw_tags = frontmatter.get("tags") or []
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            tag_str = str(t).strip()
            if tag_str and tag_str not in tags:
                tags.append(tag_str)

    status = str(frontmatter.get("status") or "active")
    if status not in ("active", "ghost", "archived"):
        status = "active"

    cluster_id = (
        str(frontmatter["cluster_id"]) if frontmatter.get("cluster_id") else None
    )
    resolved_namespace = str(frontmatter.get("namespace") or namespace or "default")
    updated_at = str(frontmatter.get("updated_at") or utc_now_iso())

    return {
        "slug": page_slug,
        "title": page_title,
        "namespace": resolved_namespace,
        "status": status,
        "cluster_id": cluster_id,
        "tags": tags,
        "out_links": out_links,
        "backlinks": backlinks,
        "relations": relations,
        "sources": sources,
        "updated_at": updated_at,
        "markdown_body": body_stripped,
        "wikilinks": wikilinks,
        "wikilink_titles": wikilink_titles,
    }


def serialize_wiki_page(page: WikiPage) -> str:
    """Serialize a WikiPage to YAML frontmatter + Markdown body."""
    frontmatter_data: dict[str, Any] = {
        "slug": page.slug,
        "title": page.title,
        "namespace": page.namespace,
        "status": page.status,
        "cluster_id": page.cluster_id,
        "tags": list(page.tags),
        "out_links": list(page.out_links),
        "backlinks": list(page.backlinks),
        "relations": [{"type": r.type, "target": r.target} for r in page.relations],
        "sources": [
            {
                "episode_id": s.episode_id,
                "source_agent": s.source_agent,
                **(
                    {"interaction_id": s.interaction_id}
                    if s.interaction_id is not None
                    else {}
                ),
                "timestamp": s.timestamp,
            }
            for s in page.sources
        ],
        "updated_at": page.updated_at,
    }

    yaml_str = yaml.safe_dump(
        frontmatter_data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    body = page.markdown_body.strip()
    if not body:
        body = f"# {page.title}\n\n*(Ghost node awaiting synthesis)*"

    return f"---\n{yaml_str}\n---\n\n{body}\n"
