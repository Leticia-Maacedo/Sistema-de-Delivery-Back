"""Model da nota fiscal de um pedido.

Mapeia a tabela `nota_fiscal` (sql/13_sprint4_nota_fiscal.sql). Guarda a
situacao da emissao no servico fiscal: autorizada, rejeitada pela SEFAZ ou
aguardando nova tentativa porque o servico estava fora do ar. O numero da nota
autorizada tambem vai para `pedido.cupom_fiscal`, que as telas ja mostram.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base

PROCESSANDO = "processando"
AUTORIZADA = "autorizada"
REJEITADA = "rejeitada"
PENDENTE_REENVIO = "pendente_reenvio"
FALHOU = "falhou"
CANCELADA = "cancelada"
SITUACOES = (PROCESSANDO, AUTORIZADA, REJEITADA, PENDENTE_REENVIO, FALHOU, CANCELADA)


class NotaFiscal(Base):
    """Uma nota por pedido; as tentativas de emissao atualizam a mesma linha."""

    __tablename__ = "nota_fiscal"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedido.id"), nullable=False, unique=True)

    provedor: Mapped[str] = mapped_column(String(20), nullable=False)
    ambiente: Mapped[str] = mapped_column(String(15), nullable=False)
    referencia: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PROCESSANDO)

    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serie: Mapped[str | None] = mapped_column(String(5), nullable=True)
    chave: Mapped[str | None] = mapped_column(String(60), nullable=True)
    protocolo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    url_danfe: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mensagem: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def buscar_por_pedido(db: Session, pedido_id: int) -> "NotaFiscal | None":
        return db.execute(select(NotaFiscal).where(NotaFiscal.pedido_id == pedido_id)).scalars().first()

    @staticmethod
    def listar_para_reenvio(db: Session, agora: datetime) -> list["NotaFiscal"]:
        """Notas que ficaram para depois porque o servico estava fora e ja podem tentar de novo."""

        consulta = select(NotaFiscal).where(
            NotaFiscal.status == PENDENTE_REENVIO,
            NotaFiscal.proxima_tentativa_em <= agora,
        ).order_by(NotaFiscal.proxima_tentativa_em)
        return list(db.execute(consulta).scalars())
