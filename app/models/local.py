"""MODEL — Local.

Camada Model do MVC: mapeia a tabela `local`. Um local pertence a um
usuario (endereco de entrega, ou o endereco do restaurante) e e pre-
requisito para o cadastro de um Restaurante.

Escopo desta entrega: so precisamos CRIAR um local (para desbloquear o
cadastro de Restaurante) — nao ha tela nem operacao de editar/excluir.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class Local(Base):
    __tablename__ = "local"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    endereco: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Local id={self.id} endereco={self.endereco!r}>"

    @staticmethod
    def buscar_por_id(db: Session, local_id: int) -> "Local | None":
        return db.get(Local, local_id)

    @classmethod
    def criar(
        cls,
        db: Session,
        *,
        usuario_id: int,
        endereco: str,
        tipo: str,
        latitude: Decimal,
        longitude: Decimal,
    ) -> "Local":
        local = cls(
            usuario_id=usuario_id,
            endereco=endereco.strip(),
            tipo=tipo,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(local)
        db.commit()
        db.refresh(local)
        return local
