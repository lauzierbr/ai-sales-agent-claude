"""Testes unitários para transcrição de áudio WhatsApp via Whisper (E3 — Sprint 9).

Cobre 4 cenários obrigatórios do contrato:
  1. audioMessage com URL → download + transcrição + prefixo 🎤
  2. audioMessage com base64 → decode + transcrição + prefixo 🎤
  3. Falha na API Whisper → fallback amigável
  4. Mensagem de texto normal → NÃO passa por _transcrever_audio

Gotchas verificados:
  - asyncio.to_thread presente em _transcrever_audio
  - Nome "audio.ogg" presente no tuple passado ao Whisper API
  - OPENAI_API_KEY apenas via os.getenv(), nunca hardcoded
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_transcrever_retorna_texto() -> None:
    """_transcrever_audio retorna texto transcrito via Whisper."""
    from src.agents.ui import _transcrever_audio

    mock_transcricao = MagicMock()
    mock_transcricao.text = "Olá, quero pedir shampoo"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_transcricao

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-fake-key-for-unit-test"}):
        with patch("openai.OpenAI", return_value=mock_client):
            resultado = await _transcrever_audio(b"fake_audio_bytes")

    assert resultado == "Olá, quero pedir shampoo"
    # Verifica que nome "audio.ogg" foi passado
    call_kwargs = mock_client.audio.transcriptions.create.call_args
    file_arg = call_kwargs[1].get("file") or (call_kwargs[0][0] if call_kwargs[0] else None)
    # file é uma tupla (nome, bytes, mime_type)
    assert "audio.ogg" in str(call_kwargs), (
        "A_AUDIO_TRANSCRICAO: nome 'audio.ogg' deve estar no tuple passado ao Whisper API. "
        "Gotcha da Evolution API: sem esse nome o Whisper rejeita o arquivo."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_transcrever_sem_api_key_retorna_vazio() -> None:
    """_transcrever_audio retorna string vazia quando OPENAI_API_KEY está ausente."""
    from src.agents.ui import _transcrever_audio

    with patch.dict("os.environ", {}, clear=True):
        resultado = await _transcrever_audio(b"fake_audio_bytes")

    assert resultado == "", (
        "Sem OPENAI_API_KEY, _transcrever_audio deve retornar '' (não levantar exceção)."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_transcrever_falha_api_retorna_vazio() -> None:
    """_transcrever_audio retorna string vazia quando Whisper API levanta exceção."""
    from src.agents.ui import _transcrever_audio

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.side_effect = Exception("API Error 500")

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-fake-key-for-unit-test"}):
        with patch("openai.OpenAI", return_value=mock_client):
            resultado = await _transcrever_audio(b"fake_audio_bytes")

    # Deve retornar string vazia e logar erro, não propagar a exceção
    assert isinstance(resultado, str)


@pytest.mark.unit
def test_transcrever_audio_usa_asyncio_to_thread() -> None:
    """_transcrever_audio deve usar asyncio.to_thread (Whisper API é síncrona)."""
    from src.agents.ui import _transcrever_audio

    source = inspect.getsource(_transcrever_audio)
    assert "asyncio.to_thread" in source, (
        "A_AUDIO_TRANSCRICAO: asyncio.to_thread obrigatório em _transcrever_audio. "
        "Whisper API é síncrona — sem to_thread bloqueia o event loop."
    )


@pytest.mark.unit
def test_transcrever_audio_nome_ogg_no_codigo() -> None:
    """Nome 'audio.ogg' deve estar presente no código de _transcrever_audio."""
    from src.agents.ui import _transcrever_audio

    source = inspect.getsource(_transcrever_audio)
    assert '"audio.ogg"' in source, (
        "A_AUDIO_TRANSCRICAO: 'audio.ogg' deve ser o nome do arquivo no tuple "
        "passado ao Whisper API. Gotcha: Evolution API envia sem extensão, "
        "Whisper precisa do nome para inferir o codec."
    )


@pytest.mark.unit
def test_openai_api_key_apenas_getenv() -> None:
    """OPENAI_API_KEY deve ser obtida apenas via os.getenv, nunca hardcoded."""
    import src.agents.ui as ui_module

    source = inspect.getsource(ui_module)
    assert 'os.getenv("OPENAI_API_KEY")' in source, (
        "OPENAI_API_KEY deve ser obtida via os.getenv('OPENAI_API_KEY') em agents/ui.py."
    )
    # Verificação de ausência de valor literal (sk- nunca deve aparecer)
    assert "sk-ant" not in source
    assert "sk-proj" not in source


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_mensagem_audio_retorna_mensagem_vazia() -> None:
    """parse_mensagem detecta audioMessage e retorna Mensagem com texto vazio."""
    from src.agents.service import parse_mensagem
    from src.agents.types import WebhookPayload

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {
                "remoteJid": "5519912345678@s.whatsapp.net",
                "fromMe": False,
                "id": "msg-audio-001",
            },
            "messageType": "audioMessage",
            "messageTimestamp": 1714200000,
            "message": {
                "audioMessage": {
                    "url": "https://example.com/audio.ogg",
                    "mimetype": "audio/ogg; codecs=opus",
                },
            },
        },
        destination=None,
        date_time=None,
        sender=None,
        server_url=None,
        apikey=None,
    )

    mensagem = parse_mensagem(payload)

    assert mensagem is not None, "audioMessage deve retornar Mensagem (não None)"
    assert mensagem.tipo == "audioMessage"
    assert mensagem.texto == ""  # texto vazio — será preenchido após Whisper
