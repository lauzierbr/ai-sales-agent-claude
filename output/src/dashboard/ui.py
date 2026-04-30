"""Dashboard web do gestor — endpoints FastAPI com Jinja2 + htmx.

Camada UI: pode importar de qualquer camada.
Decisão D023: auth via DASHBOARD_SECRET + cookie HttpOnly JWT (reutiliza JWT_SECRET de D021).
Prefixo /dashboard excluído do TenantProvider — tenant resolvido via cookie JWT.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.providers.auth import create_access_token, decode_token

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Disponibiliza a versão do app em todos os templates como global Jinja
from src import __version__ as _APP_VERSION
templates.env.globals["app_version"] = _APP_VERSION

# Filters Jinja pt-BR (B-31): |brl, |int_br
from src.providers.format import register_jinja_filters as _register_jinja_filters
_register_jinja_filters(templates.env)

_COOKIE_NAME = "dashboard_session"
_COOKIE_MAX_AGE = 8 * 3600  # 8h em segundos

_LOGIN_RATE_LIMIT_MAX = 5
_LOGIN_RATE_LIMIT_WINDOW = 15 * 60  # 15 min em segundos


async def _get_login_attempts(ip: str) -> int:
    """Retorna número de falhas de login recentes para o IP."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        key = f"login_fail:{ip}"
        val = await r.get(key)
        await r.aclose()
        return int(val) if val else 0
    except Exception:
        return 0


async def _increment_login_fail(ip: str) -> int:
    """Incrementa contador de falhas de login para o IP; retorna novo valor."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        key = f"login_fail:{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, _LOGIN_RATE_LIMIT_WINDOW)
        await r.aclose()
        return int(count)
    except Exception:
        return 0


async def _reset_login_fail(ip: str) -> None:
    """Remove contador de falhas após login bem-sucedido."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        await r.delete(f"login_fail:{ip}")
        await r.aclose()
    except Exception:
        pass


def _get_dashboard_secret() -> str:
    return os.getenv("DASHBOARD_SECRET", "")


def _get_dashboard_tenant_id() -> str:
    return os.getenv("DASHBOARD_TENANT_ID", "jmb")


def _verify_session(request: Request) -> dict[str, Any] | None:
    """Verifica cookie dashboard_session e retorna payload do JWT, ou None."""
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("role") != "gestor":
            return None
        return payload
    except Exception:
        return None


def _require_session(request: Request) -> dict[str, Any] | None:
    """Retorna payload do JWT ou None (para redirect no caller)."""
    return _verify_session(request)


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request) -> HTMLResponse:
    """Exibe página de login do dashboard."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": False},
    )


@router.post("/login")
async def post_login(request: Request) -> Any:
    """Processa login com DASHBOARD_SECRET.

    Sucesso → seta cookie HttpOnly SameSite=Lax + redirect /dashboard/home.
    Falha → re-renderiza login.html com error=True.
    Rate limit: 5 falhas por IP em 15min → HTTP 429.
    """
    client_ip = request.client.host if request.client else "unknown"

    attempts = await _get_login_attempts(client_ip)
    if attempts >= _LOGIN_RATE_LIMIT_MAX:
        log.warning("dashboard_login_rate_limit", ip=client_ip, attempts=attempts)
        return HTMLResponse(
            "<h2>Muitas tentativas. Aguarde 15 minutos e tente novamente.</h2>",
            status_code=429,
        )

    form = await request.form()
    senha = form.get("senha", "")

    stored_secret = _get_dashboard_secret()
    if not stored_secret:
        log.error("dashboard_secret_ausente")
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": True},
            status_code=401,
        )

    if not hmac.compare_digest(stored_secret.encode(), str(senha).encode()):
        await _increment_login_fail(client_ip)
        log.warning("dashboard_login_senha_incorreta", ip=client_ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": True},
            status_code=401,
        )

    await _reset_login_fail(client_ip)
    tenant_id = _get_dashboard_tenant_id()
    token = create_access_token(
        user_id="gestor-dashboard",
        tenant_id=tenant_id,
        role="gestor",
    )

    response = RedirectResponse(url="/dashboard/home", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        secure=os.getenv("ENVIRONMENT", "development") == "production",
    )
    log.info("dashboard_login_sucesso", tenant_id=tenant_id)
    return response


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Encerra sessão — limpa cookie + redirect para login."""
    response = RedirectResponse(url="/dashboard/login", status_code=302)
    response.delete_cookie(key=_COOKIE_NAME)
    return response


# ─────────────────────────────────────────────
# Home — KPIs em tempo real
# ─────────────────────────────────────────────


@router.get("/home", response_class=HTMLResponse)
async def home(request: Request) -> Any:
    """Dashboard home — KPIs do dia com htmx polling 30s."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    kpis = await _get_kpis(tenant_id)
    pedidos = await _get_pedidos_recentes(tenant_id, limit=10)
    conversas = await _get_conversas_ativas(tenant_id)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "kpis": kpis,
            "pedidos": pedidos,
            "conversas": conversas,
            "tenant_id": tenant_id,
        },
    )


@router.get("/home/partials/kpis", response_class=HTMLResponse)
async def partials_kpis(request: Request) -> Any:
    """Partial htmx com KPIs atualizados — chamado a cada 30s."""
    session_data = _require_session(request)
    if session_data is None:
        return HTMLResponse("<div>Sessão expirada. <a href='/dashboard/login'>Login</a></div>", status_code=401)

    tenant_id = session_data["tenant_id"]
    kpis = await _get_kpis(tenant_id)

    return templates.TemplateResponse(
        request,
        "_partials/kpis.html",
        {"kpis": kpis},
    )


# ─────────────────────────────────────────────
# Pedidos
# ─────────────────────────────────────────────


@router.get("/pedidos", response_class=HTMLResponse)
async def pedidos(request: Request) -> Any:
    """Lista de pedidos com filtros de status e período."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    pedidos_list = await _get_pedidos_recentes(tenant_id, limit=50)

    return templates.TemplateResponse(
        request,
        "pedidos.html",
        {"pedidos": pedidos_list, "tenant_id": tenant_id},
    )


