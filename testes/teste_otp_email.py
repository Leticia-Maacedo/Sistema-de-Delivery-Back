"""Testes do envio do codigo de validacao (OTP) por e-mail - login e cadastro.

Roda a API de verdade (TestClient) com SQLite em memoria. O SMTP e trocado
por um falso que guarda os e-mails "enviados", entao nao sai e-mail real.

Cobre: login por celular manda o codigo para o e-mail da conta e nao devolve
mais o codigo na resposta; conta sem e-mail; cadastro manda o codigo para o
e-mail informado; e-mail ja usado; falha do SMTP (502); sem SMTP o codigo
continua voltando em codigo_dev; modo demonstracao (OTP_MOSTRAR_CODIGO).

Executar:  python -m pytest testes/teste_otp_email.py -v
"""

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.controllers import auth_controller
from app.core import email as email_smtp
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.otp_envio import mascarar_email, montar_texto
from app.core.security import gerar_hash_senha
from app.main import app
from app.models.usuario import Usuario


class _RelogioSemFuso(datetime):
    """SQLite nao guarda fuso: o teste usa horas sem fuso no auth_controller."""

    @classmethod
    def now(cls, tz=None):
        return datetime.now()


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(auth_controller, "datetime", _RelogioSemFuso)

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = db_de_teste

    with Sessao() as db:
        agora = datetime.now()
        db.add_all([
            Usuario(nome="Richard Teste", email="richard.teste@gmail.com", telefone="11988887777",
                    tipo="cliente", senha_hash=gerar_hash_senha("senha123"), criado_em=agora),
            Usuario(nome="Sem Email", email=None, telefone="11966665555",
                    tipo="cliente", senha_hash=gerar_hash_senha("senha123"), criado_em=agora),
        ])
        db.commit()

    enviados = []

    def ligar_smtp(falhar=False, mostrar=False):
        monkeypatch.setenv("SMTP_HOST", "smtp-relay.brevo.com")
        monkeypatch.setenv("OTP_MOSTRAR_CODIGO", "true" if mostrar else "false")
        get_settings.cache_clear()

        def enviar_falso(*, para, assunto, texto, anexo=None, nome_anexo="anexo.pdf"):
            if falhar:
                raise OSError("Authentication failed")
            enviados.append({"para": para, "assunto": assunto, "texto": texto})
            return True

        monkeypatch.setattr(email_smtp, "enviar", enviar_falso)

    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
    yield {"api": TestClient(app), "enviados": enviados, "ligar_smtp": ligar_smtp}
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def codigo_do_email(texto):
    return re.search(r"\b(\d{6})\b", texto).group(1)


# ------------------------------------------------------------------ login


def test_login_manda_o_codigo_para_o_email_da_conta(ambiente):
    ambiente["ligar_smtp"]()
    api = ambiente["api"]

    r = api.post("/auth/telefone/solicitar-codigo", json={"telefone": "11988887777"})
    assert r.status_code == 200, r.text
    assert r.json()["codigo_dev"] is None  # o codigo nao aparece mais na tela
    assert "r*****e@gmail.com" in r.json()["detalhe"]

    assert len(ambiente["enviados"]) == 1
    enviado = ambiente["enviados"][0]
    assert enviado["para"] == "richard.teste@gmail.com"
    assert "entrar" in enviado["assunto"]

    r = api.post("/auth/telefone/verificar-codigo",
                 json={"telefone": "11988887777", "codigo": codigo_do_email(enviado["texto"])})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_login_de_conta_sem_email_pede_telefone_e_senha(ambiente):
    ambiente["ligar_smtp"]()
    r = ambiente["api"].post("/auth/telefone/solicitar-codigo", json={"telefone": "11966665555"})
    assert r.status_code == 400
    assert "telefone e a senha" in r.json()["detail"]
    assert ambiente["enviados"] == []


def test_falha_do_smtp_devolve_502_sem_mostrar_o_codigo(ambiente):
    ambiente["ligar_smtp"](falhar=True)
    r = ambiente["api"].post("/auth/telefone/solicitar-codigo", json={"telefone": "11988887777"})
    assert r.status_code == 502
    assert "codigo_dev" not in r.text


def test_modo_demonstracao_devolve_o_codigo_tambem(ambiente):
    ambiente["ligar_smtp"](mostrar=True)
    r = ambiente["api"].post("/auth/telefone/solicitar-codigo", json={"telefone": "11988887777"})
    assert r.status_code == 200
    assert r.json()["codigo_dev"] == codigo_do_email(ambiente["enviados"][0]["texto"])


def test_sem_smtp_o_codigo_continua_na_resposta(ambiente):
    r = ambiente["api"].post("/auth/telefone/solicitar-codigo", json={"telefone": "11966665555"})
    assert r.status_code == 200
    assert re.fullmatch(r"\d{6}", r.json()["codigo_dev"])


# ------------------------------------------------------------------ cadastro


def test_cadastro_manda_o_codigo_para_o_email_informado(ambiente):
    ambiente["ligar_smtp"]()
    api = ambiente["api"]
    dados = {"nome": "Nova Pessoa", "telefone": "11955554444", "senha": "senha123", "email": "nova@teste.com"}

    r = api.post("/auth/telefone/cadastro/solicitar-codigo", json=dados)
    assert r.status_code == 200, r.text
    assert r.json()["codigo_dev"] is None
    enviado = ambiente["enviados"][0]
    assert enviado["para"] == "nova@teste.com"
    assert "cadastro" in enviado["assunto"]

    r = api.post("/auth/telefone/cadastro/confirmar",
                 json={**dados, "codigo": codigo_do_email(enviado["texto"])})
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["email"] == "nova@teste.com"


def test_cadastro_sem_email_com_smtp_ativo(ambiente):
    ambiente["ligar_smtp"]()
    r = ambiente["api"].post("/auth/telefone/cadastro/solicitar-codigo",
                             json={"nome": "Nova Pessoa", "telefone": "11955554444", "senha": "senha123"})
    assert r.status_code == 400
    assert "e-mail" in r.json()["detail"]


def test_cadastro_com_email_de_outra_conta_nem_envia(ambiente):
    ambiente["ligar_smtp"]()
    r = ambiente["api"].post("/auth/telefone/cadastro/solicitar-codigo",
                             json={"nome": "Nova Pessoa", "telefone": "11955554444", "senha": "senha123",
                                   "email": "richard.teste@gmail.com"})
    assert r.status_code == 409
    assert ambiente["enviados"] == []


# ------------------------------------------------------------------ texto do e-mail


@pytest.mark.parametrize(
    "entrada, esperado",
    [("richardd.ferreira06@gmail.com", "r*****6@gmail.com"), ("ab@x.com", "a*@x.com"), ("ana@x.com", "a*a@x.com")],
)
def test_mascara_do_email(entrada, esperado):
    assert mascarar_email(entrada) == esperado


def test_texto_do_email_tem_codigo_e_validade():
    texto = montar_texto("Richard Ferreira", "123456", "cadastro", 5)
    assert "Olá, Richard!" in texto
    assert "123456" in texto
    assert "5 minutos" in texto
