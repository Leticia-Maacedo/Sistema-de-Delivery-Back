"""CONTROLLER — Produto.

As quatro operacoes do CRUD, uma por verbo HTTP:
    CREATE  ->  POST   /produtos
    READ    ->  GET    /produtos  e  GET /produtos/{id}
    UPDATE  ->  PUT    /produtos/{id}
    DELETE  ->  DELETE /produtos/{id}

Estoque (Sprint 4):
    GET   /produtos/{id}/estoque  consulta (publica)
    PUT   /produtos/{id}/estoque  define a contagem (null desliga o controle)
    PATCH /produtos/{id}/estoque  entrada (+) ou saida (-) de unidades

A leitura e publica (o cardapio e aberto). Cadastrar, alterar e remover
exigem login do dono do restaurante ou do admin.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario
from app.schemas.produto import (
    EstoqueAjusteIn,
    EstoqueDefinirIn,
    EstoqueOut,
    ProdutoCreate,
    ProdutoOut,
    ProdutoUpdate,
)

router = APIRouter(prefix="/produtos", tags=["Produtos"])


def _exigir_dono(restaurante: Restaurante, usuario: Usuario) -> None:
    if usuario.tipo != "admin" and restaurante.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente o dono do restaurante altera o cardápio.",
        )


def _buscar_produto_do_usuario(db: Session, produto_id: int, usuario: Usuario) -> Produto:
    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    _exigir_dono(Restaurante.buscar_por_id(db, produto.restaurante_id), usuario)
    return produto


# ---------------------------------------------------------------- CREATE
@router.post("", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED, summary="Cadastrar produto")
def criar_produto(
    dados: ProdutoCreate,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Produto:
    restaurante = Restaurante.buscar_por_id(db, dados.restaurante_id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Restaurante informado não existe.",
        )
    _exigir_dono(restaurante, usuario_logado)
    return Produto.criar(
        db,
        restaurante_id=dados.restaurante_id,
        nome=dados.nome,
        descricao=dados.descricao,
        preco=dados.preco,
        disponivel=dados.disponivel,
        estoque=dados.estoque,
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
def atualizar_produto(
    produto_id: int,
    dados: ProdutoUpdate,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Produto:
    produto = _buscar_produto_do_usuario(db, produto_id, usuario_logado)
    campos = dados.model_dump(exclude_unset=True)
    if "estoque" in campos:
        produto.estoque = campos.pop("estoque")  # null desliga o controle
    return produto.atualizar(db, **campos)


# ---------------------------------------------------------------- DELETE
@router.delete("/{produto_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remover produto")
def remover_produto(
    produto_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> None:
    produto = _buscar_produto_do_usuario(db, produto_id, usuario_logado)
    produto.remover(db)


# --------------------------------------------------------------- ESTOQUE
def _estoque_out(produto: Produto) -> EstoqueOut:
    return EstoqueOut(
        produto_id=produto.id,
        nome=produto.nome,
        disponivel=produto.disponivel,
        controla_estoque=produto.controla_estoque,
        estoque=produto.estoque,
        esgotado=produto.esgotado,
    )


@router.get("/{produto_id}/estoque", response_model=EstoqueOut, summary="Consultar estoque do produto")
def consultar_estoque(produto_id: int, db: Session = Depends(get_db)) -> EstoqueOut:
    """Unidades em estoque. `controla_estoque = false` = vende sem limite."""

    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return _estoque_out(produto)


@router.put("/{produto_id}/estoque", response_model=EstoqueOut, summary="Definir estoque do produto")
def definir_estoque(
    produto_id: int,
    dados: EstoqueDefinirIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> EstoqueOut:
    """Contagem do estoque (substitui o valor). `estoque: null` desliga o controle.

    Só o dono do restaurante ou o admin.
    """

    produto = _buscar_produto_do_usuario(db, produto_id, usuario_logado)
    return _estoque_out(produto.definir_estoque(db, dados.estoque))


@router.patch("/{produto_id}/estoque", response_model=EstoqueOut, summary="Entrada ou saída de estoque")
def ajustar_estoque(
    produto_id: int,
    dados: EstoqueAjusteIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> EstoqueOut:
    """Soma (entrada) ou subtrai (saída) unidades sem deixar o estoque negativo.

    Só o dono do restaurante ou o admin. O produto precisa controlar
    estoque (defina um valor antes com PUT).
    """

    produto = _buscar_produto_do_usuario(db, produto_id, usuario_logado)

    if dados.ajuste == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe um ajuste diferente de zero.")
    if not produto.controla_estoque:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este produto não controla estoque. Defina a quantidade antes (PUT).",
        )
    if not produto.ajustar_estoque(db, dados.ajuste):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Saída maior que o estoque atual ({produto.estoque} unidades).",
        )
    return _estoque_out(produto)
