"""Envio automático de SMS e WhatsApp (Backlog — envio automático de SMS, WhatsApp, e-mail...).

E-mail (código e nota fiscal) e push (navegador e app) já existiam; este
módulo acrescenta os dois canais que faltavam, para avisar o CLIENTE a cada
etapa do pedido no telefone cadastrado:

- SMS pela Twilio (API REST 2010-04-01):
      POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
      autenticação HTTP Basic (SID, token); formulário To, From, Body.
- WhatsApp pela WhatsApp Business Platform da Meta (Cloud API):
      POST https://graph.facebook.com/{versão}/{PHONE_NUMBER_ID}/messages
      autenticação Bearer; mensagem de MODELO (template) aprovado na Meta,
      porque a empresa só pode iniciar conversa com modelo. O modelo usado
      (WHATSAPP_TEMPLATE) tem dois parâmetros no corpo: título e texto.

Cada canal só liga com as próprias credenciais no .env / Render (vazias =
desligado, como o push e a Focus NFe). Nunca levanta erro: falha de envio
fica no log e não afeta o pedido. MENSAGERIA_BASE_URL troca os servidores
nos testes.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger("entregafood.mensageria")
TIMEOUT_SEGUNDOS = 10.0
URL_TWILIO = "https://api.twilio.com"
URL_META = "https://graph.facebook.com"


def telefone_e164(telefone: str | None) -> str | None:
    """'(11) 99999-0000' -> '+5511999990000'. Aceita com ou sem o 55; None se não der para usar."""

    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    internacional = (telefone or "").strip().startswith("+")  # com "+", o código do país já veio
    if not internacional and len(digitos) in (10, 11):  # DDD + número
        digitos = "55" + digitos
    if not (digitos.startswith("55") and len(digitos) in (12, 13)):
        return None
    return "+" + digitos


@dataclass
class Envio:
    canal: str
    para: str
    ok: bool
    detalhe: str = ""


def sms_ativo() -> bool:
    c = get_settings()
    return bool(c.TWILIO_ACCOUNT_SID and c.TWILIO_AUTH_TOKEN and c.TWILIO_FROM)


def whatsapp_ativo() -> bool:
    c = get_settings()
    return bool(c.WHATSAPP_TOKEN and c.WHATSAPP_PHONE_NUMBER_ID and c.WHATSAPP_TEMPLATE)


def mensageria_ativa() -> bool:
    return sms_ativo() or whatsapp_ativo()


def _cliente() -> httpx.Client:
    """Cliente HTTP (os testes trocam por um servidor simulado)."""

    return httpx.Client()


def _post(http: httpx.Client, canal: str, para: str, url: str, **kw) -> Envio:
    try:
        r = http.post(url, timeout=TIMEOUT_SEGUNDOS, **kw)
    except httpx.HTTPError as e:
        log.warning("%s para %s: serviço indisponível (%s)", canal, para, e.__class__.__name__)
        return Envio(canal, para, False, "serviço indisponível")
    if r.status_code >= 400:
        log.warning("%s para %s recusado: HTTP %s %s", canal, para, r.status_code, r.text[:200])
        return Envio(canal, para, False, f"HTTP {r.status_code}")
    return Envio(canal, para, True)


def enviar_sms(para: str, texto: str, http: httpx.Client | None = None) -> Envio:
    c = get_settings()
    base = (c.MENSAGERIA_BASE_URL or URL_TWILIO).rstrip("/")
    return _post(http or _cliente(), "sms", para, f"{base}/2010-04-01/Accounts/{c.TWILIO_ACCOUNT_SID}/Messages.json",
                 auth=(c.TWILIO_ACCOUNT_SID, c.TWILIO_AUTH_TOKEN), data={"To": para, "From": c.TWILIO_FROM, "Body": texto[:600]})


def enviar_whatsapp(para: str, titulo: str, texto: str, http: httpx.Client | None = None) -> Envio:
    c = get_settings()
    base = (c.MENSAGERIA_BASE_URL or URL_META).rstrip("/")
    corpo = {
        "messaging_product": "whatsapp",
        "to": para.lstrip("+"),
        "type": "template",
        "template": {
            "name": c.WHATSAPP_TEMPLATE,
            "language": {"code": c.WHATSAPP_IDIOMA},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": titulo}, {"type": "text", "text": texto}]}],
        },
    }
    return _post(http or _cliente(), "whatsapp", para, f"{base}/{c.WHATSAPP_API_VERSAO}/{c.WHATSAPP_PHONE_NUMBER_ID}/messages",
                 headers={"Authorization": f"Bearer {c.WHATSAPP_TOKEN}"}, json=corpo)


def enviar_para_telefone(telefone: str | None, titulo: str, texto: str, http: httpx.Client | None = None) -> list[Envio]:
    """Manda pelos canais ligados. Telefone vazio ou inválido: não envia nada."""

    para = telefone_e164(telefone)
    if para is None:
        return []
    envios = []
    if sms_ativo():
        envios.append(enviar_sms(para, f"EntregaFood - {titulo}: {texto}", http))
    if whatsapp_ativo():
        envios.append(enviar_whatsapp(para, titulo, texto, http))
    return envios


def enviar_para_usuario(db, usuario_id: int, titulo: str, texto: str, http: httpx.Client | None = None) -> list[Envio]:
    from app.models.usuario import Usuario

    usuario = db.get(Usuario, usuario_id)
    return enviar_para_telefone(usuario.telefone if usuario else None, titulo, texto, http)
