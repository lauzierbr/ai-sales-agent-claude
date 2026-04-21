"""Testes unitários — validação de secrets no startup (E5).

@pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


_ALL_SECRETS = {
    "POSTGRES_URL": "postgresql+asyncpg://user:pass@localhost/db",
    "REDIS_URL": "redis://localhost:6379",
    "JWT_SECRET": "jwt-secret-muito-longo-256-bits-000000000000000000000",
    "DASHBOARD_SECRET": "dashboard-secret-123",
    "DASHBOARD_TENANT_ID": "jmb",
    "EVOLUTION_API_KEY": "evo-key-123",
    "EVOLUTION_WEBHOOK_SECRET": "evo-webhook-secret",
    "OPENAI_API_KEY": "sk-openai-test",
    "ANTHROPIC_API_KEY": "sk-ant-test",
}


@pytest.mark.unit
def test_startup_validation_todos_presentes_nao_levanta() -> None:
    """Startup não levanta RuntimeError quando todos os secrets estão presentes."""
    from src.main import _validate_secrets

    # Remove vars do env para garantir estado limpo, depois injeta todos
    env_sem_secrets = {k: v for k, v in os.environ.items() if k not in _ALL_SECRETS}
    with patch.dict(os.environ, {**env_sem_secrets, **_ALL_SECRETS}, clear=True):
        _validate_secrets()  # não deve levantar


@pytest.mark.unit
def test_startup_validation_secret_ausente_levanta_runtime_error() -> None:
    """Startup levanta RuntimeError quando um secret crítico está ausente."""
    from src.main import _validate_secrets

    env_sem_um = {k: v for k, v in _ALL_SECRETS.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env_sem_um, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            _validate_secrets()
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


@pytest.mark.unit
def test_startup_validation_multiplos_ausentes_lista_todos() -> None:
    """Quando múltiplos secrets estão ausentes, a mensagem lista todos."""
    from src.main import _validate_secrets

    # Deixa apenas 2 secrets presentes
    env_parcial = {
        "POSTGRES_URL": "postgresql+asyncpg://x",
        "REDIS_URL": "redis://localhost",
    }
    with patch.dict(os.environ, env_parcial, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            _validate_secrets()

    msg = str(exc_info.value)
    # Os 7 ausentes devem aparecer na mensagem
    for var in ["JWT_SECRET", "DASHBOARD_SECRET", "DASHBOARD_TENANT_ID",
                "EVOLUTION_API_KEY", "EVOLUTION_WEBHOOK_SECRET",
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        assert var in msg, f"{var} deve aparecer na mensagem de erro"


@pytest.mark.unit
def test_startup_validation_mensagem_unica() -> None:
    """A mensagem de erro é uma única RuntimeError, não várias exceções."""
    from src.main import _validate_secrets

    with patch.dict(os.environ, {}, clear=True):
        raised = []
        try:
            _validate_secrets()
        except RuntimeError as e:
            raised.append(e)
        except Exception as e:
            pytest.fail(f"Esperado RuntimeError, got {type(e).__name__}: {e}")

    assert len(raised) == 1, "Deve levantar exatamente 1 RuntimeError com todos os secrets ausentes"
