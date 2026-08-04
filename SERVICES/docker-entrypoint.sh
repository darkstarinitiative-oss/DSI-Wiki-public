#!/bin/sh
# Regenerates JSONS/DSI-Wiki-Multi-Server-Config.json from JSONS/instances/*.json before
# starting the real command (ingest or gateway) — idempotent, safe to run in both containers.
# Deliberately calls only rebuild_multi_server_config(), never TOOLS/.../main(), which also
# installs/starts systemd --user units — meaningless (and wrong) inside a container.
set -e

python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('sup', '/app/TOOLS/DSI-Wiki-Service-Supervisor.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.rebuild_multi_server_config()
"

exec "$@"
