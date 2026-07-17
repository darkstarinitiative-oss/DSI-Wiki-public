#!/usr/bin/env python3
# =============================================================================
# wiki_server.py
# Ne yapar: LLM-Wiki-BASE'i (raw/documentation/llm/minified katmanları) bir
#   MCP server olarak dışarı açar. İKİ modda kullanılabilir:
#
#   1) MOUNT MODU (asıl istediğiniz): Bu dosyadaki `app` objesi, mevcut
#      gateway'inize (0.0.0.0:8420'de çalışan) import edilip "/LLM-wiki"
#      alt-yoluna mount edilebilecek bir ASGI app. Gateway'iniz FastAPI ise:
#
#          from mcp_wiki_server import app as wiki_app
#          main_app.mount("/LLM-wiki", wiki_app)
#
#      Ham Starlette kullanıyorsanız:
#
#          from starlette.routing import Mount
#          from mcp_wiki_server import app as wiki_app
#          routes.append(Mount("/LLM-wiki", app=wiki_app))
#
#      Sonuç: https://mcp.dsigames.com.tr/LLM-wiki üzerinden erişilebilir olur,
#      mevcut 8420'deki servisi durdurmanıza gerek YOK.
#
#   2) STANDALONE TEST MODU: python3 wiki_server.py --port 8421
#      ile tek başına ayrı bir portta çalıştırıp curl ile test edebilirsiniz,
#      mount etmeden önce doğru çalıştığından emin olmak için.
#
#   Sunulan tool'lar:
#     - wiki_list_topics(layer)         : bir katmandaki tüm konu adları
#     - wiki_get(topic, layer)          : bir konunun tam içeriği (tek katman)
#     - wiki_search(query, layer)       : basit metin araması (layer='all' da olur)
#     - wiki_ingest_raw(topic, content) : YENİ HAM VERİ yükler, tüm ingest
#                                          zincirini (doc->llm->minified) çalıştırır,
#                                          sonuçtaki özeti döner
#
# Kurulum: bash 18_install_mcp_deps.sh  (önce)
# =============================================================================
import argparse
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR", os.path.expanduser("~/LLM-Wiki-BASE"))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAYERS = ("raw", "documentation", "llm", "minified")

# NOT: Daha önce burada TransportSecuritySettings ile allowed_hosts/allowed_origins
# elle kısıtlanıyordu. Sistemde zaten çalışan (codebase_mcp.py) örnek hiçbir
# transport_security override'ı YAPMADAN, sadece host="0.0.0.0" ile kuruluyor --
# FastMCP host'un loopback olmadığını görünce DNS-rebinding korumasını zaten
# otomatik devre dışı bırakıyor. Aynı basit pattern'e dönüyoruz; hem Invalid
# Host Header riskini hem de gereksiz karmaşıklığı ortadan kaldırır.
mcp = FastMCP("llm-wiki", host="0.0.0.0")


def _layer_dir(layer: str) -> str:
    if layer not in LAYERS:
        raise ValueError(f"Geçersiz katman: '{layer}'. Olası değerler: {LAYERS}")
    return os.path.join(BASE_DIR, layer)


@mcp.tool()
def wiki_list_topics(layer: str = "minified") -> list[str]:
    """Bir katmandaki (raw/documentation/llm/minified) tüm konu adlarını listeler.
    Örn: wiki_list_topics("minified") -> ["basic", "gateway", "priority__.hermes__SOUL", ...]"""
    d = _layer_dir(layer)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md"))


@mcp.tool()
def wiki_get(topic: str, layer: str = "minified") -> str:
    """Belirli bir konunun, belirli bir katmandaki TAM içeriğini döner.
    layer='minified' en hızlı özet, 'documentation' en detaylı tarihçeli hali."""
    path = os.path.join(_layer_dir(layer), f"{topic}.md")
    if not os.path.exists(path):
        return f"(bulunamadı: {layer}/{topic}.md)"
    return open(path, encoding="utf-8").read()


