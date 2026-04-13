#!/bin/bash
# setup.sh — Setup inicial do ai-sales-agent no mac-lablz
set -e

echo "AI Sales Agent — Setup inicial"
echo "================================"
echo ""
echo "Verificando pre-requisitos..."

command -v python3 >/dev/null 2>&1 || { echo "Python 3 nao encontrado: brew install python@3.11"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker Desktop nao encontrado."; exit 1; }
command -v git >/dev/null 2>&1 || { echo "Git nao encontrado."; exit 1; }
command -v infisical >/dev/null 2>&1 || { echo "Infisical nao encontrado: brew install infisical/get-cli/infisical"; exit 1; }
command -v claude >/dev/null 2>&1 || echo "Claude Code nao encontrado: npm install -g @anthropic-ai/claude-code"

echo "Pre-requisitos ok"
echo ""
echo "Criando ambiente virtual..."
[ ! -d ".venv" ] && python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet anthropic pydantic structlog httpx opentelemetry-sdk playwright import-linter
playwright install chromium
echo "Dependencias base + Playwright instalados"

echo ""
echo "Criando estrutura de diretorios..."
mkdir -p output/src/{catalog/runtime/crawler,orders/runtime,agents/runtime,tenants/runtime,providers}
mkdir -p output/tests
mkdir -p artifacts
mkdir -p docs/exec-plans/{active,completed}
echo "Estrutura ok"

echo ""
if [ -f ".infisical.json" ]; then
    echo "Infisical ja configurado"
else
    echo "Infisical ainda nao configurado:"
    echo "  1. https://app.infisical.com — crie projeto ai-sales-agent"
    echo "  2. Ambientes: development, staging, production"
    echo "  3. infisical login && infisical init"
fi

echo ""
echo "================================"
echo "Setup concluido!"
echo ""
echo "Proximos passos:"
echo "  infisical login && infisical init"
echo "  claude"
echo "  Primeiro comando: Leia AGENTS.md. Execute Sprint Infra-Dev."
