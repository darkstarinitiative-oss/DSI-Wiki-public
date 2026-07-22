#!/usr/bin/env python3
"""internal_scan.py — detect factual drift between documentation and minified layers."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from HTTPService.api_app import load_instances, get_content

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "hf.co/prism-ml/Bonsai-27B-gguf:Q1_0"
PROMPT = (
    "Compare the factual claims (model names, file paths, ports, commands, statuses) "
    "in these two texts. Reply with exactly CONSISTENT if they do not contradict each "
    "other, or DRIFT: followed by a short list of contradictions."
)


def _ask_bonsai(doc, mini):
    content = (
        PROMPT
        + "\n\n=== TEXT A (documentation) ===\n" + doc
        + "\n\n=== TEXT B (minified) ===\n" + mini
    )
    body = json.dumps({
        "model": MODEL,
        "stream": False,
        "think": False,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"].strip()


def main():
    parser = argparse.ArgumentParser(description="DSI-Wiki internal drift scan")
    parser.add_argument("--instance", default="Cain-the-elder")
    parser.add_argument("--topic")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not args.topic and not args.all:
        sys.stderr.write("error: give --topic <name> or --all\n")
        sys.exit(2)

    scan_dir = os.path.expanduser("~/CLEANUP/MAIN/DSI-Wiki/Instances")
    instances = load_instances(scan_dir)
    if args.instance not in instances:
        sys.stderr.write("unknown instance: " + args.instance + "\n")
        sys.exit(2)
    base_dir = instances[args.instance]["base_dir"]

    if args.topic:
        topics = [args.topic]
    else:
        mini_dir = os.path.join(base_dir, "minified")
        topics = sorted(
            f[:-3] for f in os.listdir(mini_dir)
            if f.endswith(".md") and f != "log.md"
        )

    report_dir = os.path.expanduser("~/CLEANUP/MAIN/DSI-Wiki/reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(
        report_dir, "internal-scan-" + date.today().strftime("%Y%m%d") + ".md"
    )

    drift = False
    with open(report_path, "a", encoding="utf-8") as report:
        for t in topics:
            doc = get_content(base_dir, "documentation", t)
            mini = get_content(base_dir, "minified", t)
            if doc is None or mini is None:
                verdict = "SKIPPED (missing layer)"
            else:
                try:
                    verdict = _ask_bonsai(doc, mini)
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    sys.stderr.write("ollama error: " + str(e) + "\n")
                    sys.exit(4)
                if verdict.startswith("DRIFT"):
                    drift = True
            report.write("## " + t + "\n" + verdict + "\n\n")
            print(t + ": " + verdict[:80])

    sys.exit(3 if drift else 0)


if __name__ == "__main__":
    main()
