"""Envio de notificacoes push para o app mobile pelo Firebase Cloud Messaging.

Usa a API HTTP v1 do FCM:
    1. Autentica com a conta de servico do projeto Firebase (JWT assinado
       com a chave privada -> token de acesso OAuth2, guardado ate expirar).
    2. POST https://fcm.googleapis.com/v1/projects/<projeto>/messages:send
       com o token do celular, o titulo, o texto e os dados do pedido.

Configuracao: FIREBASE_CREDENCIAIS no .env / Render = o JSON da conta de
servico (Firebase > Configuracoes do projeto > Contas de servico > Gerar
nova chave privada), inteiro numa linha ou em base64. Sem ela, `fcm_ativo()`
e falso e nada e enviado. Nunca levanta erro: notificacao nao pode quebrar
o fluxo do pedido.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.push_token_fcm import PushTokenFCM

log = logging.getLogger("entregafood.push_fcm")

ESCOPO = "https://www.googleapis.com/auth/firebase.messaging"
URL_ENVIO = "https://fcm.googleapis.com/v1/projects/{projeto}/messages:send"
TIMEOUT_SEGUNDOS = 15.0

# Respostas do FCM que significam "este token nao vale mais": o app foi
# desinstalado, o token expirou ou nunca foi valido.
ERROS_TOKEN_INVALIDO = {"UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND"}

_cache_token = {"valor": None, "expira": 0.0}


@dataclass
class Credenciais:
    projeto: str
    email: str
    chave_privada: str
    url_token: str


def ler_credenciais() -> Credenciais | None:
    """Le FIREBASE_CREDENCIAIS (JSON ou base64 do JSON). None se vazio ou invalido."""

    bruto = get_settings().FIREBASE_CREDENCIAIS.strip()
    if not bruto:
        return None

    try:
        texto = bruto if bruto.startswith("{") else base64.b64decode(bruto).decode("utf-8")
        dados = json.loads(texto)
        return Credenciais(
            projeto=dados["project_id"],
            email=dados["client_email"],
            chave_privada=dados["private_key"],
            url_token=dados.get("token_uri", "https://oauth2.googleapis.com/token"),
        )
    except (ValueError, KeyError) as erro:
        log.error("FIREBASE_CREDENCIAIS invalida: %s", erro)
        return None


def fcm_ativo() -> bool:
    return ler_credenciais() is not None


def obter_token_acesso(cred: Credenciais, http: httpx.Client) -> str:
    """Token OAuth2 do Google para o FCM (reaproveitado ate perto de expirar)."""

    agora = time.time()
    if _cache_token["valor"] and _cache_token["expira"] - 60 > agora:
        return _cache_token["valor"]

    assercao = jwt.encode(
        {"iss": cred.email, "scope": ESCOPO, "aud": cred.url_token, "iat": int(agora), "exp": int(agora) + 3600},
        cred.chave_privada,
        algorithm="RS256",
    )
    resposta = http.post(
        cred.url_token,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assercao},
    )
    resposta.raise_for_status()
    dados = resposta.json()

    _cache_token["valor"] = dados["access_token"]
    _cache_token["expira"] = agora + int(dados.get("expires_in", 3600))
    return _cache_token["valor"]


def montar_mensagem(token: str, *, titulo: str, corpo: str, dados: dict[str, str]) -> dict:
    """Corpo da mensagem no formato da API v1 (os dados precisam ser texto)."""

    return {
        "message": {
            "token": token,
            "notification": {"title": titulo, "body": corpo},
            "data": {chave: str(valor) for chave, valor in dados.items()},
            "android": {"priority": "high", "notification": {"channel_id": "pedidos"}},
        }
    }


def _codigo_erro(resposta: httpx.Response) -> str | None:
    try:
        erro = resposta.json().get("error", {})
    except ValueError:
        return None

    for detalhe in erro.get("details", []):
        if detalhe.get("errorCode"):
            return detalhe["errorCode"]
    return erro.get("status")


def enviar_para_usuario_fcm(
    db: Session,
    usuario_id: int,
    *,
    titulo: str,
    corpo: str,
    dados: dict[str, str] | None = None,
    http: httpx.Client | None = None,
) -> int:
    """Envia para todos os celulares do usuario. Retorna quantos o FCM aceitou.

    Tokens que o Firebase diz que nao valem mais sao apagados.
    """

    cred = ler_credenciais()
    if cred is None:
        return 0

    tokens = PushTokenFCM.listar_por_usuario(db, usuario_id)
    if not tokens:
        return 0

    cliente = http or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
    enviados = 0

    try:
        acesso = obter_token_acesso(cred, cliente)
        url = URL_ENVIO.format(projeto=cred.projeto)

        for registro in tokens:
            resposta = cliente.post(
                url,
                headers={"Authorization": f"Bearer {acesso}"},
                json=montar_mensagem(registro.token, titulo=titulo, corpo=corpo, dados=dados or {}),
            )
            if resposta.status_code == 200:
                enviados += 1
                continue

            codigo = _codigo_erro(resposta)
            if codigo in ERROS_TOKEN_INVALIDO:
                PushTokenFCM.remover(db, registro.token)
            else:
                log.warning("FCM recusou o envio para o usuario %s: %s %s", usuario_id, resposta.status_code, codigo)
    except Exception as erro:  # noqa: BLE001 - rede, credencial errada...
        log.warning("FCM indisponivel para o usuario %s: %s", usuario_id, erro)
    finally:
        if http is None:
            cliente.close()

    return enviados
