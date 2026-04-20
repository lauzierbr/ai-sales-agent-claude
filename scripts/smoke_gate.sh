#!/usr/bin/env bash
# smoke_gate.sh — Smoke gate universal (Q4 do harness v2).
#
# Substitui smoke_gate_sprint_N.sh por um pipeline parametrizável:
#
#   infisical run --env=staging -- bash scripts/smoke_gate.sh 5
#
# Executa, na ordem:
#   G1  — /health (app responde)
#   G2  — lint-imports (arquitetura em camadas)
#   G3  — check_tool_coverage.py (capacidade ↔ tool)
#   G4  — smoke_ui.sh (dashboard HTTP por rota)
#   G5  — pytest -m unit output/src/tests/unit/
#   G6  — pytest -m unit output/src/tests/regression/ (baseline de bugs)
#   G7  — smoke_sprint_N.sh se existir (gates específicos do sprint)
#
# Exit 0 se tudo passar; exit 1 caso contrário.

set -euo pipefail

SPRINT_N="${1:-}"
BASE_URL="${APP_URL:-http://localhost:8000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_ROOT="${VENV_ROOT:-$PROJECT_ROOT/.venv}"
if [ ! -x "$VENV_ROOT/bin/python" ]; then
  # Fallback para staging layout
  VENV_ROOT="${HOME}/ai-sales-agent-claude/.venv"
fi
VENV_PYTHON="$VENV_ROOT/bin/python"
VENV_LINT="$VENV_ROOT/bin/lint-imports"

export PYTHONPATH="$PROJECT_ROOT/output"

PASSED=0
FAILED=0
FAILURES=()

_pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAILED=$((FAILED + 1)); FAILURES+=("$1: $2"); }

echo ""
echo "=== SMOKE GATE ${SPRINT_N:+(Sprint $SPRINT_N) }==="
echo "  Base URL:   $BASE_URL"
echo "  Project:    $PROJECT_ROOT"
echo "  Venv:       $VENV_ROOT"
echo ""

# ─────────────────────────────────────────────
# G1 — /health
# ─────────────────────────────────────────────
echo "[G1] Health check..."
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" || echo "000")
if [ "$HEALTH_CODE" = "200" ]; then
  _pass "G1: /health → 200"
else
  _fail "G1" "/health → HTTP $HEALTH_CODE"
fi

# ─────────────────────────────────────────────
# G2 — lint-imports (camadas)
# ─────────────────────────────────────────────
echo "[G2] lint-imports..."
if [ ! -x "$VENV_LINT" ]; then
  _fail "G2" "lint-imports não encontrado em $VENV_LINT"
else
  LINT_OUT=$("$VENV_LINT" 2>&1 || true)
  if echo "$LINT_OUT" | grep -q "0 broken"; then
    _pass "G2: lint-imports → 0 violações"
  else
    _fail "G2" "lint-imports detectou violações — $(echo "$LINT_OUT" | grep -i broken | head -1)"
  fi
fi

# ─────────────────────────────────────────────
# G3 — check_tool_coverage.py
# ─────────────────────────────────────────────
echo "[G3] check_tool_coverage..."
if "$VENV_PYTHON" "$SCRIPT_DIR/check_tool_coverage.py" > /tmp/tool_cov.log 2>&1; then
  _pass "G3: capacidade ↔ tool alinhadas"
else
  _fail "G3" "capacidade/tool divergente — ver /tmp/tool_cov.log"
fi

# ─────────────────────────────────────────────
# G4 — smoke_ui.sh (só se app responde em health)
# ─────────────────────────────────────────────
echo "[G4] smoke_ui.sh..."
if [ "$HEALTH_CODE" != "200" ]; then
  _fail "G4" "app não respondeu no G1; smoke_ui pulado"
else
  if bash "$SCRIPT_DIR/smoke_ui.sh" > /tmp/smoke_ui.log 2>&1; then
    _pass "G4: todas as rotas do dashboard OK"
  else
    FAIL_CNT=$(grep -c "\[FAIL\]" /tmp/smoke_ui.log || echo "?")
    _fail "G4" "$FAIL_CNT rota(s) falharam — ver /tmp/smoke_ui.log"
  fi
fi

# ─────────────────────────────────────────────
# G5 — pytest -m unit (todos os unit tests)
# ─────────────────────────────────────────────
echo "[G5] pytest -m unit..."
if "$VENV_PYTHON" -m pytest -m unit "$PROJECT_ROOT/output/src/tests/unit/" \
    -q --tb=line > /tmp/pytest_unit.log 2>&1; then
  PASSED_UNIT=$(grep -oE "[0-9]+ passed" /tmp/pytest_unit.log | head -1 || echo "?")
  _pass "G5: unit tests → $PASSED_UNIT"
else
  _fail "G5" "unit tests falharam — ver /tmp/pytest_unit.log"
fi

# ─────────────────────────────────────────────
# G6 — pytest -m unit regression/ (baseline de bugs conhecidos)
# ─────────────────────────────────────────────
echo "[G6] pytest -m unit regression/..."
REG_DIR="$PROJECT_ROOT/output/src/tests/regression"
if [ -d "$REG_DIR" ]; then
  if "$VENV_PYTHON" -m pytest -m unit "$REG_DIR" -q --tb=line \
      > /tmp/pytest_regression.log 2>&1; then
    PASSED_REG=$(grep -oE "[0-9]+ passed" /tmp/pytest_regression.log | head -1 || echo "?")
    _pass "G6: regression tests → $PASSED_REG"
  else
    _fail "G6" "regressão detectada — ver /tmp/pytest_regression.log"
  fi
else
  _pass "G6: sem diretório regression/ (skip)"
fi

# ─────────────────────────────────────────────
# G7 — gates específicos do sprint (opcional)
# ─────────────────────────────────────────────
if [ -n "$SPRINT_N" ]; then
  SPRINT_SCRIPT="$SCRIPT_DIR/smoke_sprint_${SPRINT_N}.sh"
  if [ -x "$SPRINT_SCRIPT" ] || [ -f "$SPRINT_SCRIPT" ]; then
    echo "[G7] smoke_sprint_${SPRINT_N}.sh..."
    if bash "$SPRINT_SCRIPT" > /tmp/smoke_sprint.log 2>&1; then
      _pass "G7: gates específicos do Sprint $SPRINT_N OK"
    else
      _fail "G7" "gates do Sprint $SPRINT_N falharam — ver /tmp/smoke_sprint.log"
    fi
  else
    echo "[G7] (sem scripts/smoke_sprint_${SPRINT_N}.sh — skip)"
  fi
fi

# ─────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────
TOTAL=$((PASSED + FAILED))
echo ""
echo "=== SMOKE GATE: $PASSED/$TOTAL PASSED, $FAILED FAILED ==="

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
