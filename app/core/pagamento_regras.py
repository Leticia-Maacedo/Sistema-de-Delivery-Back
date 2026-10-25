"""Regras do pagamento do pedido (Sprint 3 - Fechar Pedido).

Fica separado do controller para poder ser testado sem banco, igual ao
`status_pedido.py`. Aqui so existem regras: quais status o pagamento tem,
quando o restaurante pode aceitar o pedido e como o status do Asaas vira
o status do EntregaFood.

Metodos (backlog 18):
    cartao   -> cobrado na hora pelo gateway: aprovado ou recusado.
    pix      -> gera QR Code; fica "pendente" ate o cliente pagar.
    dinheiro -> nao passa pelo gateway; fica "a_receber" e vira
                "aprovado" quando o pedido e entregue (o entregador ou
                o balcao recebe o dinheiro junto com o codigo de entrega).

Regra do aceite (definida com o grupo): o restaurante so aceita o pedido
com pagamento "aprovado" (cartao e PIX) ou "a_receber" (dinheiro).
"""

PENDENTE = "pendente"
APROVADO = "aprovado"
RECUSADO = "recusado"
A_RECEBER = "a_receber"
EXPIRADO = "expirado"
CANCELADO = "cancelado"
ESTORNADO = "estornado"
# Pedido cancelado com pagamento aprovado, aguardando o Asaas aceitar o
# estorno (logo depois da aprovacao o Asaas pede para tentar mais tarde).
ESTORNO_PENDENTE = "estorno_pendente"

ROTULOS = {
    PENDENTE: "Aguardando pagamento",
    APROVADO: "Pago",
    RECUSADO: "Recusado",
    A_RECEBER: "Pagar na entrega",
    EXPIRADO: "PIX expirado",
    CANCELADO: "Cancelado",
    ESTORNADO: "Estornado",
    ESTORNO_PENDENTE: "Estorno em andamento",
}

# Status que liberam o restaurante a aceitar o pedido.
LIBERAM_ACEITE = {APROVADO, A_RECEBER}

# Status em que o cliente ainda pode trocar o metodo ou tentar de novo.
PODE_REFAZER = {PENDENTE, RECUSADO, EXPIRADO, CANCELADO, A_RECEBER}

# Status do Asaas -> status do EntregaFood.
# https://docs.asaas.com/reference/listar-cobrancas (campo "status")
STATUS_ASAAS = {
    "PENDING": PENDENTE,
    "AWAITING_RISK_ANALYSIS": PENDENTE,
    "CONFIRMED": APROVADO,
    "RECEIVED": APROVADO,
    "RECEIVED_IN_CASH": APROVADO,
    "OVERDUE": EXPIRADO,
    "REFUNDED": ESTORNADO,
    "REFUND_REQUESTED": ESTORNADO,
    "REFUND_IN_PROGRESS": ESTORNADO,
    "CHARGEBACK_REQUESTED": ESTORNADO,
    "CHARGEBACK_DISPUTE": ESTORNADO,
    "AWAITING_CHARGEBACK_REVERSAL": ESTORNADO,
    "DUNNING_REQUESTED": PENDENTE,
    "DUNNING_RECEIVED": APROVADO,
}


def rotulo(status: str) -> str:
    """Texto do status para mostrar ao cliente."""

    return ROTULOS.get(status, status)


def status_do_asaas(status_asaas: str | None) -> str:
    """Converte o status da cobranca no Asaas. Desconhecido = pendente."""

    return STATUS_ASAAS.get((status_asaas or "").upper(), PENDENTE)


def permite_aceite(metodo: str | None, status: str | None) -> bool:
    """O restaurante pode aceitar o pedido com este pagamento?"""

    if status == APROVADO:
        return True

    return metodo == "dinheiro" and status == A_RECEBER


def pode_refazer(status: str | None) -> bool:
    """Sem pagamento, ou com um pagamento que ainda nao foi aprovado."""

    return status is None or status in PODE_REFAZER


def numero_nota_fiscal(pedido_id: int, ano: int) -> str:
    """Numero da nota/cupom fiscal simulado: NF-<ano>-<pedido com 6 digitos>."""

    return f"NF-{ano}-{pedido_id:06d}"


def somente_digitos(valor: str | None) -> str:
    """Remove pontos, tracos e espacos (CPF, CEP, telefone)."""

    return "".join(c for c in (valor or "") if c.isdigit())


def cpf_valido(cpf: str | None) -> bool:
    """Confere os digitos verificadores do CPF."""

    numeros = somente_digitos(cpf)

    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[tamanho]):
            return False

    return True
