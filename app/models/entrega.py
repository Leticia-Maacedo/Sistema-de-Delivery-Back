"""Model de Entrega do EntregaFood.

Mapeia a tabela `entrega` (criada no 01_create_tables.sql e completada
no 05_sprint3_acompanhamento.sql). Cada pedido tem uma entrega, criada
junto com o pedido, que guarda o codigo de validacao que o cliente
informa ao receber.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.core.status_pedido import gerar_codigo_entrega


class Entrega(Base):
    """Representa a entrega (ou retirada) de um pedido."""

    __tablename__ = "entrega"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id"),
        nullable=False,
        unique=True,
    )

    entregador_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=True,
    )

    # aguardando -> em_transito -> entregue (ou cancelada)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="aguardando",
    )

    latitude_atual: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude_atual: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    recusada_por: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    codigo_validacao: Mapped[str | None] = mapped_column(
        String(6),
        nullable=True,
    )

    entregue_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    @staticmethod
    def buscar_por_pedido(
        db: Session,
        pedido_id: int,
    ) -> "Entrega | None":
        """Busca a entrega de um pedido."""

        consulta = select(Entrega).where(Entrega.pedido_id == pedido_id)

        return db.execute(consulta).scalars().first()

    @classmethod
    def nova(cls, pedido_id: int) -> "Entrega":
        """Monta a entrega de um pedido recem-criado, ja com o codigo.

        Nao faz commit: quem chama grava junto com o pedido.
        """

        return cls(
            pedido_id=pedido_id,
            entregador_id=None,
            status="aguardando",
            codigo_validacao=gerar_codigo_entrega(),
            atualizado_em=datetime.now(),
        )

    @classmethod
    def obter_ou_criar(
        cls,
        db: Session,
        pedido_id: int,
    ) -> "Entrega":
        """Pedidos criados antes da Sprint 3 nao tem entrega: cria na hora."""

        entrega = cls.buscar_por_pedido(db, pedido_id)

        if entrega is None:
            entrega = cls.nova(pedido_id)
            db.add(entrega)
            db.commit()
            db.refresh(entrega)

        return entrega
