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

_scripts_root = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from gateway.api_app import load_instances, get_content
from common.ollama_lock import call_ollama as _locked_call_ollama

# Switched from Bonsai-27B to qwen3:1.7b 2026-07-30 (see nightly fact-check same-day
# fix): 8GB GTX 1070 can't run a 27B model fast enough alongside anything else.
MODEL = "qwen3:1.7b"
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
    data = _locked_call_ollama(
        MODEL, [{"role": "user", "content": content}], think=False, timeout=180,
        label="wiki-internal-scan",
    )
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

    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
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

    report_dir = str(Path(__file__).resolve().parent.parent.parent / "reports")
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
