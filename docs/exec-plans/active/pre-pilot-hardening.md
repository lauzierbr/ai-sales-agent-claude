# Pre-Pilot Hardening — Funcionalidade + Operação

**Status:** 🔄 Rascunho para planejamento
**Data:** 2026-04-21
**Origem:** consolidação de avaliação funcional e operacional pré-piloto
**Objetivo:** transformar o estado atual da codebase em um baseline seguro para
liberação controlada com a JMB Distribuidora

---

## Contexto

As avaliações mais recentes convergem em um ponto central:

- o núcleo conversacional do produto está relativamente maduro
- os maiores riscos imediatos para piloto estão no dashboard operacional
- além disso, faltam alguns controles mínimos de operação para evitar falha
  silenciosa em staging/piloto

Este plano prioriza primeiro o que quebra fluxo real do gestor e depois o que
reduz risco operacional do piloto.

---

## Meta de saída

Ao final deste plano, o projeto deve estar apto para:

1. criar cliente fictício via dashboard sem erro
2. subir planilha de preços via dashboard sem erro
3. consultar top produtos e navegar pelo dashboard sem links quebrados
4. operar o webhook e o login do dashboard com hardening mínimo
5. detectar ausência de secrets e falhas Anthropic antes de afetar o usuário
6. executar smoke + homologação manual com checklist claro

---

## Gates de go/no-go

### G0 — Funcionalidade crítica do gestor
- [ ] `POST /dashboard/clientes/novo` funcional
- [ ] `POST /dashboard/precos/upload` funcional
- [ ] `GET /dashboard/top-produtos` funcional
- [ ] navegação básica do dashboard sem 404 evidente

### G1 — Baseline de qualidade do escopo tocado
- [ ] `pytest -m unit` verde
- [ ] testes novos cobrindo fluxos críticos do dashboard
- [ ] `lint-imports` verde
- [ ] `mypy --strict` pelo menos verde nos módulos tocados neste plano

### G2 — Hardening operacional mínimo
- [ ] validação de secrets críticos no startup
- [ ] rate limiting no login do dashboard
- [ ] rate limiting no webhook WhatsApp
- [ ] monitoramento/health check para falhas Anthropic críticas

### G3 — Validação manual pré-piloto
- [ ] smoke de staging atualizado e verde
- [ ] checklist de homologação manual atualizado
- [ ] passagem manual dos cenários do gestor

---

## Entregas (checklist)

### Fase 0 — Bloqueadores funcionais do dashboard

#### E1 — Corrigir cadastro de cliente fictício
- [ ] implementar `TenantService.criar_cliente_ficticio(...)`
- [ ] garantir validação mínima de CNPJ e duplicidade
- [ ] ajustar `POST /dashboard/clientes/novo`
- [ ] cobrir fluxo feliz e erro amigável em teste unitário

**Arquivos-alvo iniciais**
- `output/src/tenants/service.py`
- `output/src/tenants/repo.py`
- `output/src/dashboard/ui.py`
- `output/src/tests/unit/...`

#### E2 — Corrigir upload de preços no dashboard
- [ ] alinhar `dashboard/ui.py` com API real de `CatalogService`
- [ ] validar retorno e mensagem para sucesso/erro
- [ ] cobrir upload válido e inválido em teste unitário

**Arquivos-alvo iniciais**
- `output/src/dashboard/ui.py`
- `output/src/catalog/service.py`
- `output/src/tests/unit/...`

#### E3 — Corrigir fluxo de top produtos e navegação
- [ ] remover link quebrado ou criar destino válido
- [ ] revisar renderização e parâmetros `dias/limite`
- [ ] testar acesso autenticado à página

