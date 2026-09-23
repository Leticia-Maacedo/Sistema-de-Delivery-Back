"""Models da cesta de compras (sacola) do EntregaFood."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class Sacola(Base):
    """Representa a cesta de compras de um cliente."""

    __tablename__ = "sacola"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def buscar_por_cliente(db: Session, cliente_id: int) -> "Sacola | None":
        consulta = (
            select(Sacola)
            .where(Sacola.cliente_id == cliente_id)
            .order_by(Sacola.id.desc())
        )
        return db.execute(consulta).scalars().first()


class ItemSacola(Base):
    """Representa um produto adicionado à cesta."""

    __tablename__ = "item_sacola"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sacola_id: Mapped[int] = mapped_column(ForeignKey("sacola.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)

    @staticmethod
    def listar_por_sacola(db: Session, sacola_id: int) -> list["ItemSacola"]:
        consulta = (
            select(ItemSacola)
            .where(ItemSacola.sacola_id == sacola_id)
            .order_by(ItemSacola.id)
        )
        return list(db.execute(consulta).scalars())
