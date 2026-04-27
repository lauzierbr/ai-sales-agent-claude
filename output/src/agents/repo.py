"""Repositório do domínio Agents — acesso ao PostgreSQL.

Camada Repo: importa apenas src.agents.types e stdlib.
Toda função pública que acessa dados de tenant filtra por tenant_id.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.types import (
    ClienteB2B,
    Conversa,
    Gestor,
    MensagemConversa,
    Persona,
    Representante,
    WhatsappInstancia,
)

log = structlog.get_logger(__name__)


class WhatsappInstanciaRepo:
    """Repositório de instâncias WhatsApp — associa instância ao tenant."""

    async def get_by_instancia_id(
        self, instancia_id: str, session: AsyncSession
    ) -> WhatsappInstancia | None:
        """Busca instância pelo ID da Evolution API.

        Args:
            instancia_id: nome/ID da instância Evolution API.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            WhatsappInstancia se encontrada e ativa, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT instancia_id, tenant_id, numero_whatsapp, ativo
                FROM whatsapp_instancias
                WHERE instancia_id = :instancia_id AND ativo = true
            """),
            {"instancia_id": instancia_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return WhatsappInstancia(
            instancia_id=row["instancia_id"],
            tenant_id=row["tenant_id"],
            numero_whatsapp=row["numero_whatsapp"],
            ativo=row["ativo"],
        )

    async def create(
        self, instancia: WhatsappInstancia, session: AsyncSession
    ) -> WhatsappInstancia:
        """Persiste uma nova instância WhatsApp.

        Args:
            instancia: dados da instância.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            WhatsappInstancia persistida.
        """
        await session.execute(
            text("""
                INSERT INTO whatsapp_instancias (instancia_id, tenant_id, numero_whatsapp, ativo)
                VALUES (:instancia_id, :tenant_id, :numero_whatsapp, :ativo)
                ON CONFLICT (instancia_id) DO UPDATE SET
                    tenant_id       = EXCLUDED.tenant_id,
                    numero_whatsapp = EXCLUDED.numero_whatsapp,
                    ativo           = EXCLUDED.ativo
            """),
            {
                "instancia_id": instancia.instancia_id,
                "tenant_id": instancia.tenant_id,
                "numero_whatsapp": instancia.numero_whatsapp,
                "ativo": instancia.ativo,
            },
        )
        log.info("instancia_criada", instancia_id=instancia.instancia_id, tenant_id=instancia.tenant_id)
        return instancia


class ClienteB2BRepo:
    """Repositório de clientes B2B — lookup por telefone."""

    async def get_by_telefone(
        self, tenant_id: str, telefone: str, session: AsyncSession
    ) -> ClienteB2B | None:
        """Busca cliente B2B ativo pelo número de telefone normalizado.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            telefone: número E.164 sem sufixo @s.whatsapp.net.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            ClienteB2B se encontrado e ativo, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em, representante_id
                FROM clientes_b2b
                WHERE tenant_id = :tenant_id AND telefone = :telefone AND ativo = true
            """),
            {"tenant_id": tenant_id, "telefone": telefone},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return ClienteB2B(
            id=row["id"],
            tenant_id=row["tenant_id"],
            nome=row["nome"],
            cnpj=row["cnpj"],
            telefone=row["telefone"],
            ativo=row["ativo"],
            criado_em=row["criado_em"],
            representante_id=row["representante_id"],
        )

    async def listar_por_representante(
        self,
        tenant_id: str,
        representante_id: str,
        session: AsyncSession,
    ) -> list[ClienteB2B]:
        """Retorna todos os clientes B2B ativos vinculados ao representante.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            representante_id: ID do representante — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de ClienteB2B ordenados por nome ASC.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em, representante_id
                FROM clientes_b2b
                WHERE tenant_id = :tenant_id
                  AND representante_id = :representante_id
                  AND ativo = true
                ORDER BY nome ASC
            """),
            {"tenant_id": tenant_id, "representante_id": representante_id},
        )
        rows = result.mappings().all()
        return [
            ClienteB2B(
                id=r["id"],
                tenant_id=r["tenant_id"],
                nome=r["nome"],
                cnpj=r["cnpj"],
                telefone=r["telefone"],
                ativo=r["ativo"],
                criado_em=r["criado_em"],
                representante_id=r["representante_id"],
            )
            for r in rows
        ]

    async def buscar_por_nome(
        self,
        tenant_id: str,
        representante_id: str,
        query: str,
        session: AsyncSession,
    ) -> list[ClienteB2B]:
        """Busca clientes B2B ativos pelo nome usando unaccent + ILIKE.

        Cobre acentuação incorreta no celular ("sao" → "são",
        "farmacia" → "farmácia"). Filtra obrigatoriamente por tenant_id
        E representante_id.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            representante_id: ID do representante — filtro obrigatório.
            query: texto livre para busca no nome do cliente.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de ClienteB2B que correspondem à busca, ordenados por nome ASC.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em, representante_id
                FROM clientes_b2b
                WHERE tenant_id = :tenant_id
                  AND representante_id = :representante_id
                  AND ativo = true
                  AND unaccent(lower(nome)) ILIKE unaccent(lower('%' || :query || '%'))
                ORDER BY nome ASC
            """),
            {
                "tenant_id": tenant_id,
                "representante_id": representante_id,
                "query": query,
            },
        )
        rows = result.mappings().all()
        return [
            ClienteB2B(
                id=r["id"],
                tenant_id=r["tenant_id"],
                nome=r["nome"],
                cnpj=r["cnpj"],
                telefone=r["telefone"],
                ativo=r["ativo"],
                criado_em=r["criado_em"],
                representante_id=r["representante_id"],
            )
            for r in rows
        ]

    async def buscar_todos_por_nome(
        self,
        tenant_id: str,
        query: str,
        session: AsyncSession,
    ) -> list[ClienteB2B]:
        """Busca clientes B2B ativos pelo nome sem filtro de representante.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            query: texto livre para busca no nome do cliente.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de ClienteB2B correspondentes à busca (todos os reps).
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em, representante_id
                FROM clientes_b2b
                WHERE tenant_id = :tenant_id
                  AND ativo = true
                  AND unaccent(lower(nome)) ILIKE unaccent(lower('%' || :query || '%'))
            """),
            {"tenant_id": tenant_id, "query": query},
        )
        rows = result.mappings().all()
        clientes = [
            ClienteB2B(
                id=r["id"],
                tenant_id=r["tenant_id"],
                nome=r["nome"],
                cnpj=r["cnpj"],
                telefone=r["telefone"],
                ativo=r["ativo"],
                criado_em=r["criado_em"],
                representante_id=r["representante_id"],
            )
            for r in rows
        ]
        return sorted(clientes, key=lambda c: c.nome)

    async def buscar_todos_com_representante(
        self,
        tenant_id: str,
        query: str,
        session: AsyncSession,
    ) -> list[dict]:
        """Busca clientes B2B com nome do representante via JOIN.

        Variante de `buscar_todos_por_nome` que retorna dicts enriquecidos
        com `representante_nome` (para o AgentGestor exibir ao usuário).

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            query: texto livre para busca no nome do cliente.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts: id, nome, cnpj, telefone, representante_id,
            representante_nome.
        """
        result = await session.execute(
            text("""
                SELECT c.id, c.nome, c.cnpj, c.telefone, c.representante_id,
                       r.nome AS representante_nome
                FROM clientes_b2b c
                LEFT JOIN representantes r
                    ON r.id = c.representante_id AND r.tenant_id = c.tenant_id
                WHERE c.tenant_id = :tenant_id
                  AND c.ativo = true
                  AND unaccent(lower(c.nome)) ILIKE unaccent(lower('%' || :query || '%'))
                ORDER BY c.nome
            """),
            {"tenant_id": tenant_id, "query": query},
        )
        rows = result.mappings().all()
        return [
            {
                "id": r["id"],
                "nome": r["nome"],
                "cnpj": r["cnpj"],
                "telefone": r["telefone"],
                "representante_id": r["representante_id"],
                "representante_nome": r["representante_nome"] or "Sem representante",
            }
            for r in rows
        ]

    async def get_by_id(
        self,
        id: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> ClienteB2B | None:
        """Busca cliente B2B pelo ID e tenant.

        Args:
            id: ID UUID do cliente.
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            ClienteB2B se encontrado, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em, representante_id
                FROM clientes_b2b
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"id": id, "tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return ClienteB2B(
            id=row["id"],
            tenant_id=row["tenant_id"],
            nome=row["nome"],
            cnpj=row["cnpj"],
            telefone=row["telefone"],
            ativo=row["ativo"],
            criado_em=row["criado_em"],
            representante_id=row["representante_id"],
        )

    async def create(
        self, tenant_id: str, cliente: ClienteB2B, session: AsyncSession
    ) -> ClienteB2B:
        """Persiste novo cliente B2B.

        Args:
            tenant_id: ID do tenant.
            cliente: dados do cliente.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            ClienteB2B persistido.
        """
        await session.execute(
            text("""
                INSERT INTO clientes_b2b (tenant_id, nome, cnpj, telefone, ativo)
                VALUES (:tenant_id, :nome, :cnpj, :telefone, :ativo)
            """),
            {
                "tenant_id": tenant_id,
                "nome": cliente.nome,
                "cnpj": cliente.cnpj,
                "telefone": cliente.telefone,
                "ativo": cliente.ativo,
            },
        )
        log.info("cliente_b2b_criado", tenant_id=tenant_id, cnpj=cliente.cnpj)
        return cliente


