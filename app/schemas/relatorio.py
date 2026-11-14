"""Schemas (View) dos relatorios de vendas - Sprint 4."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PeriodoOut(BaseModel):
    """Filtro aplicado (None = sem limite daquele lado)."""

    data_inicio: date | None
    data_fim: date | None


class ReceitaRestauranteOut(BaseModel):
    restaurante_id: int
    restaurante_nome: str
    receita_bruta: Decimal
    participacao_percentual: Decimal


class RelatorioReceitaOut(BaseModel):
    """Receita bruta por restaurante e participacao no total."""

    periodo: PeriodoOut
    regra: str
    total_geral: Decimal
    restaurantes: list[ReceitaRestauranteOut]


class PedidosRestauranteOut(BaseModel):
    restaurante_id: int
    restaurante_nome: str
    quantidade_pedidos: int
    faturamento: Decimal
    ticket_medio: Decimal


class RelatorioPedidosOut(BaseModel):
    """Quantidade de pedidos, faturamento e ticket medio por restaurante."""

    periodo: PeriodoOut
    regra: str
    total_pedidos: int
    total_faturamento: Decimal
    ticket_medio_geral: Decimal
    restaurantes: list[PedidosRestauranteOut]


class PagamentoTipoOut(BaseModel):
    forma_pagamento: str
    rotulo: str
    quantidade: int
    valor: Decimal
    percentual_quantidade: Decimal
    percentual_valor: Decimal


class RelatorioPagamentosOut(BaseModel):
    """Pedidos por forma de pagamento, em quantidade e em valor (grafico de pizza)."""

    periodo: PeriodoOut
    regra: str
    total_quantidade: int
    total_valor: Decimal
    metodos: list[PagamentoTipoOut]