@mcp.tool()
def wiki_search(query: str, layer: str = "minified") -> str:
    """Bir katmanda basit (case-insensitive) metin araması yapar, eşleşen
    konuların içeriğini döner. layer='all' verilirse dört katmanda da arar.
    En fazla 10 eşleşme, her biri en fazla 1500 karakterle sınırlı döner."""
    layers_to_search = LAYERS if layer == "all" else (layer,)
    query_lower = query.lower()
    results = []
    for lyr in layers_to_search:
        d = _layer_dir(lyr)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(d, fname)
            content = open(path, encoding="utf-8", errors="ignore").read()
            if query_lower in content.lower() or query_lower in fname.lower():
                results.append(f"### [{lyr}] {fname[:-3]}\n{content[:1500]}")
    if not results:
        return f"'{query}' için hiçbir sonuç bulunamadı (katman: {layer})."
    return "\n\n---\n\n".join(results[:10])


@mcp.tool()
def wiki_ingest_raw(topic: str, content: str) -> str:
    """YENİ HAM VERİ yükler: content'i raw/<topic>.md olarak kaydeder ve tüm
    ingest zincirini (documentation -> llm -> minified) senkron çalıştırır.
    Sonuç olarak minified özetini döner. Uzun sürebilir (birkaç Ollama çağrısı)."""
    safe_topic = "".join(c for c in topic if c.isalnum() or c in ("-", "_", ".")) or "untitled"
    raw_path = os.path.join(BASE_DIR, "raw", f"{safe_topic}.md")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(content)

    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "ingest_engine.py"), raw_path],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        return f"Ingest başarısız oldu: {result.stderr[-500:]}"

    min_path = os.path.join(BASE_DIR, "minified", f"{safe_topic}.md")
    summary = (open(min_path, encoding="utf-8").read()
               if os.path.exists(min_path) else "(özet üretilemedi)")
    return f"'{safe_topic}' başarıyla işlendi.\n\nÖzet:\n{summary}"


# Gateway'inize mount edeceğiniz ASGI app objesi -- Streamable HTTP transport
# kullanır, MCP spesifikasyonunun önerdiği güncel yöntem (SSE'nin yerini alıyor).
# Gateway'inizde: main_app.mount("/LLM-wiki", app)
app = mcp.streamable_http_app()

# ÖNEMLİ: FastMCP'nin Streamable HTTP transport'u bir "session manager"
# kullanır ve bu, ana uygulamanın lifespan (başlangıç) event'i içinde
# başlatılmak ZORUNDADIR -- yoksa her istek 500 Internal Server Error
# ("task group başlatılmadı") ile patlar. Mount eden tarafta (api.py'de) bu
# context manager'ı FastAPI'nin kendi lifespan'ına bağlamanız gerekiyor:
#
#   import contextlib
#   from llm_wiki_mcp import app as llm_wiki_app, lifespan as llm_wiki_lifespan
#
#   @contextlib.asynccontextmanager
#   async def combined_lifespan(app):
#       async with llm_wiki_lifespan(app):
#           yield
#
#   app = FastAPI(..., lifespan=combined_lifespan)   # mevcut FastAPI(...) çağrısına ekleyin
#   app.mount("/LLM-wiki", llm_wiki_app)
import contextlib


@contextlib.asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():
        yield


if __name__ == "__main__":
    # Standalone test modu -- mount etmeden önce tek başına doğrulamak için.
    # Gerçek kullanımda (mount modunda) bu blok hiç çalışmaz, sadece `app`
    # objesi import edilir.
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8421,
                         help="Standalone test için port (varsayılan: 8421, "
                              "8420'deki asıl gateway ile çakışmasın diye farklı)")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f">> Standalone test modu: http://{args.host}:{args.port}/")
    print(f"   Mount modunda bu port kullanılmaz -- gateway'inize 'app' objesini")
    print(f"   import edip /LLM-wiki yoluna mount edin (dosyanın başındaki yorumlara bakın).")
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")
