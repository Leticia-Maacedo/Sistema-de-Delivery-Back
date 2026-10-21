"""Servico de processamento de pagamento por cartao.

Nesta entrega academica nao foi definido um gateway de pagamento externo.
Por isso, esta camada simula a comunicacao com um provedor de cartao.

A separacao em um servico proprio permite substituir futuramente esta
implementacao por um gateway real sem alterar as regras do controller.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4


@dataclass
class ResultadoPagamentoCartao:
    """Resultado retornado pelo servico de pagamento."""

    aprovado: bool
    status: str
    transacao_externa_id: str


def processar_pagamento_cartao(
    *,
    valor: Decimal,
) -> ResultadoPagamentoCartao:
    """Simula o processamento de uma transacao por cartao.

    Para esta entrega, pagamentos com valor positivo sao aprovados.
    Cada processamento recebe um identificador unico de transacao,
    simulando o codigo retornado por um gateway externo.
    """

    if valor <= Decimal("0.00"):
        return ResultadoPagamentoCartao(
            aprovado=False,
            status="recusado",
            transacao_externa_id=f"SIM-{uuid4().hex}",
        )

    return ResultadoPagamentoCartao(
        aprovado=True,
        status="aprovado",
        transacao_externa_id=f"SIM-{uuid4().hex}",
    )