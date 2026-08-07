#!/usr/bin/env python3
"""DSI-Wiki-UI-Server.py — browsable wiki UI, Starlette ASGI app, instance-aware.
Mounted at /http by the top-level gateway (DSI-Wiki-HTTP-Server.py). Replaces the old
single-instance socketserver-based UI, which hardcoded ~/LLM-Wiki-BASE and port 9120
(already occupied by the unrelated legacy llm-wiki-ui.service).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

# service-widget.js: one shared file, bind-mounted here and into DSI-BEHOLDER (which is where
# it's actually authored) rather than duplicated into this repo -- see docker-compose.yml.
SHARED_WIDGETS_DIR = os.environ.get("SHARED_WIDGETS_DIR", "/data/shared-widgets")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gateway"))
from api_app import load_instances, get_content  # noqa: E402

LAYERS = ("documentation", "llm", "minified")

# --- /dashboard support (health + create-topic widgets) ---------------------
STATUS_PATH = os.environ.get(
    "WIKI_STATUS_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "STATUS.json"),
)
RAW_DIR = os.environ.get("LLM_WIKI_RAW_DIR")
# Ollama's own chat endpoint URL, minus the /api/chat suffix, to reach /api/ps.
_OLLAMA_CHAT_URL = os.environ.get("LLM_WIKI_OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
OLLAMA_BASE = _OLLAMA_CHAT_URL.rsplit("/api/", 1)[0]
TOPIC_RE = re.compile(r"^(MAIN|SUB|INDEP)_[A-Za-z0-9_-]+$")
# DSI-BEHOLDER runs natively on the host (not Docker) -- host.docker.internal is how this
# container reaches it, same pattern as OLLAMA_BASE above.
BEHOLDER_BASE = os.environ.get("BEHOLDER_URL", "http://host.docker.internal:9130")


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


INFO_VIEWER_HTML = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DSI Info API — viewer</title>
<link rel="stylesheet" href="{THEME_URL}">
<style>
  body {{ padding: 2rem; }}
  .badge-ok {{ background: var(--bs-success); }}
  .badge-warning {{ background: var(--bs-warning); color: #000; }}
  .badge-error {{ background: var(--bs-danger); }}
  .badge-info, .badge-unknown {{ background: var(--bs-secondary); }}
  .feed-item {{ border-left: 3px solid var(--bs-border-color); padding-left: 0.75rem; margin-bottom: 0.75rem; }}
</style>
</head>
<body>
<div class="container" style="max-width: 800px;">
  <h3>DSI Info API — generic viewer <small class="text-secondary fs-6">(conformance test page)</small></h3>
  <p class="text-secondary" style="font-size:0.85rem;">
    Points at any URL implementing the DSI Info API Standard (see this repo's
    <code>DOCS/info-api-standard.md</code>) and renders it generically -- not specific to this
    project. The target must allow this page to fetch it (same-origin, or CORS-enabled).
  </p>
  <form id="url-form" class="d-flex gap-2 mb-4">
    <input id="url-input" class="form-control form-control-sm" placeholder="http://host:port/api/info" value="/api/info">
    <button type="submit" class="btn btn-primary btn-sm">Fetch</button>
  </form>
  <div id="error" class="alert alert-danger py-1 px-2" style="display:none;"></div>
  <div id="result" style="display:none;">
    <h5><span id="r-service"></span> <small class="text-secondary" id="r-version"></small> <span id="r-status" class="badge"></span></h5>
    <p id="r-note" class="text-secondary"></p>
    <h6 class="mt-3">Services</h6>
    <div id="r-services" class="mb-3"></div>
    <h6>Feed</h6>
    <div id="r-feed"></div>
  </div>
</div>
<script>
function badge(status) {{
  return `<span class="badge badge-${{status || 'unknown'}}">${{status || 'unknown'}}</span>`;
}}
function timeAgo(iso) {{
  if (!iso) return 'never';
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return secs + 's ago';
  if (secs < 3600) return Math.round(secs / 60) + 'm ago';
  return Math.round(secs / 3600) + 'h ago';
}}
function render(data) {{
  document.getElementById('r-service').textContent = data.service || '(unnamed service)';
  document.getElementById('r-version').textContent = data.version || '';
  const statusEl = document.getElementById('r-status');
  statusEl.className = 'badge badge-' + (data.status || 'unknown');
  statusEl.textContent = data.status || 'unknown';
  document.getElementById('r-note').textContent = data.status_note || '';
  document.getElementById('r-services').innerHTML = (data.services || []).map(s =>
    `<div>${{badge(s.status)}} <strong>${{s.name}}</strong> <span class="text-secondary">-- heartbeat: ${{timeAgo(s.last_heartbeat)}}</span></div>`
  ).join('') || '<div class="text-secondary">none reported</div>';
  document.getElementById('r-feed').innerHTML = (data.feed || []).slice(0, 10).map(f =>
    `<div class="feed-item">${{badge(f.icon)}} <strong>${{f.title}}</strong> <span class="text-secondary">${{timeAgo(f.ts)}}</span><br><span class="text-secondary">${{f.note || ''}}</span></div>`
  ).join('') || '<div class="text-secondary">empty</div>';
  document.getElementById('result').style.display = 'block';
}}
document.getElementById('url-form').addEventListener('submit', e => {{
  e.preventDefault();
  const url = document.getElementById('url-input').value.trim();
  const errEl = document.getElementById('error');
  errEl.style.display = 'none';
  document.getElementById('result').style.display = 'none';
  fetch(url).then(r => {{
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }}).then(render).catch(e => {{
    errEl.textContent = 'Fetch failed: ' + e.message + ' (CORS, wrong URL, or target unreachable)';
    errEl.style.display = 'block';
  }});
}});
document.getElementById('url-form').dispatchEvent(new Event('submit'));
</script>
</body>
</html>
"""


