"""Testes unitários de agents/repo.py — ClienteB2BRepo, RepresentanteRepo, ConversaRepo.

Todos os testes são @pytest.mark.unit — sem I/O externo.
PostgreSQL mockado via AsyncMock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.types import ClienteB2B, Conversa, MensagemConversa, Persona, Representante


# ─────────────────────────────────────────────
# ClienteB2BRepo
# ─────────────────────────────────────────────


def _make_row(data: dict) -> MagicMock:  # type: ignore[type-arg]
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


@pytest.mark.unit
async def test_cliente_b2b_repo_retorna_cliente_quando_encontrado() -> None:
    """ClienteB2BRepo.get_by_telefone retorna ClienteB2B quando encontrado."""
    from src.agents.repo import ClienteB2BRepo

    session = AsyncMock()
    row_data = {
        "id": "cli-001",
        "tenant_id": "jmb",
        "nome": "Farmacia Central",
        "cnpj": "12.345.678/0001-90",
        "telefone": "5519999999999",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "representante_id": None,  # B-10: campo agora incluso no SELECT
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = _make_row(row_data)
    session.execute = AsyncMock(return_value=result)

    repo = ClienteB2BRepo()
    cliente = await repo.get_by_telefone("jmb", "5519999999999", session)

    assert cliente is not None
    assert isinstance(cliente, ClienteB2B)
    assert cliente.id == "cli-001"
    assert cliente.telefone == "5519999999999"


@pytest.mark.unit
async def test_cliente_b2b_repo_retorna_none_nao_encontrado() -> None:
    """ClienteB2BRepo.get_by_telefone retorna None quando nao encontrado."""
    from src.agents.repo import ClienteB2BRepo

    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)

    repo = ClienteB2BRepo()
    cliente = await repo.get_by_telefone("jmb", "5500000000000", session)

    assert cliente is None


@pytest.mark.unit
async def test_cliente_b2b_repo_create_executa_insert() -> None:
    """ClienteB2BRepo.create persiste cliente e retorna o mesmo objeto."""
    from src.agents.repo import ClienteB2BRepo

    session = AsyncMock()
    result = MagicMock()
    session.execute = AsyncMock(return_value=result)

    cliente = ClienteB2B(
        id="cli-002",
        tenant_id="jmb",
        nome="Farmacia Nova",
        cnpj="98.765.432/0001-10",
        telefone="5511888888888",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    repo = ClienteB2BRepo()
    retornado = await repo.create("jmb", cliente, session)

    session.execute.assert_called_once()
    assert retornado is cliente


# ─────────────────────────────────────────────
# RepresentanteRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_representante_repo_retorna_rep_quando_encontrado() -> None:
    """RepresentanteRepo.get_by_telefone retorna Representante quando encontrado."""
    from src.agents.repo import RepresentanteRepo

    session = AsyncMock()
    row_data = {
        "id": "rep-001",
        "tenant_id": "jmb",
        "usuario_id": "usr-001",
        "telefone": "5511888888888",
        "nome": "Carlos Rep",
        "ativo": True,
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = _make_row(row_data)
    session.execute = AsyncMock(return_value=result)

    repo = RepresentanteRepo()
    rep = await repo.get_by_telefone("jmb", "5511888888888", session)

    assert rep is not None
    assert isinstance(rep, Representante)
    assert rep.id == "rep-001"
    assert rep.nome == "Carlos Rep"


@pytest.mark.unit
async def test_representante_repo_retorna_none_nao_encontrado() -> None:
    """RepresentanteRepo.get_by_telefone retorna None quando nao encontrado."""
    from src.agents.repo import RepresentanteRepo

    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)

    repo = RepresentanteRepo()
    rep = await repo.get_by_telefone("jmb", "5500000000000", session)

    assert rep is None


# ─────────────────────────────────────────────
# ConversaRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_conversa_repo_get_or_create_retorna_existente() -> None:
    """ConversaRepo.get_or_create_conversa retorna conversa existente quando encontrada."""
    from src.agents.repo import ConversaRepo

    session = AsyncMock()
    row_data = {
        "id": "conv-001",
        "tenant_id": "jmb",
        "telefone": "5519999999999",
        "persona": "cliente_b2b",
        "iniciada_em": datetime(2026, 4, 15, tzinfo=timezone.utc),
        "encerrada_em": None,
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = _make_row(row_data)
    session.execute = AsyncMock(return_value=result)

    repo = ConversaRepo()
    conversa = await repo.get_or_create_conversa(
        tenant_id="jmb",
        telefone="5519999999999@s.whatsapp.net",
        persona=Persona.CLIENTE_B2B,
        session=session,
    )

    assert conversa.id == "conv-001"
    assert conversa.persona == Persona.CLIENTE_B2B
    # Deve ter chamado execute apenas uma vez (SELECT)
    assert session.execute.call_count == 1


@pytest.mark.unit
async def test_conversa_repo_get_or_create_cria_nova() -> None:
    """ConversaRepo.get_or_create_conversa cria nova conversa quando nao existe."""
    from src.agents.repo import ConversaRepo

    session = AsyncMock()
    row_nova = {
        "id": "conv-novo",
        "tenant_id": "jmb",
        "telefone": "5519999999999",
        "persona": "cliente_b2b",
        "iniciada_em": datetime(2026, 4, 15, tzinfo=timezone.utc),
        "encerrada_em": None,
    }
    # Primeira chamada (SELECT) retorna None; segunda (INSERT) retorna nova linha
    result_vazio = MagicMock()
    result_vazio.mappings.return_value.first.return_value = None

    result_novo = MagicMock()
    result_novo.mappings.return_value.first.return_value = _make_row(row_nova)

    session.execute = AsyncMock(side_effect=[result_vazio, result_novo])

    repo = ConversaRepo()
    conversa = await repo.get_or_create_conversa(
        tenant_id="jmb",
        telefone="5519999999999",
        persona=Persona.CLIENTE_B2B,
        session=session,
    )

    assert conversa.id == "conv-novo"
    assert session.execute.call_count == 2


@pytest.mark.unit
async def test_conversa_repo_add_mensagem_retorna_mensagem() -> None:
    """ConversaRepo.add_mensagem persiste e retorna MensagemConversa."""
    from src.agents.repo import ConversaRepo

    session = AsyncMock()
    row_data = {
        "id": "msg-001",
        "conversa_id": "conv-001",
        "role": "user",
        "conteudo": "Quero ver o catalogo",
        "criado_em": datetime(2026, 4, 15, tzinfo=timezone.utc),
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = _make_row(row_data)
    session.execute = AsyncMock(return_value=result)

    repo = ConversaRepo()
    msg = await repo.add_mensagem(
        conversa_id="conv-001",
        role="user",
        conteudo="Quero ver o catalogo",
        session=session,
    )

    assert isinstance(msg, MensagemConversa)
    assert msg.role == "user"
    assert msg.conversa_id == "conv-001"


@pytest.mark.unit
async def test_conversa_repo_get_historico_retorna_lista() -> None:
    """ConversaRepo.get_historico retorna lista de MensagemConversa."""
    from src.agents.repo import ConversaRepo

    session = AsyncMock()
    rows = [
        _make_row({
            "id": f"msg-{i:03d}",
            "conversa_id": "conv-001",
            "role": "user" if i % 2 == 0 else "assistant",
            "conteudo": f"Mensagem {i}",
            "criado_em": datetime(2026, 4, 15, tzinfo=timezone.utc),
        })
        for i in range(3)
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)

    repo = ConversaRepo()
    historico = await repo.get_historico(conversa_id="conv-001", limit=10, session=session)

    assert len(historico) == 3
    assert all(isinstance(m, MensagemConversa) for m in historico)


@pytest.mark.unit
async def test_conversa_repo_encerrar_conversa_executa_update() -> None:
    """ConversaRepo.encerrar_conversa executa UPDATE com conversa_id."""
    from src.agents.repo import ConversaRepo

    session = AsyncMock()
    result = MagicMock()
    session.execute = AsyncMock(return_value=result)

    repo = ConversaRepo()
    await repo.encerrar_conversa(conversa_id="conv-001", session=session)

    session.execute.assert_called_once()
    sql = str(session.execute.call_args[0][0])
    assert "encerrada_em" in sql.lower() or "UPDATE" in sql.upper()


@pytest.mark.unit
def test_conversa_repo_normalize_phone() -> None:
    """ConversaRepo._normalize_phone remove sufixo @s.whatsapp.net."""
    from src.agents.repo import ConversaRepo

    repo = ConversaRepo()
    assert repo._normalize_phone("5519999999999@s.whatsapp.net") == "5519999999999"
    assert repo._normalize_phone("5519999999999") == "5519999999999"
