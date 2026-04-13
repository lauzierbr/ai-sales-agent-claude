# Product Sense — AI Sales Agent

## O que é este produto

Plataforma SaaS de agente de vendas B2B via WhatsApp para pequenas
distribuidoras e fabricantes brasileiras.

O agente substitui (ou aumenta) o processo manual de vendas B2B:
ligações, WhatsApp informal, planilhas de pedido, follow-up de clientes
inativos. Torna esse processo autônomo, escalável e disponível 24/7.

## Para quem

**Distribuidoras e fabricantes pequenas** (10-200 SKUs, 50-500 clientes B2B)
que vendem para varejistas: farmácias, mercados, salões, lojas de conveniência.

Características típicas do segmento:
- Processo de vendas B2B depende de representantes externos
- Clientes fazem pedidos por WhatsApp pessoal dos reps
- Sem sistema de CRM — relacionamento vive na memória dos reps
- Catálogo atualizado por planilha ou ERP sem API pública
- Preços diferenciados por cliente, negociados informalmente

## Três personas de usuário

### Representante
Usa o próprio WhatsApp. Consulta catálogo, verifica estoque, registra
pedido em nome de cliente da sua carteira. Recebe alertas de clientes
inativos. Vê metas e comissão estimada.

### Cliente B2B (farmácia, mercado, salão)
Usa WhatsApp dedicado da distribuidora. Faz pedidos, consulta status,
recebe sugestões baseadas no histórico de compras.

### Gestor (dono da distribuidora / gerente)
Usa painel web. Vê tudo em tempo real: pedidos, conversas ativas,
performance dos reps, clientes inativos. Configura o agente, carrega
tabelas de preço, define promoções.

## Cliente piloto

**JMB Distribuidora** — Vinhedo-SP, fundada 2024.
Produtos: beleza, higiene, bebê. ~450 SKUs. Sites:
- B2B (EFOS): https://pedido.jmbdistribuidora.com.br
- B2C (Loja Integrada): https://www.jmbdistribuidora.com.br

## Modelo de negócio (plataforma)

```
Lauzier (SaaS / consultoria)
    └── ai-sales-agent (plataforma)
            ├── JMB Distribuidora   ← tenant piloto
            ├── Distribuidora X     ← futuro
            └── Fabricante Y        ← futuro
```

Cada tenant paga mensalidade pela plataforma + consumo de tokens Claude.

## Métricas de sucesso

- Pedidos registrados via agente / total de pedidos do tenant
- Tempo médio de resposta ao cliente (meta: < 3s para 95% das msgs)
- Clientes ativos contactados proativamente / total da carteira
- NPS do gestor (facilidade de configuração e visibilidade)
