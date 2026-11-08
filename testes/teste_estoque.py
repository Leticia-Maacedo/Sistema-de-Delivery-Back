"""Testes do estoque de produtos - Sprint 4.

Roda a API de verdade (TestClient) com SQLite em memoria.

Cobre:
    - estrutura: produto nasce sem controle (estoque null) ou com estoque;
    - endpoints: consultar (GET), definir/desligar (PUT) e entrada/saida
      (PATCH) do estoque, so pelo dono do restaurante;
    - validacao: cesta e fechamento recusam quantidade maior que o estoque;
    - baixa: criar o pedido tira as unidades do estoque;
    - concorrencia: se o estoque acabou depois do resumo, o pedido e
      recusado (409) e nada fica gravado;
    - cancelamento: pelo cliente ou pelo restaurante devolve as unidades;
    - esgotado: some do cardapio do cliente;
    - produto sem controle continua vendendo como antes.

Executar:  python -m pytest testes/teste_estoque.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import notificacoes_pedido
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.item_pedido import ItemPedido
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

RETIRADA = {"forma_pagamento": "dinheiro", "tipo_entrega": "retirada"}


# ------------------------------------------------------------ regras puras
def test_mensagens_de_estoque():
    assert Produto(nome="X", estoque=None).problema_de_estoque(500) is None
    assert Produto(nome="X", estoque=3).problema_de_estoque(3) is None
    assert "So ha 3 unidades de 'X'" in Produto(nome="X", estoque=3).problema_de_estoque(4)
    assert "1 unidade de" in Produto(nome="X", estoque=1).problema_de_estoque(2)
    assert "esgotado" in Produto(nome="X", estoque=0).problema_de_estoque(1)
    assert Produto(estoque=0).esgotado and not Produto(estoque=None).esgotado


# --------------------------------------------------------------- pela API
@pytest.fixture
def ambiente(monkeypatch):
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
            usuario = db.get(Usuario, logado["id"])
            db.expunge(usuario)
            return usuario

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste

    with Sessao() as db:
        agora = datetime.now()
        pessoas = {t: Usuario(nome=t.title(), email=f"{t}@teste.com", tipo=tp, criado_em=agora)
                   for t, tp in (("dono", "restaurante"), ("outro_dono", "restaurante"),
                                 ("cliente", "cliente"), ("cliente2", "cliente"))}
        db.add_all(pessoas.values())
        db.flush()
        loja = Local(usuario_id=pessoas["dono"].id, endereco="Av. Paulista, 1000", tipo="restaurante",
                     latitude=Decimal("-23.561414"), longitude=Decimal("-46.655881"), criado_em=agora)
        db.add(loja)
        db.flush()
        rest = Restaurante(local_id=loja.id, usuario_id=pessoas["dono"].id, nome_fantasia="Burger",
                           cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                           taxa_entrega_km=Decimal("2.00"), ativo=True, criado_em=agora)
        db.add(rest)
        db.flush()
        lanche = Produto(restaurante_id=rest.id, nome="Lanche", preco=Decimal("30.00"), disponivel=True, estoque=5)
        suco = Produto(restaurante_id=rest.id, nome="Suco", preco=Decimal("8.00"), disponivel=True)  # sem controle
        db.add_all([lanche, suco])
        db.commit()
        ids = {k: v.id for k, v in pessoas.items()} | {
            "restaurante": rest.id, "lanche": lanche.id, "suco": suco.id}

    def logar(quem):
        logado["id"] = ids[quem]

    def estoque(produto):
        with Sessao() as db:
            return db.get(Produto, ids[produto]).estoque

    def gravar_estoque(produto, valor):
        with Sessao() as db:
            db.get(Produto, ids[produto]).estoque = valor
            db.commit()

    def contar_pedidos():
        with Sessao() as db:
            return db.query(Pedido).count(), db.query(ItemPedido).count()

    yield {"api": TestClient(app), "ids": ids, "logar": logar, "estoque": estoque,
           "gravar_estoque": gravar_estoque, "contar_pedidos": contar_pedidos}
    app.dependency_overrides.clear()


def _comprar(ambiente, produto, quantidade, quem="cliente"):
    """Coloca na cesta e fecha o pedido (retirada, dinheiro). Devolve a resposta do pedido."""
    api = ambiente["api"]
    ambiente["logar"](quem)
    r = api.post("/cesta/itens", json={"produto_id": ambiente["ids"][produto], "quantidade": quantidade})
    assert r.status_code == 201, r.text
    return api.post("/pedidos", json=RETIRADA)


# ---- estrutura e endpoints
def test_produto_novo_com_e_sem_estoque(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    rid = ambiente["ids"]["restaurante"]
    r = api.post("/produtos", json={"restaurante_id": rid, "nome": "Batata", "preco": 12})
    assert r.status_code == 201 and r.json()["estoque"] is None
    r = api.post("/parceiro/produtos", json={"nome": "Torta", "preco": 9, "estoque": 7})
    assert r.status_code == 201 and r.json()["estoque"] == 7
    assert api.post("/produtos", json={"restaurante_id": rid, "nome": "Erro", "preco": 1, "estoque": -1}).status_code == 422


def test_consultar_estoque_e_publico(ambiente):
    ambiente["logar"]("cliente")
    r = ambiente["api"].get(f"/produtos/{ambiente['ids']['lanche']}/estoque")
    assert r.status_code == 200
    assert r.json() == {"produto_id": ambiente["ids"]["lanche"], "nome": "Lanche", "disponivel": True,
                        "controla_estoque": True, "estoque": 5, "esgotado": False}
    r = ambiente["api"].get(f"/produtos/{ambiente['ids']['suco']}/estoque")
    assert r.json()["controla_estoque"] is False and r.json()["estoque"] is None
    assert ambiente["api"].get("/produtos/9999/estoque").status_code == 404


def test_dono_define_ajusta_e_desliga_estoque(ambiente):
    api = ambiente["api"]
    url = f"/produtos/{ambiente['ids']['lanche']}/estoque"
    ambiente["logar"]("dono")
    assert api.put(url, json={"estoque": 20}).json()["estoque"] == 20
    assert api.patch(url, json={"ajuste": 5}).json()["estoque"] == 25      # entrada
    assert api.patch(url, json={"ajuste": -10}).json()["estoque"] == 15    # saida
    r = api.patch(url, json={"ajuste": -16})                               # nao fica negativo
    assert r.status_code == 400 and "15" in r.json()["detail"]
    assert ambiente["estoque"]("lanche") == 15
    assert api.patch(url, json={"ajuste": 0}).status_code == 400
    r = api.put(url, json={"estoque": None})                               # desliga
    assert r.json()["controla_estoque"] is False
    assert api.patch(url, json={"ajuste": 1}).status_code == 400           # sem controle nao ajusta
    assert api.put(url, json={"estoque": -1}).status_code == 422


def test_estoque_pelo_put_do_produto(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    pid = ambiente["ids"]["lanche"]
    assert api.put(f"/parceiro/produtos/{pid}", json={"estoque": 8}).json()["estoque"] == 8
    assert api.put(f"/parceiro/produtos/{pid}", json={"preco": 31}).json()["estoque"] == 8  # omitir nao mexe
    assert api.put(f"/produtos/{pid}", json={"estoque": None}).json()["estoque"] is None


def test_so_o_dono_mexe_no_estoque(ambiente):
    api = ambiente["api"]
    url = f"/produtos/{ambiente['ids']['lanche']}/estoque"
    for quem in ("outro_dono", "cliente"):
        ambiente["logar"](quem)
        assert api.put(url, json={"estoque": 99}).status_code == 403
        assert api.patch(url, json={"ajuste": 99}).status_code == 403
    assert ambiente["estoque"]("lanche") == 5


# ---- validacao antes de confirmar
def test_cesta_recusa_mais_que_o_estoque(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("cliente")
    lanche = ambiente["ids"]["lanche"]
    r = api.post("/cesta/itens", json={"produto_id": lanche, "quantidade": 6})
    assert r.status_code == 400 and "So ha 5 unidades" in r.json()["detail"]
    assert api.post("/cesta/itens", json={"produto_id": lanche, "quantidade": 3}).status_code == 201
    r = api.post("/cesta/itens", json={"produto_id": lanche, "quantidade": 3})  # somaria 6
    assert r.status_code == 400
    assert api.put(f"/cesta/itens/{lanche}", json={"quantidade": 6}).status_code == 400
    assert api.put(f"/cesta/itens/{lanche}", json={"quantidade": 5}).status_code == 200


def test_fechamento_revalida_o_estoque(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("cliente")
    api.post("/cesta/itens", json={"produto_id": ambiente["ids"]["lanche"], "quantidade": 4})
    ambiente["gravar_estoque"]("lanche", 2)  # o restaurante corrigiu a contagem depois
    resumo = api.get("/cesta/resumo", params={"tipo_entrega": "retirada"}).json()
    assert resumo["pode_fechar"] is False and "So ha 2 unidades" in resumo["motivo"]
    r = api.post("/pedidos", json=RETIRADA)
    assert r.status_code == 400 and "So ha 2 unidades" in r.json()["detail"]
    assert ambiente["contar_pedidos"]() == (0, 0)


# ---- baixa e concorrencia
def test_pedido_baixa_o_estoque(ambiente):
    r = _comprar(ambiente, "lanche", 3)
    assert r.status_code == 201, r.text
    assert ambiente["estoque"]("lanche") == 2
    assert _comprar(ambiente, "lanche", 2, quem="cliente2").status_code == 201
    assert ambiente["estoque"]("lanche") == 0


def test_estoque_acaba_entre_o_resumo_e_o_pedido(ambiente, monkeypatch):
    """Simula outro pedido levando as unidades depois da validacao da cesta."""
    from app.controllers import pedido_controller

    original = pedido_controller.preparar_fechamento

    def fechamento_e_depois_outro_cliente_compra(*args, **kwargs):
        fechamento = original(*args, **kwargs)
        ambiente["gravar_estoque"]("lanche", 1)
        return fechamento

    monkeypatch.setattr(pedido_controller, "preparar_fechamento", fechamento_e_depois_outro_cliente_compra)
    r = _comprar(ambiente, "lanche", 3)
    assert r.status_code == 409 and "Lanche" in r.json()["detail"]
    assert ambiente["contar_pedidos"]() == (0, 0)       # nada gravado
    assert ambiente["estoque"]("lanche") == 1            # baixa desfeita
    ambiente["logar"]("cliente")
    assert len(ambiente["api"].get("/cesta").json()["itens"]) == 1  # a cesta continua la


def test_produto_sem_controle_vende_sem_limite(ambiente):
    assert _comprar(ambiente, "suco", 50).status_code == 201
    assert ambiente["estoque"]("suco") is None


# ---- cancelamento
def test_cliente_cancela_e_estoque_volta(ambiente):
    pedido = _comprar(ambiente, "lanche", 4).json()["id"]
    assert ambiente["estoque"]("lanche") == 1
    r = ambiente["api"].post(f"/pedidos/{pedido}/cancelar")
    assert r.status_code == 200, r.text
    assert ambiente["estoque"]("lanche") == 5
    assert ambiente["api"].post(f"/pedidos/{pedido}/cancelar").status_code == 400  # nao devolve 2x
    assert ambiente["estoque"]("lanche") == 5


def test_restaurante_cancela_e_estoque_volta(ambiente):
    pedido = _comprar(ambiente, "lanche", 2).json()["id"]
    ambiente["logar"]("dono")
    r = ambiente["api"].patch(f"/pedidos/{pedido}/status", json={"status": "cancelado"})
    assert r.status_code == 200, r.text
    assert ambiente["estoque"]("lanche") == 5


def test_devolucao_respeita_estoque_desligado(ambiente):
    pedido = _comprar(ambiente, "lanche", 2).json()["id"]
    ambiente["gravar_estoque"]("lanche", None)  # dono desligou o controle depois da venda
    ambiente["api"].post(f"/pedidos/{pedido}/cancelar")
    assert ambiente["estoque"]("lanche") is None


# ---- cardapio
def test_esgotado_some_do_cardapio(ambiente):
    api = ambiente["api"]
    rid = ambiente["ids"]["restaurante"]
    itens = api.get(f"/consultas/restaurantes/{rid}/cardapio").json()["itens"]
    assert {i["nome"]: i["estoque"] for i in itens} == {"Lanche": 5, "Suco": None}
    _comprar(ambiente, "lanche", 5)
    itens = api.get(f"/consultas/restaurantes/{rid}/cardapio").json()["itens"]
    assert [i["nome"] for i in itens] == ["Suco"]
    r = api.post("/cesta/itens", json={"produto_id": ambiente["ids"]["lanche"], "quantidade": 1})
    assert r.status_code == 400 and "esgotado" in r.json()["detail"]
