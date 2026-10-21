"""Testes do acompanhamento do pedido - Sprint 3.

Cobre o fluxo de status (delivery e retirada), quem pode mover cada
etapa, o cancelamento e o codigo de entrega (app/core/status_pedido.py).

Executar:  python -m pytest testes/teste_status_pedido.py -v
"""

from app.core.status_pedido import (
    ACEITO,
    AGUARDANDO_ACEITE,
    CANCELADO,
    EM_PREPARACAO,
    EM_TRANSITO,
    ENTREGUE,
    PRONTO_PARA_ENTREGA,
    PRONTO_PARA_RETIRADA,
    TAMANHO_CODIGO,
    codigo_confere,
    fluxo,
    gerar_codigo_entrega,
    proximo_status,
    rotulo,
    status_finalizado,
    validar_confirmacao_entrega,
    validar_transicao,
)


# ------------------------------------------------------------------ fluxo

def test_fluxo_delivery_passa_pelo_transito():
    assert fluxo("delivery") == [
        AGUARDANDO_ACEITE, ACEITO, EM_PREPARACAO,
        PRONTO_PARA_ENTREGA, EM_TRANSITO, ENTREGUE,
    ]


def test_fluxo_retirada_nao_tem_transito():
    etapas = fluxo("retirada")
    assert EM_TRANSITO not in etapas
    assert etapas[-2:] == [PRONTO_PARA_RETIRADA, ENTREGUE]


def test_proximo_status_delivery():
    assert proximo_status(AGUARDANDO_ACEITE, "delivery") == ACEITO
    assert proximo_status(PRONTO_PARA_ENTREGA, "delivery") == EM_TRANSITO
    assert proximo_status(EM_TRANSITO, "delivery") == ENTREGUE


def test_proximo_status_retirada():
    assert proximo_status(EM_PREPARACAO, "retirada") == PRONTO_PARA_RETIRADA
    assert proximo_status(PRONTO_PARA_RETIRADA, "retirada") == ENTREGUE


def test_sem_proximo_quando_finalizado():
    assert proximo_status(ENTREGUE, "delivery") is None
    assert proximo_status(CANCELADO, "delivery") is None


def test_finalizados():
    assert status_finalizado(ENTREGUE)
    assert status_finalizado(CANCELADO)
    assert not status_finalizado(EM_TRANSITO)


def test_rotulo_para_o_cliente():
    assert rotulo(EM_TRANSITO) == "Saiu para entrega"
    assert rotulo("desconhecido") == "desconhecido"


# ------------------------------------------------------- mudar status

def test_restaurante_aceita_pedido():
    assert validar_transicao(AGUARDANDO_ACEITE, ACEITO, "delivery", "restaurante") is None


def test_nao_pula_etapas():
    erro = validar_transicao(AGUARDANDO_ACEITE, EM_PREPARACAO, "delivery", "restaurante")
    assert erro is not None and "Pedido aceito" in erro


def test_nao_volta_etapas():
    assert validar_transicao(EM_PREPARACAO, ACEITO, "delivery", "restaurante") is not None


def test_entregador_nao_prepara_pedido():
    assert validar_transicao(ACEITO, EM_PREPARACAO, "delivery", "entregador") is not None


def test_entregador_sai_para_entrega():
    assert validar_transicao(PRONTO_PARA_ENTREGA, EM_TRANSITO, "delivery", "entregador") is None


def test_restaurante_nao_sai_para_entrega():
    assert validar_transicao(PRONTO_PARA_ENTREGA, EM_TRANSITO, "delivery", "restaurante") is not None


def test_cliente_nao_muda_status():
    assert validar_transicao(AGUARDANDO_ACEITE, ACEITO, "delivery", "cliente") is not None


def test_admin_pode_tudo_na_ordem():
    assert validar_transicao(PRONTO_PARA_ENTREGA, EM_TRANSITO, "delivery", "admin") is None


def test_retirada_nao_tem_em_transito():
    assert validar_transicao(PRONTO_PARA_RETIRADA, EM_TRANSITO, "retirada", "admin") is not None


def test_entregue_so_com_codigo():
    erro = validar_transicao(EM_TRANSITO, ENTREGUE, "delivery", "admin")
    assert erro is not None and "codigo" in erro


def test_cancelar_antes_do_preparo():
    assert validar_transicao(AGUARDANDO_ACEITE, CANCELADO, "delivery", "restaurante") is None
    assert validar_transicao(ACEITO, CANCELADO, "delivery", "restaurante") is None


def test_nao_cancela_em_preparo():
    assert validar_transicao(EM_PREPARACAO, CANCELADO, "delivery", "restaurante") is not None


def test_pedido_finalizado_nao_muda():
    assert validar_transicao(ENTREGUE, CANCELADO, "delivery", "admin") is not None
    assert validar_transicao(CANCELADO, ACEITO, "delivery", "admin") is not None


# ------------------------------------------------- confirmar entrega

def test_entregador_confirma_delivery_em_transito():
    assert validar_confirmacao_entrega(EM_TRANSITO, "delivery", "entregador") is None


def test_nao_confirma_antes_de_sair():
    assert validar_confirmacao_entrega(PRONTO_PARA_ENTREGA, "delivery", "entregador") is not None


def test_restaurante_confirma_retirada():
    assert validar_confirmacao_entrega(PRONTO_PARA_RETIRADA, "retirada", "restaurante") is None


def test_entregador_nao_confirma_retirada():
    assert validar_confirmacao_entrega(PRONTO_PARA_RETIRADA, "retirada", "entregador") is not None


# ----------------------------------------------------- codigo entrega

def test_codigo_tem_4_digitos():
    for _ in range(50):
        codigo = gerar_codigo_entrega()
        assert len(codigo) == TAMANHO_CODIGO
        assert codigo.isdigit()


def test_codigo_confere():
    assert codigo_confere("0427", "0427")
    assert codigo_confere("0427", " 0427 ")


def test_codigo_errado_ou_sem_codigo():
    assert not codigo_confere("0427", "4270")
    assert not codigo_confere(None, "0427")
    assert not codigo_confere("", "")
