"""CONTROLLER — Consultas do cliente (Sprint 2).

Endpoints de *leitura* voltados a quem usa o app pra pedir comida —
distintos do CRUD de administracao em `restaurante_controller.py` e
`produto_controller.py`:

    GET /consultas/restaurantes                  -> restaurantes aprovados (com ?busca=)
    GET /consultas/restaurantes/{id}             -> detalhe de um restaurante aprovado
    GET /consultas/restaurantes/{id}/cardapio    -> restaurante + itens disponiveis

Regras de visibilidade:
    - so aparece restaurante com status_aprovacao = 'aprovado';
    - no cardapio, so item com disponivel = true.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.schemas.consulta import CardapioOut, RestauranteConsultaOut

router = APIRouter(prefix="/consultas", tags=["Consultas (Cliente)"])


@router.get(
    "/restaurantes",
    response_model=list[RestauranteConsultaOut],
    summary="Consultar restaurantes disponiveis",
)
def consultar_restaurantes(
    busca: str | None = Query(default=None, description="Filtra por trecho do nome fantasia"),
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Restaurante]:
    return Restaurante.listar_aprovados(db, busca=busca, limite=limite, pular=pular)


@router.get(
    "/restaurantes/{restaurante_id}",
    response_model=RestauranteConsultaOut,
    summary="Consultar um restaurante",
)
def consultar_restaurante(restaurante_id: int, db: Session = Depends(get_db)) -> Restaurante:
    restaurante = Restaurante.buscar_aprovado_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurante nao encontrado ou indisponivel.",
        )
    return restaurante


@router.get(
    "/restaurantes/{restaurante_id}/cardapio",
    response_model=CardapioOut,
    summary="Consultar o cardapio de um restaurante",
)
def consultar_cardapio(restaurante_id: int, db: Session = Depends(get_db)) -> CardapioOut:
    restaurante = Restaurante.buscar_aprovado_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurante nao encontrado ou indisponivel.",
        )
    itens = Produto.listar_disponiveis(db, restaurante_id)
    return CardapioOut(
        restaurante=RestauranteConsultaOut.model_validate(restaurante),
        total_itens=len(itens),
        itens=itens,
    )
