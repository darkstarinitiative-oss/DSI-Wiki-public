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

# JSONS/instances/*.json and JSONS/DSI-Wiki-Multi-Server-Config.json/DSI-Wiki-HTTP-Config.json
# are baked in here only as a fallback default (e.g. a bare `docker run` without compose) --
# the real, live-editable copies are bind-mounted over these paths at runtime by
# docker-compose.yml (2026-08-06: previously a SEPARATE, easy-to-forget SERVICES/*.container.json
# set of files existed purely to hold container-correct values like base_dir=/data/base; that
# whole class of "edited the host file, container silently kept running the old one" bug is
# gone now that there's one file, bind-mounted, no build step in between).

COPY SERVICES/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as a non-root user matching the host user's UID/GID (default 1000:1000) instead of root,
# so anything written into a bind-mounted host directory (Wiki-RAW/ARCHIVE/BASE, the status
# volume) comes out owned by that host user, not root -- override at build time
# (--build-arg APP_UID=... APP_GID=...) if your host user isn't 1000:1000.
ARG APP_UID=1000
ARG APP_GID=1000
RUN (getent group "${APP_GID}" || groupadd -g "${APP_GID}" appuser) && \
    (getent passwd "${APP_UID}" || useradd -u "${APP_UID}" -g "${APP_GID}" -M -s /usr/sbin/nologin appuser) && \
    mkdir -p /data/status && chown -R "${APP_UID}:${APP_GID}" /app /data
USER ${APP_UID}:${APP_GID}

EXPOSE 8430
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "CODE/gateway/DSI-Wiki-HTTP-Server.py"]
