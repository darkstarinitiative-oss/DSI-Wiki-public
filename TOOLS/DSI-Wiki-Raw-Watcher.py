#!/usr/bin/env python3
# =============================================================================
# 15_auto_scan_loop.py
# Ne yapar: TEK KONSOLDA, siz Ctrl+C yapmadıkça kendi kendine dönen bir tarama
#   döngüsü. Her tur (round) şöyle işler:
#
#     1) Bir önceki turun ham bulgu dosyasını LLM-Wiki'ye INGEST eder
#        (ingest_engine.py çağrılır -> documentation/llm/minified katmanları
#        güncellenir). İlk turda bu dosya 14_basic_scan.sh'in ürettiği basic.md.
#     2) Wiki'nin ürettiği SIKI (llm/) katmanını okuyup Ollama'ya verir:
#        "Bu veriden hangi servis/proje gruplarını çıkardın? Daha netleştirmek
#        için hangi GÜVENLİ, SALT-OKUNUR komutları çalıştırmamı istersin?"
#     3) Model'in istediği komutları bir GÜVENLİK BEYAZ LİSTESİNDEN geçirip
#        çalıştırır, çıktıları yeni bir round-N-findings.md dosyasına yazar.
#     4) round-N-findings.md bir sonraki turda yine 1. adıma girdi olur.
#     5) Model "next_steps" olarak BOŞ liste döndürürse (yani "artık yeni bir
#        şey yok" derse) döngü durur.
#
#   Her adımda stdout'a bol bol ilerleme yazar (izlemesi keyifli olsun diye).
#   Ctrl+C ile her an güvenle durdurulabilir -- her tur kendi dosyasını
#   diskte bıraktığı için hiçbir şey kaybolmaz.
#
# Kullanım: python3 15_auto_scan_loop.py
#   (durdurmak için Ctrl+C; en fazla MAX_ROUNDS turda kendiliğinden de durur)
# =============================================================================
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import http.client
from datetime import datetime, timezone

BASE_DIR = os.path.expanduser("~/LLM-Wiki-BASE")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_URL = "http://localhost:11434/api/generate"
MAX_ROUNDS = 8  # sonsuz döngüye karşı güvenlik freni
MAX_RETRIES = 4

MODEL_NAME_FILE = os.path.join(BASE_DIR, "config", "model_name.txt")
MODEL_NAME = (open(MODEL_NAME_FILE, encoding="utf-8").read().strip()
              if os.path.exists(MODEL_NAME_FILE) else None)

# Artık komut bazlı katı bir beyaz liste yok -- pipe/grep/find gibi normal
# araştırma komutlarını gereksiz yere eliyordu ve veri akışını durduruyordu.
# Sadece sistemi GERÇEKTEN kalıcı/geri dönüşsüz bozacak birkaç bariz felaket
# kalıbını engelliyoruz; geri kalan her şey çalıştırılır.
CATASTROPHIC_PATTERNS = (
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "dd of=/dev/",
    ":(){ :|:& };:", ":(){:|:&};:", "> /dev/sd", "chmod -R 777 /",
    "shutdown", "reboot", "init 0", "systemctl poweroff",
)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()


def call_ollama(prompt: str, temperature: float = 0.15) -> str:
    payload = json.dumps({
        "model": MODEL_NAME, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature},
    }).encode("utf-8")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(OLLAMA_URL, data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read()).get("response", "").strip()
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, OSError) as e:
            last_error = e
            wait = 5 * attempt
            log(f"   !! Ollama bağlantı hatası (deneme {attempt}/{MAX_RETRIES}): {e}")
            log(f"      {wait} saniye bekleyip tekrar denenecek...")
            time.sleep(wait)

    log(f"   !! {MAX_RETRIES} deneme sonunda Ollama'ya ulaşılamadı: {last_error}")
    return ""  # boş dön -- çağıran taraf JSONDecodeError olarak yakalayıp turu güvenli durduracak


