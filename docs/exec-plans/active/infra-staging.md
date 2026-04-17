# Exec Plan: Sprint Infra-Staging

**Status:** ✅ Concluído (2026-04-13)
**Ambiente:** macmini-lablz (staging)
**Executado via:** Claude Code com SSH ao macmini-lablz
**Pré-requisito para:** Sprint 0 em diante em staging

---

## Objetivo

macmini-lablz com infraestrutura espelhando o development do mac-lablz.
Deploy funcional via `scripts/deploy.sh`. Serviços com auto-start via launchd.

## Pré-condições

- Sprint Infra-Dev concluído no mac-lablz
- SSH configurado: `ssh macmini-lablz` funciona sem senha
- macmini-lablz com macOS e acesso à internet

## Entregas

### 1. SSH e acesso remoto
- [ ] Chave SSH do mac-lablz copiada para macmini-lablz
- [ ] `ssh macmini-lablz` funciona sem senha
- [ ] `ssh macmini-lablz "hostname"` retorna correto

### 2. Pré-requisitos no mac-mini
- [ ] Homebrew instalado
- [ ] Python 3.11+ instalado
- [ ] Docker Desktop instalado e rodando
- [ ] Git configurado
- [ ] Claude Code instalado
- [ ] Infisical CLI instalado

### 3. Repositório clonado
- [ ] `git clone` do repositório GitHub no mac-mini
- [ ] `infisical login` executado no mac-mini
- [ ] `infisical init` executado — ambiente `staging` selecionado
- [ ] Variáveis do ambiente staging preenchidas no Infisical

### 4. Serviços Docker (staging)
- [ ] PostgreSQL + pgvector rodando (porta 5432)
- [ ] Redis rodando (porta 6379)
- [ ] Evolution API rodando (porta 8080)
- [ ] VictoriaMetrics, VictoriaLogs, Grafana rodando
- [ ] `infra/docker-compose.staging.yml` criado e commitado
- [ ] Health check passando no mac-mini

### 5. Auto-start via launchd (macOS)
- [ ] plist para PostgreSQL em `~/Library/LaunchAgents/`
- [ ] plist para Redis em `~/Library/LaunchAgents/`
- [ ] plist para Evolution API em `~/Library/LaunchAgents/`
- [ ] Serviços sobem automaticamente após reboot
- [ ] `launchctl list | grep ai-sales` mostra todos ativos

### 6. Deploy script funcional
- [ ] `scripts/deploy.sh` executa sem erro a partir do mac-lablz
- [ ] `git pull` + restart de serviços funcionam
- [ ] Log do deploy acessível

### 7. Playwright no mac-mini
- [ ] Playwright + chromium instalados
- [ ] Teste básico de navegação funciona

## Critérios de conclusão

A partir do mac-lablz:
```bash
# Deploy funciona
./scripts/deploy.sh

# Health check remoto
ssh macmini-lablz "cd ~/ai-sales-agent && ./scripts/health-check.sh"

# Infisical staging
ssh macmini-lablz "cd ~/ai-sales-agent && infisical run --env=staging -- python -c 'print(\"ok\")'"
```

## Log de decisões

| Data | Decisão | Motivo |
|------|---------|--------|
| — | — | — |
