"""Escolhe o gateway de pagamento: Asaas (real) ou simulado.

O controller so conversa com este modulo. Com `ASAAS_API_KEY` no .env as
cobrancas vao para o Asaas; com a chave vazia (local, testes, Postman sem
chave) cai no gateway simulado de app/core/pagamento_cartao.py. Assim o
resto do sistema nao muda quando o gateway muda.
"""

from decimal import Decimal

from app.core.config import get_settings
from app.core.pagamento_asaas import (
    AsaasErro,
    AsaasIndisponivel,
    ClienteAsaas,
    DadosCartao,
    Pagador,
)
from app.core.pagamento_cartao import (
    ResultadoPagamento,
    criar_pix_simulado,
    processar_pagamento_cartao,
)
from app.core.pagamento_regras import APROVADO

__all__ = [
    "AsaasErro",
    "AsaasIndisponivel",
    "DadosCartao",
    "Pagador",
    "ResultadoPagamento",
    "asaas_ativo",
    "nome_gateway",
    "cobrar_cartao",
    "criar_pix",
    "consultar_status",
    "cancelar",
    "simular_pagamento_pix",
    "simulacao_permitida",
]


def asaas_ativo() -> bool:
    return bool(get_settings().ASAAS_API_KEY.strip())


def nome_gateway(transacao_externa_id: str | None = None) -> str:
    """"asaas" ou "simulado" (pagamentos SIM-* sempre sao simulados)."""

    if transacao_externa_id and transacao_externa_id.startswith("SIM-"):
        return "simulado"

    return "asaas" if asaas_ativo() else "simulado"


def _cliente() -> ClienteAsaas:
    settings = get_settings()
    return ClienteAsaas(settings.ASAAS_API_KEY.strip(), settings.ASAAS_BASE_URL)


def cobrar_cartao(
    *,
    valor: Decimal,
    pagador: Pagador,
    cartao: DadosCartao | None,
    descricao: str,
    referencia: str,
    ip_remoto: str | None = None,
) -> ResultadoPagamento:
    if not asaas_ativo():
        return processar_pagamento_cartao(
            valor=valor,
            numero_cartao=cartao.numero if cartao else None,
        )

    return _cliente().cobrar_cartao(
        pagador=pagador,
        cartao=cartao,
        valor=valor,
        descricao=descricao,
        referencia=referencia,
        ip_remoto=ip_remoto,
    )


def criar_pix(
    *,
    valor: Decimal,
    pedido_id: int,
    pagador: Pagador,
    descricao: str,
    referencia: str,
) -> ResultadoPagamento:
    if not asaas_ativo():
        return criar_pix_simulado(valor=valor, pedido_id=pedido_id)

    return _cliente().criar_pix(
        pagador=pagador,
        valor=valor,
        descricao=descricao,
        referencia=referencia,
    )


def consultar_status(transacao_externa_id: str | None) -> str | None:
    """Status atual no gateway, ou None quando nao ha o que consultar."""

    if not transacao_externa_id or nome_gateway(transacao_externa_id) == "simulado":
        return None

    return _cliente().consultar_status(transacao_externa_id)


def cancelar(transacao_externa_id: str | None) -> None:
    """Cancela a cobranca anterior quando o cliente troca o metodo (melhor esforco)."""

    if not transacao_externa_id or nome_gateway(transacao_externa_id) == "simulado":
        return

    try:
        _cliente().cancelar(transacao_externa_id)
    except (AsaasErro, AsaasIndisponivel):
        pass  # cobranca ja paga/removida: nao impede a troca


def simular_pagamento_pix(transacao_externa_id: str | None, valor: Decimal) -> str:
    """Marca o PIX como pago (somente simulado ou sandbox do Asaas)."""

    if nome_gateway(transacao_externa_id) == "asaas":
        _cliente().confirmar_recebimento_em_dinheiro(transacao_externa_id, valor)
        return _cliente().consultar_status(transacao_externa_id)

    return APROVADO


def simulacao_permitida() -> bool:
    """A rota de simular PIX pago so existe fora da producao do Asaas."""

    return not asaas_ativo() or "sandbox" in get_settings().ASAAS_BASE_URL
