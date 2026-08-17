"""MODEL — Usuario.

Camada Model do MVC: mapeia a tabela `usuario` do PostgreSQL e concentra
as regras de negocio que dizem respeito ao usuario.

Nada de HTTP aqui. Se aparecer `status_code` neste arquivo, a regra vazou
para o lugar errado — ela pertence ao Controller.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base

TIPOS_VALIDOS: tuple[str, ...] = ("cliente", "restaurante", "entregador", "admin")


class Usuario(Base):
    """Cadastro unico para os quatro perfis da plataforma (RF01)."""

    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('cliente','restaurante','entregador','admin')",
            name="ck_usuario_tipo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    oauth_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # facilita a leitura no terminal durante o video
        return f"<Usuario id={self.id} email={self.email!r} tipo={self.tipo!r}>"

    # ------------------------------------------------------------------
    # Regras de negocio do dominio Usuario
    # ------------------------------------------------------------------

    @staticmethod
    def tipo_e_valido(tipo: str) -> bool:
        """Regra: o perfil precisa ser um dos quatro previstos no escopo."""
        return tipo in TIPOS_VALIDOS

    @staticmethod
    def email_ja_cadastrado(
        db: Session, email: str, ignorar_id: int | None = None
    ) -> bool:
        """Regra: o e-mail e unico na plataforma (sustenta o CT04).

        `ignorar_id` existe para o UPDATE: ao editar o proprio usuario,
        o e-mail dele mesmo nao pode ser considerado duplicado.
        """
        consulta = select(Usuario).where(Usuario.email == email.lower().strip())
        if ignorar_id is not None:
            consulta = consulta.where(Usuario.id != ignorar_id)
        return db.execute(consulta).scalar_one_or_none() is not None

    @staticmethod
    def buscar_por_email(db: Session, email: str) -> "Usuario | None":
        """Usado pela autenticacao (Letícia) para validar o login."""
        return db.execute(
            select(Usuario).where(Usuario.email == email.lower().strip())
        ).scalar_one_or_none()

    @staticmethod
    def buscar_por_id(db: Session, usuario_id: int) -> "Usuario | None":
        return db.get(Usuario, usuario_id)

    @staticmethod
    def listar(
        db: Session, tipo: str | None = None, limite: int = 100, pular: int = 0
    ) -> list["Usuario"]:
        consulta = select(Usuario).order_by(Usuario.id)
        if tipo:
            consulta = consulta.where(Usuario.tipo == tipo)
        return list(db.execute(consulta.offset(pular).limit(limite)).scalars())

    # ------------------------------------------------------------------
    # Operacoes de persistencia (as 4 do CRUD)
    # ------------------------------------------------------------------

    @classmethod
    def criar(
        cls,
        db: Session,
        *,
        nome: str,
        email: str,
        senha_hash: str | None,
        telefone: str | None,
        tipo: str,
        oauth_provider: str | None = None,
    ) -> "Usuario":
        usuario = cls(
            nome=nome.strip(),
            email=email.lower().strip(),
            senha_hash=senha_hash,
            telefone=telefone,
            tipo=tipo,
            oauth_provider=oauth_provider,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario

    def atualizar(self, db: Session, **campos) -> "Usuario":
        for campo, valor in campos.items():
            if valor is None:
                continue
            if campo == "email":
                valor = valor.lower().strip()
            if campo == "nome":
                valor = valor.strip()
            setattr(self, campo, valor)
        db.commit()
        db.refresh(self)
        return self

    def remover(self, db: Session) -> None:
        """Encerramento de conta (RF06)."""
        db.delete(self)
        db.commit()