DASHBOARD_HTML = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DSI-Wiki Dashboard</title>
<link rel="stylesheet" href="{THEME_URL}">
<style>
  body {{ padding: 2rem; }}
  .card {{ margin-bottom: 1.5rem; }}
  .stat-label {{ color: var(--bs-secondary-color); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  .stat-value {{ font-size: 1.05rem; }}
  #topic-table-wrap {{ max-height: 320px; overflow-y: auto; }}
  #topic-list-w2 tr td, #topic-list-w2 tr th {{ font-size: 0.85rem; }}
</style>
<!-- Shared with DSI-BEHOLDER's own dashboard -- see /BIG/_COMMON/dsi-widgets/service-widget.js.
     Restart/Stop route through this gateway's own /api/controls|action_status|action/* (see
     api_controls_proxy et al.), which proxy server-to-server to DSI-BEHOLDER -- no CORS,
     the browser stays same-origin the whole time. -->
<script src="static/service-widget.js"></script>
<!-- Same shared-widgets mount, see /BIG/_COMMON/dsi-widgets/feed-widget.js. Single source today
     (this project's own STATUS.json feed[]) but built to merge N sources' feed[] into one
     time-sorted list, ready for whenever this page (or Beholder's) pulls in more than one. -->
<script src="static/feed-widget.js"></script>
</head>
<body>
<div class="container" style="max-width: 900px;">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h3 class="mb-0">DSI-Wiki Dashboard <small class="text-secondary fs-6">(test page)</small></h3>
    <div style="min-width: 220px;">
      <select id="instance" class="form-select form-select-sm"></select>
    </div>
  </div>

  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      Health
      <span id="health-refreshed" class="text-secondary" style="font-size:0.75rem;"></span>
    </div>
    <div class="card-body">
      <div class="row row-cols-2 row-cols-md-4 g-3" id="health-grid"></div>
      <hr>
      <div class="stat-label">Services</div>
      <div id="services-widget-slot" class="stat-value"></div>
      <hr>
      <div class="stat-label">Feed</div>
      <div id="feed-widget-slot" class="stat-value"></div>
      <hr>
      <div class="stat-label">GPU (Ollama /api/ps)</div>
      <div id="gpu-info" class="stat-value">loading...</div>
    </div>
  </div>

  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <span>Topics</span>
      <div class="d-flex align-items-center gap-2">
        <select id="topic-type-filter" class="form-select form-select-sm" style="width:auto;">
          <option value="ALL">All types</option>
          <option value="MAIN">MAIN</option>
          <option value="SUB">SUB</option>
          <option value="INDEP">INDEP</option>
        </select>
        <select id="topic-instance-select" class="form-select form-select-sm" style="width:auto;"></select>
        <button id="topic-add-toggle" type="button" class="btn btn-primary btn-sm">+</button>
      </div>
    </div>
    <div class="card-body">
      <div id="create-popup" class="border rounded p-2 mb-3" style="display:none;">
        <form id="create-form" class="row g-2 align-items-start">
          <div class="col-12 col-md-4">
            <input id="new-topic-name" class="form-control form-control-sm" placeholder="MAIN_YourTopic / SUB_Main_Sub / INDEP_Topic" required>
          </div>
          <div class="col-12 col-md-6">
            <textarea id="new-topic-content" class="form-control form-control-sm" rows="2" placeholder="raw note content (optional)"></textarea>
          </div>
          <div class="col-12 col-md-2">
            <button type="submit" class="btn btn-primary btn-sm w-100">Add topic</button>
          </div>
        </form>
        <div id="create-result" class="mt-2"></div>
      </div>
      <div id="topic-table-wrap">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr><th>Konu</th><th>Tür</th><th class="text-end">Actions</th></tr>
          </thead>
          <tbody id="topic-list-w2"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
let currentInstance = null;

function fetchInstances() {{
  fetch('api/instances').then(r => r.json()).then(data => {{
    const sel = document.getElementById('instance');
    const topicSel = document.getElementById('topic-instance-select');
    sel.innerHTML = '';
    topicSel.innerHTML = '';
    data.instances.forEach(name => {{
      [sel, topicSel].forEach(s => {{
        const opt = document.createElement('option');
        opt.value = name; opt.textContent = name;
        s.appendChild(opt);
      }});
    }});
    currentInstance = data.default || data.instances[0];
    sel.value = currentInstance;
    topicSel.value = currentInstance;
    refreshTopics();
  }});
}}

function statCol(label, value) {{
  return `<div class="col"><div class="stat-label">${{label}}</div><div class="stat-value">${{value}}</div></div>`;
}}

function timeAgo(iso) {{
  if (!iso) return 'never';
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return secs + 's ago';
  if (secs < 3600) return Math.round(secs / 60) + 'm ago';
  return Math.round(secs / 3600) + 'h ago';
}}

function refreshHealth() {{
  fetch('api/health').then(r => r.json()).then(data => {{
    const s = data.status || {{}};
    const li = s.last_ingest || {{}};
    const grid = document.getElementById('health-grid');
    grid.innerHTML = [
      statCol('Ingest checked', timeAgo(s.checked_at)),
      statCol('Raw queue', data.raw_queue_count === null ? 'n/a' : data.raw_queue_count + ' file(s)'),
      statCol('Ingest status', s.status === 'ok' ? '<span class="badge text-bg-success">ok</span>' : (s.status ? `<span class="badge text-bg-danger">${{s.status}}</span>` : 'n/a')),
      statCol('Git commit', s.git_commit || 'n/a'),
      statCol('Last ingest topic', li.topic || 'n/a'),
      statCol('Last ingest result', li.ok === true ? '<span class="badge text-bg-success">ok</span>' : (li.ok === false ? '<span class="badge text-bg-danger">failed</span>' : 'n/a')),
      statCol('Last ingest finished', timeAgo(li.finished_at)),
      statCol('Last ingest duration', li.duration_seconds != null ? li.duration_seconds + 's' : 'n/a'),
    ].join('');
    const svcSlot = document.getElementById('services-widget-slot');
    svcSlot.innerHTML = '';
    if (window.DSIServiceWidget) {{
      // Enriched list (self-reported process status + container-level docker status, two
      // separate rows each) comes from DSI-BEHOLDER via this gateway's own /api/services proxy
      // -- not the bare s.services above, which only has the self-report. '/http' -- same-
      // origin, /api/controls|action_status|action/* also proxy server-to-server. No CORS.
      fetch('api/services').then(r => r.json()).then(svcData => {{
        DSIServiceWidget.renderProject(svcSlot, 'DSI-WIKI', svcData.services || [], {{
          controlsBaseUrl: '/http',
        }});
      }});
    }}
    const feedSlot = document.getElementById('feed-widget-slot');
    if (window.DSIFeedWidget) {{
      DSIFeedWidget.renderFeeds(feedSlot, [{{ project: 'DSI-WIKI', feed: s.feed || [] }}], {{ limit: 10 }});
    }}
    const gpu = data.gpu || {{}};
    const gpuEl = document.getElementById('gpu-info');
    if (!gpu.reachable) {{
      gpuEl.innerHTML = '<span class="badge text-bg-secondary">Ollama unreachable</span> ' + (gpu.error || '');
    }} else if (!gpu.models || !gpu.models.length) {{
      gpuEl.innerHTML = '<span class="badge text-bg-secondary">no model currently loaded</span>';
    }} else {{
      gpuEl.innerHTML = gpu.models.map(m =>
        `<span class="badge text-bg-info me-2">${{m.name}}: ${{m.gpu_percent == null ? '?' : m.gpu_percent + '%'}} GPU</span>`
      ).join('');
    }}
    document.getElementById('health-refreshed').textContent = 'refreshed ' + new Date().toLocaleTimeString();
    scheduleNextRefresh(s.refresh_interval_seconds);
  }}).catch(() => scheduleNextRefresh());
}}

let refreshTimer = null;
function scheduleNextRefresh(seconds) {{
  // Interval comes from STATUS.json (refresh_interval_seconds, default 60s, see
  // TOOLS/write_ingest_status.py) so the poll cadence can change without touching this page --
  // self-rescheduling via setTimeout (not a fixed setInterval) so a slow request can't stack
  // up a backlog of overlapping fetches.
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refreshHealth, (seconds || 60) * 1000);
}}

let allTopics = [];

function topicType(t) {{
  if (t.startsWith('MAIN_')) return 'MAIN';
  if (t.startsWith('SUB_')) return 'SUB';
  if (t.startsWith('INDEP_')) return 'INDEP';
  return 'OTHER';
}}

function renderTopicRows() {{
  const filterType = document.getElementById('topic-type-filter').value;
  const el = document.getElementById('topic-list-w2');
  const rows = allTopics
    .filter(t => filterType === 'ALL' || topicType(t) === filterType)
    .sort();
  el.innerHTML = rows.length ? rows.map(t => `
    <tr data-topic="${{t}}">
      <td>${{t}}</td>
      <td><span class="badge text-bg-secondary">${{topicType(t)}}</span></td>
      <td class="text-end">
        <button type="button" class="btn btn-outline-danger btn-sm topic-delete-btn">sil</button>
        <button type="button" class="btn btn-outline-warning btn-sm topic-factcheck-btn">fact-check</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="3" class="text-secondary small">No topics for this filter.</td></tr>';
}}

function refreshTopics() {{
  fetch(`api/all_topics?instance=${{encodeURIComponent(currentInstance)}}`).then(r => r.json()).then(data => {{
    allTopics = data.topics || [];
    renderTopicRows();
  }});
}}

document.getElementById('instance').addEventListener('change', e => {{
  currentInstance = e.target.value;
  document.getElementById('topic-instance-select').value = currentInstance;
  refreshTopics();
}});

document.getElementById('topic-instance-select').addEventListener('change', e => {{
  currentInstance = e.target.value;
  document.getElementById('instance').value = currentInstance;
  refreshHealth();
  refreshTopics();
}});

document.getElementById('topic-type-filter').addEventListener('change', renderTopicRows);

document.getElementById('topic-add-toggle').addEventListener('click', () => {{
  const popup = document.getElementById('create-popup');
  popup.style.display = popup.style.display === 'none' ? 'block' : 'none';
}});

document.getElementById('topic-list-w2').addEventListener('click', e => {{
  const row = e.target.closest('tr[data-topic]');
  if (!row) return;
  const topic = row.dataset.topic;
  if (e.target.classList.contains('topic-delete-btn')) {{
    if (!confirm(`Delete ${{topic}} across all layers? This cannot be undone.`)) return;
    e.target.disabled = true;
    e.target.textContent = 'wait...';
    fetch('api/delete_topic_request', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{topic}})
    }}).then(() => {{
      row.querySelectorAll('button').forEach(b => b.disabled = true);
      row.style.opacity = '0.5';
    }});
  }} else if (e.target.classList.contains('topic-factcheck-btn')) {{
    if (!confirm(`Queue a fact-check for ${{topic}}?`)) return;
    e.target.disabled = true;
    e.target.textContent = 'wait...';
    fetch('api/factcheck_request', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{topic}})
    }}).then(() => {{
      e.target.textContent = 'queued';
    }});
  }}
}});

document.getElementById('create-form').addEventListener('submit', e => {{
  e.preventDefault();
  const topic = document.getElementById('new-topic-name').value.trim();
  const content = document.getElementById('new-topic-content').value;
  const resultEl = document.getElementById('create-result');
  resultEl.innerHTML = '';
  fetch('api/create_topic', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{topic, content}})
  }}).then(r => r.json().then(data => ({{ok: r.ok, data}}))).then(({{ok, data}}) => {{
    if (ok) {{
      resultEl.innerHTML = `<div class="alert alert-success py-1 px-2 mb-0">Created ${{data.created}}.md in raw/ -- will appear here once ingest picks it up.</div>`;
      document.getElementById('new-topic-name').value = '';
      document.getElementById('new-topic-content').value = '';
    }} else {{
      resultEl.innerHTML = `<div class="alert alert-danger py-1 px-2 mb-0">${{data.error}}</div>`;
    }}
  }});
}});

fetchInstances();
refreshHealth();
</script>
</body>
</html>
"""


async def index(request):
    return HTMLResponse(HTML)


async def dashboard(request):
    return HTMLResponse(DASHBOARD_HTML)


async def info_viewer(request):
    return HTMLResponse(INFO_VIEWER_HTML)


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


def _read_status():
    if not os.path.isfile(STATUS_PATH):
        status = {"error": "STATUS.json not yet written (ingest daemon not running?)", "services": []}
    else:
        try:
            with open(STATUS_PATH, encoding="utf-8") as f:
                status = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            status = {"error": str(e), "services": []}
    # STATUS.json is the ingest daemon's own self-report -- it has no idea the Gateway
    # process exists. Append the Gateway's own live-computed entry the same way
    # api_app.py's info_endpoint does (it's "ok" with a null heartbeat whenever it's
    # answering a request at all, since it has no poll loop of its own).
    status["services"] = list(status.get("services") or []) + [
        {"name": "DSI-Wiki Gateway", "status": "ok", "last_heartbeat": None},
    ]
    return status


def _raw_queue_count():
    if not RAW_DIR or not os.path.isdir(RAW_DIR):
        return None
    return len([f for f in os.listdir(RAW_DIR) if f.endswith(".md")])


def _gpu_status():
    """Live snapshot from Ollama's own /api/ps -- loaded models and how much of
    each sits in VRAM vs. spilled to CPU. Best-effort: Ollama being unreachable
    is a normal, reportable state here, not an error worth failing the request."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/ps", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return {"reachable": False, "error": str(e)}
    models = []
    for m in data.get("models", []):
        size = m.get("size") or 0
        size_vram = m.get("size_vram") or 0
        models.append({
            "name": m.get("name"),
            "gpu_percent": round(size_vram / size * 100) if size else None,
            "expires_at": m.get("expires_at"),
        })
    return {"reachable": True, "models": models}


async def api_health(request):
    return JSONResponse({
        "status": _read_status(),
        "raw_queue_count": _raw_queue_count(),
        "gpu": _gpu_status(),
    })


def _beholder_proxy_get(path):
    """Server-to-server call to DSI-BEHOLDER -- no CORS needed anywhere, the browser only ever
    talks to this same-origin gateway. Beholder unreachable is a normal, reportable state, not
    a 500 (same spirit as _gpu_status above)."""
    try:
        with urllib.request.urlopen(f"{BEHOLDER_BASE}{path}", timeout=15) as resp:
            return JSONResponse(json.loads(resp.read().decode("utf-8")))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return JSONResponse({"error": f"DSI-BEHOLDER unreachable: {e}"}, status_code=502)


async def api_services_proxy(request):
    """Enriched services list for THIS project (self-reported process status, e.g. "DSI-Wiki
    Gateway", PLUS container-level docker status, e.g. "DSI-WIKI.docker.gateway" -- two
    independent signals, see DSI-BEHOLDER/checks.py's _docker_container_status) -- proxied from
    DSI-BEHOLDER's /api/watchlist rather than this gateway's own bare /api/health, since only
    Beholder (native, docker CLI on PATH) can see container-level status."""
    try:
        with urllib.request.urlopen(f"{BEHOLDER_BASE}/api/watchlist", timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return JSONResponse({"services": [], "error": f"DSI-BEHOLDER unreachable: {e}"}, status_code=502)
    for t in data.get("targets", []):
        if t.get("name") == "DSI-WIKI":
            return JSONResponse({"services": (t.get("info") or {}).get("services", [])})
    return JSONResponse({"services": [], "error": "DSI-WIKI not found in DSI-BEHOLDER's watchlist"})


async def api_controls_proxy(request):
    return _beholder_proxy_get("/api/controls")


async def api_action_status_proxy(request):
    return _beholder_proxy_get("/api/action_status")


async def api_action_proxy(request):
    target, service, action = request.path_params["target"], request.path_params["service"], request.path_params["action"]
    url = f"{BEHOLDER_BASE}/api/action/{urllib.parse.quote(target, safe='')}/{urllib.parse.quote(service, safe='')}/{action}"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=35) as resp:
            return JSONResponse(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        return JSONResponse(json.loads(e.read().decode("utf-8")), status_code=e.code)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return JSONResponse({"error": f"DSI-BEHOLDER unreachable: {e}"}, status_code=502)


async def api_create_topic(request):
    if not RAW_DIR:
        return JSONResponse({"error": "LLM_WIKI_RAW_DIR not configured on this gateway"}, status_code=500)
    body = await request.json()
    topic = (body.get("topic") or "").strip()
    content = body.get("content") or ""
    if not TOPIC_RE.match(topic):
        return JSONResponse(
            {"error": "topic must match MAIN_<slug> / SUB_<main>_<slug> / INDEP_<slug> (letters, digits, _, -)"},
            status_code=400,
        )
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{topic}.md")
    if os.path.exists(path):
        return JSONResponse({"error": f"{topic}.md already exists in raw/ (still pending, or a name collision)"}, status_code=409)
    body_text = content.strip() or f"# {topic}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body_text)
    return JSONResponse({"created": topic, "path": path})


def _write_ops_request(op: str, topic: str):
    """Queues a request for TOOLS/process_topic_ops.py (host cron, every minute) --
    same fire-and-forget shape as api_create_topic above, just a different watched
    subdirectory. This gateway never touches base_dir directly (its mount is
    read-only) and never runs the delete/fact-check itself -- see that script's
    header for why it's a separate host-native cron job, not folded into this
    request handler or into the ingest daemon's own loop."""
    if not RAW_DIR:
        return JSONResponse({"error": "LLM_WIKI_RAW_DIR not configured on this gateway"}, status_code=500)
    if not TOPIC_RE.match(topic):
        return JSONResponse({"error": "invalid topic name"}, status_code=400)
    ops_dir = os.path.join(RAW_DIR, "_ops")
    os.makedirs(ops_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    path = os.path.join(ops_dir, f"{op}__{topic}__{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"op": op, "topic": topic}, f)
    return JSONResponse({"queued": op, "topic": topic})


async def api_delete_topic_request(request):
    body = await request.json()
    return _write_ops_request("delete", (body.get("topic") or "").strip())


async def api_factcheck_request(request):
    body = await request.json()
    return _write_ops_request("factcheck", (body.get("topic") or "").strip())


def build_app(scan_dir):
    app = Starlette(routes=[
        Route("/", index),
        Route("/dashboard", dashboard),
        Route("/info-viewer", info_viewer),
        Route("/api/instances", api_instances),
        Route("/api/topics", api_topics),
        Route("/api/all_topics", api_all_topics),
        Route("/api/content", api_content),
        Route("/api/pin", api_pin, methods=["POST"]),
        Route("/api/health", api_health),
        Route("/api/create_topic", api_create_topic, methods=["POST"]),
        Route("/api/delete_topic_request", api_delete_topic_request, methods=["POST"]),
        Route("/api/factcheck_request", api_factcheck_request, methods=["POST"]),
        Route("/api/services", api_services_proxy),
        Route("/api/controls", api_controls_proxy),
        Route("/api/action_status", api_action_status_proxy),
        Route("/api/action/{target}/{service}/{action}", api_action_proxy, methods=["POST"]),
    ])
    if os.path.isdir(SHARED_WIDGETS_DIR):
        app.routes.append(Mount("/static", StaticFiles(directory=SHARED_WIDGETS_DIR), name="static"))
    app.state.scan_dir = scan_dir
    return app
