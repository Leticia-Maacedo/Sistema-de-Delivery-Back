"""CONTROLLER — Login social (Google e Facebook).

Fluxo: o front redireciona o navegador para /auth/{provedor}/login, o
provedor autentica o usuario e volta para /auth/{provedor}/callback, que
cria (ou reaproveita) a conta e devolve o usuario para o front com o
nosso proprio JWT na URL.
"""
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import criar_token_acesso
from app.models.usuario import Usuario

router = APIRouter(prefix="/auth", tags=["Login social"])

settings = get_settings()
oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="facebook",
    client_id=settings.FACEBOOK_APP_ID,
    client_secret=settings.FACEBOOK_APP_SECRET,
    access_token_url="https://graph.facebook.com/oauth/access_token",
    authorize_url="https://www.facebook.com/dialog/oauth",
    api_base_url="https://graph.facebook.com/",
    client_kwargs={"scope": "email public_profile"},
)


def _login_social(db: Session, *, nome: str, email: str | None, provider: str) -> RedirectResponse:
    if not email:
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/?oauth_erro=Nao foi possivel obter seu e-mail do {provider}."
        )
    usuario = Usuario.buscar_ou_criar_por_oauth(db, nome=nome, email=email, provider=provider)
    token = criar_token_acesso(usuario)
    return RedirectResponse(f"{settings.FRONTEND_URL}/?oauth_token={token}")


@router.get("/google/login", summary="Inicia o login com Google")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback", summary="Callback do Google")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as erro:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(erro)) from erro

    userinfo = token.get("userinfo") or {}
    return _login_social(
        db, nome=userinfo.get("name", ""), email=userinfo.get("email"), provider="google"
    )


@router.get("/facebook/login", summary="Inicia o login com Facebook")
async def facebook_login(request: Request):
    redirect_uri = request.url_for("facebook_callback")
    return await oauth.facebook.authorize_redirect(request, redirect_uri)


@router.get("/facebook/callback", name="facebook_callback", summary="Callback do Facebook")
async def facebook_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.facebook.authorize_access_token(request)
        resposta = await oauth.facebook.get("me?fields=id,name,email", token=token)
        perfil = resposta.json()
    except Exception as erro:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(erro)) from erro

    return _login_social(
        db, nome=perfil.get("name", ""), email=perfil.get("email"), provider="facebook"
    )
