#!/usr/bin/env python3
# =============================================================================
# 10b_parse_soul_hierarchy.py
# Ne yapar: SOUL.md dosyaları genelde başka dosya/klasörlere REFERANS VERİR
#   (markdown link, [[wikilink]], backtick path gibi). Bu script bu referansları
#   çıkarır, her birini SOUL.md'nin bulunduğu dizine göre çözer, var olup
#   olmadığını kontrol eder ve eğer referans verilen dosya da bir SOUL.md ise
#   İÇİNE GİRİP onun referanslarını da takip eder (recursive, max derinlikli).
#
#   Sonuç: "SOUL.md hiyerarşisi neye işaret ediyor" sorusuna cevap veren bir
#   referans grafiği. Bu grafik 11_generate_reorg_plan.py tarafından okunup
#   "bu klasör SOUL.md zincirinde geçiyor mu" bilgisini sınıflandırmaya katar.
#
# Girdi: ~/LLM-Wiki-BASE/reports/inventory.json (soul_md_files listesi, tohum olarak)
# Çıktı: ~/LLM-Wiki-BASE/reports/soul_hierarchy.json
# Kullanım: python3 10b_parse_soul_hierarchy.py
# =============================================================================
import json
import os
import re
from datetime import datetime, timezone

BASE_DIR = os.path.expanduser("~/LLM-Wiki-BASE")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
INVENTORY_FILE = os.path.join(REPORT_DIR, "inventory.json")
OUT_FILE = os.path.join(REPORT_DIR, "soul_hierarchy.json")

MAX_DEPTH = 5  # döngüye girmemek için recursive takip derinlik sınırı

# Referans yakalayan kalıplar: markdown link, wikilink, backtick path
PATTERNS = [
    re.compile(r'\[[^\]]*\]\(([^)]+)\)'),   # [metin](yol)
    re.compile(r'\[\[([^\]]+)\]\]'),         # [[wikilink]]
    re.compile(r'`(~?/[^`]+)`'),             # `~/bir/yol` veya `/bir/yol`
]


def extract_references(text: str) -> list:
    """Bir metindeki tüm potansiyel dosya/klasör referanslarını çıkarır."""
    refs = []
    for pattern in PATTERNS:
        refs.extend(pattern.findall(text))
    # http(s) linklerini ele (dosya referansı değil, dış link)
    return [r.strip() for r in refs if not r.strip().startswith(("http://", "https://"))]


def resolve_path(ref: str, base_dir: str) -> str:
    """Referansı, kaynağı içeren SOUL.md'nin dizinine göre mutlak yola çevirir."""
    if ref.startswith("~"):
        return os.path.expanduser(ref)
    if ref.startswith("/"):
        return ref
    return os.path.normpath(os.path.join(base_dir, ref))


def walk_soul(path: str, visited: set, depth: int, nodes: dict, edges: list, broken: list):
    if depth > MAX_DEPTH or path in visited:
        return
    visited.add(path)

    if not os.path.exists(path):
        broken.append({"from": "seed", "to": path})
        nodes[path] = {"type": "missing"}
        return

    node_type = "dir" if os.path.isdir(path) else "file"
    nodes.setdefault(path, {"type": node_type, "referenced_by": []})

    # Sadece dosya ise ve içeriği okunabiliyorsa referansları çıkar
    if node_type == "file":
        try:
            content = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            return
        base_dir = os.path.dirname(path)
        for raw_ref in extract_references(content):
            resolved = resolve_path(raw_ref, base_dir)
            edges.append({"from": path, "to": resolved})

            if not os.path.exists(resolved):
                broken.append({"from": path, "to": resolved})
                nodes.setdefault(resolved, {"type": "missing", "referenced_by": []})
                nodes[resolved]["referenced_by"].append(path)
                continue

            r_type = "dir" if os.path.isdir(resolved) else "file"
            nodes.setdefault(resolved, {"type": r_type, "referenced_by": []})
            nodes[resolved]["referenced_by"].append(path)

            # Referans başka bir SOUL.md ise, içine girip onun da referanslarını takip et
            if r_type == "file" and os.path.basename(resolved).lower() == "soul.md":
                walk_soul(resolved, visited, depth + 1, nodes, edges, broken)
            # Referans bir klasörse, o klasörün içindeki SOUL.md'yi de kontrol et
            elif r_type == "dir":
                nested_soul = os.path.join(resolved, "SOUL.md")
                if os.path.exists(nested_soul):
                    walk_soul(nested_soul, visited, depth + 1, nodes, edges, broken)


def main():
    if not os.path.exists(INVENTORY_FILE):
        print(f"!! Envanter yok: {INVENTORY_FILE}")
        print("   Önce bash 10_discover_inventory.sh çalıştırın.")
        return

    inventory = json.load(open(INVENTORY_FILE, encoding="utf-8"))
    seed_soul_files = inventory.get("soul_md_files", [])

    if not seed_soul_files:
        print("!! Envanterde SOUL.md bulunamadı, çıkılıyor.")
        return

    nodes, edges, broken, visited = {}, [], [], set()

    for soul_path in seed_soul_files:
        walk_soul(soul_path, visited, depth=0, nodes=nodes, edges=edges, broken=broken)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_files": seed_soul_files,
        "nodes": [{"path": p, **meta} for p, meta in nodes.items()],
        "edges": edges,
        "broken_references": broken,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f">> Hiyerarşi çözüldü: {len(nodes)} düğüm, {len(edges)} referans, "
          f"{len(broken)} kırık referans")
    print(f">> Kaydedildi: {OUT_FILE}")
    if broken:
        print(">> UYARI: kırık referanslar var, reorg-plan.md'de listelenecek.")
    print(">> Sonraki adım: 11_generate_reorg_plan.py (artık bu hiyerarşiyi de kullanacak)")


if __name__ == "__main__":
    main()
