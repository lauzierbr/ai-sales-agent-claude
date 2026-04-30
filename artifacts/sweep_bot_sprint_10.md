# Sweep do bot — Sprint 10 (v0.10.2)

**Data:** 2026-04-30
**Staging:** http://100.113.28.85:8000
**Método:** webhook simulado HMAC-SHA256 via `/tmp/sim_webhook.py`
**Persona usada:** gestor (5519992066177 — Lauzier). Cliente B2B real não
disponível (tabelas `clientes_b2b` e `contacts` vazias para tenant `jmb`).

## Resumo

| Cenário                                    | Resultado | Bug |
|--------------------------------------------|-----------|-----|
| H10 — busca semântica "shampoo"            | PASS      | —   |
| H12 — ranking + ano default                | PASS      | —   |
| H6 — self_registered (criar contact)       | FAIL      | **B-S10-G** SQL syntax error |
| H7 — welcome message ao desconhecido       | FAIL      | **B-S10-H** kwargs incorretos em `send_whatsapp_message` |
| H3 — histórico longo (6 turnos)            | PASS      | —   |
| H11 — Langfuse + usage tokens              | PASS      | —   |
| (extra) GMV do mês                         | FAIL      | **B-S10-I** mês reportado errado |
| (extra) IdentityRouter ignora `contacts.authorized=true` | OBSERVAÇÃO | **B-S10-J** gap de roteamento |

Cenários PASS confirmam que H1 (áudio), H4 (pedido) e H10 (semântica)
seguem operacionais. Bugs detectados são todos no caminho **desconhecido →
contacts** introduzido pelo D030 e em uma defaulteação de mês.

---

## H10 — busca semântica pós-drop produtos legacy — PASS

- Mensagem: `quero ver shampoo`
- Tool executada: `_buscar_produtos` via `busca_semantica` (log
  `busca_semantica_executada query=shampoo resultados=5 tenant_id=jmb`)
- Resposta enviada (`mensagem_enviada` em 8s) listando 5 SKUs reais
  (SHAMPOO 250 ML SONIC R$ 12,60; SHAMPOO RUSTY ROSE; SHAMPOO ANTICASPA…)
- Conclusão: embeddings em `commerce_products` operam normalmente após o
  drop de `produtos`.

## H12 — ranking + ano default — PASS

Sequência:

1. `relatório de vendas do representante Rondinele de março/26`
   → 1 tool call (`fuzzy_match_vendedor` → `relatorio_vendas_representante_efos`)
   → resposta `*Relatorio de Vendas — Rondinele | Marco/2026*` (R$ 32.221,22).

2. `qual foi o melhor vendedor de março?`
   → **1** tool call (`ranking_vendedores_efos` com `ano=2026, mes=3, top_n=1`)
   → resposta `*Melhor Vendedor — Marco/2026*` (RONALDO PINTO DE MORAIS R$ 43.578,26).

Trace Langfuse `2e9b2f70…` mostra explicitamente o assistant gerando texto
"(Mantendo março/2026 do contexto anterior)" antes da tool, confirmando
que o LLM respeitou o contexto temporal e não disparou ranking serial. Não
houve loop de 24 chamadas.

## H6/H7 — self_registered — FAIL (2 bugs críticos)

Mensagem: `Olá, sou da Drogaria Calderari, queria fazer um pedido` de
`5519999000999@s.whatsapp.net` (número novo).

### B-S10-G — `ContactRepo.create_self_registered` quebra com erro SQL

**Observado:** `webhook_recebido persona=desconhecido` é registrado, mas o
INSERT no `contacts` nunca acontece. Após o sweep, `SELECT * FROM contacts
WHERE channels::text LIKE '%5519999000999%'` retorna 0 linhas.

**Esperado:** linha em `contacts` com `origin='self_registered'`,
`authorized=false`.

**Log relevante (08:59:46):**

