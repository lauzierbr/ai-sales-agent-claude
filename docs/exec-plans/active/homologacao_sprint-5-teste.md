# Homologação Sprint 5-teste — Top Produtos por Período

**Status:** PENDENTE
**Data prevista:** 2026-04-20
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging main`
- [ ] Migrations aplicadas: `alembic upgrade head`
- [ ] Smoke gate passou: `bash scripts/smoke_sprint_5_teste.sh` → ALL OK
- [ ] Health check: `curl http://100.113.28.85:8000/health` → versão correta
- [ ] `python scripts/verify_homolog_preconditions.py --sprint 5-teste` → OK

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Página top-produtos carrega
**Condição inicial:** Usuário logado no dashboard, banco com pedidos confirmados
**Ação:** Abrir `http://100.113.28.85:8000/dashboard/top-produtos?dias=30`
**Resultado esperado:** Tabela com colunas Posição / Produto / Qtd / Valor renderizada, HTTP 200
**Verificação de banco:** `SELECT COUNT(*) FROM itens_pedido ip JOIN pedidos p ON p.id = ip.pedido_id WHERE p.tenant_id = 'jmb' AND p.status = 'confirmado'`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Período sem dados
**Condição inicial:** Banco sem pedidos confirmados nas últimas 24h
**Ação:** Abrir `/dashboard/top-produtos?dias=1`
**Resultado esperado:** Mensagem "Nenhum produto no período" — sem erro 500
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — Bot responde sobre top produtos
**Condição inicial:** WhatsApp logado como gestor JMB
**Ação:** Enviar "quais produtos mais vendidos este mês?"
**Resultado esperado:** Bot lista top 5 produtos com quantidade e valor, sem erro 400
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — Follow-up multi-turn
**Condição inicial:** Mesma sessão de H3 (histórico Redis preservado)
**Ação:** Enviar "e nos últimos 7 dias?"
**Resultado esperado:** Bot responde com dados dos últimos 7 dias — sem erro 400, sem reset de contexto
**Verificação Redis:** `redis-cli GET hist:gestor:jmb:5519000000002` → list[dict] não list[str]
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
_Lista de bugs para hotfix_