@router.get("/home/partials/pedidos_recentes", response_class=HTMLResponse)
async def partials_pedidos_recentes(request: Request) -> Any:
    """Partial htmx com pedidos recentes."""
    session_data = _require_session(request)
    if session_data is None:
        return HTMLResponse("<div>Sessão expirada.</div>", status_code=401)

    tenant_id = session_data["tenant_id"]
    pedidos_list = await _get_pedidos_recentes(tenant_id, limit=10)

    return templates.TemplateResponse(
        request,
        "_partials/pedidos_recentes.html",
        {"pedidos": pedidos_list},
    )


# ─────────────────────────────────────────────
# Conversas
# ─────────────────────────────────────────────


@router.get("/conversas", response_class=HTMLResponse)
async def conversas(request: Request) -> Any:
    """Conversas ativas das últimas 24h."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    conversas_list = await _get_conversas_ativas(tenant_id)

    return templates.TemplateResponse(
        request,
        "conversas.html",
        {"conversas": conversas_list, "tenant_id": tenant_id},
    )


@router.get("/home/partials/conversas_ativas", response_class=HTMLResponse)
async def partials_conversas_ativas(request: Request) -> Any:
    """Partial htmx com conversas ativas."""
    session_data = _require_session(request)
    if session_data is None:
        return HTMLResponse("<div>Sessão expirada.</div>", status_code=401)

    tenant_id = session_data["tenant_id"]
    conversas_list = await _get_conversas_ativas(tenant_id)

    return templates.TemplateResponse(
        request,
        "_partials/conversas_ativas.html",
        {"conversas": conversas_list},
    )


# ─────────────────────────────────────────────
# Clientes
# ─────────────────────────────────────────────


@router.get("/clientes", response_class=HTMLResponse)
async def clientes(request: Request) -> Any:
    """Lista de clientes com busca por nome/CNPJ."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    q = request.query_params.get("q", "")
    clientes_list = await _get_clientes(tenant_id, q)

    return templates.TemplateResponse(
        request,
        "clientes.html",
        {"clientes": clientes_list, "q": q, "tenant_id": tenant_id},
    )


@router.get("/clientes/novo", response_class=HTMLResponse)
async def clientes_novo_get(request: Request) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    reps = await _get_representantes_simples(tenant_id)
    return templates.TemplateResponse(
        request, "clientes_novo.html",
        {"reps": reps, "mensagem": None, "sucesso": None, "form": {}},
    )


@router.post("/clientes/novo")
async def clientes_novo_post(request: Request) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    form = await request.form()
    nome = str(form.get("nome", "")).strip()
    cnpj = str(form.get("cnpj", "")).strip()
    representante_id = str(form.get("representante_id", "")).strip() or None
    reps = await _get_representantes_simples(tenant_id)
    try:
        from src.tenants.service import TenantService
        from src.providers.db import get_session_factory
        service = TenantService(session_factory=get_session_factory())
        await service.criar_cliente_ficticio(
            tenant_id=tenant_id, nome=nome, cnpj=cnpj, telefone="",
            representante_id=representante_id,
        )
        return RedirectResponse(url="/dashboard/clientes", status_code=302)
    except Exception as exc:
        log.error("dashboard_cliente_novo_erro", error=str(exc))
        return templates.TemplateResponse(
            request, "clientes_novo.html",
            {"reps": reps, "mensagem": str(exc), "sucesso": False,
             "form": {"nome": nome, "cnpj": cnpj, "representante_id": representante_id}},
            status_code=400,
        )