**Arquivos-alvo iniciais**
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/top_produtos.html`
- `output/src/tests/unit/...`

#### E4 — Revisar queries do dashboard com foco em tenant isolation
- [ ] corrigir joins sem vínculo explícito por `tenant_id`
- [ ] revisar queries auxiliares do dashboard tocadas nesta fase
- [ ] criar ao menos um teste para o caso corrigido

**Arquivos-alvo iniciais**
- `output/src/dashboard/ui.py`
- `output/src/tests/unit/...`

---

### Fase 1 — Hardening operacional mínimo

#### E5 — Validar secrets críticos no startup
- [ ] definir lista de env vars bloqueantes
- [ ] abortar startup com mensagem clara quando faltarem
- [ ] registrar health failure explícito

**Secrets mínimos esperados**
- [ ] `JWT_SECRET`
- [ ] `DASHBOARD_SECRET`
- [ ] `EVOLUTION_WEBHOOK_SECRET`
- [ ] `OPENAI_API_KEY`
- [ ] `ANTHROPIC_API_KEY`

#### E6 — Rate limiting básico
- [ ] limitar `POST /dashboard/login`
- [ ] limitar `POST /webhook/whatsapp`
- [ ] definir comportamento em excesso de chamadas
- [ ] logar bloqueios de forma observável

#### E7 — Monitoramento de falha Anthropic
- [ ] diferenciar overload temporário de quota/chave inválida
- [ ] criar health check ou probe explícita para Anthropic
- [ ] expor sinal claro para operação em staging

#### E8 — Hardening de borda web
- [ ] restringir CORS a origens conhecidas do ambiente
- [ ] revisar necessidade de checagem de origem nos `POST`s do dashboard
- [ ] parametrizar `secure` do cookie por ambiente

#### E9 — Deduplicação degradada observável
- [ ] quando Redis falhar na deduplicação, emitir warning claro
- [ ] manter comportamento resiliente sem esconder o problema

---

### Fase 2 — Reestabelecer baseline de qualidade

#### E10 — Baseline de tipos e documentação
- [ ] reduzir ou zerar erros de `mypy --strict` no escopo tocado
- [ ] atualizar `docs/QUALITY_SCORE.md` conforme estado real
- [ ] alinhar documentação de status com a entrega real

#### E11 — Cobertura do dashboard
- [ ] expandir testes além de login/redirecionamento
- [ ] cobrir ao menos os fluxos de cliente novo, upload de preços e top produtos
- [ ] cobrir um caminho de erro do dashboard com mensagem amigável

---

### Fase 3 — Validação pré-piloto

#### E12 — Smoke e homologação
- [ ] atualizar smoke de staging com os fluxos do gestor
- [ ] atualizar checklist de homologação manual
- [ ] rodar validação manual ponta a ponta em staging

#### E13 — Checklist operacional do piloto
- [ ] definir runbook curto para “bot não responde”
- [ ] definir como verificar saúde da Anthropic, Redis e Evolution API
- [ ] registrar critérios de rollback/pausa do piloto

---

## Ordem recomendada de execução

```text
1. E1 — cliente fictício
2. E2 — upload de preços
3. E3 — top produtos / navegação
4. E4 — revisão de queries do dashboard
5. pytest -m unit
6. E5 — validação de secrets no startup
7. E6 — rate limiting
8. E7 — health check / monitoramento Anthropic
9. E8 — CORS + cookie secure por ambiente
10. E9 — warning na deduplicação degradada
11. E10 + E11 — tipos, docs e cobertura
12. E12 + E13 — smoke, homologação e runbook
```

---

## Critérios de saída por fase

### Saída da Fase 0
- todos os fluxos críticos do dashboard do gestor funcionam localmente
- testes unitários novos existem para os fluxos corrigidos
- nenhum blocker funcional conhecido permanece nesses endpoints

### Saída da Fase 1
- app não sobe silenciosamente sem secrets essenciais
- login e webhook têm proteção mínima contra abuso
- falha Anthropic deixa sinal operacional claro

### Saída da Fase 2
- baseline de qualidade do escopo tocado é confiável
- documentação não afirma um estado que o código não cumpre

### Saída da Fase 3
- staging smoke verde
- homologação manual pronta para execução
- existe runbook mínimo para incidente

---

## Itens explicitamente fora do escopo imediato

- Channel formatter multi-canal
- paginação completa do dashboard
- refactor amplo de `except Exception`
- teste de carga pesado antes de corrigir os blockers funcionais
- mudanças arquiteturais grandes fora do escopo de piloto

---

## Entradas sugeridas para o Planner

Quando iniciar o Planner para este trabalho, manter estas diretrizes:

1. priorizar funcionalidade do gestor e dashboard antes de hardening amplo
2. transformar blockers funcionais em critérios de Alta
3. incluir smoke/staging porque o escopo toca UI e Runtime
4. exigir testes específicos para os fluxos `clientes/novo`, `precos/upload` e
   `top-produtos`
5. evitar contrato genérico de “melhorar segurança”; cada item deve ser
   verificável mecanicamente

---

## Resultado esperado deste plano

Se executado integralmente, este plano deve deslocar o projeto de:

- “núcleo bom, operação frágil e dashboard parcialmente quebrado”

para:

- “piloto controlado possível, com fluxo do gestor funcional e observabilidade
  mínima para operar sem falha silenciosa”
