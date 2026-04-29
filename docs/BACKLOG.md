# Backlog de Features

Features solicitadas ainda não implementadas, priorizadas pelo PO.

## Em análise para próximo sprint

| ID   | Descrição                                   | Origem | Impacto negócio                 | Esforço | Status   |
|------|---------------------------------------------|--------|---------------------------------|---------|----------|
| F-01 | Notificação ao gestor quando pedido é feito | Piloto | Alto — visibilidade operacional | Médio   | Sprint 7 |

## Backlog

| ID   | Descrição | Origem | Impacto negócio | Esforço |
|------|-----------|--------|-----------------|---------|
| F-02 | Aceitar áudio e imagem como input no WhatsApp (transcrever pedido por voz, buscar produto por imagem ou código de barras) | Piloto | Alto — reduz fricção operacional para clientes e reps | Alto |
| F-03 | Status e versão de entrega no feedback — campos `status` (aberto/em_andamento/resolvido) e `versao_entrega` (ex: v0.7.0) na tabela `feedbacks` + UI no painel do gestor para visualizar e atualizar | Piloto | Médio — rastreabilidade do ciclo feedback→entrega | Médio |
| F-04 | Modelagem cliente PJ × contato PF — separar `commerce_accounts_b2b` (pessoa jurídica) de `cliente_contatos` (1+N pessoas físicas com WhatsApp); importar `cl_contato`, `cl_telefone`, `cl_telefonecelular`, `cl_email` do EFOS | Homologação Sprint 9 | Alto — resolve B-27 estruturalmente e dá base para múltiplos compradores por cliente | Médio |
| F-05 | **AnalystAgent — meta-agente de observabilidade** — persona admin que consulta Langfuse e extrai inteligência operacional (custo, anomalias, qualidade). Diferencial de produto. Aprovado em ADR D031, alvo Sprint 11. | Investigação 29/04 | Alto — diferencial competitivo + reduz tempo de investigação de bugs/incidentes | Alto (3 sprints incrementais) |
| F-06 | **Painel de Divergências do Catálogo ERP** — repurpose do antigo /catalog/painel: mostrar produtos com dados inconsistentes vindos do ERP (preço fora do esperado, sem categoria, sem foto, EAN inválido). QA do dado ingerido pelo sync. | Investigação 29/04 | Médio — qualidade de dado do ERP afeta resposta do bot | Médio |

> **F-06 detalhe:** Considerar pós-Bling. Substitui o painel legado do Sprint 0
> (que era acoplado ao crawler+enricher) por uma view nova alinhada com D030.
> Tem sinergia com D031 (AnalystAgent) — divergências de catálogo são tipo de
> anomalia que o agente meta detectaria. Foco: ajudar gestor a corrigir dado
> no ERP (não cadastrar duplicado no app). Decisão se entra como tela própria
> ou como capability do AnalystAgent fica para discussão futura.

| F-07 | **Controle de frequência do sync EFOS (TEMPORÁRIO)** — UI admin para escolher preset (manual/diário/2x dia/4x dia/horário), pausar/retomar, rodar agora e ver próxima/última execução. Migra scheduling do launchd para APScheduler interno. | Investigação 29/04 | Alto operacional durante piloto — controle sem editar plist; serão deprecated quando Bling entrar (webhooks) | Médio |

> **F-07 detalhe (Sprint 10):**
>
> **Caráter:** TEMPORÁRIO. Substituído quando migrar para Bling (Sprint 11+),
> que tem webhooks event-driven em vez de polling. Não vale super-engenhar.
>
> **Migration nova:** `sync_schedule` (tenant_id, connector_kind, preset,
> cron_expression, enabled, last_triggered_at, next_run_at).
>
> **Presets confirmados (5, sem cron livre):**
> - `manual` — sem agendamento, só "Rodar agora"
> - `diario` — 1x/dia às 13:00 BRT (default atual)
> - `2x_dia` — 08:00 e 13:00
> - `4x_dia` — a cada 6h
> - `horario` — a cada hora
>
> **Permissão:** admin only (operador do app, persona ANALYST do D031).
> Gestor JMB **não** controla — risco de desligar sync por engano supera
> benefício. Visibilidade no AgentGestor: **não** (admin pergunta via dashboard
> ou pelo Analyst no Sprint 11+).
>
> **UI (`/dashboard/sync`, admin only):**
> - Radio buttons dos 5 presets
> - Toggle "Sync ativo"
> - Botão "Salvar" (persiste + reschedule no APScheduler em runtime)
> - Botão "Rodar agora" (dispara subprocess com Redis lock anti-overlap)
> - Próxima execução + última execução (status, rows, duração)
> - Histórico das últimas 10 execuções de `sync_runs`
>
> **Implementação técnica:**
> - **APScheduler interno** substitui `launchd`. Já está usado no projeto
>   (D019, scheduler do crawler — também sai com a deprecação).
> - **Redis lock** `sync:efos:{tenant}:running` (TTL 30min) para evitar
>   overlap quando "Rodar agora" colide com schedule.
> - **Background task isolada** — `asyncio.create_task` com try/except interno
>   para que sync explodindo não derrube o app.
> - **Reschedule em runtime** — UI atualiza tabela + chama `scheduler.reschedule_job`
>   sem restart.
>
> **Sequência segura de migração launchd → APScheduler:**
> 1. Implementar APScheduler interno + tabela `sync_schedule` populada com
>    default `diario 13:00`
> 2. Deploy em staging — confirmar que job aparece no APScheduler list
> 3. Validar 1 execução real do agendamento interno (não manual)
> 4. **Só então** `launchctl unload ~/Library/LaunchAgents/com.jmb.efos-sync.plist`
> 5. Remover `scripts/launchd/com.jmb.efos-sync.plist` do repo
>
> Durante a transição, deixar plist do launchd com `RunAtLoad=false` e
> `Disabled=true` antes de remover — evita race condition com 2 schedulers.
>
> **Sinergia com D031:** AnalystAgent (Sprint 11+) ganha tool `sync_status_efos`
> reutilizando a mesma tabela e UI: admin pergunta "quando foi último sync?
> qual a próxima?" e o Analyst responde via WhatsApp.
>
> **Quando deprecar (não definido):** quando Bling estiver estável com webhooks
> em produção, sync polling de EFOS sai e essa UI vai junto. Provável Sprint
> 12-14. Por enquanto, é necessário enquanto JMB depender de EFOS.

