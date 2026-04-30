"""Tipos do domínio Catalog — Pydantic models, enums e protocols.

Camada Types: sem imports internos do projeto.
Imports permitidos: stdlib, pydantic, typing.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class StatusEnriquecimento(StrEnum):
    """Estado do produto no pipeline de enriquecimento."""

    PENDENTE = "pendente"
    ENRIQUECIDO = "enriquecido"
    EM_REVISAO = "em_revisao"
    ATIVO = "ativo"
    INATIVO = "inativo"


# ─────────────────────────────────────────────
# Modelos de dados do crawler
# ─────────────────────────────────────────────


class Categoria:
    """Categoria de produto extraída do site EFOS."""

    __slots__ = ("id", "nome", "url")

    def __init__(self, id: str, nome: str, url: str | None = None) -> None:
        self.id = id
        self.nome = nome
        self.url = url

    def __repr__(self) -> str:
        return f"Categoria(id={self.id!r}, nome={self.nome!r})"


class ProdutoBruto:
    """Produto extraído pelo crawler — dados brutos sem enriquecimento."""

    __slots__ = (
        "codigo_externo",
        "nome_bruto",
        "tenant_id",
        "preco_padrao",
        "descricao_bruta",
        "url_imagem",
        "imagem_local",
        "categoria",
        "url_produto",
    )

    def __init__(
        self,
        codigo_externo: str,
        nome_bruto: str,
        tenant_id: str,
        preco_padrao: Decimal | None = None,
        descricao_bruta: str | None = None,
        url_imagem: str | None = None,
        imagem_local: str | None = None,
        categoria: str | None = None,
        url_produto: str | None = None,
    ) -> None:
        self.codigo_externo = codigo_externo
        self.nome_bruto = nome_bruto
        self.tenant_id = tenant_id
        self.preco_padrao = preco_padrao
        self.descricao_bruta = descricao_bruta
        self.url_imagem = url_imagem
        self.imagem_local = imagem_local
        self.categoria = categoria
        self.url_produto = url_produto

    def __repr__(self) -> str:
        return f"ProdutoBruto(codigo={self.codigo_externo!r}, nome={self.nome_bruto!r})"


# ─────────────────────────────────────────────
# Modelos de enriquecimento
# ─────────────────────────────────────────────


class ProdutoEnriquecido:
    """Produto enriquecido pelo EnricherAgent (Claude Haiku)."""

    __slots__ = (
        "codigo_externo",
        "tenant_id",
        "nome",
        "marca",
        "categoria",
        "tags",
        "texto_rag",
        "meta_agente",
    )

    def __init__(
        self,
        codigo_externo: str,
        tenant_id: str,
        nome: str,
        marca: str,
        categoria: str,
        tags: list[str],
        texto_rag: str,
        meta_agente: dict[str, Any],
    ) -> None:
        self.codigo_externo = codigo_externo
        self.tenant_id = tenant_id
        self.nome = nome
        self.marca = marca
        self.categoria = categoria
        self.tags = tags
        self.texto_rag = texto_rag
        self.meta_agente = meta_agente

    def __repr__(self) -> str:
        return f"ProdutoEnriquecido(codigo={self.codigo_externo!r}, nome={self.nome!r})"


# ─────────────────────────────────────────────
# Modelo completo do produto (registro do BD)
# ─────────────────────────────────────────────


class CommerceProduct:
    """Produto completo mapeado de commerce_products — registro do banco de dados.

    E18 (Sprint 10): renomeado de Produto para CommerceProduct para refletir a
    tabela de origem (commerce_products, não mais produtos legado).

    O campo `embedding` (vector[1536]) não é incluído aqui para evitar
    carregar 1536 floats em respostas de lista. Fetched separadamente quando necessário.
    """

    __slots__ = (
        "id",
        "tenant_id",
        "codigo_externo",
        "nome_bruto",
        "nome",
        "marca",
        "categoria",
        "tags",
        "texto_rag",
        "meta_agente",
        "preco_padrao",
        "url_imagem",
        "imagem_local",
        "status_enriquecimento",
        "criado_em",
        "atualizado_em",
    )

    def __init__(
        self,
        id: UUID,
        tenant_id: str,
        codigo_externo: str,
        nome_bruto: str,
        status_enriquecimento: StatusEnriquecimento,
        criado_em: datetime,
        atualizado_em: datetime,
        nome: str | None = None,
        marca: str | None = None,
        categoria: str | None = None,
        tags: list[str] | None = None,
        texto_rag: str | None = None,
        meta_agente: dict[str, Any] | None = None,
        preco_padrao: Decimal | None = None,
        url_imagem: str | None = None,
        imagem_local: str | None = None,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.codigo_externo = codigo_externo
        self.nome_bruto = nome_bruto
        self.nome = nome
        self.marca = marca
        self.categoria = categoria
        self.tags = tags or []
        self.texto_rag = texto_rag
        self.meta_agente = meta_agente or {}
        self.preco_padrao = preco_padrao
        self.url_imagem = url_imagem
        self.imagem_local = imagem_local
        self.status_enriquecimento = status_enriquecimento
        self.criado_em = criado_em
        self.atualizado_em = atualizado_em

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict (usado em JSON responses e templates Jinja2)."""
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "codigo_externo": self.codigo_externo,
            "nome_bruto": self.nome_bruto,
            "nome": self.nome,
            "marca": self.marca,
            "categoria": self.categoria,
            "tags": self.tags,
            "texto_rag": self.texto_rag,
            "meta_agente": self.meta_agente,
            "preco_padrao": str(self.preco_padrao) if self.preco_padrao else None,
            "url_imagem": self.url_imagem,
            "imagem_local": self.imagem_local,
            "status_enriquecimento": self.status_enriquecimento,
            "criado_em": self.criado_em.isoformat(),
            "atualizado_em": self.atualizado_em.isoformat(),
        }

    def __repr__(self) -> str:
        return f"CommerceProduct(id={self.id!s}, codigo={self.codigo_externo!r})"


