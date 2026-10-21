"""Model do historico de status do pedido.

Mapeia a tabela `pedido_status_historico` (05_sprint3_acompanhamento.sql).
Cada mudanca de status do pedido grava uma linha: e a linha do tempo
mostrada na tela de acompanhamento do cliente.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class PedidoStatusHistorico(Base):
    """Uma mudanca de status de um pedido."""

    __tablename__ = "pedido_status_historico"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    alterado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    @classmethod
    def registrar(
        cls,
        db: Session,
        *,
        pedido_id: int,
        status: str,
        alterado_por: int | None,
    ) -> "PedidoStatusHistorico":
        """Adiciona a mudanca na sessao. Nao faz commit."""

        registro = cls(
            pedido_id=pedido_id,
            status=status,
            alterado_por=alterado_por,
            criado_em=datetime.now(),
        )
        db.add(registro)

        return registro

    @staticmethod
    def listar_por_pedido(
        db: Session,
        pedido_id: int,
    ) -> list["PedidoStatusHistorico"]:
        """Linha do tempo do pedido, da mais antiga para a mais recente."""

        consulta = (
            select(PedidoStatusHistorico)
            .where(PedidoStatusHistorico.pedido_id == pedido_id)
            .order_by(PedidoStatusHistorico.criado_em, PedidoStatusHistorico.id)
        )

        return list(db.execute(consulta).scalars())
