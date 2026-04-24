# Sprint 7 — Notificação ao Gestor (TD-08)

**Status:** Em planejamento
**Data:** 2026-04-24
**Versão alvo:** v0.7.0

## Objetivo

Corrigir bug B-01 / TD-08: gestores não recebiam PDF ao confirmar pedido
porque `tenant.whatsapp_number` era `None`. Solução: usar
`GestorRepo.listar_ativos_por_tenant()` e enviar para cada gestor ativo.

## Entregas (checklist do Generator)

- [x] E1 — `GestorRepo.listar_ativos_por_tenant()` em `output/src/agents/repo.py`
- [x] E2 — AgentCliente: substituir `if tenant.whatsapp_number:` por loop de gestores
- [x] E3 — AgentRep: mesma correção
- [x] E4 — Testes unitários (A8 atualizado + test_gestor_repo.py novo)
- [x] E5 — `scripts/smoke_sprint_7.py`

**Resultado Evaluator:** APROVADO — 279 unit tests, 13 regression, 0 falhas

## Log de decisões

| Data | Decisão | Motivo |
|------|---------|--------|
| 2026-04-24 | Sem migration — tabela `gestores` já tem `ativo` + `telefone` (0015) | Schema já suporta N gestores |
| 2026-04-24 | AgentGestor fora do escopo — já envia ao próprio gestor | Comportamento correto atual |
| 2026-04-24 | Falha no envio para 1 gestor não interrompe loop | `try/except` externo existente |

## Notas de execução

- Verificar se `self._gestor_repo` já existe no `__init__` de `AgentCliente` e
  `AgentRep` antes de modificar — `GestorRepo` é usado no `IdentityRouter` mas
  pode não estar injetado diretamente nos agents.
- `send_whatsapp_media` já é fire-and-forget (não propaga exceção). Log
  `warning` com `gestor_id` deve ser adicionado dentro do loop.
- Caption do AgentRep deve manter `Rep: {representante.nome}`.
