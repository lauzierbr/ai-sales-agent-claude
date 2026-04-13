#!/bin/bash
# deploy.sh — Deploy no mac-mini-lablz (staging)
# Execute a partir do mac-lablz
set -e

REMOTE_HOST="mac-mini-lablz"
REMOTE_PATH="~/ai-sales-agent"
REMOTE_USER="${DEPLOY_USER:-lauzier}"
ENV="${1:-staging}"

echo "🚀 Deploy — AI Sales Agent"
echo "   Destino : $REMOTE_USER@$REMOTE_HOST"
echo "   Ambiente: $ENV"
echo ""

read -p "Confirma deploy para $ENV? (s/N) " -n 1 -r
echo ""
[[ ! $REPLY =~ ^[Ss]$ ]] && echo "Deploy cancelado." && exit 0

# 1. Pull do código
echo "📥 Atualizando código..."
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_PATH && git pull origin main"

# 2. Reinicia serviços Docker
echo "🐳 Reiniciando containers..."
ssh $REMOTE_USER@$REMOTE_HOST "
    cd $REMOTE_PATH
    infisical run --env=$ENV -- \
        docker-compose -f infra/docker-compose.staging.yml up -d --build
"

# 3. Reinicia aplicação FastAPI via launchd
echo "🔄 Reiniciando aplicação..."
ssh $REMOTE_USER@$REMOTE_HOST "
    launchctl stop  com.ai-sales-agent 2>/dev/null || true
    launchctl start com.ai-sales-agent
"

# 4. Health check remoto
echo "🏥 Health check..."
sleep 3
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_PATH && ./scripts/health-check.sh"

echo ""
echo "✅ Deploy concluído!"
echo ""
echo "Logs:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'tail -f $REMOTE_PATH/logs/app.log'"
echo ""
echo "Observabilidade:"
echo "  Grafana staging: http://$REMOTE_HOST:3000"
