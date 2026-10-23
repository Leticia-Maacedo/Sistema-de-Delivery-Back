"""MODEL — Restaurante.

Camada Model do MVC: mapeia a tabela `restaurante` e concentra as
regras de negocio do dominio (CNPJ unico, vinculo obrigatorio a um
Local). Pre-requisito para o cadastro de Produto.
"""
from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Time, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.local import Local

APROVADO = "aprovado"


class Restaurante(Base):
    __tablename__ = "restaurante"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("local.id"), nullable=False)
    # Usuario (tipo "restaurante") dono do restaurante - sql/06.
    # Nullable: restaurante cadastrado pelo admin pode ficar sem dono.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    nome_fantasia: Mapped[str] = mapped_column(String(120), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, unique=True)
    status_aprovacao: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    taxa_entrega_km: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    # Gestao pelo parceiro (sql/10): pausar, raio proprio e horario.
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    raio_entrega_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    horario_abertura: Mapped[time | None] = mapped_column(Time, nullable=True)
    horario_fechamento: Mapped[time | None] = mapped_column(Time, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Endereco do restaurante. lazy="joined": a consulta ja traz o Local
    # no mesmo SELECT, sem disparar uma query extra por restaurante.
    local: Mapped["Local"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<Restaurante id={self.id} nome_fantasia={self.nome_fantasia!r}>"

    # ------------------------------------------------------------------
    # Regras de negocio
    # ------------------------------------------------------------------

    @staticmethod
    def cnpj_ja_cadastrado(db: Session, cnpj: str, ignorar_id: int | None = None) -> bool:
        consulta = select(Restaurante).where(Restaurante.cnpj == cnpj)
        if ignorar_id is not None:
            consulta = consulta.where(Restaurante.id != ignorar_id)
        return db.execute(consulta).scalar_one_or_none() is not None

    @staticmethod
    def buscar_por_id(db: Session, restaurante_id: int) -> "Restaurante | None":
        return db.get(Restaurante, restaurante_id)

    def aberto_agora(self, agora: datetime | None = None) -> bool:
        """Regra: recebe pedidos se estiver ativo e dentro do horario.

        Sem horario definido, vale so o "ativo". Fechamento antes da
        abertura atravessa a meia-noite (ex.: 18:00 as 02:00).
        """
        if not self.ativo:
            return False
        if self.horario_abertura is None or self.horario_fechamento is None:
            return True
        hora = (agora or datetime.now()).time()
        abre, fecha = self.horario_abertura, self.horario_fechamento
        if abre <= fecha:
            return abre <= hora < fecha
        return hora >= abre or hora < fecha

    @property
    def aberto(self) -> bool:
        return self.aberto_agora()

    def motivo_fechado(self) -> str:
        """Texto para o cliente quando o restaurante nao recebe pedidos."""
        if not self.ativo:
            return "O restaurante esta pausado e nao esta recebendo pedidos agora."
        return (
            f"O restaurante esta fechado agora. Funciona das "
            f"{self.horario_abertura:%H:%M} as {self.horario_fechamento:%H:%M}."
        )

    @staticmethod
    def buscar_por_dono(db: Session, usuario_id: int) -> "Restaurante | None":
        """Restaurante do usuario (tipo "restaurante") logado."""
        consulta = select(Restaurante).where(Restaurante.usuario_id == usuario_id).order_by(Restaurante.id.desc())
        return db.execute(consulta).unique().scalars().first()

    def pertence_a(self, usuario_id: int) -> bool:
        """Regra: o usuario e o dono deste restaurante."""
        return self.usuario_id is not None and self.usuario_id == usuario_id

    @staticmethod
    def listar(db: Session, limite: int = 100, pular: int = 0) -> list["Restaurante"]:
        consulta = select(Restaurante).order_by(Restaurante.id).offset(pular).limit(limite)
        return list(db.execute(consulta).scalars())

    # ------------------------------------------------------------------
    # Consultas do cliente (Sprint 2) — so restaurantes aprovados
    # ------------------------------------------------------------------

    @staticmethod
    def listar_aprovados(
        db: Session,
        busca: str | None = None,
        limite: int = 100,
        pular: int = 0,
    ) -> list["Restaurante"]:
        """Restaurantes visiveis pro cliente: status 'aprovado', opcionalmente
        filtrados por trecho do nome fantasia (case-insensitive)."""
        consulta = select(Restaurante).where(Restaurante.status_aprovacao == APROVADO)
        if busca:
            consulta = consulta.where(Restaurante.nome_fantasia.ilike(f"%{busca.strip()}%"))
        consulta = consulta.order_by(Restaurante.nome_fantasia).offset(pular).limit(limite)
        return list(db.execute(consulta).unique().scalars())

    @staticmethod
    def buscar_aprovado_por_id(db: Session, restaurante_id: int) -> "Restaurante | None":
        """Igual a buscar_por_id, mas so devolve se o restaurante estiver aprovado —
        um restaurante pendente/recusado nao existe pro cliente."""
        consulta = select(Restaurante).where(
            Restaurante.id == restaurante_id,
            Restaurante.status_aprovacao == APROVADO,
        )
        return db.execute(consulta).unique().scalar_one_or_none()

    # ------------------------------------------------------------------
    # Operacoes de persistencia (as 4 do CRUD)
    # ------------------------------------------------------------------

    @classmethod
    def criar(
        cls,
        db: Session,
        *,
        local_id: int,
        nome_fantasia: str,
        cnpj: str,
        taxa_entrega_km: Decimal,
        status_aprovacao: str = "pendente",
        usuario_id: int | None = None,
        **extras,
    ) -> "Restaurante":
        restaurante = cls(
            **extras,
            local_id=local_id,
            usuario_id=usuario_id,
            nome_fantasia=nome_fantasia.strip(),
            cnpj=cnpj.strip(),
            taxa_entrega_km=taxa_entrega_km,
            status_aprovacao=status_aprovacao,
        )
        db.add(restaurante)
        db.commit()
        db.refresh(restaurante)
        return restaurante

    def atualizar(self, db: Session, **campos) -> "Restaurante":
        for campo, valor in campos.items():
            if valor is None:
                continue
            if campo == "nome_fantasia":
                valor = valor.strip()
            if campo == "cnpj":
                valor = valor.strip()
            setattr(self, campo, valor)
        db.commit()
        db.refresh(self)
        return self

    def remover(self, db: Session) -> None:
        db.delete(self)
        db.commit()
