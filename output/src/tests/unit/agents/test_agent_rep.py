"""Testes unitários de agents/runtime/agent_rep.py — AgentRep e AgentDesconhecido.

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
def tenant_sem_whatsapp() -> Tenant:
    return Tenant(
        id="outro",
        nome="Outra Distribuidora",
        cnpj="11.111.111/0001-11",
        ativo=True,
        whatsapp_number=None,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mensagem_rep() -> Mensagem:
    return Mensagem(
        id="msg2",
        de="5519888888888@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Quero ver minha carteira",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 14, 11, 0, 0, tzinfo=timezone.utc),
    )


# ─────────────────────────────────────────────
# AgentRep
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_chama_send_whatsapp(
    mensagem_rep: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentRep.responder chama send_whatsapp_message uma vez."""
    from src.agents.runtime.agent_rep import AgentRep

    session = AsyncMock()

    with patch(
        "src.agents.runtime.agent_rep.send_whatsapp_message",
        new=AsyncMock(),
    ) as mock_send:
        await AgentRep().responder(mensagem_rep, tenant_jmb, session)

    mock_send.assert_called_once()


@pytest.mark.unit
async def test_agent_rep_usa_numero_sem_sufixo(
    mensagem_rep: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentRep.responder strip @s.whatsapp.net do número."""
    from src.agents.runtime.agent_rep import AgentRep

    session = AsyncMock()
    chamadas = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        chamadas.append((instancia_id, numero, texto))

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=mock_send):
        await AgentRep().responder(mensagem_rep, tenant_jmb, session)

    assert chamadas[0][1] == "5519888888888"


# ─────────────────────────────────────────────
# AgentDesconhecido
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_desconhecido_chama_send_whatsapp(
    mensagem_rep: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentDesconhecido.responder chama send_whatsapp_message uma vez."""
    from src.agents.runtime.agent_rep import AgentDesconhecido

    session = AsyncMock()

    with patch(
        "src.agents.runtime.agent_rep.send_whatsapp_message",
        new=AsyncMock(),
    ) as mock_send:
        await AgentDesconhecido().responder(mensagem_rep, tenant_jmb, session)

    mock_send.assert_called_once()


@pytest.mark.unit
async def test_agent_desconhecido_usa_whatsapp_number_do_tenant(
    mensagem_rep: Mensagem, tenant_jmb: Tenant
) -> None:
    """AgentDesconhecido inclui whatsapp_number do tenant na mensagem."""
    from src.agents.runtime.agent_rep import AgentDesconhecido

    session = AsyncMock()
    textos_enviados = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        textos_enviados.append(texto)

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=mock_send):
        await AgentDesconhecido().responder(mensagem_rep, tenant_jmb, session)

    assert "5519999990000" in textos_enviados[0]


@pytest.mark.unit
async def test_agent_desconhecido_sem_whatsapp_number_usa_fallback(
    mensagem_rep: Mensagem, tenant_sem_whatsapp: Tenant
) -> None:
    """AgentDesconhecido usa fallback quando tenant não tem whatsapp_number."""
    from src.agents.runtime.agent_rep import AgentDesconhecido

    session = AsyncMock()
    textos_enviados = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        textos_enviados.append(texto)

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=mock_send):
        await AgentDesconhecido().responder(mensagem_rep, tenant_sem_whatsapp, session)

    # Com whatsapp_number=None deve usar fallback "da distribuidora"
    assert len(textos_enviados) == 1
    assert textos_enviados[0]  # não vazio
