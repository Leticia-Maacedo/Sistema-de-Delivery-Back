"""Controller de Pedido do EntregaFood.

Sprint 3:
    - Fechar Pedido: criar o pedido a partir da cesta, com o tipo de
      entrega escolhido (delivery ou retirada).
    - Acompanhar Entrega: consultar os pedidos, mudar o status
      (restaurante/entregador) e concluir com o codigo de entrega.

As regras do fluxo de status ficam em app/core/status_pedido.py.
"""

from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.controllers.pagamento_controller import cancelar_pagamento_do_pedido, receber_pagamento_na_entrega
from app.controllers.sacola_controller import preparar_fechamento
from app.core import pagamento_regras, status_pedido
from app.core.database import get_db
from app.core.notificacoes_pedido import (
    notificar_cancelamento_cliente,
    notificar_mudanca_status,
    notificar_pedido_criado,
)
from app.core.security import exigir_cliente, obter_usuario_logado
from app.models.entrega import Entrega
from app.models.item_pedido import ItemPedido
from app.models.pagamento import Pagamento
from app.models.pedido import Pedido
from app.models.pedido_status_historico import PedidoStatusHistorico
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario
from app.schemas.pedido import (
    ConfirmarEntregaIn,
    EtapaPedidoOut,
    ItemPedidoOut,
    PedidoCriarIn,
    PedidoDetalheOut,
    PedidoOut,
    PedidoResumoOut,
    StatusPedidoIn,
)


router = APIRouter(prefix="/pedidos", tags=["Pedido"])


# ------------------------------------------------------------------ apoio


def exigir_operador(usuario: Usuario) -> None:
    """Somente restaurante, entregador ou admin movimentam pedidos."""

    if usuario.tipo not in status_pedido.OPERADORES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente restaurante, entregador ou admin podem acessar o painel de pedidos.",
        )


def buscar_pedido_visivel(
    db: Session,
    pedido_id: int,
    usuario: Usuario,
) -> Pedido:
    """Busca o pedido e garante que o usuario pode ve-lo.

    - Cliente: so os proprios pedidos.
    - Restaurante: so os pedidos dos restaurantes dele (restaurante.usuario_id).
    - Entregador e admin: todos.
    """

    pedido = Pedido.buscar_por_id(db, pedido_id)

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido nao encontrado.",
        )

    if not pode_ver_pedido(db, pedido, usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao possui acesso a este pedido.",
        )

    return pedido


def pode_ver_pedido(db: Session, pedido: Pedido, usuario: Usuario) -> bool:
    """Regra de visibilidade do pedido por tipo de usuario."""

    if pedido.cliente_id == usuario.id:
        return True

    if usuario.tipo in ("admin", "entregador"):
        return True

    if usuario.tipo == "restaurante":
        restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
        return restaurante is not None and restaurante.pertence_a(usuario.id)

    return False


def montar_resumo(db: Session, pedido: Pedido) -> PedidoResumoOut:
    """Dados do pedido para as listagens."""

    restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
    itens = ItemPedido.listar_por_pedido(db, pedido.id)
    proximo = status_pedido.proximo_status(pedido.status, pedido.tipo_entrega)

    return PedidoResumoOut(
        id=pedido.id,
        restaurante_id=pedido.restaurante_id,
        restaurante_nome=restaurante.nome_fantasia if restaurante else None,
        status=pedido.status,
        status_rotulo=status_pedido.rotulo(pedido.status),
        tipo_entrega=pedido.tipo_entrega,
        forma_pagamento=pedido.forma_pagamento,
        valor_total=pedido.valor_total,
        quantidade_itens=sum(item.quantidade for item in itens),
        criado_em=pedido.criado_em,
        proximo_status=proximo,
        proximo_status_rotulo=status_pedido.rotulo(proximo) if proximo else None,
        endereco_entrega=pedido.endereco_entrega,
    )


def montar_etapas(
    pedido: Pedido,
    historico: list[PedidoStatusHistorico],
) -> list[EtapaPedidoOut]:
    """Linha do tempo: todas as etapas do fluxo, marcando as ja cumpridas."""

    datas = {registro.status: registro.criado_em for registro in historico}
    datas.setdefault(status_pedido.AGUARDANDO_ACEITE, pedido.criado_em)

    if pedido.status == status_pedido.CANCELADO:
        # Mostra so o que chegou a acontecer e o cancelamento.
        etapas = [registro.status for registro in historico] or [status_pedido.AGUARDANDO_ACEITE]
        if status_pedido.CANCELADO not in etapas:
            etapas.append(status_pedido.CANCELADO)
    else:
        etapas = status_pedido.fluxo(pedido.tipo_entrega)

    posicao_atual = etapas.index(pedido.status) if pedido.status in etapas else -1

    return [
        EtapaPedidoOut(
            status=etapa,
            rotulo=status_pedido.rotulo(etapa),
            concluida=posicao <= posicao_atual,
            atual=posicao == posicao_atual,
            data=datas.get(etapa),
        )
        for posicao, etapa in enumerate(etapas)
    ]


