# Sprint 5-teste — Top Produtos por Período

**Status:** ✅ APROVADO — harness v2 validado
**Data início:** 2026-04-20
**Data conclusão:** 2026-04-20
**Objetivo:** Validar harness v2 com sprint que reproduz bugs Sprint 4

---

## Entregas (checklist)

- [x] E1 — `RelatorioRepo.top_produtos_por_periodo` com timedelta (não INTERVAL)
- [x] E2 — Endpoint `GET /dashboard/top-produtos`
- [x] E3 — Template `top_produtos.html` com `loop.index` (não `|enumerate`)
- [x] E4 — Tool `consultar_top_produtos` em `_TOOLS` + system prompt atualizado
- [x] E5 — Testes unitários (3 testes @pytest.mark.unit)
- [x] Smoke gate `scripts/smoke_sprint_5_teste.sh`

---

## Log de decisões

| Data | Decisão | Por quê |
|------|---------|---------|
| 2026-04-20 | Sprint é de validação — não avança para Sprint 5 real | Foco em testar harness, não em produzir feature |
| 2026-04-20 | Bugs plantados intencionalmente pelo Generator para exercitar gates | Se G3/G4/G7 não pegar, o harness falhou |

---

## Resultado — Evaluator R0/R1/R2/R3

| Rodada | Veredicto | Detalhe |
|--------|-----------|---------|
| R0 | REPROVADO (esperado) | Bugs plantados detectados, veredicto registrado em artifacts/ |
| R1 | REPROVADO | 4 bugs + débitos identificados mecanicamente por arquivo:linha |
| R2 | REPROVADO | Idem R1 — gates confirmaram os mesmos 4 bugs |
| R3 | APROVADO | 4 bugs corrigidos, gates mecânicos verdes, débitos harness sanados |

Harness v2 validado: G2, G3, G5, G7 detectaram os 4 bugs sem inspeção
humana. Débitos harness corrigidos: smoke sai com exit 1 em falha;
check_gotchas exclui test/ por default.

## Notas de execução

Sprint de validação — não avança para produção. O Sprint 5 real pode
começar com o harness v2 confiável.
