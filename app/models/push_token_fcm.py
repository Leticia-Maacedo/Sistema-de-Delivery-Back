"""Model do token de notificacao do app mobile (Firebase Cloud Messaging).

Mapeia a tabela `push_token_fcm` (sql/11_sprint4_push_fcm.sql). Cada
celular em que o usuario abriu o app vira uma linha. O token e unico: se o
mesmo celular entrar com outra conta, o token passa a ser dessa conta.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class PushTokenFCM(Base):
    """Token do Firebase de um celular de um usuario."""

    __tablename__ = "push_token_fcm"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=False,
    )

    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    plataforma: Mapped[str] = mapped_column(String(20), nullable=False, default="android")

    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def listar_por_usuario(db: Session, usuario_id: int) -> list["PushTokenFCM"]:
        consulta = select(PushTokenFCM).where(PushTokenFCM.usuario_id == usuario_id)
        return list(db.execute(consulta).scalars())

    @staticmethod
    def buscar_por_token(db: Session, token: str) -> "PushTokenFCM | None":
        consulta = select(PushTokenFCM).where(PushTokenFCM.token == token)
        return db.execute(consulta).scalars().first()

    @classmethod
    def salvar(
        cls,
        db: Session,
        *,
        usuario_id: int,
        token: str,
        plataforma: str,
    ) -> tuple["PushTokenFCM", bool]:
        """Cria o token ou atualiza o existente. Retorna (token, criado_agora)."""

        registro = cls.buscar_por_token(db, token)
        agora = datetime.now()
        criado = registro is None

        if criado:
            registro = cls(token=token, criado_em=agora)
            db.add(registro)

        registro.usuario_id = usuario_id
        registro.plataforma = plataforma
        registro.atualizado_em = agora

        db.commit()
        db.refresh(registro)
        return registro, criado

    @staticmethod
    def remover(db: Session, token: str, usuario_id: int | None = None) -> bool:
        """Apaga o token (logout no app, ou token que o Firebase diz que expirou)."""

        registro = PushTokenFCM.buscar_por_token(db, token)

        if registro is None or (usuario_id is not None and registro.usuario_id != usuario_id):
            return False

        db.delete(registro)
        db.commit()
        return True
