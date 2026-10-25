"""Testes da RN04 - cancelamento do pedido pelo cliente (Sprint 4).

Regras puras (sem banco): o cliente so cancela enquanto o pedido aguarda o
aceite do restaurante, e o cliente e o restaurante recebem o aviso.

Executar:  python -m pytest testes/teste_cancelamento_cliente.py -v
"""

import pytest

from app.core import status_pedido as sp
from app.core.notificacoes_pedido import avisos_cancelamento_cliente


def test_cliente_cancela_aguardando_aceite():
    assert sp.validar_cancelamento_cliente(sp.AGUARDANDO_ACEITE) is None


@pytest.mark.parametrize(
    "status",
    [sp.ACEITO, sp.EM_PREPARACAO, sp.PRONTO_PARA_ENTREGA, sp.PRONTO_PARA_RETIRADA, sp.EM_TRANSITO, sp.ENTREGUE],
)
def test_cliente_nao_cancela_depois_do_aceite(status):
    erro = sp.validar_cancelamento_cliente(status)
    assert erro is not None
    assert sp.rotulo(status) in erro


def test_pedido_ja_cancelado():
    assert sp.validar_cancelamento_cliente(sp.CANCELADO) == "O pedido ja esta cancelado."


def test_restaurante_continua_podendo_cancelar_depois_do_aceite():
    # RN04 nao muda a regra do restaurante (aguardando_aceite ou aceito).
    assert sp.validar_transicao(sp.ACEITO, sp.CANCELADO, "delivery", "restaurante") is None


def test_aviso_de_cancelamento_vai_para_cliente_e_restaurante():
    avisos = avisos_cancelamento_cliente(12)
    assert [a.para for a in avisos] == ["cliente", "restaurante"]
    assert all("#12" in a.titulo for a in avisos)
