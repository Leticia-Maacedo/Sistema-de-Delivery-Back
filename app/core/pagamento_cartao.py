"""Gateway de pagamento SIMULADO (cartao e PIX).

E usado quando `ASAAS_API_KEY` esta vazia: para rodar o projeto local,
nos testes e no Postman sem depender do Asaas. Tem a mesma interface do
gateway real (app/core/pagamento_asaas.py), escolhido em
app/core/pagamento_gateway.py.

Regras da simulacao:
    - Cartao: valor positivo e aprovado. Os cartoes de teste de recusa do
      Asaas (CARTOES_RECUSADOS) sao recusados, para o Postman poder testar
      o caso de cartao recusado com ou sem o Asaas.
    - PIX: gera um "copia e cola" de mentira; fica pendente ate a rota de
      simulacao marcar como pago.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.core.pagamento_regras import APROVADO, PENDENTE, RECUSADO

# Cartoes de teste do Asaas sandbox que simulam transacao recusada.
CARTOES_RECUSADOS = {"5184019740373151", "4916561358240741"}

VALIDADE_PIX = timedelta(hours=1)


@dataclass
class ResultadoPagamentoCartao:
    """Resultado retornado pelo gateway (simulado ou Asaas)."""

    aprovado: bool
    status: str
    transacao_externa_id: str | None
    mensagem: str | None = None
    pix_copia_cola: str | None = None
    pix_qrcode: str | None = None  # data URI da imagem (quando o gateway manda)
    pix_expira_em: datetime | None = None


# Nome mais curto para o resto do sistema.
ResultadoPagamento = ResultadoPagamentoCartao


def processar_pagamento_cartao(
    *,
    valor: Decimal,
    numero_cartao: str | None = None,
) -> ResultadoPagamentoCartao:
    """Simula o processamento de uma transacao por cartao."""

    transacao = f"SIM-{uuid4().hex}"

    if valor <= Decimal("0.00"):
        return ResultadoPagamentoCartao(
            aprovado=False,
            status=RECUSADO,
            transacao_externa_id=transacao,
            mensagem="Valor do pedido invalido para cobranca.",
        )

    if numero_cartao in CARTOES_RECUSADOS:
        return ResultadoPagamentoCartao(
            aprovado=False,
            status=RECUSADO,
            transacao_externa_id=transacao,
            mensagem="Transacao nao autorizada pela operadora do cartao.",
        )

    return ResultadoPagamentoCartao(
        aprovado=True,
        status=APROVADO,
        transacao_externa_id=transacao,
        mensagem="Pagamento aprovado.",
    )


def criar_pix_simulado(
    *,
    valor: Decimal,
    pedido_id: int,
) -> ResultadoPagamentoCartao:
    """Gera uma cobranca PIX de mentira, pendente de pagamento."""

    transacao = f"SIM-PIX-{uuid4().hex}"
    centavos = int((valor * 100).quantize(Decimal("1")))

    return ResultadoPagamentoCartao(
        aprovado=False,
        status=PENDENTE,
        transacao_externa_id=transacao,
        mensagem="PIX gerado. Aguardando pagamento.",
        pix_copia_cola=(
            "00020126SIMULADO-ENTREGAFOOD"
            f"5204000053039865406{centavos:010d}"
            f"5802BR5911ENTREGAFOOD6009SAO PAULO62110507PED{pedido_id:04d}6304SIMU"
        ),
        pix_expira_em=datetime.now() + VALIDADE_PIX,
    )
