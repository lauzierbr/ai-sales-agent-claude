# Homologação Sprint 3 — AgentRep + Hardening de Linguagem Brasileira

**Status:** Aguardando homologação humana
**Data:** 2026-04-16
**QA:** APROVADO pelo Evaluator — `artifacts/qa_sprint_3.md`

---

## Pré-requisitos antes de iniciar

```bash
# 1. Atualizar o banco com a migration 0013
infisical run --env=staging -- alembic upgrade head

# 2. Rodar seed do representante de teste
infisical run --env=staging -- python scripts/seed_homologacao_sprint-3.py

# 3. Confirmar serviços ativos
infisical run --env=staging -- python scripts/health_check.py

# 4. Reiniciar uvicorn para carregar novo código
infisical run --env=staging -- uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Representante de teste

- **Nome:** Rep Teste Sprint3
- **Telefone:** +55 19 00000-0001 (formato WhatsApp: 5519000000001)
- **Cliente vinculado:** José LZ Muzel (5519992066177)
- **Tenant:** jmb

> Para homologar o AgentRep, envie mensagens do WhatsApp a partir de um número
> cadastrado como representante na tabela `representantes`.
> O número +55 19 00000-0001 é fictício — use um número real adicionado via seed
> ou via SQL direto antes de iniciar.

---

## Checklist de cenários

### Cenário 1 — Rep consulta produto por nome informal
- [ ] Enviar: `"oi, tem heineken?"` pelo WhatsApp do representante
- [ ] Esperado: agente responde com produtos encontrados no catálogo
- [ ] Verificar: conversa persistida na tabela `conversas` com `persona = 'representante'`

### Cenário 2 — Rep busca cliente da carteira pelo nome
- [ ] Enviar: `"quero ver os clientes com muzel"`
- [ ] Esperado: agente retorna nome + CNPJ de José LZ Muzel
- [ ] Verificar: agente NÃO retorna clientes de outro representante

### Cenário 3 — Rep cria pedido em nome de cliente da carteira
- [ ] Enviar: `"quero fechar 5 shampoo 300ml pro José Muzel"`
- [ ] Esperado: agente busca produto, confirma cliente, fecha pedido
- [ ] Verificar: PDF recebido no WhatsApp do gestor (tenant.whatsapp_number)
- [ ] Verificar: pedido na tabela `pedidos` com `representante_id` preenchido

### Cenário 4 — Rep tenta criar pedido para cliente FORA da carteira
- [ ] Configurar: criar cliente sem `representante_id` vinculado
- [ ] Enviar: `"fecha pra Farmácia do Zé"` passando ID de cliente sem rep
- [ ] Esperado: agente responde com mensagem de erro clara ("Cliente não encontrado na sua carteira")
- [ ] Verificar: NENHUM pedido criado na tabela `pedidos`

### Cenário 5 — AgentCliente: confirmação coloquial
- [ ] Enviar pelo WhatsApp do CLIENTE: `"quero 3 heineken long neck"`
- [ ] Agente mostra produtos
- [ ] Enviar: `"fecha aí"`
- [ ] Esperado: pedido criado, PDF enviado para gestor

### Cenário 6 — AgentCliente: cancelamento coloquial
- [ ] Enviar pelo WhatsApp do CLIENTE: `"quero 2 nescau 400g"`
- [ ] Agente mostra produtos
- [ ] Enviar: `"não, deixa"`
- [ ] Esperado: agente confirma cancelamento, NENHUM pedido criado

### Cenário 7 — AgentCliente: abreviação de quantidade
- [ ] Enviar: `"manda 5 cx de shampoo"`
- [ ] Esperado: agente interpreta cx=caixa, quantidade=5, busca shampoo
- [ ] Verificar: pedido com quantidade 5 se cliente confirmar

### Cenário 8 — AgentCliente: saudação simples
- [ ] Enviar: `"oi"`
- [ ] Esperado: saudação de boas-vindas SEM buscar produtos no catálogo
- [ ] Verificar: mensagem amigável convidando a consultar produtos

---

## Resultado da homologação

**Data:**
**Executado por:**

- [ ] APROVADO — todos os 8 cenários passaram
- [ ] REPROVADO — bugs listados abaixo

### Bugs encontrados (se houver)

| Cenário | Descrição | Severidade |
|---------|-----------|-----------|
| | | |

---

## Pós-aprovação

Quando APROVADO:
1. Mover este arquivo para `docs/exec-plans/completed/`
2. Criar tag `v0.4.0` no git
3. Atualizar memória do projeto com estado para Sprint 4