@router.get("/clientes/{cliente_id}/editar", response_class=HTMLResponse)
async def clientes_editar_get(request: Request, cliente_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    cliente = await _get_cliente_by_id(tenant_id, cliente_id)
    if cliente is None:
        return RedirectResponse(url="/dashboard/clientes", status_code=302)
    reps = await _get_representantes_simples(tenant_id)
    return templates.TemplateResponse(
        request, "clientes_editar.html",
        {"cliente": cliente, "reps": reps, "mensagem": None, "sucesso": None},
    )


@router.post("/clientes/{cliente_id}/editar")
async def clientes_editar_post(request: Request, cliente_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    form = await request.form()
    cnpj = str(form.get("cnpj", "")).strip()
    representante_id = str(form.get("representante_id", "")).strip() or None
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            await session.execute(
                text("UPDATE clientes_b2b SET cnpj=:cnpj, representante_id=:rep_id WHERE id=:id AND tenant_id=:tid"),
                {"cnpj": cnpj, "rep_id": representante_id, "id": cliente_id, "tid": tenant_id},
            )
            await session.commit()
        return RedirectResponse(url="/dashboard/clientes", status_code=302)
    except Exception as exc:
        log.error("dashboard_cliente_editar_erro", error=str(exc))
        cliente = await _get_cliente_by_id(tenant_id, cliente_id) or {}
        reps = await _get_representantes_simples(tenant_id)
        return templates.TemplateResponse(
            request, "clientes_editar.html",
            {"cliente": cliente, "reps": reps, "mensagem": str(exc), "sucesso": False},
            status_code=500,
        )


@router.post("/clientes/{cliente_id}/remover")
async def clientes_remover(request: Request, cliente_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            await session.execute(
                text("UPDATE clientes_b2b SET ativo=false WHERE id=:id AND tenant_id=:tid"),
                {"id": cliente_id, "tid": tenant_id},
            )
            await session.commit()
    except Exception as exc:
        log.error("dashboard_cliente_remover_erro", error=str(exc))
    return RedirectResponse(url="/dashboard/clientes", status_code=302)


# ─────────────────────────────────────────────
# Contatos — gestores, reps e clientes unificados
# ─────────────────────────────────────────────


@router.get("/contatos", response_class=HTMLResponse)
async def contatos(request: Request) -> Any:
    """E10/E11: lista contatos com badge de pendentes."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    lista = await _get_todos_contatos(tenant_id)
    pendentes = await _contar_contatos_pendentes(tenant_id)
    return templates.TemplateResponse(
        request, "contatos.html",
        {"contatos": lista, "pendentes": pendentes},
    )


@router.get("/contatos/novo", response_class=HTMLResponse)
async def contatos_novo_get(request: Request) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    clientes_list = await _get_clientes(tenant_id, "")
    return templates.TemplateResponse(
        request, "contatos_novo.html",
        {"clientes": clientes_list, "mensagem": None, "sucesso": None, "form": {}},
    )


@router.post("/contatos/novo")
async def contatos_novo_post(request: Request) -> Any:
    """E11 (B-27): INSERT em contacts (não UPDATE em clientes_b2b)."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    form = await request.form()
    # B-34: normalizar perfil para lowercase — template pode enviar "Gestor"/"Representante"/"Cliente"
    # Mapear "representante" → "rep" (backend usa código curto)
    perfil = str(form.get("perfil", "")).strip().lower()
    if perfil == "representante":
        perfil = "rep"
    nome = str(form.get("nome", "")).strip()
    telefone = str(form.get("telefone", "")).strip()
    cliente_b2b_id = str(form.get("cliente_b2b_id", "")).strip()
    clientes_list = await _get_clientes(tenant_id, "")
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        import json as _json
        async with get_session_factory()() as session:
            if perfil == "gestor":
                await session.execute(
                    text("INSERT INTO gestores (tenant_id, nome, telefone) VALUES (:tid, :nome, :tel)"),
                    {"tid": tenant_id, "nome": nome, "tel": telefone},
                )
            elif perfil == "rep":
                await session.execute(
                    text("INSERT INTO representantes (tenant_id, nome, telefone) VALUES (:tid, :nome, :tel)"),
                    {"tid": tenant_id, "nome": nome, "tel": telefone},
                )
            elif perfil == "cliente":
                # E11 (B-27): INSERT em contacts, não UPDATE em clientes_b2b
                # B-35: validação explícita — cliente sem cliente_b2b_id é inválido
                if not cliente_b2b_id:
                    raise ValueError("Selecione um cliente B2B para vincular ao contato.")
                # B-33: usar CAST(:channels AS JSONB) em vez de :channels::jsonb
                # para evitar ambiguidade no parser do SQLAlchemy text()
                channels = _json.dumps([{"kind": "whatsapp", "identifier": telefone, "verified": False}]) if telefone else "[]"
                account_external_id = cliente_b2b_id
                await session.execute(
                    text("""
                        INSERT INTO contacts
                            (tenant_id, nome, papel, authorized, channels, origin,
                             account_external_id, criado_em, atualizado_em)
                        VALUES
                            (:tenant_id, :nome, 'comprador', true, CAST(:channels AS JSONB),
                             'manual', :account_external_id, NOW(), NOW())
                    """),
                    {
                        "tenant_id": tenant_id,
                        "nome": nome,
                        "channels": channels,
                        "account_external_id": account_external_id,
                    },
                )
            else:
                raise ValueError("Selecione um perfil valido.")
            await session.commit()
        return RedirectResponse(url="/dashboard/contatos", status_code=302)
    except Exception as exc:
        log.error("dashboard_contatos_novo_erro", error=str(exc))
        return templates.TemplateResponse(
            request, "contatos_novo.html",
            {"clientes": clientes_list, "mensagem": str(exc), "sucesso": False,
             "form": {"perfil": perfil, "nome": nome, "telefone": telefone}},
            status_code=400,
        )


@router.get("/contatos/{perfil}/{contato_id}/editar", response_class=HTMLResponse)
async def contatos_editar_get(request: Request, perfil: str, contato_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    contato = await _get_contato_by_id(tenant_id, perfil, contato_id)
    if contato is None:
        return RedirectResponse(url="/dashboard/contatos", status_code=302)
    return templates.TemplateResponse(
        request, "contatos_editar.html",
        {"contato": contato, "mensagem": None, "sucesso": None},
    )


@router.post("/contatos/{perfil}/{contato_id}/editar")
async def contatos_editar_post(request: Request, perfil: str, contato_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    form = await request.form()
    nome = str(form.get("nome", "")).strip()
    telefone = str(form.get("telefone", "")).strip()
    nome_contato = str(form.get("nome_contato", "")).strip() or None
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        table = {"gestor": "gestores", "rep": "representantes", "cliente": "clientes_b2b"}[perfil]
        async with get_session_factory()() as session:
            if perfil == "cliente":
                await session.execute(
                    text(f"UPDATE {table} SET nome=:nome, telefone=:tel, nome_contato=:nc WHERE id=:id AND tenant_id=:tid"),
                    {"nome": nome, "tel": telefone, "nc": nome_contato, "id": contato_id, "tid": tenant_id},
                )
            else:
                await session.execute(
                    text(f"UPDATE {table} SET nome=:nome, telefone=:tel WHERE id=:id AND tenant_id=:tid"),
                    {"nome": nome, "tel": telefone, "id": contato_id, "tid": tenant_id},
                )
            await session.commit()
        return RedirectResponse(url="/dashboard/contatos", status_code=302)
    except Exception as exc:
        log.error("dashboard_contatos_editar_erro", error=str(exc))
        contato = await _get_contato_by_id(tenant_id, perfil, contato_id) or {}
        return templates.TemplateResponse(
            request, "contatos_editar.html",
            {"contato": contato, "mensagem": str(exc), "sucesso": False},
            status_code=500,
        )


@router.post("/contatos/{perfil}/{contato_id}/remover")
async def contatos_remover(request: Request, perfil: str, contato_id: str) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        table = {"gestor": "gestores", "rep": "representantes", "cliente": "clientes_b2b"}[perfil]
        async with get_session_factory()() as session:
            await session.execute(
                text(f"UPDATE {table} SET ativo=false WHERE id=:id AND tenant_id=:tid"),
                {"id": contato_id, "tid": tenant_id},
            )
            await session.commit()
    except Exception as exc:
        log.error("dashboard_contatos_remover_erro", error=str(exc))
    return RedirectResponse(url="/dashboard/contatos", status_code=302)


# ─────────────────────────────────────────────
# Gestores
# ─────────────────────────────────────────────


@router.get("/gestores", response_class=HTMLResponse)
async def gestores(request: Request) -> Any:
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    lista = await _get_gestores(tenant_id)
    return templates.TemplateResponse(request, "gestores.html", {"gestores": lista})


# ─────────────────────────────────────────────
# Representantes
# ─────────────────────────────────────────────


@router.get("/representantes", response_class=HTMLResponse)
async def representantes(request: Request) -> Any:
    """Lista de representantes com GMV do mês."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    reps = await _get_representantes_com_gmv(tenant_id)

    return templates.TemplateResponse(
        request,
        "representantes.html",
        {"representantes": reps, "tenant_id": tenant_id},
    )


# ─────────────────────────────────────────────
# Preços — upload de planilha
# ─────────────────────────────────────────────


@router.get("/precos", response_class=HTMLResponse)
async def precos_get(request: Request) -> Any:
    """Formulário de upload de planilha de preços diferenciados."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    return templates.TemplateResponse(
        request,
        "precos.html",
        {"mensagem": None, "sucesso": None},
    )


@router.post("/precos/upload")
async def precos_upload(request: Request) -> HTMLResponse:
    """Processa upload de planilha Excel de preços diferenciados.

    Delega ao CatalogService.upload_excel_precos existente.
    Retorna HTMLResponse com mensagem inline (htmx swap).
    """
    session_data = _require_session(request)
    if session_data is None:
        return HTMLResponse("<div class='error'>Sessão expirada.</div>", status_code=401)

    tenant_id = session_data["tenant_id"]

    try:
        form = await request.form()
        file = form.get("arquivo")
        if file is None or not hasattr(file, "read"):
            return HTMLResponse(
                "<div class='msg error'>Arquivo não enviado.</div>",
                status_code=400,
            )

        conteudo = await file.read()

        from src.catalog.repo import CatalogRepo
        from src.catalog.service import CatalogService
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        catalog_repo = CatalogRepo(session_factory=factory)
        catalog_service = CatalogService(repo=catalog_repo, enricher=None, embedding_client=None)  # type: ignore[arg-type]

        result = await catalog_service.processar_excel_precos(
            tenant_id=tenant_id,
            file_bytes=conteudo,
        )

        log.info(
            "dashboard_precos_upload_ok",
            tenant_id=tenant_id,
            inseridos=result.inseridos,
            linhas=result.linhas_processadas,
        )
        return HTMLResponse(
            f"<div class='msg success'>✓ {result.inseridos} preços inseridos / "
            f"{result.linhas_processadas} linhas processadas.</div>"
        )

    except Exception as exc:
        log.error("dashboard_precos_upload_erro", error=str(exc))
        return HTMLResponse(
            f"<div class='msg error'>Erro ao processar arquivo: {exc}</div>",
            status_code=500,
        )


# ─────────────────────────────────────────────
# F-07: Sync EFOS schedule (admin only) — E15
# ─────────────────────────────────────────────

_PRESET_CRONS: dict[str, str] = {
    "manual": "",
    "diario": "0 13 * * *",
    "2x_dia": "0 8,13 * * *",
    "4x_dia": "0 8,11,14,17 * * *",
    "horario": "0 * * * *",
}


def _require_admin(session_data: dict | None) -> bool:
    """Retorna True se o gestor tem role='admin'."""
    if session_data is None:
        return False
    return session_data.get("role") == "admin"


async def _get_gestor_role(tenant_id: str, session_data: dict) -> str:
    """Busca role do gestor no banco.

    Se houver gestor com role='admin' no tenant, considera que é admin.
    Simplificação para piloto JMB com apenas 1 gestor.
    """
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("SELECT COUNT(*) AS total FROM gestores WHERE tenant_id=:tid AND role='admin' AND ativo=true"),
                {"tid": tenant_id},
            )
            row = result.mappings().first()
            admin_count = int(row["total"]) if row else 0
            return "admin" if admin_count > 0 else "gestor"
    except Exception:
        return "gestor"


@router.get("/sync", response_class=HTMLResponse)
async def sync_admin_get(request: Request) -> Any:
    """E15 (F-07): página de gerenciamento de sync EFOS (admin only)."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    role = await _get_gestor_role(tenant_id, session_data)
    if role != "admin":
        from fastapi.responses import Response
        return Response(
            content="<h1>403 — Acesso restrito a administradores.</h1>",
            status_code=403,
            media_type="text/html",
        )

    schedule = await _get_sync_schedule(tenant_id)
    ultimas_runs = await _get_ultimas_sync_runs(tenant_id)
    proxima = _calcular_proxima_execucao(schedule.get("cron_expression", ""))

    # B-S10-K: detectar estado real para feedback visual (não confiar em query string)
    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)

    def _to_aware(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                v = _dt.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return None
        if hasattr(v, "tzinfo") and v.tzinfo is None:
            v = v.replace(tzinfo=_tz.utc)
        return v

    running = bool(ultimas_runs) and (ultimas_runs[0].get("status") == "running")
    last_success_recent = False
    last_error_recent = False
    last_error_msg = ""
    if ultimas_runs:
        first = ultimas_runs[0]
        st = first.get("status")
        finished = _to_aware(first.get("finished_at"))
        if finished:
            delta_min = (now_utc - finished).total_seconds() / 60
            if delta_min < 5:
                if st == "success":
                    last_success_recent = True
                elif st in ("error", "failed"):
                    last_error_recent = True
                    last_error_msg = str(first.get("error") or "")[:200]

    # "iniciado" = POST /dashboard/sync com action=run_now ocorreu recentemente
    # mas sync_runs ainda não criou row 'running' (race window de ~1-2s).
    # Usar schedule.last_triggered_at (atualizado pelo scheduler.run_now).
    triggered_recent = False
    last_trig = _to_aware(schedule.get("last_triggered_at"))
    if last_trig:
        delta_s = (now_utc - last_trig).total_seconds()
        # Mostrar "iniciado" só se: trigger recente E ainda não há running E não há resultado recente
        if 0 <= delta_s < 30 and not running and not last_success_recent and not last_error_recent:
            triggered_recent = True

    return templates.TemplateResponse(
        request,
        "sync.html",
        {
            "schedule": schedule,
            "presets": list(_PRESET_CRONS.keys()),
            "proxima_execucao": proxima,
            "ultimas_runs": ultimas_runs,
            "mensagem": None,
            "sucesso": None,
            "triggered": triggered_recent,
            "running": running,
            "last_success_recent": last_success_recent,
            "last_error_recent": last_error_recent,
            "last_error_msg": last_error_msg,
        },
    )


@router.post("/sync")
async def sync_admin_post(request: Request) -> Any:
    """E15 (F-07): salvar preset ou disparar sync agora (admin only)."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    role = await _get_gestor_role(tenant_id, session_data)
    if role != "admin":
        from fastapi.responses import Response
        return Response(
            content="<h1>403 — Acesso restrito a administradores.</h1>",
            status_code=403,
            media_type="text/html",
        )

    form = await request.form()
    action = str(form.get("action", "save")).strip()

    if action == "run_now":
        # B-37: disparar sync como background task — não bloquear o request handler
        import asyncio as _asyncio
        try:
            from src.integrations.runtime.scheduler import run_now
            efos_scheduler = request.app.state.efos_scheduler
            session_factory = request.app.state.session_factory
            redis_client = request.app.state.redis_client

            # Verificar lock Redis antes de agendar (para retornar 409 se já em andamento)
            lock_key = f"sync:efos_backup:{tenant_id}:running"
            lock_ativo = False
            if redis_client is not None:
                try:
                    lock_ativo = bool(await redis_client.get(lock_key))
                except Exception:
                    pass

            if lock_ativo:
                from fastapi.responses import HTMLResponse as _Html
                schedule = await _get_sync_schedule(tenant_id)
                ultimas_runs = await _get_ultimas_sync_runs(tenant_id)
                proxima = _calcular_proxima_execucao(schedule.get("cron_expression", ""))
                return _Html(
                    content=(
                        templates.get_template("sync.html")
                        .render(
                            request=request,
                            schedule=schedule,
                            presets=list(_PRESET_CRONS.keys()),
                            proxima_execucao=proxima,
                            ultimas_runs=ultimas_runs,
                            mensagem="Sync ja em andamento. Aguarde 30 minutos.",
                            sucesso=False,
                        )
                    ),
                    status_code=409,
                )

            # Marcar last_triggered_at IMEDIATAMENTE para que o GET subsequente
            # detecte que houve disparo (não esperar o sync terminar).
            try:
                from sqlalchemy import text as _text
                async with session_factory() as _ses:
                    await _ses.execute(
                        _text("UPDATE sync_schedule SET last_triggered_at = NOW() "
                              "WHERE tenant_id=:tid AND connector_kind='efos_backup'"),
                        {"tid": tenant_id},
                    )
                    await _ses.commit()
            except Exception as _exc_trig:
                log.warning("dashboard_sync_trigger_marker_erro", error=str(_exc_trig))

            # Disparar como background task — retorna imediatamente
            _asyncio.create_task(
                run_now(
                    scheduler=efos_scheduler,
                    tenant_id=tenant_id,
                    connector_kind="efos_backup",
                    session_factory=session_factory,
                    redis_client=redis_client,
                )
            )
        except Exception as exc:
            log.error("dashboard_sync_run_now_erro", error=str(exc))
        return RedirectResponse(url="/dashboard/sync?triggered=1", status_code=303)

    # action == "save" — salvar preset
    preset = str(form.get("preset", "diario")).strip()
    cron_expression = _PRESET_CRONS.get(preset, "0 13 * * *")
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    UPDATE sync_schedule
                    SET preset = :preset, cron_expression = :cron, atualizado_em = NOW()
                    WHERE tenant_id = :tid AND connector_kind = 'efos_backup'
                """),
                {"preset": preset, "cron": cron_expression, "tid": tenant_id},
            )
            if result.rowcount == 0:
                log.warning("dashboard_sync_update_noop", tenant_id=tenant_id)
            await session.commit()

        # Re-agendar job no APScheduler sem restart
        if preset != "manual" and cron_expression:
            try:
                from src.integrations.runtime.scheduler import reschedule_job
                efos_scheduler = request.app.state.efos_scheduler
                session_factory = request.app.state.session_factory
                redis_client = getattr(request.app.state, "redis_client", None)
                reschedule_job(
                    scheduler=efos_scheduler,
                    tenant_id=tenant_id,
                    connector_kind="efos_backup",
                    new_cron=cron_expression,
                    session_factory=session_factory,
                    redis_client=redis_client,
                )
            except Exception as exc_sched:
                log.warning("dashboard_sync_reschedule_erro", error=str(exc_sched))

    except Exception as exc:
        log.error("dashboard_sync_save_erro", error=str(exc))
    return RedirectResponse(url="/dashboard/sync", status_code=302)


async def _get_sync_schedule(tenant_id: str) -> dict:
    """Busca schedule atual do tenant."""
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    SELECT preset, cron_expression, enabled, last_triggered_at, next_run_at
                    FROM sync_schedule
                    WHERE tenant_id = :tid AND connector_kind = 'efos_backup'
                """),
                {"tid": tenant_id},
            )
            row = result.mappings().first()
            return dict(row) if row else {"preset": "diario", "cron_expression": "0 13 * * *", "enabled": True}
    except Exception as exc:
        log.error("dashboard_sync_schedule_erro", error=str(exc))
        return {"preset": "diario", "cron_expression": "0 13 * * *", "enabled": True}


async def _get_ultimas_sync_runs(tenant_id: str, limit: int = 10) -> list[dict]:
    """Busca últimas N execuções de sync."""
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    SELECT started_at, finished_at, status, rows_published, error
                    FROM sync_runs
                    WHERE tenant_id = :tid AND connector_kind = 'efos_backup'
                    ORDER BY started_at DESC
                    LIMIT :limit
                """),
                {"tid": tenant_id, "limit": limit},
            )
            return [dict(r) for r in result.mappings().all()]
    except Exception as exc:
        log.error("dashboard_sync_runs_erro", error=str(exc))
        return []


def _calcular_proxima_execucao(cron_expression: str) -> str:
    """Calcula a próxima execução de um cron."""
    if not cron_expression:
        return "Manual"
    try:
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger.from_crontab(cron_expression, timezone="America/Sao_Paulo")
        next_fire = trigger.get_next_fire_time(None, datetime.now(timezone.utc))
        if next_fire:
            return next_fire.strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    return "Desconhecido"


# ─────────────────────────────────────────────
# Configurações (read-only)
# ─────────────────────────────────────────────


@router.get("/configuracoes", response_class=HTMLResponse)
async def configuracoes(request: Request) -> Any:
    """Exibe configurações do tenant (somente leitura)."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id = session_data["tenant_id"]
    config = await _get_tenant_config(tenant_id)

    return templates.TemplateResponse(
        request,
        "configuracoes.html",
        {"config": config, "tenant_id": tenant_id},
    )


# ─────────────────────────────────────────────
# Helpers de dados
# ─────────────────────────────────────────────




_MESES_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


async def _get_kpis(tenant_id: str) -> dict[str, Any]:
    """Retorna KPIs do mês corrente (GMV, pedidos, ticket médio).

    Como o sync EFOS é esporádico (diário ou eventual) e o bot ainda gera
    poucos pedidos próprios no piloto, usamos janela MENSAL — não diária.
    Dados vêm de commerce_orders + pedidos do bot (ficticio=FALSE)
    referentes ao mês corrente, somados.

    O timestamp "atualizado em" reflete o ÚLTIMO SYNC EFOS bem-sucedido —
    não a hora atual do servidor (essa info iludiria o gestor).
    """
    try:
        from datetime import timedelta as _timedelta, timezone as _tz
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        # B-39: usar BRT (UTC-3) para calcular o mês corrente — evita off-by-one
        # na virada de mês (ex: 30/abr 22:00 UTC = 30/abr 19:00 BRT, não maio)
        _BRT = _tz(offset=_timedelta(hours=-3))
        now_brt = datetime.now(_BRT)
        # Primeiro dia do mês corrente em BRT, 00:00 BRT (convertido para UTC para query)
        mes_inicio_brt = now_brt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mes_inicio = mes_inicio_brt.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)

        async with factory() as session:
            # Pedidos do bot no mês (não fictícios)
            r_bot = await session.execute(
                text("""
                    SELECT COUNT(*) AS n_pedidos,
                           COALESCE(SUM(total_estimado), 0) AS total_gmv
                    FROM pedidos
                    WHERE tenant_id = :tenant_id
                      AND ficticio = FALSE
                      AND criado_em >= :mes_inicio
                """),
                {"tenant_id": tenant_id, "mes_inicio": mes_inicio},
            )
            row_bot = r_bot.mappings().first()
            n_bot = int(row_bot["n_pedidos"]) if row_bot else 0
            gmv_bot = row_bot["total_gmv"] if row_bot and row_bot["total_gmv"] else 0

            # Pedidos do EFOS no mês
            r_efos = await session.execute(
                text("""
                    SELECT COUNT(*) AS n_pedidos,
                           COALESCE(SUM(total), 0) AS total_gmv
                    FROM commerce_orders
                    WHERE tenant_id = :tenant_id
                      AND data_pedido >= :mes_inicio
                """),
                {"tenant_id": tenant_id, "mes_inicio": mes_inicio},
            )
            row_efos = r_efos.mappings().first()
            n_efos = int(row_efos["n_pedidos"]) if row_efos else 0
            gmv_efos = row_efos["total_gmv"] if row_efos and row_efos["total_gmv"] else 0

            # Combina bot + EFOS (sem dedupe — bot é independente)
            n = n_bot + n_efos
            from decimal import Decimal as _Dec
            gmv = _Dec(str(gmv_bot)) + _Dec(str(gmv_efos))
            ticket = (gmv / n) if n > 0 else _Dec("0")

            # Timestamp do último sync EFOS bem-sucedido (não a hora atual)
            r_sync = await session.execute(
                text("""
                    SELECT MAX(finished_at) AS ult_sync
                    FROM sync_runs
                    WHERE tenant_id = :tenant_id AND status = 'success'
                """),
                {"tenant_id": tenant_id},
            )
            row_sync = r_sync.mappings().first()
            ult_sync_utc = row_sync["ult_sync"] if row_sync else None
            if ult_sync_utc and getattr(ult_sync_utc, "tzinfo", None):
                from datetime import timezone as _tz
                ult_sync_brt = ult_sync_utc.astimezone(_tz(offset=_timedelta(hours=-3)))
                atualizado_em = ult_sync_brt.strftime("%d/%m/%Y %H:%M")
            elif ult_sync_utc:
                atualizado_em = str(ult_sync_utc)[:16]
            else:
                atualizado_em = "aguardando primeira sincronização"

            # B-39: usar mês BRT para o label (mes_inicio_brt é o primeiro dia do mês em BRT)
            mes_label = f"{_MESES_PT[mes_inicio_brt.month]}/{mes_inicio_brt.year}"

            return {
                "total_gmv": gmv,
                "n_pedidos": n,
                "ticket_medio": ticket,
                "mes_label": mes_label,
                "atualizado_em": atualizado_em,
            }
    except Exception as exc:
        log.error("dashboard_kpis_erro", error=str(exc))
        return {
            "total_gmv": 0,
            "n_pedidos": 0,
            "ticket_medio": 0,
            "mes_label": "—",
            "atualizado_em": "—",
        }


