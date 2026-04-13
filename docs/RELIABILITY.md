# Reliability & Observabilidade — AI Sales Agent

## Stack de observabilidade

```
Aplicação (FastAPI + Agentes Claude)
    │
    │  OpenTelemetry SDK
    ↓
OTEL Collector
    ├── traces  → VictoriaMetrics (via OTLP)
    ├── metrics → VictoriaMetrics (via OTLP)
    └── logs    → VictoriaLogs   (via OTLP)
                        │
                    Grafana (visualização)
                    PromQL + LogQL queries
```

### Por que VictoriaMetrics + VictoriaLogs

- **Single binary** — sem Zookeeper, sem cluster, sem dor operacional
- **Compatível com PromQL** — métricas consultáveis com PromQL standard
- **VictoriaLogs compatível com LogQL** — logs com a mesma API do Loki/Grafana
- **Extremamente leve** — roda confortavelmente no mac-mini-lablz
- **Migração para cloud transparente** — mesma API, apenas muda o endpoint

### Agentes consultam observabilidade diretamente

O Evaluator e o Generator têm acesso a PromQL e LogQL via MCP.
Isso permite prompts como:

```
"Garanta que o tempo de resposta do AgentCliente está abaixo de 3s
 para 95% das mensagens no último dia"

"Verifique se houve erros 5xx nos endpoints de webhook nas últimas 2h"

"Confirme que o crawler do tenant JMB completou sem erros hoje"
```

## Instrumentação obrigatória

### Toda função de Service deve ter span OTel
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def resolve_preco(tenant_id: str, cliente_id: str, produto_id: str) -> float:
    with tracer.start_as_current_span("resolve_preco") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("produto_id", produto_id)
        # ...
```

### Logging estruturado obrigatório (structlog)
```python
import structlog
log = structlog.get_logger()

# CORRETO
log.info("pedido_criado", tenant_id=tenant_id, pedido_id=pedido_id, valor=total)

# ERRADO — nunca usar print() ou logging.info()
print(f"Pedido criado: {pedido_id}")
```

### Métricas críticas

#### Por tenant
```
agent_response_latency_seconds{tenant_id, persona}
agent_tokens_consumed_total{tenant_id, model, agent_type}
pedidos_criados_total{tenant_id}
pedidos_valor_brl_total{tenant_id}
whatsapp_mensagens_recebidas_total{tenant_id, persona}
whatsapp_mensagens_enviadas_total{tenant_id, persona}
```

#### Qualidade do agente
```
evaluator_aprovacoes_total{tenant_id, sprint}
evaluator_reprovacoes_total{tenant_id, motivo}
agent_erros_total{tenant_id, agent_type, tipo_erro}
```

#### Crawler
```
crawler_produtos_capturados_total{tenant_id}
crawler_run_duration_seconds{tenant_id}
crawler_erros_total{tenant_id, tipo}
crawler_ultima_execucao_timestamp{tenant_id}
```

#### Infraestrutura
```
postgres_query_duration_seconds{tenant_id, query_type}
redis_operations_total{operation}
evolution_api_requests_total{status}
```

## Alertas recomendados

| Alerta | Condição | Severidade |
|--------|----------|------------|
| Resposta lenta | p95 latência > 5s por 5min | warning |
| Agente falhando | erros > 5% das msgs por 10min | critical |
| Crawler parado | última execução > 25h | warning |
| PostgreSQL lento | query p95 > 2s | warning |
| Tokens disparando | consumo > 2x média dos últimos 7d | warning |

## Configuração docker-compose (observabilidade)

```yaml
# Parte do docker-compose.dev.yml
services:
  victoriametrics:
    image: victoriametrics/victoria-metrics:latest
    ports:
      - "8428:8428"
    volumes:
      - vm_data:/storage

  victorialogs:
    image: victoriametrics/victoria-logs:latest
    ports:
      - "9428:9428"
    volumes:
      - vl_data:/vlogs

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
```

## SLOs por jornada crítica

| Jornada | Latência máxima (p95) | Disponibilidade |
|---------|-----------------------|-----------------|
| Cliente faz pedido via WhatsApp | 5s | 99.5% |
| Rep consulta catálogo | 3s | 99.5% |
| Crawler completa ciclo | 30min | 99% (diário) |
| Painel gestor carrega | 2s | 99% |
