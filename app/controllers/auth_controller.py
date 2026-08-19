"""CONTROLLER — Autenticacao (RF02).

Tarefa da Letícia. Fica aqui porque o CRUD do Geovane depende do login
funcionando para a demonstracao ponta a ponta do video.
"""

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    criar_token_acesso,
    obter_usuario_logado,
    verificar_senha,
)
from app.models.usuario import Usuario
from app.schemas.usuario import LoginRequest, TokenResponse, UsuarioOut


router = APIRouter(prefix="/auth", tags=["Autenticação"])
settings = get_settings()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login por e-mail e senha",
)
def login(
    dados: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica e devolve o JWT."""

    usuario = Usuario.buscar_por_email(db, dados.email)

    if (
        usuario is None
        or usuario.senha_hash is None
        or not verificar_senha(dados.senha, usuario.senha_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    return TokenResponse(
        access_token=criar_token_acesso(usuario),
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.get(
    "/eu",
    response_model=UsuarioOut,
    summary="Dados do usuário logado",
)
def usuario_logado(
    usuario: Usuario = Depends(obter_usuario_logado),
) -> Usuario:
    """Rota protegida."""
    return usuario


@router.get("/google", summary="Login com Google")
def login_google():
    """Inicia o fluxo de autenticação OAuth com Google."""

    state_oauth = secrets.token_urlsafe(32)

    parametros = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_oauth,
        "prompt": "select_account",
    }

    url_google = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(parametros)
    )

    resposta = RedirectResponse(url=url_google)

    resposta.set_cookie(
        key="google_oauth_state",
        value=state_oauth,
        httponly=True,
        samesite="lax",
        max_age=600,
    )

    return resposta


@router.get(
    "/google/callback",
    summary="Callback do login com Google",
)
async def google_callback(
    request: Request,
    code: str | None = None,
    state_oauth: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Recebe o retorno do Google e gera o JWT do EntregaFood."""

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Login com Google cancelado: {error}",
        )

    state_recebido = state or state_oauth
    state_salvo = request.cookies.get("google_oauth_state")

    if not state_salvo or state_recebido != state_salvo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado OAuth inválido.",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de autorização do Google não recebido.",
        )

    async with httpx.AsyncClient() as client:
        resposta_token = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

        if resposta_token.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível obter o token do Google.",
            )

        dados_token = resposta_token.json()
        access_token_google = dados_token.get("access_token")

        if not access_token_google:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google não retornou um access token.",
            )

        resposta_usuario = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={
                "Authorization": f"Bearer {access_token_google}",
            },
        )

        if resposta_usuario.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível consultar o usuário Google.",
            )

        dados_google = resposta_usuario.json()

    email = dados_google.get("email")
    nome = dados_google.get("name")
    email_verificado = dados_google.get("email_verified")

    if not email or not email_verificado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta Google não possui e-mail verificado.",
        )

    usuario = Usuario.buscar_por_email(db, email)

    if usuario is None:
        usuario = Usuario.criar(
            db,
            nome=nome or email.split("@")[0],
            email=email,
            senha_hash=None,
            telefone=None,
            tipo="cliente",
            oauth_provider="google",
        )

    token_entregafood = criar_token_acesso(usuario)

    resposta = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/#oauth_token={token_entregafood}"
    )

    resposta.delete_cookie("google_oauth_state")

    return resposta


@router.get("/facebook", summary="Login com Facebook")
def login_facebook():
    """Inicia o fluxo de autenticação OAuth com Facebook."""

    state_oauth = secrets.token_urlsafe(32)

    parametros = {
        "client_id": settings.FACEBOOK_APP_ID,
        "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": "public_profile,email",
        "state": state_oauth,
    }

    url_facebook = (
        "https://www.facebook.com/dialog/oauth?"
        + urlencode(parametros)
    )

    resposta = RedirectResponse(url=url_facebook)

    resposta.set_cookie(
        key="facebook_oauth_state",
        value=state_oauth,
        httponly=True,
        samesite="lax",
        max_age=600,
    )

    return resposta


@router.get(
    "/facebook/callback",
    summary="Callback do login com Facebook",
)
async def facebook_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Recebe o retorno do Facebook e gera o JWT do EntregaFood."""

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Login com Facebook cancelado: {error}",
        )

    state_salvo = request.cookies.get("facebook_oauth_state")

    if not state_salvo or state != state_salvo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado OAuth inválido.",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de autorização do Facebook não recebido.",
        )

    async with httpx.AsyncClient() as client:
        resposta_token = await client.get(
            "https://graph.facebook.com/oauth/access_token",
            params={
                "client_id": settings.FACEBOOK_APP_ID,
                "client_secret": settings.FACEBOOK_APP_SECRET,
                "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
                "code": code,
            },
        )

        if resposta_token.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível obter o token do Facebook.",
            )

        dados_token = resposta_token.json()
        access_token_facebook = dados_token.get("access_token")

        if not access_token_facebook:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facebook não retornou um access token.",
            )

        resposta_usuario = await client.get(
            "https://graph.facebook.com/me",
            params={
                "fields": "id,name,email",
                "access_token": access_token_facebook,
            },
        )

        if resposta_usuario.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível consultar o usuário Facebook.",
            )

        dados_facebook = resposta_usuario.json()

    email = dados_facebook.get("email")
    nome = dados_facebook.get("name")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta Facebook não forneceu um endereço de e-mail.",
        )

    usuario = Usuario.buscar_por_email(db, email)

    if usuario is None:
        usuario = Usuario.criar(
            db,
            nome=nome or email.split("@")[0],
            email=email,
            senha_hash=None,
            telefone=None,
            tipo="cliente",
            oauth_provider="facebook",
        )

    token_entregafood = criar_token_acesso(usuario)

    resposta = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/#oauth_token={token_entregafood}"
    )

    resposta.delete_cookie("facebook_oauth_state")

    return resposta