"""Dados da nota fiscal de um pedido, sem depender do provedor (simulado ou real).

`montar_dados` le pedido, restaurante, cliente, itens e pagamento do banco e
devolve um `DadosNota`. O PDF simulado e o provedor real usam a mesma
estrutura, entao os valores da nota sao sempre os do pedido.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.pagamento_regras import numero_nota_fiscal

METODOS = {"cartao": "Cartão de crédito", "pix": "PIX", "dinheiro": "Dinheiro na entrega"}
ENTREGAS = {"delivery": "Entrega no endereço", "retirada": "Retirada no balcão"}


@dataclass
class ItemNota:
    nome: str
    quantidade: int
    preco_unitario: Decimal
    produto_id: int | None = None

    @property
    def subtotal(self) -> Decimal:
        return (self.preco_unitario * self.quantidade).quantize(Decimal("0.01"))


@dataclass
class DadosNota:
    """Tudo o que aparece na nota (sem depender do banco, para testar)."""

    numero: str
    emitida_em: datetime
    pedido_id: int
    restaurante_nome: str
    restaurante_cnpj: str
    restaurante_endereco: str | None
    cliente_nome: str
    cliente_email: str | None
    forma_pagamento: str
    tipo_entrega: str
    taxa_entrega: Decimal
    transacao: str | None = None
    itens: list[ItemNota] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.itens), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.taxa_entrega


def reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def montar_dados(db: Session, pedido) -> DadosNota:
    """Le pedido, restaurante, cliente, itens e pagamento para a nota."""

    from app.models.item_pedido import ItemPedido
    from app.models.pagamento import Pagamento
    from app.models.produto import Produto
    from app.models.restaurante import Restaurante
    from app.models.usuario import Usuario

    restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
    cliente = Usuario.buscar_por_id(db, pedido.cliente_id)
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    itens = []
    for item in ItemPedido.listar_por_pedido(db, pedido.id):
        produto = Produto.buscar_por_id(db, item.produto_id)
        itens.append(
            ItemNota(
                nome=produto.nome if produto else f"Produto #{item.produto_id}",
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario,
                produto_id=item.produto_id,
            )
        )

    emitida = (pagamento.atualizado_em or pagamento.criado_em) if pagamento else pedido.criado_em

    return DadosNota(
        numero=pedido.cupom_fiscal or numero_nota_fiscal(pedido.id, pedido.criado_em.year),
        emitida_em=emitida,
        pedido_id=pedido.id,
        restaurante_nome=restaurante.nome_fantasia if restaurante else "Restaurante",
        restaurante_cnpj=restaurante.cnpj if restaurante else "-",
        restaurante_endereco=restaurante.local.endereco if restaurante and restaurante.local else None,
        cliente_nome=cliente.nome if cliente else "Consumidor",
        cliente_email=cliente.email if cliente else None,
        forma_pagamento=pedido.forma_pagamento,
        tipo_entrega=pedido.tipo_entrega,
        taxa_entrega=pedido.taxa_entrega,
        transacao=pagamento.transacao_externa_id if pagamento else None,
        itens=itens,
    )
