"""Controller de Pedido do EntregaFood."""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

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
    summary="Criar pedido",
)
def criar_pedido(
    dados: PedidoCriarIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Pedido:
    """Cria um pedido para o usuário autenticado."""

    pedido = Pedido(
        cliente_id=usuario_logado.id,
        restaurante_id=dados.restaurante_id,
        entregador_id=None,
        status="aguardando_aceite",
        tipo_entrega=dados.tipo_entrega,
        forma_pagamento=dados.forma_pagamento,
        valor_total=dados.valor_total,
        taxa_entrega=dados.taxa_entrega,
        cupom_fiscal=None,
        criado_em=datetime.now(),
        atualizado_em=None,
    )

    db.add(pedido)
    db.commit()
    db.refresh(pedido)

    return pedido