"""Schemas de Pagamento do EntregaFood."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Tipo unico do metodo de pagamento, usado na criacao do pedido
# (PedidoCriarIn.forma_pagamento) e na escolha do metodo
# (EscolhaPagamentoIn.metodo). Qualquer outro valor devolve 422.
MetodoPagamento = Literal["cartao", "pix", "dinheiro"]


class EscolhaPagamentoIn(BaseModel):
    """Dados para escolher o tipo de pagamento."""

    metodo: MetodoPagamento


class PagadorIn(BaseModel):
    """Dados do pagador exigidos pelo Asaas para criar a cobranca.

    Sem o Asaas configurado (gateway simulado) podem ficar vazios.
    """

    cpf: str | None = Field(default=None, pattern=r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")
    cep: str | None = Field(default=None, pattern=r"^\d{5}-?\d{3}$")
    numero_endereco: str | None = Field(default=None, max_length=10)
    telefone: str | None = Field(default=None, max_length=20)


class CartaoIn(BaseModel):
    """Dados do cartao.

    Vao direto para o gateway e NUNCA sao gravados no banco nem no log.
    """

    titular: str = Field(min_length=3, max_length=100)
    numero: str = Field(pattern=r"^\d{13,19}$")
    mes_validade: str = Field(pattern=r"^(0[1-9]|1[0-2])$")
    ano_validade: str = Field(pattern=r"^\d{4}$")
    cvv: str = Field(pattern=r"^\d{3,4}$")


class PagamentoCartaoIn(PagadorIn):
    """Dados para pagar o pedido com cartao de credito.

    `cartao` e obrigatorio com o Asaas configurado. No gateway simulado
    pode ser omitido (o front antigo so mandava o pedido_id).
    """

    pedido_id: int = Field(gt=0)
    metodo: Literal["cartao"] = "cartao"
    cartao: CartaoIn | None = None


class PagamentoPixIn(PagadorIn):
    """Dados para gerar a cobranca PIX do pedido."""

    pedido_id: int = Field(gt=0)


class PagamentoOut(BaseModel):
    """Resposta da API apos consultar/processar um pagamento."""

    id: int
    pedido_id: int
    metodo: str
    status: str
    status_rotulo: str
    valor: Decimal
    transacao_externa_id: str | None
    mensagem: str | None = None
    gateway: str
    criado_em: datetime
    atualizado_em: datetime | None = None
    # PIX: imagem do QR Code (data URI base64) e o "copia e cola".
    pix_qrcode: str | None = None
    pix_copia_cola: str | None = None
    pix_expira_em: datetime | None = None
    # Nota fiscal (preenchida quando o pagamento e aprovado).
    nota_fiscal: str | None = None
