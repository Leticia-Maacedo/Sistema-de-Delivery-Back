"""Testes do push no app mobile pelo Firebase Cloud Messaging - Sprint 4.

Roda sem Firebase de verdade: as respostas do Google sao falsas
(httpx.MockTransport) e a chave da conta de servico e gerada no teste.
O banco e SQLite em memoria.

Cobre: leitura das credenciais (JSON e base64); formato da mensagem;
envio para os celulares do usuario; token invalido apagado; sem
credenciais nao envia; rota que registra/atualiza/remove o token; e o
disparo do aviso do pedido pelos dois canais (navegador e app).

Executar:  python -m pytest testes/teste_push_fcm.py -v
"""

import base64
import json
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import notificacoes_pedido, push_fcm
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.push_token_fcm import PushTokenFCM
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

TOKEN_A = "token-celular-a-" + "x" * 40
TOKEN_B = "token-celular-b-" + "y" * 40


def credenciais_falsas() -> str:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps({
        "type": "service_account",
        "project_id": "entregafood-teste",
        "client_email": "push@entregafood-teste.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    })


@pytest.fixture
def banco(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(notificacoes_pedido, "SessionLocal", Sessao)
    push_fcm._cache_token.update({"valor": None, "expira": 0.0})

    with Sessao() as db:
        agora = datetime.now()
        cliente = Usuario(nome="Cliente", email="c@teste.com", tipo="cliente", criado_em=agora)
        outro = Usuario(nome="Outro", email="o@teste.com", tipo="cliente", criado_em=agora)
        dono = Usuario(nome="Dono", email="d@teste.com", tipo="restaurante", criado_em=agora)
        db.add_all([cliente, outro, dono])
        db.flush()
        local = Local(usuario_id=dono.id, endereco="Rua A, 1", tipo="restaurante",
                      latitude=Decimal("-23.5"), longitude=Decimal("-46.6"), criado_em=agora)
        db.add(local)
        db.flush()
        restaurante = Restaurante(local_id=local.id, usuario_id=dono.id, nome_fantasia="Pizzaria",
                                  cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                                  taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(restaurante)
        db.flush()
        pedido = Pedido(cliente_id=cliente.id, restaurante_id=restaurante.id, status="aguardando_aceite",
                        tipo_entrega="delivery", forma_pagamento="cartao", valor_total=Decimal("50.00"),
                        taxa_entrega=Decimal("5.00"), criado_em=agora)
        db.add(pedido)
        db.commit()
        ids = {"cliente": cliente.id, "outro": outro.id, "dono": dono.id, "pedido": pedido.id}

    yield {"Sessao": Sessao, "ids": ids}
    get_settings.cache_clear()


@pytest.fixture
def com_firebase(monkeypatch):
    monkeypatch.setenv("FIREBASE_CREDENCIAIS", credenciais_falsas())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def google_falso(chamadas, tokens_invalidos=()):
    def tratar(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        if requisicao.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "acesso-123", "expires_in": 3600})
        mensagem = json.loads(requisicao.content)["message"]
        if mensagem["token"] in tokens_invalidos:
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": [
                {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]}})
        return httpx.Response(200, json={"name": "projects/entregafood-teste/messages/1"})

    return httpx.Client(transport=httpx.MockTransport(tratar))


# ------------------------------------------------------------------ credenciais e mensagem


def test_sem_credenciais_fcm_fica_desligado(monkeypatch):
    monkeypatch.setenv("FIREBASE_CREDENCIAIS", "")
    get_settings.cache_clear()
    assert not push_fcm.fcm_ativo()
    get_settings.cache_clear()


def test_credenciais_em_json_e_em_base64(monkeypatch):
    texto = credenciais_falsas()
    for valor in (texto, base64.b64encode(texto.encode()).decode()):
        monkeypatch.setenv("FIREBASE_CREDENCIAIS", valor)
        get_settings.cache_clear()
        cred = push_fcm.ler_credenciais()
        assert cred.projeto == "entregafood-teste"
    get_settings.cache_clear()


def test_credencial_invalida_nao_quebra(monkeypatch):
    monkeypatch.setenv("FIREBASE_CREDENCIAIS", "{nao e json")
    get_settings.cache_clear()
    assert push_fcm.ler_credenciais() is None
    get_settings.cache_clear()


def test_mensagem_no_formato_v1_com_dados_em_texto():
    corpo = push_fcm.montar_mensagem("tok", titulo="Pedido #7", corpo="Saiu para entrega",
                                     dados={"pedido_id": 7, "status": "em_transito"})
    mensagem = corpo["message"]
    assert mensagem["token"] == "tok"
    assert mensagem["notification"] == {"title": "Pedido #7", "body": "Saiu para entrega"}
    assert mensagem["data"] == {"pedido_id": "7", "status": "em_transito"}
    assert mensagem["android"]["priority"] == "high"


# ------------------------------------------------------------------ envio


