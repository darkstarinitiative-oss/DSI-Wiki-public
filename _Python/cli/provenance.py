#!/usr/bin/env python3
"""provenance.py — trace where a factual claim appears across a DSI-Wiki instance.

Given a claim substring, searches every layer (raw/documentation/llm/minified/
changelog/devlog) plus archive and fact-check backup dirs under the instance's
base_dir, and prints each hit oldest-first (by file mtime) so you can see where
a claim first entered the wiki and how it propagated across layers.

Reuses the wiki's OWN loader: load_instances() from
_Python/HTTPService/api_app.py, scan_dir from its HTTP config. No hardcoded dirs.
Exit 0 if any hit found, 1 if none.
"""
import argparse
import json
import os
import sys
from datetime import datetime

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_PYTHON_DIR = os.path.dirname(_CLI_DIR)
_REPO_ROOT = os.path.dirname(_PYTHON_DIR)
_HTTP_DIR = os.path.join(_PYTHON_DIR, "HTTPService")
sys.path.insert(0, _HTTP_DIR)

import api_app  # noqa: E402

_HTTP_CONFIG = os.path.join(_HTTP_DIR, "DSI-Wiki-HTTP-Config.json")


def _load_scan_dir():
    try:
        with open(_HTTP_CONFIG, encoding="utf-8") as f:
            scan_dir = json.load(f).get("scan_dir")
        if scan_dir and os.path.isdir(scan_dir):
            return scan_dir
    except (OSError, json.JSONDecodeError):
        pass
    return os.path.join(_REPO_ROOT, "Instances")


def _search_dirs(base_dir):
    """Layer dirs (from api_app.LAYERS) + archive + fact-check backup dirs."""
    dirs = [os.path.join(base_dir, layer) for layer in api_app.LAYERS]
    dirs.append(os.path.join(base_dir, "_archive"))
    try:
        for name in os.listdir(base_dir):
            full = os.path.join(base_dir, name)
            if os.path.isdir(full) and name.startswith(("_factcheck_backup_", "_archive")):
                dirs.append(full)
    except OSError:
        pass
    # de-dup while preserving order
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Trace where a claim appears across a DSI-Wiki instance's layers.")
    parser.add_argument("--instance", default="Cain-the-elder", help="wiki instance name")
    parser.add_argument("claim", help="claim substring to search for (case-insensitive)")
    parser.add_argument("--topic", help="restrict to files whose topic name contains this")
    args = parser.parse_args()

    scan_dir = _load_scan_dir()
    instances = api_app.load_instances(scan_dir)
    if args.instance not in instances:
        print(f"error: instance '{args.instance}' not found in {scan_dir} "
              f"(have: {', '.join(sorted(instances)) or 'none'})", file=sys.stderr)
        return 1
    base_dir = instances[args.instance]["base_dir"]

    claim_lower = args.claim.lower()
    topic_lower = args.topic.lower() if args.topic else None

    hits = []  # (mtime, relpath, lineno, line)
    for d in _search_dirs(base_dir):
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                if topic_lower and topic_lower not in fname.lower():
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for num, line in enumerate(f, 1):
                            if claim_lower in line.lower():
                                mtime = os.path.getmtime(fpath)
                                hits.append((mtime, os.path.relpath(fpath, base_dir),
                                             num, line.strip()))
                except OSError as e:
                    print(f"warning: cannot read {fpath}: {e}", file=sys.stderr)

    hits.sort(key=lambda h: h[0])  # oldest first
    for mtime, rel, num, line in hits:
        date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{date} | {rel}:{num} | {line}")

    if not hits:
        print(f"no occurrences of {args.claim!r} found in instance '{args.instance}'",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
