"""Schemas de Pedido do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PedidoCriarIn(BaseModel):
    """Dados necessários para criar um pedido a partir da cesta.

    Os itens, o restaurante, a taxa de entrega e o total vêm da cesta e
    são calculados pelo servidor. `restaurante_id`, `valor_total` e
    `taxa_entrega` continuam aceitos por compatibilidade com o front,
    mas são ignorados.
    """

    forma_pagamento: str = Field(min_length=1, max_length=20)
    tipo_entrega: Literal["delivery", "retirada"] = "delivery"
    local_id: int | None = None
    restaurante_id: int | None = None
    valor_total: Decimal | None = None
    taxa_entrega: Decimal | None = None


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