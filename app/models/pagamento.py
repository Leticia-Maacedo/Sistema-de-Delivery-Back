"""Model de Pagamento do EntregaFood.

Mapeia a tabela `pagamento`, que ja existe no schema do banco.
Concentra as operacoes de persistencia relacionadas ao pagamento
de um pedido.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class Pagamento(Base):
    """Representa o pagamento associado a um pedido."""

    __tablename__ = "pagamento"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id"),
        nullable=False,
        unique=True,
    )

    metodo: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pendente",
    )

    valor: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    transacao_externa_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    @staticmethod
    def buscar_por_id(
        db: Session,
        pagamento_id: int,
    ) -> "Pagamento | None":
        """Busca um pagamento pelo id."""

        return db.get(Pagamento, pagamento_id)

    @staticmethod
    def buscar_por_pedido(
        db: Session,
        pedido_id: int,
    ) -> "Pagamento | None":
        """Busca o pagamento associado a um pedido."""

        consulta = select(Pagamento).where(
            Pagamento.pedido_id == pedido_id,
        )

        return db.execute(consulta).scalars().first()

    @classmethod
    def criar(
        cls,
        db: Session,
        *,
        pedido_id: int,
        metodo: str,
        valor: Decimal,
        status: str = "pendente",
        transacao_externa_id: str | None = None,
    ) -> "Pagamento":
        """Cria um pagamento para um pedido."""

        pagamento = cls(
            pedido_id=pedido_id,
            metodo=metodo,
            status=status,
            valor=valor,
            transacao_externa_id=transacao_externa_id,
            criado_em=datetime.now(),
        )

        db.add(pagamento)
        db.commit()
        db.refresh(pagamento)

        return pagamento

    def atualizar_status(
        self,
        db: Session,
        *,
        status: str,
        transacao_externa_id: str | None = None,
    ) -> "Pagamento":
        """Atualiza o resultado do processamento do pagamento."""

        self.status = status

        if transacao_externa_id is not None:
            self.transacao_externa_id = transacao_externa_id

        db.commit()
        db.refresh(self)

        return self