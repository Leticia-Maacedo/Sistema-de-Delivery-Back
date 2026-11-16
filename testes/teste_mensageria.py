"""Testes do envio de SMS (Twilio) e WhatsApp (WhatsApp Business Platform) - Backlog.

Os servidores da Twilio e da Meta são simulados com httpx.MockTransport: o
teste confere exatamente a requisição que a API mandaria (URL, autenticação
e corpo) e o que acontece quando o serviço recusa ou cai.

Executar:  python -m pytest testes/teste_mensageria.py -v
"""

import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import mensageria, notificacoes_pedido
from app.core.config import get_settings
from app.core.database import Base
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

TWILIO = {"TWILIO_ACCOUNT_SID": "AC123", "TWILIO_AUTH_TOKEN": "segredo-twilio", "TWILIO_FROM": "+15005550006"}
META = {"WHATSAPP_TOKEN": "token-meta", "WHATSAPP_PHONE_NUMBER_ID": "1098765", "WHATSAPP_TEMPLATE": "entregafood_status_pedido"}


def configurar(monkeypatch, **valores):
    for k in list(TWILIO) + list(META) + ["MENSAGERIA_BASE_URL"]:
        monkeypatch.setenv(k, valores.get(k, ""))
    if "WHATSAPP_TEMPLATE" not in valores:
        monkeypatch.setenv("WHATSAPP_TEMPLATE", "")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def limpar_config():
    yield
    get_settings.cache_clear()


def servidor(chamadas, status=200):
    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas.append(req)
        if status == "cai":
            raise httpx.ConnectError("sem rede", request=req)
        return httpx.Response(status, json={"ok": True})
    return httpx.Client(transport=httpx.MockTransport(tratar))


# ------------------------------------------------------------ telefone
@pytest.mark.parametrize("entrada,saida", [
    ("(11) 99999-0000", "+5511999990000"), ("11999990000", "+5511999990000"), ("+55 11 99999-0000", "+5511999990000"),
    ("1133334444", "+551133334444"), ("", None), (None, None), ("12345", None), ("+1 415 555 0100", None),
])
def test_telefone_e164(entrada, saida):
    assert mensageria.telefone_e164(entrada) == saida


# ------------------------------------------------------------ canais
def test_sem_credenciais_fica_desligado(monkeypatch):
    configurar(monkeypatch)
    chamadas = []
    assert not mensageria.mensageria_ativa()
    assert mensageria.enviar_para_telefone("11999990000", "T", "x", servidor(chamadas)) == []
    assert chamadas == []


def test_sms_no_formato_da_twilio(monkeypatch):
    configurar(monkeypatch, **TWILIO)
    chamadas = []
    envios = mensageria.enviar_para_telefone("(11) 99999-0000", "Pedido #7: Saiu para entrega", "Tenha o código em mãos.", servidor(chamadas))
    assert [(e.canal, e.ok) for e in envios] == [("sms", True)]
    req = chamadas[0]
    assert str(req.url) == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert req.headers["authorization"].startswith("Basic ")
    form = parse_qs(req.content.decode())
    assert form["To"] == ["+5511999990000"] and form["From"] == ["+15005550006"]
    assert form["Body"] == ["EntregaFood - Pedido #7: Saiu para entrega: Tenha o código em mãos."]


def test_whatsapp_no_formato_da_meta(monkeypatch):
    configurar(monkeypatch, **META)
    chamadas = []
    envios = mensageria.enviar_para_telefone("11999990000", "Pedido #7: Entregue", "Bom apetite!", servidor(chamadas))
    assert [(e.canal, e.ok) for e in envios] == [("whatsapp", True)]
    req = chamadas[0]
    assert str(req.url) == "https://graph.facebook.com/v21.0/1098765/messages"
    assert req.headers["authorization"] == "Bearer token-meta"
    corpo = json.loads(req.content)
    assert corpo["messaging_product"] == "whatsapp" and corpo["to"] == "5511999990000" and corpo["type"] == "template"
    assert corpo["template"]["name"] == "entregafood_status_pedido" and corpo["template"]["language"] == {"code": "pt_BR"}
    assert [p["text"] for p in corpo["template"]["components"][0]["parameters"]] == ["Pedido #7: Entregue", "Bom apetite!"]


