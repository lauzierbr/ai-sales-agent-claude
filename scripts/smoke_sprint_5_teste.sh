#!/usr/bin/env bash
# smoke_sprint_5_teste.sh — Gates específicos do Sprint 5-teste
# Roda como G7 dentro de smoke_gate.sh 5-teste
set -euo pipefail

BASE_URL="${APP_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${VENV_ROOT:-$PROJECT_ROOT/.venv}/bin/python"

PASSED=0; FAILED=0; FAILURES=()
_pass() { echo "  [PASS] $1"; PASSED=$((PASSED+1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAILED=$((FAILED+1)); FAILURES+=("$1: $2"); }

echo ""
echo "=== SMOKE Sprint 5-teste — Top Produtos ==="

# S1: sem sessão → redirect para login
# || echo "000" impede set -e de abortar o script quando curl falha por conexão recusada
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dashboard/top-produtos?dias=30" 2>/dev/null || echo "000")
if [ "$CODE" = "302" ] || [ "$CODE" = "303" ]; then
  _pass "S1: sem sessão → redirect ($CODE)"
else
  _fail "S1" "/dashboard/top-produtos sem sessão → HTTP $CODE (esperado 302)"
fi

# S2: check_gotchas não encontra violações no código novo
if "$VENV_PYTHON" "$SCRIPT_DIR/check_gotchas.py" \
    --path "$PROJECT_ROOT/output/src/agents/repo.py" \
         "$PROJECT_ROOT/output/src/dashboard/ui.py" \
         "$PROJECT_ROOT/output/src/dashboard/templates/top_produtos.html" \
    > /tmp/gotchas_s5.log 2>&1; then
  _pass "S2: check_gotchas → sem violações"
else
  VIOLS=$(grep -c "violação" /tmp/gotchas_s5.log 2>/dev/null || echo "?")
  _fail "S2" "check_gotchas detectou violações — ver /tmp/gotchas_s5.log"
  cat /tmp/gotchas_s5.log
fi

# S3: tool coverage alinhada
if "$VENV_PYTHON" "$SCRIPT_DIR/check_tool_coverage.py" \
    > /tmp/tool_cov_s5.log 2>&1; then
  _pass "S3: check_tool_coverage → capacidade_sem_tool=0"
else
  _fail "S3" "tool coverage com divergência — ver /tmp/tool_cov_s5.log"
  cat /tmp/tool_cov_s5.log
fi

echo ""
echo "=== Sprint 5-teste: $PASSED/$((PASSED+FAILED)) PASSED ==="
if [ $FAILED -eq 0 ]; then
  echo "ALL OK"
  exit 0
else
  echo "Falhas: ${FAILURES[*]}"
  exit 1
fi
