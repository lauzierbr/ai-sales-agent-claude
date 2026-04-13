"""Agente de enriquecimento de produtos — Claude Haiku.

Camada Runtime: implementa EnricherProtocol definido em src.catalog.types.
Usa claude-haiku-4-5-20251001 para normalizar nomes, extrair marcas,
gerar tags e construir texto_rag para busca semântica.

Credenciais lidas via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import json
import os

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from src.catalog.types import EnricherProtocol, ProdutoBruto, ProdutoEnriquecido

log = structlog.get_logger(__name__)

ENRICHMENT_PROMPT = """\
Você é um especialista em produtos de distribuição B2B brasileira.
Receba os dados brutos de um produto e retorne JSON estruturado para uso em busca semântica.

PRODUTO BRUTO:
Código: {codigo_externo}
Nome original: {nome_bruto}
Categoria: {categoria}
Descrição: {descricao_bruta}

Retorne EXATAMENTE este JSON (sem markdown, sem texto antes ou depois, apenas JSON puro):
{{
  "nome": "nome normalizado e legível (máx 80 chars, sem abreviações)",
  "marca": "marca ou fabricante extraída do nome ou descrição (ou 'Sem marca' se não identificado)",
  "categoria": "categoria normalizada em português",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "texto_rag": "texto completo otimizado para busca semântica: inclua nome, marca, categoria, descrição, sinônimos, usos e características. 150-300 palavras em português.",
  "meta_agente": {{
    "unidade": "ml/g/un/kg/caixa/pacote/par (null se não identificado)",
    "quantidade": null,
    "variante": null,
    "grupo_produto": "categoria funcional em uma ou duas palavras"
  }}
}}
"""


class EnricherAgent:
    """Agente de enriquecimento usando Claude Haiku.

    Implementa EnricherProtocol estruturalmente — mypy valida a conformidade.
    Injetado em CatalogService via tipo EnricherProtocol (sem import de Runtime).
    """

    def __init__(self) -> None:
        """Inicializa com cliente Anthropic.

        A API key é lida de ANTHROPIC_API_KEY (injetada via Infisical).
        Raises:
            ValueError: se ANTHROPIC_API_KEY não estiver definida.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Variável Infisical não configurada: ANTHROPIC_API_KEY")

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = "claude-haiku-4-5-20251001"

    async def enriquecer(self, produto: ProdutoBruto) -> ProdutoEnriquecido:
        """Enriquece um produto bruto com nome, marca, tags, texto_rag e meta_agente.

        Args:
            produto: produto bruto extraído pelo crawler.

        Returns:
            ProdutoEnriquecido com todos os campos preenchidos.

        Raises:
            ValueError: se a resposta do Haiku não for JSON válido.
            RuntimeError: se a chamada à API falhar.
        """
        prompt = ENRICHMENT_PROMPT.format(
            codigo_externo=produto.codigo_externo,
            nome_bruto=produto.nome_bruto,
            categoria=produto.categoria or "Não informada",
            descricao_bruta=produto.descricao_bruta or "Não informada",
        )

        log.debug(
            "enricher_chamada_haiku",
            tenant_id=produto.tenant_id,
            codigo_externo=produto.codigo_externo,
            model=self._model,
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            log.error(
                "enricher_erro_api",
                tenant_id=produto.tenant_id,
                codigo_externo=produto.codigo_externo,
                error=str(exc),
            )
            raise RuntimeError(
                f"Falha na chamada ao Claude Haiku para produto '{produto.codigo_externo}': {exc}"
            ) from exc

        block = response.content[0]
        if not isinstance(block, TextBlock):
            raise ValueError(
                f"JSON inválido: resposta do modelo não é TextBlock para '{produto.codigo_externo}'"
            )
        texto_resposta = block.text.strip()

        # Remove possível markdown caso o modelo inclua ```json
        if texto_resposta.startswith("```"):
            linhas = texto_resposta.split("\n")
            texto_resposta = "\n".join(
                l for l in linhas if not l.startswith("```")
            ).strip()

        try:
            dados = json.loads(texto_resposta)
        except json.JSONDecodeError as exc:
            log.error(
                "enricher_json_invalido",
                tenant_id=produto.tenant_id,
                codigo_externo=produto.codigo_externo,
                resposta_raw=texto_resposta[:200],
                error=str(exc),
            )
            raise ValueError(
                f"Haiku retornou JSON inválido para produto '{produto.codigo_externo}': {exc}"
            ) from exc

        # Valida campos obrigatórios
        campos_obrigatorios = ["nome", "marca", "categoria", "tags", "texto_rag", "meta_agente"]
        faltando = [c for c in campos_obrigatorios if c not in dados]
        if faltando:
            raise ValueError(
                f"Resposta do Haiku faltando campos obrigatórios: {faltando}"
            )

        log.info(
            "produto_enriquecido_haiku",
            tenant_id=produto.tenant_id,
            codigo_externo=produto.codigo_externo,
            nome=dados.get("nome", ""),
            marca=dados.get("marca", ""),
        )

        return ProdutoEnriquecido(
            codigo_externo=produto.codigo_externo,
            tenant_id=produto.tenant_id,
            nome=str(dados["nome"]),
            marca=str(dados["marca"]),
            categoria=str(dados["categoria"]),
            tags=list(dados.get("tags", [])),
            texto_rag=str(dados["texto_rag"]),
            meta_agente=dict(dados.get("meta_agente", {})),
        )


# Verificação de conformidade com o Protocol (executada em import time pelo mypy)
def _check_protocol_conformance() -> None:
    """Garante que EnricherAgent satisfaz EnricherProtocol."""
    _agent: EnricherAgent = EnricherAgent.__new__(EnricherAgent)
    _protocol: EnricherProtocol = _agent  # mypy verifica conformidade estrutural aqui
