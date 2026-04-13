"""Crawler para o sistema EFOS (pedido.jmbdistribuidora.com.br).

Camada Runtime: usa Playwright para navegar e extrair produtos do site B2B.
Credenciais lidas via CrawlerConfig.for_tenant() — nunca hardcoded aqui.

Nota técnica (D018): crawler disparado on-demand via POST /catalog/crawl.
Scheduler automático pertence ao Sprint 1.

mypy: playwright não tem stubs completos — erros de tipo em playwright suprimidos
com # type: ignore[import-untyped] abaixo.
"""

from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.catalog.config import CrawlerConfig
from src.catalog.runtime.crawler.base import CrawlerBase
from src.catalog.types import Categoria, ProdutoBruto

log = structlog.get_logger(__name__)


class EfosCrawler(CrawlerBase):
    """Crawler para o sistema EFOS usado pela JMB Distribuidora.

    O sistema EFOS é um portal B2B PHP/ASP com:
    - Autenticação por formulário (login/senha)
    - Listagem de categorias em menu lateral
    - Grid de produtos por categoria com paginação numérica
    - Cada produto tem código, descrição, preço e imagem

    Uso:
        async with EfosCrawler(CrawlerConfig.for_tenant("jmb")) as crawler:
            categorias = await crawler.get_categorias()
            for cat in categorias:
                produtos = await crawler.get_produtos(cat)
    """

    def __init__(self, config: CrawlerConfig) -> None:
        super().__init__(config)
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def _init_browser(self) -> None:
        """Inicia Playwright com Chromium."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)

        log.info(
            "browser_iniciado",
            tenant_id=self.config.tenant_id,
            headless=self.config.headless,
        )

    async def _close_browser(self) -> None:
        """Fecha browser e libera recursos Playwright."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            log.warning(
                "erro_fechar_browser",
                tenant_id=self.config.tenant_id,
                error=str(exc),
            )
        finally:
            self._page = None
            self._browser = None
            self._playwright = None

    async def login(self) -> bool:
        """Autentica no EFOS.

        Tenta dois métodos em ordem:

        1. **Session cookie** (preferencial): se `config.session_cookie` estiver
           preenchido, injeta o cookie `PHPSESSID` no contexto Playwright e
           verifica se a sessão ainda é válida navegando para a página inicial.
           Útil para bypassar reCAPTCHA v2 do EFOS.

        2. **Formulário de dois passos** (fallback):
           a. Acessa login.php
           b. Preenche CNPJ em #cnpj_cpf via type() (respeita máscara JS)
           c. Clica #btnFecharJanelas → AJAX para validacnpj.php
           d. Aguarda #campodesenha tornar-se visível
           e. Preenche senha em #senha
           f. Clica submit (#btlogin)

        Returns:
            True se autenticação bem-sucedida.
        """
        log.info("crawler_login_inicio", tenant_id=self.config.tenant_id)

        if self.config.session_cookie:
            success = await self._login_via_cookie()
            if success:
                return True
            log.warning(
                "cookie_sessao_expirado",
                tenant_id=self.config.tenant_id,
                hint="Atualize CRAWLER_SESSION no Infisical com um PHPSESSID válido",
            )

        return await self._login_via_form()

    async def _login_via_cookie(self) -> bool:
        """Injeta PHPSESSID e verifica se a sessão é válida.

        Returns:
            True se o cookie resultar em sessão autenticada.
        """
        domain = self.config.base_url.replace("https://", "").replace("http://", "").split("/")[0]
        await self._page.context.add_cookies([
            {
                "name": "PHPSESSID",
                "value": self.config.session_cookie,
                "domain": domain,
                "path": "/",
            }
        ])

        home_url = f"{self.config.base_url}/home.php"
        await self._page.goto(home_url, wait_until="networkidle")

        current_url = self._page.url
        authenticated = "login" not in current_url.lower()

        log.info(
            "crawler_login_cookie",
            tenant_id=self.config.tenant_id,
            sucesso=authenticated,
            url_final=current_url,
        )

        return authenticated

    async def _login_via_form(self) -> bool:
        """Autentica via formulário de dois passos do EFOS.

        Returns:
            True se autenticação bem-sucedida (URL não contém 'login' ou 'erro').
        """
        login_url = f"{self.config.base_url}/login.php"
        log.info("crawler_login_form", tenant_id=self.config.tenant_id, url=login_url)

        await self._page.goto(login_url, wait_until="networkidle")

        # Passo 1: preenche CNPJ via type() para respeitar máscara JS
        await self._page.type("#cnpj_cpf", self.config.username, delay=30)

        # Passo 2: clica "Continuar" — dispara AJAX que valida CNPJ
        await self._page.click("#btnFecharJanelas")

        # Passo 3: aguarda o campo de senha aparecer (AJAX popula #campodesenha)
        await self._page.wait_for_selector(
            "#campodesenha",
            state="visible",
            timeout=15000,
        )

        # Passo 4: preenche senha
        await self._page.fill("#senha", self.config.password)

        # Passo 5: submete o formulário
        await self._page.click("input[name='btlogin'], #btlogin, button[type='submit']")
        await self._page.wait_for_load_state("networkidle")

        current_url = self._page.url
        success = "login" not in current_url.lower() and "erro" not in current_url.lower()

        log.info(
            "crawler_login_resultado",
            tenant_id=self.config.tenant_id,
            sucesso=success,
            url_final=current_url,
        )

        return success

    async def get_categorias(self) -> list[Categoria]:
        """Extrai categorias do menu principal do EFOS.

        Estrutura real do site (inspecionada em 2026-04-13):
        - Categorias estão no menu `.category-item` na homepage (`/`)
        - Cada `.category-item` tem um `.category-link.dropdown-link` com o nome
        - E um link `a[href*="pesquisa.php?categoria="]` com o texto "Ver Todos"
          que aponta para a URL real da listagem

        Returns:
            Lista de categorias disponíveis para o tenant.
        """
        log.info("crawler_get_categorias", tenant_id=self.config.tenant_id)

        index_url = f"{self.config.base_url}/"
        await self._page.goto(index_url, wait_until="networkidle")
        await self._rate_limit()

        categorias: list[Categoria] = []

        # Itera por cada .category-item do menu principal
        items = await self._page.query_selector_all(".category-item")
        for item in items:
            # Nome da categoria (ex: "CHUPETAS")
            nome_el = await item.query_selector(".category-link.dropdown-link")
            if not nome_el:
                continue
            nome = str(await nome_el.inner_text()).strip()
            if not nome:
                continue

            # URL "Ver Todos" (ex: pesquisa.php?categoria=1&ordenacao=a-z&page=1&limite=48&tip=1)
            ver_todos_el = await item.query_selector("a[href*='pesquisa.php?categoria=']")
            if not ver_todos_el:
                continue
            href = await ver_todos_el.get_attribute("href") or ""
            if not href:
                continue

            # Monta URL absoluta e extrai ID da categoria
            url_cat = (
                f"{self.config.base_url}/{href}"
                if not href.startswith("http")
                else href
            )
            cat_id = self._extrair_id_url(href) or nome.lower().replace(" ", "-")

            categorias.append(Categoria(id=cat_id, nome=nome, url=url_cat))

        if not categorias:
            log.warning(
                "categorias_nao_encontradas",
                tenant_id=self.config.tenant_id,
                url=index_url,
            )

        log.info(
            "categorias_extraidas",
            tenant_id=self.config.tenant_id,
            total=len(categorias),
        )

        return categorias

    async def get_produtos(self, categoria: Categoria) -> list[ProdutoBruto]:
        """Extrai todos os produtos de uma categoria com paginação.

        Usa `_get_total_paginas()` após a primeira página para saber quantas
        páginas existem e evitar loop infinito.

        Args:
            categoria: categoria a ser crawleada.

        Returns:
            Lista de produtos brutos da categoria.
        """
        log.info(
            "crawler_get_produtos",
            tenant_id=self.config.tenant_id,
            categoria=categoria.nome,
        )

        produtos: list[ProdutoBruto] = []
        pagina = 1
        total_paginas = 1

        while pagina <= total_paginas:
            url_pagina = self._build_pagina_url(categoria, pagina)
            await self._page.goto(url_pagina, wait_until="networkidle")
            await self._rate_limit()

            novos = await self._extrair_produtos_pagina(categoria.nome)
            if not novos:
                break

            produtos.extend(novos)
            log.debug(
                "pagina_extraida",
                tenant_id=self.config.tenant_id,
                categoria=categoria.nome,
                pagina=pagina,
                total_paginas=total_paginas,
                produtos_novos=len(novos),
            )

            # Lê total de páginas após a primeira navegação
            if pagina == 1:
                total_paginas = await self._get_total_paginas()

            pagina += 1

        log.info(
            "produtos_categoria_extraidos",
            tenant_id=self.config.tenant_id,
            categoria=categoria.nome,
            total=len(produtos),
        )

        return produtos

    async def logout(self) -> None:
        """Encerra sessão no EFOS."""
        try:
            logout_url = f"{self.config.base_url}/logout"
            await self._page.goto(logout_url, wait_until="networkidle")
            log.info("crawler_logout", tenant_id=self.config.tenant_id)
        except Exception as exc:
            log.warning(
                "erro_logout",
                tenant_id=self.config.tenant_id,
                error=str(exc),
            )

    # ─────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────

    async def _extrair_produtos_pagina(self, categoria_nome: str) -> list[ProdutoBruto]:
        """Extrai produtos da página atual.

        Estrutura real do EFOS: cards `.product-card` com código em
        `a.product-image[href]`, nome em `h6.product-name`, preço em
        `h6.product-price span` e imagem em `a.product-image img`.

        Args:
            categoria_nome: nome da categoria para atribuição.

        Returns:
            Lista de produtos da página atual.
        """
        produtos: list[ProdutoBruto] = []

        # Seletor real do EFOS; fallbacks para outros layouts
        card_selectors = [
            ".product-card",
            ".produto-item",
            ".product-item",
            ".item-produto",
            ".card-produto",
        ]

        cards: list[Any] = []
        for selector in card_selectors:
            cards = await self._page.query_selector_all(selector)
            if cards:
                break

        for card in cards:
            try:
                produto = await self._extrair_produto_card(card, categoria_nome)
                if produto:
                    produtos.append(produto)
            except Exception as exc:
                log.warning(
                    "erro_extrair_produto",
                    tenant_id=self.config.tenant_id,
                    error=str(exc),
                )

        return produtos

    async def _extrair_produto_card(
        self, card: Any, categoria_nome: str
    ) -> ProdutoBruto | None:
        """Extrai dados de um card `.product-card` do EFOS.

        Estrutura real (inspecionada 2026-04-13):
          - Código: href de `a.product-image` → `product=302924`
          - Nome:   `h6.product-name a`
          - Preço:  `h6.product-price span` (ex: "R$ 14.54/Und.")
          - Imagem: `a.product-image img[src]` (path relativo, ex: "fotos/302924.jpg")

        Args:
            card: elemento Playwright do card.
            categoria_nome: nome da categoria pai.

        Returns:
            ProdutoBruto ou None se dados insuficientes.
        """
        # Código do produto — extraído do href do link de imagem
        codigo: str = ""
        link_el = await card.query_selector("a.product-image")
        if link_el:
            href_prod = await link_el.get_attribute("href") or ""
            match = re.search(r"product=(\w+)", href_prod)
            if match:
                codigo = match.group(1)

        # Nome do produto
        nome = await self._get_text(card, [
            "h6.product-name a",
            "h6.product-name",
            ".product-name a",
            ".product-name",
            "h3", "h4",
        ])

        if not codigo or not nome:
            return None

        # Preço (ex: "R$ 14.54/Und." → Decimal("14.54"))
        preco_texto = await self._get_text(card, [
            "h6.product-price span",
            "h6.product-price",
            ".product-price span",
            ".product-price",
        ])
        # Remove sufixo "/Und." ou similar antes de parsear
        if preco_texto:
            preco_texto = preco_texto.split("/")[0].strip()
        preco = self._parse_preco(preco_texto)

        # URL da imagem
        url_imagem: str | None = None
        img_el = await card.query_selector("a.product-image img, img")
        if img_el:
            src = await img_el.get_attribute("src") or ""
            if src and not src.startswith("data:"):
                url_imagem = src if src.startswith("http") else f"{self.config.base_url}/{src.lstrip('/')}"

        return ProdutoBruto(
            codigo_externo=codigo.strip(),
            nome_bruto=nome.strip(),
            tenant_id=self.config.tenant_id,
            preco_padrao=preco,
            url_imagem=url_imagem,
            categoria=categoria_nome,
        )

    async def _get_text(self, element: Any, selectors: list[str]) -> str:
        """Tenta extrair texto de um elemento filho usando lista de seletores."""
        for selector in selectors:
            try:
                el = await element.query_selector(selector)
                if el:
                    texto = await el.inner_text()
                    if texto and str(texto).strip():
                        return str(texto).strip()
            except Exception:
                continue
        return ""

    async def _get_total_paginas(self) -> int:
        """Lê o total de páginas do EFOS a partir do texto de paginação.

        O EFOS exibe: `<p class="page-info"> Total: 3 Páginas.</p>`

        Returns:
            Número total de páginas (mínimo 1).
        """
        try:
            total: Any = await self._page.evaluate("""() => {
                const els = document.querySelectorAll(".page-info");
                for (const el of els) {
                    const m = el.innerText.match(/Total:\\s*(\\d+)\\s*P/i);
                    if (m) return parseInt(m[1], 10);
                }
                return 1;
            }""")
            return max(1, int(total))
        except Exception:
            return 1

    def _build_pagina_url(self, categoria: Categoria, pagina: int) -> str:
        """Constrói URL de uma página específica de categoria.

        O EFOS usa `pesquisa.php?categoria=N&...&page=1&...`.
        Substitui o parâmetro `page=` existente em vez de duplicá-lo.

        Args:
            categoria: categoria com url já preenchida por `get_categorias`.
            pagina: número da página (1-indexed).

        Returns:
            URL completa para a página solicitada.
        """
        base = categoria.url if categoria.url else (
            f"{self.config.base_url}/pesquisa.php?categoria={categoria.id}"
        )

        # Substitui page=N ou adiciona page=N se não existir
        if re.search(r"[?&]page=\d+", base):
            return re.sub(r"(page=)\d+", rf"\g<1>{pagina}", base)
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}page={pagina}"

    @staticmethod
    def _extrair_id_url(href: str) -> str | None:
        """Extrai ID numérico de uma URL de categoria."""
        match = re.search(r"/(\d+)(?:\?|$|/)", href)
        if match:
            return match.group(1)
        match = re.search(r"[?&](?:cat|categoria|id)=(\w+)", href)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _parse_preco(texto: str | None) -> Decimal | None:
        """Converte texto de preço brasileiro para Decimal.

        Exemplos:
            "R$ 29,90" → Decimal("29.90")
            "29.90"    → Decimal("29.90")
            "1.299,00" → Decimal("1299.00")
        """
        if not texto:
            return None
        # Remove R$, espaços e caracteres não numéricos exceto vírgula e ponto
        limpo = re.sub(r"[R$\s]", "", texto).strip()
        # Formato brasileiro: 1.299,00 → 1299.00
        if "," in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        try:
            return Decimal(limpo)
        except InvalidOperation:
            return None
