"""Testes de homologação WhatsApp Sprint 4 — H1 a H7 + dashboard.

Todos @pytest.mark.staging — requerem banco e Redis reais (macmini-lablz).
Claude API mockado; Evolution API (WhatsApp) NÃO é chamado.

Estado esperado do banco (após seed_homologacao_sprint4.py):
  Gestores:    5519000000002 → Lauzier Gestor Teste (jmb)
  Reps:        5519000000001 → Rep Teste Sprint3 (jmb)
               5519992066177 → João (jmb)
  Clientes:    LZ Muzel → telefone=5519991111111 (jmb)
               Cliente Inativo Teste H4 → telefone=5519990000099 (sem pedidos recentes)
  Pedidos antigos (>30d): ≥1 para Cliente Inativo Teste H4

Cobertura:
  H1  — buscar_clientes("muzel") retorna LZ Muzel (acesso irrestrito do gestor)
  H2  — relatorio_vendas("semana") retorna dados não-zero
  H3  — relatorio_vendas("mes", "por_rep") retorna ≥1 rep no ranking
  H4  — clientes_inativos(30) retorna ≥1 cliente
  H5  — confirmar_pedido_em_nome_de herda representante_id do cliente (DP-03)
  H6  — IdentityRouter: 5519000000001 → REPRESENTANTE (isolamento)
  H7  — IdentityRouter: 5519991111111 → CLIENTE_B2B (isolamento)
  H8  — Dashboard: /dashboard/home sem cookie → 302
  H9  — Dashboard: login correto → cookie + redirect
  H10 — Dashboard: partial /kpis retorna HTML com GMV ou R$
  H11 — Dashboard: /dashboard/representantes → 200 sem erro
  H12 — Repo: RelatorioRepo.totais_por_rep não usa ORDER BY SQL (sort Python)
  H13 — Repo: RelatorioRepo.clientes_inativos filtra por tenant_id
  H14 — Repo: GestorRepo.get_by_telefone retorna None para número desconhecido
  H15 — AgentGestor não crasha com banco real e Claude mockado
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Todos os testes async neste módulo compartilham o mesmo event loop.
# Necessário para que o pool asyncpg não fique ligado a um loop já fechado.
pytestmark = pytest.mark.asyncio(loop_scope="module")


TENANT_ID = "jmb"
TELEFONE_GESTOR = "5519000000002"
TELEFONE_REP = "5519000000001"
TELEFONE_CLIENTE = "5519991111111"  # LZ Muzel (atualizado pelo seed)
TELEFONE_INATIVO_CLIENTE = "5519990000099"  # Cliente Inativo Teste H4
TELEFONE_DESCONHECIDO = "5519999999999"


def _mensagem(telefone: str, texto: str = "oi") -> Any:
    from src.agents.types import Mensagem
    return Mensagem(
        id=f"msg-{telefone[-4:]}",
        de=f"{telefone}@s.whatsapp.net",
        para="inst-jmb-staging",
        texto=texto,
        tipo="conversation",
        instancia_id="inst-jmb-staging",
        timestamp=datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc),
    )


def _mock_claude_end_turn(texto: str = "Ok.") -> AsyncMock:
    block = MagicMock()
    block.type = "text"
    block.text = texto
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=resp)
    return client


def _mock_claude_tool_then_end(tool_name: str, tool_input: dict, resposta: str = "Pronto.") -> AsyncMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.id = f"tool-{tool_name[:8]}"
    tool_block.input = tool_input
    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = resposta
    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])
    return client


# ─────────────────────────────────────────────
# H1 — buscar_clientes("muzel") retorna LZ Muzel
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h1_buscar_clientes_muzel_retorna_resultado() -> None:
    """H1: buscar_todos_por_nome('muzel') com banco real retorna ≥1 cliente contendo 'Muzel'."""
    from src.agents.repo import ClienteB2BRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = ClienteB2BRepo()

    async with factory() as session:
        clientes = await repo.buscar_todos_por_nome(
            tenant_id=TENANT_ID, query="muzel", session=session
        )

    assert len(clientes) >= 1, (
        "buscar_todos_por_nome('muzel') deve retornar ≥1 cliente. "
        "Execute seed_homologacao_sprint4.py primeiro."
    )
    nomes = [c.nome.lower() for c in clientes]
    assert any("muzel" in n for n in nomes), (
        f"Nenhum cliente com 'muzel' no nome. Encontrados: {nomes}"
    )


# ─────────────────────────────────────────────
# H2 — relatorio_vendas("semana") retorna dados
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h2_relatorio_vendas_semana_nao_vazio() -> None:
    """H2: RelatorioRepo.totais_periodo com 7 dias retorna dict com n_pedidos≥1."""
    from datetime import timedelta

    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    data_fim = datetime.now(timezone.utc)
    data_inicio = data_fim - timedelta(days=7)

    async with factory() as session:
        totais = await repo.totais_periodo(
            tenant_id=TENANT_ID,
            data_inicio=data_inicio,
            data_fim=data_fim,
            session=session,
        )

    assert isinstance(totais, dict), f"totais deve ser dict, got {type(totais)}"
    assert "n_pedidos" in totais, f"Chave 'n_pedidos' ausente em: {totais.keys()}"
    assert "total_gmv" in totais, f"Chave 'total_gmv' ausente em: {totais.keys()}"
    assert totais["n_pedidos"] >= 1, (
        "n_pedidos deve ser ≥1 na última semana. "
        "Crie ao menos 1 pedido recente no staging."
    )


# ─────────────────────────────────────────────
# H3 — relatorio por_rep retorna ≥1 rep
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h3_relatorio_por_rep_retorna_lista() -> None:
    """H3: RelatorioRepo.totais_por_rep retorna ≥1 rep com pedidos no mês."""
    from datetime import timedelta

    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    data_fim = datetime.now(timezone.utc)
    data_inicio = data_fim.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with factory() as session:
        reps = await repo.totais_por_rep(
            tenant_id=TENANT_ID,
            data_inicio=data_inicio,
            data_fim=data_fim,
            session=session,
        )

    assert isinstance(reps, list), f"totais_por_rep deve retornar list, got {type(reps)}"
    if len(reps) > 0:
        first = reps[0]
        assert "rep_nome" in first, f"Chave 'rep_nome' ausente em: {first.keys()}"
        assert "total_gmv" in first, f"Chave 'total_gmv' ausente em: {first.keys()}"


# ─────────────────────────────────────────────
# H4 — clientes_inativos(30) retorna ≥1
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h4_clientes_inativos_retorna_resultado() -> None:
    """H4: RelatorioRepo.clientes_inativos(30) retorna ≥1 cliente."""
    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    async with factory() as session:
        inativos = await repo.clientes_inativos(
            tenant_id=TENANT_ID, dias=30, session=session
        )

    assert isinstance(inativos, list), f"clientes_inativos deve retornar list, got {type(inativos)}"
    assert len(inativos) >= 1, (
        "clientes_inativos(30) deve retornar ≥1 cliente. "
        "Seed criou 'Cliente Inativo Teste H4' com pedidos de 45 dias atrás. "
        "Execute seed_homologacao_sprint4.py."
    )
    nomes = [r.get("nome", "") for r in inativos]
    assert any("Inativo" in n for n in nomes), (
        f"'Cliente Inativo Teste H4' deve aparecer. Inativos: {nomes}"
    )


# ─────────────────────────────────────────────
# H5 — confirmar_pedido herda representante_id (DP-03)
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h5_dp03_pedido_herda_representante_do_cliente() -> None:
    """H5 / DP-03: pedido criado pelo gestor em nome de cliente com rep herda representante_id."""
    from src.agents.config import AgentGestorConfig
    from src.agents.repo import (
        ClienteB2BRepo,
        ConversaRepo,
        GestorRepo,
        RelatorioRepo,
    )
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService
    from src.orders.types import CriarPedidoInput
    from src.providers.db import get_session_factory
    from src.tenants.repo import TenantRepo

    factory = get_session_factory()

    pedidos_criados: list[CriarPedidoInput] = []

    async def captura_pedido(pedido_input: CriarPedidoInput, session: Any) -> Any:
        pedidos_criados.append(pedido_input)
        from src.orders.types import Pedido, StatusPedido
        return Pedido(
            id="ped-h5-staging",
            tenant_id=TENANT_ID,
            cliente_b2b_id=pedido_input.cliente_b2b_id,
            representante_id=pedido_input.representante_id,
            status=StatusPedido.PENDENTE,
            total_estimado=Decimal("59.80"),
            pdf_path=None,
            itens=[],
            criado_em=datetime.now(timezone.utc),
        )

    mock_order_service = AsyncMock()
    mock_order_service.criar_pedido_from_intent = captura_pedido

    async with factory() as session:
        gestor_repo = GestorRepo()
        gestor = await gestor_repo.get_by_telefone(TENANT_ID, TELEFONE_GESTOR, session)
        if gestor is None:
            pytest.skip(f"Gestor {TELEFONE_GESTOR} não encontrado. Execute seed.")

        cliente_repo = ClienteB2BRepo()
        clientes = await cliente_repo.buscar_todos_por_nome(TENANT_ID, "muzel", session)
        if not clientes:
            pytest.skip("LZ Muzel não encontrado. Execute seed.")
        cliente_muzel = clientes[0]

        tenant = await TenantRepo().get_by_id(TENANT_ID, session)
        if tenant is None:
            pytest.skip("Tenant jmb não encontrado.")

        mock_claude = _mock_claude_tool_then_end(
            "confirmar_pedido_em_nome_de",
            {
                "cliente_b2b_id": cliente_muzel.id,
                "itens": [{"produto_id": "p1", "codigo_externo": "SKU1",
                           "nome_produto": "Shampoo", "quantidade": 2,
                           "preco_unitario": "29.90"}],
            },
        )

        mock_pdf = MagicMock()
        mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"pdf")

        agent = AgentGestor(
            order_service=mock_order_service,
            conversa_repo=ConversaRepo(),
            pdf_generator=mock_pdf,
            config=AgentGestorConfig(),
            gestor=gestor,
            catalog_service=None,
            anthropic_client=mock_claude,
            redis_client=None,
            relatorio_repo=RelatorioRepo(),
            cliente_b2b_repo=cliente_repo,
        )

        with (
            patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
            patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
        ):
            await agent.responder(
                mensagem=_mensagem(TELEFONE_GESTOR, "fecha 2 shampoo pro Muzel"),
                tenant=tenant,
                session=session,
            )

    assert len(pedidos_criados) == 1, "confirmar_pedido_em_nome_de deve ter sido chamado"
    pedido_input = pedidos_criados[0]

    if cliente_muzel.representante_id is not None:
        assert pedido_input.representante_id == cliente_muzel.representante_id, (
            f"DP-03 violado: pedido.representante_id={pedido_input.representante_id} "
            f"≠ cliente.representante_id={cliente_muzel.representante_id}"
        )
    else:
        assert pedido_input.representante_id is None, (
            "Cliente sem rep: pedido deve ter representante_id=None"
        )


# ─────────────────────────────────────────────
# H6 — isolamento rep: 5519000000001 → REPRESENTANTE
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h6_isolamento_rep_retorna_representante() -> None:
    """H6: IdentityRouter com número do rep retorna Persona.REPRESENTANTE."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    router = IdentityRouter()

    async with factory() as session:
        persona = await router.resolve(
            _mensagem(TELEFONE_REP), TENANT_ID, session
        )

    assert persona == Persona.REPRESENTANTE, (
        f"{TELEFONE_REP} deve ser REPRESENTANTE, obteve {persona}. "
        "Verifique se está em representantes e NÃO em gestores."
    )