async def _get_pedidos_recentes(tenant_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Retorna os N pedidos mais recentes do tenant.

    B-17: se pedidos está vazio, faz fallback para commerce_orders (2592 pedidos EFOS).
    """
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("""
                    SELECT p.id, p.status, p.total_estimado,
                           p.criado_em, c.nome AS cliente_nome
                    FROM pedidos p
                    LEFT JOIN clientes_b2b c ON c.id = p.cliente_b2b_id AND c.tenant_id = p.tenant_id
                    WHERE p.tenant_id = :tenant_id
                    ORDER BY p.criado_em DESC
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit},
            )
            rows = result.mappings().all()
            if rows:
                return [dict(r) for r in rows]

            # B-17: fallback para commerce_orders quando pedidos está vazio.
            # cliente_nome vem NULL do EFOS — usamos JOIN com commerce_accounts_b2b
            # via cliente_codigo. Mesmo padrão para nome do representante.
            log.info("dashboard_pedidos_fallback_commerce", tenant_id=tenant_id)
            fallback = await session.execute(
                text("""
                    SELECT
                        o.numero_pedido         AS id,
                        'confirmado'            AS status,
                        o.total                 AS total_estimado,
                        o.data_pedido           AS criado_em,
                        COALESCE(NULLIF(o.cliente_nome, ''), a.nome, o.cliente_codigo) AS cliente_nome
                    FROM commerce_orders o
                    LEFT JOIN commerce_accounts_b2b a
                        ON a.tenant_id = o.tenant_id
                       AND a.codigo = o.cliente_codigo
                    WHERE o.tenant_id = :tenant_id
                    ORDER BY o.data_pedido DESC
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit},
            )
            return [dict(r) for r in fallback.mappings().all()]
    except Exception as exc:
        log.error("dashboard_pedidos_erro", error=str(exc))
        return []


async def _get_conversas_ativas(tenant_id: str) -> list[dict[str, Any]]:
    """Retorna conversas das últimas 24h."""
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, telefone, persona, iniciada_em, encerrada_em
                    FROM conversas
                    WHERE tenant_id = :tenant_id
                      AND iniciada_em > NOW() - INTERVAL '24 hours'
                    ORDER BY iniciada_em DESC
                    LIMIT 50
                """),
                {"tenant_id": tenant_id},
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        log.error("dashboard_conversas_erro", error=str(exc))
        return []


async def _get_clientes(tenant_id: str, q: str) -> list[dict[str, Any]]:
    """Retorna clientes do tenant com filtro opcional por nome/CNPJ.

    B-16: se clientes_b2b retorna 0 rows, faz fallback para commerce_accounts_b2b
    que contém os 614 clientes reais do EFOS.
    """
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            base_sql = """
                SELECT c.id, c.nome, c.cnpj, c.telefone, c.ativo, c.representante_id,
                       r.nome AS representante_nome
                FROM clientes_b2b c
                LEFT JOIN representantes r ON r.id = c.representante_id AND r.tenant_id = c.tenant_id
                WHERE c.tenant_id = :tenant_id
            """
            if q:
                result = await session.execute(
                    text(base_sql + """
                          AND (
                              unaccent(lower(c.nome)) ILIKE unaccent(lower('%' || :q || '%'))
                              OR c.cnpj ILIKE '%' || :q || '%'
                          )
                        ORDER BY c.nome LIMIT 100
                    """),
                    {"tenant_id": tenant_id, "q": q},
                )
            else:
                result = await session.execute(
                    text(base_sql + "ORDER BY c.nome LIMIT 100"),
                    {"tenant_id": tenant_id},
                )
            rows = result.mappings().all()
            if rows:
                return [dict(r) for r in rows]

            # B-16: fallback para commerce_accounts_b2b quando clientes_b2b está vazio
            log.info("dashboard_clientes_fallback_commerce", tenant_id=tenant_id)
            if q:
                fallback = await session.execute(
                    text("""
                        SELECT
                            a.external_id AS id, a.nome, a.cnpj, NULL AS telefone,
                            (a.situacao_cliente = 1) AS ativo, NULL AS representante_id,
                            v.ve_nome AS representante_nome
                        FROM commerce_accounts_b2b a
                        LEFT JOIN commerce_vendedores v
                            ON v.tenant_id = a.tenant_id AND v.ve_codigo = a.vendedor_codigo
                        WHERE a.tenant_id = :tenant_id
                          AND LOWER(a.nome) LIKE LOWER(:q_like)
                        ORDER BY a.nome LIMIT 100
                    """),
                    {"tenant_id": tenant_id, "q_like": f"%{q}%"},
                )
            else:
                fallback = await session.execute(
                    text("""
                        SELECT
                            a.external_id AS id, a.nome, a.cnpj, NULL AS telefone,
                            (a.situacao_cliente = 1) AS ativo, NULL AS representante_id,
                            v.ve_nome AS representante_nome
                        FROM commerce_accounts_b2b a
                        LEFT JOIN commerce_vendedores v
                            ON v.tenant_id = a.tenant_id AND v.ve_codigo = a.vendedor_codigo
                        WHERE a.tenant_id = :tenant_id
                        ORDER BY a.nome LIMIT 100
                    """),
                    {"tenant_id": tenant_id},
                )
            return [dict(r) for r in fallback.mappings().all()]
    except Exception as exc:
        log.error("dashboard_clientes_erro", error=str(exc))
        return []


async def _get_representantes_com_gmv(tenant_id: str) -> list[dict[str, Any]]:
    """Retorna representantes com GMV do mês corrente.

    B-21: se pedidos está vazio, faz fallback para commerce_vendedores +
    commerce_orders para exibir GMV dos dados EFOS.
    """
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        now = datetime.now(timezone.utc)
        data_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with factory() as session:
            # Tenta dados do bot primeiro
            r = await session.execute(
                text("""
                    SELECT COUNT(*) AS n_pedidos
                    FROM pedidos
                    WHERE tenant_id = :tenant_id AND ficticio = FALSE
                      AND criado_em >= :data_inicio
                """),
                {"tenant_id": tenant_id, "data_inicio": data_inicio},
            )
            row = r.mappings().first()
            n_bot = int(row["n_pedidos"]) if row else 0

            if n_bot > 0:
                from src.agents.repo import RelatorioRepo
                repo = RelatorioRepo()
                return await repo.totais_por_rep(
                    tenant_id=tenant_id,
                    data_inicio=data_inicio,
                    data_fim=now,
                    session=session,
                )

            # B-21: fallback — commerce_vendedores + commerce_orders
            log.info("dashboard_reps_fallback_commerce", tenant_id=tenant_id)
            fallback = await session.execute(
                text("""
                    SELECT
                        v.ve_codigo                              AS rep_id,
                        v.ve_nome                               AS rep_nome,
                        COUNT(o.external_id)                    AS n_pedidos,
                        COALESCE(SUM(o.total), 0)               AS total_gmv
                    FROM commerce_vendedores v
                    LEFT JOIN commerce_orders o
                        ON o.tenant_id = v.tenant_id
                       AND o.vendedor_codigo = v.ve_codigo
                       AND o.data_pedido >= :data_inicio
                    WHERE v.tenant_id = :tenant_id
                    -- TODO: filtrar somente ativos quando coluna ve_situacaovendedor existir
                    GROUP BY v.ve_codigo, v.ve_nome
                    ORDER BY total_gmv DESC
                """),
                {"tenant_id": tenant_id, "data_inicio": data_inicio},
            )
            rows = fallback.mappings().all()
            return [
                {
                    "rep_id": r["rep_id"],
                    "rep_nome": r["rep_nome"] or "Sem nome",
                    "n_pedidos": int(r["n_pedidos"]),
                    "total_gmv": r["total_gmv"],
                }
                for r in rows
            ]
    except Exception as exc:
        log.error("dashboard_reps_erro", error=str(exc))
        return []


@router.get("/top-produtos", response_class=HTMLResponse)
async def top_produtos(
    request: Request,
    dias: int = 30,
    limite: int = 10,
) -> HTMLResponse:
    """Top produtos mais vendidos no período."""
    session_payload = _verify_session(request)
    if session_payload is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)  # type: ignore[return-value]

    tenant_id = session_payload.get("tenant_id", _get_dashboard_tenant_id())

    try:
        from src.agents.repo import RelatorioRepo
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            repo = RelatorioRepo()
            produtos = await repo.top_produtos_por_periodo(tenant_id, dias, limite, session)
    except Exception as exc:
        log.error("dashboard_top_produtos_erro", error=str(exc))
        produtos = []

    ctx = {"produtos": produtos, "dias": dias, "limite": limite}

    return templates.TemplateResponse(request, "top_produtos.html", ctx)


