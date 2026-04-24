# Homologação Sprint 7 — Notificação ao Gestor

**Status:** PENDENTE
**Data prevista:** TBD
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head`
- [ ] Seed de dados: `python scripts/seed_homologacao_sprint-7.py`
- [ ] Smoke gate passou: `python scripts/smoke_sprint_7.py` → ALL OK
- [ ] Health check: `curl http://100.113.28.85:8000/health` → versão correta

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Gestor recebe PDF após pedido confirmado via cliente

**Condição inicial:** Gestor com telefone cadastrado e `ativo=true` no banco; cliente piloto cadastrado com telefone
**Ação:** Enviar mensagem de pedido pelo número do cliente piloto via WhatsApp e confirmar
**Resultado esperado:** PDF do pedido chega ao WhatsApp do gestor
**Verificação de banco:** `SELECT telefone FROM gestores WHERE tenant_id='...' AND ativo=true`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Gestor recebe PDF após pedido confirmado via representante

**Condição inicial:** Mesmo gestor ativo; representante piloto cadastrado
**Ação:** Confirmar pedido pelo número do rep via WhatsApp
**Resultado esperado:** PDF chega ao gestor com caption incluindo "Rep: [nome]"
**Verificação de banco:** Checar tabela `pedidos` — 1 novo pedido criado
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — Caption correta (AgentCliente)

**Condição inicial:** Pedido confirmado em H1
**Ação:** Verificar texto da mensagem recebida pelo gestor
**Resultado esperado:** "Novo pedido PED-XXXXXXXX | N iten(s) | R$ X,XX"
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — Caption correta (AgentRep)

**Condição inicial:** Pedido confirmado em H2
**Ação:** Verificar texto da mensagem recebida pelo gestor
**Resultado esperado:** Contém "Rep: [nome do representante]"
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H5 — Sem duplicatas

**Condição inicial:** Um único pedido confirmado
**Ação:** Verificar inbox do gestor no WhatsApp
**Resultado esperado:** Exatamente 1 PDF recebido por confirmação de pedido
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H6 — Banco confirma gestor ativo cadastrado

**Condição inicial:** Banco staging acessível
**Ação:** `SELECT id, telefone, nome FROM gestores WHERE tenant_id='<jmb_id>' AND ativo=true`
**Resultado esperado:** ≥ 1 linha com telefone correspondente ao gestor JMB
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
[lista de bugs para hotfix antes do Sprint 8]
