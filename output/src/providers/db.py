"""Provider de banco de dados — async SQLAlchemy engine e session factory.

Não importa nenhum domínio (catalog, orders, etc.).
Usado por todos os Repos via injeção de dependência.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def get_engine() -> AsyncEngine:
    """Cria AsyncEngine do SQLAlchemy a partir da variável POSTGRES_URL.

    Returns:
        AsyncEngine configurado com pool de conexões.

    Raises:
        ValueError: se POSTGRES_URL não estiver definida.
    """
    url = os.getenv("POSTGRES_URL", "")
    if not url:
        raise ValueError("Variável Infisical não configurada: POSTGRES_URL")

    # Garante driver assíncrono (asyncpg)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    return create_async_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )


# Engine e session factory como singletons lazy
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retorna (ou cria) a session factory singleton.

    Returns:
        async_sessionmaker configurado para uso com async with.
    """
    global _engine, _session_factory
    if _session_factory is None:
        _engine = get_engine()
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency FastAPI: injeta AsyncSession no request.

    Uso:
        async def endpoint(session: AsyncSession = Depends(get_session)): ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


# ─────────────────────────────────────────────
# Redis — singleton lazy para cache e locks
# ─────────────────────────────────────────────

import redis.asyncio as aioredis  # noqa: E402

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Retorna (ou cria) o cliente Redis singleton.

    Lê REDIS_URL do Infisical. Se indisponível, caller deve tratar exceção.

    Returns:
        Cliente Redis assíncrono.
    """
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client
