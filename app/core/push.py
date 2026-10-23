"""Envio de notificacoes push (Web Push com chaves VAPID).

Funciona com o servico de push do proprio navegador (Chrome, Edge, Firefox,
Safari no iOS com o site na tela inicial): nao depende de conta em servico
externo. As chaves ficam no .env (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY).
Sem as chaves, `push_ativo()` e falso e nada e enviado.
"""

import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.push_inscricao import PushInscricao

log = logging.getLogger("entregafood.push")


def push_ativo() -> bool:
    s = get_settings()
    return bool(s.VAPID_PUBLIC_KEY and s.VAPID_PRIVATE_KEY)


def enviar_para_usuario(
    db: Session,
    usuario_id: int,
    *,
    titulo: str,
    corpo: str,
    url: str = "/",
    tag: str | None = None,
) -> int:
    """Envia a notificacao para todos os navegadores do usuario.

    Retorna quantas foram entregues ao servico de push. Inscricoes que o
    navegador ja cancelou (HTTP 404/410) sao apagadas. Nunca levanta erro:
    notificacao nao pode quebrar o fluxo do pedido.
    """

    if not push_ativo():
        return 0

    s = get_settings()
    dados = json.dumps({"titulo": titulo, "corpo": corpo, "url": url, "tag": tag}, ensure_ascii=False)
    enviados = 0

    for inscricao in PushInscricao.listar_por_usuario(db, usuario_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": inscricao.endpoint,
                    "keys": {"p256dh": inscricao.p256dh, "auth": inscricao.auth},
                },
                data=dados,
                vapid_private_key=s.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": s.VAPID_SUBJECT},
                ttl=3600,
            )
            enviados += 1
        except WebPushException as erro:
            codigo = getattr(erro.response, "status_code", None)
            if codigo in (404, 410):
                PushInscricao.remover_por_endpoint(db, inscricao.endpoint)
            else:
                log.warning("push falhou para o usuario %s: %s", usuario_id, erro)
        except Exception as erro:  # rede, chave invalida...
            log.warning("push falhou para o usuario %s: %s", usuario_id, erro)

    return enviados
