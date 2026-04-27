"""Testes unitários de integrations/connectors/efos_backup/normalize.py.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
def test_normalize_vendedores_deduplica() -> None:
    """A9: normalize_vendedores aplica DISTINCT ON ve_codigo — de-duplica por filial."""
    from src.integrations.connectors.efos_backup.normalize import normalize_vendedores

    # Duas linhas para o mesmo ve_codigo (filiais diferentes)
    rows = [
        {"ve_codigo": "001", "ve_nome": "Rondinele Ritter"},
        {"ve_codigo": "001", "ve_nome": "Rondinele Ritter"},  # duplicata por filial
        {"ve_codigo": "002", "ve_nome": "João Silva"},
    ]
    result = normalize_vendedores(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 2, f"Esperado 2 vendedores, obtido {len(result)}"
    codigos = [v.ve_codigo for v in result]
    assert "001" in codigos
    assert "002" in codigos


@pytest.mark.unit
def test_normalize_vendedores_preserva_primeiro() -> None:
    """normalize_vendedores mantém a primeira ocorrência em caso de duplicata."""
    from src.integrations.connectors.efos_backup.normalize import normalize_vendedores

    rows = [
        {"ve_codigo": "001", "ve_nome": "Rondinele Ritter"},
        {"ve_codigo": "001", "ve_nome": "RONDINELE RITTER (FILIAL B)"},
    ]
    result = normalize_vendedores(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 1
    assert result[0].ve_nome == "Rondinele Ritter"  # primeira ocorrência


@pytest.mark.unit
def test_normalize_accounts_b2b_cidade_uppercase() -> None:
    """normalize_accounts_b2b converte cidades para UPPERCASE."""
    from src.integrations.connectors.efos_backup.normalize import normalize_accounts_b2b

    rows = [
        {"cl_codigo": "C001", "cl_nome": "Farmácia Central", "cl_cidade": "Vinhedo"},
        {"cl_codigo": "C002", "cl_nome": "Drogaria Norte", "cl_cidade": "campinas"},
        {"cl_codigo": "C003", "cl_nome": "Drogaria Sul", "cl_cidade": "JUNDIAÍ"},
    ]
    result = normalize_accounts_b2b(rows, tenant_id="jmb", checksum="abc123")

    cidades = {r.codigo: r.cidade for r in result}
    assert cidades["C001"] == "VINHEDO"
    assert cidades["C002"] == "CAMPINAS"
    assert cidades["C003"] == "JUNDIAÍ"


@pytest.mark.unit
def test_normalize_products_basico() -> None:
    """normalize_products normaliza lista de produtos."""
    from src.integrations.connectors.efos_backup.normalize import normalize_products

    rows = [
        {"pr_codigo": "P001", "pr_nome": "Produto A", "pr_preco": "10.50"},
        {"pr_codigo": "P002", "pr_nome": "Produto B", "pr_preco": None},
    ]
    result = normalize_products(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 2
    assert result[0].nome == "Produto A"
    assert result[0].preco_padrao == Decimal("10.50")
    assert result[1].preco_padrao is None


@pytest.mark.unit
def test_normalize_products_sem_external_id_ignorado() -> None:
    """normalize_products ignora rows sem external_id."""
    from src.integrations.connectors.efos_backup.normalize import normalize_products

    rows = [
        {"pr_codigo": "", "pr_nome": "Produto sem código"},
        {"pr_codigo": "P001", "pr_nome": "Produto válido"},
    ]
    result = normalize_products(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 1
    assert result[0].codigo == "P001"


@pytest.mark.unit
def test_normalize_orders_normaliza_mes_ano() -> None:
    """normalize_orders extrai mes e ano de data_pedido."""
    from src.integrations.connectors.efos_backup.normalize import normalize_orders

    pedido_rows = [
        {
            "pe_numero": "1001",
            "pe_cliente": "C001",
            "pe_data": "2026-04-15",
            "pe_total": "1500.00",
            "pe_vendedor": "001",
        }
    ]
    orders, items = normalize_orders(
        pedido_rows, [], [], tenant_id="jmb", checksum="abc123"
    )

    assert len(orders) == 1
    assert orders[0].mes == 4
    assert orders[0].ano == 2026


@pytest.mark.unit
def test_normalize_inventory_basico() -> None:
    """normalize_inventory normaliza saldo de estoque."""
    from src.integrations.connectors.efos_backup.normalize import normalize_inventory

    rows = [
        {"sa_id": "S001", "sa_produto": "P001", "sa_saldo": "100.5", "sa_deposito": "DEP1"},
    ]
    result = normalize_inventory(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 1
    assert result[0].saldo == Decimal("100.5")
    assert result[0].deposito == "DEP1"


@pytest.mark.unit
def test_normalize_sales_history_mes_ano() -> None:
    """normalize_sales_history extrai mes e ano."""
    from src.integrations.connectors.efos_backup.normalize import normalize_sales_history

    rows = [
        {
            "vd_id": "V001",
            "vd_cliente": "C001",
            "vd_produto": "P001",
            "vd_data": "2026-03-20",
            "vd_total": "500.00",
        }
    ]
    result = normalize_sales_history(rows, tenant_id="jmb", checksum="abc123")

    assert len(result) == 1
    assert result[0].mes == 3
    assert result[0].ano == 2026
