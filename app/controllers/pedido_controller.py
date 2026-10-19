"""Controller de Pedido do EntregaFood."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers.sacola_controller import preparar_fechamento
from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.schemas.pedido import PedidoCriarIn, PedidoOut


router = APIRouter(prefix="/pedidos", tags=["Pedido"])


@router.post(
    "",
    response_model=PedidoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Criar pedido a partir da cesta",
)
def criar_pedido(
    dados: PedidoCriarIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Pedido:
    """Fecha a cesta do usuário autenticado e cria o pedido.

    Antes de criar: valida cesta vazia, disponibilidade e quantidade de
    cada item, restaurante aprovado, endereço e raio de entrega. O total
    e a taxa de entrega são calculados aqui (os valores enviados pelo
    front são ignorados). Depois de criar, os itens vão para
    `item_pedido` com o preço do momento e a cesta é esvaziada.
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

    return Pedido.criar_a_partir_da_cesta(
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
    )