@router.get("/feedbacks", response_class=HTMLResponse)
async def feedbacks(request: Request) -> Any:
    """Lista de feedbacks recebidos pelos agentes."""
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    tenant_id: str = session_data["tenant_id"]
    perfil_filtro: str = request.query_params.get("perfil", "")

    try:
        from src.agents.repo_feedback import FeedbackRepo
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            feedbacks_list = await FeedbackRepo().listar(
                tenant_id=tenant_id,
                session=session,
                perfil=perfil_filtro or None,
            )
    except Exception as exc:
        log.error("dashboard_feedbacks_erro", error=str(exc))
        feedbacks_list = []

    return templates.TemplateResponse(
        request,
        "feedbacks.html",
        {"feedbacks": feedbacks_list, "perfil_filtro": perfil_filtro, "tenant_id": tenant_id},
    )


async def _get_todos_contatos(tenant_id: str) -> list[dict[str, Any]]:
    """E11 (D030): UNION de contacts + gestores + representantes.

    Inclui contacts da nova tabela (D030) com badge de origem.
    """
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    SELECT id::text, nome,
                           (channels->0->>'identifier') AS telefone,
                           authorized AS ativo,
                           'contato' AS perfil,
                           origin AS nome_contato
                    FROM contacts
                    WHERE tenant_id = :tid
                    UNION ALL
                    SELECT id::text, nome, telefone, ativo, 'gestor' AS perfil, NULL AS nome_contato
                    FROM gestores WHERE tenant_id = :tid
                    UNION ALL
                    SELECT id::text, nome, telefone, ativo, 'rep' AS perfil, NULL AS nome_contato
                    FROM representantes WHERE tenant_id = :tid
                    ORDER BY nome
                """),
                {"tid": tenant_id},
            )
            return [dict(r) for r in result.mappings().all()]
    except Exception as exc:
        log.error("dashboard_contatos_erro", error=str(exc))
        return []


async def _contar_contatos_pendentes(tenant_id: str) -> int:
    """E10: conta contacts self_registered não autorizados."""
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    SELECT COUNT(*) AS total
                    FROM contacts
                    WHERE tenant_id = :tid
                      AND authorized = false
                      AND origin = 'self_registered'
                """),
                {"tid": tenant_id},
            )
            row = result.mappings().first()
            return int(row["total"]) if row else 0
    except Exception as exc:
        log.error("dashboard_pendentes_erro", error=str(exc))
        return 0


