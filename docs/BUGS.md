# Bug Tracker

## Abertos

| ID   | Descrição                                           | Severidade | Sprint origem    | Data abertura |
|------|-----------------------------------------------------|------------|------------------|---------------|
| B-01 | Gestor não recebe notificação quando pedido é feito | Alta       | Sprint 6 homolog | 2026-04-21    |
| B-10 | Pedido criado sem representante mesmo quando cliente tem rep. vinculado | Alta | Piloto | 2026-04-24 |
| B-11 | Agente perde contexto conversacional mid-session após troca de persona do número | Alta | Piloto | 2026-04-24 |
| B-12 | Instrumentação Langfuse incompleta — output null, zero tokens/custo, sem generations nem sessions | Média | Piloto | 2026-04-24 |
| B-13 | Busca de produto por EAN falha — bot não mapeia últimos 6 dígitos do EAN para código interno JMB | Alta | Piloto | 2026-04-27 |
| B-28 | Criar pedido em nome de cliente EFOS falha — get_by_id sem fallback commerce + LLM alucina "instabilidade de ID" | Crítica | Homologação Sprint 9 | 2026-04-29 |
| B-29 | Logs poluídos com "'str' object has no attribute 'decode'" em persona_key_redis_erro — fix B-11 quebra com redis-py >= 5.0 (decode_responses já retorna str) | Baixa | Homologação Sprint 9 | 2026-04-29 |
| B-30 | B-12 só parcialmente resolvido — Langfuse continua sem tokens/custo. `_get_anthropic_client` tem docstring mentindo: não wrappa o cliente, só seta session_id no trace. Generations nunca são criadas | Média | Homologação Sprint 9 | 2026-04-29 |
| B-31 | Valores monetários no dashboard em formato americano ("R$ 2106925.14" em vez de "R$ 2.106.925,14") — corrigido em v0.9.2 com filter Jinja `\|brl` central em providers/format.py | Média | Homologação Sprint 9 | 2026-04-29 |
| B-32 | KPIs "GMV HOJE / PEDIDOS HOJE" mostravam total histórico EFOS (2592 pedidos, R$ 2.1M) quando não há pedidos hoje — fallback de 3 níveis caía em "efos_total" sem mudar label. Corrigido em v0.9.3 — KPIs zeram quando hoje vazio; total histórico vai pro bloco sync. | Alta | Homologação Sprint 9 | 2026-04-29 |

