#!/bin/bash
# staging-up.sh — Garante que a stack de staging esteja ativa no host macOS
# Executado pelo launchd no login do usuário dev no macmini-lablz
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/Cellar/infisical/0.43.72/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HOME="/Users/dev"
export DOCKER_HOST="unix:///Users/dev/.docker/run/docker.sock"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

VENV_UVICORN="$ROOT_DIR/.venv/bin/uvicorn"
INFISICAL="/usr/local/Cellar/infisical/0.43.72/bin/infisical"

# ── 1. Aguarda Docker daemon ficar pronto (max 60s) ────────────────────────
echo "[staging-up] Aguardando Docker daemon..."
for i in $(seq 1 60); do
    docker info >/dev/null 2>&1 && break || true
    sleep 1
done

# ── 2. Containers Docker ────────────────────────────────────────────────────
cd "$ROOT_DIR"
docker compose -f infra/docker-compose.staging.yml up -d

# ── 3. Aguarda Postgres ficar saudável (max 60s) ────────────────────────────
echo "[staging-up] Aguardando Postgres..."
for i in $(seq 1 30); do
    docker exec ai-sales-postgres pg_isready -U aisales >/dev/null 2>&1 && break || true
    sleep 1
done
docker exec ai-sales-postgres pg_isready -U aisales || {
    echo "[staging-up] ERRO: Postgres não ficou saudável em 30s" >&2
    exit 1
}

# ── 4. Para uvicorn anterior se estiver rodando ─────────────────────────────
pkill -f "uvicorn src.main:app" 2>/dev/null || true
sleep 1

# ── 5. Inicia uvicorn via infisical (staging) ───────────────────────────────
echo "[staging-up] Iniciando uvicorn..."
cd "$ROOT_DIR/output"
export PYTHONPATH="."

# Subshell + disown desacopla do process group do launchd no macOS,
# evitando SIGTERM quando o script pai termina
(
    nohup "$INFISICAL" run --env=staging -- \
        "$VENV_UVICORN" src.main:app \
        --host 0.0.0.0 --port 8000 --log-level info \
        >> "$LOG_DIR/app.log" 2>&1 &
    disown
)

# ── 6. Health check (aguarda até 30s) ───────────────────────────────────────
echo "[staging-up] Aguardando uvicorn ficar pronto..."
for i in $(seq 1 30); do
    curl -sf http://localhost:8000/health >/dev/null 2>&1 && break || true
    sleep 1
done
curl -sf http://localhost:8000/health \
    && echo "[staging-up] uvicorn OK — health check passou" \
    || echo "[staging-up] AVISO: uvicorn não respondeu em 30s" >&2
