"""Regra das sugestoes de produtos (Sprint 4 - Sugestao de Produtos).

Fica separada do controller para poder ser testada sem banco: recebe os
produtos que podem ser sugeridos e as contagens ja lidas do banco, e
devolve a lista pronta, na ordem certa e com o motivo de cada sugestao.

Regra (popularidade, com prioridade para o que combina com a cesta):
    1. So entra produto do restaurante, disponivel e nao esgotado, e que
       ainda nao esta na cesta do cliente.
    2. Primeiro os que costumam ser pedidos JUNTO com os itens da cesta
       (quantos pedidos tiveram os dois).
    3. Depois os mais pedidos do restaurante (unidades vendidas).
    4. Empate: ordem alfabetica. Produto sem nenhuma venda ainda aparece
       no fim, para completar a lista.
Conta so pedidos que o restaurante aceitou (de "aceito" ate "entregue"),
igual aos relatorios: aguardando aceite e cancelados ficam de fora.
"""

import unicodedata
from dataclasses import dataclass

MOTIVO_JUNTOS = "Costuma ser pedido junto com os itens da sua cesta"
MOTIVO_POPULAR = "Um dos mais pedidos deste restaurante"
MOTIVO_CARDAPIO = "Do cardápio deste restaurante"

LIMITE_PADRAO = 5
LIMITE_MAXIMO = 20

REGRA = (
    "Produtos disponíveis do restaurante que ainda não estão na cesta. Primeiro os que "
    "costumam ser pedidos junto com os itens da cesta, depois os mais pedidos do "
    "restaurante. Conta só pedidos aceitos; esgotados e indisponíveis ficam de fora."
)


def chave_nome(nome: str) -> str:
    """Nome sem acento e em minusculas, para 'Água' ficar junto do 'A'."""

    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower()


@dataclass
class Sugestao:
    produto: object  # app.models.produto.Produto
    motivo: str
    vezes_pedido: int
    pedidos_juntos: int


def montar_sugestoes(
    candidatos: list,
    vendidos: dict[int, int],
    juntos: dict[int, int],
    na_cesta: set[int],
    limite: int = LIMITE_PADRAO,
) -> list[Sugestao]:
    """Ordena os candidatos e corta no limite.

    `candidatos`: produtos disponiveis do restaurante.
    `vendidos`:   produto_id -> unidades vendidas em pedidos aceitos.
    `juntos`:     produto_id -> pedidos aceitos em que ele saiu junto com
                  algum item da cesta.
    """

    lista = []
    for produto in candidatos:
        if produto.id in na_cesta:
            continue
        qtd_juntos = juntos.get(produto.id, 0)
        qtd_vendida = vendidos.get(produto.id, 0)
        if qtd_juntos:
            motivo = MOTIVO_JUNTOS
        elif qtd_vendida:
            motivo = MOTIVO_POPULAR
        else:
            motivo = MOTIVO_CARDAPIO
        lista.append(Sugestao(produto, motivo, qtd_vendida, qtd_juntos))

    lista.sort(key=lambda s: (-s.pedidos_juntos, -s.vezes_pedido, chave_nome(s.produto.nome)))
    return lista[:limite]
