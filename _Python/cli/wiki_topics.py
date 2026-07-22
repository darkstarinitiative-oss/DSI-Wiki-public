#!/usr/bin/env python3
"""wiki_topics.py — list topics in a DSI-Wiki layer, one per line."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from HTTPService.api_app import load_instances, list_topics


def main():
    parser = argparse.ArgumentParser(description="List DSI-Wiki topics in a layer.")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--layer", default="minified")
    args = parser.parse_args()

    scan_dir = os.path.expanduser("~/CLEANUP/MAIN/DSI-Wiki/Instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        print(f"instance not found: {args.instance}", file=sys.stderr)
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    for topic in list_topics(base_dir, args.layer):
        print(topic)


if __name__ == "__main__":
    main()