> **B-32 detalhe:** Hotfix Sprint 9 (B-19) introduziu fallback em 3 níveis no
> `_get_kpis`: bot → EFOS hoje → **EFOS total histórico**. Quando não havia
> pedidos hoje, exibia o total acumulado desde 2024-06-10 (2592 pedidos,
> R$ 2.106.925,14) com label "GMV HOJE" — semanticamente errado. Gestor JMB
> identificou imediatamente em homologação 29/04 ("não aconteceram 2592
> pedidos em um único dia").
>
> **Correção (v0.9.3):**
> - Removido o terceiro fallback `efos_total` em `_get_kpis`
> - KPIs "hoje" voltam a ser estritos: 0 quando hoje não há pedidos, ponto
> - `kpis.fonte` exposto ao template (bot | efos_hoje) — label muda quando
>   dados vêm do EFOS-hoje ("GMV Hoje (EFOS hoje)")
> - Total histórico EFOS movido para o bloco "Última sincronização EFOS"
>   onde faz sentido: linha extra "Histórico EFOS: 2.592 pedidos · R$ 2.106.925,14
>   · 10/06/2024 a 27/04/2026"

> **B-30 detalhe (continuação do B-12):**
>
> Sprint 8 marcou B-12 como resolvido alegando "wrapper Langfuse + session_id +
> output". Verificação via Langfuse API mostra que apenas 2 dos 3 gaps foram
> corrigidos:
>
> | Gap | Status | Observado |
> |-----|--------|-----------|
> | `output=null` no trace | ✅ resolvido | `update_current_observation(output=...)` chamado |
> | `session_id` ausente | ✅ resolvido | `update_current_trace(session_id=...)` chamado |
> | tokens/custo zerados | ❌ **NÃO resolvido** | `observations: []` vazio em todos os traces |
>
> **Evidência via API Langfuse (29/04 13:05 traces reais):**
> ```json
> {
>   "id": "2a33baa6-...",
>   "name": "processar_mensagem_gestor",
>   "sessionId": "d6f3753a-...",   ← OK
>   "output": "Houve um erro ao registrar...",  ← OK
>   "totalCost": 0,                ← FALHA
>   "latency": 0,                  ← FALHA
>   "observations": []             ← FALHA — sem generations
> }
> ```
>
> **Causa raiz:**
>
> `output/src/agents/runtime/agent_gestor.py:1309-1326` (e equivalente em
> agent_cliente.py e agent_rep.py):
>
> ```python
> def _get_anthropic_client(self, session_id: str = "") -> Any:
>     """Retorna cliente Anthropic com wrapper Langfuse..."""  # ← MENTIRA
>     if self._anthropic is not None:
>         return self._anthropic
>     import anthropic
>     if _LANGFUSE_ENABLED and session_id:
>         _lf_ctx.update_current_trace(session_id=session_id)
>     return anthropic.AsyncAnthropic()  # ← cliente PURO
> ```
>
> Não há wrapping. A chamada subsequente
> `client.messages.create(model=..., messages=..., tools=...)` é invisível
> ao Langfuse. Sem generation registrada, Langfuse não tem tokens nem
> contagem de uso para calcular custo.
>
> **Por que o Sprint 8 errou:**
>
> Não existe integração nativa Langfuse-Anthropic (existe para OpenAI via
> `from langfuse.openai import openai`). Para Anthropic, precisa de wrapper
> manual. O Generator não percebeu — leu a doc do Langfuse de OpenAI por
> analogia e implementou só metade.
>
> **Correção (uma das três opções):**
>
> **Opção A — Context manager manual em torno do `call_with_overload_retry`:**
> ```python
> async def call_anthropic_with_langfuse(client, **kwargs):
>     if not _LANGFUSE_ENABLED:
>         return await client.messages.create(**kwargs)
>     with _lf.start_generation(
>         name="anthropic_call",
>         model=kwargs.get("model"),
>         input=kwargs.get("messages"),
>     ) as gen:
>         response = await client.messages.create(**kwargs)
>         gen.update(
>             output=[b.model_dump() for b in response.content],
>             usage={
>                 "input": response.usage.input_tokens,
>                 "output": response.usage.output_tokens,
>             },
>         )
>     return response
> ```
> Aplicar nos 3 agentes (cliente, rep, gestor) substituindo a chamada direta
> a `client.messages.create()`.
>
> **Opção B — Subclasse interceptando:**
> ```python
> class LangfuseWrappedAnthropic(anthropic.AsyncAnthropic):
>     async def messages_create(self, **kwargs):
>         # mesma lógica de wrap acima
>         ...
> ```
> Mais limpo se for usado em vários lugares.
>
> **Opção C — Decorator @observe(as_type="generation"):**
> Decorar uma função wrapper. Funciona mas exige refatoração maior.
>
> Recomendação: **Opção A** — menos invasivo, alinhada com `call_with_overload_retry`
> existente, fácil de testar.
>
> **Severidade Média (não Crítica):**
> - Não bloqueia funcionalidade do produto
> - Mas bloqueia observabilidade — sem custo por conversa, não dá para
>   monitorar gasto de tokens (importante para governance)
> - Sem generations não dá para fazer evals de qualidade no Langfuse
| B-23 | Áudio WhatsApp (H-20/F-02a) não funciona — Whisper rejeita 400 "Invalid file format" porque audioMessage.url retorna conteúdo criptografado E2E | Alta | Homologação Sprint 9 | 2026-04-29 |
| B-24 | Bot nega capacidade de áudio em vez de admitir falha temporária — fallback injeta texto que confunde o LLM + system prompt não menciona a capacidade | Alta | Homologação Sprint 9 | 2026-04-29 |
| B-25 | Inconsistência de ano em relatórios + ausência de tool de ranking — agente faz 24 chamadas seriais e escolhe ano default diferente da pergunta anterior | Alta | Homologação Sprint 9 | 2026-04-29 |
| B-26 | Truncação cega do histórico Redis quebra pares tool_use/tool_result, dispara erro 400 e "recovery destrutivo" que apaga TODO o contexto conversacional | Crítica | Homologação Sprint 9 | 2026-04-29 |
| B-27 | Criar contato com perfil "cliente" via dashboard é NO-OP silencioso — UPDATE em clientes_b2b com ID do EFOS (commerce_accounts_b2b) acerta 0 rows e redireciona como sucesso | Crítica | Homologação Sprint 9 | 2026-04-29 |

| B-28 | Criar pedido em nome de cliente EFOS falha — get_by_id sem fallback commerce_accounts_b2b + LLM aluciena erro técnico ("continua retornando o mesmo ID") | Crítica | Homologação Sprint 9 | 2026-04-29 |

> **B-28 detalhe (showstopper do fluxo de pedido pelo gestor):**
>
> Caso real 29/04 10:02-10:03. Gestor pediu pedido para "Lauzier Pereira", bot
> encontrou em commerce_accounts_b2b, mostrou confirmação correta, gestor
> respondeu "sim", bot retornou:
>
> > "O sistema continua retornando o mesmo ID. Pode ser uma instabilidade
> > pontual. Recomendo tentar novamente em instantes ou verificar diretamente
> > no sistema se o cliente esta ativo."
>
> Essa frase é **alucinação do LLM** reformulando o erro real
> `{"erro": "Cliente XYZ não encontrado."}` que veio da tool. Nada disso
> sobre "ID instável" existe no código.
>
> **Mecanismo:**
>
> 1. Gestor: "quero 5 Loção... para o cliente Lauzier Pereira"
> 2. AgentGestor chama `_buscar_clientes("Lauzier Pereira")`
> 3. `_buscar_clientes` em `agents/repo.py` faz fallback para
>    `commerce_accounts_b2b` quando `clientes_b2b` retorna vazio (B-16 fix)
> 4. Retorna cliente Lauzier com `id = external_id` do EFOS (string tipo "63.153.691")
> 5. Bot mostra confirmação "Cliente: 63.153.691 LAUZIER PEREIRA DE ARAUJO" ✓
> 6. Gestor: "sim"
> 7. AgentGestor chama `confirmar_pedido_em_nome_de(cliente_b2b_id="63.153.691", ...)`
> 8. `_confirmar_pedido` em `agent_gestor.py:768` chama
>    `self._cliente_b2b_repo.get_by_id(id="63.153.691", tenant_id="jmb", session=...)`
> 9. `ClienteB2BRepo.get_by_id` em `agents/repo.py:367-374`:
>    ```python
>    SELECT id, ... FROM clientes_b2b WHERE id = :id AND tenant_id = :tenant_id
>    ```
>    **NÃO TEM FALLBACK para commerce_accounts_b2b** (diferente de
>    `_buscar_clientes`). E `clientes_b2b` está vazia.
> 10. Retorna `None` → `{"erro": "Cliente 63.153.691 não encontrado."}`
> 11. LLM tenta reformular o erro mas alucina "ID instável", "instabilidade
>     pontual" — porque vê "Cliente {id} não encontrado" e infere problema
>     técnico de ID
> 12. Em iteration 2 (logs 10:03:01), bot tenta de novo `_buscar_clientes`
>     no fluxo (talvez para validar) — busca acerta de novo no EFOS, mas o
>     loop continua. Atinge limite ou desiste.
> 13. Gestor recebe alucinação técnica
>
> **Por que a tool de busca funciona mas a de confirmar não:**
> - `_buscar_clientes` foi atualizada no hotfix Sprint 9 (B-16) com fallback
>   para `commerce_accounts_b2b`
> - `get_by_id` NÃO foi atualizada — não estava no escopo grep do hotfix
>   porque não usa "FROM clientes_b2b" como pattern principal (usa por id)
> - Esse é o tipo de inconsistência que o D030 resolve estruturalmente
>
> **Severidade Crítica:** bloqueia o fluxo de "gestor fazer pedido em nome de
> cliente" — caso de uso central do produto. Combinado com B-26 (recovery
> destrutivo) e B-27 (cadastro contato no-op), o gestor na prática não
> consegue operar via WhatsApp.
>
> **Resolução:**
>
> Estrutural via D030 — mesmo grupo de B-27. Quando migrar para tabela
> `contacts` + `commerce_accounts`, `confirmar_pedido_em_nome_de` deve
> aceitar `account_external_id` (do `commerce_accounts`) e gravar em
> `pedidos.cliente_b2b_id` apontando para... aqui há decisão arquitetural:
>
> - **Opção A**: `pedidos.account_external_id VARCHAR` (sem FK) — pedido
>   referencia EFOS direto, simples
> - **Opção B**: criar `clientes_b2b` automaticamente clonando do EFOS
>   antes do INSERT — mantém schema atual mas suja a tabela
> - **Opção C**: substituir `pedidos.cliente_b2b_id` por
>   `pedidos.account_external_id` em migration; remover FK
>
> Recomendação: **Opção C** — alinhada com D030 onde `commerce_accounts`
> é fonte de verdade para PJ. Migration nova no Sprint 10.
>
> **Bug adicional (Média) detectado nos logs:**
> `persona_key_redis_erro error="'str' object has no attribute 'decode'"`
> aparece em todas as mensagens. É no fix do B-11 (invalidação Redis ao
> trocar persona) — código chama `persona_anterior.decode()` mas em
> redis-py >= 5.0 o `get()` já retorna string em modo `decode_responses=True`.
> Não impede funcionalidade mas polui logs. Registrar como B-29 leve.

