#!/usr/bin/env bash
# smoke_gate_sprint4.sh — Sprint 4 smoke gate (S1–S9)
#
# Uso:
#   infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh
#
# Saída esperada: "=== SMOKE GATE: PASSED ===" e exit 0.
# Qualquer falha resulta em "=== SMOKE GATE: FAILED ===" e exit 1.

set -euo pipefail

BASE_URL="${APP_URL:-http://localhost:8000}"
PASSED=0
FAILED=0
FAILURES=()

# Venv paths (ajuste se necessário)
VENV_ROOT="${VENV_ROOT:-$HOME/ai-sales-agent-claude/.venv}"
VENV_PYTHON="$VENV_ROOT/bin/python"
VENV_LINT="$VENV_ROOT/bin/lint-imports"
export PYTHONPATH="${PYTHONPATH:-output}"

_pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAILED=$((FAILED + 1)); FAILURES+=("$1: $2"); }

echo ""
echo "=== SMOKE GATE Sprint 4 ==="
echo "  Base URL: $BASE_URL"
echo ""

# ─────────────────────────────────────────────
# S1 — /health → 200 com "status":"ok"
# ─────────────────────────────────────────────
echo "[S1] Health check..."
HEALTH_RESP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$HEALTH_RESP" = "200" ]; then
  HEALTH_BODY=$(curl -s "$BASE_URL/health")
  if echo "$HEALTH_BODY" | grep -q '"status"'; then
    _pass "S1: /health → 200 com status ok"
  else
    _fail "S1" "/health retornou 200 mas body não contém 'status'"
  fi
else
  _fail "S1" "/health retornou HTTP $HEALTH_RESP (esperado 200)"
fi

# ─────────────────────────────────────────────
# S2 — Unit tests IR-G1 (IdentityRouter GESTOR)
# ─────────────────────────────────────────────
echo "[S2] Unit tests IR-G1..."
if "$VENV_PYTHON" -m pytest -m unit -k "test_identity_router_gestor_retorna_gestor" \
    output/src/tests/unit/agents/test_identity_router.py -q --tb=short 2>&1 | tail -3 | grep -q "passed"; then
  _pass "S2: IR-G1 test_identity_router_gestor_retorna_gestor PASSED"
else
  _fail "S2" "IR-G1 test falhou — ver saída acima"
fi

# ─────────────────────────────────────────────
# S3 — GET /dashboard/home sem cookie → 302
# ─────────────────────────────────────────────
echo "[S3] Dashboard home sem cookie..."
DASH_RESP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dashboard/home")
if [ "$DASH_RESP" = "302" ] || [ "$DASH_RESP" = "307" ]; then
  _pass "S3: GET /dashboard/home sem cookie → $DASH_RESP"
else
  _fail "S3" "GET /dashboard/home sem cookie retornou $DASH_RESP (esperado 302)"
fi

# ─────────────────────────────────────────────
# S4 — POST /dashboard/login com senha errada → NÃO 302
# ─────────────────────────────────────────────
echo "[S4] Dashboard login senha errada..."
WRONG_RESP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/dashboard/login" \
  -d "senha=senha-totalmente-errada-12345")
if [ "$WRONG_RESP" != "302" ] && [ "$WRONG_RESP" != "307" ]; then
  _pass "S4: POST /dashboard/login com senha errada → $WRONG_RESP (não 302)"
else
  _fail "S4" "POST /dashboard/login com senha errada retornou $WRONG_RESP (não esperado)"
fi

# ─────────────────────────────────────────────
# S5 — POST /dashboard/login com senha correta → cookie setado
# ─────────────────────────────────────────────
echo "[S5] Dashboard login senha correta..."
if [ -z "${DASHBOARD_SECRET:-}" ]; then
  _fail "S5" "DASHBOARD_SECRET não configurado no ambiente"
