"""Tipos do domínio Tenants — Pydantic models e enums.

Camada Types: sem imports internos do projeto.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    """Papel do usuário na plataforma."""

    gestor = "gestor"
    rep = "rep"
    cliente = "cliente"


class Tenant(BaseModel):
    """Tenant — distribuidora ou fabricante cadastrada na plataforma."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    cnpj: str
    ativo: bool = True
    whatsapp_number: str | None = None
    config_json: dict[str, Any] = {}
    criado_em: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict compatível com JSONResponse."""
        return {
            "id": self.id,
            "nome": self.nome,
            "cnpj": self.cnpj,
            "ativo": self.ativo,
            "whatsapp_number": self.whatsapp_number,
            "config_json": self.config_json,
            "criado_em": self.criado_em.isoformat(),
        }


class Usuario(BaseModel):
    """Usuário autenticável — gestor, representante ou cliente B2B."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    cnpj: str
    senha_hash: str
    role: Role
    ativo: bool = True
    criado_em: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict — exclui senha_hash por segurança."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "cnpj": self.cnpj,
            "role": self.role,
            "ativo": self.ativo,
            "criado_em": self.criado_em.isoformat(),
        }
