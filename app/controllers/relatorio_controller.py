"""Controller dos relatorios de vendas (Sprint 4 - Relatorios).

Tres relatorios, todos com filtro opcional de data (data_inicio e data_fim,
inclusive):
    GET /relatorios/receita-por-restaurante   receita bruta e participacao %
    GET /relatorios/pedidos-por-restaurante   quantidade, faturamento e ticket medio
    GET /relatorios/pagamentos-por-tipo       quantidade e valor por forma de pagamento

Quem ve: administrador (todos os restaurantes) e usuario restaurante (so os
restaurantes dele). Cliente e entregador recebem 403.

As regras de calculo ficam em app/core/relatorios.py; a leitura do banco em
Pedido.listar_vendas (Model); o formato da resposta em app/schemas/relatorio.py.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core import relatorios
from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.schemas.relatorio import (
    PeriodoOut,
    RelatorioPagamentosOut,
    RelatorioPedidosOut,
    RelatorioReceitaOut,
)

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

REGRA = (
    "Considera os pedidos aceitos pelo restaurante (de 'aceito' até 'entregue'). "
    "Pedidos aguardando aceite e cancelados ficam de fora. "
    "Valores incluem produtos e taxa de entrega."
)


def carregar_vendas(
    db: Session,
    usuario: Usuario,
    data_inicio: date | None,
    data_fim: date | None,
) -> list[relatorios.Venda]:
    """Confere quem pede e o periodo, e le as vendas do banco."""

    if usuario.tipo not in ("admin", "restaurante"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente o administrador e o restaurante podem ver os relatórios.",
        )

    problema = relatorios.periodo_invalido(data_inicio, data_fim)
    if problema is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problema)

    inicio, fim = relatorios.intervalo(data_inicio, data_fim)
    dono = usuario.id if usuario.tipo == "restaurante" else None  # restaurante ve so os dele

    return [
        relatorios.Venda(
            restaurante_id=restaurante_id,
            restaurante_nome=nome,
            forma_pagamento=forma,
            valor_total=Decimal(valor),
        )
        for restaurante_id, nome, forma, valor in Pedido.listar_vendas(
            db, inicio=inicio, fim=fim, dono_restaurante_id=dono
        )
    ]


DataInicio = Query(default=None, description="Primeiro dia do período (AAAA-MM-DD). Vazio = desde o início.")
DataFim = Query(default=None, description="Último dia do período, inclusive (AAAA-MM-DD). Vazio = até hoje.")


@router.get(
    "/receita-por-restaurante",
    response_model=RelatorioReceitaOut,
    summary="Receita bruta e participação percentual por restaurante",
)
def receita_por_restaurante(
    data_inicio: date | None = DataInicio,
    data_fim: date | None = DataFim,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> RelatorioReceitaOut:
    """Quanto cada restaurante vendeu no período e quanto isso representa do total.

    Ordenado da maior para a menor receita. As participações somam 100%.
    """

    vendas = carregar_vendas(db, usuario_logado, data_inicio, data_fim)
    return RelatorioReceitaOut(
        periodo=PeriodoOut(data_inicio=data_inicio, data_fim=data_fim),
        regra=REGRA,
        **relatorios.receita_por_restaurante(vendas),
    )


@router.get(
    "/pedidos-por-restaurante",
    response_model=RelatorioPedidosOut,
    summary="Quantidade de pedidos, faturamento e ticket médio por restaurante",
)
def pedidos_por_restaurante(
    data_inicio: date | None = DataInicio,
    data_fim: date | None = DataFim,
    ordenar_por: Literal["quantidade_pedidos", "faturamento", "ticket_medio", "restaurante_nome"] = Query(
        default="faturamento", description="Coluna usada para ordenar a tabela."
    ),
    ordem: Literal["asc", "desc"] = Query(default="desc", description="asc = crescente, desc = decrescente."),
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> RelatorioPedidosOut:
    """Tabela por restaurante, já ordenada pela coluna escolhida, com os totais gerais."""

    vendas = carregar_vendas(db, usuario_logado, data_inicio, data_fim)
    return RelatorioPedidosOut(
        periodo=PeriodoOut(data_inicio=data_inicio, data_fim=data_fim),
        regra=REGRA,
        **relatorios.pedidos_por_restaurante(vendas, ordenar_por, ordem),
    )


@router.get(
    "/pagamentos-por-tipo",
    response_model=RelatorioPagamentosOut,
    summary="Pedidos por forma de pagamento, em quantidade e em valor",
)
def pagamentos_por_tipo(
    data_inicio: date | None = DataInicio,
    data_fim: date | None = DataFim,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> RelatorioPagamentosOut:
    """Cartão, PIX e dinheiro: quantos pedidos, quanto em reais e o percentual de cada um.

    Os três métodos sempre aparecem (com zero quando não houve venda), prontos
    para o gráfico de pizza.
    """

    vendas = carregar_vendas(db, usuario_logado, data_inicio, data_fim)
    return RelatorioPagamentosOut(
        periodo=PeriodoOut(data_inicio=data_inicio, data_fim=data_fim),
        regra=REGRA,
        **relatorios.pagamentos_por_tipo(vendas),
    )
