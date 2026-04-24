# Handoff Sprint 7

## Arquivos alterados

- `output/src/agents/repo.py` — adicionado `GestorRepo.listar_ativos_por_tenant` após linha 629 (fim de `get_by_telefone`)
- `output/src/agents/runtime/agent_cliente.py` — import de `GestorRepo`, `gestor_repo` no `__init__`, bloco `if tenant.whatsapp_number:` substituído por loop sobre gestores ativos
- `output/src/agents/runtime/agent_rep.py` — import de `GestorRepo`, `gestor_repo` no `__init__`, mesmo bloco substituído (caption mantém `Rep: {nome}`)
- `output/src/agents/ui.py` — `_gestor_repo = GestorRepo()` instanciado como dep compartilhada; injetado em `AgentCliente` e `AgentRep`
- `output/src/tests/unit/agents/test_gestor_repo.py` — novo arquivo com 4 testes unit (A1–A4 do contrato)
- `output/src/tests/unit/agents/test_agent_cliente.py` — teste A8 reescrito com mock `GestorRepo` retornando 2 gestores; novo A8b (lista vazia)
- `output/src/tests/unit/agents/test_agent_rep.py` — fixture `gestores_fixture`, `_make_agent` atualizado com `gestor_repo`, R03 reescrito (A7), novo A8 análogo
- `output/src/tests/unit/agents/test_agent_cliente_linguagem_br.py` — `_make_agent` atualizado com `_make_gestor_mock()` (1 gestor default); H01 assertion corrigida (número do gestor, não `tenant.whatsapp_number`)
- `scripts/smoke_sprint_7.py` — novo script: S1-HEALTH, S2-GESTOR-ATIVO, S3-PYTEST-UNIT

## Decisões de design relevantes

**Injeção com default `GestorRepo()`:** `gestor_repo: GestorRepo | None = None` com `self._gestor_repo = gestor_repo or GestorRepo()` satisfaz M_INJECT (ui.py injeta instância real) e mantém compatibilidade retroativa (construtores sem `gestor_repo` continuam funcionando).

**try/except individual por gestor:** exceção em um gestor não impede notificação dos demais. Log com `gestor_id` facilita diagnóstico em produção.

**test_agent_cliente_linguagem_br.py:** arquivo fora do escopo primário do sprint mas afetado pela mudança. `_make_agent` recebe `gestor_repo=_make_gestor_mock()` que retorna 1 gestor com número `5519999990000` — coincide com `tenant.whatsapp_number` anterior para mínima disrupção nos asserts existentes.

## Pendências ou riscos

- A_SMOKE requer acesso ao macmini-lablz (`ssh macmini-lablz`) e ao menos 1 gestor cadastrado no banco JMB (`INSERT INTO gestores ...`) — verificar antes da homologação.
- Se `DATABASE_URL` não estiver configurado no macmini, S2 do smoke reportará `FAILED` mas é recuperável via `infisical run --env=staging`.

## Auto-avaliação

| Check | Resultado |
|-------|-----------|
| lint-imports | N/A (não encontra config fora de `output/`) |
| zero print() | PASS |
| zero secrets | PASS |
| pytest unit | 279 passed, 0 failed |

Testes novos/modificados passando:
- `test_gestor_repo.py` — 4/4
- `test_agent_cliente.py::test_agent_cliente_confirmar_pedido_cadeia_completa` — PASS (2 chamadas, números corretos)
- `test_agent_cliente.py::test_agent_cliente_confirmar_pedido_sem_gestores` — PASS (0 chamadas)
- `test_agent_rep.py::test_agent_rep_confirmar_cliente_valido_cria_pedido` — PASS (2 chamadas, caption com "Rep: ")
- `test_agent_rep.py::test_agent_rep_confirmar_sem_gestores_nao_envia_media` — PASS (0 chamadas)
- `test_agent_cliente_linguagem_br.py::test_grupo_h_h01_confirmar_pedido_cadeia_completa` — PASS (corrigido)

## Invocar Evaluator
O Evaluator deve ser invocado agora com: `artifacts/sprint_contract.md` como referência.
