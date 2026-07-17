#!/usr/bin/env python3
import os
import json
import socketserver
import http.server
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.expanduser("~/LLM-Wiki-BASE")
VISIBLE_TOPICS_CONFIG = os.path.join(BASE_DIR, "config/visible_topics.json")
PORT = 9120
LAYERS = ("documentation", "llm", "minified")


def load_visible_topics():
    if os.path.exists(VISIBLE_TOPICS_CONFIG):
        with open(VISIBLE_TOPICS_CONFIG, "r") as f:
            return json.load(f)
    return None


def save_visible_topics(topics):
    os.makedirs(os.path.dirname(VISIBLE_TOPICS_CONFIG), exist_ok=True)
    with open(VISIBLE_TOPICS_CONFIG, "w") as f:
        json.dump(sorted(topics), f, ensure_ascii=False, indent=2)


def list_all_topics():
    layer_dir = os.path.join(BASE_DIR, "llm")
    if not os.path.isdir(layer_dir):
        return []
    return sorted(f[:-3] for f in os.listdir(layer_dir) if f.endswith(".md") and f != "log.md")


def list_topics():
    visible = load_visible_topics()
    if visible is not None:
        return visible
    return list_all_topics()


def get_content(topic, layer):
    if layer not in LAYERS:
        layer = "llm"
    path = os.path.join(BASE_DIR, layer, f"{topic}.md")
    if not os.path.exists(path):
        return f"# Not found\n\n`{path}` bulunamadı."
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


THEME_URL = "https://bootswatch.com/5/cyborg/bootstrap.min.css"

HTML = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM Wiki</title>
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
  /* markdown content tweaks */
  #content table {{ width: 100%; }}
  #content pre {{ border: 1px solid var(--bs-border-color); border-radius: 6px; }}
  #content blockquote {{ border-left: 3px solid var(--bs-primary); padding-left: 1rem; color: var(--bs-secondary-color); }}
  /* mermaid diagram centering */
  #content .language-mermaid, #content svg {{ display: block; margin: 1rem auto; max-width: 100%; }}
</style>
</head>
<body class="d-flex" style="height:100vh; overflow:hidden;">

<div id="sidebar">
  <div id="sidebar-header">📚 LLM Wiki</div>
  <div id="controls">
    <input id="search" type="text" class="form-control form-control-sm" placeholder="Konu ara...">
    <select id="layer" class="form-select form-select-sm">
      <option value="llm" selected>LLM</option>
      <option value="documentation">Documentation</option>
      <option value="minified">Minified</option>
    </select>
    <div class="form-check form-check-sm ms-1">
      <input class="form-check-input" type="checkbox" id="show-all">
      <label class="form-check-label small text-secondary" for="show-all">Tümünü göster</label>
    </div>
    <select id="theme-select" class="form-select form-select-sm">
      <optgroup label="── Dark ──">
        <option value="cyborg" selected>Cyborg</option>
        <option value="darkly">Darkly</option>
        <option value="slate">Slate</option>
        <option value="superhero">Superhero</option>
        <option value="vapor">Vapor</option>
        <option value="solar">Solar</option>
      </optgroup>
      <optgroup label="── Light ──">
        <option value="flatly">Flatly</option>
        <option value="lux">Lux</option>
        <option value="minty">Minty</option>
        <option value="journal">Journal</option>
        <option value="litera">Litera</option>
        <option value="pulse">Pulse</option>
        <option value="sandstone">Sandstone</option>
        <option value="united">United</option>
        <option value="yeti">Yeti</option>
        <option value="zephyr">Zephyr</option>
      </optgroup>
    </select>
  </div>
  <div id="topic-list"></div>
  <div id="sidebar-footer">📌 = sabitlenmiş konu</div>
</div>

<div id="main">
  <div id="placeholder">Bir konu seçin</div>
  <div id="content" style="display:none"></div>
</div>

<script>
let allTopics = [];
let pinnedTopics = [];
let currentTopic = null;
let showAll = false;

const DARK_THEMES = ['cyborg','darkly','slate','superhero','vapor','solar'];

function applyTheme(name) {{
  document.getElementById('theme-link').href = `https://bootswatch.com/5/${{name}}/bootstrap.min.css`;
  const isDark = DARK_THEMES.includes(name);
  document.documentElement.setAttribute('data-bs-theme', isDark ? 'dark' : 'light');
  mermaid.initialize({{ startOnLoad: false, theme: isDark ? 'dark' : 'default' }});
  localStorage.setItem('wiki-theme', name);
}}

document.getElementById('theme-select').addEventListener('change', e => applyTheme(e.target.value));

const savedTheme = localStorage.getItem('wiki-theme') || 'cyborg';
document.getElementById('theme-select').value = savedTheme;
applyTheme(savedTheme);


function displayName(t) {{
  return t.replace(/__/g, '/');
}}

function fetchTopics() {{
  Promise.all([
    fetch('/api/topics').then(r => r.json()),
    fetch('/api/all_topics').then(r => r.json())
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
    btn.textContent = '📌';
    btn.title = isPinned ? 'Sabitlemeyi kaldır' : 'Sabitle';
    btn.addEventListener('click', e => {{ e.stopPropagation(); togglePin(t, !isPinned); }});

    div.appendChild(name);
    div.appendChild(btn);
    ul.appendChild(div);
  }});
}}

function togglePin(topic, pin) {{
  fetch('/api/pin', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{topic, pinned: pin}})
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
  fetch(`/api/content?topic=${{encodeURIComponent(topic)}}&layer=${{layer}}`)
    .then(r => r.json()).then(data => {{
      document.getElementById('placeholder').style.display = 'none';
      const el = document.getElementById('content');
      el.style.display = 'block';
      el.innerHTML = marked.parse(data.content);
      mermaid.run({{ nodes: el.querySelectorAll('.language-mermaid') }});
    }});
}}

document.getElementById('search').addEventListener('input', renderList);
document.getElementById('layer').addEventListener('change', () => {{
  if (currentTopic) loadContent(currentTopic);
}});
document.getElementById('show-all').addEventListener('change', e => {{
  showAll = e.target.checked;
  renderList();
}});

fetchTopics();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/topics":
            self._json({"topics": list_topics()})
        elif parsed.path == "/api/all_topics":
            self._json({"topics": list_all_topics()})
        elif parsed.path == "/api/content":
            topic = qs.get("topic", [""])[0]
            layer = qs.get("layer", ["llm"])[0]
            self._json({"content": get_content(topic, layer)})
        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/pin":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            topic = body.get("topic", "")
            pin = body.get("pinned", True)

            current = load_visible_topics() or []
            if pin and topic not in current:
                current.append(topic)
            elif not pin and topic in current:
                current.remove(topic)
            save_visible_topics(current)
            self._json({"pinned": sorted(current)})
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"LLM Wiki running on http://0.0.0.0:{PORT}")
        httpd.serve_forever()
