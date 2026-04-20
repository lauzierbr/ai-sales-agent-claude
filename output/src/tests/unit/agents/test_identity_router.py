"""Testes unitários de agents/service.py — IdentityRouter (Sprint 2 + Sprint 4).

Todos os testes são @pytest.mark.unit — sem I/O externo.
PostgreSQL mockado via AsyncMock.

Sprint 4 adiciona IR-G1 a IR-G4 para persona GESTOR.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.types import ClienteB2B, Gestor, Mensagem, Persona, Representante


@pytest.fixture
def mensagem_fixture() -> Mensagem:
    return Mensagem(
        id="msg1",
        de="5519999999999@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Olá, quero fazer um pedido",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def cliente_b2b_fixture() -> ClienteB2B:
    return ClienteB2B(
        id="cli-001",
        tenant_id="jmb",
        nome="Farmácia Central",
        cnpj="12.345.678/0001-90",
        telefone="5519999999999",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def representante_fixture() -> Representante:
    return Representante(
        id="rep-001",
        tenant_id="jmb",
        usuario_id="usr-001",
        telefone="5511888888888",
        nome="Carlos Representante",
        ativo=True,
    )


# ─────────────────────────────────────────────
# A5: telefone em clientes_b2b → CLIENTE_B2B
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_retorna_cliente_b2b(
    mensagem_fixture: Mensagem, cliente_b2b_fixture: ClienteB2B
) -> None:
    """A5: IdentityRouter retorna CLIENTE_B2B quando número está em clientes_b2b."""
    from unittest.mock import patch

    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(
            router._cliente_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=cliente_b2b_fixture),
        ),
        patch.object(
            router._rep_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=None),
        ),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.CLIENTE_B2B


# ─────────────────────────────────────────────
# A6: telefone desconhecido → DESCONHECIDO
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_retorna_desconhecido(
    mensagem_fixture: Mensagem,
) -> None:
    """A6: IdentityRouter retorna DESCONHECIDO quando número não está em nenhuma tabela."""
    from unittest.mock import patch

    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(
            router._cliente_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            router._rep_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=None),
        ),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.DESCONHECIDO


# ─────────────────────────────────────────────
# A7: strip do sufixo @s.whatsapp.net
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_strip_whatsapp_suffix(
    mensagem_fixture: Mensagem, cliente_b2b_fixture: ClienteB2B
) -> None:
    """A7: IdentityRouter chama repo com digits apenas, sem sufixo @s.whatsapp.net."""
    from unittest.mock import patch

    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    chamadas: list[str] = []

    async def mock_get_by_telefone(tenant_id: str, telefone: str, session: AsyncMock) -> ClienteB2B | None:
        chamadas.append(telefone)
        return cliente_b2b_fixture

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._rep_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._cliente_repo, "get_by_telefone", new=mock_get_by_telefone),
    ):
        await router.resolve(mensagem_fixture, "jmb", session)

    assert len(chamadas) == 1
    assert "@" not in chamadas[0], f"Sufixo WhatsApp não foi removido: {chamadas[0]}"
    assert chamadas[0] == "5519999999999"


# ─────────────────────────────────────────────
# Representante identificado
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_retorna_representante(
    representante_fixture: Representante,
) -> None:
    """IdentityRouter retorna REPRESENTANTE quando número está em representantes."""
    from unittest.mock import patch

    from src.agents.service import IdentityRouter

    mensagem_rep = Mensagem(
        id="msg2",
        de="5511888888888@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Consulta de catálogo",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
    )

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(
            router._cliente_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            router._rep_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=representante_fixture),
        ),
    ):
        persona = await router.resolve(mensagem_rep, "jmb", session)

    assert persona == Persona.REPRESENTANTE


# ─────────────────────────────────────────────
# Cliente tem prioridade sobre representante
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_representante_tem_prioridade_sobre_cliente(
    mensagem_fixture: Mensagem,
    cliente_b2b_fixture: ClienteB2B,
    representante_fixture: Representante,
) -> None:
    """IdentityRouter retorna REPRESENTANTE quando número está em ambas as tabelas (rep tem prioridade sobre cliente)."""
    from unittest.mock import patch

    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(
            router._cliente_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=cliente_b2b_fixture),
        ),
        patch.object(
            router._rep_repo,
            "get_by_telefone",
            new=AsyncMock(return_value=representante_fixture),
        ),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.REPRESENTANTE


# ─────────────────────────────────────────────
# parse_mensagem (mantido do Sprint 1)
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_parse_mensagem_extrai_texto_conversation() -> None:
    """parse_mensagem extrai texto de mensagem tipo conversation."""
    from src.agents.service import parse_mensagem
    from src.agents.types import WebhookPayload

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {"id": "msg1", "remoteJid": "5519999999999@s.whatsapp.net"},
            "message": {"conversation": "Olá"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    )
    mensagem = parse_mensagem(payload)

    assert mensagem.texto == "Olá"
    assert mensagem.de == "5519999999999@s.whatsapp.net"
    assert mensagem.instancia_id == "inst-jmb-01"


# ─────────────────────────────────────────────
# send_whatsapp_message (M4 coverage)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_send_whatsapp_message_sucesso() -> None:
    """send_whatsapp_message envia POST para Evolution API com sucesso."""
    from unittest.mock import MagicMock, patch

    import httpx

    from src.agents.service import send_whatsapp_message

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        await send_whatsapp_message("inst-jmb-01", "5519999999999", "Ola!")

    mock_client_instance.post.assert_called_once()
    call_kwargs = mock_client_instance.post.call_args
    assert "inst-jmb-01" in call_kwargs[0][0]


@pytest.mark.unit
async def test_send_whatsapp_message_erro_nao_propaga() -> None:
    """send_whatsapp_message captura HTTPStatusError sem propagar."""
    from unittest.mock import MagicMock, patch

    import httpx

    from src.agents.service import send_whatsapp_message

    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=error)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        await send_whatsapp_message("inst-jmb-01", "5519999999999", "Ola!")


# ─────────────────────────────────────────────
# send_whatsapp_media (M3 + M4 coverage)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_send_whatsapp_media_usa_base64_e_endpoint() -> None:
    """M3: send_whatsapp_media usa base64 e endpoint /sendMedia; erro nao propaga."""
    import base64
    from unittest.mock import MagicMock, patch

    from src.agents.service import send_whatsapp_media

    pdf_bytes = b"PDF_FAKE_CONTENT" * 50
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        await send_whatsapp_media(
            instancia_id="inst-jmb-01",
            numero="5519999990000",
            pdf_bytes=pdf_bytes,
            caption="Novo pedido PED-ABC123",
            file_name="pedido-abc123.pdf",
        )

    mock_client_instance.post.assert_called_once()
    url_called = mock_client_instance.post.call_args[0][0]
    assert "/message/sendMedia/" in url_called

    payload_sent = mock_client_instance.post.call_args.kwargs["json"]
    assert payload_sent["media"] == base64.b64encode(pdf_bytes).decode()
    assert payload_sent["mimetype"] == "application/pdf"
    assert payload_sent["number"] == "5519999990000"


@pytest.mark.unit
async def test_send_whatsapp_media_erro_nao_propaga() -> None:
    """send_whatsapp_media captura erro HTTP sem propagar."""
    from unittest.mock import MagicMock, patch

    import httpx

    from src.agents.service import send_whatsapp_media

    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=error)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # Nao deve propagar
        await send_whatsapp_media(
            instancia_id="inst-jmb-01",
            numero="5519999990000",
            pdf_bytes=b"pdf",
            caption="Caption",
            file_name="pedido.pdf",
        )


# ─────────────────────────────────────────────
# validate_webhook_signature (M4 coverage)
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# IR-G1: GESTOR identificado — retorna Persona.GESTOR
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_gestor_retorna_gestor(
    mensagem_fixture: Mensagem,
) -> None:
    """IR-G1: IdentityRouter retorna GESTOR quando número está em gestores."""
    from src.agents.service import IdentityRouter

    gestor = Gestor(
        id="gest-001",
        tenant_id="jmb",
        telefone="5519999999999",
        nome="Lauzier Gestor",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=gestor)),
        patch.object(router._rep_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._cliente_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.GESTOR


# ─────────────────────────────────────────────
# IR-G2: GESTOR tem prioridade sobre REPRESENTANTE (perfis cumulativos, DP-02)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_gestor_rep_cumulativo_retorna_gestor(
    mensagem_fixture: Mensagem,
    representante_fixture: Representante,
) -> None:
    """IR-G2: Quando mock retorna gestor ativo E representante ativo para o mesmo telefone,
    IdentityRouter.resolve() retorna Persona.GESTOR; GestorRepo chamado antes de RepresentanteRepo.
    """
    from src.agents.service import IdentityRouter

    gestor = Gestor(
        id="gest-001",
        tenant_id="jmb",
        telefone="5519999999999",
        nome="Lauzier Gestor",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    session = AsyncMock()
    router = IdentityRouter()

    chamadas: list[str] = []

    async def mock_gestor_get(tenant_id: str, telefone: str, session: AsyncMock) -> Gestor:
        chamadas.append("gestor")
        return gestor

    async def mock_rep_get(tenant_id: str, telefone: str, session: AsyncMock) -> Representante:
        chamadas.append("rep")
        return representante_fixture

    async def mock_cliente_get(tenant_id: str, telefone: str, session: AsyncMock) -> None:
        chamadas.append("cliente")
        return None

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=mock_gestor_get),
        patch.object(router._rep_repo, "get_by_telefone", new=mock_rep_get),
        patch.object(router._cliente_repo, "get_by_telefone", new=mock_cliente_get),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.GESTOR
    assert chamadas[0] == "gestor", "GestorRepo deve ser chamado antes de RepresentanteRepo"


# ─────────────────────────────────────────────
# IR-G3: Número só em representantes → REPRESENTANTE (sem regressão)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_gestor_ausente_retorna_representante(
    mensagem_fixture: Mensagem,
    representante_fixture: Representante,
) -> None:
    """IR-G3: Sem gestor, número em representantes → REPRESENTANTE (sem regressão)."""
    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._rep_repo, "get_by_telefone", new=AsyncMock(return_value=representante_fixture)),
        patch.object(router._cliente_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.REPRESENTANTE


# ─────────────────────────────────────────────
# IR-G4: Número desconhecido → DESCONHECIDO (com gestor_repo mockado)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_gestor_ausente_desconhecido(
    mensagem_fixture: Mensagem,
) -> None:
    """IR-G4: Sem gestor, sem rep, sem cliente → DESCONHECIDO."""
    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    with (
        patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._rep_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
        patch.object(router._cliente_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
    ):
        persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.DESCONHECIDO


# ─────────────────────────────────────────────
# validate_webhook_signature
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_validate_webhook_signature_sem_secret_retorna_false() -> None:
    """validate_webhook_signature retorna False quando EVOLUTION_WEBHOOK_SECRET ausente."""
    from unittest.mock import patch

    from src.agents.service import validate_webhook_signature

    with patch.dict("os.environ", {}, clear=True):
        result = validate_webhook_signature(b"body", "qualquer-assinatura")

    assert result is False
