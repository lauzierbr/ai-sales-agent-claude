"""Entry point da aplicação — FastAPI app com todos os domínios do Sprint 1.

Sprint 0: catalog
Sprint 1: TenantProvider middleware, auth JWT, tenants, agents, scheduler.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.catalog.ui import router as catalog_router
from src.dashboard.ui import router as dashboard_router
from src.providers.telemetry import setup_telemetry
from src.providers.tenant_context import TenantProvider
from src.tenants.ui import auth_router, router as tenants_router
from src.agents.ui import router as agents_router

log = structlog.get_logger(__name__)

_REQUIRED_SECRETS = [
    "POSTGRES_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "DASHBOARD_SECRET",
    "DASHBOARD_TENANT_ID",
    "EVOLUTION_API_KEY",
    "EVOLUTION_WEBHOOK_SECRET",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
]


def _validate_secrets() -> None:
    """Falha no startup se algum secret crítico estiver ausente."""
    missing = [k for k in _REQUIRED_SECRETS if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            "Secrets críticos ausentes — a aplicação não pode iniciar: "
            + ", ".join(missing)
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia ciclo de vida da aplicação — inicia e encerra scheduler."""
    from src.providers.db import get_session_factory
    from src.providers.scheduler import create_scheduler, start_scheduler_from_db

    _validate_secrets()

    # Garante diretório de PDFs
    pdf_storage_path = os.getenv("PDF_STORAGE_PATH", "./pdfs")
    Path(pdf_storage_path).mkdir(parents=True, exist_ok=True)
    log.info("pdf_storage_pronto", path=pdf_storage_path)

    scheduler = create_scheduler()
    await start_scheduler_from_db(scheduler, get_session_factory())

    log.info("app_iniciada", versao="0.9.0")
    yield

    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("scheduler_encerrado")


def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    setup_telemetry("ai-sales-agent")

    app = FastAPI(
        title="AI Sales Agent",
        description="Agente de vendas B2B via WhatsApp para distribuidoras brasileiras",
        version="0.9.0",
        lifespan=lifespan,
    )

    # ─────────────────────────────────────────────
    # Middleware
    # ─────────────────────────────────────────────

    environment = os.getenv("ENVIRONMENT", "development")
    if environment == "development":
        cors_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    else:
        raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
        if not raw:
            raise RuntimeError(
                f"CORS_ALLOWED_ORIGINS deve ser definido em ambiente {environment!r}"
            )
        cors_origins = [o.strip() for o in raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # TenantProvider — injeta tenant em todo request (exceto rotas excluídas)
    app.add_middleware(TenantProvider)

    # ─────────────────────────────────────────────
    # Routers
    # ─────────────────────────────────────────────

    app.include_router(catalog_router)
    app.include_router(auth_router)
    app.include_router(tenants_router)
    app.include_router(agents_router)
    app.include_router(dashboard_router)

    # ─────────────────────────────────────────────
    # Static files — imagens do crawler
    # ─────────────────────────────────────────────

    images_dir = Path(__file__).parent.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

    # PDFs gerados pelo agente
    pdfs_dir = Path(os.getenv("PDF_STORAGE_PATH", "./pdfs"))
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/pdfs", StaticFiles(directory=str(pdfs_dir)), name="pdfs")

    # ─────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Endpoint de health check — excluído do TenantProvider."""
        from src.agents.runtime._retry import get_anthropic_health

        anthropic_state = get_anthropic_health()
        overall = "ok" if anthropic_state == "ok" else "degraded"
        return {
            "status": overall,
            "version": "0.9.0",
            "components": {
                "anthropic": anthropic_state,
            },
        }

    return app


app = create_app()
