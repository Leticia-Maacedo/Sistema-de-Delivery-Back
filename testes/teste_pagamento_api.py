"""Testes das rotas de pagamento e nota fiscal - Sprint 3 (backlog 18, 19 e 22).

Roda a API de verdade (TestClient) com um banco SQLite em memoria e o
gateway SIMULADO (sem ASAAS_API_KEY e sem SMTP): nao precisa de
PostgreSQL nem de internet. Cada teste monta o proprio pedido.

Cobre: cartao aprovado, cartao recusado (e nova tentativa), PIX (criacao,
consulta e pagamento), dinheiro na entrega (aceite e aprovacao na entrega),
metodo invalido (422), acesso de outro cliente (403) e a nota fiscal.

Executar:  python -m pytest testes/teste_pagamento_api.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.controllers import pagamento_controller
from app.core import nota_fiscal, notificacoes_pedido, pagamento_gateway
from app.core.pagamento_asaas import AsaasErro
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.entrega import Entrega
from app.models.item_pedido import ItemPedido
from app.models.local import Local
from app.models.pagamento import Pagamento
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

CARTAO_OK = {"titular": "CLIENTE TESTE", "numero": "5162306219378829",
             "mes_validade": "05", "ano_validade": "2030", "cvv": "318"}
CARTAO_RECUSADO = {**CARTAO_OK, "numero": "5184019740373151"}


@pytest.fixture
def ambiente(monkeypatch):
    """Banco em memoria, gateway simulado e login trocavel."""

    monkeypatch.setenv("ASAAS_API_KEY", "")
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # As tarefas em segundo plano (NF por e-mail, push) abrem sessao propria.
    monkeypatch.setattr(nota_fiscal, "SessionLocal", Sessao)
    monkeypatch.setattr(pagamento_controller, "SessionLocal", Sessao)
    monkeypatch.setattr(notificacoes_pedido, "SessionLocal", Sessao)

    logado = {"usuario_id": None}

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    def usuario_de_teste():
        with Sessao() as db:
            usuario = db.get(Usuario, logado["usuario_id"])
            db.expunge(usuario)
            return usuario

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste

    with Sessao() as db:
        agora = datetime.now()
        cliente = Usuario(nome="Cliente", email="cliente@teste.com", tipo="cliente", criado_em=agora)
        outro = Usuario(nome="Outro", email="outro@teste.com", tipo="cliente", criado_em=agora)
        dono = Usuario(nome="Dono", email="dono@teste.com", tipo="restaurante", criado_em=agora)
        entregador = Usuario(nome="Moto", email="moto@teste.com", tipo="entregador", criado_em=agora)
        db.add_all([cliente, outro, dono, entregador])
        db.flush()
        local = Local(usuario_id=dono.id, endereco="Rua A, 1", tipo="restaurante",
                      latitude=Decimal("-23.5"), longitude=Decimal("-46.6"), criado_em=agora)
        db.add(local)
        db.flush()
        restaurante = Restaurante(local_id=local.id, usuario_id=dono.id, nome_fantasia="Pizzaria Teste",
                                  cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                                  taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(restaurante)
        db.flush()
        produto = Produto(restaurante_id=restaurante.id, nome="Pizza", preco=Decimal("40.00"),
                          disponivel=True)
        db.add(produto)
        db.commit()
        ids = {"cliente": cliente.id, "outro": outro.id, "dono": dono.id,
               "entregador": entregador.id, "restaurante": restaurante.id, "produto": produto.id}

    def logar(quem: str) -> None:
        logado["usuario_id"] = ids[quem]

    def novo_pedido(forma_pagamento: str = "cartao", tipo_entrega: str = "delivery") -> int:
        with Sessao() as db:
            pedido = Pedido(cliente_id=ids["cliente"], restaurante_id=ids["restaurante"],
                            status="aguardando_aceite", tipo_entrega=tipo_entrega,
                            forma_pagamento=forma_pagamento, valor_total=Decimal("85.00"),
                            taxa_entrega=Decimal("5.00"), criado_em=datetime.now())
            db.add(pedido)
            db.flush()
            db.add(ItemPedido(pedido_id=pedido.id, produto_id=ids["produto"], quantidade=2,
                              preco_unitario=Decimal("40.00")))
            entrega = Entrega.nova(pedido.id)
            entrega.codigo_validacao = "1234"
            db.add(entrega)
            db.commit()
            return pedido.id

    def ler(modelo, **filtro):
        with Sessao() as db:
            return db.query(modelo).filter_by(**filtro).first()

    logar("cliente")
    yield {"api": TestClient(app), "logar": logar, "novo_pedido": novo_pedido, "ler": ler}

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def escolher(api, pedido_id, metodo):
    return api.put(f"/pagamentos/pedidos/{pedido_id}/metodo", json={"metodo": metodo})


# ------------------------------------------------------------------ cartao


def test_cartao_aprovado_emite_nota_e_libera_aceite(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")

    assert escolher(api, pedido_id, "cartao").status_code == 200
    r = api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status"] == "aprovado"
    assert corpo["gateway"] == "simulado"
    assert corpo["nota_fiscal"] == f"NF-{datetime.now().year}-{pedido_id:06d}"

    pagamento = ambiente["ler"](Pagamento, pedido_id=pedido_id)
    assert pagamento.status == "aprovado"
    assert "5162" not in (pagamento.mensagem or "") + (pagamento.transacao_externa_id or "")

    ambiente["logar"]("dono")
    r = api.patch(f"/pedidos/{pedido_id}/status", json={"status": "aceito"})
    assert r.status_code == 200, r.text


def test_cartao_recusado_mantem_pedido_aguardando_e_permite_tentar_de_novo(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")

    r = api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_RECUSADO})
    assert r.status_code == 201
    assert r.json()["status"] == "recusado"
    assert "nao autorizada" in r.json()["mensagem"]
    assert r.json()["nota_fiscal"] is None

    ambiente["logar"]("dono")
    r = api.patch(f"/pedidos/{pedido_id}/status", json={"status": "aceito"})
    assert r.status_code == 400
    assert ambiente["ler"](Pedido, id=pedido_id).status == "aguardando_aceite"

    ambiente["logar"]("cliente")
    r = api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})
    assert r.json()["status"] == "aprovado"

    r = api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})
    assert r.status_code == 409  # ja pago


def test_cartao_exige_forma_de_pagamento_cartao(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("pix")
    r = api.post("/pagamentos/cartao", json={"pedido_id": pedido_id})
    assert r.status_code == 400


# ------------------------------------------------------------------ PIX


def test_pix_gera_qrcode_consulta_e_aprova(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")

    assert escolher(api, pedido_id, "pix").status_code == 200
    r = api.post("/pagamentos/pix", json={"pedido_id": pedido_id})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status"] == "pendente"
    assert corpo["pix_copia_cola"]
    assert corpo["pix_qrcode"].startswith("data:image/png;base64,")

    r = api.get(f"/pagamentos/pedidos/{pedido_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "pendente"

    r = api.post(f"/pagamentos/pedidos/{pedido_id}/pix/simular-pagamento")
    assert r.status_code == 200
    assert r.json()["status"] == "aprovado"
    assert r.json()["nota_fiscal"]
    assert r.json()["pix_copia_cola"] is None

    assert ambiente["ler"](Pedido, id=pedido_id).cupom_fiscal == r.json()["nota_fiscal"]


# ------------------------------------------------------------------ dinheiro


def test_dinheiro_fica_a_receber_e_vira_aprovado_na_entrega(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao", "retirada")

    r = escolher(api, pedido_id, "dinheiro")
    assert r.status_code == 200
    assert r.json()["pagamento_status"] == "a_receber"

    ambiente["logar"]("dono")
    for etapa in ("aceito", "em_preparacao", "pronto_para_retirada"):
        r = api.patch(f"/pedidos/{pedido_id}/status", json={"status": etapa})
        assert r.status_code == 200, r.text

    r = api.post(f"/pedidos/{pedido_id}/entrega/confirmar", json={"codigo": "1234"})
    assert r.status_code == 200, r.text
    assert r.json()["nota_fiscal"]

    pagamento = ambiente["ler"](Pagamento, pedido_id=pedido_id)
    assert pagamento.status == "aprovado"


def test_trocar_dinheiro_por_cartao_bloqueia_o_aceite(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("dinheiro")
    escolher(api, pedido_id, "dinheiro")
    r = escolher(api, pedido_id, "cartao")
    assert r.json()["pagamento_status"] == "cancelado"

    ambiente["logar"]("dono")
    assert api.patch(f"/pedidos/{pedido_id}/status", json={"status": "aceito"}).status_code == 400


# ------------------------------------------------------------------ validacoes e acesso


def test_metodo_invalido_devolve_422(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]()
    assert escolher(api, pedido_id, "boleto").status_code == 422
    assert api.post("/pedidos", json={"forma_pagamento": "boleto"}).status_code == 422


def test_outro_cliente_nao_acessa_pagamento_nem_nota(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    ambiente["logar"]("outro")
    assert escolher(api, pedido_id, "pix").status_code == 403
    assert api.post("/pagamentos/cartao", json={"pedido_id": pedido_id}).status_code == 403
    assert api.get(f"/pagamentos/pedidos/{pedido_id}").status_code == 403
    assert api.get(f"/pagamentos/pedidos/{pedido_id}/nota-fiscal").status_code == 403

    ambiente["logar"]("entregador")
    assert api.get(f"/pagamentos/pedidos/{pedido_id}/nota-fiscal").status_code == 403


# ------------------------------------------------------------------ nota fiscal


def test_nota_fiscal_em_pdf_para_cliente_e_restaurante(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")

    assert api.get(f"/pagamentos/pedidos/{pedido_id}/nota-fiscal").status_code == 404  # sem pagamento

    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})
    r = api.get(f"/pagamentos/pedidos/{pedido_id}/nota-fiscal")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]

    ambiente["logar"]("dono")
    assert api.get(f"/pagamentos/pedidos/{pedido_id}/nota-fiscal").status_code == 200

    detalhe = api.get(f"/pedidos/{pedido_id}").json()
    assert detalhe["nota_fiscal"] == f"NF-{datetime.now().year}-{pedido_id:06d}"


# ------------------------------------------------------------------ RN04: cancelamento pelo cliente


def test_cliente_cancela_pedido_pago_e_o_valor_e_estornado(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    r = api.post(f"/pedidos/{pedido_id}/cancelar")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelado"
    assert r.json()["pagamento_status"] == "estornado"
    assert ambiente["ler"](Pagamento, pedido_id=pedido_id).status == "estornado"


def test_cliente_cancela_pix_pendente_e_dinheiro(ambiente):
    api = ambiente["api"]

    pix = ambiente["novo_pedido"]("pix")
    escolher(api, pix, "pix")
    api.post("/pagamentos/pix", json={"pedido_id": pix})
    assert api.post(f"/pedidos/{pix}/cancelar").json()["pagamento_status"] == "cancelado"

    dinheiro = ambiente["novo_pedido"]("dinheiro")
    escolher(api, dinheiro, "dinheiro")
    assert api.post(f"/pedidos/{dinheiro}/cancelar").json()["pagamento_status"] == "cancelado"

    sem_pagamento = ambiente["novo_pedido"]("cartao")
    r = api.post(f"/pedidos/{sem_pagamento}/cancelar")
    assert r.status_code == 200
    assert r.json()["pagamento_status"] is None


def test_cliente_nao_cancela_depois_do_aceite(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})
    ambiente["logar"]("dono")
    assert api.patch(f"/pedidos/{pedido_id}/status", json={"status": "aceito"}).status_code == 200

    ambiente["logar"]("cliente")
    r = api.post(f"/pedidos/{pedido_id}/cancelar")
    assert r.status_code == 400
    assert "aguarda o aceite" in r.json()["detail"]
    assert ambiente["ler"](Pedido, id=pedido_id).status == "aceito"
    assert ambiente["ler"](Pagamento, pedido_id=pedido_id).status == "aprovado"


def test_cancelar_duas_vezes_e_recusado(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    assert api.post(f"/pedidos/{pedido_id}/cancelar").status_code == 200
    r = api.post(f"/pedidos/{pedido_id}/cancelar")
    assert r.status_code == 400
    assert "ja esta cancelado" in r.json()["detail"]


def test_so_o_cliente_dono_cancela(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")

    ambiente["logar"]("outro")
    assert api.post(f"/pedidos/{pedido_id}/cancelar").status_code == 403

    ambiente["logar"]("dono")  # restaurante usa PATCH /status, nao esta rota
    assert api.post(f"/pedidos/{pedido_id}/cancelar").status_code == 403

    assert api.post("/pedidos/99999/cancelar").status_code in (403, 404)
    assert ambiente["ler"](Pedido, id=pedido_id).status == "aguardando_aceite"


def test_restaurante_cancela_pedido_pago_e_estorna(ambiente):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    ambiente["logar"]("dono")
    api.patch(f"/pedidos/{pedido_id}/status", json={"status": "aceito"})
    r = api.patch(f"/pedidos/{pedido_id}/status", json={"status": "cancelado"})
    assert r.status_code == 200, r.text
    assert r.json()["pagamento_status"] == "estornado"


def test_estorno_recusado_pelo_asaas_fica_pendente_e_e_refeito(ambiente, monkeypatch):
    api, pedido_id = ambiente["api"], ambiente["novo_pedido"]("cartao")
    api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    def asaas_ocupado(_):
        raise AsaasErro("Nao e possivel solicitar estorno no momento.")

    monkeypatch.setattr(pagamento_gateway, "estornar", asaas_ocupado)
    monkeypatch.setattr(pagamento_controller, "INTERVALO_ESTORNO_SEGUNDOS", 0)

    r = api.post(f"/pedidos/{pedido_id}/cancelar")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelado"  # o cancelamento nunca trava
    assert r.json()["pagamento_status"] == "estorno_pendente"

    monkeypatch.setattr(pagamento_gateway, "estornar", lambda _: None)  # Asaas liberou
    r = api.get(f"/pagamentos/pedidos/{pedido_id}")
    assert r.json()["status"] == "estornado"
