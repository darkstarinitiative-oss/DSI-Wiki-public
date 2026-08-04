#!/usr/bin/env python3
"""DSI-Wiki-UI-Server.py — browsable wiki UI, Starlette ASGI app, instance-aware.
Mounted at /http by the top-level gateway (DSI-Wiki-HTTP-Server.py). Replaces the old
single-instance socketserver-based UI, which hardcoded ~/LLM-Wiki-BASE and port 9120
(already occupied by the unrelated legacy llm-wiki-ui.service).
"""
import json
import os
import sys

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gateway"))
from api_app import load_instances, get_content  # noqa: E402

LAYERS = ("documentation", "llm", "minified")


def _visible_topics_path(base_dir):
    return os.path.join(base_dir, "config", "visible_topics.json")


def load_visible_topics(base_dir):
    path = _visible_topics_path(base_dir)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return None


def save_visible_topics(base_dir, topics):
    path = _visible_topics_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(sorted(topics), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def list_all_topics(base_dir):
    d = os.path.join(base_dir, "llm")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f != "log.md")


def list_topics(base_dir):
    visible = load_visible_topics(base_dir)
    return visible if visible is not None else list_all_topics(base_dir)


def _default_instance(instances):
    for name, data in instances.items():
        if "keyword" not in data:
            return name
    return next(iter(instances), None)


def _base_dir(request):
    instances = load_instances(request.app.state.scan_dir)
    name = request.query_params.get("instance") or _default_instance(instances)
    return instances.get(name, {}).get("base_dir"), name, instances


THEME_URL = "https://bootswatch.com/5/cyborg/bootstrap.min.css"

HTML = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DSI-Wiki</title>
<link id="theme-link" rel="stylesheet" href="{THEME_URL}">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<style>
  html, body {{ height: 100%; overflow: hidden; }}
  #sidebar {{
    width: 280px; min-width: 220px; flex-shrink: 0;
    display: flex; flex-direction: column;
    border-right: 1px solid var(--bs-border-color);
    overflow: hidden;
  }}
  #sidebar-header {{
    padding: 0.85rem 1rem;
    border-bottom: 1px solid var(--bs-border-color);
    font-weight: 600; font-size: 1rem; letter-spacing: 0.02em;
  }}
  #controls {{ padding: 0.6rem; border-bottom: 1px solid var(--bs-border-color); display: flex; flex-direction: column; gap: 0.4rem; }}
  #topic-list {{ flex: 1; overflow-y: auto; padding: 0.25rem 0; }}
  .topic-item {{
    display: flex; align-items: center;
    padding: 0.3rem 0.75rem; gap: 0.4rem;
    cursor: pointer; font-size: 0.85rem;
    border-left: 3px solid transparent;
    transition: background 0.1s;
  }}
  .topic-item:hover {{ background: var(--bs-tertiary-bg); }}
  .topic-item.active {{
    border-left-color: var(--bs-primary);
    background: var(--bs-secondary-bg);
    color: var(--bs-primary);
  }}
  .topic-item .name {{ flex: 1; word-break: break-all; }}
  .pin-btn {{
    background: none; border: none; cursor: pointer;
    font-size: 0.9rem; opacity: 0.25; padding: 0 2px;
    transition: opacity 0.15s; line-height: 1;
  }}
  .topic-item:hover .pin-btn {{ opacity: 0.6; }}
  .pin-btn.pinned {{ opacity: 1 !important; }}
  #sidebar-footer {{ padding: 0.5rem 0.75rem; font-size: 0.72rem; color: var(--bs-secondary-color); border-top: 1px solid var(--bs-border-color); }}
  #main {{ flex: 1; overflow-y: auto; padding: 2rem 2.5rem; }}
  #placeholder {{ color: var(--bs-secondary-color); text-align: center; margin-top: 5rem; font-size: 1.05rem; }}
  #content table {{ width: 100%; }}
  #content pre {{ border: 1px solid var(--bs-border-color); border-radius: 6px; }}
  #content blockquote {{ border-left: 3px solid var(--bs-primary); padding-left: 1rem; color: var(--bs-secondary-color); }}
  #content .language-mermaid, #content svg {{ display: block; margin: 1rem auto; max-width: 100%; }}
</style>
</head>
<body class="d-flex" style="height:100vh; overflow:hidden;">

<div id="sidebar">
  <div id="sidebar-header">DSI-Wiki</div>
  <div id="controls">
    <select id="instance" class="form-select form-select-sm"></select>
    <input id="search" type="text" class="form-control form-control-sm" placeholder="Search topics...">
    <select id="layer" class="form-select form-select-sm">
      <option value="llm" selected>LLM</option>
      <option value="documentation">Documentation</option>
      <option value="minified">Minified</option>
    </select>
    <div class="form-check form-check-sm ms-1">
      <input class="form-check-input" type="checkbox" id="show-all">
      <label class="form-check-label small text-secondary" for="show-all">Show all</label>
    </div>
  </div>
  <div id="topic-list"></div>
  <div id="sidebar-footer">pinned topics are marked</div>
</div>

<div id="main">
  <div id="placeholder">Select a topic</div>
  <div id="content" style="display:none"></div>
</div>

<script>
mermaid.initialize({{ startOnLoad: false, theme: 'dark' }});

let allTopics = [];
let pinnedTopics = [];
let currentTopic = null;
let showAll = false;
let currentInstance = null;

function displayName(t) {{ return t.replace(/__/g, '/'); }}

