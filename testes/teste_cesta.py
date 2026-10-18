
"""Testes das regras da cesta - Sprint 3."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.controllers.sacola_controller import (
    QUANTIDADE_MAXIMA_POR_PRODUTO,
    calcular_subtotal,
    calcular_total,
    validar_disponibilidade,
    validar_quantidade,
    validar_restaurante_cesta,
)


def test_subtotal_um_produto():
    assert calcular_subtotal(Decimal("25.50"), 2) == Decimal("51.00")


def test_subtotal_com_quantidade_um():
    assert calcular_subtotal(Decimal("19.90"), 1) == Decimal("19.90")


def test_total_cesta():
    subtotais = [
        Decimal("51.00"),
        Decimal("19.90"),
        Decimal("10.00"),
    ]
    assert calcular_total(subtotais) == Decimal("80.90")


def test_total_cesta_vazia():
    assert calcular_total([]) == Decimal("0.00")


def test_quantidade_valida():
    validar_quantidade(1)
    validar_quantidade(QUANTIDADE_MAXIMA_POR_PRODUTO)


def test_quantidade_acima_do_limite():
    with pytest.raises(HTTPException) as erro:
        validar_quantidade(100)

    assert erro.value.status_code == 400


def test_quantidade_zero():
    with pytest.raises(HTTPException) as erro:
        validar_quantidade(0)

    assert erro.value.status_code == 400


def test_produto_disponivel():
    produto = SimpleNamespace(disponivel=True)
    validar_disponibilidade(produto)


def test_produto_indisponivel():
    produto = SimpleNamespace(disponivel=False)

    with pytest.raises(HTTPException) as erro:
        validar_disponibilidade(produto)

    assert erro.value.status_code == 400


def test_produtos_do_mesmo_restaurante():
    sacola = SimpleNamespace(id=1)
    novo_produto = SimpleNamespace(restaurante_id=10)
    item = SimpleNamespace(produto_id=5)
    produto_existente = SimpleNamespace(restaurante_id=10)

    with (
        patch(
            "app.controllers.sacola_controller."
            "ItemSacola.listar_por_sacola",
            return_value=[item],
        ),
        patch(
            "app.controllers.sacola_controller."
            "Produto.buscar_por_id",
            return_value=produto_existente,
        ),
    ):
        validar_restaurante_cesta(None, sacola, novo_produto)


def test_produtos_de_restaurantes_diferentes():
    sacola = SimpleNamespace(id=1)
    novo_produto = SimpleNamespace(restaurante_id=20)
    item = SimpleNamespace(produto_id=5)
    produto_existente = SimpleNamespace(restaurante_id=10)

    with (
        patch(
            "app.controllers.sacola_controller."
            "ItemSacola.listar_por_sacola",
            return_value=[item],
        ),
        patch(
            "app.controllers.sacola_controller."
            "Produto.buscar_por_id",
            return_value=produto_existente,
        ),
    ):
        with pytest.raises(HTTPException) as erro:
            validar_restaurante_cesta(None, sacola, novo_produto)

    assert erro.value.status_code == 400
