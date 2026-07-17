#!/usr/bin/env python3
# =============================================================================
# 11_generate_reorg_plan.py
# Ne yapar: 10_discover_inventory.sh'in çıkardığı ham envanteri okur, Ollama'ya
#   verir ve her klasör için şu sınıflandırmayı yaptırır:
#     - KEEP        : olduğu yerde kalsın, zaten doğru konumda
#     - MIGRATE      : yeni yapıya taşınmalı (hedef yol önerisiyle)
#     - ARCHIVE      : atıl ama silinmesin, arşive kaldırılsın
#     - DELETE_CANDIDATE : muhtemelen ölü/gereksiz, silinme adayı (KESİN SİLMEZ)
#     - DUPLICATE_SUSPECT: başka bir klasörle çakışıyor olabilir
#
#   *** BU SCRIPT HİÇBİR DOSYAYI TAŞIMAZ/SİLMEZ. Sadece plan üretir. ***
#   Onay verdiğinizde taşıma işlemini SİZ ya da ayrı bir "apply" script'i yapar.
#
# Çıktı:
#   ~/LLM-Wiki-BASE/reports/reorg-plan.md    (insan okuması için)
#   ~/LLM-Wiki-BASE/reports/reorg-plan.json  (ileride otomatik uygulanabilmesi için)
#
# Kullanım: python3 11_generate_reorg_plan.py
# =============================================================================
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.expanduser("~/LLM-Wiki-BASE")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
INVENTORY_FILE = os.path.join(REPORT_DIR, "inventory.json")
HIERARCHY_FILE = os.path.join(REPORT_DIR, "soul_hierarchy.json")
PLAN_MD = os.path.join(REPORT_DIR, "reorg-plan.md")
PLAN_JSON = os.path.join(REPORT_DIR, "reorg-plan.json")
OLLAMA_URL = "http://localhost:11434/api/generate"

with open(os.path.join(BASE_DIR, "config", "model_name.txt")) as f:
    MODEL_NAME = f.read().strip()

# Hedef yapı şeması -- AGENTS.md'deki namespace'lerle uyumlu (prompt'a İngilizce
# gidiyor, model tutarlı dilde kalsın diye)
TARGET_SCHEMA = """
Target directory structure (aligned with AGENTS.md):
  ~/projects-clean/servisler/<service-name>/   -> active, running services
  ~/projects-clean/projeler/<project-name>/    -> actively developed projects
  ~/projects-clean/arsiv/<folder-name>/        -> dormant but kept for reference
  (delete candidates are not moved anywhere, only flagged in the list)
"""


def call_ollama(prompt: str, temperature: float = 0.15) -> str:
    # Düşük temperature: küçük modelin "yaratıcı" dil kaymasını (Çince/İngilizce
    # karışması) azaltır, daha deterministik/itaatkâr çıktı verir.
    payload = json.dumps({
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read()).get("response", "").strip()


CJK_PATTERN = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff]')  # Çince/Japonca karakter aralığı


def has_language_drift(text: str) -> bool:
    return bool(CJK_PATTERN.search(text or ""))


def fix_language_drift(bad_text: str, path_context: str) -> str:
    """CJK/yabancı karaktere kayan bir gerekçeyi İngilizceye çevirtir (tek satır, hızlı)."""
    prompt = (f"Rewrite the following text in English, as a single short sentence. "
              f"Do not use any Chinese/Japanese characters:\n\n{bad_text}\n\n"
              f"(Context: {path_context})")
    fixed = call_ollama(prompt, temperature=0.1)
    return fixed if not has_language_drift(fixed) else "Needs manual review (could not auto-generate reason)."


