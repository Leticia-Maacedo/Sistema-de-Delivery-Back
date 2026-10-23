"""Testes das notificacoes push e do rastreio - Sprint 3 (Backlog 21, 23 e 25).

Cobre quem recebe cada aviso e o link do Google Maps, sem banco.

Executar:  python -m pytest testes/teste_notificacoes_rastreio.py -v
"""

from urllib.parse import parse_qs, urlparse

from app.controllers.entrega_controller import link_google_maps
from app.core import status_pedido as sp
from app.core.notificacoes_pedido import avisos_mudanca_status, avisos_pedido_criado


def test_pedido_criado_avisa_cliente_e_restaurante():
    avisos = avisos_pedido_criado(7, "delivery")
    assert [a.para for a in avisos] == ["cliente", "restaurante"]
    assert "#7" in avisos[0].titulo and "#7" in avisos[1].titulo


def test_pedido_criado_retirada_informa_o_tipo():
    assert "retirada" in avisos_pedido_criado(3, "retirada")[1].corpo


def test_cada_mudanca_avisa_o_cliente():
    for status in (sp.ACEITO, sp.EM_PREPARACAO, sp.PRONTO_PARA_ENTREGA, sp.EM_TRANSITO, sp.ENTREGUE, sp.CANCELADO):
        avisos = avisos_mudanca_status(1, status, "delivery")
        assert avisos[0].para == "cliente"
        assert sp.rotulo(status) in avisos[0].titulo


def test_pronto_para_entrega_avisa_os_entregadores():
    assert [a.para for a in avisos_mudanca_status(1, sp.PRONTO_PARA_ENTREGA, "delivery")] == ["cliente", "entregadores"]


def test_retirada_nao_chama_entregador():
    assert [a.para for a in avisos_mudanca_status(1, sp.PRONTO_PARA_RETIRADA, "retirada")] == ["cliente"]


def test_saiu_para_entrega_lembra_o_codigo():
    assert "código" in avisos_mudanca_status(1, sp.EM_TRANSITO, "delivery")[0].corpo


def test_link_google_maps_com_origem_e_destino():
    q = parse_qs(urlparse(link_google_maps((-23.56, -46.65), (-23.55, -46.63))).query)
    assert q["origin"] == ["-23.56,-46.65"] and q["destination"] == ["-23.55,-46.63"] and q["api"] == ["1"]


def test_link_google_maps_sem_origem():
    q = parse_qs(urlparse(link_google_maps(None, (-23.55, -46.63))).query)
    assert "origin" not in q and q["destination"] == ["-23.55,-46.63"]


def test_link_google_maps_sem_destino():
    assert link_google_maps((-23.5, -46.6), None) is None