```
2026-04-30 08:59:46 [info     ] webhook_recebido               from_number_hash=598e4e69... persona=desconhecido tenant_id=jmb
2026-04-30 08:59:46 [warning  ] contact_self_registered_erro   error='(sqlalchemy...PostgresSyntaxError): syntax error at or near ":"
[SQL:
    SELECT id, tenant_id, account_external_id, nome, papel,
           authorized, channels, origin,
           last_active_at, criado_em, authorized_by_gestor_id
    FROM contacts
    WHERE tenant_id = $1
      AND channels @> :channel_filter::jsonb
]
[parameters: ('jmb',)]'
```

**Causa-raiz hipótese:** SQL textual mistura placeholders `$1` (asyncpg
posicional) com `:channel_filter` (SQLAlchemy named) na mesma query — o
asyncpg recebe `$1` mas o `:channel_filter` chega ao Postgres literal e
quebra. Provavelmente em `output/src/agents/repo.py`, método de pesquisa
de contato por canal usado dentro de `create_self_registered` (idempotência).
**O mesmo pattern aparece em outro arquivo**: `dashboard_contatos_novo_erro`
(linhas 08:50:11 e 08:51:07 do `app.log`) com SQL idêntico em
`INSERT INTO contacts ... VALUES ($1, $2, ..., :channels::jsonb, ...)` —
sugere repo compartilhado com o mesmo bug. Fix esperado: padronizar para
`:channels` em toda a query (e usar `text(...).bindparams()`) ou trocar
para `$N`.

### B-S10-H — `send_whatsapp_message` chamado com kwargs errados

**Observado:** mesmo após falhar o INSERT, o fluxo seguia para enviar a
mensagem de boas-vindas ao desconhecido — mas explodiu:

```
2026-04-30 08:59:48 [error    ] agent_resposta_erro            error="send_whatsapp_message() got an unexpected keyword argument 'telefone'" persona=desconhecido tenant_id=jmb
```

**Esperado:** mensagem "Ola! Sua mensagem foi recebida. Vou avisar o
gestor para te autorizar. Aguarde!" enviada ao remetente desconhecido.
Nada chegou.

**Causa-raiz:** assinatura de `send_whatsapp_message` (output/src/agents/service.py:382)
é `(instancia_id, numero, texto)` mas há **6 chamadas** em
`output/src/agents/ui.py` que usam `telefone=` e `mensagem=`:

- linha 330 — fallback áudio sem transcrição
- linha 341 — fallback áudio com exceção
- linha 350 — fallback áudio sem conteúdo
- linha 444 — confirmação `AUTORIZAR <numero>` sucesso
- linha 456 — `AUTORIZAR` falha (número não encontrado)
- linha 564 — welcome do self_registered (este caminho)

Significa que **TODOS os caminhos de "saída direta sem LLM"** quebraram.
H1 (áudio) só está dando "PASS" porque o caso atual cai sempre na
transcrição ok; basta um áudio inaudível para reproduzir o B-S10-H. Os
caminhos AUTORIZAR sucesso/erro também estão quebrados — o gestor não
recebe confirmação após autorizar contatos via WhatsApp (mas o UPDATE
no banco em si funciona, é só o feedback que falha).

**Cenário H7 (`AUTORIZAR +5519999000999`) não foi executado**: como
B-S10-G impede a criação do contato, não havia o que autorizar. Mesmo
que se autorizasse, B-S10-H quebraria a confirmação ao gestor.

## H3 — histórico longo — PASS

6 turnos `clientes inativos → clientes inativos em Itupeva → relatório
Rondinele março/26 → pedidos pendentes → meus representantes → GMV do
mês`. Cada um disparou `n_tools=1` e respondeu em ~3s.

- `grep -c historico_corrompido_recovery /logs/app.log` → **0** ocorrências
- Redis `hist:gestor:jmb:5519992066177` (string JSON, não LIST):
  `STRLEN=6708`, `entries=20` (10 user + 10 assistant entries totais
  considerando o histórico anterior somado aos 6 novos turnos), todas as
  roles alternam corretamente `user/assistant/user/assistant…`.
- Conteúdo de cada resposta consistente com o pedido (clientes inativos
  com 3 nomes reais, Itupeva = 0, Rondinele R$ 32.221,22, etc.)

