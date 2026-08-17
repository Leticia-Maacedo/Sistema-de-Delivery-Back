"""CONTROLLER — Produto.

As quatro operacoes do CRUD, uma por verbo HTTP:
    CREATE  ->  POST   /produtos
    READ    ->  GET    /produtos  e  GET /produtos/{id}
    UPDATE  ->  PUT    /produtos/{id}
    DELETE  ->  DELETE /produtos/{id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.schemas.produto import ProdutoCreate, ProdutoOut, ProdutoUpdate

router = APIRouter(prefix="/produtos", tags=["Produtos"])


# ---------------------------------------------------------------- CREATE
@router.post("", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED, summary="Cadastrar produto")
def criar_produto(dados: ProdutoCreate, db: Session = Depends(get_db)) -> Produto:
    if Restaurante.buscar_por_id(db, dados.restaurante_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Restaurante informado não existe.",
        )
    return Produto.criar(
        db,
        restaurante_id=dados.restaurante_id,
        nome=dados.nome,
        descricao=dados.descricao,
        preco=dados.preco,
        disponivel=dados.disponivel,
    )


# ------------------------------------------------------------------ READ
@router.get("", response_model=list[ProdutoOut], summary="Listar produtos")
def listar_produtos(
    restaurante_id: int | None = Query(default=None, description="Filtra por restaurante"),
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Produto]:
    return Produto.listar(db, restaurante_id=restaurante_id, limite=limite, pular=pular)


@router.get("/{produto_id}", response_model=ProdutoOut, summary="Consultar produto")
def obter_produto(produto_id: int, db: Session = Depends(get_db)) -> Produto:
    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return produto


# ---------------------------------------------------------------- UPDATE
@router.put("/{produto_id}", response_model=ProdutoOut, summary="Alterar produto")
def atualizar_produto(produto_id: int, dados: ProdutoUpdate, db: Session = Depends(get_db)) -> Produto:
    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return produto.atualizar(db, **dados.model_dump(exclude_unset=True))


# ---------------------------------------------------------------- DELETE
@router.delete("/{produto_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remover produto")
def remover_produto(produto_id: int, db: Session = Depends(get_db)) -> None:
    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    produto.remover(db)