def test_os_dois_canais_juntos(monkeypatch):
    configurar(monkeypatch, **TWILIO, **META)
    chamadas = []
    envios = mensageria.enviar_para_telefone("11999990000", "T", "x", servidor(chamadas))
    assert [e.canal for e in envios] == ["sms", "whatsapp"] and len(chamadas) == 2


@pytest.mark.parametrize("status,detalhe", [(400, "HTTP 400"), (401, "HTTP 401"), (503, "HTTP 503"), ("cai", "serviço indisponível")])
def test_falha_do_servico_nao_levanta_erro(monkeypatch, status, detalhe):
    configurar(monkeypatch, **TWILIO)
    envios = mensageria.enviar_para_telefone("11999990000", "T", "x", servidor([], status))
    assert len(envios) == 1 and not envios[0].ok and envios[0].detalhe == detalhe


def test_base_url_dos_testes(monkeypatch):
    configurar(monkeypatch, **META, MENSAGERIA_BASE_URL="http://127.0.0.1:8014/")
    chamadas = []
    mensageria.enviar_para_telefone("11999990000", "T", "x", servidor(chamadas))
    assert str(chamadas[0].url) == "http://127.0.0.1:8014/v21.0/1098765/messages"


# ------------------------------------------------------------ no fluxo do pedido
@pytest.fixture
def banco(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(notificacoes_pedido, "SessionLocal", Sessao)
    with Sessao() as db:
        agora = datetime.now()
        cliente = Usuario(nome="Ana", email="a@teste.com", tipo="cliente", telefone="(11) 98888-7777", criado_em=agora)
        dono = Usuario(nome="Dono", email="d@teste.com", tipo="restaurante", telefone="11977776666", criado_em=agora)
        sem_tel = Usuario(nome="Bia", email="b@teste.com", tipo="cliente", criado_em=agora)
        db.add_all([cliente, dono, sem_tel])
        db.flush()
        loc = Local(usuario_id=dono.id, endereco="Rua A, 1", tipo="restaurante", latitude=Decimal("-23.5"), longitude=Decimal("-46.6"), criado_em=agora)
        db.add(loc)
        db.flush()
        rest = Restaurante(local_id=loc.id, usuario_id=dono.id, nome_fantasia="Pizzaria", cnpj="12.345.678/0001-90",
                           status_aprovacao="aprovado", taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(rest)
        db.flush()
        pedidos = {}
        for chave, u in (("ana", cliente), ("bia", sem_tel)):
            p = Pedido(cliente_id=u.id, restaurante_id=rest.id, status="em_transito", tipo_entrega="delivery", forma_pagamento="pix",
                       valor_total=Decimal("40.00"), taxa_entrega=Decimal("5.00"), criado_em=agora)
            db.add(p)
            db.flush()
            pedidos[chave] = p.id
        db.commit()
    return pedidos


def test_mudanca_de_status_avisa_so_o_cliente_por_sms_e_whatsapp(monkeypatch, banco):
    configurar(monkeypatch, **TWILIO, **META)
    chamadas = []
    monkeypatch.setattr(mensageria, "_cliente", lambda: servidor(chamadas))
    notificacoes_pedido.notificar_pedido_criado(banco["ana"])  # vai para o cliente e para o restaurante
    destinos = {(r.url.host, parse_qs(r.content.decode()).get("To", [None])[0] if r.url.host == "api.twilio.com" else json.loads(r.content)["to"]) for r in chamadas}
    assert destinos == {("api.twilio.com", "+5511988887777"), ("graph.facebook.com", "5511988887777")}  # o dono (restaurante) não recebe


def test_cliente_sem_telefone_nao_recebe(monkeypatch, banco):
    configurar(monkeypatch, **TWILIO)
    chamadas = []
    monkeypatch.setattr(mensageria, "_cliente", lambda: servidor(chamadas))
    notificacoes_pedido.notificar_mudanca_status(banco["bia"])
    assert chamadas == []


def test_servico_fora_do_ar_nao_quebra_o_fluxo(monkeypatch, banco):
    configurar(monkeypatch, **TWILIO, **META)
    monkeypatch.setattr(mensageria, "_cliente", lambda: servidor([], "cai"))
    notificacoes_pedido.notificar_mudanca_status(banco["ana"])  # não levanta erro
