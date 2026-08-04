# DSI-Wiki — shared image for both the `ingest` and `gateway` services (see
# docker-compose.yml; only the container command differs). Ollama stays on the
# host, reached over the network — no GPU/CUDA deps in this image.
#
# Build context is the repo root (see docker-compose.yml's `build.context: ..`).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY CODE/ CODE/
COPY TOOLS/ TOOLS/
COPY SKILLS/ SKILLS/
COPY JSONS/ JSONS/

# Container-specific instance + HTTP config (base_dir=/data/base, scan_dir=/app/JSONS/instances)
# — the real, host-pathed JSONS/instances/*.json (gitignored) never enters the image.
COPY SERVICES/instances.container/ JSONS/instances/
COPY SERVICES/DSI-Wiki-HTTP-Config.container.json JSONS/DSI-Wiki-HTTP-Config.json

COPY SERVICES/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8430
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "CODE/gateway/DSI-Wiki-HTTP-Server.py"]
