# Sprint 2 — Agente Cliente Completo

**Status:** ✅ APROVADO  
**Data conclusão:** 2026-04-15  
**Versão:** v0.3.0  
**QA report:** `artifacts/qa_sprint_2.md`

---

## Resumo

Sprint 2 implementou o AgentCliente completo com Claude SDK, domínio Orders com captura de pedidos, geração de PDF (fpdf2) e notificação via WhatsApp Evolution API.

## Entregas principais

- `IdentityRouter` real com lookup em `clientes_b2b` e `representantes`
- `AgentCliente` com Claude SDK: tool use, Redis memory, DB persistence, max 5 iterations
- Ferramentas: `buscar_produtos` (catalog) + `confirmar_pedido` (order + PDF + WhatsApp)
- `OrderService.criar_pedido_from_intent` com total calculado em Python
- `PDFGenerator.gerar_pdf_pedido` → bytes (fpdf2 A4 layout)
- `send_whatsapp_media` com base64 + endpoint /message/sendMedia/
- 6 novas migrations (0007–0012): clientes_b2b, representantes, conversas, mensagens_conversa, pedidos, itens_pedido
- 163 testes unitários passando, mypy 0 erros, lint-imports 5/5

## Decisão arquitetural D023

Fluxo de pedido via PDF + WhatsApp sem integração ERP no MVP. Gestor processa manualmente no EFOS.

## Métricas finais

- pytest -m unit: 163 passed
- mypy --strict: 0 errors
- lint-imports: 5/5 KEPT
- agents/service coverage: 93%
- agents/repo coverage: 84%
