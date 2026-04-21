# Sprint 6 — Pre-Pilot Hardening

**Status:** Em planejamento
**Data:** 2026-04-21
**Pré-requisitos:** Sprint 5 concluído na branch alvo; staging acessível; tenant piloto JMB com catálogo, ao menos 1 representante ativo e pedidos confirmados para smoke/homologação

## Objetivo

Colocar o dashboard do gestor e o baseline operacional mínimo num estado seguro para um piloto controlado com a JMB, priorizando primeiro os blockers funcionais reais do gestor.

## Contexto

O plano-base em `docs/exec-plans/active/pre-pilot-hardening.md` já separa corretamente a prioridade: funcionalidade do gestor antes de hardening amplo. A revisão do código atual confirma quatro blockers imediatos do dashboard:

1. `POST /dashboard/clientes/novo` chama `TenantService.criar_cliente_ficticio(...)`, mas esse método não existe em `output/src/tenants/service.py`.
2. `POST /dashboard/precos/upload` chama `CatalogService.upload_excel_precos(...)`, porém o contrato atual do catálogo expõe `processar_excel_precos(...)` e retorna `ExcelUploadResult`, não um inteiro.
3. `/dashboard/top-produtos` existe, mas não tem entrada clara na navegação principal e o template aponta "Voltar ao início" para `/dashboard`, rota inexistente.
4. O dashboard ainda concentra SQL em helpers de UI e há ao menos uma junção sem vínculo explícito por `tenant_id` (`_get_pedidos_recentes`).

Com esses pontos quebrados, qualquer hardening mais amplo perde valor: o gestor do piloto continua sem conseguir operar o fluxo básico. Este sprint corrige esses blockers e adiciona apenas o hardening operacional mínimo para evitar falha silenciosa no piloto.

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| dashboard | UI |
| tenants | Repo, Service |
| catalog | Service |
| agents | Repo, Service, UI, Runtime |
| providers | Config, Runtime |
| app/bootstrap | Runtime |

## Considerações multi-tenant

- Todo fluxo corrigido do dashboard continua resolvendo `tenant_id` exclusivamente pelo cookie JWT `dashboard_session`; nenhum dado de tenant pode ser aceito por query string, form ou body.
- Toda query de dashboard tocada neste sprint deve filtrar por `tenant_id` e, quando houver `JOIN` entre tabelas compartilhadas, a condição deve incluir tanto a chave de relacionamento quanto `...tenant_id = ...tenant_id`.
- Cadastro de cliente e upload de preços devem persistir apenas dados do tenant logado; tentativas de usar `representante_id` ou entidades de outro tenant devem falhar sem side effects.
- Rate limiting do webhook deve ser particionado por identidade resolvida do tenant (`instance_id` e remetente) para que tráfego de um tenant não consuma a cota de outro.
- Os testes do sprint devem semear pelo menos dois tenants e provar que páginas/queries corrigidas do dashboard não leem nem alteram registros do tenant vizinho.

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| POSTGRES_URL | development, staging | conexão PostgreSQL com credenciais válidas |
| REDIS_URL | development, staging | Redis usado por deduplicação e rate limiting |
| JWT_SECRET | development, staging | assinatura do cookie JWT do dashboard |
| DASHBOARD_SECRET | development, staging | senha compartilhada de login do dashboard |
| EVOLUTION_API_KEY | development, staging | autenticação para chamadas à Evolution API |
| EVOLUTION_WEBHOOK_SECRET | development, staging | autenticação do webhook WhatsApp |
| OPENAI_API_KEY | development, staging | embeddings e componentes que dependem de OpenAI |
| ANTHROPIC_API_KEY | development, staging | LLM principal e health operacional Anthropic |

> Configs obrigatórias não-secretas para o sprint: `ENVIRONMENT`, `DASHBOARD_TENANT_ID` e `CORS_ALLOWED_ORIGINS`.

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| SQLAlchemy AsyncSession | Escritas em `async with session` não fazem commit automático | Todo insert/update tocado no sprint deve terminar com `await session.commit()` explícito |
| Starlette 1.0 | `TemplateResponse("name", {...})` usa API antiga e quebra em runtime | Sempre chamar `templates.TemplateResponse(request, "name.html", ctx)` |
| Jinja2 | `\|enumerate` não existe e gera 500 | Usar `loop.index` ou `loop.index0` nos templates |
| SQL período | `INTERVAL '30 days'` hardcoded ignora filtro dinâmico | Calcular `data_inicio` em Python e passar como parâmetro |
| Anthropic SDK | Overload/transiente e auth/quota não têm o mesmo significado operacional | Health/monitoramento deve classificar overload/timeout como `degraded` e auth/quota/chave inválida como `fail` |

