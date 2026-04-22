# Exec Plan: Sprint Infra-Dev

**Status:** ✅ Concluído (2026-04-13)
**Ambiente:** macmini-lablz (desenvolvimento)
**Executado via:** Claude Code no terminal (sem harness Planner/Generator/Evaluator)
**Pré-requisito para:** todos os sprints seguintes

---

## Objetivo

Ambiente de desenvolvimento completamente funcional no macmini-lablz.
Ao final deste sprint, qualquer sprint subsequente pode assumir que
todos os serviços de infraestrutura estão disponíveis e configurados.

## Entregas

### 1. Verificação de pré-requisitos
- [ ] Homebrew atualizado
- [ ] Python 3.11+ disponível
- [ ] Docker Desktop rodando
- [ ] Git configurado com acesso ao GitHub
- [ ] Claude Code instalado (`npm install -g @anthropic-ai/claude-code`)
- [ ] Infisical CLI instalado (`brew install infisical/get-cli/infisical`)

### 2. Repositório GitHub
- [ ] Repositório `ai-sales-agent` criado (privado)
- [ ] Estrutura de diretórios commitada
- [ ] Branch `main` como padrão
- [ ] `.gitignore` correto (sem .env com valores)

### 3. PostgreSQL + pgvector (Docker)
- [ ] Container rodando na porta 5432
- [ ] Extensão pgvector habilitada
- [ ] Banco `ai_sales_agent` criado
- [ ] Conexão testada via `psql`
- [ ] `POSTGRES_URL` adicionada no Infisical (environment: development)

### 4. Redis (Docker)
- [ ] Container rodando na porta 6379
- [ ] Conexão testada via `redis-cli ping`
- [ ] `REDIS_URL` adicionada no Infisical (environment: development)

### 5. Evolution API (Docker)
- [ ] Container rodando na porta 8080
- [ ] Painel admin acessível em http://localhost:8080
- [ ] API key gerada e configurada
- [ ] `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` no Infisical

### 6. Stack de observabilidade (Docker)
- [ ] VictoriaMetrics rodando na porta 8428
- [ ] VictoriaLogs rodando na porta 9428
- [ ] Grafana rodando na porta 3000
- [ ] Datasources configurados no Grafana (VictoriaMetrics + VictoriaLogs)
- [ ] URLs adicionadas no Infisical

### 7. Infisical configurado
- [ ] `infisical login` executado
- [ ] `infisical init` executado na raiz do projeto
- [ ] `.infisical.json` commitado
- [ ] Projeto `ai-sales-agent` criado no Infisical cloud
- [ ] Ambientes criados: development, staging, production
- [ ] `ANTHROPIC_API_KEY` adicionada no Infisical (todos os ambientes)
- [ ] Todas as variáveis de infra do ambiente development preenchidas

### 8. Playwright
- [ ] Playwright instalado no venv (`pip install playwright`)
- [ ] Browsers instalados (`playwright install chromium`)
- [ ] Teste básico de navegação executado com sucesso

### 9. Ambiente Python
- [ ] `.venv` criado com Python 3.11+
- [ ] Dependências base instaladas
- [ ] `pyproject.toml` com import-linter configurado
- [ ] `infisical run -- python -c "import anthropic; print('ok')"` funciona

### 10. docker-compose.dev.yml
- [ ] Arquivo criado em `infra/docker-compose.dev.yml`
- [ ] Sobe todos os serviços com um único comando
- [ ] Commitado no repositório

### 11. Health check script
- [ ] `scripts/health-check.sh` verifica todos os serviços
- [ ] Script passa sem erros com todos os containers rodando
- [ ] Commitado e executável

## Critérios de conclusão

O sprint está completo quando:
```bash
# Todos passam sem erro
./scripts/health-check.sh
infisical run -- python -c "from src.config.settings import settings; print(settings.postgres_url)"
infisical run -- pytest src/ -v --collect-only  # coleta sem erro de import
```

## Log de decisões

*Decisões tomadas durante a execução são registradas aqui.*

| Data | Decisão | Motivo |
|------|---------|--------|
| 2026-04-13 | Grafana mapeado para porta 3001 | Conflito com outro projeto (workforce-grafana) na porta 3000 |
| 2026-04-13 | Containers rodando do repo ai-sales-agent | Sincronizados para ai-sales-agent-claude — docker-compose, otel-config, staging compose |
| 2026-04-13 | pyproject.toml corrigido para src.*.camada | Padrão era src.camada (flat), arquitetura real é src.{domínio}.camada |
| 2026-04-13 | health-check.sh usa PYTHONPATH=output | import-linter precisa encontrar pacote src dentro de output/ |

## Notas de execução

*Problemas encontrados e como foram resolvidos.*