> **Observação operacional:** o spec falava em `LLEN`, mas o histórico
> está armazenado como STRING JSON serializado, não LIST Redis. A
> comparação correta é `entries` no JSON parseado.

## H11 — Langfuse + usage tokens — PASS

Trace mais recente (`2e9b2f70-c58e-41c4-9a84-0025456c112f`,
`anthropic_gestor`, 2026-04-30T12:01:51Z): observation
`729ef43c-9687-48de-a761-e2b91d0dd693` tipo `GENERATION`, model
`claude-sonnet-4-6`, com:

```
promptTokens: 6638
completionTokens: 78
totalTokens: 6716
```

Token tracking funcionando. **Sub-issue:** `totalCost=0` em todos os
traces — provavelmente custo não está configurado no projeto Langfuse
(falta cadastro de pricing para `claude-sonnet-4-6`). Isso é configuração
de Langfuse, não bug do app.

## (extra) B-S10-I — GMV reporta mês errado

**Observado:** turno 6 do H3, mensagem `qual o GMV do mês?` em 30/abr/2026
às 09:01 BRT (12:01 UTC). Resposta:

```
*GMV — Mes Atual (Maio/2026)*
• Total GMV: R$ 0,00
• Pedidos: 0
• Ticket medio: R$ 0,00
Nenhum pedido registrado no mes ate o momento.
```

**Esperado:** GMV de **Abril/2026**, mês corrente.

**Hipótese:** off-by-one no cálculo do mês corrente. Possíveis causas:

- `datetime.utcnow()` + `+ relativedelta(months=1)` em algum lugar.
- Confusão entre "mês atual" e "próximo mês" na tool de GMV.
- TZ: 30/abr 12:00 UTC ainda é abril, então não é o problema clássico
  de "fim de mês cruzando UTC".

Este bug torna o KPI de GMV inutilizável durante o piloto — gestor sempre
verá "R$ 0,00" porque consulta sempre um mês no futuro.

## (extra) B-S10-J — IdentityRouter ignora `contacts.authorized=true`

**Observado:** lendo `output/src/agents/service.py:46-115` e cruzando
com o D030 (contacts como segunda fonte de autorização):

- IdentityRouter resolve persona consultando apenas `gestores`,
  `representantes`, `clientes_b2b` — **não consulta `contacts`**.
- Logo, mesmo que um contato seja criado via self_registered e
  autorizado pelo gestor (`AUTORIZAR …`), o próximo webhook desse número
  ainda cai em `Persona.DESCONHECIDO`, gerando novo `create_self_registered`
  (que falha com B-S10-G de qualquer forma).

**Hipótese:** D030 esperava que `contacts.authorized=true` mapeasse para
`Persona.CLIENTE_B2B`, mas a integração no router não foi feita. Sem
essa rota, o ciclo "AUTORIZAR → cliente atendido" nunca fecha.

Severidade: alta — feature de auto-onboarding (objetivo do Sprint 10
F-09 / D030) está totalmente quebrada na cadeia G + H + J.

---

## Recomendação consolidada para hotfix

Ordem de prioridade:

1. **B-S10-H** (kwargs `send_whatsapp_message`): trivial, 6 chamadas, 5
   minutos de fix. Sem isso nenhum dos outros caminhos finaliza.
2. **B-S10-G** (SQL repo contacts): identificar o text() problemático e
   uniformizar placeholders. Verificar se o mesmo repo é usado pelo
   dashboard (parece sim).
3. **B-S10-J** (IdentityRouter ignora contacts): adicionar lookup de
   `contacts WHERE authorized=true` antes do fallback DESCONHECIDO. Sem
   isso o ciclo de autorização não fecha.
4. **B-S10-I** (GMV mês errado): investigar tool de GMV em
   `agents/runtime/agent_gestor.py` (provavelmente em
   `consultar_top_produtos` ou helper de período).

Sweep concluída sem mudanças no banco. Nenhum contato real foi alterado.
Não houve sync EFOS executado.
