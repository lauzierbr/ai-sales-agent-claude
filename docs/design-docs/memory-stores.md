# D015 — Memory Stores: separação e mapeamento

**Status:** Aprovado
**Data:** 2026-04
**Contexto:** Migração do harness para Claude Managed Agents (Fase 2).
Os documentos do repositório precisam ser distribuídos em Memory Stores
para que cada agente receba exatamente o contexto necessário — nem mais,
nem menos.

---

## Por que Memory Stores, não um único CLAUDE.md

O `AGENTS.md` funciona como ponto de entrada no Claude Code porque o
agente lê tudo de uma vez e você está presente para corrigir desvios.
No Managed Agents, cada session tem custo de tokens e contexto limitado.

Carregar o repositório inteiro em cada session desperdiça tokens em
informação irrelevante. Por exemplo: o Generator que está escrevendo
`catalog/repo.py` não precisa do `docs/FRONTEND.md` naquele momento.
O Planner que está gerando o spec do Sprint 2 precisa do histórico do
Sprint 1, mas não do `infra/docker-compose.dev.yml`.

Memory Stores resolvem isso: o agente faz `memory_search` antes de
iniciar uma tarefa e carrega apenas o que é relevante.

---

## Os três stores

### Store 1: `project-knowledge`
**Acesso:** read-only para todos os agents
**Ciclo de vida:** criado uma vez, atualizado a cada ADR aprovado ou
sprint concluído. Nunca deletado.
**Responsável por popular/atualizar:** você (via script) após cada sprint

### Store 2: `active-sprint`
**Acesso:** read-write para todos os agents
**Ciclo de vida:** criado no início de cada sprint, arquivado ao final.
Um novo store é criado para o sprint seguinte.
**Responsável por criar:** script `run_sprint.py` no início de cada ciclo

### Store 3: `agent-prompts`
**Acesso:** read-only para todos os agents
**Ciclo de vida:** criado uma vez, atualizado quando os system prompts
evoluem (raramente).
**Responsável por popular/atualizar:** você ao evoluir os prompts

---

## Mapeamento completo: arquivo → store → path no store

### Store: `project-knowledge` (read-only)

| Arquivo no repo | Path no store | Atualiza quando |
|-----------------|---------------|-----------------|
| `AGENTS.md` | `/map.md` | Estrutura do repo muda |
| `ARCHITECTURE.md` | `/architecture.md` | Novo domínio ou camada |
| `docs/PRODUCT_SENSE.md` | `/product.md` | Novo tenant ou persona |
| `docs/DESIGN.md` | `/design.md` | Stack ou ambiente muda |
| `docs/SECURITY.md` | `/security.md` | Nova regra de segurança |
| `docs/RELIABILITY.md` | `/reliability.md` | Nova métrica ou SLO |
| `docs/FRONTEND.md` | `/frontend.md` | Sprint de UI concluído |
| `docs/design-docs/index.md` | `/adrs/index.md` | Novo ADR aprovado |
| `docs/design-docs/harness.md` | `/harness.md` | Processo do harness muda |
| `docs/design-docs/memory-stores.md` | `/adrs/D015.md` | Este documento |
| `pyproject.toml` | `/pyproject.toml` | Dependência ou linter muda |
| `output/.env.example` | `/env-example.md` | Nova variável de ambiente |

**ADRs individuais** (um arquivo por ADR):

| Arquivo no repo | Path no store |
|-----------------|---------------|
| *(inline em index.md agora)* | `/adrs/D001-D014.md` |
| Cada novo ADR aprovado | `/adrs/DXXX.md` |

**Histórico de sprints concluídos** (acrescenta a cada sprint):

| Conteúdo | Path no store |
|----------|---------------|
| Resumo do Sprint 0 ao final | `/sprint-history/sprint-0.md` |
| Resumo do Sprint 1 ao final | `/sprint-history/sprint-1.md` |
| ... | ... |

O resumo de sprint é um documento de ~1 página criado pelo Evaluator ao
aprovar, contendo: o que foi implementado, decisões técnicas tomadas,
débitos registrados, e o que o próximo sprint deve saber.

---

### Store: `active-sprint` (read-write)

Contém apenas os artefatos do sprint em execução. Tudo aqui é temporário.

| Arquivo | Path no store | Quem escreve | Quem lê |
|---------|---------------|--------------|---------|
| `artifacts/spec.md` | `/spec.md` | Planner | Generator, Evaluator |
| `artifacts/sprint_contract.md` | `/contract.md` | Generator (proposta) + Evaluator (negocia) | Todos |
| `docs/exec-plans/active/sprint-N.md` | `/exec-plan.md` | Planner (cria), Generator (atualiza) | Evaluator |
| `artifacts/handoff_sprint_N.md` | `/handoff.md` | Generator | Planner do próximo sprint |
| `artifacts/qa_sprint_N.md` | `/qa-report.md` | Evaluator | Você |
| `artifacts/qa_sprint_N_r1.md` | `/qa-report-r1.md` | Evaluator (se houver reprovação) | Generator, você |
| `artifacts/qa_sprint_N_r2.md` | `/qa-report-r2.md` | Evaluator (se houver 2ª reprovação) | Você |

