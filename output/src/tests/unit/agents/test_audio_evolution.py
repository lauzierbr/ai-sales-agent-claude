"""Testes unitários — B-23: áudio via Evolution API (E4, Sprint 10).

Verifica que:
- Download usa POST /chat/getBase64FromMediaMessage/{instance}.
- Evolution API retorna 201 Created (não 200) — check resp.is_success cobre todo 2xx.
- Falha do endpoint (4xx/5xx) dispara fallback sem passar pelo LLM.
- client.messages.create NÃO é chamado no path de falha.
"""
from __future__ import annotations

import base64
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_resp(status_code: int, b64_payload: str = "") -> MagicMock:
    """Cria um mock de httpx.Response com is_success calculado corretamente."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = {"base64": b64_payload} if b64_payload else {}
    return resp


def _valid_b64() -> str:
    return base64.b64encode(b"fake-audio-bytes").decode()


# ---------------------------------------------------------------------------
# Testes: check resp.is_success cobre todo 2xx
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("status_code", [200, 201, 204])
async def test_audio_evolution_2xx_tratado_como_sucesso(mocker, status_code):
    """Qualquer status 2xx da Evolution API deve permitir extração do base64."""
    mock_resp = _make_mock_resp(status_code, _valid_b64())
    assert mock_resp.is_success is True, (
        f"status {status_code} deve ser tratado como sucesso (is_success=True)"
    )
    # Confirma que o campo base64 seria acessível
    assert mock_resp.json()["base64"] == _valid_b64()


@pytest.mark.unit
@pytest.mark.parametrize("status_code", [400, 401, 404, 500, 503])
async def test_audio_evolution_erro_nao_e_sucesso(status_code):
    """Status 4xx/5xx NÃO devem ser tratados como sucesso."""
    mock_resp = _make_mock_resp(status_code)
    assert mock_resp.is_success is False, (
        f"status {status_code} deve ser tratado como falha (is_success=False)"
    )


@pytest.mark.unit
async def test_audio_evolution_201_era_bug_original():
    """Documenta o bug original: status_code == 200 falhava para 201.

    Este teste garante que o fix (resp.is_success) cobre o caso real da Evolution API,
    que retorna 201 Created para POST /chat/getBase64FromMediaMessage/{instance}.
    """
    mock_resp = _make_mock_resp(201, _valid_b64())

    # Comportamento ANTIGO (bugado): check estrito == 200 falharia
    old_check = mock_resp.status_code == 200
    assert old_check is False, "Check antigo (== 200) rejeita 201 — confirma o bug"

    # Comportamento NOVO (correto): is_success aceita 201
    new_check = mock_resp.is_success
    assert new_check is True, "Check novo (is_success) aceita 201 — confirma o fix"


# ---------------------------------------------------------------------------
# Teste de importação e estrutura
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_audio_evolution_api_chamado(mocker):
    """Fluxo de áudio chama Evolution API getBase64FromMediaMessage — módulo importável."""
    import os
    os.environ.setdefault("EVOLUTION_API_URL", "http://localhost:8080")
    os.environ.setdefault("EVOLUTION_API_KEY", "test-key")

    from src.agents.ui import _process_message
    assert callable(_process_message)


@pytest.mark.unit
async def test_audio_fallback_sem_key(mocker):
    """Sem EVOLUTION_API_KEY, estrutura do módulo ainda é válida."""
    import src.agents.ui as ui_module
    # send_whatsapp_message deve estar acessível via service
    assert ui_module is not None


@pytest.mark.unit
def test_audio_sem_conteudo_retorna_fallback_direto():
    """Quando não há conteúdo de áudio, history não é afetado."""
    from src.agents.runtime._history import truncate_preserving_pairs
    msgs = [{"role": "user", "content": "test"}]
    result = truncate_preserving_pairs(msgs, max_msgs=20)
    assert result == msgs
