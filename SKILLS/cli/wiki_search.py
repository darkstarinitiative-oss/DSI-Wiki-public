#!/usr/bin/env python3
"""wiki_search.py — search DSI-Wiki content and print matching topics."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from gateway.api_app import load_instances, search


def main():
    parser = argparse.ArgumentParser(description="Search DSI-Wiki content.")
    parser.add_argument("query")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--layer", default="all")
    args = parser.parse_args()

    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        print(f"instance not found: {args.instance}", file=sys.stderr)
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    results = search(base_dir, args.query, args.layer)
    if not results:
        sys.exit(1)
    query_lower = args.query.lower()
    for r in results:
        # search() already centers r["excerpt"] on the match within the full
        # document; re-center the shorter terminal preview within that excerpt
        # too, or a match near the end of the (already offset) excerpt gets cut
        # off by a naive [:200] here.
        idx = r["excerpt"].lower().find(query_lower)
        start = max(0, idx - 60) if idx != -1 else 0
        excerpt = " ".join(r["excerpt"][start:start + 200].split())
        print(f"{r['layer']}/{r['topic']}: {excerpt}")


if __name__ == "__main__":
    main()
