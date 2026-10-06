"""Schemas de Pedido do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PedidoCriarIn(BaseModel):
    """Dados necessários para criar um pedido."""

    restaurante_id: int
    tipo_entrega: str = Field(min_length=1, max_length=20)
    forma_pagamento: str = Field(min_length=1, max_length=20)
    valor_total: Decimal = Field(ge=0)
    taxa_entrega: Decimal = Field(ge=0)


class PedidoOut(BaseModel):
    """Dados retornados pela API após criação do pedido."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    restaurante_id: int
    entregador_id: int | None = None
    status: str
    tipo_entrega: str
    forma_pagamento: str
    valor_total: Decimal
    taxa_entrega: Decimal
    cupom_fiscal: str | None = None
    criado_em: datetime
    atualizado_em: datetime | None = None