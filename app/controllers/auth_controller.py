"""CONTROLLER — Autenticacao (RF02).

Tarefa da Letícia. Fica aqui porque o CRUD do Geovane depende do login
funcionando para a demonstracao ponta a ponta do video.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import criar_token_acesso, obter_usuario_logado, verificar_senha
from app.models.usuario import Usuario
from app.schemas.usuario import LoginRequest, TokenResponse, UsuarioOut

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse, summary="Login por e-mail e senha")
def login(dados: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Autentica e devolve o JWT. Credencial invalida retorna 401 (caso de teste CT02)."""
    usuario = Usuario.buscar_por_email(db, dados.email)

    # Mensagem generica de proposito: nao revela se o e-mail existe.
    if usuario is None or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    return TokenResponse(
        access_token=criar_token_acesso(usuario),
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.get("/eu", response_model=UsuarioOut, summary="Dados do usuário logado")
def usuario_logado(usuario: Usuario = Depends(obter_usuario_logado)) -> Usuario:
    """Rota protegida — serve para provar no video que o middleware funciona."""
    return usuario
