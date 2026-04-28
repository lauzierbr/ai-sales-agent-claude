# Pre-Homologation Review — Protocolo obrigatório

Antes de declarar um sprint pronto para homologação humana, o Generator (ou um
sub-agente delegado) DEVE executar este protocolo e anexar o resultado em
`artifacts/pre_homolog_review_sprint_N.md`. Sem esse artefato com PASS, o
Evaluator não emite APROVADO final.

Este protocolo é o que descobre bugs comportamentais que `pytest -m unit`,
`smoke gate` de endpoints e `lint-imports` não pegam. Foi instituído após a
rejeição do Sprint 9, onde 8 bugs (B-14 a B-21) foram descobertos pelo usuário
em 30 segundos de uso real, com smoke gate verde e Evaluator aprovado.

---

## Parte 1 — Dashboard (Chrome DevTools MCP / Playwright / Preview MCP)

### Pré-requisitos

- App rodando em staging com versão correta no `/health`
- Credenciais de staging:
  - `DASHBOARD_TENANT_ID` (lido via Infisical)
  - `DASHBOARD_SECRET` (lido via Infisical)
- BD com dados não-triviais (`commerce_*` populado, contatos cadastrados)

### Rotas a navegar (sempre todas — sem cherry-picking)

Login em `/dashboard/login` com `DASHBOARD_SECRET`, depois navegar:

| # | Rota | O que verificar |
|---|------|-----------------|
| 1 | `/dashboard/home` | KPIs (GMV, pedidos, ticket) refletem dados reais; bloco "Última sync EFOS" mostra timestamp real (não "Nunca sincronizado" se há sync_runs success); pedidos recentes; conversas ativas |
| 2 | `/dashboard/pedidos` | Listagem com pedidos do banco — se `commerce_orders` tem N rows, listagem deve mostrar N (ou paginação correta). Se `pedidos` estiver vazia mas `commerce_orders` populada, exibir os EFOS |
| 3 | `/dashboard/conversas` | Conversas dos últimos 24h aparecem; persona, telefone, status corretos |
| 4 | `/dashboard/contatos` | Listagem de gestores/reps cadastrados; coluna CONTATO não pode ser sempre "—" |
| 5 | `/dashboard/clientes` | Listagem mostra clientes — se `clientes_b2b` vazia mas `commerce_accounts_b2b` populada (ex: 614), exibir os EFOS |
| 6 | `/dashboard/precos` | UI de upload Excel renderiza |
| 7 | `/dashboard/feedbacks` | Listagem de feedbacks por perfil |
| 8 | `/dashboard/top-produtos` | Top N produtos vendidos — se `pedidos`/`itens_pedido` vazios mas `commerce_sales_history` ou `commerce_order_items` populadas, exibir agregação dos EFOS |
| 9 | `/dashboard/representantes` | Listagem de reps com GMV — fallback para `commerce_vendedores` + `commerce_orders` quando `pedidos` vazio. **Verificar se a rota está no menu de navegação principal** — se existe mas não está na nav, é bug |
| 10 | `/dashboard/configuracoes` | Tenant info; campos preenchidos |

### Critério de PASS por rota

Para cada rota com listagem (1, 2, 4, 5, 7, 8, 9):
- Se o banco tem dados (verificar via `SELECT COUNT(*)` na tabela canônica),
  a página NÃO pode mostrar "Nenhum X encontrado"
- Comparar count do banco vs count visível na página (ou paginação)
- Capturar screenshot e snapshot a11y

Para cada rota com KPIs/dashboards (1):
- KPIs não podem ser todos zero quando há dados no banco
- Bloco de status (sync_runs, conexões, etc) deve refletir dados reais

### Output esperado

`artifacts/pre_homolog_review_sprint_N.md` com tabela:

```markdown
| Rota | Esperado | Observado | Status |
|------|----------|-----------|--------|
| /dashboard/home | GMV>0, sync=27/04, pedidos>0 | GMV=0, sync="Nunca", pedidos=0 | FAIL — B-18, B-19 |
| /dashboard/pedidos | 2592 itens (commerce_orders) | "Nenhum pedido" | FAIL — B-17 |
| ... | ... | ... | ... |
```

---

## Parte 2 — Bot (POST /webhook simulado OU revisão de conversa real)

### Pré-requisitos