def montar_detalhe(
    db: Session,
    pedido: Pedido,
    usuario: Usuario,
) -> PedidoDetalheOut:
    """Pedido completo para a tela de acompanhamento."""

    resumo = montar_resumo(db, pedido)

    itens_saida: list[ItemPedidoOut] = []
    for item in ItemPedido.listar_por_pedido(db, pedido.id):
        produto = Produto.buscar_por_id(db, item.produto_id)
        itens_saida.append(
            ItemPedidoOut(
                produto_id=item.produto_id,
                nome=produto.nome if produto else f"Produto #{item.produto_id}",
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario,
                subtotal=(item.preco_unitario * item.quantidade).quantize(Decimal("0.01")),
            )
        )

    historico = PedidoStatusHistorico.listar_por_pedido(db, pedido.id)
    entrega = Entrega.obter_ou_criar(db, pedido.id)
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)
    eh_dono = pedido.cliente_id == usuario.id

    return PedidoDetalheOut(
        **resumo.model_dump(),
        cliente_id=pedido.cliente_id,
        entregador_id=entrega.entregador_id,
        taxa_entrega=pedido.taxa_entrega,
        subtotal=pedido.valor_total - pedido.taxa_entrega,
        atualizado_em=pedido.atualizado_em,
        finalizado=status_pedido.status_finalizado(pedido.status),
        itens=itens_saida,
        etapas=montar_etapas(pedido, historico),
        codigo_entrega=entrega.codigo_validacao if eh_dono else None,
        pagamento_status=pagamento.status if pagamento else None,
        nota_fiscal=pedido.cupom_fiscal,
    )


# ------------------------------------------------------------------ rotas


@router.post(
    "",
    response_model=PedidoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Criar pedido a partir da cesta",
)
def criar_pedido(
    dados: PedidoCriarIn,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(exigir_cliente),
) -> Pedido:
    """Fecha a cesta do usuário autenticado e cria o pedido.

    Antes de criar: valida cesta vazia, disponibilidade e quantidade de
    cada item, restaurante aprovado, endereço e raio de entrega. O total
    e a taxa de entrega são calculados aqui (os valores enviados pelo
    front são ignorados). Depois de criar, os itens vão para
    `item_pedido` com o preço do momento e a cesta é esvaziada.

    `tipo_entrega` escolhe entre "delivery" (com taxa pela distância) e
    "retirada" no balcão (sem taxa). O pedido já nasce com o código de
    entrega e o primeiro status da linha do tempo.
    """

    fechamento = preparar_fechamento(
        db,
        usuario_logado,
        dados.local_id,
        dados.tipo_entrega,
    )

    if fechamento.problema is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=fechamento.problema,
        )

    pedido = Pedido.criar_a_partir_da_cesta(
        db,
        cliente_id=usuario_logado.id,
        restaurante_id=fechamento.restaurante.id,
        tipo_entrega=dados.tipo_entrega,
        forma_pagamento=dados.forma_pagamento,
        subtotal=fechamento.subtotal,
        taxa_entrega=fechamento.taxa_entrega,
        itens=[
            (produto.id, item.quantidade, produto.preco)
            for item, produto in fechamento.itens
        ],
        sacola=fechamento.sacola,
        local_entrega=fechamento.local if dados.tipo_entrega == "delivery" else None,
    )
    tarefas.add_task(notificar_pedido_criado, pedido.id)  # push ao cliente e ao restaurante
    return pedido


