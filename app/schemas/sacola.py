"""Schemas da cesta de compras do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
