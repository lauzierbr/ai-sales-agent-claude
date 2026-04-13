"""Configurações do domínio Catalog.

Camada Config: importa apenas src.catalog.types e stdlib.
Secrets são lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import os


# ─────────────────────────────────────────────
# Configuração do Crawler
# ─────────────────────────────────────────────


class CrawlerConfig:
    """Configuração para o crawler Playwright de um tenant específico.

    Usa padrão dinâmico de variáveis Infisical:
      - CRAWLER_USER_{TENANT_ID_UPPER}
      - CRAWLER_PASS_{TENANT_ID_UPPER}
      - CRAWLER_BASE_URL_{TENANT_ID_UPPER}
      - CRAWLER_SESSION_{TENANT_ID_UPPER}  (opcional — bypass reCAPTCHA via cookie)
    """

    def __init__(
        self,
        tenant_id: str,
        base_url: str,
        username: str,
        password: str,
        headless: bool = True,
        timeout_ms: int = 30_000,
        max_retries: int = 3,
        delay_between_pages_ms: int = 1_000,
        session_cookie: str = "",
    ) -> None:
        self.tenant_id = tenant_id
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.delay_between_pages_ms = delay_between_pages_ms
        self.session_cookie = session_cookie

    @classmethod
    def for_tenant(cls, tenant_id: str) -> "CrawlerConfig":
        """Constrói CrawlerConfig para um tenant lendo variáveis do Infisical.

        Args:
            tenant_id: slug do tenant (ex: "jmb")

        Returns:
            CrawlerConfig populado com as variáveis de ambiente do tenant.

        Raises:
            ValueError: se alguma variável obrigatória não estiver definida.
        """
        tid = tenant_id.upper()

        base_url = os.getenv(f"CRAWLER_BASE_URL_{tid}", "")
        username = os.getenv(f"CRAWLER_USER_{tid}", "")
        password = os.getenv(f"CRAWLER_PASS_{tid}", "")
        session_cookie = os.getenv(f"CRAWLER_SESSION_{tid}", "")  # opcional

        missing = []
        if not base_url:
            missing.append(f"CRAWLER_BASE_URL_{tid}")
        if not username:
            missing.append(f"CRAWLER_USER_{tid}")
        if not password:
            missing.append(f"CRAWLER_PASS_{tid}")

        if missing:
            raise ValueError(
                f"Variáveis Infisical não configuradas para tenant '{tenant_id}': "
                + ", ".join(missing)
            )

        return cls(
            tenant_id=tenant_id,
            base_url=base_url,
            username=username,
            password=password,
            session_cookie=session_cookie,
        )

    def __repr__(self) -> str:
        return (
            f"CrawlerConfig(tenant_id={self.tenant_id!r}, "
            f"base_url={self.base_url!r}, headless={self.headless})"
        )


# ─────────────────────────────────────────────
# Configuração do Enriquecimento
# ─────────────────────────────────────────────


class EnrichmentConfig:
    """Configuração para o pipeline de enriquecimento (Haiku + OpenAI embeddings)."""

    def __init__(self) -> None:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")

        missing = []
        if not anthropic_key:
            missing.append("ANTHROPIC_API_KEY")
        if not openai_key:
            missing.append("OPENAI_API_KEY")

        if missing:
            raise ValueError(
                "Variáveis Infisical não configuradas: " + ", ".join(missing)
            )

        self.anthropic_api_key: str = anthropic_key
        self.openai_api_key: str = openai_key
        self.haiku_model: str = "claude-haiku-4-5-20251001"
        self.embedding_model: str = "text-embedding-3-small"
        self.embedding_dimensions: int = 1536
        self.max_concurrent_enrichments: int = 5

    def __repr__(self) -> str:
        return (
            f"EnrichmentConfig(model={self.haiku_model!r}, "
            f"embedding={self.embedding_model!r})"
        )


# ─────────────────────────────────────────────
# Configuração do banco de dados
# ─────────────────────────────────────────────


class DatabaseConfig:
    """Configuração de conexão com PostgreSQL."""

    def __init__(self) -> None:
        url = os.getenv("POSTGRES_URL", "")
        if not url:
            raise ValueError("Variável Infisical não configurada: POSTGRES_URL")
        self.postgres_url: str = url

    def __repr__(self) -> str:
        # Omite credenciais do repr
        parts = self.postgres_url.split("@")
        host_part = parts[-1] if len(parts) > 1 else "..."
        return f"DatabaseConfig(host={host_part!r})"