> **B-27 — RESOLUÇÃO ESTRUTURAL VIA D030 (não fix raso):**
> Decisão do PO em 29/04: B-27 NÃO será corrigido com remendo no
> `clientes_b2b`. Será resolvido no Sprint 10 com a estrutura nova de
> `contacts` (write model app) referenciando `commerce_accounts` (read model
> ERP). Ver [ADR D030](design-docs/D030-erp-adapter-and-contact-ownership.md)
> para o modelo completo.

> **B-27 detalhe (showstopper):** Caso real homologação 29/04 09:30-09:32.
> Logs confirmam 2 POSTs `/dashboard/contatos/novo` retornando 302 sem erro,
> mas `clientes_b2b` permaneceu com 0 rows.
>
> **Mecanismo do bug:**
>
> 1. Página `/dashboard/contatos/novo` (GET) chama `_get_clientes(tenant_id, "")`
>    para popular dropdown de clientes B2B existentes
> 2. `clientes_b2b` está vazia (0 rows após reset Sprint 8/9)
> 3. `_get_clientes` cai no fallback de `commerce_accounts_b2b` (B-16 fix do
>    hotfix) — retorna 614 clientes do EFOS, com `id = external_id` do EFOS
> 4. Usuário seleciona um cliente do dropdown — `cliente_b2b_id` no form vai
>    com ID do `commerce_accounts_b2b` (não existe em `clientes_b2b`)
> 5. POST `/dashboard/contatos/novo` (linha 502-506 de `dashboard/ui.py`):
>    ```python
>    elif perfil == "cliente" and cliente_b2b_id:
>        await session.execute(
>            text("UPDATE clientes_b2b SET telefone=:tel, nome_contato=:nc
>                  WHERE id=:id AND tenant_id=:tid"),
>            {"tel": telefone, "nc": nome_contato,
>             "id": cliente_b2b_id, "tid": tenant_id},
>        )
>    ```
> 6. UPDATE acerta **0 rows** (id do EFOS não existe em `clientes_b2b`)
> 7. PostgreSQL não levanta erro em UPDATE sem match — é semanticamente válido
> 8. `await session.commit()` roda sem erro
> 9. Redirect 302 para `/dashboard/contatos` — usuário vê tela como se sucesso
> 10. Listagem `/dashboard/contatos` lista gestores+reps+contatos de
>     `clientes_b2b` (que continua vazia) — novo contato não aparece
>
> **Por que é showstopper:** Impede o gestor de cadastrar novos contatos de
> cliente via dashboard. Único método alternativo é via /dashboard/clientes/novo
> (que cria cliente novo do zero, não vincula a um EFOS existente). Mesmo essa
> rota provavelmente tem o mesmo problema de visibilidade (será criado em
> `clientes_b2b` mas a listagem `/dashboard/clientes` mostra fallback EFOS
> ignorando os 1-N novos cadastros — verificar B-27b abaixo).
>
> **Sub-bugs:**
>
> **B-27a — UPDATE silencioso sem feedback de NO-OP**
> O código deveria verificar `result.rowcount` após UPDATE e levantar erro
> se 0 rows afetadas. Hoje aceita silenciosamente.
>
> **B-27b — Fallback condicional do `_get_clientes` esconde mistura**
> A lógica `if rows: return ... fallback` faz com que a listagem mostre OU
> `clientes_b2b` (quando ≥ 1 row) OU `commerce_accounts_b2b` (quando vazia)
> — nunca os dois juntos. Quando o gestor criar 1 cliente novo em
> `clientes_b2b`, a listagem vai mostrar APENAS esse 1 e esconder os 614 do
> EFOS. UX inconsistente.
>
> **B-27c — Modelo conceitual misturado**
> O fluxo de "criar contato cliente" assume que o cliente B2B já existe e o
> gestor está apenas adicionando contato/telefone. Mas com o reset, ninguém
> existe. Em vez de UPDATE, o fluxo deveria ser:
> - "Criar cliente B2B novo" (INSERT em clientes_b2b)
> - "Vincular telefone a cliente EFOS existente" (INSERT em clientes_b2b
>   clonando dados do commerce_accounts_b2b + telefone fornecido)
>
> **Correções:**
>
> 1. Verificar `result.rowcount` em todos os UPDATEs do dashboard, retornar
>    400 se 0 rows
> 2. Para "cliente": se `cliente_b2b_id` aponta para EFOS (não existe em
>    `clientes_b2b`), fazer INSERT em `clientes_b2b` clonando dados de
>    `commerce_accounts_b2b` + adicionando telefone/nome_contato
> 3. Padronizar listagem: mostrar UNION ALL de `clientes_b2b` + clientes do
>    EFOS que ainda não foram clonados, com badge indicando origem
> 4. Adicionar teste de regressão `test_b27_*` que cria contato cliente e
>    valida que aparece na listagem
>
> **Locais a modificar:**
> - `output/src/dashboard/ui.py:475-518` (POST contatos/novo)
> - `output/src/dashboard/ui.py:927-1003` (`_get_clientes` listagem)
> - `output/src/dashboard/ui.py` rota POST de `/dashboard/clientes/novo`
>   (verificar mesmo padrão)