- `EVOLUTION_WEBHOOK_SECRET` para HMAC-SHA256
- Endpoint `POST /webhook/whatsapp` (header `X-Evolution-Signature`)
- Conta de teste em `gestores`/`representantes`/`clientes_b2b` ou usar números mockados

### Cenários por persona

**Cliente** (5+ perguntas):
- "oi" — saudação básica → resposta amigável, sem erro
- "quero ver o catálogo" → lista de produtos do `commerce_products` (ou `produtos` se for fallback)
- "busca [nome de produto real]" → match por nome
- "busca [EAN completo, ex: 7898923148571]" → match via `query[-6:]` em `codigo_externo`
- "quero comprar [N] de [produto]" → fluxo de pedido inicia
- "confirma" → pedido confirmado, PDF gerado, gestor notificado

**Representante** (3+ perguntas):
- "quem são meus clientes?" → lista da carteira (filtra por `representante_id`)
- "fazer pedido para [nome de cliente da carteira]" → fluxo inicia
- "relatório de vendas do mês" → totais reais (não zerado)

**Gestor** (5+ perguntas — onde mais bugs aparecem por causa das tools EFOS):
- "lista de clientes inativos" → ≥ 1 resultado se `commerce_accounts_b2b` tem `situacao_cliente=2`
- "lista de clientes inativos na cidade de Itupeva" → resultados de cidade=ITUPEVA
- "quais os representantes do sistema?" → lista de `commerce_vendedores` (24 reps no caso JMB), não inferência de pedidos
- "relatório de vendas do representante [nome]" → fuzzy match + dados de `commerce_orders`
- "lista de pedidos pendentes" → busca em `pedidos` E `commerce_orders`

### Critério de PASS por cenário

Para cada pergunta enviada:
- Resposta NÃO contém: "nenhum cliente", "nenhum pedido", "não encontrei",
  "sem dados", "no momento não tenho" — quando o banco tem dados
- Resposta contém ao menos 1 valor real do banco (nome, número, valor)
- Sem erro 500 / sem mensagem técnica vazada
- Sem violação de feedback histórico (ex: "Não usar emojis" do feedback 20/04)

### Output esperado

`artifacts/pre_homolog_review_sprint_N.md` seção "Bot":

```markdown
| Persona | Pergunta | Resposta (excerpt) | Esperado | Status |
|---------|----------|--------------------|----------|--------|
| Gestor | "lista clientes inativos Itupeva" | "Nenhum inativo em Itupeva" | ≥ 1 cliente (banco tem 8) | FAIL — B-15 |
| Cliente | "EAN 7898923148571" | "Não encontrei produto" | produto 148571 | FAIL — B-13 |
| ... | ... | ... | ... | ... |
```

---

## Parte 3 — Verificação de invariantes históricos

Lê `docs/BUGS.md` (resolvidos) e `docs/feedbacks_history.md` se existir.
Para cada bug resolvido em sprint anterior, garantir que NÃO regrediu.

Para cada feedback histórico ativo do gestor (ex: "Não usar emojis"), verificar
no system prompt e em respostas reais.

---

## Quem executa este protocolo

- **Generator** executa antes de declarar sprint pronto, anexa o artefato
- **Evaluator** verifica que o artefato existe e tem PASS antes de aprovar
- **Lauzier** valida apenas se o protocolo passou — se algo escapar, é bug
  para o próximo sprint, não rejeição do atual

## O que NÃO é este protocolo

- Não substitui a homologação humana — é o gate antes dela
- Não substitui `pytest -m unit` — testes unitários cobrem lógica isolada
- Não substitui smoke gate de infra (deploy, migrations, health) — esses
  garantem pré-condições; este protocolo garante comportamento

---

## Lição que originou este protocolo (Sprint 9, 2026-04-28)

Sprint 9 foi declarado pronto para homologação com:
- ✅ pytest -m unit: 374 passed
- ✅ smoke gate: ALL OK (8/8 checks)
- ✅ Evaluator: APROVADO
- ✅ deploy + migrations + sync_efos: tudo OK

O usuário rejeitou em 30 segundos abrindo o dashboard, porque encontrou 8 bugs
que o pipeline não pegou:
- B-14 a B-21 — todos do mesmo padrão: queries em tabelas legadas vazias

A causa raiz não era ausência de testes — era ausência de **revisão exploratória
do produto como um humano usa**. Este protocolo formaliza essa revisão.