async def _get_contato_by_id(tenant_id: str, perfil: str, contato_id: str) -> dict[str, Any] | None:
    table = {"gestor": "gestores", "rep": "representantes", "cliente": "clientes_b2b"}.get(perfil)
    if not table:
        return None
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            extra = ", nome_contato" if perfil == "cliente" else ", NULL AS nome_contato"
            result = await session.execute(
                text(f"SELECT id, nome, telefone, ativo{extra} FROM {table} WHERE id=:id AND tenant_id=:tid"),
                {"id": contato_id, "tid": tenant_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            d = dict(row)
            d["perfil"] = perfil
            return d
    except Exception as exc:
        log.error("dashboard_contato_by_id_erro", error=str(exc))
        return None


async def _get_gestores(tenant_id: str) -> list[dict[str, Any]]:
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("SELECT id, nome, telefone, ativo FROM gestores WHERE tenant_id=:tid ORDER BY nome"),
                {"tid": tenant_id},
            )
            return [dict(r) for r in result.mappings().all()]
    except Exception as exc:
        log.error("dashboard_gestores_erro", error=str(exc))
        return []


async def _get_cliente_by_id(tenant_id: str, cliente_id: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("SELECT id, nome, cnpj, telefone, representante_id, ativo FROM clientes_b2b WHERE id=:id AND tenant_id=:tid"),
                {"id": cliente_id, "tid": tenant_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None
    except Exception as exc:
        log.error("dashboard_cliente_by_id_erro", error=str(exc))
        return None


async def _get_representantes_simples(tenant_id: str) -> list[dict[str, Any]]:
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("SELECT id, nome FROM representantes WHERE tenant_id=:tid AND ativo=true ORDER BY nome"),
                {"tid": tenant_id},
            )
            return [dict(r) for r in result.mappings().all()]
    except Exception as exc:
        log.error("dashboard_reps_simples_erro", error=str(exc))
        return []


async def _get_tenant_config(tenant_id: str) -> dict[str, Any]:
    """Retorna configurações do tenant."""
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("SELECT id, nome, cnpj, whatsapp_number, config_json FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
            row = result.mappings().first()
            if row is None:
                return {}
            return dict(row)
    except Exception as exc:
        log.error("dashboard_config_erro", error=str(exc))
        return {}
