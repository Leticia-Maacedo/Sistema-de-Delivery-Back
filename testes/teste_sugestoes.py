"""Testes da sugestao de produtos - Sprint 4.

Duas partes:
    1. Regra pura (app/core/sugestoes.py), sem banco.
    2. A rota de verdade (TestClient + SQLite em memoria), com pedidos
       montados no teste: cesta vazia, cesta com itens, produto esgotado,
       indisponivel, pedido cancelado, restaurante inexistente e limite.

Executar:  python -m pytest testes/teste_sugestoes.py -v
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import sugestoes
from app.core.database import Base, get_db
from app.main import app
from app.models.item_pedido import ItemPedido
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

D = Decimal


# ------------------------------------------------------------------ 1. regra


def produto(pid, nome):
    return SimpleNamespace(id=pid, nome=nome)


CANDIDATOS = [produto(1, "Pizza"), produto(2, "Refrigerante"), produto(3, "Sobremesa"), produto(4, "Água")]


def test_cesta_vazia_mais_pedidos_primeiro():
    lista = sugestoes.montar_sugestoes(CANDIDATOS, vendidos={2: 10, 3: 4}, juntos={}, na_cesta=set())
    assert [s.produto.nome for s in lista] == ["Refrigerante", "Sobremesa", "Água", "Pizza"]
    assert lista[0].motivo == sugestoes.MOTIVO_POPULAR
    assert lista[-1].motivo == sugestoes.MOTIVO_CARDAPIO  # sem venda: completa a lista


def test_pedido_junto_com_a_cesta_vem_antes_do_mais_pedido():
    lista = sugestoes.montar_sugestoes(CANDIDATOS, vendidos={2: 10, 3: 4}, juntos={3: 2}, na_cesta={1})
    assert [s.produto.nome for s in lista][:2] == ["Sobremesa", "Refrigerante"]
    assert lista[0].motivo == sugestoes.MOTIVO_JUNTOS
    assert all(s.produto.id != 1 for s in lista)  # o que esta na cesta nao volta


def test_limite_corta_a_lista():
    assert len(sugestoes.montar_sugestoes(CANDIDATOS, {}, {}, set(), limite=2)) == 2


# ------------------------------------------------------------------ 2. rota


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Sessao() as db:
        agora = datetime.now()
        dono = Usuario(nome="Dono", email="d@t.com", tipo="restaurante", criado_em=agora)
        cliente = Usuario(nome="Cliente", email="c@t.com", tipo="cliente", criado_em=agora)
        db.add_all([dono, cliente])
        db.flush()

        def restaurante(nome, cnpj, aprovacao="aprovado"):
            local = Local(usuario_id=dono.id, endereco="Rua", tipo="restaurante",
                          latitude=D("-23.5"), longitude=D("-46.6"), criado_em=agora)
            db.add(local)
            db.flush()
            rest = Restaurante(local_id=local.id, usuario_id=dono.id, nome_fantasia=nome, cnpj=cnpj,
                               status_aprovacao=aprovacao, taxa_entrega_km=D("2.00"), criado_em=agora)
            db.add(rest)
            db.flush()
            return rest

        pizzaria = restaurante("Pizzaria", "11.111.111/0001-11")
        pendente = restaurante("Pendente", "22.222.222/0001-22", aprovacao="pendente")

        def item(nome, preco, **extra):
            p = Produto(restaurante_id=pizzaria.id, nome=nome, preco=D(preco), disponivel=True, **extra)
            db.add(p)
            db.flush()
            return p

        pizza = item("Pizza", "50.00")
        refri = item("Refrigerante", "8.00")
        sobremesa = item("Sobremesa", "15.00")
        agua = item("Água", "4.00")
        esgotado = item("Calzone", "40.00", estoque=0)
        pausado = item("Esfiha", "6.00")
        pausado.disponivel = False

        def pedido(status, itens):
            p = Pedido(cliente_id=cliente.id, restaurante_id=pizzaria.id, status=status,
                       tipo_entrega="retirada", forma_pagamento="pix", valor_total=D("10.00"),
                       taxa_entrega=D("0.00"), criado_em=agora)
            db.add(p)
            db.flush()
            for prod, qtd in itens:
                db.add(ItemPedido(pedido_id=p.id, produto_id=prod.id, quantidade=qtd,
                                  preco_unitario=prod.preco))

        # Refrigerante e o mais vendido; com Pizza, quem mais sai junto e a Sobremesa.
        pedido("entregue", [(refri, 6)])
        pedido("entregue", [(pizza, 1), (sobremesa, 1)])
        pedido("aceito", [(pizza, 1), (sobremesa, 1), (agua, 1)])
        pedido("em_transito", [(esgotado, 9), (pausado, 9), (pizza, 1)])  # esgotado/pausado nao podem aparecer
        pedido("cancelado", [(pizza, 1), (agua, 30)])  # nao conta
        pedido("aguardando_aceite", [(pizza, 1), (agua, 30)])  # nao conta
        db.commit()
        ids = {"pizzaria": pizzaria.id, "pendente": pendente.id, "pizza": pizza.id, "refri": refri.id,
               "sobremesa": sobremesa.id, "agua": agua.id, "esgotado": esgotado.id, "pausado": pausado.id}

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = db_de_teste
    yield {"cliente": TestClient(app), "ids": ids}
    app.dependency_overrides.clear()


def rota(ids, consulta=""):
    return f"/consultas/restaurantes/{ids['pizzaria']}/sugestoes{consulta}"


def test_cesta_vazia_sugere_os_mais_pedidos(api):
    resposta = api["cliente"].get(rota(api["ids"]))
    assert resposta.status_code == 200
    corpo = resposta.json()
    nomes = [s["nome"] for s in corpo["sugestoes"]]
    assert nomes[0] == "Refrigerante"  # 6 unidades vendidas
    assert corpo["sugestoes"][0]["vezes_pedido"] == 6
    assert corpo["sugestoes"][0]["motivo"] == sugestoes.MOTIVO_POPULAR
    assert corpo["na_cesta"] == [] and "aceitos" in corpo["regra"]


def test_esgotado_e_indisponivel_nunca_aparecem(api):
    nomes = {s["nome"] for s in api["cliente"].get(rota(api["ids"], "?limite=20")).json()["sugestoes"]}
    assert nomes == {"Pizza", "Refrigerante", "Sobremesa", "Água"}


def test_cancelado_e_aguardando_aceite_nao_contam(api):
    por_nome = {s["nome"]: s for s in api["cliente"].get(rota(api["ids"], "?limite=20")).json()["sugestoes"]}
    assert por_nome["Água"]["vezes_pedido"] == 1  # os 60 dos pedidos cancelado/aguardando ficam de fora


def test_com_pizza_na_cesta_sugere_o_que_sai_junto(api):
    ids = api["ids"]
    corpo = api["cliente"].get(rota(ids, f"?na_cesta={ids['pizza']}")).json()
    primeira = corpo["sugestoes"][0]
    assert primeira["nome"] == "Sobremesa" and primeira["pedidos_juntos"] == 2
    assert primeira["motivo"] == sugestoes.MOTIVO_JUNTOS
    assert ids["pizza"] not in [s["id"] for s in corpo["sugestoes"]]  # o que ja esta na cesta nao volta
    assert corpo["na_cesta"] == [ids["pizza"]]


def test_varios_itens_na_cesta_e_limite(api):
    ids = api["ids"]
    corpo = api["cliente"].get(rota(ids, f"?na_cesta={ids['pizza']}&na_cesta={ids['sobremesa']}&limite=1")).json()
    assert corpo["total"] == 1
    assert corpo["sugestoes"][0]["nome"] == "Água"  # saiu junto com pizza e sobremesa


def test_limite_invalido_e_restaurante_que_nao_aparece(api):
    ids = api["ids"]
    assert api["cliente"].get(rota(ids, "?limite=0")).status_code == 422
    assert api["cliente"].get(rota(ids, "?limite=21")).status_code == 422
    assert api["cliente"].get(f"/consultas/restaurantes/{ids['pendente']}/sugestoes").status_code == 404
    assert api["cliente"].get("/consultas/restaurantes/9999/sugestoes").status_code == 404
