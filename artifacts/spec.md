# Sprint 7 — Notificação ao Gestor (TD-08)

**Status:** Em planejamento
**Data:** 2026-04-24
**Pré-requisitos:** Sprint 6 APROVADO (v0.6.1), piloto JMB ativo

## Objetivo

Ao final deste sprint, todo pedido confirmado via AgentCliente ou AgentRep
envia o PDF para **todos os gestores ativos do tenant** via WhatsApp, em vez
de depender de `tenant.whatsapp_number` que estava `None` no tenant JMB.

## Contexto

Durante o piloto JMB (iniciado 2026-04-22), identificamos que nenhuma
notificação chegava ao gestor após pedidos confirmados — bug B-01 / TD-08.
Causa raiz: `tenant.whatsapp_number` é `None` para JMB; o código em
`agent_cliente.py:713` e `agent_rep.py:889` faz `if tenant.whatsapp_number:`
e salta o envio. A tabela `gestores` (migration 0015) já suporta múltiplos
gestores por tenant com campo `telefone`, mas `GestorRepo` só expõe
`get_by_telefone()`. Este sprint adiciona `listar_ativos_por_tenant()` e
corrige ambos os agents para iterar sobre os gestores.

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents | Repo, Runtime, Tests |

## Considerações multi-tenant

Toda chamada a `listar_ativos_por_tenant` passa `tenant_id` explicitamente
(parâmetro obrigatório). A query filtra `WHERE tenant_id = :tenant_id AND ativo = true`.
Nenhum gestor de outro tenant pode aparecer no resultado. Não há impacto em
dados de pedidos ou clientes.

## Secrets necessários (Infisical)

Nenhum secret novo. `EVOLUTION_API_KEY` e `EVOLUTION_API_URL` já cadastrados
(Sprint 1).

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| asyncpg | `result.mappings().all()` retorna lista vazia (não None) quando sem rows | Tratar como lista vazia — coberto pelo `if gestores:` |
| Evolution API | `send_whatsapp_media` silencia exceção | Log `warning` com `gestor_id` em cada falha individual |

## Entregas

### E1 — GestorRepo: `listar_ativos_por_tenant`

**Camadas:** Repo
**Arquivo(s):** `output/src/agents/repo.py` (após linha 629)

**Critérios de aceitação:**
- [ ] Método `async def listar_ativos_por_tenant(self, tenant_id: str, session: AsyncSession) -> list[Gestor]` existe em `GestorRepo`
- [ ] Retorna apenas gestores com `ativo = true` filtrados por `tenant_id`
- [ ] Retorna lista vazia (não levanta exceção) quando nenhum gestor cadastrado
- [ ] Gestor inativo não aparece no resultado
- [ ] Gestor de outro tenant não aparece no resultado

### E2 — AgentCliente: loop sobre gestores ativos

**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/runtime/agent_cliente.py` (linhas 712–726)

**Critérios de aceitação:**
- [ ] Bloco `if tenant.whatsapp_number:` removido
- [ ] Substituído por `gestores = await self._gestor_repo.listar_ativos_por_tenant(tenant.id, session)`
- [ ] Loop `for gestor in gestores:` chama `send_whatsapp_media` com `numero=gestor.telefone`
- [ ] Quando lista vazia: nenhum envio, nenhuma exceção, pedido segue confirmado
- [ ] `GestorRepo` injetado no `__init__` do `AgentCliente` se ainda não estiver

### E3 — AgentRep: loop sobre gestores ativos

**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/runtime/agent_rep.py` (linhas 888–903)

**Critérios de aceitação:**
- [ ] Mesma correção de E2 aplicada
- [ ] Caption mantém `Rep: {representante.nome}` no texto
- [ ] `GestorRepo` injetado no `__init__` do `AgentRep` se ainda não estiver

### E4 — Testes unitários

