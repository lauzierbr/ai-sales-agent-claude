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
                SELECT id, tenant_id, nome, cnpj, telefone, ativo, criado_em
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