def classify_batch(batch: list, soul_context: str) -> list:
    """Adayları küçük gruplar (batch) halinde sınıflandırır -- büyük tek prompt
    küçük modelin bunalıp dil kaymasına (Çince karışması) yol açıyordu."""
    batch_text = json.dumps(batch, ensure_ascii=False, indent=2)
    prompt = f"""You are a system/project inventory analyst. For each folder in the
JSON below, assign a CLASSIFICATION. Options: KEEP, MIGRATE, ARCHIVE,
DELETE_CANDIDATE, DUPLICATE_SUSPECT.

*** Write the "reason" field in English. ***

When deciding, consider:
- "referenced_in_soul_hierarchy": true means the folder is directly referenced
  in the SOUL.md chain -- this is the STRONGEST signal, these should lean
  KEEP/MIGRATE, never DELETE_CANDIDATE.
- runtime_status "no-match-found" likely means it's not running (ARCHIVE/DELETE_CANDIDATE candidate)
- very old git_last_commit (>6 months) likely means abandoned
- similarly-named folders may be DUPLICATE_SUSPECT

{TARGET_SCHEMA}

SOUL.md CONTEXT (summary):
{soul_context if soul_context else "(none)"}

FOLDERS:
{batch_text}

Output format: ONLY a valid JSON array, each element: path,
classification, reason (in English), suggested_target, duplicate_of.
No other explanation."""

    raw = call_ollama(prompt, temperature=0.15)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        cleaned = cleaned[4:] if cleaned.startswith("json") else cleaned
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        print("   !! Bu batch'te geçersiz JSON döndü, atlanıyor (path'ler KEEP varsayılan işaretlenecek).")
        return [{"path": item["path"], "classification": "KEEP",
                  "reason": "Otomatik analiz başarısız oldu, elle incelenmeli.",
                  "suggested_target": None, "duplicate_of": None} for item in batch]

    # Dil kayması kontrolü: Çince/yabancı karakter tespit edilirse gerekçeyi düzelt
    for item in result:
        if has_language_drift(item.get("reason", "")):
            item["reason"] = fix_language_drift(item["reason"], item.get("path", ""))

    return result


