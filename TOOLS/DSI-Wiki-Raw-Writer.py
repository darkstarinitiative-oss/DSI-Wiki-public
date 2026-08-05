#!/usr/bin/env python3
"""
DSI-Wiki-Raw-Writer — drop a raw note into the LLM-Wiki ingest inbox.

This is the ONLY thing an external producer (e.g. the dispatcher) should do:
write a `<topic>.md` file into the raw/ inbox. The already-running
`dsi-wiki-ingest.service` polls that inbox, generates the documentation/llm/
minified layers via Bonsai, and archives the note. No `hermes`, no LLM call,
no per-note process spawn happens here.

Inbox resolution (first hit wins) — so the writer always sees the SAME raw dir
the ingest service actually uses, instead of a hardcoded guess:
  1. --raw-dir argument
  2. $LLM_WIKI_RAW_DIR
  3. LLM_WIKI_RAW_DIR from the ingest service's EnvironmentFile
  4. hard fallback: /home/user/CLEANUP/DATA/Wiki-RAW

Routing: the ingest service routes a note to an instance by matching a route
keyword contained in the topic name; a topic with no keyword lands in the
default instance (default-instance). So a plain topic like
`dispatcher-run-t_1a2b3c4d` goes to the default wiki, while a topic containing
e.g. `witch` routes to the witch instance.

Usage:
  DSI-Wiki-Raw-Writer --topic dispatcher-run-t_1a2b --content "..."
  DSI-Wiki-Raw-Writer --topic MAIN_DSI-Foo --content-file note.md
  some_producer | DSI-Wiki-Raw-Writer --topic SUB_DSI-Foo_Bar        # content from stdin
"""
import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

INGEST_ENV_FILE = Path(__file__).resolve().parent.parent / "CODE" / "ingest" / ".env"
FALLBACK_RAW_DIR = Path(os.environ.get("WIKI_RAW_DIR", "/home/user/CLEANUP/DATA/Wiki-RAW"))

# A topic becomes a filename stem, so keep it to safe characters only.
_VALID_TOPIC = re.compile(r"^[A-Za-z0-9._-]+$")


def _raw_dir_from_env_file(env_file: Path) -> str | None:
    """Read LLM_WIKI_RAW_DIR out of a KEY=VALUE env file, if present."""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("LLM_WIKI_RAW_DIR="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def resolve_raw_dir(cli_value: str | None) -> Path:
    """Resolve the raw inbox, preferring explicit config over the fallback."""
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get("LLM_WIKI_RAW_DIR")
    if env_value:
        return Path(env_value).expanduser()
    file_value = _raw_dir_from_env_file(INGEST_ENV_FILE)
    if file_value:
        return Path(file_value).expanduser()
    return FALLBACK_RAW_DIR


def validate_topic(topic: str) -> str:
    topic = topic.strip()
    if not topic or not _VALID_TOPIC.match(topic):
        raise ValueError(
            f"Invalid topic {topic!r}: use only letters, digits, '.', '_', '-' "
            "(the topic becomes the raw filename)."
        )
    return topic


def read_content(args: argparse.Namespace) -> str:
    if args.content is not None:
        return args.content
    if args.content_file:
        return Path(args.content_file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("No content given: pass --content, --content-file, or pipe via stdin.")


def write_note(raw_dir: Path, topic: str, content: str) -> Path:
    """Atomically place <topic>.md into raw_dir.

    The file is first written under a non-'.md' temp name in the same directory,
    then os.replace()'d into place, so the ingest service's `glob('*.md')` poll
    can never pick up a half-written note.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    final_path = raw_dir / f"{topic}.md"
    fd, tmp_name = tempfile.mkstemp(dir=raw_dir, prefix=f".{topic}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, final_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="DSI-Wiki-Raw-Writer",
        description="Drop a raw note into the LLM-Wiki ingest inbox (no LLM, no hermes).",
    )
    parser.add_argument("--topic", required=True,
                        help="Topic / filename stem, e.g. dispatcher-run-t_1a2b or MAIN_DSI-Foo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--content", help="Note body as a string")
    group.add_argument("--content-file", help="Read note body from this file")
    parser.add_argument("--raw-dir", help="Override the inbox directory (else env / service .env)")
    args = parser.parse_args()

    try:
        topic = validate_topic(args.topic)
        content = read_content(args)
        raw_dir = resolve_raw_dir(args.raw_dir)
        path = write_note(raw_dir, topic, content)
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
