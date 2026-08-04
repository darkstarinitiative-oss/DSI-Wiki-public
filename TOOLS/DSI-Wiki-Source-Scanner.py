#!/usr/bin/env python3
"""
DSI-Wiki Wave 1 — Agentless Source Scanner
No LLM calls. Scans project sources and outputs structured markdown to raw/.

Usage:
  python3 source_scanner.py --project DSI-LLM-Wiki \
      --source ~/LLM-Wiki/ \
      --services wiki-v2.service,llm-wiki-watch.service \
      --output ~/LLM-Wiki-BASE-staging/raw/
"""

import argparse
import ast
import subprocess
from datetime import datetime
from pathlib import Path


def file_tree(source_dir: Path, max_depth: int = 2) -> str:
    source_dir = source_dir.expanduser().resolve()
    if not source_dir.exists():
        return f"[bulunamadı: {source_dir}]"

    lines = [str(source_dir)]

    def _walk(path: Path, depth: int, prefix: str):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            size = f"  ({entry.stat().st_size}B)" if entry.is_file() else ""
            lines.append(f"{prefix}{connector}{entry.name}{size}")
            if entry.is_dir() and depth < max_depth:
                _walk(entry, depth + 1, prefix + ("    " if is_last else "│   "))

    _walk(source_dir, 1, "")
    return "\n".join(lines)


def service_status(services: list) -> str:
    if not services:
        return "_tanımlı servis yok_"
    rows = []
    for svc in services:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "show", svc,
                 "--property=ActiveState,SubState,MainPID"],
                capture_output=True, text=True, timeout=5
            )
            props = dict(
                line.split("=", 1)
                for line in r.stdout.strip().splitlines()
                if "=" in line
            )
            state = props.get("ActiveState", "unknown")
            sub = props.get("SubState", "")
            pid = props.get("MainPID", "0")
            rows.append(f"| {svc} | {state} ({sub}) | PID {pid} |")
        except Exception as e:
            rows.append(f"| {svc} | hata | {e} |")
    header = "| Servis | Durum | PID |\n|---|---|---|"
    return header + "\n" + "\n".join(rows)


def py_metadata(filepath: Path) -> str:
    try:
        src = filepath.read_text(errors="replace")
        tree = ast.parse(src)
    except Exception as e:
        return f"[parse hatası: {e}]"

    imports, classes, functions = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:
                functions.append(node.name)

    lines = len(src.splitlines())
    parts = [f"**{filepath.name}** ({lines} satır)"]
    if imports:
        parts.append(f"  imports: `{', '.join(sorted(set(imports))[:15])}`")
    if classes:
        parts.append(f"  class: `{', '.join(classes)}`")
    if functions:
        parts.append(f"  def: `{', '.join(functions[:20])}`")
    return "\n".join(parts)


def read_head(filepath: Path, max_lines: int = 40) -> str:
    try:
        lines = filepath.read_text(errors="replace").splitlines()
        body = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            body += f"\n... (+{len(lines) - max_lines} satır)"
        return body
    except Exception as e:
        return f"[okuma hatası: {e}]"


def scan(project: str, sources: list, services: list, output_dir: str) -> Path:
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{project}-source-scan.md"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    blocks = [
        f"# {project} — Kaynak Taraması",
        f"**Tarih:** {ts}",
        f"**Kaynaklar:** {', '.join(sources)}",
        "**Dalga:** 1 — Agentless Script",
        "",
        "---",
    ]

    for src_str in sources:
        src = Path(src_str).expanduser().resolve()
        blocks.append(f"\n## Dosya Ağacı — `{src_str}`\n\n```\n{file_tree(src)}\n```")

        # Python metadata — sadece üst dizindeki .py dosyaları
        py_files = sorted(src.glob("*.py"))[:15]
        if py_files:
            blocks.append(f"\n## Python Dosyaları — `{src_str}`\n")
            for pf in py_files:
                if not pf.name.startswith("_"):
                    blocks.append(py_metadata(pf))

        # Temel belgeler
        for doc in ["README.md", "DEVLOG.md", "CLAUDE.md", "requirements.txt", "config.yaml"]:
            f = src / doc
            if f.exists():
                blocks.append(f"\n## {doc}\n\n```\n{read_head(f)}\n```")

    # Servisler
    blocks.append(f"\n## Servisler\n\n{service_status(services)}")

    out_file.write_text("\n".join(blocks))
    return out_file


def main():
    p = argparse.ArgumentParser(description="DSI-Wiki Wave 1 Source Scanner")
    p.add_argument("--project", required=True)
    p.add_argument("--source", action="append", required=True)
    p.add_argument("--services", default="")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    svcs = [s.strip() for s in args.services.split(",") if s.strip()]
    out = scan(args.project, args.source, svcs, args.output)
    print(f"OK {out}")


if __name__ == "__main__":
    main()
