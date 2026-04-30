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

## Parte 1 — Dashboard via Playwright/Chrome DevTools MCP (executável)

**Princípio:** cada cenário tem `click → fill → submit → assert URL → assert DB`.
**Sem submit, não conta.**

> **Lição v0.10.6 (2026-04-30):** a11y snapshot (`take_snapshot`) NÃO captura
> layout visual quebrado por CSS. Em v0.10.5 todos os 5 radios de `/dashboard/sync`
> estavam semanticamente OK no a11y tree mas visualmente despencados em coluna
> separada das labels (regra global `input { width: 100%; }` aplicava em radio).
> **Para cada rota com form criado ou alterado no sprint, adicionar `take_screenshot()`
> e revisar visualmente** — comparar com mock/template esperado. Layout quebrado
> = FAIL.

### Cenários por sprint

Para cada rota com POST handler **alterado ou criado no sprint**:

| Cenário | Pré | Ação MCP | Assert URL | Assert DB |
|---------|-----|----------|------------|-----------|
| Cliente novo | login | navigate /X/novo → fill perfil=Cliente, cliente=<EFOS>, telefone=5519... → submit | redirect 302/303 (não 400, não erro inline) | SELECT count(*) FROM target WHERE ... = 1 |
| (etc) | | | | |

Para rotas com listagem (GET) inalteradas, manter checklist atual de
COUNT(*) DB vs visível.

**Output:** `artifacts/pre_homolog_review_sprint_N.md` com tabela de
PASS/FAIL **por cenário**, screenshot anexado.

### Critério de PASS

Cada POST do sprint exercitado com payload realista, redirect 302/303 (ou 400
com mensagem amigável), DB confirma efeito esperado.

## Parte 2 — Bot via webhook simulado HMAC (executável)

**Princípio:** webhook real ao endpoint, multi-turn, log inspection.

Helper canônico: `scripts/sim_webhook.py <numero> "<texto>"` — assina HMAC
com `EVOLUTION_WEBHOOK_SECRET`, posta para `/webhook/whatsapp`.

### Cenários obrigatórios por persona (sprint conversacional)

**Cliente:** mensagem texto → produto buscado, áudio (se sprint mexeu) →
transcrito, EAN completo (B-13), conversa de 6 turnos (B-26).

**Rep:** "meus clientes", "fazer pedido para X", relatório.

**Gestor:** áudio (B-23/24), pedido em nome de cliente EFOS-only (B-28),
ranking (B-25), AUTORIZAR (D030), 6 turnos seguidos.

**Self_registered:** número desconhecido manda mensagem → criação contact +
notificação dual + AUTORIZAR + segunda mensagem roteada como cliente
(D030 fluxo completo).

### Critério de PASS

Para cada cenário:
- Webhook HTTP 200 (recebido)
- Log `agent_*_respondeu` ≥ 1 com `resposta_len > 50`
- **Zero linhas** `agent_*_erro`, `*_lookup_erro`, `historico_corrompido_recovery`
- DB tem efeito esperado (contact criado, pedido inserido, etc.)
- Langfuse trace mais recente: ≥ 1 generation com `usage.input_tokens > 0`
- (Para multi-turn) Conversação preservou contexto (LLM responde fazendo
  referência à mensagem anterior)

**Output:** `artifacts/sweep_bot_sprint_N.md` com tabela.

## Quem executa

- **Generator** ANTES de declarar pronto. Sprint não pode receber Evaluator final
  sem ambos `pre_homolog_review_sprint_N.md` (Parte 1) e `sweep_bot_sprint_N.md`
  (Parte 2) com PASS em **todos** os cenários do sprint.
- **Evaluator** verifica que ambos artefatos existem, têm PASS, e contêm
  evidência de POST/webhook real (não navegação solo). Pode pedir re-execução
  se cenário foi marcado PASS sem o submit/webhook visível.
- **Lauzier** valida apenas se o pipeline mecânico passou — se algo escapar,
  é bug do próximo sprint, não rejeição do atual.

---

## Parte 3 — Verificação de invariantes históricos

Lê `docs/BUGS.md` (resolvidos) e `docs/feedbacks_history.md` se existir.
Para cada bug resolvido em sprint anterior, garantir que NÃO regrediu.

Para cada feedback histórico ativo do gestor (ex: "Não usar emojis"), verificar
no system prompt e em respostas reais.

---

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
