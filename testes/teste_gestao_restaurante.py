"""Testes do Portal do Parceiro - Sprint 3 (gestao do restaurante pelo dono).

Roda a API de verdade (TestClient) com SQLite em memoria.

Cobre: horario de funcionamento (inclusive virando a meia-noite) e pausa;
cadastro do restaurante pelo dono (nasce pendente, um por dono, CNPJ
unico); alteracao de dados, raio e horario; cardapio do dono (criar,
alterar, desativar, excluir; item vendido nao exclui; item de outro
restaurante nao aparece); cesta bloqueada para restaurante fechado,
pausado ou fora do raio proprio; so cliente compra.

Executar:  python -m pytest testes/teste_gestao_restaurante.py -v
"""

from datetime import datetime, time
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

ENDERECO = {"endereco": "Rua Augusta, 1500, Consolação, São Paulo - SP",
            "latitude": -23.558300, "longitude": -46.661500}
NOVO = {"nome_fantasia": "Cantina Nova", "cnpj": "11.222.333/0001-81", "taxa_entrega_km": 2.5,
        "raio_entrega_km": 5, "horario_abertura": "00:00", "horario_fechamento": "23:59", **ENDERECO}


# ------------------------------------------------------------ regras puras
def _rest(ativo=True, abre=None, fecha=None):
    return Restaurante(ativo=ativo, horario_abertura=abre, horario_fechamento=fecha)


def test_sem_horario_vale_so_o_ativo():
    assert _rest().aberto_agora() is True
    assert _rest(ativo=False).aberto_agora() is False


def test_horario_no_mesmo_dia():
    r = _rest(abre=time(11), fecha=time(23))
    assert r.aberto_agora(datetime(2026, 10, 23, 12, 0)) is True
    assert r.aberto_agora(datetime(2026, 10, 23, 10, 59)) is False
    assert r.aberto_agora(datetime(2026, 10, 23, 23, 0)) is False


def test_horario_que_vira_a_meia_noite():
    r = _rest(abre=time(18), fecha=time(2))
    assert r.aberto_agora(datetime(2026, 10, 23, 23, 30)) is True
    assert r.aberto_agora(datetime(2026, 10, 24, 1, 30)) is True
    assert r.aberto_agora(datetime(2026, 10, 24, 15, 0)) is False


def test_motivo_fechado():
    assert "pausado" in _rest(ativo=False).motivo_fechado()
    assert "11:00" in _rest(abre=time(11), fecha=time(23)).motivo_fechado()


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
                   for t, tp in (("dono", "restaurante"), ("novo", "restaurante"), ("cliente", "cliente"),
                                 ("entregador", "entregador"))}
        db.add_all(pessoas.values())
        db.flush()
        loja = Local(usuario_id=pessoas["dono"].id, endereco="Av. Paulista, 1000", tipo="restaurante",
                     latitude=Decimal("-23.561414"), longitude=Decimal("-46.655881"), criado_em=agora)
        casa = Local(usuario_id=pessoas["cliente"].id, endereco="Praça da Sé, 1", tipo="Casa",
                     latitude=Decimal("-23.550520"), longitude=Decimal("-46.633308"), criado_em=agora)
        db.add_all([loja, casa])
        db.flush()
        rest = Restaurante(local_id=loja.id, usuario_id=pessoas["dono"].id, nome_fantasia="Burger",
                           cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                           taxa_entrega_km=Decimal("2.00"), ativo=True, criado_em=agora)
        db.add(rest)
        db.flush()
        lanche = Produto(restaurante_id=rest.id, nome="Lanche", preco=Decimal("30.00"), disponivel=True)
        db.add(lanche)
        db.commit()
        ids = {k: v.id for k, v in pessoas.items()} | {"restaurante": rest.id, "lanche": lanche.id}

    def logar(quem):
        logado["id"] = ids[quem]

    def ler(modelo, chave):
        with Sessao() as db:
            return db.get(modelo, chave)

    def gravar(modelo, chave, **campos):
        with Sessao() as db:
            obj = db.get(modelo, chave)
            for k, v in campos.items():
                setattr(obj, k, v)
            db.commit()

    yield {"api": TestClient(app), "ids": ids, "logar": logar, "ler": ler, "gravar": gravar, "Sessao": Sessao}
    app.dependency_overrides.clear()


