"""MODEL — Produto.

Camada Model do MVC: mapeia a tabela `produto` e concentra as regras
de negocio do dominio (vinculo obrigatorio a um Restaurante, preco
positivo). E o CRUD que esta entrega pede pra demonstrar.

Estoque (Sprint 4, sql/12): `estoque` NULL = sem controle (vende sem
limite); numero = unidades disponiveis. A baixa acontece quando o pedido
e criado e a devolucao quando ele e cancelado (app/models/pedido.py).
"""
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, or_, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class EstoqueInsuficiente(Exception):
    """O estoque acabou entre a validacao da cesta e a criacao do pedido."""

    def __init__(self, nome_produto: str):
        self.nome_produto = nome_produto
        super().__init__(
            f"O produto '{nome_produto}' nao tem estoque suficiente. "
            "Ajuste a quantidade na cesta para continuar."
        )


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        CheckConstraint("estoque IS NULL OR estoque >= 0", name="ck_produto_estoque_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurante_id: Mapped[int] = mapped_column(ForeignKey("restaurante.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(300), nullable=True)
    preco: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    disponivel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    estoque: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    def __repr__(self) -> str:
        return f"<Produto id={self.id} nome={self.nome!r} restaurante_id={self.restaurante_id}>"

    # ------------------------------------------------------------------
    # Estoque
    # ------------------------------------------------------------------

    @property
    def controla_estoque(self) -> bool:
        return self.estoque is not None

    @property
    def esgotado(self) -> bool:
        return self.estoque is not None and self.estoque <= 0

    def problema_de_estoque(self, quantidade: int) -> str | None:
        """Mensagem quando `quantidade` passa do estoque; None se cabe."""

        if self.estoque is None or quantidade <= self.estoque:
            return None
        if self.estoque <= 0:
            return f"O produto '{self.nome}' esta esgotado."
        unidades = "unidade" if self.estoque == 1 else "unidades"
        return f"So ha {self.estoque} {unidades} de '{self.nome}' em estoque."

    @staticmethod
    def baixar_estoque(db: Session, produto_id: int, quantidade: int) -> bool:
        """Tira `quantidade` do estoque sem fazer commit (faz parte da
        transacao do pedido).

        O UPDATE so acontece se ainda houver estoque, entao dois pedidos ao
        mesmo tempo nao deixam o estoque negativo. Produto sem controle
        (NULL) passa direto. Retorna False se faltou estoque.
        """

        resultado = db.execute(
            update(Produto)
            .where(
                Produto.id == produto_id,
                or_(Produto.estoque.is_(None), Produto.estoque >= quantidade),
            )
            .values(estoque=Produto.estoque - quantidade)  # NULL - n continua NULL
            .execution_options(synchronize_session=False)
        )
        return resultado.rowcount == 1

    @staticmethod
    def devolver_estoque(db: Session, produto_id: int, quantidade: int) -> None:
        """Devolve `quantidade` ao estoque (pedido cancelado). Sem commit."""

        db.execute(
            update(Produto)
            .where(Produto.id == produto_id, Produto.estoque.is_not(None))
            .values(estoque=Produto.estoque + quantidade)
            .execution_options(synchronize_session=False)
        )

    def definir_estoque(self, db: Session, estoque: int | None) -> "Produto":
        """Define o estoque (contagem). None desliga o controle."""

        self.estoque = estoque
        db.commit()
        db.refresh(self)
        return self

    def ajustar_estoque(self, db: Session, ajuste: int) -> bool:
        """Entrada (+) ou saida (-) de unidades. Nao deixa ficar negativo.

        Retorna False se o produto nao controla estoque ou se a saida for
        maior que o estoque atual.
        """

        resultado = db.execute(
            update(Produto)
            .where(
                Produto.id == self.id,
                Produto.estoque.is_not(None),
                Produto.estoque + ajuste >= 0,
            )
            .values(estoque=Produto.estoque + ajuste)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        db.refresh(self)
        return resultado.rowcount == 1

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

    @staticmethod
    def listar_disponiveis(db: Session, restaurante_id: int) -> list["Produto"]:
        """Itens do cardapio que o cliente pode pedir: de um restaurante,
        com `disponivel = true` e nao esgotados (estoque NULL ou > 0).
        Ordenado por nome pra montar a tela."""
        consulta = (
            select(Produto)
            .where(
                Produto.restaurante_id == restaurante_id,
                Produto.disponivel.is_(True),
                or_(Produto.estoque.is_(None), Produto.estoque > 0),
            )
            .order_by(Produto.nome)
        )
        return list(db.execute(consulta).scalars())

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
        estoque: int | None = None,
    ) -> "Produto":
        produto = cls(
            restaurante_id=restaurante_id,
            nome=nome.strip(),
            descricao=descricao,
            preco=preco,
            disponivel=disponivel,
            estoque=estoque,
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
