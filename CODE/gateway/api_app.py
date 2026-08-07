#!/usr/bin/env python3
"""api_app.py — read-only REST bridge (instances/topics/wiki/search), Starlette ASGI app.
Mounted at /api by the top-level gateway (DSI-Wiki-HTTP-Server.py).
"""
import json
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

LAYERS = ("raw", "documentation", "llm", "minified", "brief", "changelog", "devlog", "silinmişler")


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
        if not isinstance(data, dict):  # skip stray/malformed non-object JSON
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
            match_idx = content.lower().find(query_lower)
            if match_idx != -1 or query_lower in fname.lower():
                # Center the excerpt on the match so it's actually visible in long
                # documents, instead of always showing the first 1500 chars (which,
                # for a doc where the match is further in, silently omits it).
                if match_idx == -1:
                    excerpt = content[:1500]
                else:
                    start = max(0, match_idx - 300)
                    excerpt = content[start:start + 1500]
                results.append({"layer": lyr, "topic": fname[:-3], "excerpt": excerpt})
    return results[:10]


def _instance_base_dir(request, scan_dir):
    instances = load_instances(scan_dir)
    name = request.query_params.get("instance")
    if name is None or name not in instances:
        return None, instances
    return instances[name]["base_dir"], instances


def _status_path():
    return os.environ.get(
        "WIKI_STATUS_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "STATUS.json"),
    )


async def status_endpoint(request):
    status_path = _status_path()
    if not os.path.isfile(status_path):
        return JSONResponse({"error": "STATUS.json not yet written (ingest daemon not running?)"}, status_code=503)
    try:
        with open(status_path, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except (OSError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def info_endpoint(request):
    """DSI Info API Standard (DOCS/info-api-standard.md) -- a passthrough adapter over the
    ingest daemon's STATUS.json, plus this Gateway's own live-computed services[] entry
    (it has no poll loop of its own, so it's "ok" with a null heartbeat whenever it's
    answering a request at all)."""
    status_path = _status_path()
    ingest_status, ingest_note, services, feed = "error", "STATUS.json not yet written (ingest daemon not running?)", [], []
    service_name, version = "dsi-wiki", "0.1a"
    refresh_interval_seconds = 60
    if os.path.isfile(status_path):
        try:
            with open(status_path, encoding="utf-8") as f:
                raw = json.load(f)
            ingest_status = raw.get("status", "error")
            ingest_note = raw.get("status_note", "")
            services = raw.get("services", [])
            feed = raw.get("feed", [])
            version = raw.get("version", version)
            refresh_interval_seconds = raw.get("refresh_interval_seconds", refresh_interval_seconds)
        except (OSError, json.JSONDecodeError) as e:
            ingest_status, ingest_note = "error", str(e)

    services = list(services) + [
        {"name": "DSI-Wiki Gateway", "status": "ok", "last_heartbeat": None},
    ]
    return JSONResponse({
        "service": service_name,
        "version": version,
        "status": ingest_status,
        "status_note": ingest_note,
        "services": services,
        "feed": feed,
        "refresh_interval_seconds": refresh_interval_seconds,
    })


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
        Route("/status", status_endpoint),
        Route("/info", info_endpoint),
    ])
    app.state.scan_dir = scan_dir
    return app