> **B-26 detalhe:** **CAUSA RAIZ do B-25c**. Investigação aprofundada mostrou
> que o agente perde contexto não por limitação do LLM, mas por bug estrutural
> no gerenciamento de histórico. Afeta os **3 agentes** (cliente, rep, gestor).
>
> **Mecanismo exato (passo a passo, exemplo do gestor 28/04 13:16):**
>
> 1. Conversa do gestor acumula >= 20 mensagens (cada tool_use gera 4 entries:
>    user, assistant_tool_use, user_tool_result, assistant_text)
> 2. `_salvar_historico_redis` (agent_gestor.py:1353) trunca cegamente:
>    `trimmed = messages[-historico_max_msgs:]` (max=20)
> 3. Truncação corta no meio de um par tool_use/tool_result — o histórico
>    salvo começa com um `tool_result` órfão ou contém `tool_use` sem `tool_result`
> 4. Próxima mensagem do usuário: `_carregar_historico_redis` lê histórico
>    inválido, anexa nova mensagem e envia à API
> 5. Anthropic API retorna 400: `"messages.0.content.0: unexpected tool_result..."`
> 6. Bloco `except` em agent_gestor.py:487-507 detecta o erro e:
>    a. Loga `agent_gestor_historico_corrompido_recovery`
>    b. **Chama `_limpar_historico_redis` — APAGA TODO O HISTÓRICO REDIS**
>    c. Reseta `messages = [{"role":"user","content":mensagem.texto}]`
>    d. Refaz a chamada com histórico vazio
> 7. **Resultado: agente perdeu TODO o contexto da conversa anterior**
>
> **Frequência observada:** 3 ocorrências em 19h (27/04 23:22, 28/04 09:15,
> 28/04 13:16). Não é raro — qualquer conversa com >= 5 tool calls dispara.
>
> **Locais afetados (mesmo padrão nos 3 agentes):**
> - `output/src/agents/runtime/agent_gestor.py:495` (limpar) + `:1353` (truncar)
> - `output/src/agents/runtime/agent_rep.py:350` (limpar) + `:528` (truncar)
> - `output/src/agents/runtime/agent_cliente.py:301` (limpar) + `:469` (truncar)
> - `output/src/agents/runtime/agent_cliente.py:441` (truncar no load também)
> - `output/src/agents/runtime/agent_rep.py:502` (truncar no load também)
>
> **Correções (precisa ambas):**
>
> **B-26a — Truncação respeitando integridade**
> Substituir `messages[-N:]` por uma função `truncate_preserving_pairs(messages, max)`:
> - Se o slice começaria com `{"role":"user","content":[{"type":"tool_result",...}]}`,
>   recuar até o `assistant` com `tool_use` correspondente (incluí-lo)
> - Se o slice terminaria com `{"role":"assistant","content":[{"type":"tool_use",...}]}`
>   sem `tool_result` adjacente após, avançar até incluir o `tool_result` ou
>   recuar até excluir o `tool_use`
> - Alternativa mais simples: trabalhar em "turnos" (user-message → assistant-final-text),
>   nunca cortar dentro de um turno
>
> **B-26b — Recovery não-destrutivo**
> Em vez de `_limpar_historico_redis`, usar uma função `repair_history`:
> - Tentar remover apenas os pares órfãos do início do histórico
> - Se ainda assim falhar, descartar TOOL CALLS antigas mas manter o texto
>   das mensagens user/assistant (preservando o contexto conversacional)
> - Apagar tudo só como último recurso, e logar como erro (não warning)
>
> **Teste de regressão obrigatório:**
> - `tests/regression/test_b26_truncation_integrity.py`
> - Criar histórico de 25 mensagens com pares tool_use/tool_result
> - Aplicar truncação para 20 → assertar que o histórico retornado é válido
>   para Anthropic API (cada tool_use tem seu tool_result, nenhum órfão)
> - Aplicar repair com histórico já corrompido → assertar que retorna histórico
>   válido com pelo menos as N últimas mensagens text-only preservadas
>
> **Severidade Crítica porque:**
> - Afeta os 3 agentes (todo o produto)
> - Impede continuidade conversacional (UX core do bot)
> - Não foi pego por nenhum teste anterior (mocks não simulam API real)
> - Confundido com bug de LLM (B-25c) — investigação revelou ser estrutural

