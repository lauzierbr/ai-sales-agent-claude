# Homologação Sprint 6 — Pre-Pilot Hardening

**Status:** PENDENTE
**Data prevista:** 2026-04-21
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head`
- [ ] Seed de dados: `python scripts/seed_homologacao_sprint-6.py`
- [ ] Smoke gate passou: `python scripts/smoke_sprint_6.py` → ALL OK
- [ ] Health check geral: `python scripts/health_check.py` → exit 0
- [ ] Health HTTP: `curl http://100.113.28.85:8000/health` → componente Anthropic diferente de `fail`

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## SQL de precondição

| ID | Cenário | SQL precondição | Esperado |
|----|---------|-----------------|----------|
| H2 | Cadastro de cliente válido | `SELECT id, nome FROM representantes WHERE tenant_id = 'jmb' AND ativo = true LIMIT 1;` | ao menos 1 representante ativo |
| H4 | Upload de preços via dashboard | `SELECT id, cnpj FROM clientes_b2b WHERE tenant_id = 'jmb' AND ativo = true LIMIT 1;` | ao menos 1 cliente do tenant |
| H5 | Top produtos acessível e navegável | `SELECT COUNT(*) AS n FROM pedidos WHERE tenant_id = 'jmb' AND status = 'confirmado';` | `n > 0` |

---

## Cenários de homologação

### H1 — Login do dashboard
**Condição inicial:** `DASHBOARD_SECRET` e `DASHBOARD_TENANT_ID` válidos em staging.
**Ação:** Acessar `/dashboard/login` e autenticar com a senha do ambiente.
**Resultado esperado:** Redirect para `/dashboard/home` com cookie `dashboard_session`.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Cadastro de cliente válido
**Condição inicial:** Há ao menos 1 representante ativo no seed.
**Ação:** Dashboard → Clientes → Novo Cliente → preencher nome, CNPJ válido e representante.
**Resultado esperado:** Redirect para `/dashboard/clientes`; cliente aparece imediatamente na listagem.
**Verificação adicional:** SQL precondição `SELECT id, nome FROM clientes_b2b WHERE tenant_id = 'jmb' AND cnpj = '12345678000199';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — CNPJ duplicado retorna erro amigável
**Condição inicial:** H2 executado com sucesso.
**Ação:** Repetir o cadastro usando o mesmo CNPJ.
**Resultado esperado:** Form re-renderiza com mensagem `CNPJ já cadastrado` e sem duplicar linha no banco.
**Verificação adicional:** SQL precondição `SELECT COUNT(*) AS n FROM clientes_b2b WHERE tenant_id = 'jmb' AND cnpj = '12345678000199';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — Upload de preços via dashboard
**Condição inicial:** Arquivo/fixture de homologação disponível.
**Ação:** Dashboard → Preços → subir a planilha de homologação.
**Resultado esperado:** Mensagem inline com contagem de linhas processadas e sem erro 500.
**Verificação adicional:** SQL precondição `SELECT COUNT(*) AS n FROM precos_diferenciados WHERE tenant_id = 'jmb';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H5 — Top produtos acessível e navegável
**Condição inicial:** Seed criou pedidos confirmados no tenant `jmb`.
**Ação:** Navegar pela UI até Top Produtos, alterar `dias` e `limite`, voltar para Home.
**Resultado esperado:** `/dashboard/top-produtos` responde 200, filtros são preservados e não há link quebrado para `/dashboard`.
**Verificação adicional:** SQL precondição `SELECT COUNT(*) AS n FROM pedidos WHERE tenant_id = 'jmb' AND status = 'confirmado';`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H6 — Health operacional Anthropic
**Condição inicial:** Ambiente staging em pé e app iniciado com secrets válidos.
**Ação:** Executar `python scripts/health_check.py` e abrir `/health`.
**Resultado esperado:** `health_check.py` retorna exit 0; Anthropic aparece como `ok` ou `degraded`, nunca `fail`.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H7 — Rate limiting do login
**Condição inicial:** Dashboard acessível.
**Ação:** Fazer 6 tentativas consecutivas de login com senha errada a partir da mesma origem.
**Resultado esperado:** A tentativa bloqueada retorna 429 com mensagem visível de throttling.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
[listar hotfixes obrigatórios antes do piloto]
