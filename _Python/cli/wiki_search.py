#!/usr/bin/env python3
"""wiki_search.py — search DSI-Wiki content and print matching topics."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from HTTPService.api_app import load_instances, search


def main():
    parser = argparse.ArgumentParser(description="Search DSI-Wiki content.")
    parser.add_argument("query")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--layer", default="all")
    args = parser.parse_args()

    scan_dir = os.path.expanduser("~/CLEANUP/MAIN/DSI-Wiki/Instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        print(f"instance not found: {args.instance}", file=sys.stderr)
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    results = search(base_dir, args.query, args.layer)
    if not results:
        sys.exit(1)
    for r in results:
        excerpt = " ".join(r["excerpt"][:200].split())
        print(f"{r['layer']}/{r['topic']}: {excerpt}")


if __name__ == "__main__":
    main()
