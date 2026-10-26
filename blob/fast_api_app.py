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

import contextlib
import os
from collections.abc import AsyncIterator

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner

from blob.api.explorer_routes import explorer_router
from blob.app_utils import services
from blob.app_utils.a2a import attach_a2a_routes
from blob.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)
from blob.mcp_server import mcp

load_dotenv()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)
otel_to_cloud = os.environ.get(
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", ""
).lower() in ("true", "1")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from blob.agent import app as adk_app
    from blob.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=otel_to_cloud,
    lifespan=lifespan,
)
app.title = "blob"
app.description = "API for interacting with the Agent blob"

# Proxy routes so the Google Cloud console playground (reasoning_engine SDK) can
# talk to this agent alongside the native adk_api routes.
attach_reasoning_engine_routes(app)

# Explorer REST & SSE API (/api/*)
app.include_router(explorer_router)

# Universal MCP Server (/mcp Streamable SSE/HTTP)
app.mount("/mcp", mcp.sse_app())

FRONTEND_DIST_DIR = os.path.join(AGENT_DIR, "frontend", "dist")
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")
if os.path.isdir(FRONTEND_ASSETS_DIR):
    app.mount(
        "/insider/assets",
        StaticFiles(directory=FRONTEND_ASSETS_DIR),
        name="insider-assets",
    )

_FALLBACK_INSIDER_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Blob — Insider View Memory Fabric</title>
  </head>
  <body style="background:#0b0f19;color:#e2e8f0;font-family:system-ui,sans-serif;padding:2rem;">
    <div id="root">
      <h1>Blob — Insider View Workspace</h1>
      <p>Visual memory fabric &amp; Obsidian graph co-curation workspace.</p>
    </div>
  </body>
</html>
"""


def _serve_insider_spa(subpath: str = "") -> Response:
    """Serve static assets or SPA index.html from `frontend/dist` with a fallback."""
    dist_root = os.path.realpath(FRONTEND_DIST_DIR)
    if subpath:
        candidate = os.path.realpath(os.path.join(dist_root, subpath.lstrip("/")))
        if candidate.startswith(dist_root + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)

    index_file = os.path.join(dist_root, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return HTMLResponse(content=_FALLBACK_INSIDER_HTML, status_code=200)


@app.get("/insider", include_in_schema=False)
async def insider_root() -> Response:
    """Serve the Insider View React SPA entrypoint."""
    return _serve_insider_spa()


@app.get("/insider/{path:path}", include_in_schema=False)
async def insider_subpath(path: str) -> Response:
    """Serve Insider View static assets or SPA client-side routes."""
    return _serve_insider_spa(path)


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
