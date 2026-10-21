"""Testes do fechamento da cesta - Sprint 3.

Cobre a taxa de entrega pela distancia (app/core/frete.py) e a
revalidacao dos itens antes de criar o pedido.

Executar:  python -m pytest testes/teste_fechamento_cesta.py -v
"""

from decimal import Decimal
from types import SimpleNamespace

from app.controllers.sacola_controller import (
    QUANTIDADE_MAXIMA_POR_PRODUTO,
    validar_itens_para_fechamento,
)
from app.core.frete import (
    calcular_taxa_entrega,
    distancia_linha_reta_km,
    entrega_no_raio,
    medir_distancia,
)

# Coordenadas reais do seed (sql/04_seed_cardapio.sql) e de um endereco de teste
BURGER_PAULISTA = SimpleNamespace(latitude=Decimal("-23.561414"), longitude=Decimal("-46.655881"))
SUSHI_AURORA = SimpleNamespace(latitude=Decimal("-23.539000"), longitude=Decimal("-46.640000"))
CLIENTE_SE = SimpleNamespace(latitude=Decimal("-23.550520"), longitude=Decimal("-46.633308"))


# --------------------------------------------------------------- distancia

def test_linha_reta_burger_paulista():
    assert distancia_linha_reta_km(
        BURGER_PAULISTA.latitude, BURGER_PAULISTA.longitude,
        CLIENTE_SE.latitude, CLIENTE_SE.longitude,
    ) == Decimal("2.6")


def test_linha_reta_sushi_aurora():
    km = distancia_linha_reta_km(
        SUSHI_AURORA.latitude, SUSHI_AURORA.longitude,
        CLIENTE_SE.latitude, CLIENTE_SE.longitude,
    )
    assert abs(km - Decimal("1.45")) < Decimal("0.01")


def test_mesmo_ponto_distancia_zero():
    assert distancia_linha_reta_km(1, 1, 1, 1) == Decimal("0")


def test_estimativa_sem_chave_usa_fator():
    distancia = medir_distancia(BURGER_PAULISTA, CLIENTE_SE)
    assert distancia.metodo == "estimada"
    assert distancia.km == Decimal("4.160")  # 2,60 km x 1,6


# ------------------------------------------------------- taxa de entrega

def test_taxa_dentro_dos_km_inclusos_e_a_base():
    assert calcular_taxa_entrega(Decimal("1.5"), Decimal("1.50")) == Decimal("4.00")


def test_taxa_com_km_adicional():
    # 4,00 + 1,50 x (4,43 - 2) = 7,645 -> sobe para 7,70
    assert calcular_taxa_entrega(Decimal("4.43"), Decimal("1.50")) == Decimal("7.70")


def test_taxa_usa_valor_km_do_restaurante():
    # 4,00 + 4,50 x (4,16 - 2) = 13,72 -> 13,80
    assert calcular_taxa_entrega(Decimal("4.16"), Decimal("4.50")) == Decimal("13.80")


def test_taxa_nunca_abaixo_da_minima():
    assert calcular_taxa_entrega(Decimal("0"), Decimal("0")) == Decimal("4.00")


def test_taxa_arredonda_para_cima_em_dez_centavos():
    # 4,00 + 1,00 x 0,01 = 4,01 -> 4,10
    assert calcular_taxa_entrega(Decimal("2.01"), Decimal("1.00")) == Decimal("4.10")


def test_raio_maximo():
    assert entrega_no_raio(Decimal("8.0")) is True
    assert entrega_no_raio(Decimal("8.01")) is False


# ------------------------------------------- revalidacao no fechamento

def _item(quantidade=1):
    return SimpleNamespace(quantidade=quantidade)


def _produto(nome="X-Salada", disponivel=True, restaurante_id=1):
    return SimpleNamespace(nome=nome, disponivel=disponivel, restaurante_id=restaurante_id)


def test_itens_validos_podem_fechar():
    assert validar_itens_para_fechamento([(_item(2), _produto()), (_item(1), _produto("Batata"))]) is None


def test_produto_indisponivel_bloqueia():
    motivo = validar_itens_para_fechamento([(_item(), _produto("Milk-shake", disponivel=False))])
    assert "Milk-shake" in motivo and "indisponivel" in motivo


def test_produto_removido_do_catalogo_bloqueia():
    assert "nao existe mais" in validar_itens_para_fechamento([(_item(), None)])


def test_quantidade_acima_do_limite_bloqueia():
    motivo = validar_itens_para_fechamento([(_item(QUANTIDADE_MAXIMA_POR_PRODUTO + 1), _produto())])
    assert "limite" in motivo


def test_restaurantes_diferentes_bloqueia():
    motivo = validar_itens_para_fechamento(
        [(_item(), _produto(restaurante_id=1)), (_item(), _produto(restaurante_id=2))]
    )
    assert "restaurantes diferentes" in motivo
