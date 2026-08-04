#!/usr/bin/env python3
"""wiki_write.py — write a topic's content to a DSI-Wiki layer."""

import argparse
import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from gateway.api_app import load_instances


def _base_dir():
    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    return load_instances(scan_dir)['Cain-the-elder']['base_dir']


LAYERS = ('raw', 'documentation', 'llm', 'minified', 'brief', 'changelog', 'devlog', 'silinmişler')


def write_topic(topic: str, layer: str, content: str, instance: str = 'Cain-the-elder') -> Path:
    """Write content to a topic in a specific layer."""
    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    instances = load_instances(scan_dir)
    if instance not in instances:
        raise ValueError(f"Instance '{instance}' not found. Available: {list(instances.keys())}")
    base_dir = instances[instance]['base_dir']
    
    if layer not in LAYERS:
        raise ValueError(f"Layer '{layer}' not valid. Valid layers: {LAYERS}")
    
    layer_dir = Path(base_dir) / layer
    layer_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure topic has .md extension
    if not topic.endswith('.md'):
        topic = topic + '.md'
    
    file_path = layer_dir / topic
    file_path.write_text(content, encoding='utf-8')
    return file_path


def main():
    parser = argparse.ArgumentParser(description="Write a DSI-Wiki topic's content.")
    parser.add_argument("topic")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--layer", default="minified", choices=LAYERS)
    parser.add_argument("--content", help="Content to write (if not provided, reads from stdin)")
    parser.add_argument("--file", help="Read content from file")
    
    args = parser.parse_args()
    
    if args.content is not None:
        content = args.content
    elif args.file:
        content = Path(args.file).read_text(encoding='utf-8')
    else:
        content = sys.stdin.read()
    
    path = write_topic(args.topic, args.layer, content, args.instance)
    print(f"Written to {path}")


if __name__ == '__main__':
    main()