## Entregas

### E1 — Corrigir cadastro de cliente via dashboard
**Camadas:** Repo, Service, UI
**Arquivo(s):**
- `output/src/tenants/repo.py`
- `output/src/tenants/service.py`
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/clientes_novo.html`
- `output/src/tests/unit/agents/test_dashboard.py`
**Critérios de aceitação:**
- [ ] `GET /dashboard/clientes/novo` autenticado retorna 200 e o select de representantes contém apenas reps ativos do tenant logado.
- [ ] `POST /dashboard/clientes/novo` com `nome`, `cnpj` e `representante_id` válidos cria exatamente 1 linha em `clientes_b2b` com `tenant_id` da sessão e redireciona para `/dashboard/clientes`.
- [ ] CNPJ com menos de 14 dígitos após normalização retorna 400, re-renderiza o formulário e não persiste cliente.
- [ ] CNPJ duplicado no mesmo tenant retorna 400 com mensagem `CNPJ já cadastrado`; o mesmo CNPJ em outro tenant não bloqueia a criação.
- [ ] `representante_id` de outro tenant não cria cliente e retorna erro observável (400 ou 404).

### E2 — Corrigir upload de preços via dashboard
**Camadas:** Service, UI
**Arquivo(s):**
- `output/src/dashboard/ui.py`
- `output/src/catalog/service.py`
- `output/src/tests/unit/agents/test_dashboard.py`
- `output/src/tests/fixtures/precos_teste.xlsx`
**Critérios de aceitação:**
- [ ] `POST /dashboard/precos/upload` usa o contrato atual do catálogo (`processar_excel_precos`) e trata `ExcelUploadResult` sem `AttributeError` nem `TypeError`.
- [ ] Com a fixture `precos_teste.xlsx`, a resposta HTTP 200 contém fragmento HTML com `linhas_processadas`, `inseridos` e total de erros.
- [ ] Arquivo ausente, vazio ou inválido retorna erro amigável inline (`4xx`) e não responde 500.
- [ ] Registros persistidos em `precos_diferenciados` ficam associados ao `tenant_id` da sessão do dashboard.

### E3 — Revisar fluxo e navegação de top produtos
**Camadas:** Repo, UI
**Arquivo(s):**
- `output/src/agents/repo.py`
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/base.html`
- `output/src/dashboard/templates/home.html`
- `output/src/dashboard/templates/top_produtos.html`
- `output/src/tests/unit/agents/test_dashboard.py`
**Critérios de aceitação:**
- [ ] Existe um ponto de entrada autenticado e visível para `/dashboard/top-produtos` a partir da navegação principal ou da home do dashboard.
- [ ] `GET /dashboard/top-produtos?dias=7&limite=5` retorna 200, preserva `dias` e `limite` no HTML e nunca aponta links para a rota inexistente `/dashboard`.
- [ ] O link de retorno do template aponta para `/dashboard/home`.
- [ ] O ranking mostra apenas itens de pedidos `confirmado` do tenant logado e não agrega dados de outro tenant.
- [ ] Estado vazio continua renderizando com 200 e mensagem visível, sem 500.

### E4 — Revisar queries do dashboard com foco em tenant isolation
**Camadas:** Repo, UI
**Arquivo(s):**
- `output/src/dashboard/ui.py`
- `output/src/agents/repo.py`
- `output/src/tests/unit/agents/test_dashboard.py`
**Critérios de aceitação:**
- [ ] Toda query de dashboard tocada neste sprint inclui filtro por `tenant_id` e todo `JOIN` entre tabelas multi-tenant inclui condição explícita de tenant.
- [ ] `_get_pedidos_recentes` passa a juntar `clientes_b2b` com `c.id = p.cliente_b2b_id AND c.tenant_id = p.tenant_id`.
- [ ] Testes negativos com tenant A e tenant B provam que `/dashboard/clientes`, `/dashboard/top-produtos` e os fluxos de edição/criação não leem nem alteram registros do outro tenant.
- [ ] Nenhum helper novo ou corrigido do dashboard lê `tenant_id` de query param, form ou body.