> **F-05 detalhe:** Visto em ADR [D031](../docs/design-docs/D031-analyst-agent-observability.md).
>
> **MVP (Sprint 11):** 3 tools (cost_breakdown, top_anomalies,
> conversation_summary) + 4 detectors (loop, cost_outlier, recovery_destrutivo,
> tool_failure) + persona Analyst exclusiva admin via WhatsApp + endpoint
> `/dashboard/insights`.
>
> **Pré-requisito:** B-30 corrigido no Sprint 10 (sem generations no Langfuse,
> não há o que analisar).
>
> **Decisões PO confirmadas:**
> - Persona separada (não integra ao AgentGestor)
> - Single admin/operador no MVP; preparar arch para futuro Manager por tenant
> - Dados internos (sem PII redaction no MVP)
> - Sprint 11 alvo
>
> **Por que é diferencial:** poucos sistemas SaaS de agentes têm
> meta-observabilidade conversacional. Reduz drasticamente tempo de investigação
> (B-26, B-28, B-30 levaram horas de análise manual nesta semana — auto-detectados
> seriam minutos).

> **F-04 detalhe (investigação 29/04):**
>
> **Como o EFOS modela cliente vs contato:**
>
> EFOS usa **modelo embutido**: 1 contato por cliente, dentro da própria
> `tb_clientes`. Não há tabela `tb_contatos` ou `tb_clientescontato` separada.
>
> Campos relevantes em `tb_clientes`:
>
> | Campo | Significado | Qualidade (1030 ativos) |
> |-------|-------------|------------------------|
> | `cl_nome` | Razão social da PJ | 100% preenchido |
> | `cl_nomefantasia` | Nome fantasia | ~100% |
> | `cl_cnpjcpfrg` | CNPJ/CPF | 100% |
> | `cl_contato` | **Nome do contato (pessoa física)** | **22% preenchido (223 reais)** |
> | `cl_telefone` | Telefone fixo do estabelecimento | 93% (961) |
> | `cl_telefonecelular` | Celular do contato/estabelecimento | 92% (953) |
> | `cl_email`, `cl_email1` | Emails | 95% (981) |
>
> Exemplos reais de `cl_contato`: "FABIO REP", "VITOR", "ROSANA", "HUGO",
> "CLEIDE" — geralmente primeiro nome, às vezes com função anexa.
>
> **Limitações do modelo EFOS:**
> - 1 contato por cliente (não suporta múltiplos compradores)
> - 78% dos clientes ativos sem `cl_contato` preenchido — qualidade variável
> - Telefones tendem a ser "do estabelecimento", não "do contato"
>
> **Decisão de modelagem para o nosso write model:**
>
> Separar em duas estruturas:
>
> 1. **`commerce_accounts_b2b`** (read model EFOS, já existe) — PJ
>    - Adicionar campos perdidos no Sprint 8: `contato_padrao`, `telefone`,
>      `telefone_celular`, `email`, `nome_fantasia`, `dataultimacompra`
>    - Atualizar `normalize_accounts_b2b` em
>      `output/src/integrations/connectors/efos_backup/normalize.py`
>    - Migration nova para adicionar colunas ao schema
>
> 2. **`cliente_contatos`** (write model novo) — PF, 1:N por cliente
>    - Estrutura: `id, tenant_id, cliente_external_id, nome, telefone_whatsapp,
>      email, eh_padrao, ativo, criado_em`
>    - `cliente_external_id` aponta para `commerce_accounts_b2b.external_id`
>      (cliente do EFOS) — não pra `clientes_b2b.id` (cliente "manual")
>    - Bot identifica persona "cliente" via lookup
>      `cliente_contatos.telefone_whatsapp` → `cliente_external_id` →
>      `commerce_accounts_b2b`
>    - Quando gestor cadastra contato via dashboard, INSERT em
>      `cliente_contatos` referenciando `commerce_accounts_b2b.external_id`
>      do dropdown
>
> **O que isso resolve:**
> - B-27 (showstopper) estruturalmente — não precisa mais clonar EFOS para
>   `clientes_b2b`; INSERT em `cliente_contatos` é o caminho correto
> - 1 cliente PJ pode ter múltiplos compradores (caso comum em supermercados:
>   responsável compras, gerente, dono)
> - `cl_contato` do EFOS vira sugestão no dropdown ao adicionar contato novo,
>   mas não é o telefone do WhatsApp (esse vem do gestor cadastrando)
>
> **O que NÃO resolve (escopo separado):**
> - Migração da tabela `clientes_b2b` legada (write model atual). Decidir:
>   deprecar `clientes_b2b` em favor de `commerce_accounts_b2b` +
>   `cliente_contatos`, OU manter `clientes_b2b` como cache/cópia local de
>   commerce com flag de origem
>
> **Esforço estimado:** Médio. Migration nova + atualizar normalize_accounts_b2b
> + nova tabela cliente_contatos + atualizar agents/repo.py para identificação
> via cliente_contatos + atualizar dashboard /contatos/novo para inserir lá.

<!-- Populado via sessão de triage ou PO agent -->
