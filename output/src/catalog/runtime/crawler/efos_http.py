"""Crawler httpx para o sistema EFOS (pedido.jmbdistribuidora.com.br).

Alternativa sem Playwright: usa httpx.AsyncClient + BeautifulSoup.
- 10-50× mais rápido que Playwright (sem overhead de browser)
- Sem reCAPTCHA (usa PHPSESSID via config.session_cookie)
- Baixa imagens em paralelo e armazena localmente
- Imagens servidas via FastAPI em /images/{tenant_id}/{codigo}.jpg

Requer: CRAWLER_SESSION_{TENANT_ID} no Infisical (PHPSESSID válido).
"""

from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from src.catalog.config import CrawlerConfig
from src.catalog.runtime.crawler.base import CrawlerBase
from src.catalog.types import Categoria, ProdutoBruto

log = structlog.get_logger(__name__)

# Diretório base para imagens — relativo ao arquivo (independente de CWD)
# output/src/catalog/runtime/crawler/ → up 5 levels → output/ → images/
_IMAGES_BASE = Path(__file__).parent.parent.parent.parent.parent / "images"


class EfosHttpCrawler(CrawlerBase):
    """Crawler httpx para o EFOS — mais rápido que Playwright, sem browser.

    Requer PHPSESSID válido em `config.session_cookie`.
    Baixa imagens de `fotos/{codigo}.jpg` e as armazena em
    `output/images/{tenant_id}/{codigo}.jpg`, servidas em
    `/images/{tenant_id}/{codigo}.jpg`.

    Uso:
        async with EfosHttpCrawler(CrawlerConfig.for_tenant("jmb")) as crawler:
            categorias = await crawler.get_categorias()
            for cat in categorias:
                produtos = await crawler.get_produtos(cat)
    """

    def __init__(self, config: CrawlerConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._img_dir = _IMAGES_BASE / config.tenant_id
        self._img_semaphore = asyncio.Semaphore(10)  # máx 10 downloads simultâneos

    # ─────────────────────────────────────────────
    # Ciclo de vida (protocolo CrawlerBase)
    # ─────────────────────────────────────────────

    async def _init_browser(self) -> None:
        """Inicia AsyncClient httpx com cookie de sessão."""
        cookies: dict[str, str] = {}
        if self.config.session_cookie:
            cookies["PHPSESSID"] = self.config.session_cookie

        self._client = httpx.AsyncClient(
            cookies=cookies,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        )
        self._img_dir.mkdir(parents=True, exist_ok=True)
        log.info("http_crawler_iniciado", tenant_id=self.config.tenant_id)

    async def _close_browser(self) -> None:
        """Fecha AsyncClient."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def login(self) -> bool:
        """Verifica sessão via PHPSESSID — sem formulário, sem reCAPTCHA.

        Returns:
            True se a sessão é válida (página inicial carregada sem redirecionar ao login).
        """
        assert self._client is not None
        if not self.config.session_cookie:
            log.error(
                "http_crawler_sem_cookie",
                tenant_id=self.config.tenant_id,
                hint="Defina CRAWLER_SESSION no Infisical",
            )
            return False

        r = await self._client.get(f"{self.config.base_url}/")
        authenticated = "login" not in str(r.url).lower()

        log.info(
            "http_crawler_login",
            tenant_id=self.config.tenant_id,
            sucesso=authenticated,
            url_final=str(r.url),
        )
        return authenticated

    async def logout(self) -> None:
        """Não há logout necessário para sessão httpx."""
        pass

    # ─────────────────────────────────────────────
    # Catálogo
    # ─────────────────────────────────────────────

    async def get_categorias(self) -> list[Categoria]:
        """Extrai categorias do menu principal da homepage.

        Estrutura real do EFOS (inspecionada 2026-04-13):
        `.category-item` → `.category-link.dropdown-link` (nome)
                         + `a[href*="pesquisa.php?categoria="]` (URL)

        Returns:
            Lista de categorias disponíveis.
        """
        assert self._client is not None
        log.info("http_get_categorias", tenant_id=self.config.tenant_id)

        r = await self._client.get(f"{self.config.base_url}/")
        await self._rate_limit()

        soup = BeautifulSoup(r.text, "html.parser")
        categorias: list[Categoria] = []

        for item in soup.select(".category-item"):
            nome_el = item.select_one(".category-link.dropdown-link")
            url_el = item.select_one("a[href*='pesquisa.php?categoria=']")
            if not nome_el or not url_el:
                continue

            nome = nome_el.get_text(strip=True)
            href_raw = url_el.get("href")
            if not isinstance(href_raw, str) or not href_raw or not nome:
                continue
            href: str = href_raw

            url_cat = (
                href if href.startswith("http")
                else f"{self.config.base_url}/{href.lstrip('/')}"
            )
            cat_id = self._extrair_id_url(href) or nome.lower().replace(" ", "-")
            categorias.append(Categoria(id=cat_id, nome=nome, url=url_cat))

        log.info(
            "http_categorias_extraidas",
            tenant_id=self.config.tenant_id,
            total=len(categorias),
        )
        return categorias

    async def get_produtos(self, categoria: Categoria) -> list[ProdutoBruto]:
        """Extrai todos os produtos de uma categoria com paginação.

        Args:
            categoria: categoria a ser crawleada.

        Returns:
            Lista de produtos brutos com imagens baixadas localmente.
        """
        assert self._client is not None
        log.info(
            "http_get_produtos",
            tenant_id=self.config.tenant_id,
            categoria=categoria.nome,
        )

        produtos: list[ProdutoBruto] = []
        pagina = 1
        total_paginas = 1

        while pagina <= total_paginas:
            url = self._build_pagina_url(categoria, pagina)
            r = await self._client.get(url)
            await self._rate_limit()

            soup = BeautifulSoup(r.text, "html.parser")
            novos = await self._extrair_e_baixar_produtos(soup, categoria.nome)

            if not novos:
                break

            produtos.extend(novos)
            log.debug(
                "http_pagina_extraida",
                tenant_id=self.config.tenant_id,
                categoria=categoria.nome,
                pagina=pagina,
                produtos_novos=len(novos),
                total_paginas=total_paginas,
            )

            if pagina == 1:
                total_paginas = self._get_total_paginas_soup(soup)

            pagina += 1

        log.info(
            "http_produtos_extraidos",
            tenant_id=self.config.tenant_id,
            categoria=categoria.nome,
            total=len(produtos),
        )
        return produtos

    # ─────────────────────────────────────────────
    # Extração + download de imagens
    # ─────────────────────────────────────────────

    async def _extrair_e_baixar_produtos(
        self, soup: Any, categoria_nome: str
    ) -> list[ProdutoBruto]:
        """Extrai produtos da página e baixa imagens em paralelo.

        Args:
            soup: BeautifulSoup da página de listagem.
            categoria_nome: nome da categoria para atribuição.

        Returns:
            Lista de produtos com `imagem_local` preenchida.
        """
        cards = soup.select(".product-card")
        tasks = [self._extrair_produto_card_http(card, categoria_nome) for card in cards]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        produtos: list[ProdutoBruto] = []
        for r in resultados:
            if isinstance(r, ProdutoBruto):
                produtos.append(r)
            elif isinstance(r, Exception):
                log.warning(
                    "http_erro_extrair_produto",
                    tenant_id=self.config.tenant_id,
                    error=str(r),
                )
        return produtos

    async def _extrair_produto_card_http(
        self, card: Any, categoria_nome: str
    ) -> ProdutoBruto | None:
        """Extrai dados de um `.product-card` e baixa a imagem.

        Estrutura real (inspecionada 2026-04-13):
          - Código:  href de `a.product-image` → `product=302924`
          - Nome:    `h6.product-name a`
          - Preço:   `h6.product-price span` (ex: "R$ 14.54/Und.")
          - Imagem:  `a.product-image img[src]` → `fotos/302924.jpg`

        Args:
            card: tag BeautifulSoup do card.
            categoria_nome: nome da categoria pai.

        Returns:
            ProdutoBruto com imagem_local preenchida ou None.
        """
        # Código via href do link de imagem
        link = card.select_one("a.product-image")
        if not link:
            return None
        href = link.get("href", "")
        m = re.search(r"product=(\w+)", href)
        if not m:
            return None
        codigo = m.group(1)

        # Nome
        nome_tag = card.select_one("h6.product-name a") or card.select_one("h6.product-name")
        if not nome_tag:
            return None
        nome = nome_tag.get_text(strip=True)
        if not nome:
            return None

        # Preço
        preco_tag = card.select_one("h6.product-price span") or card.select_one("h6.product-price")
        preco_texto = preco_tag.get_text(strip=True).split("/")[0].strip() if preco_tag else None
        preco = self._parse_preco(preco_texto)

        # URL remota da imagem
        img_tag = card.select_one("a.product-image img")
        src = img_tag.get("src", "") if img_tag else ""
        url_remota: str | None = None
        if src and not src.startswith("data:"):
            url_remota = (
                src if src.startswith("http")
                else f"{self.config.base_url}/{src.lstrip('/')}"
            )

        # Download local da imagem
        imagem_local = await self._download_imagem(codigo, url_remota) if url_remota else None

        return ProdutoBruto(
            codigo_externo=codigo,
            nome_bruto=nome,
            tenant_id=self.config.tenant_id,
            preco_padrao=preco,
            url_imagem=url_remota,
            imagem_local=imagem_local,
            categoria=categoria_nome,
        )

    async def _download_imagem(self, codigo: str, url: str) -> str | None:
        """Baixa a imagem do produto e salva em disco.

        Usa semáforo para limitar concorrência a 10 downloads simultâneos.
        Idempotente: se o arquivo já existe, retorna o caminho sem re-download.

        Args:
            codigo: código externo do produto (usado como nome do arquivo).
            url: URL remota da imagem.

        Returns:
            URL relativa para servir via FastAPI (`/images/{tenant_id}/{codigo}.jpg`)
            ou None em caso de falha.
        """
        img_path = self._img_dir / f"{codigo}.jpg"
        url_local = f"/images/{self.config.tenant_id}/{codigo}.jpg"

        # Idempotente — não re-baixa se já existe
        if img_path.exists():
            return url_local

        async with self._img_semaphore:
            try:
                assert self._client is not None
                r = await self._client.get(url, timeout=httpx.Timeout(20.0))
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and "image" in ct:
                    img_path.write_bytes(r.content)
                    log.debug(
                        "imagem_baixada",
                        tenant_id=self.config.tenant_id,
                        codigo=codigo,
                        bytes=len(r.content),
                    )
                    return url_local
            except Exception as exc:
                log.warning(
                    "imagem_download_falhou",
                    tenant_id=self.config.tenant_id,
                    codigo=codigo,
                    url=url,
                    error=str(exc),
                )
        return None

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def _get_total_paginas_soup(soup: Any) -> int:
        """Lê total de páginas do texto `Total: X Páginas.`"""
        for el in soup.select(".page-info"):
            m = re.search(r"Total:\s*(\d+)\s*P", el.get_text(), re.IGNORECASE)
            if m:
                return max(1, int(m.group(1)))
        return 1

    def _build_pagina_url(self, categoria: Categoria, pagina: int) -> str:
        """Constrói URL de página substituindo page=N."""
        base = categoria.url or f"{self.config.base_url}/pesquisa.php?categoria={categoria.id}"
        if re.search(r"[?&]page=\d+", base):
            return re.sub(r"(page=)\d+", rf"\g<1>{pagina}", base)
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}page={pagina}"

    @staticmethod
    def _extrair_id_url(href: str) -> str | None:
        """Extrai ID numérico de URL de categoria."""
        m = re.search(r"[?&](?:cat|categoria|id)=(\w+)", href)
        if m:
            return m.group(1)
        m = re.search(r"/(\d+)(?:\?|$|/)", href)
        return m.group(1) if m else None

    @staticmethod
    def _parse_preco(texto: str | None) -> Decimal | None:
        """Converte texto de preço brasileiro para Decimal."""
        if not texto:
            return None
        limpo = re.sub(r"[R$\s]", "", texto).strip()
        if "," in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        try:
            return Decimal(limpo)
        except InvalidOperation:
            return None
