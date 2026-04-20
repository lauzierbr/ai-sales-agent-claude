# Retrospectiva Sprint 4 — Gestor/Admin (AgentGestor + Dashboard Web)

**Data:** 2026-04-20
**Participantes:** Lauzier + Claude
**Sprint:** 4 (branch `claude/nice-bassi-395798`, tag `v0.5.0`)

---

## O que foi bem

- **Três perfis WhatsApp funcionais end-to-end** — Cliente, Rep e Gestor operam de forma isolada e correta; IdentityRouter com prioridade `gestores → representantes → clientes_b2b` validado em produção
- **Dashboard web entregue no mesmo sprint (DP-01)** — Jinja2 + htmx + CSS puro, sem build step; padrão consistente com o painel de catálogo do Sprint 0
- **DP-02 e DP-03 validados** — Perfil cumulativo gestor/rep e herança de `representante_id` no pedido funcionaram sem bug em produção
- **Auto-recovery de Redis** — Padrão implementado nos 3 agentes; detecção de 400 com `tool_use_id` / `tool_result` limpa o histórico e retenta automaticamente
- **Typing indicator UX resolvido** — Iteração rápida (4 versões em uma sessão) chegou na solução correta: fire-and-forget start + stop explícito só em falha
- **229 testes unitários passando** — Cobertura expandida com G01–G15, IR-G1–IR-G4, A_MULTITURN, A_TOOL_COVERAGE

---

## O que poderia ter sido melhor

### P1 — Capacidades anunciadas sem ferramentas reais
**O que aconteceu:** O model começou a prometer "posso listar pedidos" e "posso aprovar" antes de as ferramentas existirem, gerando respostas incoerentes em produção.

**Por que escapou:** O Evaluator não tinha critério `A_TOOL_COVERAGE` obrigatório até esta sprint. O QA r1 aprovou sem verificar cobertura de ferramentas vs. system prompt.

**Regra criada:** `A_TOOL_COVERAGE` é critério mandatory em todo sprint com agente conversacional. Adicionado em `prompts/evaluator.md`.

---

### P2 — Parâmetro `dias` hardcoded no SQL
**O que aconteceu:** `listar_por_tenant_status` usava `NOW() - INTERVAL '30 days'` fixo no SQL. Quando o usuário pediu "últimos 60 dias", o bot ignorou silenciosamente.

**Por que escapou:** O gotcha do projeto (Python timedelta > SQL INTERVAL) estava documentado nos gotchas do spec mas não foi aplicado a este método na implementação inicial.

**Regra criada:** Qualquer parâmetro de período em repo deve receber `dias: int` e usar `datetime.now(timezone.utc) - timedelta(days=dias)`. Verificação adicionada ao checklist do Evaluator.

---

### P3 — Redis history corruption descoberta em produção
**O que aconteceu:** Histórico corrompido com `tool_result` orphan causava 400 em toda mensagem subsequente até o Redis expirar (24h). Descoberto apenas quando usuário reportou bot não respondendo.

**Por que escapou:** Cenário de falha parcial (tool_use enviado mas resposta não salva) não estava coberto em testes. O erro 400 era logado como `agent_resposta_erro` genérico sem diagnóstico.

**Correção:** Auto-recovery nos 3 agentes + log específico `agent_*_historico_corrompido_recovery`.

---

### P4 — Typing indicator precisou de 4 iterações
**O que aconteceu:** Loop → race condition → `send_typing_stop` no finally → "voltou a mostrar digitando" → só on-except. Total: 4 tentativas para chegar na solução correta.

**Por que aconteceu:** A Evolution API tem comportamento não-documentado: `/chat/sendPresence` bloqueia por `delay` ms antes de responder (ReadTimeout de 5s), e `presence: paused` mostrava brevemente como "digitando" no WhatsApp.

**Lição:** Para integrações de API não-documentadas, testar o comportamento real antes de implementar UX em cima.

---

### P5 — Anthropic API 529 sem retry
**O que aconteceu:** API sobrecarregada em dois momentos durante a homologação; bot não respondeu. Nenhum retry implementado.

**Ação:** TD-05 aberto no tech-debt-tracker: retry com exponential backoff para erros 529/529 da Anthropic API. Sprint 5 ou hotfix de alta prioridade.

---

## O que fazemos de agora em diante

| # | Regra | Onde está documentado |
|---|-------|-----------------------|
| R1 | `A_TOOL_COVERAGE` obrigatório: toda capacidade no system prompt precisa de tool | `prompts/evaluator.md` — lição aprendida Sprint 4 |
| R2 | Parâmetros de período: sempre `dias: int` + Python `timedelta`, nunca SQL INTERVAL | Gotchas do spec + checklist Evaluator |
| R3 | Após deploy, testar explicitamente o caminho de erro (tool fail, API down) | Checklist de homologação |
| R4 | Para APIs não-documentadas: testar comportamento raw antes de construir UX | Convenção de desenvolvimento |
| R5 | TD-05: retry Anthropic 529 com backoff | `tech-debt-tracker.md` |

---

## Métricas do sprint

| Métrica | Valor |
|---------|-------|
| Testes unitários entregues | 229 (100% pass) |
| Bugs encontrados na homologação | 8 (B1–B8) |
| Hotfixes pós-QA | 8 commits |
| Perfis WhatsApp operacionais | 3 (Cliente, Rep, Gestor) |
| Páginas de dashboard entregues | 8 (home, pedidos, conversas, clientes, reps, preços, config, login) |
| Ferramentas novas nos agentes | 5 (listar×3, aprovar×2) |
| Iterações typing indicator | 4 |
