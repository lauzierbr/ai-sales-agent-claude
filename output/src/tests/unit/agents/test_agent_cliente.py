"""Testes unitários de agents/runtime/agent_cliente.py — AgentCliente.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.types import Mensagem
from src.tenants.types import Tenant


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def tenant_jmb() -> Tenant:
    return Tenant(
        id="jmb",
        nome="JMB Distribuidora",
        cnpj="00.000.000/0001-00",
        ativo=True,
        whatsapp_number="5519999990000",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mensagem_cliente() -> Mensagem:
    return Mensagem(
        id="msg1",
        de="5519999999999@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Quero ver o catálogo",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
    )


# ─────────────────────────────────────────────
# AgentCliente
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_chama_send_whatsapp(
    mensagem_cliente: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentCliente.responder chama send_whatsapp_message exatamente uma vez."""
    from src.agents.runtime.agent_cliente import AgentCliente

    session = AsyncMock()

    with patch(
        "src.agents.runtime.agent_cliente.send_whatsapp_message",
        new=AsyncMock(),
    ) as mock_send:
        await AgentCliente().responder(mensagem_cliente, tenant_jmb, session)

    mock_send.assert_called_once()


@pytest.mark.unit
async def test_agent_cliente_usa_instancia_correta(
    mensagem_cliente: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentCliente.responder usa instancia_id da mensagem no envio."""
    from src.agents.runtime.agent_cliente import AgentCliente

    session = AsyncMock()
    chamadas = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        chamadas.append((instancia_id, numero, texto))

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=mock_send):
        await AgentCliente().responder(mensagem_cliente, tenant_jmb, session)

    assert len(chamadas) == 1
    instancia_usada, numero_usado, _ = chamadas[0]
    assert instancia_usada == "inst-jmb-01"
    assert numero_usado == "5519999999999"  # strip @s.whatsapp.net


@pytest.mark.unit
async def test_agent_cliente_template_contem_tenant_nome(
    mensagem_cliente: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentCliente.responder inclui nome do tenant no template."""
    from src.agents.runtime.agent_cliente import AgentCliente

    session = AsyncMock()
    textos_enviados = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        textos_enviados.append(texto)

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=mock_send):
        await AgentCliente().responder(mensagem_cliente, tenant_jmb, session)

    assert len(textos_enviados) == 1
    assert "JMB Distribuidora" in textos_enviados[0]
