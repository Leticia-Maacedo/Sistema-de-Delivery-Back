"""MODEL — Restaurante.

Camada Model do MVC: mapeia a tabela `restaurante` e concentra as
regras de negocio do dominio (CNPJ unico, vinculo obrigatorio a um
Local). Pre-requisito para o cadastro de Produto.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.local import Local

APROVADO = "aprovado"


class Restaurante(Base):
    __tablename__ = "restaurante"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("local.id"), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(120), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, unique=True)
    status_aprovacao: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    taxa_entrega_km: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
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
    ) -> "Restaurante":
        restaurante = cls(
            local_id=local_id,
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
