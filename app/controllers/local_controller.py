"""CONTROLLER — Local.

So a operacao de CREATE: e o minimo necessario pra desbloquear o
cadastro de Restaurante (que exige um local_id valido). Nao faz parte
do escopo desta entrega ter edicao/exclusao de Local.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.local import Local
from app.schemas.local import LocalCreate, LocalOut

router = APIRouter(prefix="/locais", tags=["Locais"])


@router.post("", response_model=LocalOut, status_code=status.HTTP_201_CREATED, summary="Cadastrar local")
def criar_local(dados: LocalCreate, db: Session = Depends(get_db)) -> Local:
    return Local.criar(
        db,
        usuario_id=dados.usuario_id,
        endereco=dados.endereco,
        tipo=dados.tipo,
        latitude=dados.latitude,
        longitude=dados.longitude,
    )