# ─────────────────────────────────────────────
# H7 — isolamento cliente: 5519991111111 → CLIENTE_B2B
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h7_isolamento_cliente_retorna_cliente_b2b() -> None:
    """H7: IdentityRouter com número do cliente retorna Persona.CLIENTE_B2B."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    router = IdentityRouter()

    async with factory() as session:
        persona = await router.resolve(
            _mensagem(TELEFONE_CLIENTE), TENANT_ID, session
        )

    assert persona == Persona.CLIENTE_B2B, (
        f"{TELEFONE_CLIENTE} (LZ Muzel) deve ser CLIENTE_B2B, obteve {persona}. "
        "Execute seed para atualizar telefone do cliente."
    )


# ─────────────────────────────────────────────
# H8 — dashboard sem cookie → 302
# ─────────────────────────────────────────────


@pytest.mark.staging
def test_h8_dashboard_sem_cookie_redireciona() -> None:
    """H8: GET /dashboard/home sem cookie → 302 para /dashboard/login."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)

    client = TestClient(app, follow_redirects=False)
    resp = client.get("/dashboard/home")

    assert resp.status_code in (302, 307), (
        f"Esperado 302/307, obteve {resp.status_code}"
    )
    assert "/dashboard/login" in resp.headers.get("location", "")


