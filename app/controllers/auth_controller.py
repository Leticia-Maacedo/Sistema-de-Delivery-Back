"""CONTROLLER — Autenticacao (RF02).

Tarefa da Leticia. Fica aqui porque o CRUD do Geovane depende do login
funcionando para a demonstracao ponta a ponta do video.
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    criar_token_acesso,
    gerar_hash_senha,
    obter_usuario_logado,
    verificar_senha,
)
from app.models.codigo_otp import CodigoOTP
from app.models.usuario import Usuario
from app.schemas.usuario import (
    CadastroTelefoneRequest,
    ConfirmarCadastroTelefoneRequest,
    LoginRequest,
    OTPResponse,
    SolicitarOTPRequest,
    TokenResponse,
    UsuarioOut,
    VerificarOTPRequest,
)


router = APIRouter(prefix="/auth", tags=["Autenticação"])
settings = get_settings()


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_telefone(telefone: str) -> str:
    """Mantém apenas os números do telefone."""
    return "".join(filter(str.isdigit, telefone))


def _chave_oauth() -> bytes:
    """Obtém a chave usada para assinar o state OAuth."""
    return settings.JWT_SECRET.encode("utf-8")


def criar_state_oauth() -> str:
    """
    Cria um state OAuth assinado.

    O state contém:
      - nonce aleatório
      - timestamp
      - assinatura HMAC

    Assim não dependemos de cookie para validar o retorno do OAuth.
    """

    nonce = secrets.token_urlsafe(32)
    timestamp = str(int(time.time()))

    mensagem = f"{nonce}.{timestamp}".encode("utf-8")

    assinatura = hmac.new(
        _chave_oauth(),
        mensagem,
        hashlib.sha256,
    ).digest()

    assinatura_b64 = base64.urlsafe_b64encode(
        assinatura
    ).decode("utf-8").rstrip("=")

    return f"{nonce}.{timestamp}.{assinatura_b64}"


def validar_state_oauth(state: str | None) -> bool:
    """
    Valida o state recebido pelo provedor OAuth.

    O state:
      - precisa existir;
      - precisa possuir formato correto;
      - precisa ter no máximo 10 minutos;
      - precisa possuir assinatura válida.
    """

    if not state:
        return False

    try:
        partes = state.split(".")

        if len(partes) != 3:
            return False

        nonce, timestamp_str, assinatura_recebida = partes

        if not nonce or not timestamp_str or not assinatura_recebida:
            return False

        timestamp = int(timestamp_str)

        agora = int(time.time())

        # Estado válido por no máximo 10 minutos.
        if agora - timestamp > 600:
            return False

        # Não aceita timestamp no futuro muito além da margem normal.
        if timestamp - agora > 60:
            return False

        mensagem = f"{nonce}.{timestamp_str}".encode("utf-8")

        assinatura_calculada = hmac.new(
            _chave_oauth(),
            mensagem,
            hashlib.sha256,
        ).digest()

        assinatura_calculada_b64 = base64.urlsafe_b64encode(
            assinatura_calculada
        ).decode("utf-8").rstrip("=")

        return hmac.compare_digest(
            assinatura_recebida,
            assinatura_calculada_b64,
        )

    except (ValueError, TypeError):
        return False


# ============================================================
# LOGIN NORMAL
# ============================================================

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login por e-mail ou telefone e senha",
)
def login(
    dados: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica por e-mail ou telefone e devolve o JWT."""

    if dados.email:
        usuario = Usuario.buscar_por_email(
            db,
            str(dados.email),
        )
    else:
        usuario = Usuario.buscar_por_telefone(
            db,
            dados.telefone or "",
        )

    if (
        usuario is None
        or usuario.senha_hash is None
        or not verificar_senha(
            dados.senha,
            usuario.senha_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail, telefone ou senha incorretos.",
        )

    return TokenResponse(
        access_token=criar_token_acesso(usuario),
        usuario=UsuarioOut.model_validate(usuario),
    )


# ============================================================
# OTP — LOGIN POR TELEFONE
# ============================================================

@router.post(
    "/telefone/solicitar-codigo",
    response_model=OTPResponse,
    summary="Solicitar codigo OTP por telefone",
)
def solicitar_codigo_otp(
    dados: SolicitarOTPRequest,
    db: Session = Depends(get_db),
) -> OTPResponse:
    """Gera um codigo OTP de 6 digitos com validade de 5 minutos."""

    telefone = normalizar_telefone(dados.telefone)

    if len(telefone) < 10 or len(telefone) > 13:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telefone inválido.",
        )

    usuario = Usuario.buscar_por_telefone(
        db,
        telefone,
    )

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Não existe usuário cadastrado com este telefone.",
        )

    codigo = f"{secrets.randbelow(1_000_000):06d}"

    registro_otp = db.get(
        CodigoOTP,
        (telefone, "login"),
    )

    if registro_otp is None:
        registro_otp = CodigoOTP(
            telefone=telefone,
            finalidade="login",
            codigo=codigo,
            expira_em=datetime.now(timezone.utc)
            + timedelta(minutes=5),
            tentativas=0,
        )

        db.add(registro_otp)

    else:
        registro_otp.codigo = codigo
        registro_otp.expira_em = (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        )
        registro_otp.tentativas = 0

    db.commit()

    return OTPResponse(
        detalhe="Código OTP gerado. Validade de 5 minutos.",
        codigo_dev=codigo,
    )


