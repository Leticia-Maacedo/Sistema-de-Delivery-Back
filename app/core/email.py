"""Envio de e-mail por SMTP (usado pela nota fiscal).

Configuracao no .env: SMTP_HOST, SMTP_PORTA, SMTP_USUARIO, SMTP_SENHA e
SMTP_REMETENTE. No Gmail use uma "senha de app" (porta 587).
Sem SMTP_HOST o envio so e registrado no log: o sistema continua
funcionando normalmente.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("entregafood.email")


def smtp_ativo() -> bool:
    return bool(get_settings().SMTP_HOST.strip())


def montar_mensagem(
    *,
    remetente: str,
    para: str,
    assunto: str,
    texto: str,
    anexo: bytes | None = None,
    nome_anexo: str = "anexo.pdf",
) -> EmailMessage:
    mensagem = EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = para
    mensagem["Subject"] = assunto
    mensagem.set_content(texto)

    if anexo is not None:
        mensagem.add_attachment(anexo, maintype="application", subtype="pdf", filename=nome_anexo)

    return mensagem


def enviar(
    *,
    para: str,
    assunto: str,
    texto: str,
    anexo: bytes | None = None,
    nome_anexo: str = "anexo.pdf",
) -> bool:
    """Envia o e-mail. Devolve True se saiu; False se o SMTP nao esta configurado."""

    settings = get_settings()

    if not smtp_ativo():
        log.info("SMTP nao configurado: e-mail '%s' para %s nao enviado.", assunto, para)
        return False

    mensagem = montar_mensagem(
        remetente=settings.SMTP_REMETENTE or settings.SMTP_USUARIO,
        para=para,
        assunto=assunto,
        texto=texto,
        anexo=anexo,
        nome_anexo=nome_anexo,
    )

    if settings.SMTP_PORTA == 465:
        conexao = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORTA, timeout=30)
    else:
        conexao = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORTA, timeout=30)

    with conexao:
        if settings.SMTP_PORTA != 465:
            conexao.starttls()
        if settings.SMTP_USUARIO:
            conexao.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
        conexao.send_message(mensagem)

    log.info("E-mail '%s' enviado para %s.", assunto, para)
    return True
