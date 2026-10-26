"""MODEL — Usuario.

Camada Model do MVC: mapeia a tabela `usuario` do PostgreSQL e concentra
as regras de negocio que dizem respeito ao usuario.

Nada de HTTP aqui. Se aparecer `status_code` neste arquivo, a regra vazou
para o lugar errado — ela pertence ao Controller.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, delete, func, inspect, select, text, update
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
    email: Mapped[str | None] = mapped_column(
        String(150), nullable=True, unique=True, index=True
    )
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
    def telefone_ja_cadastrado(
        db: Session, telefone: str, ignorar_id: int | None = None
    ) -> bool:
        """Regra: o telefone deve ser unico quando informado."""
        telefone_normalizado = "".join(filter(str.isdigit, telefone))

        consulta = select(Usuario).where(
            Usuario.telefone == telefone_normalizado
        )

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
    def buscar_por_telefone(db: Session, telefone: str) -> "Usuario | None":
        """Usado pela autenticacao para localizar usuario pelo telefone."""
        telefone_normalizado = "".join(filter(str.isdigit, telefone))

        return db.execute(
            select(Usuario).where(Usuario.telefone == telefone_normalizado)
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
        email: str | None,
        senha_hash: str | None,
        telefone: str | None,
        tipo: str,
        oauth_provider: str | None = None,
    ) -> "Usuario":
        usuario = cls(
            nome=nome.strip(),
            email=email.lower().strip() if email else None,
            senha_hash=senha_hash,
            telefone="".join(filter(str.isdigit, telefone)) if telefone else None,
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
            if campo == "telefone":
                valor = "".join(filter(str.isdigit, valor))
            if campo == "nome":
                valor = valor.strip()
            setattr(self, campo, valor)
        db.commit()
        db.refresh(self)
        return self

    def remover(self, db: Session) -> None:
        """Encerramento de conta (RF06).

        A cesta, as inscricoes de notificacao e os enderecos de entrega saem
        sempre. Sem historico, a conta e apagada. Com pedidos, entregas ou
        restaurante, a conta e anonimizada: nome, e-mail, telefone, senha e
        login social saem e a conta nao entra mais, mas os pedidos continuam
        integros para o restaurante e para os relatorios.
        """
        from app.models.entrega import Entrega
        from app.models.local import Local
        from app.models.pedido import Pedido
        from app.models.pedido_status_historico import PedidoStatusHistorico
        from app.models.push_inscricao import PushInscricao
        from app.models.restaurante import Restaurante
        from app.models.sacola import ItemSacola, Sacola

        sacolas = select(Sacola.id).where(Sacola.cliente_id == self.id)
        db.execute(delete(ItemSacola).where(ItemSacola.sacola_id.in_(sacolas)))
        db.execute(delete(Sacola).where(Sacola.cliente_id == self.id))
        db.execute(delete(PushInscricao).where(PushInscricao.usuario_id == self.id))
        db.execute(delete(Local).where(Local.usuario_id == self.id, Local.id.not_in(select(Restaurante.local_id))))

        referencias = [
            (Pedido, Pedido.cliente_id), (Restaurante, Restaurante.usuario_id), (Entrega, Entrega.entregador_id),
            (PedidoStatusHistorico, PedidoStatusHistorico.alterado_por), (Local, Local.usuario_id),
        ]
        tem_historico = any(
            db.scalar(select(func.count()).select_from(tabela).where(coluna == self.id)) for tabela, coluna in referencias
        )
        if not tem_historico and inspect(db.get_bind()).has_table("avaliacao"):
            tem_historico = bool(db.scalar(
                text("SELECT count(*) FROM avaliacao WHERE avaliador_id = :id OR avaliado_id = :id"), {"id": self.id}
            ))

        if tem_historico:
            self.nome = "Conta encerrada"
            self.email = f"conta.encerrada.{self.id}@entregafood.com"  # unico e sem dono real
            self.telefone = None
            self.senha_hash = None
            self.oauth_provider = None
            db.execute(update(Restaurante).where(Restaurante.usuario_id == self.id).values(ativo=False))
        else:
            db.delete(self)
        db.commit()