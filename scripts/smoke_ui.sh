#!/usr/bin/env bash
# smoke_ui.sh — UI Smoke Gate (P1 do harness v2)
#
# Faz login e GET em todas as rotas do dashboard, asserta HTTP 200 + conteúdo
# âncora. Pega bugs como os 3 do Sprint 4 (coluna inexistente → 500, filtro
# Jinja inexistente → 500, contexto faltando → KPI vazio) em ~5 segundos.
#
# Uso:
#   infisical run --env=staging -- bash scripts/smoke_ui.sh
#   (DASHBOARD_SECRET e APP_URL vêm do ambiente)
#
# Exit 0 se todas as rotas passarem; exit 1 caso contrário.

set -euo pipefail

BASE_URL="${APP_URL:-http://localhost:8000}"
PASSED=0
FAILED=0
FAILURES=()

_pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAILED=$((FAILED + 1)); FAILURES+=("$1: $2"); }

echo ""
echo "=== UI SMOKE GATE ==="
echo "  Base URL: $BASE_URL"
echo ""

# ─────────────────────────────────────────────
# L0 — Login (precondição para rotas autenticadas)
# ─────────────────────────────────────────────
echo "[L0] Login dashboard..."
if [ -z "${DASHBOARD_SECRET:-}" ]; then
  echo "  [ABORT] DASHBOARD_SECRET não configurado."
  exit 1
fi

LOGIN_RESP=$(curl -s -D - -o /dev/null \
  -X POST "$BASE_URL/dashboard/login" \
  -d "senha=${DASHBOARD_SECRET}")

COOKIE_VALUE=$(echo "$LOGIN_RESP" | grep -i "set-cookie:" | \
  head -1 | sed 's/.*dashboard_session=\([^;]*\).*/\1/')

if [ -z "$COOKIE_VALUE" ] || [ "$COOKIE_VALUE" = "$LOGIN_RESP" ]; then
  echo "  [ABORT] Login falhou — sem cookie dashboard_session."
  exit 1
fi
_pass "L0: login → cookie dashboard_session setado"

# ─────────────────────────────────────────────
# Helper: testa uma rota GET autenticada com asserts HTTP 200 + âncora
# Args: route_id url anchor_regex
# ─────────────────────────────────────────────
_test_auth_route() {
  local id="$1"
  local url="$2"
  local anchor="$3"

  local tmpfile
  tmpfile=$(mktemp)
  local http_code
  http_code=$(curl -s -o "$tmpfile" -w "%{http_code}" \
    -H "Cookie: dashboard_session=${COOKIE_VALUE}" \
    "$BASE_URL$url")

  if [ "$http_code" != "200" ]; then
    local head
    head=$(head -c 200 "$tmpfile" | tr -d '\n' | tr -s ' ')
    rm -f "$tmpfile"
    _fail "$id" "GET $url → HTTP $http_code (esperado 200). Body: ${head:0:160}"
    return
  fi

  if ! grep -qiE "$anchor" "$tmpfile"; then
    local head
    head=$(head -c 200 "$tmpfile" | tr -d '\n' | tr -s ' ')
    rm -f "$tmpfile"
    _fail "$id" "GET $url → 200 mas sem âncora /$anchor/. Body: ${head:0:160}"
    return
  fi

  rm -f "$tmpfile"
  _pass "$id: GET $url → 200 + âncora /$anchor/"
}

# ─────────────────────────────────────────────
# Rotas autenticadas — cada rota do dashboard deve retornar 200 + conteúdo
# ─────────────────────────────────────────────
_test_auth_route "U1"  "/dashboard/home"                          "GMV|R\\$"
_test_auth_route "U2"  "/dashboard/home/partials/kpis"            "GMV|R\\$|pedido"
_test_auth_route "U3"  "/dashboard/home/partials/pedidos_recentes" "<"
_test_auth_route "U4"  "/dashboard/home/partials/conversas_ativas" "<"
_test_auth_route "U5"  "/dashboard/pedidos"                       "Pedido|Cliente"
_test_auth_route "U6"  "/dashboard/conversas"                     "Conversa|Cliente"
_test_auth_route "U7"  "/dashboard/clientes"                      "Cliente|CNPJ"
_test_auth_route "U8"  "/dashboard/representantes"                "Represent|GMV"
_test_auth_route "U9"  "/dashboard/precos"                        "Preç|Upload|upload"
_test_auth_route "U10" "/dashboard/configuracoes"                 "Config|E-mail|SMTP|WhatsApp"

# ─────────────────────────────────────────────
# Rotas públicas — login e redirecionamento sem cookie
# ─────────────────────────────────────────────
echo "[U11] GET /dashboard/login sem cookie → 200 + form..."
LOGIN_PAGE=$(mktemp)
LOGIN_CODE=$(curl -s -o "$LOGIN_PAGE" -w "%{http_code}" "$BASE_URL/dashboard/login")
if [ "$LOGIN_CODE" = "200" ] && grep -qiE "senha|password" "$LOGIN_PAGE"; then
  _pass "U11: /dashboard/login → 200 + form de senha"
else
  _fail "U11" "/dashboard/login retornou $LOGIN_CODE ou sem form de senha"
fi
rm -f "$LOGIN_PAGE"

echo "[U12] GET /dashboard/home sem cookie → 302/307..."
NO_COOKIE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dashboard/home")
if [ "$NO_COOKIE" = "302" ] || [ "$NO_COOKIE" = "307" ]; then
  _pass "U12: /dashboard/home sem cookie → $NO_COOKIE"
else
  _fail "U12" "/dashboard/home sem cookie retornou $NO_COOKIE (esperado 302/307)"
fi

# ─────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────
echo ""
TOTAL=$((PASSED + FAILED))
echo "=== UI SMOKE: $PASSED/$TOTAL PASSED, $FAILED FAILED ==="

if [ $FAILED -eq 0 ]; then
  echo ""
  echo "=== UI SMOKE GATE: PASSED ==="
  echo ""
  exit 0
else
  echo ""
  echo "Falhas:"
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
  echo ""
  echo "=== UI SMOKE GATE: FAILED ==="
  echo ""
  exit 1
fi