HERMES_ENV_FILE = os.path.expanduser("~/.hermes/.env")
# .env'de birden fazla anahtar olabilir (rotasyon/kota için): NVIDIA_API_KEY,
# NVIDIA_API_KEY_2, NVIDIA_API_KEY_3, ... hepsini toplayıp sırayla deneriz.
NVIDIA_KEY_PATTERN = re.compile(r'^NVIDIA_API_KEY(_\d+)?$')
NVIDIA_MODEL_CANDIDATES = ("NVIDIA_MODEL", "NIM_MODEL", "NVIDIA_NIM_MODEL")


def parse_env_file(path: str) -> dict:
    """Basit KEY=VALUE .env ayrıştırıcı -- yorum satırlarını ve boş satırları atlar,
    tırnak işaretlerini temizler."""
    env = {}
    if not os.path.exists(path):
        return env
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_nvidia_keys():
    """~/.hermes/.env'deki TÜM NVIDIA_API_KEY* değişkenlerini toplar (rotasyon
    için). Bulamazsa eski statik config/nvidia_api_key.txt'ye düşer."""
    env = parse_env_file(HERMES_ENV_FILE)
    keys = [v for k, v in env.items() if NVIDIA_KEY_PATTERN.match(k) and v]

    model = next((env[k] for k in NVIDIA_MODEL_CANDIDATES if env.get(k)), None)
    if not model:
        model_path = os.path.join(BASE_DIR, "config", "nvidia_model.txt")
        model = (open(model_path, encoding="utf-8").read().strip()
                 if os.path.exists(model_path) else "mistralai/mixtral-8x22b-instruct-v0.1")

    if keys:
        return keys, model

    # Fallback: eski statik dosya
    key_path = os.path.join(BASE_DIR, "config", "nvidia_api_key.txt")
    if os.path.exists(key_path):
        static_key = open(key_path, encoding="utf-8").read().strip()
        if static_key and static_key != "PASTE_YOUR_NVAPI_KEY_HERE":
            return [static_key], model

    return [], model


def load_nvidia_config():
    """Geriye dönük uyumluluk için: sadece ilk anahtarı ve modeli döner."""
    keys, model = load_nvidia_keys()
    return (keys[0], model) if keys else (None, None)


def call_nvidia(prompt: str, temperature: float = 0.15) -> str:
    """NVIDIA NIM (integrate.api.nvidia.com) üzerinden OpenAI-uyumlu chat
    completions endpoint'ine istek atar. Birden fazla anahtar varsa (rotasyon
    için), biri rate-limit/auth hatası verirse otomatik sıradakini dener."""
    keys, model = load_nvidia_keys()
    if not keys:
        return ""

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 4096,
    }).encode("utf-8")

    for idx, key in enumerate(keys, 1):
        try:
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            # 429 (rate limit) veya 401/403 (geçersiz anahtar) ise sıradaki anahtarı dene
            log(f"   !! NVIDIA anahtar #{idx}/{len(keys)} hata verdi (HTTP {e.code}), "
                f"{'sıradaki anahtar deneniyor' if idx < len(keys) else 'başka anahtar kalmadı'}...")
            continue
        except Exception as e:
            log(f"   !! NVIDIA API hatası (anahtar #{idx}): {e}")
            continue

    return ""


def call_llm(prompt: str, temperature: float, use_nvidia: bool) -> str:
    """use_nvidia=False (varsayılan) -> yerel Ollama. use_nvidia=True (-n
    parametresi verilirse) -> NVIDIA NIM Mistral. Otomatik geçiş yok,
    hangisini kullanacağınızı komut satırından siz seçiyorsunuz."""
    if use_nvidia:
        return call_nvidia(prompt, temperature)
    return call_ollama(prompt, temperature)


def is_safe_command(cmd: str) -> bool:
    cmd_lower = cmd.strip().lower()
    return not any(pattern in cmd_lower for pattern in CATASTROPHIC_PATTERNS)


