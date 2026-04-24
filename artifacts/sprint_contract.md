# Sprint Contract — Sprint 7 — Notificação ao Gestor

**Status:** ACEITO
**Data:** 2026-04-24

---

## Entregas comprometidas

1. **E1 — GestorRepo.listar_ativos_por_tenant**: método async adicionado em
   `output/src/agents/repo.py` após a linha 629 (fim do método `get_by_telefone`),
   retornando `list[Gestor]` com filtros obrigatórios `tenant_id` e `ativo = true`.

2. **E2 — AgentCliente._confirmar_pedido loop de notificação**: bloco
   `if tenant.whatsapp_number:` (linhas 713–726 de `agent_cliente.py`) substituído
   por consulta a `GestorRepo.listar_ativos_por_tenant` e loop `for gestor in gestores:`;
   `GestorRepo` injetado no `__init__` do `AgentCliente`.

3. **E3 — AgentRep._confirmar_pedido_em_nome_de loop de notificação**: mesma
   correção aplicada em `agent_rep.py` linhas 888–903; caption mantém
   `Rep: {representante.nome}`; `GestorRepo` injetado no `__init__` do `AgentRep`.

4. **E4 — Testes unitários**: teste A8 atualizado em
   `test_agent_cliente.py`; novo A8b (lista vazia); testes análogos para
   `AgentRep`; novo `test_gestor_repo.py` com 3 casos; todos `@pytest.mark.unit`;
   `pytest -m unit` passa sem erros.

5. **E5 — Smoke script**: `scripts/smoke_sprint_7.py` verifica `/health`,
   gestor ativo no banco JMB e `pytest -m unit`; saída `ALL OK`, exit 0.

---

## Critérios de aceitação — Alta (bloqueantes)

**A1. GestorRepo.listar_ativos_por_tenant — assinatura e isolamento de tenant**
    Teste:
    ```python
    import inspect, src.agents.repo as r
    sig = inspect.signature(r.GestorRepo.listar_ativos_por_tenant)
    assert "tenant_id" in sig.parameters
    assert "session" in sig.parameters
    ```
    Evidência esperada: sem `AssertionError`; tipo de retorno anotado como
    `list[Gestor]`; corpo da função contém `WHERE tenant_id = :tenant_id AND ativo = true`.

**A2. GestorRepo.listar_ativos_por_tenant — lista vazia segura**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_gestor_repo.py::test_listar_ativos_lista_vazia`
    Evidência esperada: 1 passed; mock retorna 0 rows; método devolve `[]` sem levantar exceção.

**A3. GestorRepo.listar_ativos_por_tenant — gestor inativo excluído**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_gestor_repo.py::test_listar_ativos_exclui_inativos`
    Evidência esperada: 1 passed; gestor com `ativo=false` não aparece na lista.

**A4. GestorRepo.listar_ativos_por_tenant — isolamento de tenant**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_gestor_repo.py::test_listar_ativos_isolamento_tenant`
    Evidência esperada: 1 passed; gestor de tenant diferente não aparece na lista.

**A5. AgentCliente — loop notifica 2 gestores**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_cliente.py::test_agent_cliente_confirmar_pedido_cadeia_completa`
    (teste A8 atualizado)
    Evidência esperada: 1 passed; `send_whatsapp_media` chamado exatamente
    2 vezes com telefones dos 2 gestores mockados; `tenant.whatsapp_number` não referenciado.

**A6. AgentCliente — lista vazia não chama send_whatsapp_media**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_cliente.py::test_agent_cliente_confirmar_pedido_sem_gestores`
    (teste A8b novo)
    Evidência esperada: 1 passed; `send_whatsapp_media` chamado 0 vezes;
    pedido retornado normalmente sem exceção.

**A7. AgentRep — loop notifica gestores com caption correta**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_rep.py` (teste análogo ao A5)
    Evidência esperada: 1 passed; `send_whatsapp_media` chamado para cada gestor;
    `caption` contém a substring `"Rep: "`.

