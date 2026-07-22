#!/usr/bin/env python3
"""topic_ops.py — delete or rename a DSI-Wiki topic across all layers."""

import os
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from HTTPService.api_app import load_instances

LAYERS = ('raw', 'documentation', 'llm', 'minified', 'changelog', 'devlog')


def _base_dir():
    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "Instances")
    return load_instances(scan_dir)['Cain-the-elder']['base_dir']


def delete_topic(topic):
    base = _base_dir()
    found = False
    for layer in LAYERS:
        p = os.path.join(base, layer, topic + '.md')
        if os.path.exists(p):
            os.remove(p)
            print(p)
            found = True
    if found:
        return 0
    sys.stderr.write('not found: ' + topic + '\n')
    return 1


def rename_topic(old, new):
    base = _base_dir()
    found = False
    for layer in LAYERS:
        op = os.path.join(base, layer, old + '.md')
        np = os.path.join(base, layer, new + '.md')
        if not os.path.exists(op):
            continue
        if os.path.exists(np):
            sys.stderr.write('warning: target exists, skipping: ' + np + '\n')
            continue
        os.rename(op, np)
        print(np)
        found = True
    if found:
        return 0
    sys.stderr.write('not found: ' + old + '\n')
    return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.stderr.write('usage: topic_ops.py delete_topic <topic> | rename_topic <old> <new>\n')
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == 'delete_topic' and len(sys.argv) == 3:
        sys.exit(delete_topic(sys.argv[2]))
    elif cmd == 'rename_topic' and len(sys.argv) == 4:
        sys.exit(rename_topic(sys.argv[2], sys.argv[3]))
    else:
        sys.stderr.write('usage: topic_ops.py delete_topic <topic> | rename_topic <old> <new>\n')
        sys.exit(2)