**Ao final do sprint aprovado:**
1. Evaluator cria `/sprint-history/sprint-N.md` no store `project-knowledge`
2. O store `active-sprint` é arquivado (não deletado — mantém auditoria)
3. Um novo store `active-sprint` é criado vazio para o próximo sprint

---

### Store: `agent-prompts` (read-only)

| Arquivo no repo | Path no store |
|-----------------|---------------|
| `prompts/planner.md` | `/planner.md` |
| `prompts/generator.md` | `/generator.md` |
| `prompts/evaluator.md` | `/evaluator.md` |

**Por que um store separado para os prompts:**
Os prompts são os system prompts dos próprios agentes — eles precisam
estar disponíveis para auto-referência (ex: o Generator pode consultar
o prompt do Evaluator para entender o que será verificado antes de
submeter). Separar em store próprio evita que sejam confundidos com
documentação de produto e mantém controle de versão independente.

---

## Qual store cada agente recebe por session

| Agent | `project-knowledge` | `active-sprint` | `agent-prompts` |
|-------|--------------------|-----------------|--------------------|
| Planner | ✅ read-only | ✅ read-write | ✅ read-only |
| Generator | ✅ read-only | ✅ read-write | ✅ read-only |
| Evaluator | ✅ read-only | ✅ read-write | ✅ read-only |

Todos os agents recebem todos os três stores. A diferença é o acesso:
`project-knowledge` e `agent-prompts` são sempre read-only — nenhum
agente pode alterar ADRs ou os próprios prompts durante uma session.
`active-sprint` é read-write para todos porque cada agente escreve
seus próprios artefatos nele.

---

## O que NÃO vai para nenhum store

| Arquivo | Motivo |
|---------|--------|
| `infra/docker-compose.dev.yml` | Configuração de ambiente físico — irrelevante para agentes de código |
| `infra/grafana/` | Configuração de infraestrutura — não influencia geração de código |
| `infra/init-db.sql` | O Generator escreve migrations; não precisa do SQL de init |
| `scripts/setup.sh` | Script de setup do macmini-lablz — não relevante no container |
| `scripts/deploy.sh` | Script de deploy — não relevante para geração de código |
| `scripts/health-check.sh` | Script de saúde da infra local — não relevante no container |
| `scripts/health_check.py` | Idem |
| `README.md` | Documentação para humanos — coberto pelo `AGENTS.md` |
| `output/` (código gerado) | O código vive no filesystem do container, não nos stores |
| `prompts/` (no repo) | Cobertos pelo store `agent-prompts` |

---

## Quando atualizar `project-knowledge`

Atualizações são feitas por você via script, não automaticamente pelos agentes.
Os agentes têm acesso read-only — eles não podem modificar o conhecimento
do projeto por conta própria.

| Gatilho | O que atualizar no store |
|---------|--------------------------|
| Novo ADR aprovado | `/adrs/DXXX.md` + `/adrs/index.md` |
| Sprint concluído | `/sprint-history/sprint-N.md` |
| Stack atualizada | `/design.md` |
| Nova regra de segurança | `/security.md` |
| Novo domínio na arquitetura | `/architecture.md` |
| Nova variável de ambiente | `/env-example.md` |

**Frequência esperada:** a cada sprint concluído (sprint-history) +
ad-hoc quando ADRs são aprovados.

---

## Script de inicialização dos stores

Ver `scripts/init-memory-stores.py` (criado no Passo 3 do onboarding
da Fase 2). O script:
1. Cria os três stores via API
2. Faz upload de todos os documentos listados acima
3. Retorna os IDs dos stores para configuração do `run_sprint.py`

---

## Consequências desta decisão

**Fica mais fácil:**
- Controle de versão do conhecimento do projeto — cada ADR tem seu arquivo
- Custo de tokens por session — agentes carregam só o relevante
- Auditoria — cada sprint tem seu store arquivado com todo o histórico
- Evolução dos prompts — store `agent-prompts` tem ciclo de vida independente

**Fica mais difícil:**
- Manter stores sincronizados com o repo — requer disciplina de atualizar
  o store sempre que um documento relevante muda no repo
- Onboarding — um colaborador novo precisa entender dois sistemas
  (repo + stores) em vez de apenas o repo

**Risco aceito:**
Store desatualizado em relação ao repo. Mitigação: o script
`scripts/init-memory-stores.py` tem modo `--sync` que compara
hashes dos documentos e atualiza apenas o que mudou.
