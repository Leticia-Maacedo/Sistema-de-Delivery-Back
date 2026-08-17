"""CONTROLLER — Restaurante.

As quatro operacoes do CRUD, uma por verbo HTTP:
    CREATE  ->  POST   /restaurantes
    READ    ->  GET    /restaurantes  e  GET /restaurantes/{id}
    UPDATE  ->  PUT    /restaurantes/{id}
    DELETE  ->  DELETE /restaurantes/{id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.restaurante import Restaurante
from app.schemas.restaurante import RestauranteCreate, RestauranteOut, RestauranteUpdate

router = APIRouter(prefix="/restaurantes", tags=["Restaurantes"])


# ---------------------------------------------------------------- CREATE
@router.post("", response_model=RestauranteOut, status_code=status.HTTP_201_CREATED, summary="Cadastrar restaurante")
def criar_restaurante(dados: RestauranteCreate, db: Session = Depends(get_db)) -> Restaurante:
    if Restaurante.cnpj_ja_cadastrado(db, dados.cnpj):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um restaurante cadastrado com este CNPJ.",
        )
    return Restaurante.criar(
        db,
        local_id=dados.local_id,
        nome_fantasia=dados.nome_fantasia,
        cnpj=dados.cnpj,
        taxa_entrega_km=dados.taxa_entrega_km,
    )


# ------------------------------------------------------------------ READ
@router.get("", response_model=list[RestauranteOut], summary="Listar restaurantes")
def listar_restaurantes(
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Restaurante]:
    return Restaurante.listar(db, limite=limite, pular=pular)


@router.get("/{restaurante_id}", response_model=RestauranteOut, summary="Consultar restaurante")
def obter_restaurante(restaurante_id: int, db: Session = Depends(get_db)) -> Restaurante:
    restaurante = Restaurante.buscar_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurante não encontrado.")
    return restaurante


# ---------------------------------------------------------------- UPDATE
@router.put("/{restaurante_id}", response_model=RestauranteOut, summary="Alterar restaurante")
def atualizar_restaurante(
    restaurante_id: int, dados: RestauranteUpdate, db: Session = Depends(get_db)
) -> Restaurante:
    restaurante = Restaurante.buscar_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurante não encontrado.")

    if dados.cnpj and Restaurante.cnpj_ja_cadastrado(db, dados.cnpj, ignorar_id=restaurante_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este CNPJ já pertence a outro restaurante.",
        )

    return restaurante.atualizar(db, **dados.model_dump(exclude_unset=True))


# ---------------------------------------------------------------- DELETE
@router.delete("/{restaurante_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remover restaurante")
def remover_restaurante(restaurante_id: int, db: Session = Depends(get_db)) -> None:
    restaurante = Restaurante.buscar_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurante não encontrado.")
    restaurante.remover(db)
