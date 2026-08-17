"""MODEL — Produto.

Camada Model do MVC: mapeia a tabela `produto` e concentra as regras
de negocio do dominio (vinculo obrigatorio a um Restaurante, preco
positivo). E o CRUD que esta entrega pede pra demonstrar.
"""
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class Produto(Base):
    __tablename__ = "produto"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurante_id: Mapped[int] = mapped_column(ForeignKey("restaurante.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(300), nullable=True)
    preco: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    disponivel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Produto id={self.id} nome={self.nome!r} restaurante_id={self.restaurante_id}>"

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    @staticmethod
    def buscar_por_id(db: Session, produto_id: int) -> "Produto | None":
        return db.get(Produto, produto_id)

    @staticmethod
    def listar(
        db: Session, restaurante_id: int | None = None, limite: int = 100, pular: int = 0
    ) -> list["Produto"]:
        consulta = select(Produto).order_by(Produto.id)
        if restaurante_id is not None:
            consulta = consulta.where(Produto.restaurante_id == restaurante_id)
        return list(db.execute(consulta.offset(pular).limit(limite)).scalars())

    # ------------------------------------------------------------------
    # Operacoes de persistencia (as 4 do CRUD)
    # ------------------------------------------------------------------

    @classmethod
    def criar(
        cls,
        db: Session,
        *,
        restaurante_id: int,
        nome: str,
        preco: Decimal,
        descricao: str | None = None,
        disponivel: bool = True,
    ) -> "Produto":
        produto = cls(
            restaurante_id=restaurante_id,
            nome=nome.strip(),
            descricao=descricao,
            preco=preco,
            disponivel=disponivel,
        )
        db.add(produto)
        db.commit()
        db.refresh(produto)
        return produto

    def atualizar(self, db: Session, **campos) -> "Produto":
        for campo, valor in campos.items():
            if valor is None:
                continue
            if campo == "nome":
                valor = valor.strip()
            setattr(self, campo, valor)
        db.commit()
        db.refresh(self)
        return self

    def remover(self, db: Session) -> None:
        db.delete(self)
        db.commit()
