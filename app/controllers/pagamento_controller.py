"""Controller de pagamento do EntregaFood."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagamento_cartao import processar_pagamento_cartao
from app.core.security import obter_usuario_logado
from app.models.pagamento import Pagamento
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.schemas.pagamento import (
    EscolhaPagamentoIn,
    PagamentoCartaoIn,
    PagamentoOut,
)

router = APIRouter(prefix="/pagamentos", tags=["Pagamento"])


def buscar_pedido_do_usuario(
    db: Session,
    pedido_id: int,
    usuario_logado: Usuario,
) -> Pedido:
    """Busca o pedido e garante que ele pertence ao usuario autenticado."""

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

    return pedido


@router.put(
    "/pedidos/{pedido_id}/metodo",
    summary="Escolher tipo de pagamento",
)
def escolher_tipo_pagamento(
    pedido_id: int,
    dados: EscolhaPagamentoIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> dict[str, str | int]:
    """Define o tipo de pagamento escolhido para o pedido."""

    pedido = buscar_pedido_do_usuario(
        db,
        pedido_id,
        usuario_logado,
    )

    pedido.definir_forma_pagamento(
        db,
        dados.metodo,
    )

    return {
        "pedido_id": pedido.id,
        "metodo": pedido.forma_pagamento,
        "mensagem": "Tipo de pagamento definido com sucesso.",
    }


@router.post(
    "/cartao",
    response_model=PagamentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Processar pagamento por cartao",
)
def pagar_com_cartao(
    dados: PagamentoCartaoIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Pagamento:
    """Processa o pagamento por cartao de um pedido.

    O servico de cartao utilizado nesta entrega e simulado.
    Nenhum numero de cartao, CVV ou senha e armazenado pelo backend.
    """

    pedido = buscar_pedido_do_usuario(
        db,
        dados.pedido_id,
        usuario_logado,
    )

    if pedido.forma_pagamento != "cartao":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O tipo de pagamento do pedido deve ser cartao.",
        )

    pagamento_existente = Pagamento.buscar_por_pedido(
        db,
        pedido.id,
    )

    if pagamento_existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido ja possui um pagamento.",
        )

    resultado = processar_pagamento_cartao(
        valor=pedido.valor_total,
    )

    pagamento = Pagamento.criar(
        db,
        pedido_id=pedido.id,
        metodo="cartao",
        valor=pedido.valor_total,
        status=resultado.status,
        transacao_externa_id=resultado.transacao_externa_id,
    )

    return pagamento