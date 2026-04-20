"""Entry point da aplicação — FastAPI app com todos os domínios do Sprint 1.

Sprint 0: catalog
Sprint 1: TenantProvider middleware, auth JWT, tenants, agents, scheduler.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia ciclo de vida da aplicação — inicia e encerra scheduler."""
    import os

    from src.providers.db import get_session_factory
    from src.providers.scheduler import create_scheduler, start_scheduler_from_db

    # Garante diretório de PDFs
    pdf_storage_path = os.getenv("PDF_STORAGE_PATH", "./pdfs")
    Path(pdf_storage_path).mkdir(parents=True, exist_ok=True)
    log.info("pdf_storage_pronto", path=pdf_storage_path)

    scheduler = create_scheduler()
    await start_scheduler_from_db(scheduler, get_session_factory())

    log.info("app_iniciada", versao="0.4.0")
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
        version="0.5.0",
        lifespan=lifespan,
    )

    # ─────────────────────────────────────────────
    # Middleware
    # ─────────────────────────────────────────────

    # CORS — Sprint 1 ainda permissivo; Sprint 4 restringirá por origem
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
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
    import os as _os
    pdfs_dir = Path(_os.getenv("PDF_STORAGE_PATH", "./pdfs"))
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/pdfs", StaticFiles(directory=str(pdfs_dir)), name="pdfs")

    # ─────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Endpoint de health check — excluído do TenantProvider."""
        return {"status": "ok", "version": "0.5.0"}

    return app


app = create_app()
