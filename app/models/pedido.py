"""Model de Pedido do EntregaFood.

Mapeia a tabela `pedido`, que ja existe no schema do banco.
Nesta etapa, o model fornece as operacoes necessarias para
integrar o pedido ao fluxo de pagamento.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.models.item_pedido import ItemPedido


class Pedido(Base):
    """Representa um pedido realizado por um cliente."""

    __tablename__ = "pedido"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=False,
    )

    restaurante_id: Mapped[int] = mapped_column(
        ForeignKey("restaurante.id"),
        nullable=False,
    )

    entregador_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="aguardando_aceite",
    )

    tipo_entrega: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    forma_pagamento: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    valor_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    taxa_entrega: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
    )

    cupom_fiscal: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    @staticmethod
    def buscar_por_id(
        db: Session,
        pedido_id: int,
    ) -> "Pedido | None":
        """Busca um pedido pelo id."""

        return db.get(Pedido, pedido_id)

    @classmethod
    def criar_a_partir_da_cesta(
        cls,
        db: Session,
        *,
        cliente_id: int,
        restaurante_id: int,
        tipo_entrega: str,
        forma_pagamento: str,
        subtotal: Decimal,
        taxa_entrega: Decimal,
        itens: list[tuple[int, int, Decimal]],
        sacola,
    ) -> "Pedido":
        """Cria o pedido, copia os itens com o preco do momento e esvazia a cesta.

        `itens` e uma lista de (produto_id, quantidade, preco_unitario).
        Tudo e gravado num unico commit: se algo falhar, nada fica pela metade.
        """

        pedido = cls(
            cliente_id=cliente_id,
            restaurante_id=restaurante_id,
            entregador_id=None,
            status="aguardando_aceite",
            tipo_entrega=tipo_entrega,
            forma_pagamento=forma_pagamento,
            valor_total=subtotal + taxa_entrega,
            taxa_entrega=taxa_entrega,
            cupom_fiscal=None,
            criado_em=datetime.now(),
            atualizado_em=None,
        )
        db.add(pedido)
        db.flush()  # gera o id do pedido para os itens

        for produto_id, quantidade, preco_unitario in itens:
            db.add(
                ItemPedido(
                    pedido_id=pedido.id,
                    produto_id=produto_id,
                    quantidade=quantidade,
                    preco_unitario=preco_unitario,
                )
            )

        sacola.esvaziar(db)

        db.commit()
        db.refresh(pedido)

        return pedido

    def definir_forma_pagamento(
        self,
        db: Session,
        forma_pagamento: str,
    ) -> "Pedido":
        """Define a forma de pagamento escolhida para o pedido."""

        self.forma_pagamento = forma_pagamento
        self.atualizado_em = datetime.now()

        db.commit()
        db.refresh(self)

        return self