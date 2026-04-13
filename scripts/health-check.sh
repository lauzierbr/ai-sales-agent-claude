#!/bin/bash
# health-check.sh — Verifica todos os serviços de infraestrutura
set -e

echo "Health Check — AI Sales Agent"
echo "================================="

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo "OK  $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL $name"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "Docker containers..."
check "PostgreSQL (5432)"    "docker exec ai-sales-postgres pg_isready -U aisales"
check "Redis (6379)"         "docker exec ai-sales-redis redis-cli ping | grep -q PONG"
check "Evolution API (8080)" "curl -sf http://localhost:8080/"

echo ""
echo "Observabilidade..."
check "VictoriaMetrics (8428)" "curl -sf http://localhost:8428/health"
check "VictoriaLogs (9428)"    "curl -sf http://localhost:9428/health"
check "OTEL Collector (13133)" "curl -sf http://localhost:13133/"
check "Grafana (3001)"         "curl -sf http://localhost:3001/api/health"

echo ""
echo "Infisical..."
check "Infisical CLI autenticado" "infisical secrets --env=dev > /dev/null"

echo ""
echo "Python..."
check "Imports básicos" "$(dirname "$0")/../.venv/bin/python -c 'import anthropic, fastapi, sqlalchemy, redis, playwright, structlog; print(\"ok\")'"
check "import-linter"   "PYTHONPATH=$(dirname "$0")/../output $(dirname "$0")/../.venv/bin/lint-imports --config $(dirname "$0")/../pyproject.toml"

echo ""
echo "================================="
echo "Resultado: $PASS OK, $FAIL falhas"

[ $FAIL -eq 0 ] && echo "Todos os servicos operacionais!" && exit 0
echo "$FAIL servico(s) com problema. Verifique os logs." && exit 1
