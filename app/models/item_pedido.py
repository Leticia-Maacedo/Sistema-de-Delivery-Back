"""Model de Item do Pedido do EntregaFood.

Mapeia a tabela `item_pedido`, que ja existe no schema do banco.
Guarda uma copia dos itens da cesta no momento do fechamento, com o
preco unitario congelado: se o restaurante mudar o preco depois, o
pedido continua com o valor que foi cobrado.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class ItemPedido(Base):
    """Representa um produto dentro de um pedido."""

    __tablename__ = "item_pedido"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id"),
        nullable=False,
    )

    produto_id: Mapped[int] = mapped_column(
        ForeignKey("produto.id"),
        nullable=False,
    )

    quantidade: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    preco_unitario: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    @staticmethod
    def listar_por_pedido(
        db: Session,
        pedido_id: int,
    ) -> list["ItemPedido"]:
        """Lista os itens de um pedido."""

        consulta = (
            select(ItemPedido)
            .where(ItemPedido.pedido_id == pedido_id)
            .order_by(ItemPedido.id)
        )

        return list(db.execute(consulta).scalars())
