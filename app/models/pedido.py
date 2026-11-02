"""Model de Pedido do EntregaFood.

Mapeia a tabela `pedido`, que ja existe no schema do banco.
Nesta etapa, o model fornece as operacoes necessarias para
integrar o pedido ao fluxo de pagamento.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.core.status_pedido import AGUARDANDO_ACEITE, CANCELADO, ENTREGUE, EM_TRANSITO
from app.models.entrega import Entrega
from app.models.item_pedido import ItemPedido
from app.models.pedido_status_historico import PedidoStatusHistorico
from app.models.restaurante import Restaurante


class Pedido(Base):
    """Representa um pedido realizado por um cliente."""

    __tablename__ = "pedido"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id"),
        nullable=False,
    )

    restaurante_id: Mapped[int] = mapped_column(
        ForeignKey("restaurante.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="aguardando_aceite",
    )

    tipo_entrega: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    forma_pagamento: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    valor_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    taxa_entrega: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
    )

    cupom_fiscal: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Endereco de entrega copiado no fechamento (delivery). Fica gravado no
    # pedido para que trocar ou excluir o endereco depois nao mude o destino.
    endereco_entrega: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    latitude_entrega: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude_entrega: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
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

    @staticmethod
    def buscar_por_id(
        db: Session,
        pedido_id: int,
    ) -> "Pedido | None":
        """Busca um pedido pelo id."""

        return db.get(Pedido, pedido_id)

    @classmethod
    def criar_a_partir_da_cesta(
        cls,
        db: Session,
        *,
        cliente_id: int,
        restaurante_id: int,
        tipo_entrega: str,
        forma_pagamento: str,
        subtotal: Decimal,
        taxa_entrega: Decimal,
        itens: list[tuple[int, int, Decimal]],
        sacola,
        local_entrega=None,
    ) -> "Pedido":
        """Cria o pedido, copia os itens com o preco do momento e esvazia a cesta.

        `itens` e uma lista de (produto_id, quantidade, preco_unitario).
        `local_entrega` (delivery) e copiado para o pedido.
        Tudo e gravado num unico commit: se algo falhar, nada fica pela metade.
        """

        pedido = cls(
            cliente_id=cliente_id,
            restaurante_id=restaurante_id,
            status="aguardando_aceite",
            tipo_entrega=tipo_entrega,
            forma_pagamento=forma_pagamento,
            valor_total=subtotal + taxa_entrega,
            taxa_entrega=taxa_entrega,
            cupom_fiscal=None,
            endereco_entrega=local_entrega.endereco if local_entrega else None,
            latitude_entrega=local_entrega.latitude if local_entrega else None,
            longitude_entrega=local_entrega.longitude if local_entrega else None,
            criado_em=datetime.now(),
            atualizado_em=None,
        )
        db.add(pedido)
        db.flush()  # gera o id do pedido para os itens

        for produto_id, quantidade, preco_unitario in itens:
            db.add(
                ItemPedido(
                    pedido_id=pedido.id,
                    produto_id=produto_id,
                    quantidade=quantidade,
                    preco_unitario=preco_unitario,
                )
            )

        # Sprint 3: a entrega nasce com o codigo de validacao e a linha do
        # tempo do pedido comeca em "aguardando_aceite".
        db.add(Entrega.nova(pedido.id))
        PedidoStatusHistorico.registrar(
            db,
            pedido_id=pedido.id,
            status=AGUARDANDO_ACEITE,
            alterado_por=cliente_id,
        )

        sacola.esvaziar(db)

        db.commit()
        db.refresh(pedido)

        return pedido

    def definir_forma_pagamento(
        self,
        db: Session,
        forma_pagamento: str,
    ) -> "Pedido":
        """Define a forma de pagamento escolhida para o pedido."""

        self.forma_pagamento = forma_pagamento
        self.atualizado_em = datetime.now()

        db.commit()
        db.refresh(self)

        return self

    @staticmethod
    def listar_por_cliente(
        db: Session,
        cliente_id: int,
    ) -> list["Pedido"]:
        """Pedidos do cliente, do mais recente para o mais antigo."""

        consulta = (
            select(Pedido)
            .where(Pedido.cliente_id == cliente_id)
            .order_by(Pedido.criado_em.desc(), Pedido.id.desc())
        )

        return list(db.execute(consulta).scalars())

    @staticmethod
    def listar_vendas(
        db: Session,
        *,
        inicio: datetime | None = None,
        fim: datetime | None = None,
        dono_restaurante_id: int | None = None,
    ) -> list[tuple[int, str, str, Decimal]]:
        """Pedidos aceitos no periodo, para os relatorios (Sprint 4).

        Retorna (restaurante_id, nome do restaurante, forma de pagamento,
        valor total). Fora: aguardando aceite e cancelados. `fim` e
        exclusivo. Com `dono_restaurante_id`, so os restaurantes desse dono.
        """

        consulta = (
            select(
                Pedido.restaurante_id,
                Restaurante.nome_fantasia,
                Pedido.forma_pagamento,
                Pedido.valor_total,
            )
            .join(Restaurante, Restaurante.id == Pedido.restaurante_id)
            .where(Pedido.status.not_in([AGUARDANDO_ACEITE, CANCELADO]))
        )

        if inicio is not None:
            consulta = consulta.where(Pedido.criado_em >= inicio)
        if fim is not None:
            consulta = consulta.where(Pedido.criado_em < fim)
        if dono_restaurante_id is not None:
            consulta = consulta.where(Restaurante.usuario_id == dono_restaurante_id)

        return [tuple(linha) for linha in db.execute(consulta)]

    @staticmethod
    def listar_para_operacao(
        db: Session,
        *,
        incluir_finalizados: bool = False,
        dono_restaurante_id: int | None = None,
    ) -> list["Pedido"]:
        """Pedidos que o restaurante/entregador ainda precisam movimentar.

        Com `dono_restaurante_id`, traz so os pedidos dos restaurantes
        desse usuario (painel do usuario restaurante).
        """

        consulta = select(Pedido).order_by(Pedido.criado_em.desc(), Pedido.id.desc())

        if dono_restaurante_id is not None:
            consulta = consulta.join(
                Restaurante, Restaurante.id == Pedido.restaurante_id
            ).where(Restaurante.usuario_id == dono_restaurante_id)

        if not incluir_finalizados:
            consulta = consulta.where(Pedido.status.not_in([ENTREGUE, CANCELADO]))

        return list(db.execute(consulta).scalars())

    def alterar_status(
        self,
        db: Session,
        novo_status: str,
        *,
        usuario_id: int,
    ) -> "Pedido":
        """Muda o status, registra no historico e acompanha a entrega.

        As regras (ordem do fluxo, quem pode) sao conferidas antes, pelo
        controller, com app/core/status_pedido.py.
        """

        agora = datetime.now()
        self.status = novo_status
        self.atualizado_em = agora

        entrega = Entrega.buscar_por_pedido(db, self.id)

        if entrega is not None:
            if novo_status == EM_TRANSITO:
                # O entregador fica so na entrega (sql/06): quem marca
                # "em_transito" e quem leva o pedido.
                entrega.status = "em_transito"
                entrega.entregador_id = usuario_id
            elif novo_status == ENTREGUE:
                entrega.status = "entregue"
                entrega.entregue_em = agora
            elif novo_status == CANCELADO:
                entrega.status = "cancelada"
            entrega.atualizado_em = agora

        PedidoStatusHistorico.registrar(
            db,
            pedido_id=self.id,
            status=novo_status,
            alterado_por=usuario_id,
        )

        db.commit()
        db.refresh(self)

        return self