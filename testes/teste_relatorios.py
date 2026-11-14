"""Testes dos relatorios de vendas - Sprint 4.

Duas partes:
    1. Calculos puros (app/core/relatorios.py), sem banco.
    2. As tres rotas de verdade (TestClient + SQLite em memoria), com
       pedidos montados no teste: quem pode ver, filtro de datas, periodo
       sem pedidos, pedidos que ficam de fora e ordenacao.

Executar:  python -m pytest testes/teste_relatorios.py -v
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import relatorios as r
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

D = Decimal


def venda(rid, nome, forma, valor):
    return r.Venda(restaurante_id=rid, restaurante_nome=nome, forma_pagamento=forma, valor_total=D(valor))


VENDAS = [
    venda(1, "Pizzaria", "cartao", "60.00"),
    venda(1, "Pizzaria", "pix", "40.00"),
    venda(2, "Sushi", "dinheiro", "100.00"),
    venda(2, "Sushi", "cartao", "50.00"),
    venda(2, "Sushi", "cartao", "50.00"),
]


# ------------------------------------------------------------------ 1. calculos


def test_receita_e_participacao():
    rel = r.receita_por_restaurante(VENDAS)
    assert rel["total_geral"] == D("300.00")
    assert [x["restaurante_nome"] for x in rel["restaurantes"]] == ["Sushi", "Pizzaria"]  # maior primeiro
    assert rel["restaurantes"][0]["receita_bruta"] == D("200.00")
    assert rel["restaurantes"][0]["participacao_percentual"] == D("66.67")
    assert rel["restaurantes"][1]["participacao_percentual"] == D("33.33")


def test_quantidade_faturamento_e_ticket_medio():
    rel = r.pedidos_por_restaurante(VENDAS)
    sushi, pizzaria = rel["restaurantes"]
    assert (sushi["quantidade_pedidos"], sushi["faturamento"], sushi["ticket_medio"]) == (3, D("200.00"), D("66.67"))
    assert (pizzaria["quantidade_pedidos"], pizzaria["ticket_medio"]) == (2, D("50.00"))
    assert (rel["total_pedidos"], rel["total_faturamento"], rel["ticket_medio_geral"]) == (5, D("300.00"), D("60.00"))


@pytest.mark.parametrize(
    "coluna, ordem, primeiro",
    [("quantidade_pedidos", "asc", "Pizzaria"), ("ticket_medio", "desc", "Sushi"), ("restaurante_nome", "asc", "Pizzaria")],
)
def test_ordenacao_da_tabela(coluna, ordem, primeiro):
    rel = r.pedidos_por_restaurante(VENDAS, coluna, ordem)
    assert rel["restaurantes"][0]["restaurante_nome"] == primeiro


def test_pagamentos_por_tipo_em_quantidade_e_valor():
    rel = r.pagamentos_por_tipo(VENDAS)
    por_metodo = {m["forma_pagamento"]: m for m in rel["metodos"]}
    assert por_metodo["cartao"]["quantidade"] == 3 and por_metodo["cartao"]["valor"] == D("160.00")
    assert por_metodo["pix"]["percentual_quantidade"] == D("20.00")
    assert por_metodo["dinheiro"]["percentual_valor"] == D("33.33")
    assert rel["total_quantidade"] == 5 and rel["total_valor"] == D("300.00")
    assert rel["metodos"][0]["forma_pagamento"] == "cartao"  # maior valor primeiro


def test_sem_vendas_tudo_zerado():
    assert r.receita_por_restaurante([]) == {"total_geral": D("0.00"), "restaurantes": []}
    vazio = r.pedidos_por_restaurante([])
    assert vazio["total_pedidos"] == 0 and vazio["ticket_medio_geral"] == D("0.00") and vazio["restaurantes"] == []
    pagamentos = r.pagamentos_por_tipo([])
    assert [m["quantidade"] for m in pagamentos["metodos"]] == [0, 0, 0]  # os tres metodos aparecem
    assert all(m["percentual_valor"] == D("0.00") for m in pagamentos["metodos"])


def test_periodo():
    assert r.periodo_invalido(date(2026, 11, 10), date(2026, 11, 1)) is not None
    assert r.periodo_invalido(date(2026, 11, 1), date(2026, 11, 1)) is None
    inicio, fim = r.intervalo(date(2026, 11, 1), date(2026, 11, 1))
    assert (inicio, fim) == (datetime(2026, 11, 1), datetime(2026, 11, 2))  # fim inclui o dia todo


# ------------------------------------------------------------------ 2. rotas


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    logado = {"id": None}

    with Sessao() as db:
        agora = datetime.now()
        admin = Usuario(nome="Admin", email="a@t.com", tipo="admin", criado_em=agora)
        dono1 = Usuario(nome="Dono 1", email="d1@t.com", tipo="restaurante", criado_em=agora)
        dono2 = Usuario(nome="Dono 2", email="d2@t.com", tipo="restaurante", criado_em=agora)
        cliente = Usuario(nome="Cliente", email="c@t.com", tipo="cliente", criado_em=agora)
        db.add_all([admin, dono1, dono2, cliente])
        db.flush()
        restaurantes = {}
        for nome, dono, cnpj in (("Pizzaria", dono1, "11.111.111/0001-11"), ("Sushi", dono2, "22.222.222/0001-22")):
            local = Local(usuario_id=dono.id, endereco="Rua", tipo="restaurante",
                          latitude=D("-23.5"), longitude=D("-46.6"), criado_em=agora)
            db.add(local)
            db.flush()
            rest = Restaurante(local_id=local.id, usuario_id=dono.id, nome_fantasia=nome, cnpj=cnpj,
                               status_aprovacao="aprovado", taxa_entrega_km=D("2.00"), criado_em=agora)
            db.add(rest)
            db.flush()
            restaurantes[nome] = rest.id

        def pedido(rest, status, forma, valor, quando):
            db.add(Pedido(cliente_id=cliente.id, restaurante_id=restaurantes[rest], status=status,
                          tipo_entrega="delivery", forma_pagamento=forma, valor_total=D(valor),
                          taxa_entrega=D("5.00"), criado_em=quando))

        pedido("Pizzaria", "entregue", "cartao", "60.00", datetime(2026, 11, 2, 12, 0))
        pedido("Pizzaria", "aceito", "pix", "40.00", datetime(2026, 11, 3, 23, 59))
        pedido("Sushi", "em_transito", "dinheiro", "100.00", datetime(2026, 11, 3, 10, 0))
        pedido("Sushi", "entregue", "cartao", "50.00", datetime(2026, 10, 20, 10, 0))  # fora de novembro
        pedido("Sushi", "cancelado", "cartao", "999.00", datetime(2026, 11, 2, 10, 0))  # fica de fora
        pedido("Pizzaria", "aguardando_aceite", "pix", "888.00", datetime(2026, 11, 2, 10, 0))  # fica de fora
        db.commit()
        ids = {"admin": admin.id, "dono1": dono1.id, "dono2": dono2.id, "cliente": cliente.id}

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

    def logar(quem):
        logado["id"] = ids[quem]

    logar("admin")
    yield {"cliente": TestClient(app), "logar": logar}
    app.dependency_overrides.clear()


NOVEMBRO = "?data_inicio=2026-11-01&data_fim=2026-11-30"


def test_admin_ve_todos_e_cancelados_ficam_de_fora(api):
    rel = api["cliente"].get("/relatorios/receita-por-restaurante").json()
    assert D(rel["total_geral"]) == D("250.00")  # 60 + 40 + 100 + 50; sem cancelado e sem aguardando
    assert "aceitos" in rel["regra"]


def test_filtro_de_data_inclui_o_ultimo_dia_inteiro(api):
    rel = api["cliente"].get("/relatorios/receita-por-restaurante" + NOVEMBRO).json()
    assert D(rel["total_geral"]) == D("200.00")
    assert rel["periodo"] == {"data_inicio": "2026-11-01", "data_fim": "2026-11-30"}
    um_dia = api["cliente"].get("/relatorios/receita-por-restaurante?data_inicio=2026-11-03&data_fim=2026-11-03").json()
    assert D(um_dia["total_geral"]) == D("140.00")  # o pedido das 23:59 entra


def test_restaurante_ve_so_os_seus(api):
    api["logar"]("dono1")
    rel = api["cliente"].get("/relatorios/pedidos-por-restaurante").json()
    assert [x["restaurante_nome"] for x in rel["restaurantes"]] == ["Pizzaria"]
    assert rel["total_pedidos"] == 2


def test_cliente_nao_ve_relatorios(api):
    api["logar"]("cliente")
    for rota in ("receita-por-restaurante", "pedidos-por-restaurante", "pagamentos-por-tipo"):
        assert api["cliente"].get(f"/relatorios/{rota}").status_code == 403


def test_periodo_invertido_e_data_invalida(api):
    assert api["cliente"].get("/relatorios/pagamentos-por-tipo?data_inicio=2026-11-30&data_fim=2026-11-01").status_code == 400
    assert api["cliente"].get("/relatorios/pagamentos-por-tipo?data_inicio=30/11/2026").status_code == 422


def test_periodo_sem_pedidos(api):
    rel = api["cliente"].get("/relatorios/pagamentos-por-tipo?data_inicio=2025-01-01&data_fim=2025-01-31").json()
    assert rel["total_quantidade"] == 0
    assert [m["forma_pagamento"] for m in rel["metodos"]] == ["cartao", "dinheiro", "pix"]


def test_tabela_ordenada_pela_coluna_pedida(api):
    rel = api["cliente"].get("/relatorios/pedidos-por-restaurante" + NOVEMBRO + "&ordenar_por=quantidade_pedidos&ordem=asc").json()
    assert [x["restaurante_nome"] for x in rel["restaurantes"]] == ["Sushi", "Pizzaria"]
    assert api["cliente"].get("/relatorios/pedidos-por-restaurante?ordenar_por=nome").status_code == 422


def test_pizza_por_metodo(api):
    rel = api["cliente"].get("/relatorios/pagamentos-por-tipo" + NOVEMBRO).json()
    por_metodo = {m["forma_pagamento"]: m for m in rel["metodos"]}
    assert por_metodo["dinheiro"]["quantidade"] == 1 and D(por_metodo["dinheiro"]["percentual_valor"]) == D("50.00")
    assert sum(D(m["percentual_valor"]) for m in rel["metodos"]) == D("100.00")
