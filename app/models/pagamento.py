"""Model de Pagamento do EntregaFood.

Mapeia a tabela `pagamento` (01_create_tables.sql, completada no
08_sprint3_pagamento_nf.sql). Concentra as operacoes de persistencia
relacionadas ao pagamento de um pedido. Cada pedido tem no maximo um
pagamento: uma nova tentativa (cartao recusado, troca de metodo) atualiza
a mesma linha.

Dados do cartao nunca sao gravados aqui.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, select
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

    # pendente, aprovado, recusado, a_receber, expirado, cancelado, estornado
    # (app/core/pagamento_regras.py)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pendente",
    )

    valor: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    # Id da cobranca no Asaas (ou SIM-... no gateway simulado).
    transacao_externa_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    mensagem: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    pix_copia_cola: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    pix_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    nota_enviada_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
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

    @classmethod
    def registrar_tentativa(
        cls,
        db: Session,
        *,
        pedido_id: int,
        metodo: str,
        valor: Decimal,
        status: str,
        transacao_externa_id: str | None = None,
        mensagem: str | None = None,
        pix_copia_cola: str | None = None,
        pix_expira_em: datetime | None = None,
    ) -> "Pagamento":
        """Grava o resultado de uma tentativa, criando ou reaproveitando a linha.

        A tabela permite um pagamento por pedido (pedido_id UNIQUE), entao
        uma nova tentativa substitui os dados da anterior.
        """

        pagamento = cls.buscar_por_pedido(db, pedido_id)
        agora = datetime.now()

        if pagamento is None:
            pagamento = cls(pedido_id=pedido_id, criado_em=agora)
            db.add(pagamento)

        pagamento.metodo = metodo
        pagamento.valor = valor
        pagamento.status = status
        pagamento.transacao_externa_id = transacao_externa_id
        pagamento.mensagem = (mensagem or "")[:300] or None
        pagamento.pix_copia_cola = pix_copia_cola
        pagamento.pix_expira_em = pix_expira_em
        pagamento.atualizado_em = agora

        db.commit()
        db.refresh(pagamento)

        return pagamento

    def atualizar_status(
        self,
        db: Session,
        *,
        status: str,
        transacao_externa_id: str | None = None,
        mensagem: str | None = None,
    ) -> "Pagamento":
        """Atualiza o resultado do processamento do pagamento."""

        self.status = status
        self.atualizado_em = datetime.now()

        if transacao_externa_id is not None:
            self.transacao_externa_id = transacao_externa_id

        if mensagem is not None:
            self.mensagem = mensagem[:300]

        db.commit()
        db.refresh(self)

        return self

    def marcar_nota_enviada(self, db: Session) -> None:
        """Registra que a nota fiscal foi enviada por e-mail."""

        self.nota_enviada_em = datetime.now()
        db.commit()