### E5 — Validar secrets críticos no startup
**Camadas:** Config, Runtime
**Arquivo(s):**
- `output/src/main.py`
- `output/src/providers/auth.py`
- `output/src/providers/db.py`
- `output/src/tests/unit/providers/test_startup_validation.py`
**Critérios de aceitação:**
- [ ] A inicialização da aplicação falha antes de aceitar requests se qualquer uma das variáveis `POSTGRES_URL`, `REDIS_URL`, `JWT_SECRET`, `DASHBOARD_SECRET`, `DASHBOARD_TENANT_ID`, `EVOLUTION_API_KEY`, `EVOLUTION_WEBHOOK_SECRET`, `OPENAI_API_KEY` ou `ANTHROPIC_API_KEY` estiver ausente em `development` ou `staging`.
- [ ] A mensagem de erro lista todas as variáveis ausentes numa única falha legível.
- [ ] `create_app()`/lifespan não retorna app saudável quando a validação falha.
- [ ] Teste unitário cobre cenário com múltiplas variáveis ausentes.

### E6 — Aplicar rate limiting no login do dashboard
**Camadas:** Config, UI
**Arquivo(s):**
- `output/src/dashboard/ui.py`
- `output/src/providers/db.py`
- `output/src/tests/unit/agents/test_dashboard.py`
**Critérios de aceitação:**
- [ ] `POST /dashboard/login` limita tentativas falhas a 5 por 15 minutos por IP de origem.
- [ ] A 6ª tentativa falha dentro da janela retorna HTTP 429 e mensagem visível de bloqueio temporário.
- [ ] Login correto antes de atingir o limite continua retornando 302 com cookie `dashboard_session`.
- [ ] Login correto após falhas abaixo do limite reseta o contador daquela origem.

### E7 — Aplicar rate limiting no webhook WhatsApp
**Camadas:** Config, UI
**Arquivo(s):**
- `output/src/agents/ui.py`
- `output/src/providers/db.py`
- `output/src/tests/unit/agents/test_webhook.py`
**Critérios de aceitação:**
- [ ] Webhooks `MESSAGES_UPSERT` válidos passam a ser limitados a 30 eventos por minuto por combinação `instance_id + remoteJid`.
- [ ] O primeiro request acima do limite retorna HTTP 429 com payload JSON estável e não agenda `_process_message`.
- [ ] Eventos que não são `MESSAGES_UPSERT` continuam retornando 200 sem agendar processamento.
- [ ] Testes unitários cobrem cenário dentro do limite e cenário bloqueado.

### E8 — Expor monitoramento/health check para falhas Anthropic
**Camadas:** Runtime, UI
**Arquivo(s):**
- `output/src/agents/runtime/_retry.py`
- `output/src/main.py`
- `scripts/health_check.py`
- `output/src/tests/unit/agents/test_anthropic_health.py`
**Critérios de aceitação:**
- [ ] `/health` passa a expor status por componente e inclui Anthropic com estados `ok`, `degraded` ou `fail`.
- [ ] Falhas transitórias Anthropic (ex.: overload 529 ou timeout) atualizam o componente para `degraded` e emitem log estruturado.
- [ ] Falhas definitivas (auth/quota/chave inválida) atualizam o componente para `fail`.
- [ ] `scripts/health_check.py` sai com exit code diferente de zero quando Anthropic estiver em `fail`.

### E9 — Ajustar CORS e cookie por ambiente
**Camadas:** Config, Runtime, UI
**Arquivo(s):**
- `output/src/main.py`
- `output/src/dashboard/ui.py`
- `output/src/tests/unit/agents/test_dashboard.py`
**Critérios de aceitação:**
- [ ] `create_app()` não usa mais `allow_origins=["*"]` em `staging` ou `production`.
- [ ] `ENVIRONMENT=development` permite apenas origens locais de desenvolvimento; `staging` e `production` exigem `CORS_ALLOWED_ORIGINS` explícito.
- [ ] O cookie `dashboard_session` continua `SameSite=Lax`, fica `Secure=False` em `development` e `staging`, e `Secure=True` em `production`.
- [ ] Testes unitários validam o `Set-Cookie` e o allow/deny de CORS por ambiente.

### E10 — Expandir testes do dashboard para os fluxos críticos
**Camadas:** UI
**Arquivo(s):**
- `output/src/tests/unit/agents/test_dashboard.py`
- `output/src/tests/unit/agents/test_webhook.py`
- `output/src/tests/unit/providers/test_startup_validation.py`
- `output/src/tests/staging/agents/test_dashboard_pre_pilot.py`
**Critérios de aceitação:**
- [ ] A suíte unitária cobre sucesso e erro de cadastro de cliente, upload de preços, top produtos, tenant isolation, rate limit de login, rate limit de webhook, startup validation e health Anthropic.
- [ ] A suíte de staging cobre login do dashboard e os três fluxos críticos do gestor (`clientes/novo`, `precos/upload`, `top-produtos`) contra infra real.
- [ ] `pytest -m unit` passa sem `xfail`/`skip` adicionados para mascarar os fluxos críticos.
- [ ] `lint-imports` passa sem violações nas camadas tocadas.

