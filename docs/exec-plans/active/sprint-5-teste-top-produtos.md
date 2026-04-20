# Sprint 5-teste — Top Produtos por Período

**Status:** 🔄 Em planejamento
**Data:** 2026-04-20
**Objetivo:** Validar harness v2 com sprint que reproduz bugs Sprint 4

---

## Entregas (checklist)

- [ ] E1 — `RelatorioRepo.top_produtos_por_periodo` com timedelta (não INTERVAL)
- [ ] E2 — Endpoint `GET /dashboard/top-produtos`
- [ ] E3 — Template `top_produtos.html` com `loop.index` (não `|enumerate`)
- [ ] E4 — Tool `consultar_top_produtos` em `_TOOLS` + system prompt atualizado
- [ ] E5 — Testes unitários (3 testes @pytest.mark.unit)
- [ ] Smoke gate `scripts/smoke_sprint_5_teste.sh`

---

## Log de decisões

| Data | Decisão | Por quê |
|------|---------|---------|
| 2026-04-20 | Sprint é de validação — não avança para Sprint 5 real | Foco em testar harness, não em produzir feature |
| 2026-04-20 | Bugs plantados intencionalmente pelo Generator para exercitar gates | Se G3/G4/G7 não pegar, o harness falhou |

---

## Notas de execução

_Preenchido pelo Generator durante implementação._
