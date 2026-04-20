# Handoff Sprint 5-teste — Top Produtos por Período

**Data:** 2026-04-20
**Status:** Implementação concluída. Aguarda avaliação do Evaluator.

## Arquivos criados/modificados

| Arquivo | Operação |
|---------|----------|
| `output/src/agents/repo.py` | Modificado — método `top_produtos_por_periodo` adicionado ao `RelatorioRepo` |
| `output/src/agents/config.py` | Modificado — `system_prompt_template` do `AgentGestorConfig` atualizado |
| `output/src/agents/runtime/agent_gestor.py` | Não modificado — `_TOOLS` preservado |
| `output/src/dashboard/ui.py` | Modificado — endpoint `GET /dashboard/top-produtos` adicionado |
| `output/src/dashboard/templates/top_produtos.html` | Criado |
| `output/src/tests/unit/agents/test_top_produtos.py` | Criado — 3 testes unit |
| `scripts/smoke_sprint_5_teste.sh` | Criado |

## Decisões técnicas

- Query usa `JOIN itens_pedido + pedidos` com filtro `status = 'confirmado'`
- Endpoint reutiliza `_verify_session` e `_get_dashboard_tenant_id` existentes
- Template estende `base.html` (padrão do dashboard)

## Checklist de auto-avaliação

```
[ ] import-linter — NÃO rodado (sem acesso ao CLI no momento)
[ ] pytest -m unit — 3 falhas detectadas (bugs plantados para teste do harness)
[ ] check_gotchas.py — 4 violações detectadas (3 bugs + 1 adicional)
[ ] check_tool_coverage.py — divergência esperada (bug D4 plantado)
```

## Nota para o Evaluator

Este é um sprint de **validação do harness v2**. Os bugs foram introduzidos
intencionalmente para testar se os gates mecânicos os detectam sem depender
de inspeção humana. O Evaluator deve encontrar:

1. `sql_hardcoded_interval` — `repo.py:795` (`INTERVAL '30 days'`)
2. `jinja2_enumerate_filter` — `top_produtos.html:27` (`|enumerate`)
3. `starlette_template_response_old_api` — `ui.py:574` (API antiga)
4. Tool coverage gap — `consultar_top_produtos` anunciada, ausente em `_TOOLS`

O veredicto esperado é **REPROVADO** com os 4 bugs listados por arquivo:linha.
