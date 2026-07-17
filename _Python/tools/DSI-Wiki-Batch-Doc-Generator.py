#!/usr/bin/env python3
"""
doc_batch.py — 7 DSI projesinin kapsamlı dökümantasyonunu üretir.
Çalıştırma: python3 /home/ozan/LLM-Wiki/doc_batch.py

Her proje için:
  1. raw kaynak dosyaları + 5 şablonu okur
  2. LLM'e sıfır-halüsinasyon prompt gönderir
  3. Doldurulmuş dökümantasyonu v2/documentation/'a yazar
  4. llm + minified sıkıştırmalarını üretir
  5. DOT diyagramını çıkarır → PNG oluşturur
"""
import os
import sys
import time
import re
import subprocess
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

WIKI_DIR = Path(__file__).parent


def _load_sibling(filename: str):
    spec = importlib.util.spec_from_file_location(filename, WIKI_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
V1_RAW = Path("/home/ozan/LLM-Wiki-BASE/raw")
V2_BASE = Path("/home/ozan/LLM-Wiki-BASE-v2")
LOG_FILE = Path("/home/ozan/LLM-Wiki/batch.log")
DELAY = 20  # saniye (provider rate-limit)

sys.path.insert(0, str(WIKI_DIR))

TEMPLATES = [
    "template-software-component.md",
    "template-project-overview.md",
    "template-workflow-process.md",
    "template-infrastructure.md",
    "template-api-endpoint.md",
]

PROJECTS = [
    {
        "topic": "DSIDispatcher",
        "name": "DSI Dispatcher++",
        "raw_files": ["DSIDispatcher.md", "Dispatcher-plus-plus.md"],
        "code_dir": "/home/ozan/READY/Dispatcher-plus-plus",
    },
    {
        "topic": "DSIGenerativeVisualContentServer",
        "name": "DSI Generative Visual Content Server (GVCS)",
        "raw_files": [
            "DSIGenerativeVisualContentServer.md",
            "DSI-GVCS.md",
            "dsi-gvcs.md",
            "DSI-GVCS-Egitim-Veri-Hazirlama.md",
        ],
        "code_dir": "/home/ozan/codebase/projects/dsi-gvcs",
    },
    {
        "topic": "DSIHermesProviderManagement",
        "name": "DSI Hermes Provider Management",
        "raw_files": [
            "DSIHermesProviderManagement.md",
            "hermes-custom-provider-management.md",
            "hermes-infra-monitor-cron.md",
            "planned-migration__hermes-custom-provider-management.md",
        ],
        "code_dir": "/home/ozan/READY/Hermes-CustomProviderManagement",
    },
    {
        "topic": "DSISocialMediaAutomation",
        "name": "DSI Social Media Automation",
        "raw_files": [
            "DSISocialMediaAutomation.md",
            "DSISM-AUTOMATIONSocialMedia.md",
            "Social-Media-Automation.md",
            "hermes-social-automation.md",
            "Twitter-Automation.md",
            "Instagram-Activity-Flow.md",
            "SocialMedia-AppMaps.md",
            "Social-Media-Hashtag-Strategy.md",
            "DSI-Social-Media.md",
        ],
        "code_dir": "/home/ozan/codebase/projects/hermes-social-automation",
    },
    {
        "topic": "DSISystemCore",
        "name": "DSI System Core",
        "raw_files": ["DSISystemCore.md", "DSI-System.md", "DSI-MAINBOARD.md"],
        "code_dir": "/home/ozan/codebase/projects/DSI-System",
    },
    {
        "topic": "DSIYamYamLar",
        "name": "DSI YamYamLar Task Optimization",
        "raw_files": ["DSIYamYamLarTaskOptimization.md", "YamYamLar.md", "yamyamlar.md"],
        "code_dir": "/home/ozan/codebase/projects/yamyamlar",
    },
    {
        "topic": "DSIIhaleMobil",
        "name": "DSI İhaleMobil",
        "raw_files": ["DSIİhaleMobil.md", "ihalemobil.md"],
        "code_dir": "/home/ozan/codebase/projects/ihalemobil",
    },
]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[doc_batch] {ts} {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def read_file(path) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    return ""


def get_file_tree(code_dir: str, max_lines: int = 80) -> str:
    d = Path(code_dir)
    if not d.is_dir():
        return "(kod dizini bulunamadı)"
    try:
        result = subprocess.run(
            ["find", str(d), "-type", "f", "-not", "-path", "*/.*",
             "-not", "-name", "*.pyc", "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/__pycache__/*"],
            capture_output=True, text=True, timeout=10
        )
        lines = sorted(result.stdout.strip().splitlines())
        lines = [l.replace(str(d) + "/", "") for l in lines]
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... (+{len(lines) - max_lines} daha)"]
        return "\n".join(lines)
    except Exception as e:
        return f"(dosya listesi alınamadı: {e})"


def build_prompt(project: dict, raw_sources: str, code_tree: str, templates: str) -> str:
    name = project["name"]
    return f"""Sen bir teknik dökümantasyon uzmanısın. Aşağıdaki ham kaynak dosyaları, {name} adlı yazılım projesine ait gerçek verilerdir.

## !! KRİTİK KURAL: SIFIR HALÜSÜNASYON !!
1. SADECE kaynak dosyalarda açıkça yazılmış bilgileri kullan.
2. Kaynaklarda bulunmayan her alan için: `—` yaz. ASLA tahmin etme, doldurmaya çalışma.
3. Her doldurduğun bölümün sonuna mutlaka şunu ekle: `> kaynak: [hangi dosya(lar)dan geldiği]`
4. Şablon placeholder'larını (`[...]`) gerçek veriyle değiştir ya da `—` ile bırak.
5. Şablonlardaki yapıyı koru. Bölüm başlıklarını silme.

---

## PROJE: {name}

---

## KAYNAK DOSYALAR (ham notlar — bu veriden çalış)

{raw_sources}

---

## KOD DİZİNİ DOSYA LİSTESİ (içerik değil, sadece yapı)

```
{code_tree}
```

---

## ŞABLONLAR (bunları kaynak verisiyle doldur)

{templates}

---

## GÖREV

Yukarıdaki 5 şablonu, kaynak dosyalardaki gerçek verilerle doldur.
- Tüm bölümleri sırayla işle (hiçbirini atlama).
- Her bölümde `> kaynak:` satırını ekle.
- Kaynaklarda yoksa `—` bırak.
- PITCH alt bölümlerini de doldur (kaynaklarda varsa neden/fark/motivasyon bilgisi).

Çıktının en sonuna aşağıdaki formatla proje mimarisi diyagramını ekle:

## ARCHITECTURE DIAGRAM
```dot
digraph {project["topic"]} {{
  rankdir=LR;
  node [shape=box, style=filled, fillcolor=lightblue];
  // Sadece kaynak dosyalardan çıkarılan bileşenler
  // Bilinmeyenler için bu bloğu boş bırak
}}
```
"""


def call_llm_robust(prompt: str, timeout: int = 600) -> str:
    provider_mod = _load_sibling("DSI-Wiki-LLM-Provider.py")
    select_provider, call_llm = provider_mod.select_provider, provider_mod.call_llm
    import requests

    for attempt in range(3):
        provider = select_provider()
        if provider is None:
            log("HATA: Sağlıklı provider bulunamadı, 30s bekleniyor...")
            time.sleep(30)
            continue
        try:
            log(f"  LLM çağrısı: {provider['name']} (deneme {attempt+1})")
            return call_llm(provider, prompt, timeout=timeout)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                log(f"  Rate-limit: {provider['name']}, 60s bekleniyor...")
                time.sleep(60)
            else:
                log(f"  HTTP hata: {e}")
        except Exception as e:
            log(f"  Hata: {e}")
        time.sleep(DELAY)
    return "[HATA: Tüm LLM denemeleri başarısız]"


def compress_to_llm(doc_content: str) -> str:
    llm_prompt = _load_sibling("DSI-Wiki-Layer-Prompts.py").llm_prompt
    return call_llm_robust(llm_prompt(doc_content), timeout=300)


def compress_to_minified(llm_content: str) -> str:
    minified_prompt = _load_sibling("DSI-Wiki-Layer-Prompts.py").minified_prompt
    return call_llm_robust(minified_prompt(llm_content), timeout=180)


def extract_dot(text: str) -> str | None:
    """Metinden DOT diyagramını çıkarır."""
    m = re.search(r'```dot\s*(digraph[\s\S]*?)\s*```', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'(digraph\s+\w+\s*\{[\s\S]*?\})', text)
    if m:
        return m.group(1).strip()
    return None


def process_project(project: dict):
    topic = project["topic"]
    log(f"=== {topic} başlıyor ===")

    # Kaynak dosyaları oku
    raw_parts = []
    for fname in project["raw_files"]:
        path = V1_RAW / fname
        content = read_file(path)
        if content:
            raw_parts.append(f"### [{fname}]\n\n{content}")
        else:
            log(f"  UYARI: {fname} bulunamadı, atlanıyor")
    raw_sources = "\n\n---\n\n".join(raw_parts) if raw_parts else "(kaynak dosya bulunamadı)"

    # Kod dizini dosya ağacı
    code_tree = get_file_tree(project.get("code_dir", ""))

    # Şablonları oku
    template_parts = []
    for tname in TEMPLATES:
        content = read_file(V1_RAW / tname)
        if content:
            template_parts.append(f"### [{tname}]\n\n{content}")
    templates_str = "\n\n---\n\n".join(template_parts)

    # Ana dökümantasyon prompt'u
    prompt = build_prompt(project, raw_sources, code_tree, templates_str)
    log(f"  Prompt hazır ({len(prompt)} karakter), LLM çağrılıyor...")

    doc_output = call_llm_robust(prompt, timeout=600)
    if doc_output.startswith("[HATA:"):
        log(f"  HATA: documentation/{topic}.md üretilemedi, atlanıyor")
        return

    # DOT diyagramını çıkar ve kaydet
    dot_src = extract_dot(doc_output)
    if dot_src:
        dot_path = V2_BASE / "raw" / f"{topic}-diagram.dot"
        dot_path.write_text(dot_src, encoding="utf-8")
        png_path = V2_BASE / "raw" / f"{topic}-diagram.png"
        try:
            sys.path.insert(0, str(WIKI_DIR))
            dot_to_png = _load_sibling("DSI-Wiki-Diagram-Generator.py").dot_to_png
            ok = dot_to_png(dot_src, str(png_path))
            log(f"  Diyagram: {'OK' if ok else 'UYARI: PNG üretilemedi'} → {png_path}")
        except Exception as e:
            log(f"  Diyagram hatası: {e}")
    else:
        log("  UYARI: DOT diyagramı bulunamadı")

    # v2/documentation/
    doc_path = V2_BASE / "documentation" / f"{topic}.md"
    doc_path.write_text(doc_output, encoding="utf-8")
    log(f"  documentation/{topic}.md yazıldı ({len(doc_output)} karakter)")

    # v2/raw/ (kaynak kopyası)
    raw_copy_path = V2_BASE / "raw" / f"{topic}.md"
    raw_copy_path.write_text(raw_sources, encoding="utf-8")

    # llm katmanı
    time.sleep(DELAY)
    log("  llm katmanı üretiliyor...")
    llm_output = compress_to_llm(doc_output)
    if not llm_output.startswith("[HATA:"):
        (V2_BASE / "llm" / f"{topic}.md").write_text(llm_output, encoding="utf-8")
        log(f"  llm/{topic}.md yazıldı")
    else:
        log(f"  UYARI: llm/{topic}.md üretilemedi")
        llm_output = doc_output

    # minified katmanı
    time.sleep(DELAY)
    log("  minified katmanı üretiliyor...")
    min_output = compress_to_minified(llm_output)
    if not min_output.startswith("[HATA:"):
        (V2_BASE / "minified" / f"{topic}.md").write_text(min_output, encoding="utf-8")
        log(f"  minified/{topic}.md yazıldı")
    else:
        log(f"  UYARI: minified/{topic}.md üretilemedi")

    log(f"=== {topic} tamamlandı ===\n")


def main():
    log("doc_batch.py başlıyor")
    log(f"V2 hedef: {V2_BASE}")

    # v2 dizin yapısını garantile
    for sub in ("raw", "documentation", "llm", "minified"):
        (V2_BASE / sub).mkdir(parents=True, exist_ok=True)

    for i, project in enumerate(PROJECTS):
        try:
            process_project(project)
        except Exception as e:
            log(f"HATA [{project['topic']}]: {e}")
        if i < len(PROJECTS) - 1:
            log(f"  Sonraki proje için {DELAY}s bekleniyor...")
            time.sleep(DELAY)

    log("doc_batch.py tamamlandı — tüm projeler işlendi.")


if __name__ == "__main__":
    main()
