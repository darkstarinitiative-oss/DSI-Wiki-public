#!/usr/bin/env python3
"""
DSI-Wiki-HTTP-Server.py — read-only HTTP bridge for external (non-MCP) callers.
Mirrors the three MCP tools (list_topics / get / search) but instance-scoped,
since DSI-Wiki manages multiple project instances (Instances/*.json), unlike
the legacy single-BASE_DIR wiki_server.py this config was originally modeled on.
"""
import http.server
import json
import os
import socketserver
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "DSI-Wiki-HTTP-Config.json")
LAYERS = ("raw", "documentation", "llm", "minified", "changelog", "devlog")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


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


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _instance_base_dir(self, qs):
        instances = load_instances(load_config()["scan_dir"])
        name = qs.get("instance", [None])[0]
        if name is None or name not in instances:
            return None, instances
        return instances[name]["base_dir"], instances

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/instances":
            instances = load_instances(load_config()["scan_dir"])
            self._json(200, {"instances": sorted(instances.keys())})
            return

        if parsed.path == "/topics":
            base_dir, instances = self._instance_base_dir(qs)
            if base_dir is None:
                self._json(400, {"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())})
                return
            layer = qs.get("layer", ["minified"])[0]
            self._json(200, {"topics": list_topics(base_dir, layer)})
            return

        if parsed.path == "/wiki":
            base_dir, instances = self._instance_base_dir(qs)
            if base_dir is None:
                self._json(400, {"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())})
                return
            topic = qs.get("topic", [None])[0]
            layer = qs.get("layer", ["minified"])[0]
            if not topic:
                self._json(400, {"error": "missing ?topic="})
                return
            content = get_content(base_dir, layer, topic)
            if content is None:
                self._json(404, {"error": f"not found: {layer}/{topic}.md"})
                return
            self._json(200, {"instance": qs.get("instance")[0], "layer": layer, "topic": topic, "content": content})
            return

        if parsed.path == "/search":
            base_dir, instances = self._instance_base_dir(qs)
            if base_dir is None:
                self._json(400, {"error": "unknown or missing ?instance=", "instances": sorted(instances.keys())})
                return
            query = qs.get("q", [None])[0]
            if not query:
                self._json(400, {"error": "missing ?q="})
                return
            layer = qs.get("layer", ["minified"])[0]
            self._json(200, {"results": search(base_dir, query, layer)})
            return

        self._json(404, {"error": "unknown route", "routes": ["/instances", "/topics", "/wiki", "/search"]})

    def log_message(self, fmt, *args):
        pass  # quiet by default; systemd journal captures stdout separately if needed


def main():
    cfg = load_config()
    port = cfg.get("port", 8430)
    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f">> DSI-Wiki HTTP-Service listening on :{port} (scan_dir={cfg['scan_dir']})")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
