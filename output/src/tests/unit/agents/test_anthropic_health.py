"""Testes unitários — health Anthropic ok/degraded/fail (E8).

@pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _reset_health() -> None:
    """Reseta estado global de health para 'ok' entre testes."""
    from src.agents.runtime import _retry
    _retry._anthropic_health_state = "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_ok_apos_sucesso() -> None:
    """Estado 'ok' após chamada bem-sucedida à API."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    mock_create = AsyncMock(return_value=MagicMock())
    await call_with_overload_retry(mock_create, agent_name="teste")

    assert get_anthropic_health() == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_degraded_em_overload_529() -> None:
    """Estado 'degraded' quando a API retorna 529 overload."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    overload_exc = Exception("overloaded_error — service temporarily unavailable")
    overload_exc.status_code = 529  # type: ignore[attr-defined]

    call_count = 0

    async def fail_then_succeed(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise overload_exc
        return MagicMock()

    await call_with_overload_retry(fail_then_succeed, agent_name="teste")

    # Após retry bem-sucedido, estado deve voltar para ok
    assert get_anthropic_health() == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_degraded_quando_overload_exaure_retries() -> None:
    """Estado 'degraded' quando todos os retries são esgotados por overload."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    overload_exc = Exception("overloaded_error")
    overload_exc.status_code = 529  # type: ignore[attr-defined]

    async def always_overload(**kwargs):
        raise overload_exc

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(Exception):
            await call_with_overload_retry(always_overload, agent_name="teste")

    assert get_anthropic_health() == "degraded"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_fail_em_auth_error_401() -> None:
    """Estado 'fail' quando API retorna 401 (auth error)."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    auth_exc = Exception("authentication_error: invalid api key")
    auth_exc.status_code = 401  # type: ignore[attr-defined]

    async def auth_fail(**kwargs):
        raise auth_exc

    with pytest.raises(Exception):
        await call_with_overload_retry(auth_fail, agent_name="teste")

    assert get_anthropic_health() == "fail"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_fail_em_quota_error_402() -> None:
    """Estado 'fail' quando API retorna 402 (quota/billing)."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    quota_exc = Exception("quota exceeded")
    quota_exc.status_code = 402  # type: ignore[attr-defined]

    async def quota_fail(**kwargs):
        raise quota_exc

    with pytest.raises(Exception):
        await call_with_overload_retry(quota_fail, agent_name="teste")

    assert get_anthropic_health() == "fail"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_health_fail_em_permission_error_403() -> None:
    """Estado 'fail' quando API retorna 403 (permission error)."""
    _reset_health()
    from src.agents.runtime._retry import call_with_overload_retry, get_anthropic_health

    perm_exc = Exception("permission_error: insufficient permissions")
    perm_exc.status_code = 403  # type: ignore[attr-defined]

    async def perm_fail(**kwargs):
        raise perm_exc

    with pytest.raises(Exception):
        await call_with_overload_retry(perm_fail, agent_name="teste")

    assert get_anthropic_health() == "fail"