function fetchInstances() {{
  fetch('api/instances').then(r => r.json()).then(data => {{
    const sel = document.getElementById('instance');
    sel.innerHTML = '';
    data.instances.forEach(name => {{
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }});
    currentInstance = data.default || data.instances[0];
    sel.value = currentInstance;
    fetchTopics();
  }});
}}

function fetchTopics() {{
  const q = `?instance=${{encodeURIComponent(currentInstance)}}`;
  Promise.all([
    fetch('api/topics' + q).then(r => r.json()),
    fetch('api/all_topics' + q).then(r => r.json())
  ]).then(([pinned, all]) => {{
    pinnedTopics = pinned.topics;
    allTopics = all.topics;
    renderList();
  }});
}}

function renderList() {{
  const q = document.getElementById('search').value.toLowerCase();
  const source = showAll ? allTopics : pinnedTopics;
  const topics = q ? source.filter(t => displayName(t).toLowerCase().includes(q)) : source;

  const ul = document.getElementById('topic-list');
  ul.innerHTML = '';
  topics.forEach(t => {{
    const div = document.createElement('div');
    div.className = 'topic-item' + (t === currentTopic ? ' active' : '');

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = displayName(t);
    name.addEventListener('click', () => loadContent(t));

    const btn = document.createElement('button');
    const isPinned = pinnedTopics.includes(t);
    btn.className = 'pin-btn' + (isPinned ? ' pinned' : '');
    btn.textContent = '\\u{{1F4CC}}';
    btn.title = isPinned ? 'Unpin' : 'Pin';
    btn.addEventListener('click', e => {{ e.stopPropagation(); togglePin(t, !isPinned); }});

    div.appendChild(name);
    div.appendChild(btn);
    ul.appendChild(div);
  }});
}}

function togglePin(topic, pin) {{
  fetch('api/pin', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{instance: currentInstance, topic, pinned: pin}})
  }}).then(r => r.json()).then(data => {{
    pinnedTopics = data.pinned;
    renderList();
  }});
}}

function loadContent(topic) {{
  currentTopic = topic;
  const layer = document.getElementById('layer').value;
  document.querySelectorAll('.topic-item').forEach(el => {{
    el.classList.toggle('active', el.querySelector('.name') && el.querySelector('.name').textContent === displayName(topic));
  }});
  fetch(`api/content?instance=${{encodeURIComponent(currentInstance)}}&topic=${{encodeURIComponent(topic)}}&layer=${{layer}}`)
    .then(r => r.json()).then(data => {{
      document.getElementById('placeholder').style.display = 'none';
      const el = document.getElementById('content');
      el.style.display = 'block';
      el.innerHTML = marked.parse(data.content);
      mermaid.run({{ nodes: el.querySelectorAll('.language-mermaid') }});
    }});
}}

document.getElementById('instance').addEventListener('change', e => {{
  currentInstance = e.target.value;
  currentTopic = null;
  document.getElementById('placeholder').style.display = 'block';
  document.getElementById('content').style.display = 'none';
  fetchTopics();
}});
document.getElementById('search').addEventListener('input', renderList);
document.getElementById('layer').addEventListener('change', () => {{
  if (currentTopic) loadContent(currentTopic);
}});
document.getElementById('show-all').addEventListener('change', e => {{
  showAll = e.target.checked;
  renderList();
}});

fetchInstances();
</script>
</body>
</html>
"""


async def index(request):
    return HTMLResponse(HTML)


async def api_instances(request):
    instances = load_instances(request.app.state.scan_dir)
    return JSONResponse({"instances": sorted(instances.keys()), "default": _default_instance(instances)})


async def api_topics(request):
    base_dir, name, instances = _base_dir(request)
    if base_dir is None:
        return JSONResponse({"error": "unknown instance", "instances": sorted(instances.keys())}, status_code=400)
    return JSONResponse({"topics": list_topics(base_dir)})


async def api_all_topics(request):
    base_dir, name, instances = _base_dir(request)
    if base_dir is None:
        return JSONResponse({"error": "unknown instance", "instances": sorted(instances.keys())}, status_code=400)
    return JSONResponse({"topics": list_all_topics(base_dir)})


async def api_content(request):
    base_dir, name, instances = _base_dir(request)
    if base_dir is None:
        return JSONResponse({"error": "unknown instance", "instances": sorted(instances.keys())}, status_code=400)
    topic = request.query_params.get("topic", "")
    layer = request.query_params.get("layer", "llm")
    if layer not in LAYERS:
        layer = "llm"
    content = get_content(base_dir, layer, topic)
    if content is None:
        content = f"# Not found\n\n`{layer}/{topic}.md` does not exist."
    return JSONResponse({"content": content})


async def api_pin(request):
    body = await request.json()
    instances = load_instances(request.app.state.scan_dir)
    base_dir = instances.get(body.get("instance"), {}).get("base_dir")
    if base_dir is None:
        return JSONResponse({"error": "unknown instance"}, status_code=400)
    topic = body.get("topic", "")
    pin = body.get("pinned", True)
    current = load_visible_topics(base_dir) or []
    if pin and topic not in current:
        current.append(topic)
    elif not pin and topic in current:
        current.remove(topic)
    save_visible_topics(base_dir, current)
    return JSONResponse({"pinned": sorted(current)})


def build_app(scan_dir):
    app = Starlette(routes=[
        Route("/", index),
        Route("/api/instances", api_instances),
        Route("/api/topics", api_topics),
        Route("/api/all_topics", api_all_topics),
        Route("/api/content", api_content),
        Route("/api/pin", api_pin, methods=["POST"]),
    ])
    app.state.scan_dir = scan_dir
    return app
