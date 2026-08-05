#!/usr/bin/env python3
"""DSI-Wiki-HTTP-Server.py — top-level gateway on a single port.
Mounts three sub-apps: /api (read-only REST bridge), /mcp (MCP protocol,
streamable-HTTP), /http (browsable UI). External callers reach each surface
through its own subdomain (wiki-api / wiki-mcp / wiki-http .example.com),
all forwarded by Cloudflare Tunnel to this same origin:port — the tunnel
can't rewrite paths, so a Host-header dispatch middleware here maps each
configured hostname to its internal mount, driven by `subdomain_routes` in
DSI-Wiki-HTTP-Config.json (config-driven, not hardcoded).
"""
import contextlib
import importlib.util
import json
import os
import sys

import uvicorn
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CONFIG_PATH = os.environ.get(
    "LLM_WIKI_HTTP_CONFIG", os.path.join(REPO_ROOT, "JSONS", "DSI-Wiki-HTTP-Config.json")
)

sys.path.insert(0, SCRIPT_DIR)

import api_app  # noqa: E402


def _load_module(name, path):
    """mcpserver/ui filenames use hyphens, so a plain `import` can't
    reach them — load each by explicit file path instead."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


class SubdomainDispatchMiddleware:
    """Rewrites scope['path'] to <mount>/<original path> based on the Host
    header, using the hostname -> mount map from config. Requests that
    already target a mount directly (e.g. local curl to /api/... or /mcp/...)
    pass through unchanged."""

    def __init__(self, app: ASGIApp, subdomain_routes: dict):
        self.app = app
        self.routes = subdomain_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            host = dict(scope.get("headers", [])).get(b"host", b"").decode().split(":")[0]
            mount = self.routes.get(host)
            if mount and not scope["path"].startswith(mount):
                scope = dict(scope)
                scope["path"] = mount + scope["path"]
        await self.app(scope, receive, send)


def build_app():
    cfg = load_config()
    scan_dir = cfg["scan_dir"]
    repo_python_dir = os.path.dirname(SCRIPT_DIR)

    mcp_module = _load_module("dsi_wiki_mcp_server", os.path.join(repo_python_dir, "mcpserver", "DSI-Wiki-MCP-Server.py"))
    ui_module = _load_module("dsi_wiki_ui_server", os.path.join(repo_python_dir, "ui", "DSI-Wiki-UI-Server.py"))

    api_sub_app = api_app.build_app(scan_dir)
    mcp_sub_app = mcp_module.build_app(scan_dir)
    ui_sub_app = ui_module.build_app(scan_dir)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp_module.mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[],
        lifespan=lifespan,
    )
    app.mount("/api", api_sub_app)
    app.mount("/mcp", mcp_sub_app)
    app.mount("/http", ui_sub_app)

    return SubdomainDispatchMiddleware(app, cfg.get("subdomain_routes", {})), cfg.get("port", 8430)


app, PORT = build_app()


def main():
    print(f">> DSI-Wiki Gateway listening on :{PORT} (mounts: /api /mcp /http)")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
