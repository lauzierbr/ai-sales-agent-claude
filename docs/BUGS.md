# Bug Tracker

## Abertos

| ID   | Descrição                                           | Severidade | Sprint origem    | Data abertura |
|------|-----------------------------------------------------|------------|------------------|---------------|
| B-01 | Gestor não recebe notificação quando pedido é feito | Alta       | Sprint 6 homolog | 2026-04-21    |
| B-10 | Pedido criado sem representante mesmo quando cliente tem rep. vinculado | Alta | Piloto | 2026-04-24 |
| B-11 | Agente perde contexto conversacional mid-session após troca de persona do número | Alta | Piloto | 2026-04-24 |
| B-12 | Instrumentação Langfuse incompleta — output null, zero tokens/custo, sem generations nem sessions | Média | Piloto | 2026-04-24 |
| B-13 | Busca de produto por EAN falha — bot não mapeia últimos 6 dígitos do EAN para código interno JMB | Alta | Piloto | 2026-04-27 |
| B-23 | Áudio WhatsApp (H-20/F-02a) não funciona — Whisper rejeita 400 "Invalid file format" porque audioMessage.url retorna conteúdo criptografado E2E | Alta | Homologação Sprint 9 | 2026-04-29 |
| B-24 | Bot nega capacidade de áudio em vez de admitir falha temporária — fallback injeta texto que confunde o LLM + system prompt não menciona a capacidade | Alta | Homologação Sprint 9 | 2026-04-29 |

