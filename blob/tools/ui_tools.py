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

"""Bidirectional Agent-in-the-Loop UI action tools for the Insider View workspace."""

from __future__ import annotations

from typing import Any

from opentelemetry import trace

from blob.storage import get_event_bus, slugify

tracer = trace.get_tracer(__name__)


def ui_navigate_to_page(
    slug: str,
    reason: str = "",
    namespace: str = "default",
) -> dict[str, Any]:
    """Navigate the user's Insider View Wiki editor and graph selection to a specific WikiPage.

    Args:
        slug: The slug or title of the WikiPage to open in the UI.
        reason: Brief explanation shown to the user for why the agent opened this page.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary confirming the emitted UI navigation event.
    """
    with tracer.start_as_current_span("blob.tool.ui_navigate_to_page") as span:
        ns = namespace or "default"
        norm_slug = slugify(slug)
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.ui.slug", norm_slug)

        event = get_event_bus().publish(
            "ui_navigate_to_page",
            {"slug": norm_slug, "reason": reason},
            namespace=ns,
        )
        return {
            "status": "ok",
            "action": "ui_navigate_to_page",
            "slug": norm_slug,
            "reason": reason,
            "namespace": ns,
            "event": event.model_dump(),
        }


def ui_highlight_graph_nodes(
    slugs: list[str],
    reason: str = "",
    namespace: str = "default",
) -> dict[str, Any]:
    """Pulse and highlight a set of nodes on the 2D force-directed graph canvas in the Insider View UI.

    Args:
        slugs: List of WikiPage slugs or titles to highlight on the graph canvas.
        reason: Brief explanation of how the highlighted nodes relate to the user's question.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary confirming the emitted UI highlight event.
    """
    with tracer.start_as_current_span("blob.tool.ui_highlight_graph_nodes") as span:
        ns = namespace or "default"
        norm_slugs = [slugify(s) for s in (slugs or []) if str(s).strip()]
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.ui.highlight_count", len(norm_slugs))

        event = get_event_bus().publish(
            "ui_highlight_nodes",
            {"slugs": norm_slugs, "reason": reason},
            namespace=ns,
        )
        return {
            "status": "ok",
            "action": "ui_highlight_nodes",
            "slugs": norm_slugs,
            "reason": reason,
            "namespace": ns,
            "event": event.model_dump(),
        }


def ui_focus_cluster(
    cluster_id: str,
    reason: str = "",
    namespace: str = "default",
) -> dict[str, Any]:
    """Zoom and focus the 2D graph canvas onto a semantic cluster hull in the Insider View UI.

    Args:
        cluster_id: Identifier of the semantic cluster to focus (e.g. "cluster-system-architecture").
        reason: Brief explanation of why the agent is focusing this semantic cluster.
        namespace: Memory namespace scope (defaults to "default").

    Returns:
        A structured dictionary confirming the emitted UI cluster focus event.
    """
    with tracer.start_as_current_span("blob.tool.ui_focus_cluster") as span:
        ns = namespace or "default"
        clean_id = (cluster_id or "").strip()
        span.set_attribute("blob.namespace", ns)
        span.set_attribute("blob.ui.cluster_id", clean_id)

        event = get_event_bus().publish(
            "ui_focus_cluster",
            {"cluster_id": clean_id, "reason": reason},
            namespace=ns,
        )
        return {
            "status": "ok",
            "action": "ui_focus_cluster",
            "cluster_id": clean_id,
            "reason": reason,
            "namespace": ns,
            "event": event.model_dump(),
        }


UI_TOOLS = [
    ui_navigate_to_page,
    ui_highlight_graph_nodes,
    ui_focus_cluster,
]
