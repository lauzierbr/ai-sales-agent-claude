# Product Spec — AgentGestor (Persona Gestor/Admin)

**Status:** Backlog — Sprint 4
**Autor:** Lauzier (2026-04-17)
**Contexto:** Terceiro perfil do sistema após CLIENTE_B2B e REPRESENTANTE.

---

## Problema

O gestor/dono da distribuidora hoje não consegue interagir com o bot WhatsApp.
Para acompanhar vendas, precisa acessar o banco diretamente ou esperar um painel
web. A homologação do Sprint 3 revelou que o gestor também precisa de:

- Visão consolidada de todos os pedidos e clientes sem filtro de carteira
- Capacidade de fechar pedidos em nome de qualquer cliente (não só os da carteira
  de um rep específico)
- Relatórios de performance por representante e por cliente

---

## Quem é o gestor

O gestor é o **dono ou gerente da distribuidora** — no caso JMB, o próprio Lauzier.
Ele conhece todos os clientes, todos os representantes e precisa de visão 360°.

Diferença dos outros perfis:

| Capacidade | Cliente B2B | Representante | Gestor |
|------------|-------------|---------------|--------|
| Consultar catálogo | ✅ (próprio pedido) | ✅ | ✅ |
| Fazer pedido | ✅ (para si) | ✅ (carteira) | ✅ (qualquer cliente) |
| Ver clientes | ❌ | ✅ (só carteira) | ✅ (todos) |
| Ver pedidos | ❌ | ✅ (próprios) | ✅ (todos) |
| Ver relatório de vendas | ❌ | ❌ | ✅ |
| Ver performance por rep | ❌ | ❌ | ✅ |
| Ver totais da empresa | ❌ | ❌ | ✅ |

---

## Comportamento esperado via WhatsApp

### Consultar clientes
```
Gestor: "quem são os clientes da Ana?"
Bot: Lista clientes com representante_id = Ana, com nome + CNPJ + último pedido

Gestor: "busca cliente Farmácia Central"
Bot: Retorna todos os clientes com "farmácia central" no nome, de qualquer rep
```

### Fazer pedido por qualquer cliente
```
Gestor: "quero fechar 10 shampoo anticaspa pro cliente Muzel"
Bot: Confirma produto + cliente + valor total, sem validar carteira do rep
     Pedido criado com representante_id = NULL (ou rep do cliente se tiver)
     PDF enviado normalmente para tenant.whatsapp_number
```

### Relatórios de vendas
```
Gestor: "quanto vendeu essa semana?"
Bot: Total de pedidos (R$) dos últimos 7 dias, número de pedidos, ticket médio

Gestor: "ranking dos representantes esse mês"
Bot: Lista reps ordenada por volume (R$) no mês corrente

Gestor: "quais clientes não compraram no último mês?"
Bot: Lista de clientes sem pedido nos últimos 30 dias (alerta de inatividade)

Gestor: "resumo de vendas do José Muzel"
Bot: Histórico de pedidos do cliente: total gasto, frequência, último pedido
```

### Gestão operacional
```
Gestor: "quais pedidos estão abertos hoje?"
Bot: Lista pedidos do dia com status

Gestor: "cancela o pedido 12345"
Bot: Altera status do pedido para cancelado (a definir — pode exigir confirmação)
```

---

## Impacto técnico (para o Planner)

### Novo: tabela `gestores`
Similar à tabela `representantes`:
```sql
CREATE TABLE gestores (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    telefone    TEXT NOT NULL,
    nome        TEXT NOT NULL,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, telefone)
);
```

### Camadas impactadas
- **Types**: novo `Persona.GESTOR`, novo dataclass `Gestor`
- **Repo**: `GestorRepo.get_by_telefone()`, novo `RelatorioRepo` (queries de vendas)
- **Config**: `AgentGestorConfig` com system prompt e ferramentas
- **Runtime**: `AgentGestor` com ferramentas:
  - `buscar_clientes` (todos, sem filtro de rep)
  - `buscar_produtos` (igual ao rep)
  - `confirmar_pedido_em_nome_de` (qualquer cliente, sem validação de carteira)
  - `relatorio_vendas` (período, por rep, por cliente)
  - `clientes_inativos` (sem pedido nos últimos N dias)
- **Service/IdentityRouter**: lookup em `gestores` antes de `representantes`
- **UI**: wiring do `AgentGestor`

### Hierarquia de prioridade no IdentityRouter (nova)
```
gestores → representantes → clientes_b2b → DESCONHECIDO
```

### Queries de relatório (notas para o Planner)
- Todas as queries precisam de `tenant_id` como filtro obrigatório (isolamento)
- Agregações por período: usar `DATE_TRUNC` no PostgreSQL
- Ranking de reps: JOIN `representantes` + SUM de `pedidos.total`
- Clientes inativos: LEFT JOIN `pedidos` + WHERE pedidos.criado_em < NOW() - INTERVAL

---

## Critérios de aceitação mínimos (homologação)

1. Gestor busca cliente por nome → retorna clientes de qualquer rep
2. Gestor faz pedido para cliente fora da carteira de qualquer rep → pedido criado
3. Gestor pede "resumo da semana" → recebe total R$, nº pedidos, ticket médio
4. Gestor pede "ranking dos reps esse mês" → lista ordenada por volume
5. Gestor pede "clientes inativos" → lista com clientes sem pedido há 30+ dias
6. Cliente B2B envia mensagem → não é confundido com gestor
7. Representante envia mensagem → não é confundido com gestor

---

## Fora do escopo deste spec (Sprint 4)

- Interface web (dashboard) — pode ser Sprint 5 se escopo estourar
- Autenticação por senha ou 2FA — WhatsApp já autentica pelo número
- Criação/edição de clientes via WhatsApp — operação de cadastro fica para painel web
- Configuração de tenants via WhatsApp
