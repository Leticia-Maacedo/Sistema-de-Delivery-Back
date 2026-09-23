"""CONTROLLER — Local.

CRUD de locais/enderecos do EntregaFood.
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.geocoding import geocodificar_endereco
from app.models.local import Local
from app.schemas.local import (
    LocalCreate,
    LocalOut,
    LocalUpdate,
)

router = APIRouter(
    prefix="/locais",
    tags=["Locais"],
)


@router.post(
    "",
    response_model=LocalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar local",
)
def criar_local(
    dados: LocalCreate,
    db: Session = Depends(get_db),
) -> Local:
    latitude = dados.latitude
    longitude = dados.longitude

    # Sem coordenadas explicitas (ex.: alguem chamando so com endereco
    # pelo Swagger) -> geocodifica sozinho via Nominatim. O front hoje
    # ja calcula e manda lat/lng prontos, entao na pratica isso so entra
    # em acao quando ninguem mandou.
    if latitude is None or longitude is None:
        latitude, longitude = geocodificar_endereco(dados.endereco)

    return Local.criar(
        db,
        usuario_id=dados.usuario_id,
        endereco=dados.endereco,
        tipo=dados.tipo,
        latitude=latitude,
        longitude=longitude,
    )


@router.get(
    "",
    response_model=list[LocalOut],
    summary="Listar locais",
)
def listar_locais(
    usuario_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Local]:
    return Local.listar(
        db,
        usuario_id=usuario_id,
    )


@router.get(
    "/{local_id}",
    response_model=LocalOut,
    summary="Consultar local",
)
def obter_local(
    local_id: int,
    db: Session = Depends(get_db),
) -> Local:
    local = Local.buscar_por_id(
        db,
        local_id,
    )

    if local is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local nao encontrado.",
        )

    return local


@router.put(
    "/{local_id}",
    response_model=LocalOut,
    summary="Atualizar local",
)
def atualizar_local(
    local_id: int,
    dados: LocalUpdate,
    db: Session = Depends(get_db),
) -> Local:
    local = Local.buscar_por_id(
        db,
        local_id,
    )

    if local is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local nao encontrado.",
        )

    alteracoes = dados.model_dump(
        exclude_unset=True
    )

    # Endereco mudou mas ninguem mandou coordenada nova junto -> as
    # coordenadas antigas ficariam erradas. Regeocodifica.
    endereco_novo = alteracoes.get("endereco")
    if endereco_novo and "latitude" not in alteracoes and "longitude" not in alteracoes:
        alteracoes["latitude"], alteracoes["longitude"] = geocodificar_endereco(
            endereco_novo
        )

    return local.atualizar(
        db,
        **alteracoes,
    )


@router.delete(
    "/{local_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir local",
)
def excluir_local(
    local_id: int,
    db: Session = Depends(get_db),
) -> Response:
    local = Local.buscar_por_id(
        db,
        local_id,
    )

    if local is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local nao encontrado.",
        )

    local.excluir(db)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )