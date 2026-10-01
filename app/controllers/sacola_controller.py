"""Controller da cesta de compras do EntregaFood."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.produto import Produto
from app.models.sacola import ItemSacola, Sacola
from app.models.usuario import Usuario
from app.schemas.sacola import (
    ItemSacolaAdicionar,
    ItemSacolaOut,
    ItemSacolaQuantidade,
    SacolaOut,
)

router = APIRouter(prefix="/cesta", tags=["Cesta"])


def montar_resposta_cesta(
    db: Session,
    sacola: Sacola,
) -> SacolaOut:
    """Monta a resposta completa da cesta."""

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

    return montar_resposta_cesta(db, sacola)


@router.post(
    "/itens",
    response_model=SacolaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar produto a cesta",
)
def adicionar_produto_cesta(
    dados: ItemSacolaAdicionar,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Adiciona um produto a cesta do usuario autenticado."""

    produto = Produto.buscar_por_id(db, dados.produto_id)

    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado.",
        )

    if not produto.disponivel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto indisponivel.",
        )

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        sacola = Sacola(
            cliente_id=usuario_logado.id,
            criado_em=datetime.now(),
            atualizado_em=None,
        )

        db.add(sacola)
        db.commit()
        db.refresh(sacola)

    item_existente = ItemSacola.buscar_por_produto(
        db,
        sacola.id,
        produto.id,
    )

    if item_existente is not None:
        item_existente.quantidade += dados.quantidade
        sacola.atualizado_em = datetime.now()

        db.commit()
        db.refresh(item_existente)
        db.refresh(sacola)

    else:
        ItemSacola.adicionar(
            db,
            sacola_id=sacola.id,
            produto_id=produto.id,
            quantidade=dados.quantidade,
        )

        sacola.atualizado_em = datetime.now()
        db.commit()
        db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)


@router.put(
    "/itens/{produto_id}",
    response_model=SacolaOut,
    summary="Alterar quantidade de produto da cesta",
)
def alterar_quantidade_cesta(
    produto_id: int,
    dados: ItemSacolaQuantidade,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Altera a quantidade de um produto da cesta do usuario autenticado."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cesta nao encontrada.",
        )

    item = ItemSacola.buscar_por_produto(
        db,
        sacola.id,
        produto_id,
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado na cesta.",
        )

    item.quantidade = dados.quantidade
    sacola.atualizado_em = datetime.now()

    db.commit()
    db.refresh(item)
    db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)


@router.delete(
    "/itens/{produto_id}",
    response_model=SacolaOut,
    summary="Excluir produto da cesta",
)
def excluir_produto_cesta(
    produto_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Exclui um produto da cesta do usuario autenticado."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cesta nao encontrada.",
        )

    item = ItemSacola.buscar_por_produto(
        db,
        sacola.id,
        produto_id,
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado na cesta.",
        )

    item.remover(db)

    sacola.atualizado_em = datetime.now()
    db.commit()
    db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)