@router.get(
    "",
    response_model=list[PedidoResumoOut],
    summary="Listar meus pedidos",
)
def listar_meus_pedidos(
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> list[PedidoResumoOut]:
    """Pedidos do usuário logado, do mais recente para o mais antigo."""

    return [
        montar_resumo(db, pedido)
        for pedido in Pedido.listar_por_cliente(db, usuario_logado.id)
    ]


@router.get(
    "/painel",
    response_model=list[PedidoResumoOut],
    summary="Painel de pedidos (restaurante / entregador / admin)",
)
def listar_painel(
    incluir_finalizados: bool = Query(
        default=False,
        description="Inclui pedidos entregues e cancelados.",
    ),
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> list[PedidoResumoOut]:
    """Pedidos em andamento para o restaurante e o entregador movimentarem.

    O restaurante so recebe os pedidos dos restaurantes dele; entregador e
    admin recebem todos.
    """

    exigir_operador(usuario_logado)

    # Restaurante ve so os pedidos dos restaurantes dele.
    dono = usuario_logado.id if usuario_logado.tipo == "restaurante" else None

    return [
        montar_resumo(db, pedido)
        for pedido in Pedido.listar_para_operacao(
            db,
            incluir_finalizados=incluir_finalizados,
            dono_restaurante_id=dono,
        )
    ]


@router.get(
    "/{pedido_id}",
    response_model=PedidoDetalheOut,
    summary="Acompanhar pedido",
)
def obter_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PedidoDetalheOut:
    """Pedido com itens, linha do tempo de status e código de entrega.

    O código de entrega só é devolvido para o próprio cliente.
    """

    pedido = buscar_pedido_visivel(db, pedido_id, usuario_logado)

    return montar_detalhe(db, pedido, usuario_logado)


@router.patch(
    "/{pedido_id}/status",
    response_model=PedidoDetalheOut,
    summary="Alterar status do pedido",
)
def alterar_status_pedido(
    pedido_id: int,
    dados: StatusPedidoIn,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PedidoDetalheOut:
    """Avança o pedido para a próxima etapa (ou cancela).

    Restaurante: aceito, em_preparacao, pronto_para_entrega /
    pronto_para_retirada e cancelado. Entregador: em_transito. Admin: todos.
    Para "entregue" use POST /pedidos/{id}/entrega/confirmar com o código.
    """

    exigir_operador(usuario_logado)
    pedido = buscar_pedido_visivel(db, pedido_id, usuario_logado)

    problema = status_pedido.validar_transicao(
        pedido.status,
        dados.status,
        pedido.tipo_entrega,
        usuario_logado.tipo,
    )

    if problema is None and dados.status == status_pedido.ACEITO:
        pagamento = Pagamento.buscar_por_pedido(db, pedido.id)
        if pagamento is None or not pagamento_regras.permite_aceite(pagamento.metodo, pagamento.status):
            problema = (
                "O pedido so pode ser aceito depois do pagamento aprovado "
                "(ou com pagamento em dinheiro na entrega)."
            )

    if problema is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problema,
        )

    if dados.status == status_pedido.CANCELADO:
        cancelar_pagamento_do_pedido(db, pedido, tarefas)  # estorna ou cancela a cobranca

    pedido.alterar_status(db, dados.status, usuario_id=usuario_logado.id)
    tarefas.add_task(notificar_mudanca_status, pedido.id)  # push a cada mudanca

    return montar_detalhe(db, pedido, usuario_logado)


@router.post(
    "/{pedido_id}/entrega/confirmar",
    response_model=PedidoDetalheOut,
    summary="Confirmar entrega com o código do cliente",
)
def confirmar_entrega(
    pedido_id: int,
    dados: ConfirmarEntregaIn,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PedidoDetalheOut:
    """Conclui o pedido conferindo o código que o cliente informou.

    Delivery: o entregador que saiu com o pedido confere quando ele está
    "em_transito".
    Retirada: o restaurante confere quando está "pronto_para_retirada".
    """

    exigir_operador(usuario_logado)
    pedido = buscar_pedido_visivel(db, pedido_id, usuario_logado)

    problema = status_pedido.validar_confirmacao_entrega(
        pedido.status,
        pedido.tipo_entrega,
        usuario_logado.tipo,
    )

    if problema is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problema,
        )

    entrega = Entrega.obter_ou_criar(db, pedido.id)

    # Delivery: so o entregador que saiu com o pedido (marcou "em_transito")
    # pode concluir.
    if (
        usuario_logado.tipo == "entregador"
        and entrega.entregador_id is not None
        and entrega.entregador_id != usuario_logado.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este pedido esta com outro entregador.",
        )

    if not status_pedido.codigo_confere(entrega.codigo_validacao, dados.codigo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Codigo de entrega incorreto.",
        )

    pedido.alterar_status(db, status_pedido.ENTREGUE, usuario_id=usuario_logado.id)
    receber_pagamento_na_entrega(db, pedido, tarefas)  # dinheiro: vira "aprovado" e emite a NF
    tarefas.add_task(notificar_mudanca_status, pedido.id)

    return montar_detalhe(db, pedido, usuario_logado)


@router.post(
    "/{pedido_id}/cancelar",
    response_model=PedidoDetalheOut,
    summary="Cancelar meu pedido (cliente, enquanto aguarda aceite)",
)
def cancelar_pedido_cliente(
    pedido_id: int,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(exigir_cliente),
) -> PedidoDetalheOut:
    """RN04: o cliente cancela o próprio pedido enquanto ele aguarda o aceite.

    Depois que o restaurante aceita, só o restaurante pode cancelar.
    Se o pedido já estava pago (cartão ou PIX), o valor é estornado no
    Asaas; se o Asaas pedir para esperar, o estorno fica "estorno_pendente"
    e é refeito em segundo plano.
    """

    pedido = Pedido.buscar_por_id(db, pedido_id)

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido nao encontrado.",
        )

    if pedido.cliente_id != usuario_logado.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao possui acesso a este pedido.",
        )

    problema = status_pedido.validar_cancelamento_cliente(pedido.status)

    if problema is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problema,
        )

    cancelar_pagamento_do_pedido(db, pedido, tarefas)
    pedido.alterar_status(db, status_pedido.CANCELADO, usuario_id=usuario_logado.id)
    tarefas.add_task(notificar_cancelamento_cliente, pedido.id)  # avisa cliente e restaurante

    return montar_detalhe(db, pedido, usuario_logado)
