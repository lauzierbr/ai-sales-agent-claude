#!/bin/bash
# staging-up.sh — Garante que a stack de staging esteja ativa no host macOS
# Executado pelo launchd no boot do mac-mini-lablz
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HOME="/Users/dev"
export DOCKER_HOST="unix:///Users/dev/.docker/run/docker.sock"

cd "$ROOT_DIR"
docker compose -f infra/docker-compose.staging.yml up -d
