"""Envio do codigo de validacao (OTP) do login e do cadastro por e-mail.

O codigo de 6 digitos vai para o e-mail da conta (login) ou para o e-mail
informado no cadastro, pelo mesmo SMTP da nota fiscal (app/core/email.py,
Brevo no Render).

Sem SMTP configurado (rodando local, testes) o codigo volta na resposta
em `codigo_dev`, como antes, para nao travar o desenvolvimento. Com
`OTP_MOSTRAR_CODIGO=true` ele volta mesmo com o e-mail enviado (so para
demonstracao).
"""

import logging

from app.core import email
from app.core.config import get_settings

log = logging.getLogger("entregafood.otp")

ASSUNTOS = {
    "login": "EntregaFood - seu código para entrar",
    "cadastro": "EntregaFood - código para confirmar seu cadastro",
}

TEXTOS = {
    "login": "Use o código abaixo para entrar no EntregaFood.",
    "cadastro": "Use o código abaixo para confirmar o seu cadastro no EntregaFood.",
}


class EnvioIndisponivel(Exception):
    """O SMTP esta configurado, mas o e-mail nao saiu (servidor fora, senha errada)."""


def mascarar_email(endereco: str) -> str:
    """richardd.ferreira06@gmail.com -> r*****6@gmail.com (mostrado na tela)."""

    usuario, _, dominio = endereco.partition("@")
    if len(usuario) <= 2:
        return f"{usuario[:1]}*@{dominio}"
    return f"{usuario[0]}{'*' * min(len(usuario) - 2, 5)}{usuario[-1]}@{dominio}"


def montar_texto(nome: str | None, codigo: str, finalidade: str, minutos: int) -> str:
    saudacao = f"Olá, {nome.split()[0]}!" if nome else "Olá!"
    return (
        f"{saudacao}\n\n"
        f"{TEXTOS.get(finalidade, TEXTOS['login'])}\n\n"
        f"    {codigo}\n\n"
        f"Ele vale por {minutos} minutos e só pode ser usado uma vez.\n"
        "Se não foi você quem pediu, ignore este e-mail.\n\n"
        "Equipe EntregaFood"
    )


def enviar_codigo(
    *,
    para: str | None,
    nome: str | None,
    codigo: str,
    finalidade: str,
    minutos: int = 5,
) -> bool:
    """Manda o codigo por e-mail. True = enviado; False = SMTP nao configurado.

    Levanta EnvioIndisponivel se o SMTP esta configurado e o envio falhou.
    """

    if not para or not email.smtp_ativo():
        return False

    try:
        return email.enviar(
            para=para,
            assunto=ASSUNTOS.get(finalidade, ASSUNTOS["login"]),
            texto=montar_texto(nome, codigo, finalidade, minutos),
        )
    except Exception as erro:  # noqa: BLE001 - smtplib levanta varios tipos
        log.exception("Falha ao enviar o codigo de %s para %s", finalidade, para)
        raise EnvioIndisponivel(str(erro)) from erro


def codigo_na_resposta(codigo: str, enviado: bool) -> str | None:
    """`codigo_dev` so quando o e-mail nao foi enviado (ou em modo demonstracao)."""

    if not enviado or get_settings().OTP_MOSTRAR_CODIGO:
        return codigo
    return None