**Camadas:** Tests
**Arquivo(s):**
- `output/src/tests/unit/agents/test_agent_cliente.py`
- `output/src/tests/unit/agents/test_agent_rep.py`
- `output/src/tests/unit/agents/test_gestor_repo.py` (novo)

**Critérios de aceitação:**
- [ ] Teste A8 atualizado: mock `listar_ativos_por_tenant` retorna 2 gestores → `send_whatsapp_media` chamado 2 vezes com telefones corretos
- [ ] Teste A8b (novo): mock retorna lista vazia → `send_whatsapp_media` não chamado
- [ ] Teste análogo no AgentRep atualizado
- [ ] `test_gestor_repo.py` com 3 testes: lista ativos, isolamento tenant, lista vazia
- [ ] Todos marcados com `@pytest.mark.unit`
- [ ] `pytest -m unit` passa sem erros

### E5 — Smoke script

**Camadas:** Scripts
**Arquivo(s):** `scripts/smoke_sprint_7.py`

**Critérios de aceitação:**
- [ ] Script executa contra macmini-lablz sem parâmetros
- [ ] Verifica `GET /health` → status ok
- [ ] Verifica existência de ≥ 1 gestor ativo no tenant JMB via query direta
- [ ] Saída `ALL OK` quando tudo passa

## Critério de smoke staging (obrigatório)

Script: `scripts/smoke_sprint_7.py`

O script deve verificar automaticamente, contra infra real (macmini-lablz):
- [ ] `GET http://100.113.28.85:8000/health` → `{"status": "ok"}`
- [ ] Query: `SELECT COUNT(*) FROM gestores WHERE tenant_id = '<jmb_tenant_id>' AND ativo = true` → ≥ 1
- [ ] `pytest -m unit` passa sem erros (roda no macmini-lablz)

Execução esperada: `python scripts/smoke_sprint_7.py` → saída `ALL OK`

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | Gestor recebe PDF — pedido via cliente | Confirmar pedido pelo número do cliente piloto via WhatsApp | PDF do pedido chega ao número do gestor |
| H2 | Gestor recebe PDF — pedido via rep | Confirmar pedido pelo número do rep piloto | PDF chega ao gestor com caption incluindo "Rep: [nome]" |
| H3 | Caption correta AgentCliente | Ler texto da mensagem recebida | "Novo pedido PED-XXXXXXXX \| N iten(s) \| R$ X,XX" |
| H4 | Caption correta AgentRep | Ler texto da mensagem recebida | Contém "Rep: [nome do rep]" |
| H5 | Sem duplicatas | Um pedido → verificar inbox do gestor | Exatamente 1 PDF por confirmação |
| H6 | Banco — gestor ativo cadastrado | `SELECT telefone FROM gestores WHERE tenant_id=... AND ativo=true` | Retorna número correto do gestor JMB |

## Decisões pendentes

Nenhuma. A estratégia "notificar todos os gestores ativos" é determinística
a partir do bug report B-01 e não requer novo ADR.

## Fora do escopo

- AgentGestor não é alterado (já envia PDF ao gestor que confirmou)
- Nenhuma nova migration ou alteração de schema
- Nenhuma configuração no dashboard de quais gestores recebem notificação
- Nenhum retry automático em falha na Evolution API
- Cadastro/CRUD de gestores não faz parte deste sprint

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| `GestorRepo` não injetado nos agents | Média | Alto | Verificar `__init__` antes de codificar; injetar se ausente |
| Exceção silenciosa no loop de gestores | Baixa | Médio | `try/except` externo existente captura; log `warning` por gestor |
| Gestor com número inválido no banco | Baixa | Baixo | Evolution API silencia falha; warning logado com `gestor_id` |

## Handoff para Sprint 8

- `GestorRepo.listar_ativos_por_tenant` disponível para broadcast de promoções
  e alertas proativos
- Se piloto confirmar multi-gestor estável, Sprint 8 pode adicionar
  configuração de notificação por evento no dashboard
