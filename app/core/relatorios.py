"""Calculos dos relatorios de vendas (Sprint 4 - Relatorios).

Fica separado do controller para poder ser testado sem banco: recebe as
vendas ja lidas do banco e devolve os numeros prontos.

Regras (iguais nos tres relatorios):
    - Venda = pedido que o restaurante ACEITOU: qualquer status a partir de
      "aceito" (aceito, em preparacao, pronto, em transito, entregue).
      Ficam de fora os pedidos aguardando aceite (ainda podem nao ter sido
      pagos) e os cancelados.
    - Receita bruta / faturamento = soma do valor total dos pedidos
      (produtos + taxa de entrega), sem descontar nada.
    - Ticket medio = faturamento / quantidade de pedidos.
    - Percentuais com 2 casas; valores em reais com 2 casas.
    - Sem vendas no periodo: listas vazias e totais zerados (nunca erro).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.status_pedido import AGUARDANDO_ACEITE, CANCELADO

STATUS_FORA_DO_RELATORIO = {AGUARDANDO_ACEITE, CANCELADO}

METODOS = {
    "cartao": "Cartão de crédito",
    "pix": "PIX",
    "dinheiro": "Dinheiro na entrega",
}

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


@dataclass
class Venda:
    """Um pedido aceito, so com o que os relatorios usam."""

    restaurante_id: int
    restaurante_nome: str
    forma_pagamento: str
    valor_total: Decimal


def arredondar(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def percentual(parte: Decimal, total: Decimal) -> Decimal:
    if not total:
        return ZERO
    return arredondar(parte * 100 / total)


def intervalo(data_inicio: date | None, data_fim: date | None) -> tuple[datetime | None, datetime | None]:
    """Datas do filtro -> [inicio 00:00, dia seguinte ao fim 00:00). Fim inclui o dia todo."""

    inicio = datetime.combine(data_inicio, time.min) if data_inicio else None
    fim = datetime.combine(data_fim + timedelta(days=1), time.min) if data_fim else None
    return inicio, fim


def periodo_invalido(data_inicio: date | None, data_fim: date | None) -> str | None:
    if data_inicio and data_fim and data_inicio > data_fim:
        return "A data inicial não pode ser depois da data final."
    return None


# ------------------------------------------------------------------ 1. receita por restaurante


def receita_por_restaurante(vendas: list[Venda]) -> dict:
    """Receita bruta de cada restaurante e quanto ela representa do total."""

    receita = defaultdict(lambda: ZERO)
    nomes = {}
    for venda in vendas:
        receita[venda.restaurante_id] += venda.valor_total
        nomes[venda.restaurante_id] = venda.restaurante_nome

    total = sum(receita.values(), ZERO)
    linhas = [
        {
            "restaurante_id": rid,
            "restaurante_nome": nomes[rid],
            "receita_bruta": arredondar(valor),
            "participacao_percentual": percentual(valor, total),
        }
        for rid, valor in receita.items()
    ]
    linhas.sort(key=lambda linha: (-linha["receita_bruta"], linha["restaurante_nome"]))

    return {"total_geral": arredondar(total), "restaurantes": linhas}


# ------------------------------------------------------------------ 2. pedidos, faturamento e ticket medio


ORDENACOES = {"quantidade_pedidos", "faturamento", "ticket_medio", "restaurante_nome"}


def pedidos_por_restaurante(vendas: list[Venda], ordenar_por: str = "faturamento", ordem: str = "desc") -> dict:
    """Quantidade de pedidos, faturamento e ticket medio por restaurante."""

    quantidade = defaultdict(int)
    faturamento = defaultdict(lambda: ZERO)
    nomes = {}
    for venda in vendas:
        quantidade[venda.restaurante_id] += 1
        faturamento[venda.restaurante_id] += venda.valor_total
        nomes[venda.restaurante_id] = venda.restaurante_nome

    linhas = [
        {
            "restaurante_id": rid,
            "restaurante_nome": nomes[rid],
            "quantidade_pedidos": quantidade[rid],
            "faturamento": arredondar(faturamento[rid]),
            "ticket_medio": arredondar(faturamento[rid] / quantidade[rid]),
        }
        for rid in quantidade
    ]
    linhas.sort(key=lambda linha: linha[ordenar_por], reverse=(ordem == "desc"))

    total_pedidos = sum(quantidade.values())
    total_faturamento = sum(faturamento.values(), ZERO)
    return {
        "total_pedidos": total_pedidos,
        "total_faturamento": arredondar(total_faturamento),
        "ticket_medio_geral": arredondar(total_faturamento / total_pedidos) if total_pedidos else ZERO,
        "restaurantes": linhas,
    }


# ------------------------------------------------------------------ 3. por tipo de pagamento


def pagamentos_por_tipo(vendas: list[Venda]) -> dict:
    """Quantidade e valor por forma de pagamento (os tres metodos sempre aparecem)."""

    quantidade = {metodo: 0 for metodo in METODOS}
    valor = {metodo: ZERO for metodo in METODOS}
    for venda in vendas:
        quantidade[venda.forma_pagamento] = quantidade.get(venda.forma_pagamento, 0) + 1
        valor[venda.forma_pagamento] = valor.get(venda.forma_pagamento, ZERO) + venda.valor_total

    total_quantidade = sum(quantidade.values())
    total_valor = sum(valor.values(), ZERO)
    metodos = [
        {
            "forma_pagamento": metodo,
            "rotulo": METODOS.get(metodo, metodo),
            "quantidade": quantidade[metodo],
            "valor": arredondar(valor[metodo]),
            "percentual_quantidade": percentual(Decimal(quantidade[metodo]), Decimal(total_quantidade)),
            "percentual_valor": percentual(valor[metodo], total_valor),
        }
        for metodo in quantidade
    ]
    metodos.sort(key=lambda linha: (-linha["valor"], linha["forma_pagamento"]))

    return {
        "total_quantidade": total_quantidade,
        "total_valor": arredondar(total_valor),
        "metodos": metodos,
    }
