# Homologação Sprint 4 — Gestor/Admin

**Status:** PENDENTE
**Data prevista:** A definir após aprovação do Evaluator
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head` (confirmar migration 0015 presente)
- [ ] Seed de dados: `infisical run --env=staging -- python scripts/seed_homologacao_sprint4.py`
- [ ] Smoke gate passou: `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh` → `PASSED`
- [ ] Health check: `curl http://100.113.28.85:8000/health` → versão correta com Sprint 4
- [ ] Secrets configurados no Infisical staging: `DASHBOARD_SECRET`, `DASHBOARD_TENANT_ID`

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Gestor busca clientes por nome
**Condição inicial:** Banco populado com clientes de múltiplos reps (seed executado)
**Ação:** Enviar pelo WhatsApp do gestor: `"busca cliente Muzel"`
**Resultado esperado:** Bot lista clientes com "muzel" no nome, de qualquer rep do tenant; cada entry mostra nome + CNPJ
**Verificação de banco:** `SELECT nome, cnpj, representante_id FROM clientes_b2b WHERE tenant_id='jmb' AND unaccent(lower(nome)) LIKE '%muzel%';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Gestor pede relatório semanal
**Condição inicial:** Banco com pedidos dos últimos 7 dias (seed garante isso)
**Ação:** Enviar: `"quanto vendeu essa semana?"`
**Resultado esperado:** Bot responde com total R$, número de pedidos e ticket médio para os últimos 7 dias
**Verificação de banco:** `SELECT COUNT(*), SUM(total_estimado) FROM pedidos WHERE tenant_id='jmb' AND criado_em >= NOW() - INTERVAL '7 days';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — Gestor pede ranking de representantes
**Condição inicial:** Banco com pedidos com `representante_id` preenchido
**Ação:** Enviar: `"ranking dos reps esse mês"`
**Resultado esperado:** Bot lista representantes ordenados por volume (R$) do mês corrente, do maior para o menor
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — Gestor consulta clientes inativos
**Condição inicial:** Seed criou ≥1 cliente sem pedido há 31+ dias
**Ação:** Enviar: `"clientes inativos"`
**Resultado esperado:** Bot retorna lista com ≥1 cliente sem pedido há 30+ dias
**Verificação de banco:** `SELECT nome FROM clientes_b2b c LEFT JOIN pedidos p ON p.cliente_b2b_id = c.id AND p.tenant_id='jmb' WHERE c.tenant_id='jmb' GROUP BY c.id, c.nome HAVING MAX(p.criado_em) IS NULL OR MAX(p.criado_em) < NOW() - INTERVAL '30 days';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H5 — Gestor fecha pedido para qualquer cliente (DP-03)
**Condição inicial:** Cliente "José LZ Muzel" existe com `representante_id` preenchido
**Ação:** Enviar: `"fecha 2 shampoo anticaspa pro Muzel"` → confirmar quando bot apresentar resumo
**Resultado esperado:** Pedido criado; PDF enviado ao número do gestor (`tenant.whatsapp_number`); banco registra `representante_id` = rep do cliente (não NULL)
**Verificação de banco:** `SELECT representante_id, total_estimado FROM pedidos WHERE tenant_id='jmb' ORDER BY criado_em DESC LIMIT 1;`
**Resultado:** [ ] PASSOU / [ ] FALHOU — `representante_id` = ___ (esperado: rep do Muzel)
**Observações:** ___

### H6 — Isolamento: representante não vira gestor
**Condição inicial:** Número `5519000000001` cadastrado apenas em `representantes`, não em `gestores`
**Ação:** Enviar mensagem por esse número
**Resultado esperado:** Bot responde como AgentRep (ex: menciona "carteira de clientes"), NÃO como AgentGestor
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H7 — Isolamento: cliente não vira gestor
**Condição inicial:** Número `5519992066177` cadastrado apenas em `clientes_b2b`
**Ação:** Enviar: `"oi"`
**Resultado esperado:** Bot responde como AgentCliente (saudação padrão de cliente), NÃO como AgentGestor
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H8 — Dashboard requer autenticação
**Condição inicial:** Dashboard rodando em staging
**Ação:** Acessar `http://100.113.28.85:8000/dashboard/home` no browser sem estar logado
**Resultado esperado:** Browser redireciona automaticamente para `/dashboard/login`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H9 — Dashboard login funcional
**Condição inicial:** `DASHBOARD_SECRET` configurado no Infisical staging
**Ação:** Acessar `/dashboard/login`; preencher a senha correta; clicar em entrar
**Resultado esperado:** Redirecionado para `/dashboard/home`; página exibe KPIs do dia com pedidos e GMV
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H10 — Dashboard KPIs atualizam automaticamente
**Condição inicial:** Logado no dashboard
**Ação:** Ficar na página `/dashboard/home` por 35 segundos sem recarregar
**Resultado esperado:** Seção de KPIs atualiza (visível por mudança de timestamp ou contador) sem reload completo da página
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H11 — Upload de planilha de preços
**Condição inicial:** Logado no dashboard; arquivo Excel válido disponível com colunas `codigo_produto | ean | cliente_cnpj | preco_cliente`
**Ação:** Acessar `/dashboard/precos`; fazer upload do arquivo
**Resultado esperado:** Mensagem de sucesso exibida inline (sem reload de página); preços persistidos no banco
**Verificação de banco:** `SELECT COUNT(*) FROM precos_diferenciados WHERE tenant_id='jmb';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H12 — Dashboard representantes com GMV
**Condição inicial:** Logado no dashboard; banco com pedidos de representantes
**Ação:** Acessar `/dashboard/representantes`
**Resultado esperado:** Tabela exibe lista de representantes com nome e GMV do mês (em R$)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Executado por:** Lauzier

**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
_(lista de bugs para hotfix antes do Sprint 5)_
