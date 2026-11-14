"""Controller das notificacoes push (Backlog 21 e 23; app mobile na Sprint 4).

O front pede a chave publica, inscreve o navegador no servico de push e
envia a inscricao para ca. Os avisos em si sao disparados pelo pedido
(app/core/notificacoes_pedido.py).
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.push import push_ativo
from app.core.push_fcm import fcm_ativo
from app.core.security import obter_usuario_logado
from app.models.push_inscricao import PushInscricao
from app.models.push_token_fcm import PushTokenFCM
from app.models.usuario import Usuario
from app.schemas.entrega import (
    CancelarPushIn,
    CancelarTokenFcmIn,
    ChavePublicaOut,
    InscricaoPushIn,
    TokenFcmIn,
)

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


@router.get("/chave-publica", response_model=ChavePublicaOut, summary="Chave pública VAPID para o navegador")
def chave_publica() -> ChavePublicaOut:
    ativo = push_ativo()
    return ChavePublicaOut(ativo=ativo, chave_publica=get_settings().VAPID_PUBLIC_KEY if ativo else None)


@router.post("/inscricao", status_code=status.HTTP_201_CREATED, summary="Ativar notificações neste navegador")
def inscrever(
    dados: InscricaoPushIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> dict[str, str | int]:
    """Guarda a inscricao do navegador para o usuario logado.

    Se o mesmo navegador ja estava inscrito (outro login), passa a ser deste usuario.
    """

    inscricao = PushInscricao.salvar(
        db,
        usuario_id=usuario_logado.id,
        endpoint=dados.endpoint,
        p256dh=dados.keys.p256dh,
        auth=dados.keys.auth,
    )
    return {"id": inscricao.id, "mensagem": "Notificações ativadas neste navegador."}


@router.delete("/inscricao", status_code=status.HTTP_204_NO_CONTENT, summary="Desativar notificações neste navegador")
def cancelar(
    dados: CancelarPushIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Response:
    PushInscricao.remover_por_endpoint(db, dados.endpoint, usuario_logado.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ app mobile (FCM)


@router.post("/fcm", summary="Registrar o token do app mobile (Firebase)")
def registrar_token_fcm(
    dados: TokenFcmIn,
    resposta: Response,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> dict[str, str | int | bool]:
    """Guarda o token do Firebase do celular para o usuario logado.

    O app chama ao abrir e sempre que o Firebase troca o token. Token novo
    responde 201; token ja conhecido e so atualizado (200). Se o celular
    estava com outra conta, o token passa a ser deste usuario.
    """

    registro, criado = PushTokenFCM.salvar(
        db,
        usuario_id=usuario_logado.id,
        token=dados.token,
        plataforma=dados.plataforma,
    )
    resposta.status_code = status.HTTP_201_CREATED if criado else status.HTTP_200_OK
    return {
        "id": registro.id,
        "plataforma": registro.plataforma,
        "fcm_ativo": fcm_ativo(),
        "mensagem": "Notificações ativadas neste celular.",
    }


@router.delete("/fcm", status_code=status.HTTP_204_NO_CONTENT, summary="Remover o token do app mobile")
def remover_token_fcm(
    dados: CancelarTokenFcmIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Response:
    """Logout no app: o celular para de receber os avisos desta conta."""

    PushTokenFCM.remover(db, dados.token, usuario_logado.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
