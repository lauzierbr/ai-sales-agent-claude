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

_COOKIE_NAME = "dashboard_session"
_COOKIE_MAX_AGE = 8 * 3600  # 8h em segundos


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
    """
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
        log.warning("dashboard_login_senha_incorreta")
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": True},
            status_code=401,
        )

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
        secure=False,  # True em produção com HTTPS
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
        {"kpis": kpis, "pedidos": pedidos, "conversas": conversas, "tenant_id": tenant_id},
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
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    lista = await _get_todos_contatos(tenant_id)
    return templates.TemplateResponse(request, "contatos.html", {"contatos": lista})


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
    session_data = _require_session(request)
    if session_data is None:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    tenant_id = session_data["tenant_id"]
    form = await request.form()
    perfil = str(form.get("perfil", "")).strip()
    nome = str(form.get("nome", "")).strip()
    telefone = str(form.get("telefone", "")).strip()
    cliente_b2b_id = str(form.get("cliente_b2b_id", "")).strip()
    nome_contato = str(form.get("nome_contato", "")).strip() or None
    clientes_list = await _get_clientes(tenant_id, "")
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
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
            elif perfil == "cliente" and cliente_b2b_id:
                await session.execute(
                    text("UPDATE clientes_b2b SET telefone=:tel, nome_contato=:nc WHERE id=:id AND tenant_id=:tid"),
                    {"tel": telefone, "nc": nome_contato, "id": cliente_b2b_id, "tid": tenant_id},
                )
            else:
                raise ValueError("Selecione um perfil válido e, para Cliente, selecione o cliente.")
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

        conteudo = await file.read()  # type: ignore[union-attr]

        from src.catalog.service import CatalogService
        from src.catalog.repo import CatalogRepo
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        catalog_repo = CatalogRepo(session_factory=factory)
        catalog_service = CatalogService(repo=catalog_repo, enricher=None, embedding_client=None)  # type: ignore[arg-type]

        async with factory() as db_session:
            n = await catalog_service.upload_excel_precos(
                tenant_id=tenant_id,
                conteudo=conteudo,
                session=db_session,
            )

        log.info("dashboard_precos_upload_ok", tenant_id=tenant_id, n_registros=n)
        return HTMLResponse(
            f"<div class='msg success'>✓ {n} preços atualizados com sucesso.</div>"
        )

    except Exception as exc:
        log.error("dashboard_precos_upload_erro", error=str(exc))
        return HTMLResponse(
            f"<div class='msg error'>Erro ao processar arquivo: {exc}</div>",
            status_code=500,
        )


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


async def _get_kpis(tenant_id: str) -> dict[str, Any]:
    """Retorna KPIs do dia (GMV, pedidos, ticket médio)."""
    try:
        from datetime import timedelta

        from src.agents.repo import RelatorioRepo
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        repo = RelatorioRepo()
        now = datetime.now(timezone.utc)
        data_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async with factory() as session:
            totais = await repo.totais_periodo(
                tenant_id=tenant_id,
                data_inicio=data_inicio,
                data_fim=now,
                session=session,
            )
        return {
            **totais,
            "atualizado_em": now.strftime("%H:%M:%S"),
        }
    except Exception as exc:
        log.error("dashboard_kpis_erro", error=str(exc))
        return {"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0, "atualizado_em": "--:--:--"}


async def _get_pedidos_recentes(tenant_id: str, limit: int = 10) -> list[dict]:
    """Retorna os N pedidos mais recentes do tenant."""
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
                    LEFT JOIN clientes_b2b c ON c.id = p.cliente_b2b_id
                    WHERE p.tenant_id = :tenant_id
                    ORDER BY p.criado_em DESC
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit},
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        log.error("dashboard_pedidos_erro", error=str(exc))
        return []


async def _get_conversas_ativas(tenant_id: str) -> list[dict]:
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


async def _get_clientes(tenant_id: str, q: str) -> list[dict]:
    """Retorna clientes do tenant com filtro opcional por nome/CNPJ."""
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            if q:
                result = await session.execute(
                    text("""
                        SELECT id, nome, cnpj, telefone, ativo, representante_id
                        FROM clientes_b2b
                        WHERE tenant_id = :tenant_id
                          AND (
                              unaccent(lower(nome)) ILIKE unaccent(lower('%' || :q || '%'))
                              OR cnpj ILIKE '%' || :q || '%'
                          )
                        ORDER BY nome
                        LIMIT 100
                    """),
                    {"tenant_id": tenant_id, "q": q},
                )
            else:
                result = await session.execute(
                    text("""
                        SELECT id, nome, cnpj, telefone, ativo, representante_id
                        FROM clientes_b2b
                        WHERE tenant_id = :tenant_id
                        ORDER BY nome
                        LIMIT 100
                    """),
                    {"tenant_id": tenant_id},
                )
            rows = result.mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        log.error("dashboard_clientes_erro", error=str(exc))
        return []


async def _get_representantes_com_gmv(tenant_id: str) -> list[dict]:
    """Retorna representantes com GMV do mês corrente."""
    try:
        from datetime import timedelta

        from src.agents.repo import RelatorioRepo
        from src.providers.db import get_session_factory

        factory = get_session_factory()
        repo = RelatorioRepo()
        now = datetime.now(timezone.utc)
        data_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with factory() as session:
            return await repo.totais_por_rep(
                tenant_id=tenant_id,
                data_inicio=data_inicio,
                data_fim=now,
                session=session,
            )
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


async def _get_todos_contatos(tenant_id: str) -> list[dict]:
    try:
        from sqlalchemy import text
        from src.providers.db import get_session_factory
        async with get_session_factory()() as session:
            result = await session.execute(
                text("""
                    SELECT id, nome, telefone, ativo, 'gestor' AS perfil, NULL AS nome_contato FROM gestores
                    WHERE tenant_id = :tid
                    UNION ALL
                    SELECT id, nome, telefone, ativo, 'rep' AS perfil, NULL AS nome_contato FROM representantes
                    WHERE tenant_id = :tid
                    UNION ALL
                    SELECT id, nome, telefone, ativo, 'cliente' AS perfil, nome_contato FROM clientes_b2b
                    WHERE tenant_id = :tid
                    ORDER BY nome
                """),
                {"tid": tenant_id},
            )
            return [dict(r) for r in result.mappings().all()]
    except Exception as exc:
        log.error("dashboard_contatos_erro", error=str(exc))
        return []


async def _get_contato_by_id(tenant_id: str, perfil: str, contato_id: str) -> dict | None:
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


async def _get_gestores(tenant_id: str) -> list[dict]:
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


async def _get_cliente_by_id(tenant_id: str, cliente_id: str) -> dict | None:
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


async def _get_representantes_simples(tenant_id: str) -> list[dict]:
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
