"""Provider de telemetria — OpenTelemetry setup.

Configura TracerProvider apontando para o OTEL Collector (localhost:4317).
Importado pelo main.py na inicialização da aplicação.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_telemetry(service_name: str = "ai-sales-agent") -> None:
    """Configura OpenTelemetry com exportador OTLP gRPC.

    Args:
        service_name: nome do serviço para identificação nas traces.
    """
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    """Retorna tracer para uso nos serviços.

    Args:
        name: identificador do módulo (use __name__).

    Returns:
        Tracer configurado.
    """
    return trace.get_tracer(name)
