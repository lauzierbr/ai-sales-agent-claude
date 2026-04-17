# Retrospectiva Sprint 3 — AgentRep + Hardening Linguagem Brasileira

**Data:** 2026-04-17
**Participantes:** Lauzier + Claude
**Sprint:** 3 (branch `claude/awesome-benz`, tag `v0.4.0`)

---

## O que foi bem

- **Generator/Evaluator loop convergiu** — 2 rodadas de negociação de contrato,
  202/202 testes passando antes de chegar na homologação
- **AgentRep funcional end-to-end** — busca produto, busca cliente da carteira,
  fecha pedido em nome do cliente; isolamento de carteira validado no staging
- **35 cenários de linguagem brasileira** — cobertura real de "fecha aí", "manda
  5 cx", "não deixa", saudação sem tool-call; hardening funcionou em produção
- **Fix de IdentityRouter detectado na homologação** — mesmo número em duas
  tabelas, prioridade estava errada; o staging com dados reais revelou o que
  os testes com mocks não pegaram
- **UX de feedback** (mark-as-read + typing) — implementado e validado em <15
  minutos após pedido, mostrou que a arquitetura de `service.py` está extensível
- **Detecção de conflito cross-table** — `IdentityRouter` agora loga warning
  explícito quando mesmo telefone aparece em `representantes` e `clientes_b2b`

---

## O que poderia ter sido melhor

### P1 — Migration sem atualização do modelo Pydantic
**O que aconteceu:** Migration 0014 tornou `clientes_b2b.telefone` nullable e o
dado foi limpo no banco, mas `ClienteB2B.telefone: str` no modelo Pydantic não
foi atualizado. Resultado: `ValidationError` em produção descoberto só após o
deploy.

**Por que escapou:** A checagem foi feita DB → dado, sem verificar o contrato
da camada de Types. Não rodei `pytest -m unit` antes do deploy.

**Regra criada:** Toda migration que altera nullable obriga atualização do
modelo Pydantic na mesma PR + `pytest -m unit` antes de qualquer deploy.
Ver checklist em `HOMOLOGACAO.md`.

---

### P2 — ANTHROPIC_API_KEY esgotada sem aviso
**O que aconteceu:** A chave em staging estava com saldo zerado. O bot recebia
os webhooks normalmente mas falha silenciosa no Claude API bloqueou 40+ min
de homologação.

**Por que escapou:** Não há health check de saldo na API key. O `health_check.py`
verifica Postgres, Redis, Evolution — mas não a Anthropic.

**Ação:** TD-02 aberto no tech-debt-tracker. Sprint 4 ou Sprint 5 deve incluir
um endpoint `/health` que faz uma chamada mínima à Anthropic e retorna status.

---

### P3 — Dados de seed do Sprint 1 conflitaram com Sprint 3
**O que aconteceu:** O telefone `5519992066177` foi inserido como cliente LZ Muzel
no Sprint 1 (seed de teste com número real do Lauzier). No Sprint 3, o mesmo
número virou o representante João. IdentityRouter retornava `CLIENTE_B2B` em vez
de `REPRESENTANTE`.

**Por que aconteceu:** Seeds de homologação usaram número real sem verificar
conflito com dados de sprints anteriores.

**Regra criada:** Seeds de homologação devem usar números sintéticos (ex:
`5519000000001`) para papéis de teste. Números reais só para o papel definitivo
(cliente/rep real da JMB).

---

### P4 — Documentação de infra de staging desatualizada
**O que aconteceu:** `HOMOLOGACAO.md` listava hostname `mac-mini-lablz`; o correto
é `macmini-lablz` (sem hífen). Custou uma tentativa de SSH com erro.

**Ação:** Corrigido inline. Regra: qualquer mudança de hostname/porta de staging
vai direto no `HOMOLOGACAO.md` no mesmo commit.

---

### P5 — Infisical session expirou no staging sem aviso
**O que aconteceu:** `infisical run` falhou silenciosamente no macmini por sessão
expirada. Deploy bloqueado até login manual.

**Ação:** Antes de cada homologação, rodar `infisical whoami` no staging como
parte do pré-requisito. Adicionar ao checklist de homologação.

---

## O que fazemos de agora em diante

| # | Regra | Onde está documentado |
|---|-------|-----------------------|
| R1 | Toda migration nullable → atualizar Pydantic na mesma PR + `pytest -m unit` antes do deploy | `HOMOLOGACAO.md` — Checklist de migrations |
| R2 | Seeds de homologação usam números sintéticos; nunca reutilizar número real entre sprints | Esta retro + checklist de seed |
| R3 | `pytest -m unit` é gate obrigatório antes de qualquer `git push` para staging | `HOMOLOGACAO.md` — Fluxo item 2b |
| R4 | Verificar `infisical whoami` no staging antes de iniciar homologação | `HOMOLOGACAO.md` — Pré-requisitos |
| R5 | Mudança de hostname/porta de staging → commit imediato em `HOMOLOGACAO.md` | Convenção de documentação |
| R6 | TD-02: health check de saldo Anthropic API a implementar no Sprint 4 ou 5 | `tech-debt-tracker.md` |

---

## Métricas do sprint

| Métrica | Valor |
|---------|-------|
| Testes unitários entregues | 202 (100% pass) |
| Bugs encontrados na homologação | 3 (IdentityRouter priority, API key, telefone nullable) |
| Bugs introduzidos pelo fix | 1 (Pydantic model não atualizado com migration) |
| Hotfixes pós-homologação | 4 commits |
| Funcionalidades homologadas com sucesso | AgentRep + hardening linguagem |
| UX extras entregues | mark-as-read + typing indicator |
