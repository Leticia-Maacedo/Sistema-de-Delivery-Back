"""Model para codigos OTP temporarios."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CodigoOTP(Base):
    """Codigo OTP temporario usado em login ou cadastro."""

    __tablename__ = "codigo_otp"

    telefone: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    finalidade: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    codigo: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )

    expira_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    tentativas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