@router.post(
    "/telefone/verificar-codigo",
    response_model=TokenResponse,
    summary="Validar codigo OTP por telefone",
)
def verificar_codigo_otp(
    dados: VerificarOTPRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Valida o OTP e gera o JWT do usuario."""

    telefone = normalizar_telefone(dados.telefone)

    if not dados.codigo.isdigit() or len(dados.codigo) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código OTP inválido.",
        )

    registro_otp = db.get(
        CodigoOTP,
        (telefone, "login"),
    )

    if registro_otp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Nenhum código OTP válido foi solicitado "
                "para este telefone."
            ),
        )

    if datetime.now(timezone.utc) > registro_otp.expira_em:
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código OTP expirado. Solicite um novo código.",
        )

    if registro_otp.tentativas >= 5:
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Limite de tentativas excedido. "
                "Solicite um novo código."
            ),
        )

    if not secrets.compare_digest(
        str(registro_otp.codigo),
        dados.codigo,
    ):
        registro_otp.tentativas += 1
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código OTP incorreto.",
        )

    usuario = Usuario.buscar_por_telefone(
        db,
        telefone,
    )

    if usuario is None:
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    # OTP é de uso único.
    db.delete(registro_otp)
    db.commit()

    return TokenResponse(
        access_token=criar_token_acesso(usuario),
        usuario=UsuarioOut.model_validate(usuario),
    )


# ============================================================
# OTP — CADASTRO POR TELEFONE
# ============================================================

@router.post(
    "/telefone/cadastro/solicitar-codigo",
    response_model=OTPResponse,
    summary="Solicitar OTP para cadastro por telefone",
)
def solicitar_codigo_cadastro_telefone(
    dados: CadastroTelefoneRequest,
    db: Session = Depends(get_db),
) -> OTPResponse:
    """Gera OTP para um novo cadastro por telefone."""

    telefone = normalizar_telefone(dados.telefone)

    if len(telefone) < 10 or len(telefone) > 13:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telefone inválido.",
        )

    if dados.tipo == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Conta admin não pode ser criada "
                "por autocadastro."
            ),
        )

    if not Usuario.tipo_e_valido(dados.tipo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de usuário inválido.",
        )

    if Usuario.telefone_ja_cadastrado(
        db,
        telefone,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe uma conta cadastrada "
                "com este telefone."
            ),
        )

    codigo = f"{secrets.randbelow(1_000_000):06d}"

    registro_otp = db.get(
        CodigoOTP,
        (telefone, "cadastro"),
    )

    if registro_otp is None:
        registro_otp = CodigoOTP(
            telefone=telefone,
            finalidade="cadastro",
            codigo=codigo,
            expira_em=datetime.now(timezone.utc)
            + timedelta(minutes=5),
            tentativas=0,
        )

        db.add(registro_otp)

    else:
        registro_otp.codigo = codigo
        registro_otp.expira_em = (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        )
        registro_otp.tentativas = 0

    db.commit()

    return OTPResponse(
        detalhe=(
            "Código OTP de cadastro gerado. "
            "Validade de 5 minutos."
        ),
        codigo_dev=codigo,
    )


@router.post(
    "/telefone/cadastro/confirmar",
    response_model=TokenResponse,
    summary="Confirmar cadastro por telefone com OTP",
)
def confirmar_cadastro_telefone(
    dados: ConfirmarCadastroTelefoneRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Valida o OTP e cria a conta usando somente o telefone."""

    telefone = normalizar_telefone(dados.telefone)

    if not dados.codigo.isdigit() or len(dados.codigo) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código OTP inválido.",
        )

    registro_otp = db.get(
        CodigoOTP,
        (telefone, "cadastro"),
    )

    if registro_otp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Nenhum código OTP válido foi solicitado "
                "para este cadastro."
            ),
        )

    if datetime.now(timezone.utc) > registro_otp.expira_em:
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Código OTP expirado. "
                "Solicite um novo código."
            ),
        )

    if registro_otp.tentativas >= 5:
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Limite de tentativas excedido. "
                "Solicite um novo código."
            ),
        )

    if not secrets.compare_digest(
        str(registro_otp.codigo),
        dados.codigo,
    ):
        registro_otp.tentativas += 1
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código OTP incorreto.",
        )

    if dados.tipo == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Conta admin não pode ser criada "
                "por autocadastro."
            ),
        )

    if not Usuario.tipo_e_valido(dados.tipo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de usuário inválido.",
        )

    if Usuario.telefone_ja_cadastrado(
        db,
        telefone,
    ):
        db.delete(registro_otp)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe uma conta cadastrada "
                "com este telefone."
            ),
        )

    usuario = Usuario.criar(
        db,
        nome=dados.nome,
        email=None,
        senha_hash=gerar_hash_senha(dados.senha),
        telefone=telefone,
        tipo=dados.tipo,
        oauth_provider=None,
    )

    db.delete(registro_otp)
    db.commit()

    return TokenResponse(
        access_token=criar_token_acesso(usuario),
        usuario=UsuarioOut.model_validate(usuario),
    )