class RepresentanteRepo:
    """Repositório de representantes — lookup por telefone."""

    async def get_by_telefone(
        self, tenant_id: str, telefone: str, session: AsyncSession
    ) -> Representante | None:
        """Busca representante ativo pelo número de telefone normalizado.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            telefone: número E.164 sem sufixo @s.whatsapp.net.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Representante se encontrado e ativo, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, usuario_id, telefone, nome, ativo
                FROM representantes
                WHERE tenant_id = :tenant_id AND telefone = :telefone AND ativo = true
            """),
            {"tenant_id": tenant_id, "telefone": telefone},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return Representante(
            id=row["id"],
            tenant_id=row["tenant_id"],
            usuario_id=row["usuario_id"],
            telefone=row["telefone"],
            nome=row["nome"],
            ativo=row["ativo"],
        )


class ConversaRepo:
    """Repositório de conversas e histórico de mensagens."""

    @staticmethod
    def _normalize_phone(telefone: str) -> str:
        """Remove sufixo @s.whatsapp.net e normaliza para digits E.164.

        Args:
            telefone: número com ou sem sufixo WhatsApp.

        Returns:
            Número apenas com digits.
        """
        return telefone.split("@")[0]

    async def get_or_create_conversa(
        self,
        tenant_id: str,
        telefone: str,
        persona: Persona,
        session: AsyncSession,
    ) -> Conversa:
        """Retorna conversa aberta mais recente ou cria nova.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            telefone: número do interlocutor (normalizado internamente).
            persona: persona identificada para esta conversa.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Conversa aberta (existente ou recém-criada).
        """
        tel = self._normalize_phone(telefone)

        # Tenta encontrar conversa aberta recente (últimas 24h)
        result = await session.execute(
            text("""
                SELECT id, tenant_id, telefone, persona, iniciada_em, encerrada_em
                FROM conversas
                WHERE tenant_id = :tenant_id
                  AND telefone = :telefone
                  AND encerrada_em IS NULL
                  AND iniciada_em > NOW() - INTERVAL '24 hours'
                ORDER BY iniciada_em DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id, "telefone": tel},
        )
        row = result.mappings().first()

        if row is not None:
            return Conversa(
                id=row["id"],
                tenant_id=row["tenant_id"],
                telefone=row["telefone"],
                persona=Persona(row["persona"]),
                iniciada_em=row["iniciada_em"],
                encerrada_em=row["encerrada_em"],
            )

        # Cria nova conversa
        result2 = await session.execute(
            text("""
                INSERT INTO conversas (tenant_id, telefone, persona)
                VALUES (:tenant_id, :telefone, :persona)
                RETURNING id, tenant_id, telefone, persona, iniciada_em, encerrada_em
            """),
            {"tenant_id": tenant_id, "telefone": tel, "persona": persona.value},
        )
        row2 = result2.mappings().first()
        if row2 is None:
            raise RuntimeError("Falha ao criar conversa")

        log.info("conversa_criada", tenant_id=tenant_id, persona=persona.value)
        return Conversa(
            id=row2["id"],
            tenant_id=row2["tenant_id"],
            telefone=row2["telefone"],
            persona=Persona(row2["persona"]),
            iniciada_em=row2["iniciada_em"],
            encerrada_em=row2["encerrada_em"],
        )

    async def add_mensagem(
        self,
        conversa_id: str,
        role: str,
        conteudo: str,
        session: AsyncSession,
    ) -> MensagemConversa:
        """Persiste uma mensagem na conversa.

        Args:
            conversa_id: ID da conversa.
            role: "user" ou "assistant".
            conteudo: texto da mensagem.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            MensagemConversa persistida.
        """
        result = await session.execute(
            text("""
                INSERT INTO mensagens_conversa (conversa_id, role, conteudo)
                VALUES (:conversa_id, :role, :conteudo)
                RETURNING id, conversa_id, role, conteudo, criado_em
            """),
            {"conversa_id": conversa_id, "role": role, "conteudo": conteudo},
        )
        row = result.mappings().first()
        if row is None:
            raise RuntimeError("Falha ao persistir mensagem")
        return MensagemConversa(
            id=row["id"],
            conversa_id=row["conversa_id"],
            role=row["role"],
            conteudo=row["conteudo"],
            criado_em=row["criado_em"],
        )

    async def get_historico(
        self,
        conversa_id: str,
        limit: int,
        session: AsyncSession,
    ) -> list[MensagemConversa]:
        """Retorna as últimas N mensagens da conversa em ordem cronológica.

        Args:
            conversa_id: ID da conversa.
            limit: número máximo de mensagens.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de MensagemConversa ordenada por criado_em ASC.
        """
        result = await session.execute(
            text("""
                SELECT id, conversa_id, role, conteudo, criado_em
                FROM mensagens_conversa
                WHERE conversa_id = :conversa_id
                ORDER BY criado_em ASC
                LIMIT :limit
            """),
            {"conversa_id": conversa_id, "limit": limit},
        )
        rows = result.mappings().all()
        return [
            MensagemConversa(
                id=r["id"],
                conversa_id=r["conversa_id"],
                role=r["role"],
                conteudo=r["conteudo"],
                criado_em=r["criado_em"],
            )
            for r in rows
        ]

    async def encerrar_conversa(
        self, conversa_id: str, session: AsyncSession
    ) -> None:
        """Marca a conversa como encerrada.

        Args:
            conversa_id: ID da conversa a encerrar.
            session: sessão SQLAlchemy assíncrona.
        """
        await session.execute(
            text("""
                UPDATE conversas
                SET encerrada_em = NOW()
                WHERE id = :conversa_id AND encerrada_em IS NULL
            """),
            {"conversa_id": conversa_id},
        )


class GestorRepo:
    """Repositório de gestores — lookup por telefone."""

    async def get_by_telefone(
        self, tenant_id: str, telefone: str, session: AsyncSession
    ) -> Gestor | None:
        """Busca gestor ativo pelo número de telefone normalizado.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            telefone: número E.164 sem sufixo @s.whatsapp.net.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Gestor se encontrado e ativo, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, telefone, nome, ativo, criado_em
                FROM gestores
                WHERE tenant_id = :tenant_id AND telefone = :telefone AND ativo = true
            """),
            {"tenant_id": tenant_id, "telefone": telefone},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return Gestor(
            id=row["id"],
            tenant_id=row["tenant_id"],
            telefone=row["telefone"],
            nome=row["nome"],
            ativo=row["ativo"],
            criado_em=row["criado_em"],
        )

    async def listar_ativos_por_tenant(
        self, tenant_id: str, session: AsyncSession
    ) -> list[Gestor]:
        """Retorna todos os gestores ativos do tenant, ordenados por criado_em.

        Args:
            tenant_id: ID do tenant — filtro obrigatório para isolamento.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de gestores ativos. Vazia se nenhum cadastrado.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, telefone, nome, ativo, criado_em
                FROM gestores
                WHERE tenant_id = :tenant_id AND ativo = true
                ORDER BY criado_em ASC
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.mappings().all()
        return [
            Gestor(
                id=row["id"],
                tenant_id=row["tenant_id"],
                telefone=row["telefone"],
                nome=row["nome"],
                ativo=row["ativo"],
                criado_em=row["criado_em"],
            )
            for row in rows
        ]


class RelatorioRepo:
    """Repositório de relatórios — queries agregadas sobre pedidos."""

    async def totais_periodo(
        self,
        tenant_id: str,
        data_inicio: object,
        data_fim: object,
        session: AsyncSession,
    ) -> dict:
        """Retorna totais GMV, n_pedidos e ticket_médio no período.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            data_inicio: datetime de início do período.
            data_fim: datetime de fim do período.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Dict com {total_gmv, n_pedidos, ticket_medio} como Decimal/int.
        """
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)              AS n_pedidos,
                    COALESCE(SUM(total_estimado), 0) AS total_gmv
                FROM pedidos
                WHERE tenant_id = :tenant_id
                  AND criado_em >= :data_inicio
                  AND criado_em <= :data_fim
            """),
            {"tenant_id": tenant_id, "data_inicio": data_inicio, "data_fim": data_fim},
        )
        row = result.mappings().first()
        n = int(row["n_pedidos"]) if row else 0
        gmv = row["total_gmv"] if row else 0
        ticket = (gmv / n) if n > 0 else 0
        return {"total_gmv": gmv, "n_pedidos": n, "ticket_medio": ticket}

    async def totais_por_rep(
        self,
        tenant_id: str,
        data_inicio: object,
        data_fim: object,
        session: AsyncSession,
    ) -> list[dict]:
        """Retorna totais por representante no período, ordenado por GMV DESC.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            data_inicio: datetime de início do período.
            data_fim: datetime de fim do período.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {rep_id, rep_nome, n_pedidos, total_gmv} ordenada por total_gmv DESC.
        """
        result = await session.execute(
            text("""
                SELECT
                    p.representante_id                   AS rep_id,
                    r.nome                               AS rep_nome,
                    COUNT(*)                             AS n_pedidos,
                    COALESCE(SUM(p.total_estimado), 0)  AS total_gmv
                FROM pedidos p
                LEFT JOIN representantes r
                    ON r.id = p.representante_id AND r.tenant_id = p.tenant_id
                WHERE p.tenant_id = :tenant_id
                  AND p.criado_em >= :data_inicio
                  AND p.criado_em <= :data_fim
                GROUP BY p.representante_id, r.nome
            """),
            {"tenant_id": tenant_id, "data_inicio": data_inicio, "data_fim": data_fim},
        )
        rows = result.mappings().all()
        items = [
            {
                "rep_id": r["rep_id"],
                "rep_nome": r["rep_nome"] or "Sem representante",
                "n_pedidos": int(r["n_pedidos"]),
                "total_gmv": r["total_gmv"],
            }
            for r in rows
        ]
        return sorted(items, key=lambda x: x["total_gmv"], reverse=True)

    async def totais_por_cliente(
        self,
        tenant_id: str,
        data_inicio: object,
        data_fim: object,
        session: AsyncSession,
    ) -> list[dict]:
        """Retorna totais por cliente no período, ordenado por GMV DESC.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            data_inicio: datetime de início do período.
            data_fim: datetime de fim do período.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {cliente_id, nome, cnpj, n_pedidos, total_gmv} ordenada por total_gmv DESC.
        """
        result = await session.execute(
            text("""
                SELECT
                    p.cliente_b2b_id                    AS cliente_id,
                    c.nome                              AS nome,
                    c.cnpj                              AS cnpj,
                    COUNT(*)                            AS n_pedidos,
                    COALESCE(SUM(p.total_estimado), 0) AS total_gmv
                FROM pedidos p
                LEFT JOIN clientes_b2b c
                    ON c.id = p.cliente_b2b_id AND c.tenant_id = p.tenant_id
                WHERE p.tenant_id = :tenant_id
                  AND p.criado_em >= :data_inicio
                  AND p.criado_em <= :data_fim
                GROUP BY p.cliente_b2b_id, c.nome, c.cnpj
            """),
            {"tenant_id": tenant_id, "data_inicio": data_inicio, "data_fim": data_fim},
        )
        rows = result.mappings().all()
        items = [
            {
                "cliente_id": r["cliente_id"],
                "nome": r["nome"] or "Desconhecido",
                "cnpj": r["cnpj"] or "",
                "n_pedidos": int(r["n_pedidos"]),
                "total_gmv": r["total_gmv"],
            }
            for r in rows
        ]
        return sorted(items, key=lambda x: x["total_gmv"], reverse=True)

    async def clientes_inativos(
        self,
        tenant_id: str,
        dias: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Retorna clientes sem pedido nos últimos N dias, ordenados por último pedido ASC.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            dias: número de dias sem pedido para considerar inativo.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {cliente_id, nome, cnpj, ultimo_pedido_em} ordenada por ultimo_pedido_em ASC.
        """
        result = await session.execute(
            text("""
                SELECT
                    c.id                        AS cliente_id,
                    c.nome                      AS nome,
                    c.cnpj                      AS cnpj,
                    MAX(p.criado_em)            AS ultimo_pedido_em
                FROM clientes_b2b c
                LEFT JOIN pedidos p
                    ON p.cliente_b2b_id = c.id AND p.tenant_id = c.tenant_id
                WHERE c.tenant_id = :tenant_id
                  AND c.ativo = true
                GROUP BY c.id, c.nome, c.cnpj
                HAVING MAX(p.criado_em) IS NULL
                    OR MAX(p.criado_em) < NOW() - (:dias * INTERVAL '1 day')
            """),
            {"tenant_id": tenant_id, "dias": dias},
        )
        rows = result.mappings().all()
        items = [
            {
                "cliente_id": r["cliente_id"],
                "nome": r["nome"],
                "cnpj": r["cnpj"],
                "ultimo_pedido_em": r["ultimo_pedido_em"],
            }
            for r in rows
        ]
        return sorted(items, key=lambda x: (x["ultimo_pedido_em"] is not None, x["ultimo_pedido_em"]))

    async def top_produtos_por_periodo(
        self,
        tenant_id: str,
        dias: int,
        limite: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Retorna top produtos por quantidade vendida no período.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            dias: número de dias para o período (ex: 30 = últimos 30 dias).
            limite: máximo de produtos a retornar.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {produto_nome, quantidade_total, valor_total} ordenada DESC.
        """
        from datetime import datetime, timedelta, timezone
        data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)
        result = await session.execute(
            text("""
                SELECT
                    ip.produto_nome                       AS produto_nome,
                    SUM(ip.quantidade)                    AS quantidade_total,
                    COALESCE(SUM(ip.preco_unitario * ip.quantidade), 0) AS valor_total
                FROM itens_pedido ip
                JOIN pedidos p ON p.id = ip.pedido_id
                WHERE p.tenant_id = :tenant_id
                  AND p.status = 'confirmado'
                  AND p.criado_em >= :data_inicio
                GROUP BY ip.produto_nome
                ORDER BY quantidade_total DESC
                LIMIT :limite
            """),
            {"tenant_id": tenant_id, "limite": limite, "data_inicio": data_inicio},
        )
        rows = result.mappings().all()
        return [
            {
                "produto_nome": r["produto_nome"],
                "quantidade_total": int(r["quantidade_total"]),
                "valor_total": r["valor_total"],
            }
            for r in rows
        ]
