#!/usr/bin/env python3
"""DSI-Wiki servislerinin sağlığını kontrol eder, kurulu değilse kurar, düşükse kaldırır."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"
INSTANCES_DIR = ROOT / "JSONS" / "instances"
MULTI_SERVER_CONFIG = ROOT / "JSONS" / "DSI-Wiki-Multi-Server-Config.json"
SERVICES_DIR = ROOT / "SERVICES"
STATUS_PATH = ROOT / "STATUS.json"


def ensure_status_stub():
    """Guarantee STATUS.json exists after install, so /api/status doesn't 503 before the
    ingest daemon's first poll cycle overwrites it with live data."""
    if STATUS_PATH.exists():
        return
    STATUS_PATH.write_text(json.dumps({
        "service": "dsi-wiki-ingest",
        "last_poll_ts": None,
        "instances_loaded": None,
        "ollama_model": None,
        "service_version": "0.1a",
        "git_commit": None,
        "note": "stub written by DSI-Wiki-Service-Supervisor.py at install time; "
                "overwritten by the ingest daemon on its first poll cycle",
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  >> {STATUS_PATH.name} stub oluşturuldu (ingest daemon ilk poll'da güncelleyecek).")


def rebuild_multi_server_config():
    if not INSTANCES_DIR.is_dir():
        return
    routes = []
    default_base_dir = None
    default_layers = None
    for f in sorted(INSTANCES_DIR.glob("*.json")):
        instance = json.loads(f.read_text(encoding="utf-8"))
        if not instance.get("enabled"):
            continue
        if "keyword" not in instance or "tag" not in instance:
            default_base_dir = instance.get("base_dir", default_base_dir)
            default_layers = instance.get("layers", default_layers)
            continue
        routes.append({
            "keyword": instance["keyword"],
            "tag": instance["tag"],
            "base_dir": instance["base_dir"],
            "layers": instance.get("layers", {}),
        })

    config = json.loads(MULTI_SERVER_CONFIG.read_text(encoding="utf-8"))
    config["routes"] = routes
    if default_base_dir:
        config["default_base_dir"] = default_base_dir
    if default_layers:
        config["default_layers"] = default_layers
    MULTI_SERVER_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  >> {MULTI_SERVER_CONFIG.name} güncellendi ({len(routes)} route, JSONS/instances/'tan üretildi)")


def find_units() -> list[Path]:
    return sorted(SERVICES_DIR.glob("*.service")) + sorted(SERVICES_DIR.glob("*.target"))


def is_installed(unit: Path) -> bool:
    return (SYSTEMD_USER_DIR / unit.name).exists()


def install(unit: Path):
    dest = SYSTEMD_USER_DIR / unit.name
    dest.write_text(unit.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  >> kuruldu: {unit.name}")


def is_active(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", name],
        capture_output=True, text=True,
    )
    return result.stdout.strip() == "active"


def enable_now(name: str):
    subprocess.run(["systemctl", "--user", "enable", "--now", name], check=False)


def main():
    rebuild_multi_server_config()
    ensure_status_stub()

    units = find_units()
    if not units:
        print("Hiç .service/.target dosyası bulunamadı.")
        return

    reload_needed = False
    for unit in units:
        name = unit.name
        if not is_installed(unit):
            install(unit)
            reload_needed = True

    if reload_needed:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

    for unit in units:
        if unit.suffix == ".target":
            continue
        name = unit.name
        if is_active(name):
            print(f"  OK: {name}")
        else:
            print(f"  DUSUK, kaldiriliyor: {name}")
            enable_now(name)
            print(f"  OK (yeniden baslatildi): {name}" if is_active(name) else f"  !! basarisiz: {name}")


if __name__ == "__main__":
    main()
