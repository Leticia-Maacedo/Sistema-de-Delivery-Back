"""Controller da cesta de compras do EntregaFood."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.produto import Produto
from app.models.sacola import ItemSacola, Sacola
from app.models.usuario import Usuario
from app.schemas.sacola import ItemSacolaOut, SacolaOut

router = APIRouter(prefix="/cesta", tags=["Cesta"])


@router.get(
    "",
    response_model=SacolaOut,
    summary="Consultar cesta do usuario logado",
)
def consultar_cesta(
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Consulta a cesta e os itens do usuario autenticado."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        return SacolaOut(
            id=None,
            cliente_id=usuario_logado.id,
            criado_em=None,
            atualizado_em=None,
            itens=[],
            total=Decimal("0.00"),
        )

    itens_saida: list[ItemSacolaOut] = []
    total = Decimal("0.00")

    for item in ItemSacola.listar_por_sacola(db, sacola.id):
        produto = Produto.buscar_por_id(db, item.produto_id)

        if produto is None:
            continue

        subtotal = produto.preco * item.quantidade
        total += subtotal

        itens_saida.append(
            ItemSacolaOut(
                id=item.id,
                produto_id=produto.id,
                nome=produto.nome,
                quantidade=item.quantidade,
                preco_unitario=produto.preco,
                subtotal=subtotal,
            )
        )

    return SacolaOut(
        id=sacola.id,
        cliente_id=sacola.cliente_id,
        criado_em=sacola.criado_em,
        atualizado_em=sacola.atualizado_em,
        itens=itens_saida,
        total=total,
    )