def main():
    if not os.path.exists(INVENTORY_FILE):
        print(f"!! Envanter yok: {INVENTORY_FILE}")
        print("   Önce bash 10_discover_inventory.sh çalıştırın.")
        return

    inventory = json.load(open(INVENTORY_FILE, encoding="utf-8"))
    candidates = inventory.get("candidates", [])
    soul_files = inventory.get("soul_md_files", [])

    if not candidates:
        print("!! Envanterde aday klasör bulunamadı, taranan yolları kontrol edin.")
        return

    # SOUL.md içeriklerini context'e ekle -- ama SINIRLI: 20 dosyanın hepsini tam
    # basmak (her batch'te) modeli bunaltıp dil kaymasına yol açan bir diğer etkendi.
    # Asıl karar sinyali zaten referenced_in_soul_hierarchy bayrağında var; burada
    # sadece kısa bir bağlam özeti yeterli.
    soul_context = ""
    for sf in soul_files[:3]:  # en fazla ilk 3 dosya
        if os.path.exists(sf):
            content = open(sf, encoding="utf-8", errors="ignore").read()[:500]
            soul_context += f"\n--- {sf} (özet) ---\n{content}\n"
    if len(soul_files) > 3:
        soul_context += f"\n(+ {len(soul_files) - 3} SOUL.md daha var, referans grafiği ayrıca hesaplandı)\n"

    # --- SOUL.md referans grafiğini yükle (10b_parse_soul_hierarchy.py çıktısı) ---
    referenced_paths = set()
    broken_refs = []
    if os.path.exists(HIERARCHY_FILE):
        hierarchy = json.load(open(HIERARCHY_FILE, encoding="utf-8"))
        referenced_paths = {n["path"] for n in hierarchy.get("nodes", [])
                             if n.get("type") != "missing"}
        broken_refs = hierarchy.get("broken_references", [])
        print(f">> SOUL.md hiyerarşisi yüklendi: {len(referenced_paths)} referanslı yol, "
              f"{len(broken_refs)} kırık referans")
    else:
        print(">> UYARI: soul_hierarchy.json bulunamadı, önce 10b_parse_soul_hierarchy.py "
              "çalıştırılırsa sınıflandırma daha isabetli olur. Şimdilik onsuz devam ediliyor.")

    # Her aday klasöre "SOUL.md zincirinde referans veriliyor mu" bilgisini işle --
    # bu bilgi modele KEEP/MIGRATE ile ARCHIVE/DELETE_CANDIDATE arasında karar verirken
    # en güçlü sinyal olacak.
    for c in candidates:
        c["referenced_in_soul_hierarchy"] = any(
            os.path.normpath(c["path"]) == os.path.normpath(rp) or
            os.path.normpath(c["path"]).startswith(os.path.normpath(rp) + os.sep)
            for rp in referenced_paths
        )

    candidates_text = json.dumps(candidates, ensure_ascii=False, indent=2)  # (artık sadece log/debug için)

    # --- Büyük listeyi küçük gruplara böl -- 7B model 100+ klasörü tek seferde
    # işleyince bunalıp dil kaymasına (Çince karışması) uğruyordu.
    BATCH_SIZE = 15
    plan = []
    total_batches = (len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f">> Batch {batch_num}/{total_batches} analiz ediliyor ({len(batch)} klasör)...")
        plan.extend(classify_batch(batch, soul_context))

    # Model'in ürettiği plan'a, candidate'lardaki referans bilgisini geri işle
    # (model bu alanı çıktısında tekrar üretmeyebilir, biz garantiye alıyoruz)
    ref_lookup = {c["path"]: c.get("referenced_in_soul_hierarchy", False) for c in candidates}
    for item in plan:
        item["referenced_in_soul_hierarchy"] = ref_lookup.get(item.get("path"), False)

    # --- JSON planı kaydet ---
    with open(PLAN_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL_NAME,
            "plan": plan,
        }, f, ensure_ascii=False, indent=2)

    # --- İnsan okuması için markdown rapor üret ---
    lines = ["# Reorganizasyon Planı (DRY-RUN — hiçbir dosya taşınmadı)\n"]
    lines.append(f"_Üretilme zamanı: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n")

    if broken_refs:
        lines.append(f"\n## ⚠ SOUL.md'de Kırık Referanslar ({len(broken_refs)})\n")
        lines.append("Bu dosyalar SOUL.md zincirinde referans veriliyor ama diskte yok — "
                      "muhtemelen taşınmış/silinmiş, SOUL.md'nin güncellenmesi gerekebilir.\n")
        for br in broken_refs:
            lines.append(f"- `{br['from']}` -> bulunamayan: `{br['to']}`")

    for label in ["MIGRATE", "ARCHIVE", "DELETE_CANDIDATE", "DUPLICATE_SUSPECT", "KEEP"]:
        items = [p for p in plan if p.get("classification") == label]
        if not items:
            continue
        lines.append(f"\n## {label} ({len(items)})\n")
        for item in items:
            ref_tag = " 🔗 SOUL.md'de referanslı" if item.get("referenced_in_soul_hierarchy") else ""
            lines.append(f"- **{item['path']}**{ref_tag}")
            lines.append(f"  - Gerekçe: {item.get('reason', '-')}")
            if item.get("suggested_target"):
                lines.append(f"  - Önerilen hedef: `{item['suggested_target']}`")
            if item.get("duplicate_of"):
                lines.append(f"  - Muhtemel çift: `{item['duplicate_of']}`")

    with open(PLAN_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f">> Plan hazır: {PLAN_MD}")
    print(f">> Yapısal veri: {PLAN_JSON}")
    print(">> Hiçbir dosya taşınmadı/silinmedi. İnceleyip onayladıktan sonra")
    print("   taşıma işlemini uygulayacak script'i isteyin.")


if __name__ == "__main__":
    main()