> **B-25 detalhe:** Caso real (28/04 13:16-13:17):
>
> - **Pergunta 1:** "relatório de vendas do representante Rondinele de março/26"
>   → R$ 32.221,22 / 43 pedidos (correto: março/2026 confirmado no banco)
> - **Pergunta 2:** "qual foi o melhor vendedor de março?"
>   → Rondinele com R$ 34.283,49 / 27 pedidos (correto: março/2025 no banco, mas
>     ano errado — usuário esperava 2026, mesmo contexto da pergunta anterior)
>
> **3 problemas independentes na mesma cena:**
>
> **B-25a — Sem tool de ranking consolidada**
> O agente não tem tool tipo `ranking_vendedores_efos(mes, ano)` que retorne o
> ranking completo numa query. Ao receber "melhor vendedor de março", iterou
> em 24 chamadas seriais de `relatorio_vendas_representante_efos` (uma por rep
> ativo), confirmado nos logs `fuzzy_match_vendedor` para todos os 24 reps em
> sequência às 13:17:12. Comportamento ineficiente, lento, custoso (24x tokens).
>
> **Correção:** Adicionar tool `ranking_vendedores_efos(mes, ano, top_n=10)`
> que faz uma única SQL agregada em `commerce_orders` JOIN `commerce_vendedores`
> ordenada por SUM(total) DESC LIMIT top_n. Anunciar no system prompt como a
> tool preferida para perguntas de ranking/comparação.
>
> **B-25b — Ano default inconsistente**
> Hoje é 2026-04-29. "Março" sem qualificação deveria ser março/2026 (último
> março passado). Mas o agente escolheu março/2025. Provável causa: tool
> consultada (`relatorio_vendas_representante_efos`) recebe `ano` como parâmetro
> obrigatório do LLM — se LLM não tem default claro no system prompt, escolha
> é arbitrária.
>
> **Correção:** No system prompt do AgentGestor, adicionar regra explícita:
> "Quando o usuário não informar ano, use o ano corrente. Se o mês mencionado
> ainda não passou no ano corrente, use o ano anterior."
>
> Em `_relatorio_vendas_representante_efos` e `_relatorio_vendas_cidade_efos`,
> tornar `ano` opcional com default `datetime.now().year`.
>
> **B-25c — Sem manutenção de contexto temporal entre perguntas**
> Quando a primeira pergunta especifica "março/26", a segunda sobre "março"
> deveria herdar o mesmo ano (mesmo escopo conversacional). Hoje cada
> tool_call é independente.
>
> **Correção (escopo maior):** Adicionar ao system prompt: "Quando o usuário
> fizer perguntas sequenciais sobre o mesmo período, mantenha o ano da pergunta
> anterior se não houver indicação contrária." Isso é uma regra de prompt;
> não requer mudança estrutural.
>
> **Arquivos a modificar:**
> - `output/src/agents/runtime/agent_gestor.py` — nova tool ranking +
>   defaults de ano nas tools existentes
> - `output/src/commerce/repo.py` — novo método `ranking_vendedores`
> - `output/src/agents/config.py` — system prompt do gestor com regras de ano

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
