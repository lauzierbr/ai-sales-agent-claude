"""Interface base para crawlers de sites de distribuição.

Camada Runtime: importa src.catalog.types e src.catalog.config.
Cada site de distribuição implementa esta interface.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any

import structlog

from src.catalog.config import CrawlerConfig
from src.catalog.types import Categoria, ProdutoBruto

log = structlog.get_logger(__name__)


class CrawlerBase(ABC):
    """Interface abstrata para crawlers de sites B2B.

    Implementações concretas:
        - EfosCrawler (output/src/catalog/runtime/crawler/efos.py)
    """

    def __init__(self, config: CrawlerConfig) -> None:
        """Inicializa com configuração do tenant.

        Args:
            config: CrawlerConfig com URL, credenciais e parâmetros.
        """
        self.config = config
        self._authenticated = False

    # ─────────────────────────────────────────────
    # Context manager async
    # ─────────────────────────────────────────────

    async def __aenter__(self) -> "CrawlerBase":
        """Inicia browser Playwright e autentica."""
        await self._init_browser()
        success = await self.login()
        if not success:
            raise RuntimeError(
                f"Falha na autenticação do crawler para tenant '{self.config.tenant_id}'"
            )
        self._authenticated = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Faz logout e fecha o browser."""
        try:
            await self.logout()
        except Exception:
            log.warning("erro_logout_crawler", tenant_id=self.config.tenant_id)
        finally:
            await self._close_browser()

    # ─────────────────────────────────────────────
    # Métodos abstratos — implementados por cada site
    # ─────────────────────────────────────────────

    @abstractmethod
    async def _init_browser(self) -> None:
        """Inicializa o browser Playwright."""
        ...

    @abstractmethod
    async def _close_browser(self) -> None:
        """Fecha o browser e libera recursos."""
        ...

    @abstractmethod
    async def login(self) -> bool:
        """Autentica no site.

        Returns:
            True se autenticação bem-sucedida.
        """
        ...

    @abstractmethod
    async def get_categorias(self) -> list[Categoria]:
        """Extrai lista de categorias de produtos.

        Returns:
            Lista de categorias disponíveis.
        """
        ...

    @abstractmethod
    async def get_produtos(self, categoria: Categoria) -> list[ProdutoBruto]:
        """Extrai produtos de uma categoria.

        Args:
            categoria: categoria a ser crawleada.

        Returns:
            Lista de produtos brutos da categoria.
        """
        ...

    @abstractmethod
    async def logout(self) -> None:
        """Encerra a sessão autenticada."""
        ...

    # ─────────────────────────────────────────────
    # Helpers com retry
    # ─────────────────────────────────────────────

    async def _with_retry(
        self,
        fn: Any,
        *args: Any,
        operation: str = "operação",
        **kwargs: Any,
    ) -> Any:
        """Executa uma coroutine com retry exponencial.

        Args:
            fn: coroutine function a executar.
            *args: argumentos posicionais.
            operation: nome da operação para logging.
            **kwargs: argumentos nomeados.

        Returns:
            Resultado da coroutine.

        Raises:
            Exception: se todos os retries falharem.
        """
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                wait = 2**attempt  # backoff exponencial: 1s, 2s, 4s
                log.warning(
                    "crawler_retry",
                    tenant_id=self.config.tenant_id,
                    operation=operation,
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    error=str(exc),
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"Crawler falhou após {self.config.max_retries} tentativas "
            f"em '{operation}': {last_exc}"
        ) from last_exc

    async def _rate_limit(self) -> None:
        """Aguarda delay configurado entre requisições."""
        await asyncio.sleep(self.config.delay_between_pages_ms / 1000)
