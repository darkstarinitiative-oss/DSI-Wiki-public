# DSI-Wiki — containerized setup test / gateway image.
# Ingest daemon needs an Ollama endpoint (LLM_WIKI_OLLAMA_URL); the gateway and
# CLIs are fully functional without it.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-interactive setup: answers via env vars, no systemd inside the container.
ENV WIKI_RAW_DIR=/data/raw \
    WIKI_ARCHIVE_DIR=/data/archive \
    WIKI_INSTANCE_NAME=containertest \
    WIKI_BASE_DIR=/data/base
RUN ./setup.sh --no-systemd

EXPOSE 8430
CMD ["python3", "/app/_Python/HTTPService/DSI-Wiki-HTTP-Server.py"]
