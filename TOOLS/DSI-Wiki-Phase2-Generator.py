#!/usr/bin/env python3
"""
phase2_generator.py — Dalga 2: Her Ana Başlık için kaynak dosyaları okuyup
zengin raw belgesi üretir → raw/ dizinine yazar → ingest_worker staging'e işler.
"""
import os
import subprocess
from pathlib import Path
from datetime import datetime

RAW_DIR = Path("/home/user/LLM-Wiki/raw")
STAGING_MINIFIED = Path("/home/user/LLM-Wiki-BASE-staging/minified")

# Ana Başlık → kaynak dizin/dosya listesi (DocumentUpdatePlan kaynak tablosundan)
TOPICS = {
    "DSI-LLM-Wiki": {
        "src_dirs": ["~/LLM-Wiki"],
        "src_files": [
            "~/LLM-Wiki/wiki_server.py",
            "~/LLM-Wiki/ingest_engine.py",
            "~/LLM-Wiki/ingest_worker.py",
            "~/LLM-Wiki/provider.py",
            "~/LLM-Wiki/prompts.py",
            "~/LLM-Wiki/source_scanner.py",
            "~/LLM-Wiki/config.yaml",
        ],
        "services": ["wiki-v2.service", "llm-wiki-ingest-worker.service"],
    },
    "DSI-Dispatcher-Plus-Plus": {
        "src_dirs": ["~/READY/Dispatcher-plus-plus"],
        "src_files": [],
        "services": ["dispatcher.service"],
    },
    "DSI-GVCS": {
        "src_dirs": ["~/codebase/projects/dsi-gvcs"],
        "src_files": [],
        "services": [],
    },
    "DSI-MAINBOARD": {
        "src_dirs": ["~/codebase/projects/dsi-mainboard"],
        "src_files": [],
        "services": ["dsi-mainboard.service", "hermes-dashboard.service"],
    },
    "DSI-System": {
        "src_dirs": ["~/.hermes"],
        "src_files": [],
        "services": ["hermes-gateway.service"],
    },
    "DSI-Social-Media": {
        "src_dirs": ["~/codebase/projects/hermes-social-automation"],
        "src_files": [],
        "services": [],
    },
    "DSI-ihalemobil": {
        "src_dirs": ["~/codebase/projects/ihalemobil"],
        "src_files": [],
        "services": [],
    },
    "DSI-YamYamLar": {
        "src_dirs": ["~/codebase/projects/yamyamlar"],
        "src_files": [],
        "services": [],
    },
    "DSI-Provider-Management": {
        "src_dirs": ["~/READY/Hermes-CustomProviderManagement"],
        "src_files": [
            "~/READY/Hermes-CustomProviderManagement/config/paths.py",
            "~/READY/Hermes-CustomProviderManagement/core/db_tools.py",
            "~/READY/Hermes-CustomProviderManagement/core/sqlite_provider_filter.py",
            "~/READY/Hermes-CustomProviderManagement/dashboard/app.py",
        ],
        "services": ["provider-dashboard.service"],
    },
    "DSI-Agent-Profiles": {
        "src_dirs": ["~/.hermes/profiles"],
        "src_files": [],
        "services": [],
    },
}


def run(cmd: str, timeout: int = 10) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL, timeout=timeout).strip()
    except Exception:
        return ""


def dir_tree(path: str, depth: int = 2) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"(dizin yok: {path})"
    lines = []
    for item in sorted(p.rglob("*")):
        rel = item.relative_to(p)
        parts = rel.parts
        if len(parts) > depth:
            continue
        indent = "  " * (len(parts) - 1)
        lines.append(f"{indent}{item.name}{'/' if item.is_dir() else ''}")
    return "\n".join(lines[:80]) or "(boş)"


def read_file_head(path: str, lines: int = 40) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"(dosya yok: {path})"
    try:
        content = p.read_text(errors="ignore").splitlines()
        return "\n".join(content[:lines])
    except Exception as e:
        return f"(okuma hatası: {e})"


def service_status(name: str) -> str:
    out = run(f"systemctl --user status {name} --no-pager -l 2>/dev/null | head -5", timeout=5)
    if not out:
        out = run(f"systemctl status {name} --no-pager -l 2>/dev/null | head -5", timeout=5)
    return out or "(servis bulunamadı)"


def get_staging_minified(topic: str) -> str:
    candidates = [
        STAGING_MINIFIED / f"{topic}-source-scan.md",
        STAGING_MINIFIED / f"{topic}.md",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text()
    return "(minified bulunamadı)"


def generate_raw(topic: str, cfg: dict) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"tags: project",
        f"",
        f"# {topic} — Dalga 2 Kaynak Belgesi",
        f"",
        f"**Oluşturulma:** {ts}",
        f"**Kaynak:** Doğrudan dosya okuma — halüsinasyon yok",
        f"",
        f"---",
        f"",
        f"## Dalga 1 Minified Özeti (Staging'den)",
        f"",
        get_staging_minified(topic),
        f"",
        f"---",
        f"",
    ]

    # Dizin ağaçları
    for src_dir in cfg["src_dirs"]:
        expanded = str(Path(src_dir).expanduser())
        lines += [
            f"## Dizin Yapısı: {src_dir}",
            f"```",
            dir_tree(src_dir),
            f"```",
            f"",
        ]

    # Servis durumları
    if cfg["services"]:
        lines += ["## Servis Durumları", ""]
        for svc in cfg["services"]:
            lines += [
                f"### {svc}",
                f"```",
                service_status(svc),
                f"```",
                f"",
            ]

    # Kaynak dosya içerikleri
    if cfg["src_files"]:
        lines += ["## Kaynak Dosyalar (ilk 40 satır)", ""]
        for f in cfg["src_files"]:
            lines += [
                f"### {f}",
                f"```python",
                read_file_head(f),
                f"```",
                f"",
            ]

    # README / DEVLOG varsa ekle
    for src_dir in cfg["src_dirs"]:
        p = Path(src_dir).expanduser()
        for extra in ["README.md", "DEVLOG.md"]:
            ep = p / extra
            if ep.exists():
                lines += [
                    f"## {extra} ({src_dir})",
                    ep.read_text(errors="ignore")[:2000],
                    f"",
                ]

    return "\n".join(lines)


def main():
    RAW_DIR.mkdir(exist_ok=True)
    print(f">> Dalga 2 başladı — {len(TOPICS)} konu")

    for topic, cfg in TOPICS.items():
        print(f"   -> {topic}...")
        content = generate_raw(topic, cfg)
        out_path = RAW_DIR / f"{topic}-phase2.md"
        out_path.write_text(content)
        print(f"      yazıldı: {out_path.name} ({len(content)} karakter)")

    print(f">> Tamamlandı. raw/ dizininde {len(TOPICS)} dosya hazır.")
    print(f"   ingest_worker staging'e işleyecek.")


if __name__ == "__main__":
    main()
