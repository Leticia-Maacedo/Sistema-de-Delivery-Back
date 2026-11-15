"""Testes dos avisos pelo Telegram - Backlog.

O servidor do Telegram é simulado (httpx.MockTransport): getMe, getUpdates
(com as mensagens "/start <código>" que o cliente mandaria) e sendMessage.

Executar:  python -m pytest testes/teste_telegram.py -v
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import notificacoes_pedido, telegram
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

TOKEN = "123456:ABCdefTOKENdeTESTE"


class TelegramFalso:
    """Guarda as mensagens enviadas e entrega as atualizações que o teste colocar."""

    def __init__(self):
        self.enviadas, self.fila, self.urls, self.bloqueados, self.proximo = [], [], [], set(), 1

    def start(self, chat_id, texto):
        self.fila.append({"update_id": self.proximo, "message": {"chat": {"id": chat_id}, "text": texto}})
        self.proximo += 1

    def tratar(self, req: httpx.Request) -> httpx.Response:
        self.urls.append(str(req.url))
        metodo = req.url.path.rsplit("/", 1)[-1]
        dados = json.loads(req.content or b"{}")
        if metodo == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "entregafood_teste_bot"}})
        if metodo == "getUpdates":
            offset = dados.get("offset")
            if offset is not None:
                self.fila = [u for u in self.fila if u["update_id"] >= offset]
            return httpx.Response(200, json={"ok": True, "result": list(self.fila)})
        if metodo == "sendMessage":
            if str(dados["chat_id"]) in self.bloqueados:
                return httpx.Response(403, json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
            self.enviadas.append((str(dados["chat_id"]), dados["text"]))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.enviadas)}})
        return httpx.Response(404, json={"ok": False, "description": "Not Found"})


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    for k in ("TWILIO_ACCOUNT_SID", "WHATSAPP_TOKEN"):
        monkeypatch.setenv(k, "")
    get_settings.cache_clear()
    falso = TelegramFalso()
    monkeypatch.setattr(telegram, "_cliente", lambda: httpx.Client(transport=httpx.MockTransport(falso.tratar)))
    monkeypatch.setattr(telegram, "_estado", {"bot": None, "offset": None})

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(notificacoes_pedido, "SessionLocal", Sessao)
    logado = {"id": None}

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    def usuario_de_teste():
        with Sessao() as db:
            u = db.get(Usuario, logado["id"])
            db.expunge(u)
            return u

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste
    with Sessao() as db:
        agora = datetime.now()
        ana = Usuario(nome="Ana", email="ana@teste.com", tipo="cliente", criado_em=agora)
        bia = Usuario(nome="Bia", email="bia@teste.com", tipo="cliente", criado_em=agora)
        dono = Usuario(nome="Dono", email="dono@teste.com", tipo="restaurante", criado_em=agora)
        db.add_all([ana, bia, dono])
        db.flush()
        loc = Local(usuario_id=dono.id, endereco="Rua A, 1", tipo="restaurante", latitude=Decimal("-23.5"), longitude=Decimal("-46.6"), criado_em=agora)
        db.add(loc)
        db.flush()
        rest = Restaurante(local_id=loc.id, usuario_id=dono.id, nome_fantasia="Pizzaria", cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                           taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(rest)
        db.flush()
        pedido = Pedido(cliente_id=ana.id, restaurante_id=rest.id, status="em_preparacao", tipo_entrega="delivery", forma_pagamento="pix",
                        valor_total=Decimal("40.00"), taxa_entrega=Decimal("5.00"), criado_em=agora)
        db.add(pedido)
        db.commit()
        ids = {"ana": ana.id, "bia": bia.id, "dono": dono.id, "pedido": pedido.id}

    def logar(quem):
        logado["id"] = ids[quem]

    def usuario(quem):
        with Sessao() as db:
            return db.get(Usuario, ids[quem])

    yield {"api": TestClient(app), "falso": falso, "logar": logar, "usuario": usuario, "ids": ids, "Sessao": Sessao}
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _vincular(amb, quem, chat_id):
    amb["logar"](quem)
    r = amb["api"].post("/notificacoes/telegram/vincular")
    assert r.status_code == 200, r.text
    codigo = r.json()["link"].split("start=")[1]
    amb["falso"].start(chat_id, f"/start {codigo}")
    return amb["api"].post("/notificacoes/telegram/confirmar")


def test_sem_token_fica_desligado(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()
    assert not telegram.telegram_ativo()
    get_settings.cache_clear()


def test_situacao_e_link_com_o_nome_do_bot(ambiente):
    ambiente["logar"]("ana")
    assert ambiente["api"].get("/notificacoes/telegram").json() == {"disponivel": True, "vinculado": False}
    r = ambiente["api"].post("/notificacoes/telegram/vincular").json()
    assert r["link"].startswith("https://t.me/entregafood_teste_bot?start=")
    codigo = r["link"].split("start=")[1]
    assert len(codigo) >= 16 and all(c.isalnum() or c in "-_" for c in codigo)
    assert any(f"/bot{TOKEN}/getMe" in u for u in ambiente["falso"].urls)


def test_vincular_liga_a_conta_e_da_boas_vindas(ambiente):
    r = _vincular(ambiente, "ana", 555001)
    assert r.json() == {"disponivel": True, "vinculado": True}
    u = ambiente["usuario"]("ana")
    assert u.telegram_chat_id == "555001" and u.telegram_codigo is None
    assert ambiente["falso"].enviadas[-1] == ("555001", telegram.BOAS_VINDAS)


def test_codigo_de_outra_pessoa_ou_vencido_nao_liga(ambiente):
    api, falso = ambiente["api"], ambiente["falso"]
    ambiente["logar"]("ana")
    codigo = api.post("/notificacoes/telegram/vincular").json()["link"].split("start=")[1]
    falso.start(777, "/start codigo-inventado")
    falso.start(778, "/start")
    ambiente["logar"]("bia")
    assert api.post("/notificacoes/telegram/confirmar").json()["vinculado"] is False
    assert ambiente["usuario"]("ana").telegram_chat_id is None
    assert [c for c, _ in falso.enviadas] == ["777", "778"]  # ambos recebem a orientação
    with ambiente["Sessao"]() as db:  # vence o código da Ana
        db.get(Usuario, ambiente["ids"]["ana"]).telegram_codigo_expira = datetime.now() - timedelta(minutes=1)
        db.commit()
    falso.start(555, f"/start {codigo}")
    ambiente["logar"]("ana")
    assert api.post("/notificacoes/telegram/confirmar").json()["vinculado"] is False
    assert "expirou" in falso.enviadas[-1][1]


def test_mensagens_lidas_nao_sao_processadas_de_novo(ambiente):
    _vincular(ambiente, "ana", 555001)
    total = len(ambiente["falso"].enviadas)
    ambiente["api"].post("/notificacoes/telegram/confirmar")
    assert len(ambiente["falso"].enviadas) == total and ambiente["falso"].fila == []


def test_mudanca_de_status_chega_no_telegram_so_do_cliente(ambiente):
    _vincular(ambiente, "ana", 555001)
    _vincular(ambiente, "dono", 999)  # o dono também ligou, mas avisos por Telegram são do cliente
    antes = len(ambiente["falso"].enviadas)
    notificacoes_pedido.notificar_mudanca_status(ambiente["ids"]["pedido"])
    novas = ambiente["falso"].enviadas[antes:]
    assert novas == [("555001", f"Pedido #{ambiente['ids']['pedido']}: Em preparação\nSeu pedido está sendo preparado.")]


def test_bot_bloqueado_desliga_o_vinculo(ambiente):
    _vincular(ambiente, "ana", 555001)
    ambiente["falso"].bloqueados.add("555001")
    notificacoes_pedido.notificar_mudanca_status(ambiente["ids"]["pedido"])  # não levanta erro
    assert ambiente["usuario"]("ana").telegram_chat_id is None


def test_desvincular(ambiente):
    _vincular(ambiente, "ana", 555001)
    assert ambiente["api"].delete("/notificacoes/telegram").status_code == 204
    assert ambiente["api"].get("/notificacoes/telegram").json()["vinculado"] is False


def test_telegram_fora_do_ar(ambiente, monkeypatch):
    def cai(req):
        raise httpx.ConnectError("sem rede", request=req)
    monkeypatch.setattr(telegram, "_cliente", lambda: httpx.Client(transport=httpx.MockTransport(cai)))
    ambiente["logar"]("ana")
    r = ambiente["api"].post("/notificacoes/telegram/vincular")
    assert r.status_code == 502 and "Telegram indisponível" in r.json()["detail"]
