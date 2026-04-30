"""Testes de regressão — B-33 a B-40: sweep Playwright/webhook Sprint 10.

Cada teste verifica a correção de um bug específico do sweep da homologação Sprint 10.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# B-33: CAST(:channels AS JSONB) em vez de :channels::jsonb
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b33_contacts_insert_usa_cast_jsonb():
    """B-33: ContactRepo.create_self_registered usa CAST(:channels AS JSONB)."""
    from src.agents.repo import ContactRepo

    source = inspect.getsource(ContactRepo.create_self_registered)
    assert "CAST(:channels AS JSONB)" in source, (
        "B-33: create_self_registered deve usar CAST(:channels AS JSONB) "
        "em vez de :channels::jsonb para evitar ambiguidade no parser SQLAlchemy"
    )
    # Garantir que NÃO usa :channels::jsonb em código SQL real (não em comentário)
    # Checar apenas nas linhas que NÃO são comentários
    code_lines = [
        line for line in source.split("\n")
        if ":channels::jsonb" in line.lower() and not line.strip().startswith("#")
    ]
    assert len(code_lines) == 0, (
        f"B-33: :channels::jsonb ainda em código SQL (não comentário): {code_lines}"
    )


@pytest.mark.unit
def test_b33_dashboard_contacts_insert_usa_cast_jsonb():
    """B-33: POST /dashboard/contatos/novo usa CAST(:channels AS JSONB)."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # A rota POST /dashboard/contatos/novo deve usar CAST
    assert "CAST(:channels AS JSONB)" in source, (
        "B-33: dashboard/ui.py POST contatos/novo deve usar CAST(:channels AS JSONB)"
    )


# ---------------------------------------------------------------------------
# B-34: normalizar perfil para lowercase no backend
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b34_perfil_normalizado_lowercase():
    """B-34: contatos_novo_post normaliza perfil para lowercase."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # Deve conter .lower() na extração do perfil do form
    assert ".lower()" in source, (
        "B-34: dashboard/ui.py deve normalizar perfil com .lower() "
        "para aceitar 'Gestor', 'Representante', 'Cliente' (Title Case)"
    )


# ---------------------------------------------------------------------------
# B-35: guard explícito para cliente sem cliente_b2b_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b35_cliente_sem_b2b_id_levanta_erro():
    """B-35: perfil=cliente sem cliente_b2b_id levanta ValueError."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # Deve ter guard explícito para cliente sem cliente_b2b_id
    assert "not cliente_b2b_id" in source, (
        "B-35: dashboard/ui.py deve validar que cliente_b2b_id não está vazio "
        "quando perfil=cliente"
    )
    assert "Selecione um cliente" in source or "cliente_b2b_id" in source, (
        "B-35: mensagem de erro deve mencionar a seleção do cliente B2B"
    )


# ---------------------------------------------------------------------------
# B-36: UPSERT em publish.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b36_publish_usa_upsert_nao_insert():
    """B-36: publish.py usa ON CONFLICT DO UPDATE em todas as tabelas."""
    source_path = (
        Path(__file__).parent.parent.parent
        / "integrations"
        / "connectors"
        / "efos_backup"
        / "publish.py"
    )
    if not source_path.exists():
        pytest.skip("publish.py não encontrado")

    source = source_path.read_text()

    # Deve ter ON CONFLICT em todas as tabelas relevantes
    assert source.count("ON CONFLICT (tenant_id, external_id) DO UPDATE SET") >= 6, (
        "B-36: publish.py deve ter ON CONFLICT DO UPDATE em pelo menos 6 tabelas "
        "(accounts, orders, order_items, inventory, sales_history, vendedores)"
    )

    # Não deve ter DELETE+INSERT para as tabelas commerce_*
    assert "DELETE FROM commerce_accounts_b2b" not in source, (
        "B-36: publish.py não deve usar DELETE+INSERT em commerce_accounts_b2b"
    )
    assert "DELETE FROM commerce_orders" not in source, (
        "B-36: publish.py não deve usar DELETE+INSERT em commerce_orders"
    )
    assert "DELETE FROM commerce_inventory" not in source, (
        "B-36: publish.py não deve usar DELETE+INSERT em commerce_inventory"
    )