def test_restaurante_sem_cadastro_recebe_404(ambiente):
    ambiente["logar"]("novo")
    r = ambiente["api"].get("/parceiro/restaurante")
    assert r.status_code == 404 and "cadastrou" in r.json()["detail"]


def test_dono_cadastra_restaurante_pendente(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("novo")
    r = api.post("/parceiro/restaurante", json=NOVO)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status_aprovacao"] == "pendente" and corpo["ativo"] is True
    assert corpo["endereco"] == ENDERECO["endereco"] and Decimal(str(corpo["raio_entrega_km"])) == 5
    assert api.get("/parceiro/restaurante").json()["id"] == corpo["id"]
    # um restaurante por dono; CNPJ unico
    assert api.post("/parceiro/restaurante", json=NOVO).status_code == 409


def test_cnpj_repetido_e_recusado(ambiente):
    ambiente["logar"]("novo")
    r = ambiente["api"].post("/parceiro/restaurante", json={**NOVO, "cnpj": "12.345.678/0001-90"})
    assert r.status_code == 409


def test_horario_incompleto_e_recusado(ambiente):
    ambiente["logar"]("novo")
    r = ambiente["api"].post("/parceiro/restaurante", json={**NOVO, "horario_fechamento": None})
    assert r.status_code == 422


def test_dono_altera_raio_horario_pausa_e_endereco(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    r = api.put("/parceiro/restaurante", json={"raio_entrega_km": 3, "horario_abertura": "11:00",
                                               "horario_fechamento": "23:00", "ativo": False,
                                               "endereco": "Rua Nova, 10", "latitude": -23.5, "longitude": -46.6})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ativo"] is False and corpo["aberto"] is False
    assert corpo["horario_abertura"] == "11:00:00" and corpo["endereco"] == "Rua Nova, 10"
    assert ambiente["ler"](Restaurante, ambiente["ids"]["restaurante"]).status_aprovacao == "aprovado"
    # null limpa o horario e o raio
    r = api.put("/parceiro/restaurante", json={"horario_abertura": None, "horario_fechamento": None,
                                               "raio_entrega_km": None, "ativo": True})
    assert r.json()["horario_abertura"] is None and r.json()["raio_entrega_km"] is None and r.json()["aberto"] is True


def test_somente_restaurante_acessa_o_portal(ambiente):
    ambiente["logar"]("cliente")
    assert ambiente["api"].get("/parceiro/restaurante").status_code == 403


def test_cardapio_do_dono(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    r = api.post("/parceiro/produtos", json={"nome": "Batata", "descricao": " Porção ", "preco": 12.5})
    assert r.status_code == 201 and r.json()["descricao"] == "Porção"
    pid = r.json()["id"]
    assert {p["nome"] for p in api.get("/parceiro/produtos").json()} == {"Batata", "Lanche"}
    r = api.put(f"/parceiro/produtos/{pid}", json={"preco": 14, "disponivel": False})
    assert Decimal(str(r.json()["preco"])) == 14 and r.json()["disponivel"] is False
    assert api.delete(f"/parceiro/produtos/{pid}").status_code == 204
    assert ambiente["ler"](Produto, pid) is None


def test_item_vendido_nao_e_excluido(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    with ambiente["Sessao"]() as db:
        pedido = Pedido(cliente_id=ids["cliente"], restaurante_id=ids["restaurante"], status="entregue",
                        tipo_entrega="retirada", forma_pagamento="dinheiro", valor_total=Decimal("30"),
                        taxa_entrega=Decimal("0"), criado_em=datetime.now())
        db.add(pedido)
        db.flush()
        db.add(ItemPedido(pedido_id=pedido.id, produto_id=ids["lanche"], quantidade=1, preco_unitario=Decimal("30")))
        db.commit()
    ambiente["logar"]("dono")
    r = api.delete(f"/parceiro/produtos/{ids['lanche']}")
    assert r.status_code == 409 and "Desative" in r.json()["detail"]


def test_produto_de_outro_restaurante_nao_aparece(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    ambiente["logar"]("novo")
    api.post("/parceiro/restaurante", json=NOVO)
    assert api.put(f"/parceiro/produtos/{ids['lanche']}", json={"preco": 1}).status_code == 404
    assert api.delete(f"/parceiro/produtos/{ids['lanche']}").status_code == 404
    assert api.get("/parceiro/produtos").json() == []


def test_resumo_do_dia(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    with ambiente["Sessao"]() as db:
        for st, valor in (("aguardando_aceite", "40"), ("em_preparacao", "20"), ("cancelado", "99")):
            db.add(Pedido(cliente_id=ids["cliente"], restaurante_id=ids["restaurante"], status=st,
                          tipo_entrega="retirada", forma_pagamento="dinheiro", valor_total=Decimal(valor),
                          taxa_entrega=Decimal("0"), criado_em=datetime.now()))
        db.commit()
    ambiente["logar"]("dono")
    r = api.get("/parceiro/resumo").json()
    assert r["pedidos_hoje"] == 2 and Decimal(str(r["faturamento_hoje"])) == 60
    assert Decimal(str(r["ticket_medio_hoje"])) == 30
    assert r["aguardando_aceite"] == 1 and r["em_andamento"] == 1
    assert r["produtos_total"] == 1 and r["produtos_ativos"] == 1


def _cesta_com_lanche(ambiente):
    ambiente["logar"]("cliente")
    ambiente["api"].post("/cesta/itens", json={"produto_id": ambiente["ids"]["lanche"], "quantidade": 1})


def test_restaurante_pausado_nao_fecha_pedido(ambiente):
    _cesta_com_lanche(ambiente)
    ambiente["gravar"](Restaurante, ambiente["ids"]["restaurante"], ativo=False)
    resumo = ambiente["api"].get("/cesta/resumo").json()
    assert resumo["pode_fechar"] is False and "pausado" in resumo["motivo"]
    r = ambiente["api"].post("/pedidos", json={"forma_pagamento": "dinheiro", "tipo_entrega": "delivery"})
    assert r.status_code == 400


def test_restaurante_fora_do_horario_nao_fecha_pedido(ambiente):
    _cesta_com_lanche(ambiente)
    agora = datetime.now()
    abre = time((agora.hour + 2) % 24)
    fecha = time((agora.hour + 3) % 24)
    ambiente["gravar"](Restaurante, ambiente["ids"]["restaurante"], horario_abertura=abre, horario_fechamento=fecha)
    resumo = ambiente["api"].get("/cesta/resumo").json()
    assert resumo["pode_fechar"] is False and "fechado" in resumo["motivo"]


def test_raio_do_restaurante(ambiente):
    _cesta_com_lanche(ambiente)
    api = ambiente["api"]
    assert api.get("/cesta/resumo").json()["pode_fechar"] is True
    ambiente["gravar"](Restaurante, ambiente["ids"]["restaurante"], raio_entrega_km=Decimal("1"))
    resumo = api.get("/cesta/resumo").json()
    assert resumo["pode_fechar"] is False and "limite e de 1 km" in resumo["motivo"]


@pytest.mark.parametrize("quem", ["dono", "entregador"])
def test_so_cliente_compra(ambiente, quem):
    api, ids = ambiente["api"], ambiente["ids"]
    ambiente["logar"](quem)
    r = api.post("/cesta/itens", json={"produto_id": ids["lanche"], "quantidade": 1})
    assert r.status_code == 403 and "cliente" in r.json()["detail"]
    assert api.post("/pedidos", json={"forma_pagamento": "dinheiro", "tipo_entrega": "retirada"}).status_code == 403


def test_cliente_ve_se_esta_aberto(ambiente):
    ambiente["gravar"](Restaurante, ambiente["ids"]["restaurante"], ativo=False)
    lista = ambiente["api"].get("/consultas/restaurantes").json()
    assert lista[0]["aberto"] is False and lista[0]["ativo"] is False
