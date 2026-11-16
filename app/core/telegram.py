"""Avisos do pedido pelo Telegram (Backlog — envio automático de SMS, WhatsApp, e-mail, etc.).

Canal gratuito e sem restrição de país: um bot do Telegram (criado no
@BotFather) manda ao cliente os mesmos avisos do push a cada etapa do pedido.

Como a conta é ligada ao Telegram (sem webhook, funciona no Render gratuito
e localmente):
    1. O cliente pede o vínculo (POST /notificacoes/telegram/vincular): a API
       gera um código de uso único, válido por 15 minutos, e devolve o link
       https://t.me/<bot>?start=<código>.
    2. No Telegram ele toca em "Iniciar"; o bot recebe "/start <código>".
    3. O site chama POST /notificacoes/telegram/confirmar: a API lê as
       mensagens novas do bot (getUpdates), acha o dono do código e guarda o
       chat_id. Daí em diante os avisos chegam pelo sendMessage.

API do Telegram: https://api.telegram.org/bot<token>/<método> (JSON).
Configuração: TELEGRAM_BOT_TOKEN no .env / Render (vazio = desligado).
TELEGRAM_BASE_URL troca o servidor nos testes. Nunca levanta erro para o
fluxo do pedido.
"""

import logging
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings

log = logging.getLogger("entregafood.telegram")
URL_TELEGRAM = "https://api.telegram.org"
TIMEOUT_SEGUNDOS = 10.0
VALIDADE_CODIGO = timedelta(minutes=15)
BOAS_VINDAS = "Pronto! A partir de agora você recebe aqui os avisos dos seus pedidos no EntregaFood."
SEM_CODIGO = "Para receber os avisos, abra o EntregaFood, entre em Minha conta e toque em \"Receber avisos no Telegram\"."

_estado = {"bot": None, "offset": None}  # nome do bot (getMe) e próxima atualização a ler


class TelegramErro(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


def telegram_ativo() -> bool:
    return bool(get_settings().TELEGRAM_BOT_TOKEN)


def _cliente() -> httpx.Client:
    """Cliente HTTP (os testes trocam por um Telegram simulado)."""

    return httpx.Client()


def _api(metodo: str, http: httpx.Client | None = None, **dados):
    c = get_settings()
    base = (c.TELEGRAM_BASE_URL or URL_TELEGRAM).rstrip("/")
    try:
        r = (http or _cliente()).post(f"{base}/bot{c.TELEGRAM_BOT_TOKEN}/{metodo}", json=dados, timeout=TIMEOUT_SEGUNDOS)
    except httpx.HTTPError as e:
        raise TelegramErro(f"Telegram indisponível ({e.__class__.__name__})") from e
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    if r.status_code >= 400 or not corpo.get("ok"):
        raise TelegramErro(corpo.get("description") or f"HTTP {r.status_code}", r.status_code)
    return corpo["result"]


def nome_do_bot(http: httpx.Client | None = None) -> str:
    if not _estado["bot"]:
        _estado["bot"] = _api("getMe", http)["username"]
    return _estado["bot"]


def iniciar_vinculo(db: Session, usuario, http: httpx.Client | None = None, agora: datetime | None = None) -> dict:
    """Gera o código de uso único e o link do bot para o usuário."""

    agora = agora or datetime.now()
    usuario.telegram_codigo = secrets.token_urlsafe(16)  # só A-Z, a-z, 0-9, _ e - (aceitos no /start)
    usuario.telegram_codigo_expira = agora + VALIDADE_CODIGO
    link = f"https://t.me/{nome_do_bot(http)}?start={usuario.telegram_codigo}"
    db.commit()
    return {"link": link, "expira_em": usuario.telegram_codigo_expira}


def processar_atualizacoes(db: Session, http: httpx.Client | None = None, agora: datetime | None = None) -> int:
    """Lê as mensagens novas do bot e liga cada "/start <código>" à conta dona do código.

    Devolve quantas contas foram ligadas. Confirma as mensagens lidas no
    Telegram (offset) para não processar de novo.
    """

    from app.models.usuario import Usuario

    agora = agora or datetime.now()
    params = {"timeout": 0, "allowed_updates": ["message"]}
    if _estado["offset"] is not None:
        params["offset"] = _estado["offset"]
    atualizacoes = _api("getUpdates", http, **params)
    ligados = 0
    for upd in atualizacoes:
        _estado["offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        texto = (msg.get("text") or "").strip()
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None or not texto.startswith("/start"):
            continue
        codigo = texto[len("/start"):].strip()
        usuario = db.execute(select(Usuario).where(Usuario.telegram_codigo == codigo)).scalar_one_or_none() if codigo else None
        if usuario is None or usuario.telegram_codigo_expira is None or usuario.telegram_codigo_expira < agora:
            _responder(chat_id, SEM_CODIGO if not codigo else "Este link expirou ou já foi usado. Gere outro em Minha conta.", http)
            continue
        usuario.telegram_chat_id = str(chat_id)
        usuario.telegram_codigo = None
        usuario.telegram_codigo_expira = None
        db.commit()
        ligados += 1
        _responder(chat_id, BOAS_VINDAS, http)
    if atualizacoes:  # confirma no Telegram que estas já foram lidas
        try:
            _api("getUpdates", http, offset=_estado["offset"], limit=1, timeout=0)
        except TelegramErro:
            pass
    return ligados


def _responder(chat_id, texto: str, http) -> None:
    try:
        _api("sendMessage", http, chat_id=chat_id, text=texto)
    except TelegramErro as e:
        log.warning("Telegram: não foi possível responder ao chat: %s", e)


def enviar_aviso(chat_id: str, titulo: str, texto: str, http: httpx.Client | None = None) -> tuple[bool, int | None]:
    """Manda um aviso. Devolve (ok, status HTTP do erro). Nunca levanta erro."""

    try:
        _api("sendMessage", http, chat_id=chat_id, text=f"{titulo}\n{texto}")
        return True, None
    except TelegramErro as e:
        log.warning("Telegram: aviso não entregue (%s)", e)
        return False, e.status
