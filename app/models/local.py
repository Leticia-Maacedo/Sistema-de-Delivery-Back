"""MODEL - entidade Local."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class Local(Base):
    __tablename__ = "local"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=False,
    )

    endereco: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    tipo: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    latitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )

    longitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    @classmethod
    def buscar_por_id(
        cls,
        db: Session,
        local_id: int,
    ):
        return db.get(cls, local_id)

    @classmethod
    def listar(
        cls,
        db: Session,
        usuario_id: int | None = None,
    ):
        stmt = select(cls)

        if usuario_id is not None:
            stmt = stmt.where(
                cls.usuario_id == usuario_id
            )

        stmt = stmt.order_by(cls.id)

        return list(
            db.scalars(stmt).all()
        )

    @classmethod
    def criar(
        cls,
        db: Session,
        usuario_id: int,
        endereco: str,
        tipo: str,
        latitude: Decimal,
        longitude: Decimal,
    ):
        local = cls(
            usuario_id=usuario_id,
            endereco=endereco,
            tipo=tipo,
            latitude=latitude,
            longitude=longitude,
        )

        db.add(local)
        db.commit()
        db.refresh(local)

        return local

    def atualizar(
        self,
        db: Session,
        endereco: str | None = None,
        tipo: str | None = None,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
    ):
        if endereco is not None:
            self.endereco = endereco

        if tipo is not None:
            self.tipo = tipo

        if latitude is not None:
            self.latitude = latitude

        if longitude is not None:
            self.longitude = longitude

        db.add(self)
        db.commit()
        db.refresh(self)

        return self

    def excluir(
        self,
        db: Session,
    ) -> None:
        db.delete(self)
        db.commit()