# ============================================================
# USUÁRIO LOGADO
# ============================================================

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


# ============================================================
# GOOGLE OAUTH
# ============================================================

@router.get(
    "/google",
    summary="Login com Google",
)
def login_google():
    """Inicia o fluxo de autenticação OAuth com Google."""

    state_oauth = criar_state_oauth()

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

    return RedirectResponse(
        url=url_google
    )


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
            detail=(
                f"Login com Google cancelado: {error}"
            ),
        )

    state_recebido = state or state_oauth

    if not validar_state_oauth(state_recebido):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado OAuth inválido ou expirado.",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Código de autorização do Google "
                "não recebido."
            ),
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
            try:
                detalhe = resposta_token.json()
            except Exception:
                detalhe = resposta_token.text

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Não foi possível obter o token "
                    f"do Google: {detalhe}"
                ),
            )

        dados_token = resposta_token.json()

        access_token_google = dados_token.get(
            "access_token"
        )

        if not access_token_google:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Google não retornou um access token."
                ),
            )

        resposta_usuario = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={
                "Authorization": (
                    f"Bearer {access_token_google}"
                )
            },
        )

        if resposta_usuario.status_code != 200:
            try:
                detalhe = resposta_usuario.json()
            except Exception:
                detalhe = resposta_usuario.text

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Não foi possível consultar o "
                    f"usuário Google: {detalhe}"
                ),
            )

        dados_google = resposta_usuario.json()

    email = dados_google.get("email")
    nome = dados_google.get("name")
    email_verificado = dados_google.get(
        "email_verified"
    )

    if not email or not email_verificado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A conta Google não possui "
                "e-mail verificado."
            ),
        )

    usuario = Usuario.buscar_por_email(
        db,
        email,
    )

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

    token_entregafood = criar_token_acesso(
        usuario
    )

    frontend_url = settings.FRONTEND_URL.rstrip("/")

    resposta = RedirectResponse(
        url=(
            f"{frontend_url}/"
            f"#oauth_token={token_entregafood}"
        )
    )

    return resposta


# ============================================================
# FACEBOOK OAUTH
# ============================================================

@router.get(
    "/facebook",
    summary="Login com Facebook",
)
def login_facebook():
    """Inicia o fluxo de autenticação OAuth com Facebook."""

    state_oauth = criar_state_oauth()

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

    return RedirectResponse(
        url=url_facebook
    )


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
            detail=(
                f"Login com Facebook cancelado: {error}"
            ),
        )

    if not validar_state_oauth(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado OAuth inválido ou expirado.",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Código de autorização do Facebook "
                "não recebido."
            ),
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
            try:
                detalhe = resposta_token.json()
            except Exception:
                detalhe = resposta_token.text

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Não foi possível obter o token "
                    f"do Facebook: {detalhe}"
                ),
            )

        dados_token = resposta_token.json()

        access_token_facebook = dados_token.get(
            "access_token"
        )

        if not access_token_facebook:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Facebook não retornou "
                    "um access token."
                ),
            )

        resposta_usuario = await client.get(
            "https://graph.facebook.com/me",
            params={
                "fields": "id,name,email",
                "access_token": access_token_facebook,
            },
        )

        if resposta_usuario.status_code != 200:
            try:
                detalhe = resposta_usuario.json()
            except Exception:
                detalhe = resposta_usuario.text

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Não foi possível consultar o "
                    f"usuário Facebook: {detalhe}"
                ),
            )

        dados_facebook = resposta_usuario.json()

    email = dados_facebook.get("email")
    nome = dados_facebook.get("name")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A conta Facebook não forneceu "
                "um endereço de e-mail."
            ),
        )

    usuario = Usuario.buscar_por_email(
        db,
        email,
    )

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

    token_entregafood = criar_token_acesso(
        usuario
    )

    frontend_url = settings.FRONTEND_URL.rstrip("/")

    print(
        f"[FACEBOOK] Redirecionando para frontend: "
        f"{frontend_url}/"
    )

    resposta = RedirectResponse(
        url=(
            f"{frontend_url}/"
            f"#oauth_token={token_entregafood}"
        )
    )

    return resposta