"""Testes unitários do CatalogRepo.

Testa a estrutura das queries SQL sem I/O real.
Verifica obrigatoriamente que tenant_id está em todo SQL (critério A3).
Inclui testes funcionais com session factory mockada para cobertura ≥ 60%.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.catalog.repo import CatalogRepo
from src.catalog.types import (
    PrecoDiferenciado,
    ProdutoBruto,
    ProdutoEnriquecido,
    StatusEnriquecimento,
)


# ─────────────────────────────────────────────
# Helpers para criação de mocks
# ─────────────────────────────────────────────


def _make_row(**kwargs: Any) -> MagicMock:
    """Cria um RowProxy mock com valores padrão sobreponíveis."""
    row = MagicMock()
    row.id = kwargs.get("id", "00000000-0000-0000-0000-000000000001")
    row.tenant_id = kwargs.get("tenant_id", "jmb")
    row.codigo_externo = kwargs.get("codigo_externo", "SKU001")
    row.nome_bruto = kwargs.get("nome_bruto", "SHAM HID")
    row.nome = kwargs.get("nome", "Shampoo")
    row.marca = kwargs.get("marca", "Natura")
    row.categoria = kwargs.get("categoria", "Cabelos")
    row.tags = kwargs.get("tags", ["shampoo"])
    row.texto_rag = kwargs.get("texto_rag", "Shampoo hidratante.")
    row.meta_agente = kwargs.get("meta_agente", None)
    row.preco_padrao = kwargs.get("preco_padrao", None)
    row.url_imagem = kwargs.get("url_imagem", None)
    row.status_enriquecimento = kwargs.get("status_enriquecimento", "pendente")
    row.criado_em = kwargs.get("criado_em", datetime.now(timezone.utc))
    row.atualizado_em = kwargs.get("atualizado_em", datetime.now(timezone.utc))
    return row


def _make_session_factory(
    fetchone_result: Any = None,
    fetchall_result: Any = None,
) -> tuple[MagicMock, AsyncMock]:
    """Cria mock de async_sessionmaker com contexto assíncrono.

    Retorna (mock_factory, mock_session) para assertivas adicionais.
    """
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone_result
    mock_result.fetchall.return_value = fetchall_result or []

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=ctx)
    return mock_factory, mock_session


@pytest.mark.unit
def test_todos_metodos_publicos_tem_tenant_id() -> None:
    """Todo método público assíncrono de CatalogRepo deve ter parâmetro tenant_id.

    Este é o critério A3 do sprint contract — verificado estruturalmente.
    """
    metodos_publicos = [
        name for name, method in inspect.getmembers(CatalogRepo, predicate=inspect.isfunction)
        if not name.startswith("_") and inspect.iscoroutinefunction(method)
    ]

    assert len(metodos_publicos) > 0, "CatalogRepo deve ter métodos públicos assíncronos"

    sem_tenant_id = []
    for nome in metodos_publicos:
        sig = inspect.signature(getattr(CatalogRepo, nome))
        if "tenant_id" not in sig.parameters:
            sem_tenant_id.append(nome)

    assert sem_tenant_id == [], (
        f"Métodos de CatalogRepo sem parâmetro tenant_id: {sem_tenant_id}"
    )


@pytest.mark.unit
def test_sql_busca_embedding_contem_tenant_id_filter() -> None:
    """O SQL de buscar_por_embedding deve conter filtro tenant_id = :tenant_id.

    Verificação estrutural da string SQL — critério A3.
    """
    import ast
    import textwrap

    source = inspect.getsource(CatalogRepo.buscar_por_embedding)
    # Verifica que o SQL menciona tenant_id como filtro
    assert "tenant_id = :tenant_id" in source or "tenant_id=:tenant_id" in source, (
        "buscar_por_embedding não filtra por tenant_id no SQL — violação de isolamento"
    )


@pytest.mark.unit
def test_sql_listar_produtos_contem_tenant_id_filter() -> None:
    """O SQL de listar_produtos deve conter filtro tenant_id = :tenant_id."""
    source = inspect.getsource(CatalogRepo.listar_produtos)
    assert "tenant_id = :tenant_id" in source or "tenant_id=:tenant_id" in source, (
        "listar_produtos não filtra por tenant_id no SQL"
    )


@pytest.mark.unit
def test_sql_get_produto_contem_tenant_id_filter() -> None:
    """O SQL de get_produto deve conter filtro tenant_id = :tenant_id."""
    source = inspect.getsource(CatalogRepo.get_produto)
    assert "tenant_id = :tenant_id" in source or "tenant_id=:tenant_id" in source, (
        "get_produto não filtra por tenant_id no SQL"
    )


@pytest.mark.unit
def test_sql_update_status_contem_tenant_id_filter() -> None:
    """O SQL de update_status deve conter filtro tenant_id = :tenant_id."""
    source = inspect.getsource(CatalogRepo.update_status)
    assert "tenant_id = :tenant_id" in source or "tenant_id=:tenant_id" in source, (
        "update_status não filtra por tenant_id no SQL"
    )


@pytest.mark.unit
def test_sql_busca_embedding_usa_operador_pgvector() -> None:
    """buscar_por_embedding deve usar o operador <=> (cosine distance) do pgvector."""
    source = inspect.getsource(CatalogRepo.buscar_por_embedding)
    assert "<=>" in source, "buscar_por_embedding deve usar operador <=> do pgvector"
    # Implementação usa interpolação f-string ('vec_str'::vector) em vez de CAST bind param
    # porque asyncpg não infere o tipo 'vector' em prepared statements (workaround Sprint 2).
    assert "::vector" in source, (
        "buscar_por_embedding deve fazer cast para o tipo vector do pgvector"
    )


@pytest.mark.unit
def test_row_to_produto_normaliza_cnpj_tags() -> None:
    """_row_to_produto deve lidar com tags None (retorna lista vazia)."""
    row = MagicMock()
    row.id = "00000000-0000-0000-0000-000000000001"
    row.tenant_id = "jmb"
    row.codigo_externo = "SKU001"
    row.nome_bruto = "Produto"
    row.nome = None
    row.marca = None
    row.categoria = None
    row.tags = None
    row.texto_rag = None
    row.meta_agente = None
    row.preco_padrao = None
    row.url_imagem = None
    row.status_enriquecimento = "pendente"
    from datetime import datetime, timezone
    row.criado_em = datetime.now(timezone.utc)
    row.atualizado_em = datetime.now(timezone.utc)

    produto = CatalogRepo._row_to_produto(row)

    assert produto.tags == []
    assert produto.meta_agente == {}
    assert produto.preco_padrao is None
    assert produto.tenant_id == "jmb"


@pytest.mark.unit
def test_row_to_produto_com_meta_agente_json_string() -> None:
    """_row_to_produto deve parsear meta_agente quando vier como string JSON."""
    import json

    row = MagicMock()
    row.id = "00000000-0000-0000-0000-000000000002"
    row.tenant_id = "jmb"
    row.codigo_externo = "SKU002"
    row.nome_bruto = "Produto"
    row.nome = "Nome"
    row.marca = "Marca"
    row.categoria = "Cat"
    row.tags = ["t1", "t2"]
    row.texto_rag = "texto"
    row.meta_agente = json.dumps({"unidade": "ml", "quantidade": 300})
    row.preco_padrao = "29.90"
    row.url_imagem = "https://img.com/x.jpg"
    row.status_enriquecimento = "enriquecido"
    row.criado_em = datetime.now(timezone.utc)
    row.atualizado_em = datetime.now(timezone.utc)

    produto = CatalogRepo._row_to_produto(row)

    assert produto.meta_agente == {"unidade": "ml", "quantidade": 300}
    assert produto.preco_padrao == Decimal("29.90")
    assert produto.tags == ["t1", "t2"]
    assert produto.status_enriquecimento == StatusEnriquecimento.ENRIQUECIDO


# ─────────────────────────────────────────────
# Testes funcionais com session factory mockada
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_upsert_produto_bruto_retorna_produto() -> None:
    """upsert_produto_bruto deve executar SQL e retornar Produto."""
    row = _make_row(status_enriquecimento="pendente")
    mock_factory, mock_session = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    produto_bruto = ProdutoBruto(
        codigo_externo="SKU001",
        nome_bruto="SHAM HID NAT 300ML",
        tenant_id="jmb",
        preco_padrao=Decimal("29.90"),
        categoria="Cabelos",
    )

    resultado = await repo.upsert_produto_bruto("jmb", produto_bruto)

    assert resultado.codigo_externo == "SKU001"
    assert resultado.tenant_id == "jmb"
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.unit
async def test_update_produto_enriquecido_retorna_produto_atualizado() -> None:
    """update_produto_enriquecido deve atualizar campos e retornar Produto."""
    row = _make_row(
        nome="Shampoo Enriquecido",
        status_enriquecimento="enriquecido",
    )
    mock_factory, mock_session = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    enriquecido = ProdutoEnriquecido(
        codigo_externo="SKU001",
        tenant_id="jmb",
        nome="Shampoo Enriquecido",
        marca="Natura",
        categoria="Cabelos",
        tags=["shampoo"],
        texto_rag="Texto RAG.",
        meta_agente={"unidade": "ml"},
    )

    resultado = await repo.update_produto_enriquecido("jmb", "SKU001", enriquecido)

    assert resultado.nome == "Shampoo Enriquecido"
    assert resultado.status_enriquecimento == StatusEnriquecimento.ENRIQUECIDO
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.unit
async def test_update_produto_enriquecido_nao_encontrado_levanta_value_error() -> None:
    """update_produto_enriquecido deve levantar ValueError se row for None."""
    mock_factory, _ = _make_session_factory(fetchone_result=None)

    repo = CatalogRepo(mock_factory)
    enriquecido = ProdutoEnriquecido(
        codigo_externo="INEXISTENTE",
        tenant_id="jmb",
        nome="N",
        marca="M",
        categoria="C",
        tags=[],
        texto_rag="t",
        meta_agente={},
    )

    with pytest.raises(ValueError, match="Produto não encontrado"):
        await repo.update_produto_enriquecido("jmb", "INEXISTENTE", enriquecido)


@pytest.mark.unit
async def test_update_embedding_executa_sql() -> None:
    """update_embedding deve executar SQL com o vetor formatado."""
    mock_factory, mock_session = _make_session_factory()

    repo = CatalogRepo(mock_factory)
    embedding = [0.1, 0.2, 0.3]
    produto_id = UUID("00000000-0000-0000-0000-000000000001")

    await repo.update_embedding("jmb", produto_id, embedding)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()
    # Verifica que o embedding foi formatado como string de vetor
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["embedding"] == "[0.1,0.2,0.3]"
    assert call_params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_update_status_retorna_produto_com_novo_status() -> None:
    """update_status deve atualizar e retornar produto."""
    row = _make_row(status_enriquecimento="ativo")
    mock_factory, mock_session = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    produto_id = UUID("00000000-0000-0000-0000-000000000001")

    resultado = await repo.update_status("jmb", produto_id, StatusEnriquecimento.ATIVO)

    assert resultado.status_enriquecimento == StatusEnriquecimento.ATIVO
    mock_session.commit.assert_called_once()


@pytest.mark.unit
async def test_update_status_nao_encontrado_levanta_value_error() -> None:
    """update_status deve levantar ValueError se produto não existir."""
    mock_factory, _ = _make_session_factory(fetchone_result=None)

    repo = CatalogRepo(mock_factory)
    produto_id = UUID("00000000-0000-0000-0000-000000000099")

    with pytest.raises(ValueError, match="Produto não encontrado"):
        await repo.update_status("jmb", produto_id, StatusEnriquecimento.ATIVO)


@pytest.mark.unit
async def test_get_produto_retorna_produto_quando_encontrado() -> None:
    """get_produto deve retornar Produto quando row existe."""
    row = _make_row()
    mock_factory, _ = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    produto_id = UUID("00000000-0000-0000-0000-000000000001")

    resultado = await repo.get_produto("jmb", produto_id)

    assert resultado is not None
    assert resultado.codigo_externo == "SKU001"


@pytest.mark.unit
async def test_get_produto_retorna_none_quando_nao_encontrado() -> None:
    """get_produto deve retornar None quando produto não existe."""
    mock_factory, _ = _make_session_factory(fetchone_result=None)

    repo = CatalogRepo(mock_factory)
    produto_id = UUID("00000000-0000-0000-0000-000000000099")

    resultado = await repo.get_produto("jmb", produto_id)

    assert resultado is None


@pytest.mark.unit
async def test_listar_produtos_sem_filtro_retorna_lista() -> None:
    """listar_produtos sem status deve retornar todos os produtos do tenant."""
    rows = [_make_row(codigo_externo="SKU001"), _make_row(codigo_externo="SKU002")]
    mock_factory, _ = _make_session_factory(fetchall_result=rows)

    repo = CatalogRepo(mock_factory)
    resultado = await repo.listar_produtos("jmb")

    assert len(resultado) == 2
    assert resultado[0].codigo_externo == "SKU001"
    assert resultado[1].codigo_externo == "SKU002"


@pytest.mark.unit
async def test_listar_produtos_com_filtro_status() -> None:
    """listar_produtos com status deve executar SQL com filtro adicional."""
    row = _make_row(status_enriquecimento="enriquecido")
    mock_factory, mock_session = _make_session_factory(fetchall_result=[row])

    repo = CatalogRepo(mock_factory)
    resultado = await repo.listar_produtos(
        "jmb", status=StatusEnriquecimento.ENRIQUECIDO
    )

    assert len(resultado) == 1
    # Verifica que o parâmetro status foi passado
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["status"] == "enriquecido"
    assert call_params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_listar_produtos_sem_embedding_retorna_lista() -> None:
    """listar_produtos_sem_embedding deve retornar produtos sem vetor."""
    rows = [_make_row(texto_rag="texto", status_enriquecimento="enriquecido")]
    mock_factory, _ = _make_session_factory(fetchall_result=rows)

    repo = CatalogRepo(mock_factory)
    resultado = await repo.listar_produtos_sem_embedding("jmb", limit=10)

    assert len(resultado) == 1


@pytest.mark.unit
async def test_buscar_por_embedding_retorna_pares_produto_distancia() -> None:
    """buscar_por_embedding deve retornar list[tuple[Produto, float]]."""
    row = _make_row()
    row.distancia = 0.15  # campo extra do SELECT com <=>

    mock_factory, mock_session = _make_session_factory(fetchall_result=[row])

    repo = CatalogRepo(mock_factory)
    embedding = [0.1] * 1536

    resultado = await repo.buscar_por_embedding("jmb", embedding, limit=5)

    assert len(resultado) == 1
    produto, distancia = resultado[0]
    assert produto.codigo_externo == "SKU001"
    assert distancia == 0.15
    # Confirma que tenant_id e distancia_maxima foram passados como bind params.
    # embedding NÃO é bind param — é interpolado no f-string SQL (workaround asyncpg Sprint 2).
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"
    assert "distancia_maxima" in call_params


@pytest.mark.unit
async def test_upsert_preco_diferenciado_executa_sql() -> None:
    """upsert_preco_diferenciado deve executar SQL sem retornar valor."""
    mock_factory, mock_session = _make_session_factory()

    repo = CatalogRepo(mock_factory)
    preco = PrecoDiferenciado(
        tenant_id="jmb",
        codigo_produto="SKU001",
        cliente_cnpj="12345678000190",
        preco_cliente=Decimal("25.00"),
    )

    await repo.upsert_preco_diferenciado("jmb", preco)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.unit
async def test_get_preco_diferenciado_retorna_decimal() -> None:
    """get_preco_diferenciado deve retornar Decimal quando preço existe."""
    row = MagicMock()
    row.preco_cliente = "25.00"
    mock_factory, _ = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    resultado = await repo.get_preco_diferenciado("jmb", "SKU001", "12.345.678/0001-90")

    assert resultado == Decimal("25.00")


@pytest.mark.unit
async def test_get_preco_diferenciado_retorna_none() -> None:
    """get_preco_diferenciado deve retornar None quando não existir."""
    mock_factory, _ = _make_session_factory(fetchone_result=None)

    repo = CatalogRepo(mock_factory)
    resultado = await repo.get_preco_diferenciado("jmb", "SKU999", "00000000000000")

    assert resultado is None


@pytest.mark.unit
async def test_get_preco_diferenciado_normaliza_cnpj() -> None:
    """get_preco_diferenciado deve normalizar CNPJ para apenas dígitos."""
    row = MagicMock()
    row.preco_cliente = "15.50"
    mock_factory, mock_session = _make_session_factory(fetchone_result=row)

    repo = CatalogRepo(mock_factory)
    # Passa CNPJ formatado — deve normalizar para dígitos
    await repo.get_preco_diferenciado("jmb", "SKU001", "12.345.678/0001-90")

    call_params = mock_session.execute.call_args[0][1]
    assert call_params["cliente_cnpj"] == "12345678000190"
