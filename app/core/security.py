"""Seguranca — hash de senha, geracao/validacao de JWT e middleware de sessao.

TAREFA DA LETÍCIA (Bloco 3). O arquivo ja vem funcional para que o CRUD
do Geovane rode de ponta a ponta desde o primeiro dia; Letícia assume a
manutencao e a evolucao dele (RF03 a RF05 entram na Sprint 2).

Atende o RNF03: senha nunca e armazenada em texto puro.
"""
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.usuario import Usuario

settings = get_settings()
contexto_senha = CryptContext(schemes=["bcrypt"], deprecated="auto")
esquema_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- senha
def gerar_hash_senha(senha: str) -> str:
    return contexto_senha.hash(senha)


def verificar_senha(senha_pura: str, senha_hash: str | None) -> bool:
    if not senha_hash:
        return False
    return contexto_senha.verify(senha_pura, senha_hash)


# ------------------------------------------------------------------ jwt
def criar_token_acesso(usuario: Usuario) -> str:
    expira_em = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario.id),
        "email": usuario.email,
        "tipo": usuario.tipo,
        "exp": expira_em,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ----------------------------------------------------------- middleware
def obter_usuario_logado(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """Dependencia que protege as rotas. Injete com `Depends(obter_usuario_logado)`."""
    nao_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ausente ou invalido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credenciais is None:
        raise nao_autorizado

    try:
        payload = decodificar_token(credenciais.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao expirada."
        ) from None
    except jwt.PyJWTError:
        raise nao_autorizado from None

    usuario = Usuario.buscar_por_id(db, int(payload.get("sub", 0)))
    if usuario is None:
        raise nao_autorizado
    return usuario


def exigir_admin(usuario: Usuario = Depends(obter_usuario_logado)) -> Usuario:
    """Dependencia que protege rotas administrativas (gerenciar qualquer usuario)."""
    if usuario.tipo != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem acessar este recurso.",
        )
    return usuario
