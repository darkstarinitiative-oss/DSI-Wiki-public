#!/usr/bin/env python3
"""api_app.py — read-only REST bridge (instances/topics/wiki/search), Starlette ASGI app.
Mounted at /api by the top-level gateway (DSI-Wiki-HTTP-Server.py).
"""
import json
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

LAYERS = ("raw", "documentation", "llm", "minified", "changelog", "devlog")


def load_instances(scan_dir):
    instances = {}
    if not os.path.isdir(scan_dir):
        return instances
    for fname in os.listdir(scan_dir):
        if not fname.endswith(".json"):
            continue
        try:
            data = json.loads(open(os.path.join(scan_dir, fname), encoding="utf-8").read())
        except (OSError, json.JSONDecodeError):
            continue
        if not data.get("enabled") or data.get("base_dir") in (None, "N/A"):
            continue
        instances[data.get("name", fname[:-5])] = data
    return instances


def list_topics(base_dir, layer):
    d = os.path.join(base_dir, layer)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f != "log.md")


def get_content(base_dir, layer, topic):
    path = os.path.join(base_dir, layer, f"{topic}.md")
    if not os.path.exists(path):
        return None
    return open(path, encoding="utf-8").read()


def search(base_dir, query, layer):
    layers_to_search = LAYERS if layer == "all" else (layer,)
    query_lower = query.lower()
    results = []
    for lyr in layers_to_search:
        d = os.path.join(base_dir, lyr)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".md"):
                continue
            content = open(os.path.join(d, fname), encoding="utf-8", errors="ignore").read()
            if query_lower in content.lower() or query_lower in fname.lower():
                results.append({"layer": lyr, "topic": fname[:-3], "excerpt": content[:1500]})
    return results[:10]


def _instance_base_dir(request, scan_dir):
    instances = load_instances(scan_dir)
    name = request.query_params.get("instance")
    if name is None or name not in instances:
        return None, instances
    return instances[name]["base_dir"], instances


async def instances_endpoint(request):
    scan_dir = request.app.state.scan_dir
    return JSONResponse({"instances": sorted(load_instances(scan_dir).keys())})


async def topics_endpoint(request):
    base_dir, instances = _instance_base_dir(request, request.app.state.scan_dir)
    if base_dir is None:
        return JSONResponse({"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())}, status_code=400)
    layer = request.query_params.get("layer", "minified")
    return JSONResponse({"topics": list_topics(base_dir, layer)})


async def wiki_endpoint(request):
    base_dir, instances = _instance_base_dir(request, request.app.state.scan_dir)
    if base_dir is None:
        return JSONResponse({"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())}, status_code=400)
    topic = request.query_params.get("topic")
    layer = request.query_params.get("layer", "minified")
    if not topic:
        return JSONResponse({"error": "missing ?topic="}, status_code=400)
    content = get_content(base_dir, layer, topic)
    if content is None:
        return JSONResponse({"error": f"not found: {layer}/{topic}.md"}, status_code=404)
    return JSONResponse({"instance": request.query_params.get("instance"), "layer": layer, "topic": topic, "content": content})


async def search_endpoint(request):
    base_dir, instances = _instance_base_dir(request, request.app.state.scan_dir)
    if base_dir is None:
        return JSONResponse({"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())}, status_code=400)
    query = request.query_params.get("q")
    if not query:
        return JSONResponse({"error": "missing ?q="}, status_code=400)
    layer = request.query_params.get("layer", "minified")
    return JSONResponse({"results": search(base_dir, query, layer)})


def build_app(scan_dir):
    app = Starlette(routes=[
        Route("/instances", instances_endpoint),
        Route("/topics", topics_endpoint),
        Route("/wiki", wiki_endpoint),
        Route("/search", search_endpoint),
    ])
    app.state.scan_dir = scan_dir
    return app
