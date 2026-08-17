"""CONTROLLER — Usuario.

Camada Controller do MVC: recebe a requisicao HTTP, chama o Model e
devolve a resposta no formato definido pela View (schemas Pydantic).

As quatro operacoes do CRUD estao aqui, uma por verbo HTTP:
    CREATE  ->  POST   /usuarios
    READ    ->  GET    /usuarios  e  GET /usuarios/{id}
    UPDATE  ->  PUT    /usuarios/{id}
    DELETE  ->  DELETE /usuarios/{id}

Autorizacao: listar todo mundo e' coisa de admin. Consultar, editar e
excluir um usuario especifico e' permitido pro proprio dono da conta
ou por um admin — e' o que sustenta tanto a tela "Meu Perfil" (o
usuario mexe na propria conta) quanto o painel de administracao (o
admin mexe na conta de qualquer um).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import gerar_hash_senha, obter_usuario_logado
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioOut, UsuarioUpdate

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


def _exigir_dono_ou_admin(usuario_id: int, usuario_logado: Usuario) -> None:
    if usuario_logado.tipo != "admin" and usuario_logado.id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode gerenciar a sua própria conta.",
        )


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

    if dados.tipo == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta admin não pode ser criada por autocadastro.",
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
@router.get("", response_model=list[UsuarioOut], summary="Listar usuários (admin)")
def listar_usuarios(
    tipo: str | None = Query(default=None, description="Filtra por perfil"),
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> list[Usuario]:
    if usuario_logado.tipo != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem listar todos os usuários.",
        )
    return Usuario.listar(db, tipo=tipo, limite=limite, pular=pular)


@router.get("/{usuario_id}", response_model=UsuarioOut, summary="Consultar usuário")
def obter_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Usuario:
    _exigir_dono_ou_admin(usuario_id, usuario_logado)
    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )
    return usuario


# ---------------------------------------------------------------- UPDATE
@router.put("/{usuario_id}", response_model=UsuarioOut, summary="Alterar usuário")
def atualizar_usuario(
    usuario_id: int,
    dados: UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Usuario:
    _exigir_dono_ou_admin(usuario_id, usuario_logado)

    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )

    if dados.tipo and usuario_logado.tipo != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Só um administrador pode alterar o tipo de conta.",
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
def remover_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> None:
    _exigir_dono_ou_admin(usuario_id, usuario_logado)
    usuario = Usuario.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado."
        )
    usuario.remover(db)
