#!/usr/bin/env python3
"""
DSI-Wiki-Brief-Backfill.py — one-off backfill of the new `brief` layer.

For every topic that already has an `llm/` page (i.e. the consolidated topic set:
non-hierarchical topics + every MAIN_ topic; SUB_ pages are folded into their MAIN),
generate a `brief/<topic>.md` from the documentation layer using the same engine the
live ingest daemon uses (qwen3-worker via Ollama /api/chat, think=false).

Source content mirrors the daemon's consolidation:
  - MAIN_<name>  -> documentation/MAIN_<name>.md + every documentation/SUB_<name>_*.md
  - other topic  -> documentation/<topic>.md

Resumable: skips topics that already have a non-empty brief/ page (unless --force).
Usage:
  python3 DSI-Wiki-Brief-Backfill.py                # all topics
  python3 DSI-Wiki-Brief-Backfill.py --only MAIN_DSI-Wiki --only ERROR-REPORT
  python3 DSI-Wiki-Brief-Backfill.py --force        # regenerate even if brief exists
"""
import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTANCES = REPO / "JSONS" / "instances"
INSTANCE_NAME = "default-instance"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3-worker"
OLLAMA_NUM_CTX = 16384
OLLAMA_NUM_PREDICT = 900
OLLAMA_THINK = False
TIMEOUT = 300


def load_instance() -> dict:
    data = json.loads((INSTANCES / f"{INSTANCE_NAME}.json").read_text(encoding="utf-8"))
    return data


def run_llm(prompt: str) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": OLLAMA_THINK,
        "options": {"num_ctx": OLLAMA_NUM_CTX, "num_predict": OLLAMA_NUM_PREDICT},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except socket.timeout as e:
        raise TimeoutError(str(e)) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"ollama not reachable at {OLLAMA_URL}: {e}") from e
    if "error" in body:
        raise RuntimeError(str(body["error"]))
    return body.get("message", {}).get("content", "").strip()


def strip_think(text: str) -> str:
    # qwen3 with think=false should emit none, but be defensive.
    while "<think>" in text and "</think>" in text:
        i = text.index("<think>")
        j = text.index("</think>") + len("</think>")
        text = (text[:i] + text[j:]).strip()
    return text.strip()


def sources_for(topic: str, doc_dir: Path) -> list[tuple[str, str]]:
    parts = topic.split("_")
    out = []
    main_doc = doc_dir / f"{topic}.md"
    if main_doc.exists():
        out.append((topic, main_doc.read_text(encoding="utf-8")))
    if parts[0] == "MAIN" and len(parts) == 2:
        name = parts[1]
        for sub in sorted(doc_dir.glob(f"SUB_{name}_*.md")):
            out.append((sub.stem, sub.read_text(encoding="utf-8")))
    return out


def build_prompt(topic: str, brief_instr: str, sources: list[tuple[str, str]]) -> str:
    combined = "\n\n".join(f"=== SOURCE: {n} ===\n{t}" for n, t in sources)
    return (
        "You are a technical documentation writer for the DSI (Dark Star Industries) AI system.\n\n"
        "Produce the BRIEF layer for the topic below, following these instructions exactly:\n\n"
        f"{brief_instr}\n\n"
        "Output ONLY the brief prose itself — no headings, no code fences, no preamble, "
        "no delimiter markers.\n\n"
        f"TOPIC: {topic}\n\n"
        f"SOURCE DOCUMENTATION:\n{combined}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[], help="restrict to these topic(s)")
    ap.add_argument("--force", action="store_true", help="regenerate even if brief exists")
    args = ap.parse_args()

    inst = load_instance()
    base_dir = Path(inst["base_dir"])
    brief_instr = inst["layers"]["brief"]["prompt"]
    doc_dir = base_dir / "documentation"
    llm_dir = base_dir / "llm"
    brief_dir = base_dir / "brief"
    brief_dir.mkdir(parents=True, exist_ok=True)

    # Target set = the consolidated topic set = whatever has an llm/ page.
    targets = sorted(p.stem for p in llm_dir.glob("*.md") if p.name != "log.md")
    if args.only:
        want = set(args.only)
        targets = [t for t in targets if t in want]
        missing = want - set(targets)
        if missing:
            print(f"!! not in llm layer, skipping: {sorted(missing)}")

    print(f">> {len(targets)} target topic(s) | engine={OLLAMA_MODEL} think={OLLAMA_THINK}")
    ok = skipped = failed = 0
    for i, topic in enumerate(targets, 1):
        out_path = brief_dir / f"{topic}.md"
        if out_path.exists() and out_path.read_text(encoding="utf-8").strip() and not args.force:
            print(f"[{i}/{len(targets)}] skip (exists): {topic}")
            skipped += 1
            continue
        sources = sources_for(topic, doc_dir)
        if not sources:
            print(f"[{i}/{len(targets)}] !! no documentation source: {topic}")
            failed += 1
            continue
        prompt = build_prompt(topic, brief_instr, sources)
        try:
            raw = run_llm(prompt)
        except (TimeoutError, ConnectionError, RuntimeError) as e:
            print(f"[{i}/{len(targets)}] !! LLM error for {topic}: {e}")
            failed += 1
            continue
        content = strip_think(raw)
        if not content:
            print(f"[{i}/{len(targets)}] !! empty output: {topic}")
            failed += 1
            continue
        out_path.write_text(content + "\n", encoding="utf-8")
        wc = len(content.split())
        print(f"[{i}/{len(targets)}] OK {topic} ({wc} words, {len(sources)} src)")
        ok += 1

    print(f">> done: {ok} written, {skipped} skipped, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
