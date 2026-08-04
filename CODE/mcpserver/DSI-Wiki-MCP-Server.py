#!/usr/bin/env python3
"""DSI-Wiki-MCP-Server.py — instance-aware MCP tools over streamable-HTTP.
Mounted at /mcp by the top-level gateway (DSI-Wiki-HTTP-Server.py); the `app`
and `lifespan` objects below are imported and wired into the gateway's own
Starlette lifespan (FastMCP's session manager must run inside the lifespan
that's actually serving the request, not a separate one).
"""
import contextlib
import os
import sys

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gateway"))
from api_app import load_instances, list_topics, get_content, search  # noqa: E402


# streamable_http_path="/" so the sub-app's own root is the endpoint — the
# gateway mounts this whole sub-app at /mcp, so without this override the
# effective path would be /mcp/mcp (FastMCP's default sub-path is /mcp too).
mcp = FastMCP("dsi-wiki", host="0.0.0.0", streamable_http_path="/")


def _base_dir(scan_dir, instance):
    instances = load_instances(scan_dir)
    if instance not in instances:
        raise ValueError(f"unknown instance '{instance}'. available: {sorted(instances.keys())}")
    return instances[instance]["base_dir"]


def _scan_dir():
    return mcp.state_scan_dir


@mcp.tool()
def wiki_list_topics(instance: str, layer: str = "minified") -> list[str]:
    """List all topic names in a layer (raw/documentation/llm/minified/brief/changelog/devlog/
    silinmişler) for the given instance."""
    return list_topics(_base_dir(_scan_dir(), instance), layer)


@mcp.tool()
def wiki_get(instance: str, topic: str, layer: str = "minified") -> str:
    """Return the full content of one topic in one layer for the given instance."""
    content = get_content(_base_dir(_scan_dir(), instance), layer, topic)
    return content if content is not None else f"(not found: {layer}/{topic}.md)"


@mcp.tool()
def wiki_search(instance: str, query: str, layer: str = "minified") -> str:
    """Case-insensitive text search within one instance's layer (layer='all' searches
    every layer). Returns up to 10 matches, each capped at 1500 characters."""
    results = search(_base_dir(_scan_dir(), instance), query, layer)
    if not results:
        return f"no results for '{query}' (instance={instance}, layer={layer})"
    return "\n\n---\n\n".join(f"### [{r['layer']}] {r['topic']}\n{r['excerpt']}" for r in results)


def build_app(scan_dir):
    mcp.state_scan_dir = scan_dir
    return mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():
        yield


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8421, help="standalone test port")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--scan-dir", required=True)
    args = parser.parse_args()

    print(f">> Standalone test mode: http://{args.host}:{args.port}/")
    print("   In production this is mounted at /mcp by the gateway; this block never runs there.")
    mcp.state_scan_dir = args.scan_dir
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")
