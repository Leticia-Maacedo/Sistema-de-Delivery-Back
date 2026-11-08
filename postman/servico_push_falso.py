"""Servico de push falso para testar as notificacoes de ponta a ponta (Postman).

Usado por `servidor_local_teste.py --push`. Faz o papel de dois servicos de
fora, sem internet e sem navegador:

- **Servico de push do navegador** (Web Push): gera inscricoes de teste com
  chaves reais (P-256 + auth), recebe o POST cifrado que o pywebpush manda e
  **decifra** a mensagem (aes128gcm) com a chave privada da inscricao. Assim o
  teste confere titulo, texto, URL do clique e tag exatamente como o
  navegador receberia. Inscricoes com nome "expirada-*" respondem 410, como o
  navegador faz quando o usuario bloqueia as notificacoes ou limpa os dados.
- **Firebase Cloud Messaging** (app mobile): responde o token OAuth2 e o
  envio da API v1. Tokens que comecam com "invalido" respondem 404
  UNREGISTERED, como o FCM faz quando o app foi desinstalado.

Cada entrega fica guardada e e consultada pelo Postman em GET /capturas.

So muda o *transporte*: a cifragem, a assinatura VAPID, o JWT do Google e as
regras do back (quem recebe, apagar token invalido) rodam de verdade.
"""

import base64
import json
import os
import threading
import time
from urllib.parse import parse_qs

import http_ece
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import FastAPI, Request, Response

# Host "https" que a API aceita na inscricao (o schema exige https://). Na
# hora de enviar, o servidor de teste troca por http://127.0.0.1:<porta>.
HOST_FALSO = "https://push-falso.entregafood.test"


def b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def b64url_decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# ------------------------------------------------------------ chaves de teste


def gerar_vapid() -> tuple[str, str]:
    """Par VAPID: (publica para o navegador, privada no formato do pywebpush)."""

    chave = ec.generate_private_key(ec.SECP256R1())
    publica = chave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    privada = chave.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return b64url(publica), b64url(privada)


def gerar_credenciais_firebase(porta: int) -> str:
    """Conta de servico falsa (chave RSA real) com o token_uri apontando para ca."""

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return json.dumps({
        "type": "service_account",
        "project_id": "entregafood-teste",
        "client_email": "teste@entregafood-teste.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": f"http://127.0.0.1:{porta}/oauth/token",
    })


# ------------------------------------------------------------ estado

_trava = threading.Lock()
_inscricoes: dict[str, dict] = {}   # nome -> {"chave": EC privada, "auth": bytes}
_capturas: list[dict] = []


def _registrar(captura: dict) -> None:
    with _trava:
        captura["n"] = len(_capturas) + 1
        _capturas.append(captura)


# ------------------------------------------------------------ app

app = FastAPI(title="Servico de push falso (testes)")


@app.get("/inscricoes/{nome}")
def nova_inscricao(nome: str) -> dict:
    """Uma inscricao de navegador pronta para POST /notificacoes/inscricao."""

    chave = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    with _trava:
        _inscricoes[nome] = {"chave": chave, "auth": auth}
    publica = chave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"endpoint": f"{HOST_FALSO}/webpush/{nome}", "keys": {"p256dh": b64url(publica), "auth": b64url(auth)}}


@app.post("/webpush/{nome}")
async def receber_webpush(nome: str, request: Request) -> Response:
    corpo = await request.body()
    expirada = nome.startswith("expirada")
    captura = {
        "canal": "web", "destino": nome,
        "ttl": request.headers.get("ttl"),
        "content_encoding": request.headers.get("content-encoding"),
        "vapid_assinado": request.headers.get("authorization", "").startswith("vapid t="),
        "resposta": 410 if expirada else 201,
    }
    inscricao = _inscricoes.get(nome)
    if inscricao is not None:
        try:
            texto = http_ece.decrypt(corpo, private_key=inscricao["chave"], auth_secret=inscricao["auth"],
                                     version="aes128gcm")
            captura["mensagem"] = json.loads(texto)
            captura["decifrada"] = True
        except Exception as erro:  # noqa: BLE001
            captura["decifrada"] = False
            captura["erro"] = str(erro)
    _registrar(captura)
    return Response(status_code=captura["resposta"])


@app.post("/oauth/token")
async def token_google(request: Request) -> dict:
    formulario = parse_qs((await request.body()).decode())
    assercao = formulario.get("assertion", [""])[0]
    _registrar({"canal": "oauth", "jwt_recebido": assercao.count(".") == 2, "resposta": 200})
    return {"access_token": "token-de-teste", "expires_in": 3600, "token_type": "Bearer"}


@app.post("/fcm/v1/projects/{projeto}/messages:send")
async def enviar_fcm(projeto: str, request: Request) -> Response:
    corpo = await request.json()
    mensagem = corpo.get("message", {})
    token = mensagem.get("token", "")
    invalido = token.startswith("invalido")
    _registrar({
        "canal": "fcm", "destino": token, "projeto": projeto,
        "bearer": request.headers.get("authorization") == "Bearer token-de-teste",
        "titulo": mensagem.get("notification", {}).get("title"),
        "corpo": mensagem.get("notification", {}).get("body"),
        "dados": mensagem.get("data", {}),
        "resposta": 404 if invalido else 200,
    })
    if invalido:
        erro = {"error": {"code": 404, "status": "NOT_FOUND", "details": [
            {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]}}
        return Response(json.dumps(erro), status_code=404, media_type="application/json")
    return Response(json.dumps({"name": f"projects/{projeto}/messages/{time.time_ns()}"}),
                    media_type="application/json")


@app.get("/capturas")
def listar_capturas(esperar: int = 0, desde: int = 0, segundos: float = 4.0) -> dict:
    """Entregas recebidas depois da captura `desde`.

    `esperar=N` aguarda (ate `segundos`) chegarem N entregas: os avisos saem
    em segundo plano, depois da resposta da API.
    """

    limite = time.time() + segundos
    while True:
        with _trava:
            novas = [c for c in _capturas if c["n"] > desde and c["canal"] != "oauth"]
            total = len(_capturas)
        if len(novas) >= esperar or time.time() >= limite:
            break
        time.sleep(0.05)
    time.sleep(0.3 if esperar else 0)  # pega entregas que chegam logo depois
    with _trava:
        novas = [c for c in _capturas if c["n"] > desde and c["canal"] != "oauth"]
        total = len(_capturas)
    return {"total": total, "capturas": novas}


def iniciar(porta: int, host: str = "127.0.0.1") -> None:
    """Sobe o servico falso numa thread (daemon) ao lado da API."""

    config = uvicorn.Config(app, host=host, port=porta, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