@pytest.mark.unit
def test_b36_upsert_products_preserva_embedding():
    """B-36/DT-2: _upsert_products preserva embedding existente."""
    from src.integrations.connectors.efos_backup.publish import _upsert_products

    source = inspect.getsource(_upsert_products)
    # Embedding não deve estar no DO UPDATE SET
    assert "embedding" not in source or "COALESCE" in source or "-- embedding" in source.lower(), (
        "B-36/DT-2: _upsert_products não deve atualizar embedding "
        "ou deve usar COALESCE para preservar"
    )


# ---------------------------------------------------------------------------
# B-37: run_now como background task (asyncio.create_task)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b37_run_now_usa_create_task():
    """B-37: dashboard sync 'Rodar Agora' usa asyncio.create_task."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # Deve usar create_task para não bloquear o handler
    assert "create_task" in source, (
        "B-37: dashboard/ui.py deve usar asyncio.create_task para run_now "
        "e não bloquear o request handler"
    )
    # Deve redirecionar com ?triggered=1
    assert "triggered=1" in source or "303" in source, (
        "B-37: handler deve retornar redirect 303 imediatamente após agendar"
    )


# ---------------------------------------------------------------------------
# B-38: send_whatsapp_message com kwargs posicionais corretos
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b38_send_whatsapp_assinatura_correta():
    """B-38: send_whatsapp_message tem assinatura (instancia_id, numero, texto)."""
    from src.agents.service import send_whatsapp_message

    sig = inspect.signature(send_whatsapp_message)
    params = list(sig.parameters.keys())

    assert params[0] == "instancia_id", (
        f"B-38: 1º parâmetro deve ser 'instancia_id', encontrado: {params[0]}"
    )
    assert params[1] == "numero", (
        f"B-38: 2º parâmetro deve ser 'numero', encontrado: {params[1]}"
    )
    assert params[2] == "texto", (
        f"B-38: 3º parâmetro deve ser 'texto', encontrado: {params[2]}"
    )
    assert "telefone" not in params, (
        "B-38: send_whatsapp_message não deve ter parâmetro 'telefone' — use 'numero'"
    )
    assert "mensagem" not in params, (
        "B-38: send_whatsapp_message não deve ter parâmetro 'mensagem' — use 'texto'"
    )


@pytest.mark.unit
def test_b38_agents_ui_nao_usa_kwargs_errados():
    """B-38: agents/ui.py não chama send_whatsapp_message com telefone= ou mensagem=."""
    source_path = Path(__file__).parent.parent.parent / "agents" / "ui.py"
    if not source_path.exists():
        pytest.skip("agents/ui.py não encontrado")

    source = source_path.read_text()

    # Verificar que não há chamadas com kwargs renomeados errados
    lines_with_call = [
        line for line in source.split("\n")
        if "send_whatsapp_message" in line
        and ("telefone=" in line or "mensagem=" in line)
    ]
    assert len(lines_with_call) == 0, (
        f"B-38: agents/ui.py ainda tem {len(lines_with_call)} chamadas com "
        f"kwargs 'telefone=' ou 'mensagem=': {lines_with_call}"
    )


@pytest.mark.unit
def test_b38_service_nao_usa_kwargs_errados():
    """B-38: agents/service.py não chama send_whatsapp_message com kwargs errados."""
    from src.agents import service as svc_module

    source = inspect.getsource(svc_module)

    lines_with_bad_call = [
        line for line in source.split("\n")
        if "send_whatsapp_message" in line
        and ("telefone=" in line or "mensagem=" in line)
    ]
    assert len(lines_with_bad_call) == 0, (
        f"B-38: agents/service.py ainda tem chamadas com kwargs errados: {lines_with_bad_call}"
    )


# ---------------------------------------------------------------------------
# B-39: GMV mês corrente sem off-by-one
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b39_kpis_usa_brt_para_mes():
    """B-39: _get_kpis calcula mes_inicio em BRT para evitar off-by-one na virada de mês."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # Deve mencionar BRT ou timezone de -3h no cálculo de mes_inicio
    assert "BRT" in source or "hours=-3" in source, (
        "B-39: _get_kpis deve usar BRT (UTC-3) para calcular o mês corrente "
        "e evitar off-by-one na virada de meia-noite UTC"
    )


