#!/usr/bin/env python3
# Kullanım: python3 ingest_engine.py <raw_dosya_yolu>
# raw/ → documentation/ → llm/ → minified/ zinciri
import sys
import os
import time
import importlib.util
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR", "/home/user/LLM-Wiki-BASE")
MAX_RETRIES = 3
CALL_DELAY_SECONDS = 15  # RPM throttle — çağrılar arası bekleme


def _load_sibling(filename: str):
    spec = importlib.util.spec_from_file_location(filename, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call(prompt: str) -> str:
    provider_mod = _load_sibling("DSI-Wiki-LLM-Provider.py")
    select_provider, call_llm = provider_mod.select_provider, provider_mod.call_llm
    import yaml, requests

    cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
    all_providers = [p["name"] for p in cfg["providers"]]

    skip = []
    for attempt in range(MAX_RETRIES):
        candidates = [p for p in all_providers if p not in skip] or None
        provider = select_provider(candidates)
        if provider is None:
            return "[HATA: Sağlıklı provider bulunamadı]"
        try:
            return call_llm(provider, prompt, timeout=300)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                print(f"   !! {provider['name']} rate-limit, sonraki provider deneniyor...")
                skip.append(provider["name"])
            else:
                print(f"   !! {provider['name']} HTTP hata (deneme {attempt+1}): {e}")
        except Exception as e:
            print(f"   !! {provider['name']} hata (deneme {attempt+1}): {e}")
    return f"[HATA: Tüm denemeler başarısız ({MAX_RETRIES} deneme)]"


def _read(path: str) -> str:
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def main():
    if len(sys.argv) != 2:
        print("Kullanım: python3 ingest_engine.py <raw_dosya_yolu>")
        sys.exit(1)

    raw_path = sys.argv[1]
    if not os.path.exists(raw_path):
        print(f"!! Dosya bulunamadı: {raw_path}")
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(raw_path))[0]
    raw_content = open(raw_path, encoding="utf-8").read()

    doc_path = os.path.join(BASE_DIR, "documentation", f"{base_name}.md")
    llm_path = os.path.join(BASE_DIR, "llm", f"{base_name}.md")
    min_path = os.path.join(BASE_DIR, "minified", f"{base_name}.md")

    # 1) RAW → DOCUMENTATION
    prompts_mod = _load_sibling("DSI-Wiki-Layer-Prompts.py")
    doc_prompt, llm_prompt, minified_prompt = prompts_mod.doc_prompt, prompts_mod.llm_prompt, prompts_mod.minified_prompt
    prev_doc = _read(doc_path)
    prompt = doc_prompt(base_name, raw_content[:4000], prev_doc)
    doc_output = _call(prompt)

    if doc_output.startswith("[HATA:"):
        print(f"   !! documentation/{base_name}.md güncellenemedi")
        doc_output = prev_doc or doc_output
    else:
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(doc_output)

    # 2) DOCUMENTATION → LLM
    time.sleep(CALL_DELAY_SECONDS)
    llm_output = _call(llm_prompt(doc_output))

    if llm_output.startswith("[HATA:"):
        print(f"   !! llm/{base_name}.md güncellenemedi")
        llm_output = _read(llm_path) or llm_output
    else:
        with open(llm_path, "w", encoding="utf-8") as f:
            f.write(llm_output)

    # 3) LLM → MINIFIED
    time.sleep(CALL_DELAY_SECONDS)
    min_output = _call(minified_prompt(llm_output))

    if min_output.startswith("[HATA:"):
        print(f"   !! minified/{base_name}.md güncellenemedi")
        min_output = _read(min_path) or min_output
    else:
        with open(min_path, "w", encoding="utf-8") as f:
            f.write(min_output)

    # LOG
    log_path = os.path.join(BASE_DIR, "documentation", "log.md")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"- [{ts}] ingest: {base_name} (raw={raw_path})\n")

    print(f">> Tamamlandı: {base_name}")


if __name__ == "__main__":
    main()
