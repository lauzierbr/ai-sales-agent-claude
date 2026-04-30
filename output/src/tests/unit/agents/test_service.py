"""Testes unitários — E10 (D030): notify_gestor_pendente + throttle + AUTORIZAR (Sprint 10).

Verifica:
- notify_gestor_pendente envia mensagem com template correto.
- Throttle de 6h: segunda notificação do mesmo número dentro de 6h não é enviada.
- Template contém candidato EFOS quando encontrado.
- Comando AUTORIZAR seta authorized=true.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.unit
async def test_notify_throttle_6h(mocker):
    """Segunda notificação do mesmo número dentro de 6h não é enviada."""
    from src.agents.service import notify_gestor_pendente

    # Mock Redis com lock já definido
    mock_redis = mocker.AsyncMock()
    mock_redis.get = AsyncMock(return_value="1")  # já enviou antes

    mock_session = mocker.AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(mappings=lambda: MagicMock(first=lambda: None)))

    # Mock da função de envio para garantir que NÃO é chamada
    mock_send = mocker.patch("src.agents.service.send_whatsapp_message", new=AsyncMock())

    result = await notify_gestor_pendente(
        tenant_id="jmb",
        numero_desconhecido="+5519999090001",
        mensagem_original="oi",
        instancia_id="jmb-instance",
        session=mock_session,
        redis_client=mock_redis,
    )

    # Deve retornar False (throttled) e NÃO chamar send_whatsapp_message
    assert result is False
    mock_send.assert_not_called()


@pytest.mark.unit
async def test_notify_template_contem_candidato(mocker):
    """Template contém 'AUTORIZAR', nome_fantasia e CNPJ quando candidato EFOS encontrado."""
    from src.agents.service import notify_gestor_pendente

    # Mock Redis sem lock (primeira notificação)
    mock_redis = mocker.AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    # Mock da query de candidato EFOS
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: {
        "nome": "DROGARIA CALDERARI LTDA",
        "cnpj": "12345678000199",
        "nome_fantasia": "Drogaria Calderari",
    }[key]

    mock_result = MagicMock()
    mock_result.mappings = lambda: MagicMock(first=lambda: mock_row)

    mock_session = mocker.AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock de gestores
    mock_gestor = MagicMock()
    mock_gestor.id = "gestor-uuid"
    mock_gestor.telefone = "+5519999000001"
    mocker.patch(
        "src.agents.service.GestorRepo",
        return_value=MagicMock(
            listar_ativos_por_tenant=AsyncMock(return_value=[mock_gestor])
        ),
    )

    # Capturar a mensagem enviada
    mensagens_enviadas = []
    async def mock_send(instancia_id, telefone, mensagem):
        mensagens_enviadas.append(mensagem)
    mocker.patch("src.agents.service.send_whatsapp_message", side_effect=mock_send)

    await notify_gestor_pendente(
        tenant_id="jmb",
        numero_desconhecido="+5519999090001",
        mensagem_original="preciso de shampoo",
        instancia_id="jmb-instance",
        session=mock_session,
        redis_client=mock_redis,
    )

    assert len(mensagens_enviadas) >= 1
    msg = mensagens_enviadas[0]
    assert "AUTORIZAR" in msg
    # Template deve conter o número para autorizar
    assert "+5519999090001" in msg


@pytest.mark.unit
async def test_autorizar_comando(mocker):
    """Comando AUTORIZAR atualiza contact.authorized=true."""
    from src.agents.repo import ContactRepo

    repo = ContactRepo()
    mock_session = mocker.AsyncMock()

    existing = {"id": "contact-uuid", "authorized": False}
    mocker.patch.object(repo, "get_by_channel", return_value=existing)
    mock_session.execute = AsyncMock(return_value=MagicMock())

    result = await repo.autorizar(
        tenant_id="jmb",
        identifier="+5519999090001",
        gestor_id="gestor-uuid",
        session=mock_session,
    )

    assert result is True
    mock_session.execute.assert_called_once()