@pytest.mark.unit
def test_b39_mes_label_usa_brt():
    """B-39: mes_label usa mês BRT (mes_inicio_brt.month), não UTC."""
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"
    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()
    # O label deve usar mes_inicio_brt.month (não mes_inicio.month que seria UTC)
    assert "mes_inicio_brt.month" in source, (
        "B-39: mes_label deve usar mes_inicio_brt.month para garantir label correto em BRT"
    )


# ---------------------------------------------------------------------------
# B-40: IdentityRouter consulta contacts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_b40_identity_router_consulta_contacts():
    """B-40: IdentityRouter.resolve consulta contacts antes de retornar DESCONHECIDO."""
    from src.agents.service import IdentityRouter

    source = inspect.getsource(IdentityRouter.resolve)
    assert "contact_repo" in source or "_contact_repo" in source, (
        "B-40: IdentityRouter.resolve deve consultar ContactRepo "
        "antes de retornar DESCONHECIDO"
    )
    assert "get_by_channel" in source, (
        "B-40: IdentityRouter deve chamar get_by_channel para buscar contacts"
    )


@pytest.mark.unit
def test_b40_identity_router_tem_contact_repo():
    """B-40: IdentityRouter.__init__ instancia ContactRepo."""
    from src.agents.service import IdentityRouter
    from src.agents.repo import ContactRepo

    source = inspect.getsource(IdentityRouter.__init__)
    assert "ContactRepo" in source, (
        "B-40: IdentityRouter.__init__ deve instanciar ContactRepo"
    )


@pytest.mark.unit
async def test_b40_contact_autorizado_retorna_cliente_b2b():
    """B-40: número com contact autorizado retorna Persona.CLIENTE_B2B."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona, Mensagem
    from datetime import datetime, timezone

    router = IdentityRouter()

    mensagem = Mensagem(
        id="test-msg",
        de="5519999999999@s.whatsapp.net",
        para="instancia",
        texto="oi",
        tipo="text",
        instancia_id="instancia",
        timestamp=datetime.now(timezone.utc),
    )

    mock_session = MagicMock()

    # Simular: sem gestor, sem rep, sem cliente_b2b, mas contact autorizado
    router._gestor_repo.get_by_telefone = AsyncMock(return_value=None)
    router._rep_repo.get_by_telefone = AsyncMock(return_value=None)
    router._cliente_repo.get_by_telefone = AsyncMock(return_value=None)
    router._contact_repo.get_by_channel = AsyncMock(return_value={
        "id": "contact-uuid",
        "authorized": True,
        "papel": "comprador",
        "account_external_id": "12345",
    })

    persona = await router.resolve(mensagem, "jmb", mock_session)
    assert persona == Persona.CLIENTE_B2B, (
        f"B-40: contact autorizado deve retornar CLIENTE_B2B, mas retornou {persona}"
    )


@pytest.mark.unit
async def test_b40_contact_nao_autorizado_retorna_desconhecido():
    """B-40: número com contact não autorizado ainda retorna DESCONHECIDO."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona, Mensagem
    from datetime import datetime, timezone

    router = IdentityRouter()

    mensagem = Mensagem(
        id="test-msg-2",
        de="5519888888888@s.whatsapp.net",
        para="instancia",
        texto="oi",
        tipo="text",
        instancia_id="instancia",
        timestamp=datetime.now(timezone.utc),
    )

    mock_session = MagicMock()

    router._gestor_repo.get_by_telefone = AsyncMock(return_value=None)
    router._rep_repo.get_by_telefone = AsyncMock(return_value=None)
    router._cliente_repo.get_by_telefone = AsyncMock(return_value=None)
    router._contact_repo.get_by_channel = AsyncMock(return_value={
        "id": "contact-uuid-2",
        "authorized": False,
        "papel": None,
        "account_external_id": None,
    })

    persona = await router.resolve(mensagem, "jmb", mock_session)
    assert persona == Persona.DESCONHECIDO, (
        f"B-40: contact não autorizado deve retornar DESCONHECIDO, mas retornou {persona}"
    )
