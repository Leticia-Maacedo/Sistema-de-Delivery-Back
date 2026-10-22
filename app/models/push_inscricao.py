"""Model da inscricao de notificacoes push (Web Push).

Mapeia a tabela `push_inscricao` (sql/07_sprint3_push.sql). Cada navegador
em que o usuario ativou as notificacoes vira uma linha.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class PushInscricao(Base):
    """Uma inscricao de push de um usuario num navegador."""

    __tablename__ = "push_inscricao"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=False,
    )

    endpoint: Mapped[str] = mapped_column(String(600), nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    @staticmethod
    def listar_por_usuario(db: Session, usuario_id: int) -> list["PushInscricao"]:
        consulta = select(PushInscricao).where(PushInscricao.usuario_id == usuario_id)
        return list(db.execute(consulta).scalars())

    @staticmethod
    def buscar_por_endpoint(db: Session, endpoint: str) -> "PushInscricao | None":
        consulta = select(PushInscricao).where(PushInscricao.endpoint == endpoint)
        return db.execute(consulta).scalars().first()

    @classmethod
    def salvar(
        cls,
        db: Session,
        *,
        usuario_id: int,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> "PushInscricao":
        """Cria a inscricao ou atualiza a existente (mesmo navegador)."""

        inscricao = cls.buscar_por_endpoint(db, endpoint)

        if inscricao is None:
            inscricao = cls(endpoint=endpoint, criado_em=datetime.now())
            db.add(inscricao)

        inscricao.usuario_id = usuario_id
        inscricao.p256dh = p256dh
        inscricao.auth = auth

        db.commit()
        db.refresh(inscricao)
        return inscricao

    @staticmethod
    def remover_por_endpoint(db: Session, endpoint: str, usuario_id: int | None = None) -> bool:
        inscricao = PushInscricao.buscar_por_endpoint(db, endpoint)

        if inscricao is None or (usuario_id is not None and inscricao.usuario_id != usuario_id):
            return False

        db.delete(inscricao)
        db.commit()
        return True
