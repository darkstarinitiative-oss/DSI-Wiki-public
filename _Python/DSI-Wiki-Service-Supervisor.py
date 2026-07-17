#!/usr/bin/env python3
"""DSI-Wiki servislerinin sağlığını kontrol eder, kurulu değilse kurar, düşükse kaldırır."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"
INSTANCES_DIR = ROOT.parent / "Instances"
MULTI_SERVER_CONFIG = ROOT / "IngestService" / "DSI-Wiki-Multi-Server-Config.json"


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
    print(f"  >> {MULTI_SERVER_CONFIG.name} güncellendi ({len(routes)} route, Instances/'tan üretildi)")


def find_units() -> list[Path]:
    return sorted(ROOT.glob("*/*.service")) + sorted(ROOT.glob("*/*.target"))


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
