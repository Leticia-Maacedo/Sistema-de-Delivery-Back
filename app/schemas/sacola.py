"""Schemas da cesta de compras do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ItemSacolaAdicionar(BaseModel):
    """Dados necessários para adicionar um produto à cesta."""

    produto_id: int
    quantidade: int = Field(default=1, ge=1)


class ItemSacolaQuantidade(BaseModel):
    """Dados necessários para alterar a quantidade de um item da cesta."""

    quantidade: int = Field(ge=1)


class ItemSacolaOut(BaseModel):
    id: int
    produto_id: int
    nome: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal


class SacolaOut(BaseModel):
    id: int | None
    cliente_id: int
    criado_em: datetime | None
    atualizado_em: datetime | None
    itens: list[ItemSacolaOut]
    total: Decimal