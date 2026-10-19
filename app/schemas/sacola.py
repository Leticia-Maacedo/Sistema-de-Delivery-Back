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

class ResumoCestaOut(BaseModel):
    """Subtotal, taxa de entrega e total da cesta antes do fechamento."""

    cesta_id: int | None
    restaurante_id: int | None
    quantidade_itens: int
    subtotal: Decimal
    tipo_entrega: str
    local_entrega_id: int | None
    distancia_km: Decimal | None
    metodo_distancia: str | None  # "rota", "estimada" ou None (retirada)
    taxa_entrega: Decimal
    total: Decimal
    pode_fechar: bool
    motivo: str | None