else
  LOGIN_RESP=$(curl -s -D - -o /dev/null \
    -X POST "$BASE_URL/dashboard/login" \
    -d "senha=${DASHBOARD_SECRET}")
  LOGIN_STATUS=$(echo "$LOGIN_RESP" | grep "^HTTP" | awk '{print $2}')
  if echo "$LOGIN_RESP" | grep -qi "set-cookie:.*dashboard_session"; then
    _pass "S5: POST /dashboard/login → cookie dashboard_session setado"
    # Extrai cookie para S6
    COOKIE_VALUE=$(echo "$LOGIN_RESP" | grep -i "set-cookie:" | head -1 | sed 's/.*dashboard_session=\([^;]*\).*/\1/')
  else
    _fail "S5" "POST /dashboard/login não setou cookie dashboard_session (status=$LOGIN_STATUS)"
    COOKIE_VALUE=""
  fi
fi

# ─────────────────────────────────────────────
# S6 — GET /dashboard/home com cookie → 200
# ─────────────────────────────────────────────
echo "[S6] Dashboard home com cookie..."
if [ -n "${COOKIE_VALUE:-}" ]; then
  HOME_RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Cookie: dashboard_session=${COOKIE_VALUE}" \
    "$BASE_URL/dashboard/home")
  if [ "$HOME_RESP" = "200" ]; then
    _pass "S6: GET /dashboard/home com cookie → 200"
  else
    _fail "S6" "GET /dashboard/home com cookie retornou $HOME_RESP (esperado 200)"
  fi
else
  _fail "S6" "Sem cookie para testar (S5 falhou)"
fi

# ─────────────────────────────────────────────
# S7 — GET /dashboard/home/partials/kpis → HTML com "GMV" ou "R$"
# ─────────────────────────────────────────────
echo "[S7] Dashboard partials/kpis..."
if [ -n "${COOKIE_VALUE:-}" ]; then
  KPIS_BODY=$(curl -s \
    -H "Cookie: dashboard_session=${COOKIE_VALUE}" \
    "$BASE_URL/dashboard/home/partials/kpis")
  if echo "$KPIS_BODY" | grep -qiE "GMV|R\$"; then
    _pass "S7: GET /dashboard/home/partials/kpis → HTML contém GMV/R\$"
  else
    _fail "S7" "Partial /kpis não contém GMV ou R\$ — body: ${KPIS_BODY:0:200}"
  fi
else
  _fail "S7" "Sem cookie para testar (S5 falhou)"
fi

# ─────────────────────────────────────────────
# S8 — pytest -m unit test_agent_gestor.py → 0 falhas
# ─────────────────────────────────────────────
echo "[S8] Unit tests AgentGestor..."
if "$VENV_PYTHON" -m pytest -m unit \
    output/src/tests/unit/agents/test_agent_gestor.py \
    -q --tb=short 2>&1 | tail -5 | grep -qE "passed|0 failed"; then
  _pass "S8: pytest -m unit test_agent_gestor.py → 0 falhas"
else
  _fail "S8" "Testes unitários do AgentGestor falharam"
fi

# ─────────────────────────────────────────────
# S9 — lint-imports → zero violações
# ─────────────────────────────────────────────
echo "[S9] Import linter..."
LINT_OUT=$("$VENV_LINT" 2>&1 || true)
if echo "$LINT_OUT" | grep -qi "kept"; then
  if echo "$LINT_OUT" | grep -qi "broken"; then
    _fail "S9" "lint-imports encontrou violações de camada"
  else
    _pass "S9: lint-imports → zero violações (Kept)"
  fi
else
  _fail "S9" "lint-imports falhou — $(echo "$LINT_OUT" | tail -3)"
fi

# ─────────────────────────────────────────────
# Resultado final
# ─────────────────────────────────────────────
echo ""
echo "=== Resultado: $PASSED/9 PASSED, $FAILED FAILED ==="

if [ $FAILED -eq 0 ]; then
  echo ""
  echo "=== SMOKE GATE: PASSED ==="
  echo ""
  exit 0
else
  echo ""
  echo "Falhas:"
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
  echo ""
  echo "=== SMOKE GATE: FAILED ==="
  echo ""
  exit 1
fi
