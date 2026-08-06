#!/usr/bin/env python3
"""DSI-wiki-obsidian-link — look up the Wiki<->Obsidian cross-reference.

Source of truth: $WIKI_BASE_DIR/_meta/obsidian_links.json, a flat
{wiki_topic: obsidian_relpath|null} map, hand-maintained (never touched by the
LLM ingest pipeline). obsidian_relpath is relative to ~/GOOGLE_DRIVE/OBSIDIAN/DSI/.

Usage:
  DSI-wiki-obsidian-link --topic MAIN_DSI-Database      -> prints obsidian path or "none"
  DSI-wiki-obsidian-link --obsidian-path DSI-DATABASE/DSI-DATABASE.md -> prints wiki topic or "none"
  DSI-wiki-obsidian-link --list                          -> prints the full map
"""
import argparse
import json
import os

if not os.environ.get("WIKI_BASE_DIR"):
    raise SystemExit(
        "error: WIKI_BASE_DIR is not set — source SERVICES/.env first "
        "(`set -a; source SERVICES/.env; set +a`). No fallback path."
    )
WIKI_BASE_DIR = os.environ["WIKI_BASE_DIR"]
LINKS_PATH = os.path.join(WIKI_BASE_DIR, "_meta", "obsidian_links.json")


def load_links():
    with open(LINKS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


def main():
    parser = argparse.ArgumentParser(description="Wiki<->Obsidian cross-reference lookup")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topic", help="Wiki topic name (e.g. MAIN_DSI-Database)")
    group.add_argument("--obsidian-path", help="Obsidian note path relative to OBSIDIAN/DSI/")
    group.add_argument("--list", action="store_true", help="Print the full map")
    args = parser.parse_args()

    links = load_links()

    if args.list:
        for topic, path in sorted(links.items()):
            print(f"{topic}: {path or 'none'}")
        return

    if args.topic:
        print(links.get(args.topic, "unknown topic") or "none")
        return

    reverse = {v: k for k, v in links.items() if v}
    print(reverse.get(args.obsidian_path, "none"))


if __name__ == "__main__":
    main()
