# Homologação Sprint 5 — Observabilidade LLM, Configurações e Relatórios

**Status:** PENDENTE
**Data prevista:** TBD (após smoke gate passar)
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head` (migrations 0016 + 0017)
- [ ] Seed de dados: `python scripts/seed_homologacao_sprint-5.py`
- [ ] Smoke gate passou: `python scripts/smoke_sprint_5.py` → ALL OK
- [ ] Health check geral: `curl http://100.113.28.85:8000/health` → versão correta
- [ ] Langfuse UP: `curl http://100.113.28.85:3000/api/public/health` → 200 OK
- [ ] Gates harness v2 passaram: G2, G3, G5, G7 todos verdes

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Trace AgentCliente aparece no Langfuse
**Condição inicial:** Langfuse rodando em staging. Cliente cadastrado no seed.
**Ação:** Enviar mensagem WhatsApp como cliente (ex: "quero 2 caixas de shampoo Johnson").
**Resultado esperado:** Abrir http://100.113.28.85:3000 → Traces → trace da conversa visível com nome `processar_mensagem_cliente` e tag do tenant.
**Verificação adicional:** Spans de tool call (buscar_produtos, confirmar_pedido) aparecem como filhos do trace.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Tokens/custo registrados por conversa
**Condição inicial:** H1 executado.
**Ação:** Abrir o trace gerado em H1 → aba "Usage".
**Resultado esperado:** `input_tokens` e `output_tokens` preenchidos (valores > 0).
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — Criar cliente fictício via dashboard
**Condição inicial:** Dashboard acessível. Ao menos 1 rep cadastrado no seed.
**Ação:** Dashboard → Clientes → botão "Novo Cliente" → preencher:
  - Nome: Farmácia Teste Ltda
  - CNPJ: 12345678000199
  - Telefone: +5511999990001
  - Representante: {rep do seed}
  - → Salvar
**Resultado esperado:** Redirect para `/dashboard/clientes`. "Farmácia Teste Ltda" aparece na lista.
**Verificação de banco:** `SELECT nome FROM clientes_b2b WHERE cnpj = '12345678000199' AND tenant_id = '{tenant}';` → retorna 1 linha.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — CNPJ duplicado retorna erro amigável
**Condição inicial:** H3 executado (cliente com CNPJ 12345678000199 existe).
**Ação:** Dashboard → Clientes → Novo Cliente → mesmo CNPJ (12345678000199) → Salvar.
**Resultado esperado:** Form retorna com mensagem "CNPJ já cadastrado" — sem criar duplicata.
**Verificação de banco:** `SELECT COUNT(*) FROM clientes_b2b WHERE cnpj = '12345678000199';` → retorna 1.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H5 — Editar telefone de representante e testar IdentityRouter
**Condição inicial:** Rep cadastrado no seed com telefone antigo (ex: +5511888880001).
**Ação:** Dashboard → Representantes → {rep} → Editar → Telefone: +5511777770099 → Salvar.
**Resultado esperado:** Salvo com sucesso (redirect ou mensagem de confirmação).
**Verificação:** Enviar mensagem WhatsApp do número +5511777770099 → agente responde como rep (não como cliente).
**Verificação de banco:** `SELECT telefone FROM representantes WHERE id = '{rep_id}';` → retorna '+5511777770099'.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H6 — Filtro de período na página de representantes
**Condição inicial:** Ao menos 1 pedido confirmado no seed (variando por data).
**Ação:** Dashboard → Representantes → clicar "7 dias" no seletor de período.
**Resultado esperado:** Tabela atualiza via htmx (sem reload completo da página). GMV pode diferir do período de 30 dias se houver pedidos antigos no seed.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H7 — Detalhe de rep com breakdown por cliente
**Condição inicial:** Rep com ao menos 2 clientes com pedidos confirmados no seed.
**Ação:** Dashboard → Representantes → clicar no nome de um rep.
**Resultado esperado:** Nova página `/dashboard/representantes/{id}` com tabela: Cliente | Pedidos | GMV | Último pedido. Ordenado por GMV desc.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H8 — AgentGestor relatório de reps via WhatsApp
**Condição inicial:** Gestor cadastrado. Ao menos 1 rep com pedidos no seed.
**Ação:** Gestor via WhatsApp: "quais reps venderam mais nos últimos 7 dias?"
**Resultado esperado:** Resposta em formato WhatsApp com ranking usando *bold*, GMV por rep e cliente topo. Sem tabela markdown.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
[lista de bugs para hotfix antes do Sprint 6]
