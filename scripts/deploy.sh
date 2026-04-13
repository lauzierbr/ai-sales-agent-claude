#!/bin/bash
# deploy.sh — Deploy no macmini-lablz (staging)
# Execute a partir do mac-lablz: ./scripts/deploy.sh
set -e

REMOTE_HOST="macmini-lablz"
REMOTE_PATH="~/ai-sales-agent-claude"
ENV="${1:-staging}"

echo "Deploy — AI Sales Agent"
echo "   Destino : $REMOTE_HOST"
echo "   Ambiente: $ENV"
echo ""

read -p "Confirma deploy para $ENV? (s/N) " -n 1 -r
echo ""
[[ ! $REPLY =~ ^[Ss]$ ]] && echo "Deploy cancelado." && exit 0

# 1. Pull do código
echo "Atualizando codigo..."
ssh "$REMOTE_HOST" "export PATH=/usr/local/bin:\$PATH && cd $REMOTE_PATH && git pull origin main"

# 2. Reinicia serviços Docker (staging)
echo "Reiniciando containers..."
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:\$PATH
    cd $REMOTE_PATH
    docker compose -f infra/docker-compose.staging.yml up -d
"

# 3. Health check remoto
echo "Health check..."
sleep 5
ssh "$REMOTE_HOST" "
    export PATH=/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:\$PATH
    cd $REMOTE_PATH
    bash scripts/health-check.sh
"

echo ""
echo "Deploy concluido!"
echo ""
echo "Logs FastAPI (quando disponivel):"
echo "  ssh $REMOTE_HOST 'tail -f $REMOTE_PATH/logs/app.log'"
echo ""
echo "Grafana staging: http://100.113.28.85:3001"
