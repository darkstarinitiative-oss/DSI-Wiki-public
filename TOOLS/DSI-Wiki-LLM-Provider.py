"""LLM provider seçimi ve çağrısı. Hermes bağımlılığı yok."""
import os
import sqlite3
from pathlib import Path

import requests
import yaml

_WIKI_DIR = Path(__file__).parent
_CONFIG_PATH = _WIKI_DIR / "config.yaml"
_ENV_PATH = _WIKI_DIR / ".env"


def _load_env() -> None:
    """Proje .env dosyasını os.environ'a yükle (mevcut değerleri ezmez)."""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key not in os.environ:
            os.environ[key] = val


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text())


def _is_healthy(name: str, db_path: str) -> bool:
    """Hermes health DB varsa sorgula, yoksa True döndür (provider'ı dene)."""
    path = Path(db_path).expanduser()
    if not path.exists():
        return True
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT status FROM global_provider_health WHERE provider_id=?",
                (f"custom:{name}",),
            ).fetchone()
        return row is None or row[0] == "healthy"
    except Exception:
        return True


def select_provider(preferred: list[str] | None = None) -> dict | None:
    """Preferred listesinden sağlıklı ilk provider'ı döndür, yoksa config sırasını kullan."""
    _load_env()
    # Worker tarafından seçilen provider env var'dan geliyorsa direkt kullan
    override = os.environ.get("LLM_WIKI_PROVIDER_NAME")
    if override:
        return {
            "name": override,
            "base_url": os.environ.get("LLM_WIKI_PROVIDER_BASE_URL", ""),
            "model": os.environ.get("LLM_WIKI_PROVIDER_MODEL", ""),
            "api_key": os.environ.get("LLM_WIKI_PROVIDER_KEY", ""),
        }
    cfg = _load_config()
    db_path = cfg.get("hermes_health_db", "")
    providers = {p["name"]: p for p in cfg["providers"]}
    order = preferred if preferred is not None else cfg.get("preferred_order", list(providers))

    seen = set()
    for name in order + list(providers):
        if name in seen or name not in providers:
            continue
        seen.add(name)
        if _is_healthy(name, db_path):
            p = providers[name]
            return {
                "name": name,
                "base_url": p["base_url"],
                "model": p["model"],
                "api_key": os.environ.get(p.get("key_env") or "", ""),
            }
    return None


def call_llm(provider: dict, prompt: str, timeout: int = 120) -> str:
    """OpenAI-compatible /chat/completions. Retry yok — caller yönetir."""
    resp = requests.post(
        f"{provider['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {provider['api_key']}"},
        json={
            "model": provider["model"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
