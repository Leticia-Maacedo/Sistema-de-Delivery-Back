"""Schemas de Pagamento do EntregaFood."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EscolhaPagamentoIn(BaseModel):
    """Dados para escolher o tipo de pagamento."""

    metodo: Literal["cartao"]


class PagamentoCartaoIn(BaseModel):
    """Dados necessarios para simular o processamento por cartao.

    O backend nao recebe nem armazena numero completo do cartao,
    CVV ou senha. Para esta entrega, o gateway externo e simulado.
    """

    pedido_id: int = Field(gt=0)
    metodo: Literal["cartao"] = "cartao"


class PagamentoOut(BaseModel):
    """Resposta da API apos consultar/processar um pagamento."""

    id: int
    pedido_id: int
    metodo: str
    status: str
    valor: Decimal
    transacao_externa_id: str | None
    criado_em: datetime