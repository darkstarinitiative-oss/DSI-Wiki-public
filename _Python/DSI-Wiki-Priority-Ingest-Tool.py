#!/usr/bin/env python3
# =============================================================================
# 17_ingest_priority_sources.py
# Ne yapar: Basit sistem taramasının (14_basic_scan.sh) GÖREMEDİĞİ asıl zengin
#   kaynağı işler -- şu 4 kökteki HER .md dosyasının TAM İÇERİĞİNİ (sadece
#   ismini/konumunu değil) tek tek LLM-Wiki'ye ingest eder:
#     - ~/.hermes/*.md                              (sistemde ne var/ne çalışıyor)
#     - ~/codebase/projects/hermes-improvement/**    (4 katman derinliğe kadar)
#     - ~/codebase/projects/hermes-social-automation/** (4 katman derinliğe kadar)
#     - ~/codebase/projects/yamyamlar/**             (4 katman derinliğe kadar)
#
#   Her .md dosyası AYRI bir ingest çağrısı olarak işlenir (hepsini tek dosyada
#   birleştirmek 06_ingest_engine.py'deki 8000 karakterlik kesmeye takılıp veri
#   kaybettirirdi). Konu adı, dosyanın göreli yolundan türetilir, böylece
#   documentation/llm/minified katmanlarında her kaynağın kendi sayfası olur.
#
#   Resumable: crawl_state.json'a işlenenleri kaydeder, Ctrl+C sonrası kaldığı
#   yerden devam eder.
#
# Kullanım: python3 17_ingest_priority_sources.py
#   python3 17_ingest_priority_sources.py --delay 2   # çağrılar arası bekleme
# =============================================================================
import argparse
import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.expanduser("~/LLM-Wiki-BASE")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "reports", "priority-ingest-state.json")
RAW_STAGING_DIR = os.path.join(BASE_DIR, "raw", "priority")

# (kök klasör, maksimum derinlik) -- derinlik None ise sınırsız
SOURCES = [
    (os.path.expanduser("~/.hermes"), 2),
    (os.path.expanduser("~/codebase/projects/hermes-improvement"), 4),
    (os.path.expanduser("~/codebase/projects/hermes-social-automation"), 4),
    (os.path.expanduser("~/codebase/projects/yamyamlar"), 4),
]


def find_md_files(root: str, max_depth: int) -> list:
    if not os.path.isdir(root):
        print(f"   !! Kök bulunamadı, atlanıyor: {root}")
        return []
    root_depth = root.rstrip(os.sep).count(os.sep)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if max_depth is not None and depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in
                        ("node_modules", ".git", ".venv", "__pycache__")]
        for fname in filenames:
            if fname.lower().endswith(".md"):
                found.append(os.path.join(dirpath, fname))
    return sorted(found)


def slugify(path: str) -> str:
    """Dosya yolunu, konu adı olarak kullanılabilecek güvenli bir slug'a çevirir."""
    home = os.path.expanduser("~")
    rel = path[len(home):].lstrip(os.sep) if path.startswith(home) else path
    slug = rel.replace(os.sep, "__").replace(" ", "-")
    if slug.lower().endswith(".md"):
        slug = slug[:-3]
    return f"priority__{slug}"[:200]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"processed": []}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=2.0,
                         help="Ingest çağrıları arası bekleme (saniye)")
    args = parser.parse_args()

    os.makedirs(RAW_STAGING_DIR, exist_ok=True)
    state = load_state()
    processed = set(state["processed"])

    all_files = []
    for root, depth in SOURCES:
        files = find_md_files(root, depth)
        print(f">> {root} -> {len(files)} .md dosyası bulundu (max derinlik: {depth})")
        all_files.extend(files)

    all_files = sorted(set(all_files))
    todo = [f for f in all_files if f not in processed]

    print(f"\n>> Toplam {len(all_files)} dosya, {len(todo)} tanesi henüz işlenmemiş.")
    if not todo:
        print(">> Hepsi zaten işlenmiş.")
        return

    for idx, filepath in enumerate(todo, 1):
        slug = slugify(filepath)
        staged_path = os.path.join(RAW_STAGING_DIR, f"{slug}.md")

        print(f"\n>> [{idx}/{len(todo)}] {filepath}")
        print(f"   -> konu: {slug}")

        try:
            content = open(filepath, encoding="utf-8", errors="ignore").read()
        except OSError as e:
            print(f"   !! Okunamadı: {e}, atlanıyor.")
            continue

        with open(staged_path, "w", encoding="utf-8") as f:
            f.write(f"Source file: {filepath}\n\n{content}")

        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "06_ingest_engine.py"), staged_path],
            check=False,
        )
        if result.returncode != 0:
            print(f"   !! ingest başarısız oldu (exit {result.returncode}), bu dosya sonra tekrar denenebilir.")
            continue

        processed.add(filepath)
        state["processed"] = sorted(processed)
        save_state(state)

        if idx < len(todo):
            time.sleep(args.delay)

    print(f"\n>> Bitti. İşlenen: {len(processed)}/{len(all_files)}")
    print(f">> documentation/, llm/, minified/ katmanlarında 'priority__*' önekli sayfaları görebilirsiniz:")
    print(f"   ls {BASE_DIR}/minified/priority__*")


if __name__ == "__main__":
    main()