# Alias de compatibilidade — permite que testes e callers legados importem Produto
# sem quebrar. CommerceProduct foi o nome adotado em Sprint 10 (B-33).
Produto = CommerceProduct


# ─────────────────────────────────────────────
# Preço diferenciado
# ─────────────────────────────────────────────


class PrecoDiferenciado:
    """Preço especial de um produto para um cliente específico."""

    __slots__ = (
        "tenant_id",
        "codigo_produto",
        "ean",
        "cliente_cnpj",
        "preco_cliente",
    )

    def __init__(
        self,
        tenant_id: str,
        codigo_produto: str,
        cliente_cnpj: str,
        preco_cliente: Decimal,
        ean: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.codigo_produto = codigo_produto
        self.ean = ean
        # Normaliza CNPJ para apenas dígitos
        self.cliente_cnpj = "".join(c for c in cliente_cnpj if c.isdigit())
        self.preco_cliente = preco_cliente

    def __repr__(self) -> str:
        return (
            f"PrecoDiferenciado(codigo={self.codigo_produto!r}, "
            f"cnpj={self.cliente_cnpj!r})"
        )


# ─────────────────────────────────────────────
# Resultados compostos
# ─────────────────────────────────────────────


class ResultadoBusca:
    """Resultado de busca semântica por embedding."""

    __slots__ = ("produto", "distancia", "score")

    def __init__(self, produto: CommerceProduct, distancia: float) -> None:
        self.produto = produto
        self.distancia = distancia
        self.score = round(1.0 - distancia, 4)  # cosine similarity

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict (usado em JSON responses)."""
        return {
            "produto": self.produto.to_dict(),
            "distancia": self.distancia,
            "score": self.score,
        }

    def __repr__(self) -> str:
        return f"ResultadoBusca(codigo={self.produto.codigo_externo!r}, score={self.score})"


class CrawlStatus:
    """Status de uma execução de crawl."""

    __slots__ = (
        "tenant_id",
        "total_categorias",
        "total_produtos",
        "novos",
        "atualizados",
        "erros",
        "iniciado_em",
        "finalizado_em",
    )

    def __init__(
        self,
        tenant_id: str,
        total_categorias: int,
        total_produtos: int,
        novos: int,
        atualizados: int,
        erros: int,
        iniciado_em: datetime,
        finalizado_em: datetime | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.total_categorias = total_categorias
        self.total_produtos = total_produtos
        self.novos = novos
        self.atualizados = atualizados
        self.erros = erros
        self.iniciado_em = iniciado_em
        self.finalizado_em = finalizado_em

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict."""
        return {
            "tenant_id": self.tenant_id,
            "total_categorias": self.total_categorias,
            "total_produtos": self.total_produtos,
            "novos": self.novos,
            "atualizados": self.atualizados,
            "erros": self.erros,
            "iniciado_em": self.iniciado_em.isoformat(),
            "finalizado_em": self.finalizado_em.isoformat() if self.finalizado_em else None,
        }


class ExcelUploadResult:
    """Resultado do processamento de upload de preços via Excel."""

    __slots__ = ("linhas_processadas", "inseridos", "atualizados", "erros")

    def __init__(
        self,
        linhas_processadas: int,
        inseridos: int,
        atualizados: int,
        erros: list[str],
    ) -> None:
        self.linhas_processadas = linhas_processadas
        self.inseridos = inseridos
        self.atualizados = atualizados
        self.erros = erros

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict."""
        return {
            "linhas_processadas": self.linhas_processadas,
            "inseridos": self.inseridos,
            "atualizados": self.atualizados,
            "erros": self.erros,
        }


# ─────────────────────────────────────────────
# Protocols (evita violação Service → Runtime)
# ─────────────────────────────────────────────


class EnricherProtocol(Protocol):
    """Protocol para o agente de enriquecimento.

    Definido em types.py para que Service possa depender deste contrato
    sem importar nada da camada Runtime.
    O EnricherAgent em runtime/enricher.py implementa este Protocol
    structuralmente (duck typing verificado pelo mypy).
    """

    async def enriquecer(self, produto: ProdutoBruto) -> ProdutoEnriquecido:
        """Enriquece um produto bruto com nome, marca, tags, texto_rag e meta_agente."""
        ...
