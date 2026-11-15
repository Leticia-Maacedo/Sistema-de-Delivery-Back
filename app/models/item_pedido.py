"""Model de Item do Pedido do EntregaFood.

Mapeia a tabela `item_pedido`, que ja existe no schema do banco.
Guarda uma copia dos itens da cesta no momento do fechamento, com o
preco unitario congelado: se o restaurante mudar o preco depois, o
pedido continua com o valor que foi cobrado.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, distinct, func, select
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

    # ------------------------------------------------------------------
    # Sugestao de produtos (Sprint 4)
    # ------------------------------------------------------------------

    @staticmethod
    def _pedidos_aceitos(restaurante_id: int):
        """Filtro comum: pedidos do restaurante que ele aceitou."""

        from app.core.status_pedido import AGUARDANDO_ACEITE, CANCELADO
        from app.models.pedido import Pedido

        return (
            Pedido.restaurante_id == restaurante_id,
            Pedido.status.not_in([AGUARDANDO_ACEITE, CANCELADO]),
        )

    @staticmethod
    def unidades_vendidas(db: Session, restaurante_id: int) -> dict[int, int]:
        """produto_id -> unidades vendidas em pedidos aceitos do restaurante."""

        from app.models.pedido import Pedido

        consulta = (
            select(ItemPedido.produto_id, func.sum(ItemPedido.quantidade))
            .join(Pedido, Pedido.id == ItemPedido.pedido_id)
            .where(*ItemPedido._pedidos_aceitos(restaurante_id))
            .group_by(ItemPedido.produto_id)
        )
        return {produto_id: int(total) for produto_id, total in db.execute(consulta)}

    @staticmethod
    def pedidos_junto_com(db: Session, restaurante_id: int, produto_ids: set[int]) -> dict[int, int]:
        """produto_id -> em quantos pedidos aceitos ele saiu junto com algum
        dos `produto_ids` (os itens da cesta). Os proprios itens da cesta
        nao entram no resultado."""

        if not produto_ids:
            return {}

        from app.models.pedido import Pedido

        pedidos_com_a_cesta = select(ItemPedido.pedido_id).where(ItemPedido.produto_id.in_(produto_ids))
        consulta = (
            select(ItemPedido.produto_id, func.count(distinct(ItemPedido.pedido_id)))
            .join(Pedido, Pedido.id == ItemPedido.pedido_id)
            .where(
                *ItemPedido._pedidos_aceitos(restaurante_id),
                ItemPedido.pedido_id.in_(pedidos_com_a_cesta),
                ItemPedido.produto_id.not_in(produto_ids),
            )
            .group_by(ItemPedido.produto_id)
        )
        return {produto_id: int(total) for produto_id, total in db.execute(consulta)}