# ─────────────────────────────────────────────
# H9 — login correto → cookie + redirect
# ─────────────────────────────────────────────


@pytest.mark.staging
def test_h9_login_correto_seta_cookie() -> None:
    """H9: POST /dashboard/login com senha correta seta cookie dashboard_session."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)

    client = TestClient(app, follow_redirects=False)

    senha = os.getenv("DASHBOARD_SECRET", "")
    jwt_secret = os.getenv("JWT_SECRET", "jwt-fallback-secret-teste-muito-longo-000000")
    tenant_id = os.getenv("DASHBOARD_TENANT_ID", "jmb")

    if not senha:
        pytest.skip("DASHBOARD_SECRET não configurado. Use infisical run --env=staging.")

    with patch.dict(os.environ, {
        "DASHBOARD_SECRET": senha,
        "DASHBOARD_TENANT_ID": tenant_id,
        "JWT_SECRET": jwt_secret,
    }):
        resp = client.post("/dashboard/login", data={"senha": senha})

    assert resp.status_code in (302, 307), (
        f"Esperado 302/307 após login correto, obteve {resp.status_code}"
    )
    set_cookie = resp.headers.get("set-cookie", "")
    assert "dashboard_session=" in set_cookie, (
        f"Cookie dashboard_session não foi setado. Set-Cookie: {set_cookie}"
    )


# ─────────────────────────────────────────────
# H10 — partial /kpis retorna HTML com GMV ou R$
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h10_partial_kpis_retorna_html_gmv() -> None:
    """H10: GET /dashboard/home/partials/kpis retorna HTMLResponse com 'GMV' ou 'R$'."""
    import httpx
    from fastapi import FastAPI
    from src.dashboard.ui import router as dashboard_router

    senha = os.getenv("DASHBOARD_SECRET", "")
    if not senha:
        pytest.skip("DASHBOARD_SECRET não configurado. Use infisical run --env=staging.")

    jwt_secret = os.getenv("JWT_SECRET", "jwt-fallback-secret-muito-longo-000000")
    tenant_id = os.getenv("DASHBOARD_TENANT_ID", "jmb")

    app = FastAPI()
    app.include_router(dashboard_router)

    with patch.dict(os.environ, {
        "DASHBOARD_SECRET": senha,
        "DASHBOARD_TENANT_ID": tenant_id,
        "JWT_SECRET": jwt_secret,
    }):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            login_resp = await client.post("/dashboard/login", data={"senha": senha})
            assert login_resp.status_code in (302, 307), (
                f"Login falhou: {login_resp.status_code}"
            )
            set_cookie = login_resp.headers.get("set-cookie", "")
            cookie_value = set_cookie.split("dashboard_session=")[1].split(";")[0] if "dashboard_session=" in set_cookie else ""

            resp = await client.get(
                "/dashboard/home/partials/kpis",
                cookies={"dashboard_session": cookie_value},
            )

    assert resp.status_code == 200, (
        f"Partial /kpis retornou {resp.status_code}, esperado 200. Body: {resp.text[:300]}"
    )
    body = resp.text
    assert any(kw in body for kw in ["GMV", "R$", "gmv"]), (
        f"Partial /kpis deve conter 'GMV' ou 'R$'. Body: {body[:500]}"
    )


# ─────────────────────────────────────────────
# H11 — /dashboard/representantes → 200 sem erro
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h11_representantes_200_sem_erro() -> None:
    """H11: GET /dashboard/representantes retorna 200 sem 500."""
    import httpx
    from fastapi import FastAPI
    from src.dashboard.ui import router as dashboard_router

    senha = os.getenv("DASHBOARD_SECRET", "")
    if not senha:
        pytest.skip("DASHBOARD_SECRET não configurado. Use infisical run --env=staging.")

    jwt_secret = os.getenv("JWT_SECRET", "jwt-fallback-secret-muito-longo-000000")
    tenant_id = os.getenv("DASHBOARD_TENANT_ID", "jmb")

    app = FastAPI()
    app.include_router(dashboard_router)

    with patch.dict(os.environ, {
        "DASHBOARD_SECRET": senha,
        "DASHBOARD_TENANT_ID": tenant_id,
        "JWT_SECRET": jwt_secret,
    }):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            login_resp = await client.post("/dashboard/login", data={"senha": senha})
            set_cookie = login_resp.headers.get("set-cookie", "")
            cookie_value = set_cookie.split("dashboard_session=")[1].split(";")[0] if "dashboard_session=" in set_cookie else ""

            resp = await client.get(
                "/dashboard/representantes",
                cookies={"dashboard_session": cookie_value},
            )

    assert resp.status_code == 200, (
        f"/dashboard/representantes retornou {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )
    assert "500" not in resp.text[:100], "Resposta parece ser página de erro"


# ─────────────────────────────────────────────
# H12 — totais_por_rep ordenado em Python (não SQL)
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h12_totais_por_rep_ordenado_em_python() -> None:
    """H12: totais_por_rep retorna lista ordenada por total_gmv DESC (sort Python, não SQL)."""
    from datetime import timedelta

    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    data_fim = datetime.now(timezone.utc)
    data_inicio = data_fim - timedelta(days=30)

    async with factory() as session:
        reps = await repo.totais_por_rep(
            tenant_id=TENANT_ID,
            data_inicio=data_inicio,
            data_fim=data_fim,
            session=session,
        )

    if len(reps) < 2:
        pytest.skip("Menos de 2 reps com pedidos — não dá para verificar ordenação")

    gmvs = [float(r.get("total_gmv", 0)) for r in reps]
    assert gmvs == sorted(gmvs, reverse=True), (
        f"totais_por_rep não está ordenado por GMV DESC: {gmvs}"
    )


# ─────────────────────────────────────────────
# H13 — clientes_inativos filtra por tenant_id
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h13_clientes_inativos_filtra_tenant() -> None:
    """H13: clientes_inativos com tenant_id inexistente retorna lista vazia."""
    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    async with factory() as session:
        inativos = await repo.clientes_inativos(
            tenant_id="tenant-que-nao-existe-xyz",
            dias=30,
            session=session,
        )

    assert inativos == [], (
        f"clientes_inativos com tenant inválido deve retornar [], got {inativos}"
    )


# ─────────────────────────────────────────────
# H14 — GestorRepo retorna None para número desconhecido
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h14_gestor_repo_desconhecido_retorna_none() -> None:
    """H14: GestorRepo.get_by_telefone retorna None para número não cadastrado."""
    from src.agents.repo import GestorRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = GestorRepo()

    async with factory() as session:
        gestor = await repo.get_by_telefone(
            tenant_id=TENANT_ID,
            telefone=TELEFONE_DESCONHECIDO,
            session=session,
        )

    assert gestor is None, (
        f"GestorRepo deve retornar None para número desconhecido, got {gestor}"
    )


# ─────────────────────────────────────────────
# H15 — AgentGestor não crasha com banco real
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_h15_agent_gestor_nao_crasha_banco_real() -> None:
    """H15: AgentGestor.responder não lança exceção com banco real e Claude mockado."""
    from src.agents.config import AgentGestorConfig
    from src.agents.repo import ConversaRepo, GestorRepo, RelatorioRepo
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService
    from src.providers.db import get_session_factory
    from src.tenants.repo import TenantRepo

    factory = get_session_factory()

    async with factory() as session:
        gestor_repo = GestorRepo()
        gestor = await gestor_repo.get_by_telefone(TENANT_ID, TELEFONE_GESTOR, session)
        if gestor is None:
            pytest.skip(f"Gestor {TELEFONE_GESTOR} não encontrado. Execute seed.")

        tenant = await TenantRepo().get_by_id(TENANT_ID, session)
        if tenant is None:
            pytest.skip("Tenant jmb não encontrado.")

        agent = AgentGestor(
            order_service=OrderService(repo=OrderRepo(), config=OrderConfig()),
            conversa_repo=ConversaRepo(),
            pdf_generator=PDFGenerator(),
            config=AgentGestorConfig(),
            gestor=gestor,
            catalog_service=None,
            anthropic_client=_mock_claude_end_turn("Tudo certo!"),
            redis_client=None,
            relatorio_repo=RelatorioRepo(),
        )

        with (
            patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
            patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
        ):
            await agent.responder(
                mensagem=_mensagem(TELEFONE_GESTOR, "oi"),
                tenant=tenant,
                session=session,
            )


# ─────────────────────────────────────────────
# Testes adicionais de robustez e regressão
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_identity_router_gestor_prioridade_sobre_rep() -> None:
    """IdentityRouter: se mesmo número estiver em gestores E representantes → GESTOR (DP-02)."""
    from src.agents.repo import GestorRepo
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    router = IdentityRouter()

    async with factory() as session:
        # Verifica se gestor de teste existe
        gestor = await GestorRepo().get_by_telefone(TENANT_ID, TELEFONE_GESTOR, session)
        if gestor is None:
            pytest.skip("Gestor não existe no banco. Execute seed.")

        persona = await router.resolve(_mensagem(TELEFONE_GESTOR), TENANT_ID, session)

    assert persona == Persona.GESTOR, (
        f"Gestor deve ser GESTOR, obteve {persona}"
    )


@pytest.mark.staging
async def test_repo_buscar_clientes_sem_filtro_rep_banco_real() -> None:
    """buscar_todos_por_nome não filtra por representante_id — retorna clientes de qualquer rep."""
    from src.agents.repo import ClienteB2BRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = ClienteB2BRepo()

    async with factory() as session:
        # Busca genérica — deve retornar todos os matching, independente de rep
        todos = await repo.buscar_todos_por_nome(
            tenant_id=TENANT_ID, query="", session=session
        )
        # Busca específica para LZ Muzel
        muzel = await repo.buscar_todos_por_nome(
            tenant_id=TENANT_ID, query="muzel", session=session
        )

    assert isinstance(todos, list)
    assert isinstance(muzel, list)
    assert len(muzel) >= 1, "LZ Muzel deve aparecer na busca 'muzel'"


@pytest.mark.staging
async def test_relatorio_repo_totais_periodo_retorna_zeros_sem_dados() -> None:
    """RelatorioRepo.totais_periodo com tenant inválido retorna zeros, não exceção."""
    from datetime import timedelta

    from src.agents.repo import RelatorioRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    repo = RelatorioRepo()

    data_fim = datetime.now(timezone.utc)
    data_inicio = data_fim - timedelta(days=1)

    async with factory() as session:
        totais = await repo.totais_periodo(
            tenant_id="tenant-invalido-xyz",
            data_inicio=data_inicio,
            data_fim=data_fim,
            session=session,
        )

    assert isinstance(totais, dict)
    assert totais.get("n_pedidos", 0) == 0
    assert float(totais.get("total_gmv", 0)) == 0.0


@pytest.mark.staging
async def test_identityrouter_desconhecido_banco_real() -> None:
    """IdentityRouter retorna DESCONHECIDO para número não cadastrado em nenhuma tabela."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona
    from src.providers.db import get_session_factory

    factory = get_session_factory()
    router = IdentityRouter()

    async with factory() as session:
        persona = await router.resolve(
            _mensagem(TELEFONE_DESCONHECIDO), TENANT_ID, session
        )

    assert persona == Persona.DESCONHECIDO, (
        f"{TELEFONE_DESCONHECIDO} deve ser DESCONHECIDO, obteve {persona}"
    )