**A8. AgentRep — lista vazia não chama send_whatsapp_media**
    Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_rep.py` (teste análogo ao A6)
    Evidência esperada: 1 passed; `send_whatsapp_media` chamado 0 vezes;
    pedido retornado normalmente.

**A9. Nenhum teste unit realiza I/O externo**
    Teste: `pytest -m unit --tb=short 2>&1 | grep -i "socket\|connection\|asyncpg\|psycopg\|redis"`
    Evidência esperada: saída vazia (nenhuma conexão real tentada).

**A10. if tenant.whatsapp_number removido de ambos os agents**
    Teste:
    ```bash
    grep -n "tenant.whatsapp_number" \
      output/src/agents/runtime/agent_cliente.py \
      output/src/agents/runtime/agent_rep.py
    ```
    Evidência esperada: zero ocorrências em ambos os arquivos.

**A11. GestorRepo injetado nos __init__ de AgentCliente e AgentRep**
    Teste:
    ```bash
    grep -n "gestor_repo\|GestorRepo" \
      output/src/agents/runtime/agent_cliente.py \
      output/src/agents/runtime/agent_rep.py
    ```
    Evidência esperada: ocorrências no `__init__` de ambas as classes e na
    atribuição `self._gestor_repo = ...`.

**A12. pytest -m unit passa integralmente**
    Teste: `pytest -m unit output/src/tests/unit/ -q`
    Evidência esperada: zero falhas; zero erros de coleta.

**A_SMOKE. Smoke gate staging — caminho crítico com infra real**
    Teste:
    ```bash
    ssh macmini-lablz "cd ~/ai-sales-agent-claude && \
      python scripts/smoke_sprint_7.py"
    ```
    Evidência esperada: saída contém `ALL OK`, exit code 0.
    Checks mínimos do script:
    - `GET http://100.113.28.85:8000/health` responde `{"status": "ok"}`
    - `SELECT COUNT(*) FROM gestores WHERE tenant_id = '<jmb_id>' AND ativo = true` retorna >= 1
    - `pytest -m unit` passa no macmini-lablz
    Nota: obrigatório pois o sprint toca Runtime.

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

**M1. Type hints completos em GestorRepo.listar_ativos_por_tenant e nos __init__ modificados**
    Teste: `mypy --strict output/src/agents/repo.py output/src/agents/runtime/agent_cliente.py output/src/agents/runtime/agent_rep.py`
    Evidência esperada: 0 erros.

**M2. Docstring em GestorRepo.listar_ativos_por_tenant**
    Teste: inspeção manual do método adicionado.
    Evidência esperada: docstring presente com Args, Returns e nota de
    isolamento de tenant.

**M3. Cobertura de testes unitários nas funções modificadas**
    Teste: `pytest -m unit --cov=output/src/agents --cov-report=term-missing`
    Evidência esperada: cobertura das funções modificadas/novas >= 80%.

**M_INJECT. Injeção de GestorRepo sem None em ui.py**
    Teste: inspeção de `output/src/agents/ui.py` (ou arquivo de factory) para
    confirmar que `GestorRepo()` e instanciado e passado ao construir
    `AgentCliente` e `AgentRep`.
    Evidência esperada: nenhuma instância de `AgentCliente` ou `AgentRep` e
    construida sem `gestor_repo` (parametro obrigatorio ou default nao-None).

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 4**

(Se 2 ou mais critérios de Média falharem, o sprint é reprovado mesmo com
todos os de Alta passando.)

---

## Fora do escopo deste contrato

- AgentGestor (`agent_gestor.py`) — não alterado neste sprint.
- Nenhuma migration de banco (tabela `gestores` já existe desde migration 0015).
- Dashboard de configuração de notificações por gestor.
- Retry automático em falha na Evolution API.
- CRUD de gestores no painel.
- Nenhuma alteração em `catalog/`, `orders/`, `tenants/` ou `providers/`.
- Teste de multi-turn (A_MULTITURN) — este sprint não altera fluxo conversacional,
  apenas o bloco de notificação pós-confirmação de pedido.

---

## Ambiente de testes

```
pytest -m unit    -> roda no container do Evaluator (sem servicos externos)
                    obrigatorio: mocks para asyncpg/SQLAlchemy e Anthropic
pytest -m staging -> roda no macmini-lablz com Postgres + Redis reais, sem WhatsApp real
                    abrange: query real de gestores, injecao de deps em ui.py
pytest -m integration -> nao roda no container; requer macmini-lablz com Evolution API
```

### Gotchas conhecidos (workarounds obrigatórios na implementação)

| Área | Gotcha | Workaround |
|------|--------|------------|
| asyncpg | `result.mappings().all()` retorna lista vazia, não None | Tratar retorno como lista — `if gestores:` antes do loop |
| Evolution API | `send_whatsapp_media` silencia exceção | `try/except` por gestor com `log.warning("notif_gestor_falha", gestor_id=..., error=...)` |
