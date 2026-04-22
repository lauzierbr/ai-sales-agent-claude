#!/bin/bash
# deploy.sh — Deploy no macmini-lablz (staging) via git checkout
#
# Uso:
#   ./scripts/deploy.sh [staging|dev] [branch|sha]
#
# Exemplos:
#   ./scripts/deploy.sh                      # main, staging
#   ./scripts/deploy.sh staging main         # branch main explícita
#   ./scripts/deploy.sh staging feat/sprint5 # branch de feature
#   ./scripts/deploy.sh staging abc1234      # SHA específico
#
# P9 (harness v2): o Generator nunca copia arquivos individuais.
# O único mecanismo de deploy é: push para o remoto + git checkout <ref>
# no destino. Isso elimina bugs de rsync --relative, paths errados e
# discrepâncias entre o que está no repo e o que está no disco.

set -euo pipefail

ENV="${1:-staging}"
REF="${2:-main}"
REMOTE_HOST="macmini-lablz"
REMOTE_PATH="~/ai-sales-agent-claude"
INFISICAL="/usr/local/Cellar/infisical/0.43.72/bin/infisical"
VENV_PYTHON="/Users/dev/ai-sales-agent-claude/.venv/bin/python"
VENV_UVICORN="/Users/dev/ai-sales-agent-claude/.venv/bin/uvicorn"
LOG_DIR="$REMOTE_PATH/logs"

echo "========================================"
echo " Deploy — AI Sales Agent"
echo "   Destino : $REMOTE_HOST"
echo "   Ambiente: $ENV"
echo "   Ref     : $REF"
echo "========================================"
echo ""

# Verifica que a ref existe no remoto antes de confirmar
echo "[0/6] Verificando ref '$REF' no remoto..."
if ! git ls-remote --exit-code origin "$REF" > /dev/null 2>&1; then
  # Pode ser um SHA — tenta fetch sem erro
  echo "    (ref não encontrada como branch/tag — tratando como SHA)"
fi

read -r -p "Confirma deploy de '$REF' para $ENV? (s/N) " -n 1 REPLY
echo ""
[[ ! $REPLY =~ ^[Ss]$ ]] && echo "Deploy cancelado." && exit 0

# ─────────────────────────────────────────────
# 1. Checkout da ref no destino
#
# Único mecanismo de sync: git fetch + git checkout.
# Nenhum arquivo é copiado individualmente (sem scp, sem rsync).
# ─────────────────────────────────────────────
echo "[1/6] Checando out '$REF' no destino..."
ssh "$REMOTE_HOST" "
    set -euo pipefail
    export PATH=/usr/local/bin:\$PATH
    cd $REMOTE_PATH

    git fetch --all --prune

    # Avisa sobre mudanças locais não-commitadas antes de descartar
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo ''
        echo '⚠️  ATENÇÃO: há mudanças locais NÃO-COMMITADAS no servidor:'
        git status --short
        echo ''
        echo 'Essas mudanças serão PERDIDAS pelo checkout -f.'
        echo 'Pressione Enter para continuar ou Ctrl+C para cancelar e commitar antes.'
        read -r _CONFIRM
    fi

    git checkout -f '$REF'
    git log -1 --oneline
"

# ─────────────────────────────────────────────
# 2. Garante containers Docker ativos
# ─────────────────────────────────────────────
echo "[2/6] Verificando containers (Postgres, Redis, etc)..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:\$PATH
    export DOCKER_HOST=unix:///Users/dev/.docker/run/docker.sock
    cd $REMOTE_PATH
    docker compose -f infra/docker-compose.staging.yml up -d
"
echo "    Aguardando Postgres..."
ssh "$REMOTE_HOST" "
    for i in \$(seq 1 15); do
        docker exec ai-sales-postgres pg_isready -U aisales >/dev/null 2>&1 && break
        sleep 1
    done
    docker exec ai-sales-postgres pg_isready -U aisales
"

# ─────────────────────────────────────────────
# 3. Pre-checklist de migrations
# ─────────────────────────────────────────────
echo "[3/6] Pre-checklist de migrations..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:\$PATH
    cd $REMOTE_PATH/output
    export PYTHONPATH=.

    echo '--- Revisao atual do banco ---'
    $INFISICAL run --env=$ENV -- ../.venv/bin/alembic current 2>&1 | grep -v INF | grep -v 'release\|update\|brew'

    echo '--- SQL que sera aplicado (migrations pendentes) ---'
    $INFISICAL run --env=$ENV -- ../.venv/bin/alembic upgrade --sql head 2>&1 \
        | grep -v INF | grep -v 'release\|update\|brew' \
        | grep -v '^\$' \
        || echo '    (nenhuma migration pendente)'
"

echo ""
read -r -p "SQL acima esta correto? Aplicar migrations? (s/N) " -n 1 REPLY
echo ""
[[ ! $REPLY =~ ^[Ss]$ ]] && echo "Deploy cancelado antes das migrations." && exit 0

# ─────────────────────────────────────────────
# 4. Aplica migrations
# ─────────────────────────────────────────────
echo "[4/6] Aplicando migrations..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:\$PATH
    cd $REMOTE_PATH/output
    export PYTHONPATH=.
    $INFISICAL run --env=$ENV -- ../.venv/bin/alembic upgrade head 2>&1 \
        | grep -v INF | grep -v 'release\|update\|brew'
    echo '--- Revisao final ---'
    $INFISICAL run --env=$ENV -- ../.venv/bin/alembic current 2>&1 \
        | grep -v INF | grep -v 'release\|update\|brew'
"

# ─────────────────────────────────────────────
# 5. Reinicia uvicorn
# ─────────────────────────────────────────────
echo "[5/6] Reiniciando uvicorn..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:\$PATH
    pkill -f 'uvicorn src.main:app' 2>/dev/null || true
    sleep 1
    cd $REMOTE_PATH/output
    export PYTHONPATH=.
    mkdir -p $LOG_DIR
    nohup $INFISICAL run --env=$ENV -- \
        $VENV_UVICORN src.main:app \
        --host 0.0.0.0 --port 8000 --log-level info \
        > $LOG_DIR/app.log 2>&1 &
    sleep 2
    curl -sf http://localhost:8000/health && echo ' uvicorn OK' || echo ' FALHA no health check'
"

# ─────────────────────────────────────────────
# 6. Health check final
# ─────────────────────────────────────────────
echo "[6/6] Health check..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:\$PATH
    cd $REMOTE_PATH
    bash scripts/health-check.sh
"

echo ""
echo "========================================"
echo " Deploy concluido!"
echo "   Ref: $REF @ $(git rev-parse --short "$REF" 2>/dev/null || echo $REF)"
echo "========================================"
echo ""
echo "URLs staging (via Tailscale):"
echo "  API:    http://100.113.28.85:8000"
echo "  Swagger: http://100.113.28.85:8000/docs"
echo "  Painel: http://100.113.28.85:8000/catalog/painel?tenant_id=jmb&limit=500"
echo "  Grafana: http://100.113.28.85:3001"
echo ""
echo "Logs:"
echo "  ssh $REMOTE_HOST 'tail -f $REMOTE_PATH/logs/app.log'"
