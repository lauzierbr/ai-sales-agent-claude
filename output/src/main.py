"""Entry point da aplicação — FastAPI app com router do catálogo.

Sprint 0: apenas o domínio catalog está disponível.
Sprint 1 adicionará: TenantProvider middleware, auth JWT, outros domínios.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.catalog.ui import router as catalog_router
from src.providers.telemetry import setup_telemetry

log = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    setup_telemetry("ai-sales-agent")

    app = FastAPI(
        title="AI Sales Agent",
        description="Agente de vendas B2B via WhatsApp para distribuidoras brasileiras",
        version="0.1.0",
    )

    # CORS — Sprint 1 restringirá por origem
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(catalog_router)

    # Serve imagens baixadas pelo crawler — /images/{tenant_id}/{codigo}.jpg
    # Usa caminho absoluto relativo ao arquivo (independente de CWD)
    images_dir = Path(__file__).parent.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Endpoint de health check."""
        return {"status": "ok"}

    log.info("app_iniciada", versao="0.1.0")
    return app


app = create_app()