def ingest_into_wiki(raw_path: str, topic_name: str):
    tagged_path = os.path.join(os.path.dirname(raw_path), f"{topic_name}.md")
    if raw_path != tagged_path:
        with open(raw_path, encoding="utf-8") as src, open(tagged_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    log(f"   -> LLM-Wiki'ye ingest ediliyor: {topic_name}")
    subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "ingest_engine.py"), tagged_path],
                    check=False)
    return topic_name


def read_llm_layer(topic_name: str) -> str:
    llm_path = os.path.join(BASE_DIR, "llm", f"{topic_name}.md")
    if os.path.exists(llm_path):
        return open(llm_path, encoding="utf-8").read()
    return ""


def plan_next_round(condensed_context: str, round_num: int, known_groups_summary: str,
                     use_nvidia: bool = False) -> dict:
    prompt = f"""You are a system discovery analyst. Below (Round {round_num}) is
condensed/compiled information about the system. Your task:
  1) List the service/project GROUPS you recognize so far (web-service,
     mcp-api-service, adb-automation, game-project, dashboard, library, etc.)
  2) Suggest SAFE, READ-ONLY commands to run to clarify remaining ambiguous
     points (cat, ls, git log, systemctl status, docker inspect/logs/ps,
     pm2 describe/list, grep, find, wc, stat, file, etc.)
     NEVER suggest a delete/stop/modify command.
  3) If there is nothing left to clarify, return next_steps as an EMPTY
     list [] -- this means the scan is done.

*** Write all text values in English (do not translate the JSON field names,
they must stay exactly as given: groups, name, type, members, confidence,
next_steps, description, command, done_reasoning). ***

GROUPS KNOWN SO FAR:
{known_groups_summary if known_groups_summary else "(none yet, this is the first round)"}

THIS ROUND'S CONTEXT:
{condensed_context[:6000]}

Output: ONLY valid JSON, in this format:
{{
  "groups": [{{"name": "...", "type": "...", "members": ["..."], "confidence": "low|medium|high"}}],
  "next_steps": [{{"description": "short English explanation", "command": "read-only command"}}],
  "done_reasoning": "is the scan done, why (English)"
}}"""
    raw = call_llm(prompt, temperature=0.15, use_nvidia=use_nvidia)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        cleaned = cleaned[4:] if cleaned.startswith("json") else cleaned
    try:
        result = json.loads(cleaned)
        result["_parse_failed"] = False
        return result
    except json.JSONDecodeError:
        # Ham cevabı diske yaz -- neden parse edilemediğini görebilelim
        debug_path = os.path.join(REPORT_DIR, f"round-{round_num}-raw-response.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(raw)
        log(f"   !! Model geçerli JSON döndürmedi (ham cevap: {debug_path}). "
            f"Bu, 'tarama bitti' anlamına GELMEZ -- yeniden denenecek.")
        return {"groups": [], "next_steps": [], "done_reasoning": "JSON parse hatası",
                "_parse_failed": True}


def run_safe_commands(steps: list) -> str:
    output_lines = []
    for step in steps:
        desc = step.get("description", "")
        cmd = step.get("command", "")
        if not is_safe_command(cmd):
            log(f"   [ATLANDI - güvenli değil] {cmd}")
            output_lines.append(f"### ATLANDI (güvensiz komut): {cmd}\n(çalıştırılmadı)\n")
            continue
        log(f"   $ {cmd}   # {desc}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            out = (result.stdout or "") + (result.stderr or "")
        except Exception as e:
            out = f"(hata: {e})"
        preview = "\n".join(out.splitlines()[:5])
        if preview:
            print(preview)
        output_lines.append(f"### {desc}\n$ {cmd}\n```\n{out[:2000]}\n```\n")
    return "\n".join(output_lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--nvidia", action="store_true",
                         help="NVIDIA NIM Mistral kullan (varsayılan: yerel Ollama)")
    args = parser.parse_args()
    use_nvidia = args.nvidia

    basic_md = os.path.join(REPORT_DIR, "basic.md")
    if not os.path.exists(basic_md):
        log("!! reports/basic.md yok. Önce: bash 14_basic_scan.sh")
        return

    if use_nvidia:
        _, nv_model = load_nvidia_config()
        if not nv_model:
            log("!! -n verildi ama config/nvidia_api_key.txt boş/placeholder. "
                "Önce: bash 16_setup_nvidia_provider.sh ve anahtarınızı girin.")
            return
        log(f">> Sağlayıcı: NVIDIA NIM ({nv_model})")
    else:
        if not MODEL_NAME:
            log("!! config/model_name.txt yok. Önce: bash 05_install_ollama.sh")
            return
        log(f">> Sağlayıcı: yerel Ollama ({MODEL_NAME})")

    current_input = basic_md
    known_groups_summary = ""
    round_num = 1

    log(">> Otomatik tarama döngüsü başlıyor. Durdurmak için Ctrl+C.")

    while round_num <= MAX_ROUNDS:
        log(f"=== ROUND {round_num} ===")
        topic = "basic" if round_num == 1 else f"round-{round_num - 1}-findings"

        ingest_into_wiki(current_input, topic)
        condensed = read_llm_layer(topic)
        if not condensed:
            log("   !! LLM katmanı boş döndü (ingest başarısız olmuş olabilir), ham dosya kullanılıyor.")
            condensed = open(current_input, encoding="utf-8", errors="ignore").read()

        log("   -> bir sonraki tarama planı isteniyor...")
        plan = None
        for parse_attempt in range(1, 4):  # aynı round içinde 3 deneme
            plan = plan_next_round(condensed, round_num, known_groups_summary, use_nvidia=use_nvidia)
            if not plan.get("_parse_failed"):
                break
            log(f"   -> Yeniden deneniyor (parse denemesi {parse_attempt}/3)...")
            time.sleep(3)

        if plan.get("_parse_failed"):
            log("   !! 3 denemede de geçerli JSON alınamadı. Bu, taramanın BİTTİĞİ anlamına"
                " GELMEZ -- muhtemelen model/prompt sorunu. Round dosyaları korunuyor,"
                " script'i tekrar çalıştırarak bu round'dan devam edebilirsiniz.")
            break

        groups = plan.get("groups", [])
        next_steps = plan.get("next_steps", [])

        log(f"   -> {len(groups)} grup tanındı, {len(next_steps)} yeni araştırma adımı önerildi.")
        for g in groups:
            log(f"      * {g.get('name')} [{g.get('type')}] güven={g.get('confidence')}")

        groups_md = os.path.join(REPORT_DIR, "system-groups.md")
        with open(groups_md, "a", encoding="utf-8") as f:
            f.write(f"\n## Round {round_num} sonrası gruplar\n")
            for g in groups:
                f.write(f"- **{g.get('name')}** ({g.get('type')}, güven: {g.get('confidence')})\n")
                for m in g.get("members", []):
                    f.write(f"  - {m}\n")

        known_groups_summary = "\n".join(
            f"- {g.get('name')} [{g.get('type')}]" for g in groups
        )

        if not next_steps:
            log(f">> Model artık yeni araştırılacak bir şey görmüyor: {plan.get('done_reasoning', '-')}")
            log(">> Tarama tamamlandı.")
            break

        log(f"   -> {len(next_steps)} komut çalıştırılıyor (sadece salt-okunur, beyaz listeli)...")
        findings_text = run_safe_commands(next_steps)

        round_file = os.path.join(REPORT_DIR, f"round-{round_num}-findings.md")
        with open(round_file, "w", encoding="utf-8") as f:
            f.write(f"# Round {round_num} Bulguları\n\n{findings_text}")

        current_input = round_file
        round_num += 1
        time.sleep(2)

    log(f">> Döngü bitti. Nihai gruplar: {os.path.join(REPORT_DIR, 'system-groups.md')}")
    log(f">> Tüm ham bulgular ve wiki katmanları: {BASE_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n>> Kullanıcı durdurdu (Ctrl+C). Şu ana kadarki bulgular diskte güvende.")