> **B-24 detalhe:** Independente do B-23 (que é técnico). Mesmo se Whisper
> funcionasse, há dois problemas de UX no comportamento do agente:
>
> **B-24a — Fallback de erro confunde o LLM**
> Em `output/src/agents/ui.py:314-330`, quando a transcrição falha, o código
> faz `mensagem.model_copy(update={"texto": "Recebi seu áudio, mas houve uma
> falha na transcrição..."})` — esse texto vai para o histórico Redis e o
> agente Claude o processa como se fosse uma mensagem do usuário. Resultado:
> Claude reformula com base no system prompt ("Sou um assistente de texto e
> não envio áudios") em vez de propagar a mensagem amigável.
>
> **B-24b — System prompt não menciona capacidade de áudio**
> Os 3 system prompts em `output/src/agents/config.py` não mencionam que o
> agente aceita áudio. Quando o usuário pergunta "Você consegue ouvir áudio?"
> o LLM responde "Trabalho apenas com texto" — porque é o que ele "sabe"
> pelo prompt. Confirmado em conversa 28/04 19:05.
>
> **Correção:**
>
> 1. Em ui.py: quando transcrição falha, enviar resposta DIRETAMENTE via
>    `send_whatsapp_message()` (sem passar pelo agente) e dar `return` — não
>    deixar o LLM processar uma mensagem fake. Padrão similar ao que já é
>    usado em outros pontos do fluxo (ex: rate limit).
>
> 2. Em config.py: adicionar bloco "## Capacidades de mensagem" nos 3 system
>    prompts:
>    ```
>    Você aceita mensagens de texto e áudio.
>    Áudios aparecem prefixados com "🎤 Ouvi: <transcrição>" — trate o
>    conteúdo após "Ouvi:" como a mensagem real do usuário.
>    Se perguntarem se você aceita áudio, confirme.
>    ```
>
> Sub-bugs B-24a e B-24b devem ser corrigidos juntos para evitar regressão.

> **B-23 detalhe:** Implementação Sprint 9 baixa o áudio via `audioMessage.url`
> (servidor mmg.whatsapp.net) e envia para Whisper. Conteúdo é criptografado
> end-to-end pelo WhatsApp — não é OGG válido. Whisper rejeita com:
> `400 Invalid file format. Supported formats: ['flac','m4a','mp3','mp4','mpeg','mpga','oga','ogg','wav','webm']`
>
> Log confirma duas tentativas em 28/04 19:04 e 19:05, ambas com erro 400.
> O bot então cai no fallback "Recebi seu áudio, mas houve uma falha na
> transcrição" — porém respondeu de forma diferente da esperada porque o
> agente cliente reformulou a mensagem como se fosse texto puro.
>
> **Correção:** baixar áudio descriptografado via endpoint da Evolution API
> ao invés da URL do WhatsApp:
>
>   ```python
>   # POST {EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}
>   # body: {"message": {"key": {...}}}
>   # headers: {"apikey": EVOLUTION_API_KEY}
>   # retorna: {"base64": "<áudio descriptografado>", "mimetype": "audio/ogg; codecs=opus"}
>   ```
>
> Alternativa: configurar `WEBHOOK_BASE64=true` no servidor Evolution API
> (env var) — webhook passaria a incluir `audioMessage.base64` já
> descriptografado. Solução via Evolution API endpoint é mais defensiva
> (não depende de config externa).
>
> **Arquivos a modificar:**
> - `output/src/agents/ui.py:285-312` — substituir tentativa de URL+base64
>   por chamada ao endpoint da Evolution API
> - Pode reaproveitar `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` já no Infisical

> **B-22 detalhe:** Feedback registrado em 20/04 instruiu "Não usar emojis nas respostas". 
> O bot continua usando 😊, 👇, 🏆, 👋 nas respostas (visto em conversa do gestor 27/04).
> O system prompt dos 3 agentes precisa explicitamente proibir emojis. Pode estar
> em `output/src/agents/config.py` (system_prompt_template). Considerar também: usar
> feedbacks da tabela `feedbacks` como instruções vivas dos agentes (system prompt
> dinâmico) — escopo maior, talvez Sprint futuro.

> **B-21 detalhe:** Rota `/dashboard/representantes` existe mas não está na navegação
> principal. Mesma raiz dos B-14/B-17/B-19 — query em `pedidos` vazio. Resolver junto
> ao hotfix de migração exaustiva.

> **B-20 detalhe:** `/dashboard/top-produtos` agrega vendas de `itens_pedido` (vazio
> após reset). Migrar para `commerce_sales_history` (27740 rows) ou
> `commerce_order_items`. Lookup de nome do produto pode usar `commerce_products`.

> **B-19 detalhe:** KPIs do home (GMV hoje, Pedidos hoje, Ticket médio) consultam
> `pedidos` filtrando por DATE(criado_em) = hoje. Tabela vazia → todos zerados.
> Decisão: KPIs devem refletir pedidos do bot (que estarão vazios em staging com
> ENVIRONMENT=staging filtrado por ficticio=FALSE) OU agregar `commerce_orders`?
> Provavelmente o segundo, com label "Histórico EFOS — hoje" para deixar claro que
> não são pedidos do bot.

> **B-18 detalhe:** Bloco "Última sincronização EFOS" no home mostra "Nunca sincronizado"
> apesar do banco ter 4 sync_runs (1 success em 27/04 17:42 com 61891 rows publicadas).
> Endpoint `/dashboard/sync-status` (criado no Sprint 9 E2) provavelmente tem bug:
> não filtra por status='success', ou não considera o registro mais recente, ou
> está com bug de tenant_id no JWT vs DB. Investigar `dashboard/ui.py` rota
> sync-status e `integrations/repo.py:SyncRunRepo.get_last_sync_run`.

> **B-17 detalhe:** Mesma raiz de B-14/B-15/B-16. Rota `/dashboard/pedidos` consulta
> tabela `pedidos` (0 linhas pós-reset). 2592 pedidos reais estão em `commerce_orders`.
> Generator deve, no hotfix, fazer grep exaustivo
> `grep -rn "FROM pedidos\|FROM clientes_b2b\|JOIN pedidos\|JOIN clientes_b2b" output/src/ --include="*.py"`
> e migrar cada hit — sem cherry-pick. Confirmar checklist em
> `docs/exec-plans/active/sprint-9-hotfix.md`.

> **B-16 detalhe:** Dashboard `/dashboard/clientes` consulta tabela `clientes_b2b` que está com
> 0 linhas após reset do banco no deploy Sprint 8/9. Os 614 clientes reais estão em
> `commerce_accounts_b2b`. Mesma raiz do B-14 e B-15 — tabelas legadas zeradas, dados migrados
> para `commerce_*`. Corrigir: endpoint do dashboard deve consultar `commerce_accounts_b2b`
> (com fallback ou substituição definitiva de `clientes_b2b`).

> **B-15 detalhe:** `commerce_vendedores` tem 24 representantes reais (EFOS) mas o AgentGestor
> não tem tools que a consultam diretamente. Dois sintomas: (1) listagem de clientes exibe
> "Sem representante" — query não faz LEFT JOIN com `commerce_vendedores` via
> `commerce_accounts_b2b.vendedor_codigo = commerce_vendedores.ve_codigo`
> (commerce/repo.py:98–119); (2) ao pedir "Liste os representantes", agente tenta inferir
> via `commerce_orders` (vazia — B-14) e responde que não há dados. Corrigir:
> (a) adicionar JOIN na query de clientes; (b) criar tool `listar_representantes` que
> consulte `commerce_vendedores` diretamente.
> Arquivos: `output/src/commerce/repo.py:98`, `output/src/agents/runtime/agent_gestor.py`.

> **B-14 detalhe:** Dois problemas: (1) tabela `pedidos` está com 0 linhas para tenant jmb no staging
> (provável reset de banco no deploy Sprint 8/9 — 2592 pedidos reais estão em `commerce_orders`,
> importados pelo sync EFOS em 2026-04-27T20:40). (2) `listar_pedidos_por_status`
> (agent_gestor.py:622) só consulta `pedidos` via `OrderRepo.listar_por_tenant_status()`
> (orders/repo.py:230) — não inclui `commerce_orders`. Corrigir: (a) verificar se houve perda
> de dados no deploy; (b) expandir a tool para incluir registros de `commerce_orders`.

> **B-13 detalhe:** EAN JMB segue padrão: últimos 6 dígitos = `codigo_externo` interno
> (ex: EAN 7898923148571 → codigo_externo "148571"). A busca atual faz match exato em
> `codigo_externo` — se o usuário digitar o EAN completo, retorna vazio. Confirmado no DB:
> produtos 148571 (Escova Quadrada 571) e 148755 (Escova Redonda 755) existem mas não são
> encontrados pelo EAN. Corrigir: em `_buscar_produtos()` (agent_cliente.py:633), se query
> numérica tiver mais de 6 dígitos, tentar também `query[-6:]` como `codigo_externo`.
> Mesmo padrão deve ser aplicado em AgentRep e AgentGestor.

> **B-12 detalhe:** Três gaps na instrumentação Langfuse dos três agentes:
> 1. `output=null`: `resposta_final` nunca repassada via `_lf_ctx.update_current_observation(output=...)`.
>    Arquivos: agent_gestor.py:489, agent_rep.py:429, agent_cliente.py:384.
> 2. Zero tokens/custo/generations: `AsyncAnthropic()` instanciado sem wrapper Langfuse em
>    agent_gestor.py:920, agent_rep.py:464, agent_cliente.py:402. Calls a `client.messages.create()`
>    são invisíveis ao Langfuse.
> 3. Sem sessions: `session_id` nunca definido no trace (agent_gestor.py:368, agent_rep.py:291,
>    agent_cliente.py:240) — impossível agrupar conversas por usuário/tenant.
> Corrigir: wrappear AsyncAnthropic com instrumentação Langfuse + setar session_id usando
> `conversa.id` (já disponível em todos os agentes) + chamar `update_current_observation(output=...)`.

> **B-11 detalhe:** Ao trocar a persona de um número (ex: cliente → gestor), o Redis não invalida
> a chave da persona anterior (`conv:{tenant_id}:{numero}`). Se alguma mensagem for roteada para
> AgentRep/AgentCliente durante ou após a transição, o agente carrega histórico stale da persona
> antiga. Adicionalmente, AgentRep e AgentCliente compartilham a mesma chave Redis — ao contrário
> do AgentGestor que usa `hist:gestor:{tenant_id}:{numero}`. Corrigir: ao alterar persona de um
> contato, invalidar todas as chaves Redis associadas ao número.
> Arquivos: `output/src/agents/runtime/agent_rep.py:481`, `agent_cliente.py:419`.

> **B-10 detalhe:** `get_by_telefone()` não faz SELECT em `representante_id`
> ([output/src/agents/repo.py:109](../output/src/agents/repo.py)) e `ui.py:297` passa
> `representante_id=None` hardcoded ao chamar `agent_cliente.responder()`. Corrigir: incluir
> `representante_id` no SELECT e propagar o campo do `ClienteB2B` para o input do pedido.

> **B-01 detalhe:** `tenant.whatsapp_number` é None — precisa buscar todos os gestores
> ativos via `GestorRepo` e notificar pelo campo `telefone`. Afeta AgentCliente e AgentRep.
> Rastreado também como TD-08.

## Resolvidos

| ID   | Descrição                                                     | Sprint fix    | Data       |
|------|---------------------------------------------------------------|---------------|------------|
| B-02 | Typing indicator continuava aparecendo após mensagem chegar   | Hotfix v0.6.1 | 2026-04-21 |
| B-03 | Catálogo do gestor não carregava (query sem tenant_id)        | Hotfix v0.6.1 | 2026-04-21 |
| B-04 | Feedback marcado como positivo mesmo em respostas de erro     | Hotfix v0.6.1 | 2026-04-21 |
| B-05 | confirmar_pedido retornava erro técnico visível ao usuário    | Hotfix v0.6.1 | 2026-04-21 |
| B-06 | PDF e chat exibiam UUIDs em vez de nomes de cliente/rep       | Hotfix v0.6.1 | 2026-04-21 |
| B-14 | listar_pedidos_por_status retorna vazio — tabela pedidos zerada | Hotfix v0.9.1 | 2026-04-27 |
| B-15 | commerce_vendedores ignorada — listar_representantes ausente   | Hotfix v0.9.1 | 2026-04-27 |
| B-16 | Dashboard /clientes mostra "Nenhum cliente" (614 em commerce_*) | Hotfix v0.9.1 | 2026-04-27 |
| B-17 | Dashboard /pedidos mostra "Nenhum pedido" (2592 em commerce_*)  | Hotfix v0.9.1 | 2026-04-27 |
| B-18 | Home sync EFOS mostra "Nunca sincronizado" (bug render inicial)  | Hotfix v0.9.1 | 2026-04-27 |
| B-19 | Home KPIs sempre 0/0/0 — pedidos vazio, sem fallback commerce   | Hotfix v0.9.1 | 2026-04-27 |
| B-20 | Dashboard /top-produtos "Nenhum produto" — itens_pedido vazio   | Hotfix v0.9.1 | 2026-04-27 |
| B-21 | Dashboard /representantes fora do menu de navegação + vazio     | Hotfix v0.9.1 | 2026-04-27 |
| B-22 | Bot usava emojis apesar de feedback "Não usar emojis" (20/04)   | Hotfix v0.9.1 | 2026-04-27 |
| B-07 | Redis history corruption — orphaned tool_result causava 400   | Sprint 4      | 2026-04-20 |
| B-08 | Agentes anunciavam ferramentas que não existiam               | Sprint 4      | 2026-04-20 |
| B-09 | Período hardcoded 30 dias no SQL — ignorava pedido do usuário | Sprint 4      | 2026-04-20 |
