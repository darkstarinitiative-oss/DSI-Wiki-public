#!/usr/bin/env python3
"""wiki_get.py — print a single topic's content from a DSI-Wiki layer."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from gateway.api_app import load_instances, get_content


def main():
    parser = argparse.ArgumentParser(description="Print a DSI-Wiki topic's content.")
    parser.add_argument("topic")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--layer", default="minified")
    args = parser.parse_args()

    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        print(f"instance not found: {args.instance}", file=sys.stderr)
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    content = get_content(base_dir, args.layer, args.topic)
    if content is None:
        print(f"not found: {args.layer}/{args.topic}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(content)


if __name__ == "__main__":
    main()
