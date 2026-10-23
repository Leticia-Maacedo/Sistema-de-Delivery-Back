"""Schemas de Pedido do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pagamento import MetodoPagamento


class PedidoCriarIn(BaseModel):
    """Dados necessários para criar um pedido a partir da cesta.

    Os itens, o restaurante, a taxa de entrega e o total vêm da cesta e
    são calculados pelo servidor. `restaurante_id`, `valor_total` e
    `taxa_entrega` continuam aceitos por compatibilidade com o front,
    mas são ignorados.
    """

    forma_pagamento: MetodoPagamento
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
    status: str
    tipo_entrega: str
    forma_pagamento: str
    valor_total: Decimal
    taxa_entrega: Decimal
    cupom_fiscal: str | None = None
    criado_em: datetime
    atualizado_em: datetime | None = None

# ------------------------------------------------- Sprint 3 - Acompanhar Entrega


class StatusPedidoIn(BaseModel):
    """Novo status pedido pelo restaurante/entregador."""

    status: str = Field(min_length=1, max_length=30)


class ConfirmarEntregaIn(BaseModel):
    """Codigo de entrega que o cliente informa ao receber o pedido."""

    codigo: str = Field(min_length=4, max_length=6, pattern=r"^\s*\d{4,6}\s*$")


class ItemPedidoOut(BaseModel):
    """Item do pedido com o preco congelado no fechamento."""

    produto_id: int
    nome: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal


class EtapaPedidoOut(BaseModel):
    """Uma etapa da linha do tempo do pedido."""

    status: str
    rotulo: str
    concluida: bool
    atual: bool
    data: datetime | None = None


class PedidoResumoOut(BaseModel):
    """Pedido na listagem (historico do cliente e painel de entregas)."""

    id: int
    restaurante_id: int
    restaurante_nome: str | None
    status: str
    status_rotulo: str
    tipo_entrega: str
    forma_pagamento: str
    valor_total: Decimal
    quantidade_itens: int
    criado_em: datetime
    proximo_status: str | None = None
    proximo_status_rotulo: str | None = None
    # Endereco copiado no fechamento (so delivery).
    endereco_entrega: str | None = None


class PedidoDetalheOut(PedidoResumoOut):
    """Pedido completo para a tela de acompanhamento."""

    cliente_id: int
    # Vem de entrega.entregador_id (o pedido nao guarda mais o entregador).
    entregador_id: int | None = None
    taxa_entrega: Decimal
    subtotal: Decimal
    atualizado_em: datetime | None = None
    finalizado: bool
    itens: list[ItemPedidoOut]
    etapas: list[EtapaPedidoOut]
    # So vai preenchido para o proprio cliente: e ele quem informa o
    # codigo ao entregador (ou no balcao, na retirada).
    codigo_entrega: str | None = None
    pagamento_status: str | None = None
    # Numero da nota fiscal (emitida quando o pagamento e aprovado).
    nota_fiscal: str | None = None