### E11 — Smoke e homologação pré-piloto
**Camadas:** UI
**Arquivo(s):**
- `scripts/smoke_sprint_6.py`
- `scripts/seed_homologacao_sprint-6.py`
- `docs/exec-plans/active/homologacao_sprint-6.md`
- `output/src/tests/staging/agents/test_dashboard_pre_pilot.py`
**Critérios de aceitação:**
- [ ] Existe smoke gate executável para o sprint e ele verifica login do dashboard, cadastro de cliente, upload de preços, top produtos e health Anthropic.
- [ ] Existe seed de homologação para staging com representante, cliente base, arquivo/fixture de preços e pedidos confirmados suficientes para `/dashboard/top-produtos`.
- [ ] O checklist humano cobre os fluxos críticos do gestor e os sinais operacionais mínimos antes do piloto.
- [ ] `python scripts/smoke_sprint_6.py` retorna `ALL OK` no staging antes da homologação manual.

## Critério de smoke staging (obrigatório se sprint toca Runtime ou UI)

Script: `scripts/smoke_sprint_6.py`

O script deve verificar automaticamente, contra infra real (mac-lablz/macmini-lablz):
- [ ] `GET /health` retorna 200 e o componente Anthropic não está em `fail`
- [ ] `POST /dashboard/login` com senha correta seta cookie e permite acessar `/dashboard/home`
- [ ] `POST /dashboard/clientes/novo` cria cliente de teste e o registro fica visível em `/dashboard/clientes`
- [ ] `POST /dashboard/precos/upload` processa planilha fixture e persiste ao menos 1 preço do tenant do teste
- [ ] `GET /dashboard/top-produtos?dias=30&limite=5` retorna 200 com filtro renderizado
- [ ] Burst controlado do webhook retorna 429 após ultrapassar o limite configurado

Execução esperada: `python scripts/smoke_sprint_6.py` → saída `ALL OK`

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | Login do dashboard | Acessar `/dashboard/login`, autenticar com `DASHBOARD_SECRET` | Redirect para `/dashboard/home` com cookie válido |
| H2 | Cadastro de cliente válido | Dashboard → Clientes → Novo Cliente → preencher dados válidos | Cliente aparece na lista imediatamente |
| H3 | CNPJ duplicado | Repetir H2 com o mesmo CNPJ | Form volta com mensagem `CNPJ já cadastrado` e sem duplicata |
| H4 | Upload de preços | Dashboard → Preços → subir planilha de homologação | Mensagem mostra contagem processada; preços ficam disponíveis no banco do tenant |
| H5 | Top produtos | Navegar pela UI até `/dashboard/top-produtos`, trocar `dias` e `limite` | Página responde 200, filtros preservados e navegação não cai em 404 |
| H6 | Health operacional | Executar `python scripts/health_check.py` e consultar `/health` | Anthropic aparece como `ok` ou `degraded`; nunca `fail` antes do piloto |

## Decisões pendentes

Nenhuma.

## Fora do escopo

- Redesenho completo da autenticação do dashboard com usuários individuais
- Hardening genérico de todos os endpoints HTTP além de `/dashboard/login` e `/webhook/whatsapp`
- Refactor amplo do dashboard para remover toda SQL da camada UI
- Teste de carga, chaos engineering ou tuning de performance além do smoke gate
- Novas features de produto no dashboard fora dos fluxos já existentes

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Staging sem dados mínimos para top produtos e upload | Média | Alto | Exigir `seed_homologacao_sprint-6.py` com representantes, pedidos confirmados e fixture de preços |
| Threshold de rate limiting bloquear uso legítimo do piloto | Média | Médio | Tornar limites configuráveis por env, mas com defaults fixos e testes cobrindo o contrato |
| Health Anthropic ficar superficial e não distinguir transiente de falha definitiva | Média | Alto | Exigir classificação mecânica `ok/degraded/fail` com testes unitários por tipo de erro |
| `DASHBOARD_TENANT_ID` hardcoded/default continuar escondendo bug multi-tenant | Alta | Alto | Tornar a variável obrigatória no startup validation e remover fallback silencioso |

## Handoff para o próximo sprint

Se este sprint fechar os blockers e os gates de smoke/homologação, o próximo trabalho pode sair do modo "quebrado para piloto" e voltar para backlog evolutivo: auth multiusuário do dashboard, runbooks mais completos, observabilidade mais profunda e onboarding do segundo tenant.
