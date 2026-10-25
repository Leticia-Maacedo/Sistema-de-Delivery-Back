"""Regras do acompanhamento do pedido (Sprint 3 - Acompanhar Entrega).

Fica separado do controller para poder ser testado sem banco, igual ao
`frete.py`. Aqui so existem regras: quais status existem, em que ordem
o pedido anda, quem pode mover cada etapa e como o codigo de entrega e
gerado e conferido.

Fluxo do pedido para entrega (delivery):
    aguardando_aceite -> aceito -> em_preparacao -> pronto_para_entrega
    -> em_transito -> entregue

Fluxo do pedido para retirada no balcao:
    aguardando_aceite -> aceito -> em_preparacao -> pronto_para_retirada
    -> entregue

O pedido pode ser cancelado enquanto ainda nao comecou a ser preparado
(aguardando_aceite ou aceito). "entregue" so e alcancado conferindo o
codigo de entrega que o cliente recebe.
"""

import secrets


AGUARDANDO_ACEITE = "aguardando_aceite"
ACEITO = "aceito"
EM_PREPARACAO = "em_preparacao"
PRONTO_PARA_ENTREGA = "pronto_para_entrega"
PRONTO_PARA_RETIRADA = "pronto_para_retirada"
EM_TRANSITO = "em_transito"
ENTREGUE = "entregue"
CANCELADO = "cancelado"

FLUXO_DELIVERY = [
    AGUARDANDO_ACEITE,
    ACEITO,
    EM_PREPARACAO,
    PRONTO_PARA_ENTREGA,
    EM_TRANSITO,
    ENTREGUE,
]

FLUXO_RETIRADA = [
    AGUARDANDO_ACEITE,
    ACEITO,
    EM_PREPARACAO,
    PRONTO_PARA_RETIRADA,
    ENTREGUE,
]

ROTULOS = {
    AGUARDANDO_ACEITE: "Aguardando o restaurante",
    ACEITO: "Pedido aceito",
    EM_PREPARACAO: "Em preparação",
    PRONTO_PARA_ENTREGA: "Pronto para entrega",
    PRONTO_PARA_RETIRADA: "Pronto para retirada",
    EM_TRANSITO: "Saiu para entrega",
    ENTREGUE: "Entregue",
    CANCELADO: "Cancelado",
}

# Status em que o pedido ainda pode ser cancelado.
CANCELAVEIS = {AGUARDANDO_ACEITE, ACEITO}

# Quem pode levar o pedido PARA cada status (tipo do usuario).
# O admin pode tudo. "entregue" nao aparece aqui porque so e alcancado
# pela conferencia do codigo (ver QUEM_CONFIRMA_ENTREGA).
QUEM_PODE = {
    ACEITO: {"restaurante"},
    EM_PREPARACAO: {"restaurante"},
    PRONTO_PARA_ENTREGA: {"restaurante"},
    PRONTO_PARA_RETIRADA: {"restaurante"},
    EM_TRANSITO: {"entregador"},
    CANCELADO: {"restaurante"},
}

# Quem confere o codigo e conclui o pedido, por tipo de entrega.
QUEM_CONFIRMA_ENTREGA = {
    "delivery": {"entregador"},
    "retirada": {"restaurante"},
}

# RN04: o cliente so cancela o proprio pedido enquanto ele aguarda o aceite.
CLIENTE_PODE_CANCELAR = {AGUARDANDO_ACEITE}

# Tipos de usuario que operam pedidos (restaurante, entregador e admin).
OPERADORES = {"restaurante", "entregador", "admin"}

TAMANHO_CODIGO = 4


def fluxo(tipo_entrega: str) -> list[str]:
    """Sequencia de status do pedido conforme o tipo de entrega."""

    return FLUXO_RETIRADA if tipo_entrega == "retirada" else FLUXO_DELIVERY


def rotulo(status: str) -> str:
    """Texto do status para mostrar ao cliente."""

    return ROTULOS.get(status, status)


def proximo_status(status_atual: str, tipo_entrega: str) -> str | None:
    """Proxima etapa do fluxo, ou None se o pedido ja terminou."""

    etapas = fluxo(tipo_entrega)

    if status_atual not in etapas:
        return None  # cancelado ou status desconhecido

    posicao = etapas.index(status_atual)

    if posicao + 1 >= len(etapas):
        return None

    return etapas[posicao + 1]


def status_finalizado(status: str) -> bool:
    """O pedido nao muda mais (entregue ou cancelado)."""

    return status in (ENTREGUE, CANCELADO)


def validar_transicao(
    status_atual: str,
    novo_status: str,
    tipo_entrega: str,
    tipo_usuario: str,
) -> str | None:
    """Confere se o usuario pode mover o pedido para `novo_status`.

    Retorna a mensagem de erro, ou None se a mudanca e permitida.
    """

    if status_finalizado(status_atual):
        return f"O pedido ja esta '{rotulo(status_atual)}' e nao pode mudar."

    if novo_status == ENTREGUE:
        return "Para concluir o pedido, confirme o codigo de entrega."

    if novo_status == CANCELADO:
        if status_atual not in CANCELAVEIS:
            return "O pedido so pode ser cancelado antes de entrar em preparo."
    else:
        esperado = proximo_status(status_atual, tipo_entrega)

        if novo_status != esperado:
            return (
                f"Mudanca invalida: de '{rotulo(status_atual)}' o pedido "
                f"so pode ir para '{rotulo(esperado)}'."
            )

    if tipo_usuario != "admin" and tipo_usuario not in QUEM_PODE.get(novo_status, set()):
        return f"Usuario do tipo '{tipo_usuario}' nao pode marcar '{rotulo(novo_status)}'."

    return None


def validar_confirmacao_entrega(
    status_atual: str,
    tipo_entrega: str,
    tipo_usuario: str,
) -> str | None:
    """Confere se o pedido esta na etapa de entregar e quem esta confirmando."""

    etapas = fluxo(tipo_entrega)
    etapa_de_entrega = etapas[-2]  # em_transito (delivery) / pronto_para_retirada

    if status_atual != etapa_de_entrega:
        return (
            f"O pedido precisa estar '{rotulo(etapa_de_entrega)}' "
            "para confirmar a entrega."
        )

    permitidos = QUEM_CONFIRMA_ENTREGA.get(tipo_entrega, set())

    if tipo_usuario != "admin" and tipo_usuario not in permitidos:
        return f"Usuario do tipo '{tipo_usuario}' nao pode confirmar esta entrega."

    return None


def validar_cancelamento_cliente(status_atual: str) -> str | None:
    """RN04: confere se o cliente ainda pode cancelar o pedido.

    Retorna a mensagem de erro, ou None se o cancelamento e permitido.
    """

    if status_atual == CANCELADO:
        return "O pedido ja esta cancelado."

    if status_atual not in CLIENTE_PODE_CANCELAR:
        return (
            f"O pedido ja esta '{rotulo(status_atual)}'. O cliente so pode "
            "cancelar enquanto o pedido aguarda o aceite do restaurante."
        )

    return None


def gerar_codigo_entrega() -> str:
    """Codigo numerico que o cliente informa ao receber o pedido."""

    return "".join(secrets.choice("0123456789") for _ in range(TAMANHO_CODIGO))


def codigo_confere(codigo_correto: str | None, codigo_informado: str) -> bool:
    """Compara os codigos sem vazar tempo de comparacao."""

    if not codigo_correto:
        return False

    return secrets.compare_digest(codigo_correto, codigo_informado.strip())
