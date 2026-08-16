"""CONTROLLER — Usuario.

Camada Controller do MVC: recebe a requisicao HTTP, chama o Model e
devolve a resposta no formato definido pela View (schemas Pydantic).

As quatro operacoes do CRUD estao aqui, uma por verbo HTTP:
    CREATE  ->  POST   /usuarios
    READ    ->  GET    /usuarios  e  GET /usuarios/{id}
    UPDATE  ->  PUT    /usuarios/{id}
    DELETE  ->  DELETE /usuarios/{id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import gerar_hash_senha
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioOut, UsuarioUpdate

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


# ---------------------------------------------------------------- CREATE
@router.post(
    "",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar usuário (RF01)",
)
def criar_usuario(dados: UsuarioCreate, db: Session = Depends(get_db)) -> Usuario:
    """Cria um usuário. Cobre o caso de teste CT01.

    Devolve 409 se o e-mail já existir — é o caso de teste CT04.
    """
    if Usuario.email_ja_cadastrado(db, dados.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma conta cadastrada com este e-mail.",
        )

    if not Usuario.tipo_e_valido(dados.tipo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de usuário inválido.",
        )

    return Usuario.criar(
        db,
        nome=dados.nome,
        email=dados.email,
        senha_hash=gerar_hash_senha(dados.senha),
        telefone=dados.telefone,
        tipo=dados.tipo,
    )


# ------------------------------------------------------------------ READ
@router.get("", response_model=list[UsuarioOut], summary="Listar usuários")
def listar_usuarios(
    tipo: str | None = Query(default=None, description="Filtra por perfil"),
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Usuario]:
    return Usuario.listar(db, tipo=tipo, limite=limite, pular=pular)


@router.get("/{usuario_id}", response_model=UsuarioOut, summary="Consultar usuário")
def obter_usuario(usuario_id: int, db: Session = Depends(get_db)) -> Usuario:
    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )
    return usuario


# ---------------------------------------------------------------- UPDATE
@router.put("/{usuario_id}", response_model=UsuarioOut, summary="Alterar usuário")
def atualizar_usuario(
    usuario_id: int, dados: UsuarioUpdate, db: Session = Depends(get_db)
) -> Usuario:
    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )

    if dados.email and Usuario.email_ja_cadastrado(db, dados.email, ignorar_id=usuario_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já pertence a outra conta.",
        )

    return usuario.atualizar(db, **dados.model_dump(exclude_unset=True))


# ---------------------------------------------------------------- DELETE
@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerrar conta (RF06)",
)
def remover_usuario(usuario_id: int, db: Session = Depends(get_db)) -> None:
    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )
    usuario.remover(db)
