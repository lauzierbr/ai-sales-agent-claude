# Frontend — AI Sales Agent

## Superfícies de UI

### 1. Painel do Gestor (web)
Interface administrativa para o tenant. Não é público — requer autenticação.

**Stack:** FastAPI (backend) + HTML/CSS/JS simples ou Streamlit para MVP.
Migrar para React/Next.js quando o produto estiver validado.

**Páginas:**
- Dashboard: pedidos em tempo real, clientes ativos, alertas
- Catálogo: lista de produtos, revisão de enriquecimento, upload de preços
- Representantes: carteira, metas, performance
- Clientes: cadastro, limite de crédito, histórico
- Configurações: tom do agente, promoções ativas, webhook WhatsApp
- Observabilidade: link direto para Grafana do tenant

### 2. WhatsApp (canal de conversa)
Não é UI web — é o canal principal de interação de reps e clientes.
Renderização é texto formatado (negrito com *, listas com -).
Sem markdown avançado — WhatsApp tem suporte limitado.

## Princípios de design

- **Funcional antes de bonito** — MVP foca em funcionalidade
- **Dados em tempo real** — pedidos e conversas sem refresh manual
- **Mobile-first para o painel** — gestores acessam pelo celular
- **Acessível para o agente** — Evaluator pode navegar o painel via
  Playwright para validar comportamento em testes de integração

## Observabilidade no frontend

O Grafana é exposto na porta 3000 (development) e acessível pelo gestor.
Dashboards pré-configurados por tenant são criados no Sprint de Infra.