def test_envia_para_todos_os_celulares_e_apaga_token_invalido(banco, com_firebase):
    Sessao, ids = banco["Sessao"], banco["ids"]
    with Sessao() as db:
        PushTokenFCM.salvar(db, usuario_id=ids["cliente"], token=TOKEN_A, plataforma="android")
        PushTokenFCM.salvar(db, usuario_id=ids["cliente"], token=TOKEN_B, plataforma="android")

        chamadas = []
        enviados = push_fcm.enviar_para_usuario_fcm(
            db, ids["cliente"], titulo="Pedido #1", corpo="Recebido",
            dados={"pedido_id": 1}, http=google_falso(chamadas, tokens_invalidos={TOKEN_B}),
        )

        assert enviados == 1
        assert [c.url.host for c in chamadas].count("oauth2.googleapis.com") == 1
        envio = [c for c in chamadas if c.url.host == "fcm.googleapis.com"][0]
        assert envio.url.path == "/v1/projects/entregafood-teste/messages:send"
        assert envio.headers["Authorization"] == "Bearer acesso-123"
        assert PushTokenFCM.buscar_por_token(db, TOKEN_B) is None  # apagado
        assert PushTokenFCM.buscar_por_token(db, TOKEN_A) is not None


def test_sem_firebase_nao_chama_o_google(banco, monkeypatch):
    monkeypatch.setenv("FIREBASE_CREDENCIAIS", "")
    get_settings.cache_clear()
    Sessao, ids = banco["Sessao"], banco["ids"]
    with Sessao() as db:
        PushTokenFCM.salvar(db, usuario_id=ids["cliente"], token=TOKEN_A, plataforma="android")
        chamadas = []
        assert push_fcm.enviar_para_usuario_fcm(db, ids["cliente"], titulo="t", corpo="c",
                                                http=google_falso(chamadas)) == 0
        assert chamadas == []


def test_aviso_do_pedido_vai_tambem_para_o_app(banco, monkeypatch):
    enviados = []
    monkeypatch.setattr(notificacoes_pedido, "push_ativo", lambda: False)
    monkeypatch.setattr(notificacoes_pedido, "fcm_ativo", lambda: True)
    monkeypatch.setattr(notificacoes_pedido, "enviar_para_usuario_fcm",
                        lambda db, usuario_id, **kw: enviados.append((usuario_id, kw)) or 1)

    notificacoes_pedido.notificar_pedido_criado(banco["ids"]["pedido"])

    destinos = {usuario_id for usuario_id, _ in enviados}
    assert destinos == {banco["ids"]["cliente"], banco["ids"]["dono"]}
    _, kw = enviados[0]
    assert kw["dados"]["pedido_id"] == banco["ids"]["pedido"]
    assert "#" in kw["titulo"]


# ------------------------------------------------------------------ rota


@pytest.fixture
def api(banco):
    Sessao = banco["Sessao"]
    logado = {"id": banco["ids"]["cliente"]}

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    def usuario_de_teste():
        with Sessao() as db:
            usuario = db.get(Usuario, logado["id"])
            db.expunge(usuario)
            return usuario

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste
    yield {"cliente": TestClient(app), "logado": logado, **banco}
    app.dependency_overrides.clear()


def test_rota_registra_atualiza_e_remove_o_token(api):
    cliente, Sessao, ids = api["cliente"], api["Sessao"], api["ids"]

    r = cliente.post("/notificacoes/fcm", json={"token": TOKEN_A})
    assert r.status_code == 201, r.text
    assert r.json()["plataforma"] == "android"

    assert cliente.post("/notificacoes/fcm", json={"token": TOKEN_A}).status_code == 200  # ja conhecido

    api["logado"]["id"] = ids["outro"]  # mesmo celular, outra conta
    assert cliente.post("/notificacoes/fcm", json={"token": TOKEN_A, "plataforma": "ios"}).status_code == 200
    with Sessao() as db:
        registro = PushTokenFCM.buscar_por_token(db, TOKEN_A)
        assert registro.usuario_id == ids["outro"] and registro.plataforma == "ios"

    assert cliente.request("DELETE", "/notificacoes/fcm", json={"token": TOKEN_A}).status_code == 204
    with Sessao() as db:
        assert PushTokenFCM.buscar_por_token(db, TOKEN_A) is None


def test_rota_recusa_token_curto_e_plataforma_invalida(api):
    cliente = api["cliente"]
    assert cliente.post("/notificacoes/fcm", json={"token": "curto"}).status_code == 422
    assert cliente.post("/notificacoes/fcm", json={"token": TOKEN_A, "plataforma": "windows"}).status_code == 422


def test_outro_usuario_nao_remove_o_token(api):
    cliente, Sessao, ids = api["cliente"], api["Sessao"], api["ids"]
    cliente.post("/notificacoes/fcm", json={"token": TOKEN_A})
    api["logado"]["id"] = ids["outro"]
    cliente.request("DELETE", "/notificacoes/fcm", json={"token": TOKEN_A})
    with Sessao() as db:
        assert PushTokenFCM.buscar_por_token(db, TOKEN_A).usuario_id == ids["cliente"]
