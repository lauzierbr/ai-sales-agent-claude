# Security — AI Sales Agent

## Princípios

1. **Zero secrets no código** — Infisical em todos os ambientes
2. **Isolamento total entre tenants** — dado de um tenant jamais acessível por outro
3. **Validação na borda** — parse de dados externos no ponto de entrada (Pydantic)
4. **Princípio do mínimo privilégio** — cada agente acessa apenas o que precisa

## Isolamento de tenant

### PostgreSQL — schema por tenant
```sql
-- Cada tenant tem seu próprio schema
CREATE SCHEMA tenant_jmb;
CREATE SCHEMA tenant_distribuidora_x;

-- Tabelas existem dentro do schema
CREATE TABLE tenant_jmb.produtos (...);
CREATE TABLE tenant_jmb.clientes (...);
```

### Middleware FastAPI — TenantProvider
```python
# Todo request carrega tenant_id no contexto
# Injetado via header X-Tenant-ID ou via sessão autenticada
# Nenhum endpoint funciona sem tenant_id válido
```

### Regra de lint — tenant_id obrigatório em queries
```
ERRO: Query em repo.py sem filtro de tenant_id
REMEDIAÇÃO: Adicione WHERE tenant_id = :tenant_id em toda query
```

## Validação de dados externos

Parse obrigatório em todos os pontos de entrada:
- Webhook WhatsApp (Evolution API) → Pydantic model
- Upload Excel de preços → validação linha a linha com erros explícitos
- Resposta do crawler → ProdutoBruto com validação
- Chamadas à Loja Integrada API → schema validado

Nunca acessar `dict["key"]` sem validação prévia de schema.

## Secrets — regras

| Permitido | Proibido |
|-----------|----------|
| `os.getenv("CHAVE")` | `API_KEY = "sk-ant-..."` |
| `infisical run -- comando` | `.env` com valores reais commitado |
| `settings.anthropic_api_key` (pydantic-settings) | Variável em qualquer arquivo Python |

Violação de secret hardcoded é **sempre bloqueante** no Evaluator.

## Segurança do agente

- O Evaluator verifica explicitamente se respostas do agente contêm
  dados de outros tenants antes de aprovar
- Prompts dos agentes incluem instrução explícita de não vazar
  informações entre tenants
- Logs de conversa são isolados por tenant no VictoriaLogs

## Acesso ao painel do gestor

- Autenticação obrigatória (JWT com tenant_id no payload)
- HTTPS obrigatório em staging e produção
- Rate limiting por tenant via Redis

## Evolution API (WhatsApp)

- Evolution API roda na rede interna apenas (não exposta diretamente)
- Webhook recebe apenas de IP da Evolution API local
- Número WhatsApp dedicado por tenant
