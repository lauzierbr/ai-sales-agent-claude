# Protocolo de Homologação — AI Sales Agent

Documento de referência para sessões de homologação ao final de cada sprint.

---

## O que é a homologação

A homologação é a validação **pelo dono do produto** (Lauzier) das funcionalidades implementadas no sprint, usando dados e canais reais — não mocks. Ela ocorre obrigatoriamente após o `APROVADO` do Evaluator e antes de iniciar o próximo sprint.

**Distinção clara:**

| | Avaliação do Evaluator | Homologação do usuário |
|---|---|---|
| Executa | Claude (automático) | Lauzier (manual) |
| Ambiente | Local, testes unitários | Staging, WhatsApp real |
| Dados | Mocks e fixtures | Banco real, Evolution API real |
| Foco | Corretude do código | Experiência de uso real |

---

## Regra obrigatória

> **Nenhum sprint avança para o seguinte sem APROVADO na homologação.**

Se a homologação revelar bugs:
- Bugs críticos (fluxo quebrado) → hotfix antes de iniciar próximo sprint
- Bugs menores (UX, texto) → registrar em `docs/exec-plans/tech-debt-tracker.md` e seguir

---

## Fluxo da homologação

```
1. Evaluator emite APROVADO + artifacts/qa_sprint_N.md
2. Generator executa:
   a. ./scripts/deploy.sh staging  (deploy do código novo)
   b. python scripts/seed_homologacao_sprint-N.py  (dados reais de teste)
   c. Gera docs/exec-plans/active/homologacao_sprint-N.md  (checklist)
3. Lauzier executa o checklist manualmente no staging
4. Lauzier registra resultado no arquivo homologacao_sprint-N.md:
   - APROVADO → move para completed/, inicia Sprint N+1
   - REPROVADO → lista os bugs, Generator corrige, nova homologação
```

---

## Ambiente de staging

| Recurso | Valor |
|---------|-------|
| Host | macmini-lablz (Tailscale: 100.113.28.85) |
| SSH | `ssh macmini-lablz` |
| API | http://100.113.28.85:8000 |
| Swagger | http://100.113.28.85:8000/docs |
| Logs | `ssh macmini-lablz 'tail -f ~/ai-sales-agent-claude/logs/app.log'` |
| Evolution API | http://100.113.28.85:8080 |
| Grafana | http://100.113.28.85:3001 |

**Deploy:**
```bash
./scripts/deploy.sh staging
```

---

## Números WhatsApp reais (JMB)

| Papel | Número | E.164 |
|-------|--------|-------|
| Bot JMB (instância Evolution) | (19) 99146-3559 | `5519991463559` |
| Cliente B2B — José LZ Muzel | (19) 99206-6177 | `5519992066177` |

---

## Seed por sprint

Cada sprint com funcionalidades de agente requer um script de seed para garantir
que os dados necessários existem no banco de staging antes da homologação.

| Sprint | Script | O que faz |
|--------|--------|-----------|
| Sprint 2 | `scripts/seed_homologacao_sprint2.py` | Insere José como `clientes_b2b`; verifica instância bot |
| Sprint 3 | `scripts/seed_homologacao_sprint3.py` | A definir (representante) |

---

## Template do checklist de homologação

Cada homologação tem seu arquivo em `docs/exec-plans/active/homologacao_sprint-N.md`.
O Generator cria esse arquivo antes de entregar o ambiente.

Estrutura:
```markdown
# Homologação Sprint N — [Nome]
**Status:** PENDENTE / APROVADO / REPROVADO
**Data:** YYYY-MM-DD
**Executado por:** Lauzier

## Pré-condições
- [ ] deploy.sh concluído com sucesso
- [ ] seed executado sem erros
- [ ] health check retorna 200

## Cenários de teste
### C1 — [Nome do cenário]
**Ação:** ...
**Esperado:** ...
**Resultado:** ✅ OK / ❌ BUG: [descrição]

## Resultado final
**Veredicto:** APROVADO / REPROVADO
**Bugs encontrados:** ...
**Próximo passo:** ...
```
