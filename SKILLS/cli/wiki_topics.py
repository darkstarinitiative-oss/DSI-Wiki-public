#!/usr/bin/env python3
"""wiki_topics.py — list topics in a DSI-Wiki layer, one per line."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from gateway.api_app import load_instances, list_topics


def main():
    parser = argparse.ArgumentParser(description="List DSI-Wiki topics in a layer.")
    parser.add_argument("--instance", default="default-instance")
    parser.add_argument("--layer", default="minified")
    args = parser.parse_args()

    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        print(f"instance not found: {args.instance}", file=sys.stderr)
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    for topic in list_topics(base_dir, args.layer):
        print(topic)


if __name__ == "__main__":
    main()
