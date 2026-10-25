"""Testes de permissao dos cadastros, da inclusao na cesta e do raio na consulta.

Roda a API de verdade (TestClient) com SQLite em memoria.

Cobre:
- /locais: exige login; cada usuario ve e altera so os proprios enderecos;
  o admin ve todos;
- /restaurantes: exige login; listagem e aprovacao so do admin; o dono
  altera e remove o proprio restaurante; cliente nao cadastra restaurante;
- /produtos: leitura publica; cadastrar, alterar e remover so o dono do
  restaurante ou o admin;
- cesta: produto de restaurante nao aprovado, pausado ou fechado nao entra;
- /consultas/restaurantes com latitude/longitude: so quem entrega no
  endereco, do mais perto para o mais longe.

Executar:  python -m pytest testes/teste_seguranca_cadastros.py -v
"""

from datetime import datetime, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.local import Local
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

SE = {"latitude": "-23.550520", "longitude": "-46.633308"}  # Praca da Se
CAMPINAS = {"latitude": "-22.905560", "longitude": "-47.060830"}


@pytest.fixture
def ambiente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
        u = {t: Usuario(nome=t.title(), email=f"{t}@teste.com", tipo=tp, criado_em=agora)
             for t, tp in (("dono", "restaurante"), ("outro_dono", "restaurante"), ("cliente", "cliente"),
                           ("outro_cliente", "cliente"), ("admin", "admin"))}
        db.add_all(u.values())
        db.flush()

        def local(dono, endereco, lat, lng, tipo="restaurante"):
            return Local(usuario_id=u[dono].id, endereco=endereco, tipo=tipo,
                         latitude=Decimal(lat), longitude=Decimal(lng), criado_em=agora)

        paulista = local("dono", "Av. Paulista, 1000", "-23.561414", "-46.655881")
        augusta = local("outro_dono", "Rua Augusta, 1500", "-23.558300", "-46.661500")
        liberdade = local("dono", "Rua Galvão Bueno, 100", "-23.557000", "-46.635000")
        casa = local("cliente", "Praça da Sé, 1", SE["latitude"], SE["longitude"], tipo="Casa")
        db.add_all([paulista, augusta, liberdade, casa])
        db.flush()

        def rest(loc, dono, nome, cnpj, status="aprovado", ativo=True, **extra):
            return Restaurante(local_id=loc.id, usuario_id=u[dono].id, nome_fantasia=nome, cnpj=cnpj,
                               status_aprovacao=status, taxa_entrega_km=Decimal("2.00"), ativo=ativo,
                               criado_em=agora, **extra)

        burger = rest(paulista, "dono", "Burger", "12.345.678/0001-90")
        pizza = rest(augusta, "outro_dono", "Pizzaria", "98.765.432/0001-10", raio_entrega_km=Decimal("2"))
        pastel = rest(liberdade, "dono", "Pastelaria", "11.111.111/0001-11")
        pendente = rest(liberdade, "dono", "Cantina Pendente", "22.222.222/0001-22", status="pendente")
        pausado = rest(liberdade, "dono", "Sushi Pausado", "33.333.333/0001-33", ativo=False)
        fechado = rest(liberdade, "dono", "Bar Fechado", "44.444.444/0001-44",
                       horario_abertura=time(3, 0), horario_fechamento=time(3, 1))
        db.add_all([burger, pizza, pastel, pendente, pausado, fechado])
        db.flush()
        produtos = {r.nome_fantasia: Produto(restaurante_id=r.id, nome=f"Item {r.nome_fantasia}",
                                             preco=Decimal("20.00"), disponivel=True)
                    for r in (burger, pizza, pendente, pausado, fechado)}
        db.add_all(produtos.values())
        db.commit()
        ids = {k: v.id for k, v in u.items()}
        ids.update(casa=casa.id, paulista=paulista.id, augusta=augusta.id, burger=burger.id, pizza=pizza.id)
        ids.update({f"produto_{k}": v.id for k, v in produtos.items()})

    def como(chave):
        logado["id"] = ids[chave]
        return TestClient(app)

    yield como, ids
    app.dependency_overrides.clear()


def _sem_login():
    app.dependency_overrides.pop(obter_usuario_logado, None)
    return TestClient(app)


# ------------------------------------------------------------------ locais
def test_locais_sem_login_401(ambiente):
    como, ids = ambiente
    cliente = _sem_login()
    assert cliente.get("/locais").status_code == 401
    assert cliente.post("/locais", json={"endereco": "Rua A, 10", "tipo": "Casa", **SE}).status_code == 401
    assert cliente.delete(f"/locais/{ids['casa']}").status_code == 401


def test_local_nasce_na_conta_de_quem_esta_logado(ambiente):
    como, ids = ambiente
    r = como("cliente").post("/locais", json={"endereco": "Rua Nova, 20", "tipo": "Trabalho", **SE})
    assert r.status_code == 201
    assert r.json()["usuario_id"] == ids["cliente"]


def test_nao_cadastra_local_para_outro_usuario(ambiente):
    como, ids = ambiente
    r = como("cliente").post("/locais", json={"usuario_id": ids["outro_cliente"], "endereco": "Rua X, 1",
                                              "tipo": "Casa", **SE})
    assert r.status_code == 403


def test_lista_so_os_proprios_enderecos(ambiente):
    como, ids = ambiente
    assert [l["id"] for l in como("cliente").get("/locais").json()] == [ids["casa"]]
    assert como("outro_cliente").get(f"/locais?usuario_id={ids['cliente']}").status_code == 403
    assert len(como("admin").get("/locais").json()) == 4


def test_outro_usuario_nao_le_altera_nem_exclui_o_endereco(ambiente):
    como, ids = ambiente
    intruso = como("outro_cliente")
    assert intruso.get(f"/locais/{ids['casa']}").status_code == 403
    assert intruso.put(f"/locais/{ids['casa']}", json={"tipo": "Outro"}).status_code == 403
    assert intruso.delete(f"/locais/{ids['casa']}").status_code == 403
    assert como("cliente").put(f"/locais/{ids['casa']}", json={"tipo": "Apartamento"}).json()["tipo"] == "Apartamento"


# ------------------------------------------------------------ restaurantes
def test_listagem_de_restaurantes_e_do_admin(ambiente):
    como, _ = ambiente
    assert como("dono").get("/restaurantes").status_code == 403
    assert como("cliente").get("/restaurantes").status_code == 403
    assert len(como("admin").get("/restaurantes").json()) == 6


def test_cliente_nao_cadastra_restaurante(ambiente):
    como, ids = ambiente
    r = como("cliente").post("/restaurantes", json={"local_id": ids["casa"], "nome_fantasia": "Fake",
                                                    "cnpj": "55.555.555/0001-55", "taxa_entrega_km": 2})
    assert r.status_code == 403


def test_dono_nao_usa_endereco_de_outro(ambiente):
    como, ids = ambiente
    r = como("dono").post("/restaurantes", json={"local_id": ids["augusta"], "nome_fantasia": "Copia",
                                                 "cnpj": "66.666.666/0001-66", "taxa_entrega_km": 2})
    assert r.status_code == 403


def test_dono_altera_o_proprio_mas_nao_se_aprova(ambiente):
    como, ids = ambiente
    dono = como("dono")
    assert dono.put(f"/restaurantes/{ids['burger']}", json={"nome_fantasia": "Burger Novo"}).status_code == 200
    r = dono.put(f"/restaurantes/{ids['burger']}", json={"status_aprovacao": "recusado"})
    assert r.status_code == 403


def test_outro_dono_nao_altera_nem_remove(ambiente):
    como, ids = ambiente
    intruso = como("outro_dono")
    assert intruso.get(f"/restaurantes/{ids['burger']}").status_code == 403
    assert intruso.put(f"/restaurantes/{ids['burger']}", json={"nome_fantasia": "Xis"}).status_code == 403
    assert intruso.delete(f"/restaurantes/{ids['burger']}").status_code == 403


def test_admin_aprova(ambiente):
    como, ids = ambiente
    r = como("admin").put(f"/restaurantes/{ids['pizza']}", json={"status_aprovacao": "recusado"})
    assert r.status_code == 200 and r.json()["status_aprovacao"] == "recusado"


# ---------------------------------------------------------------- produtos
def test_produtos_leitura_publica(ambiente):
    _sem_login()
    assert TestClient(app).get("/produtos").status_code == 200


def test_so_o_dono_mexe_no_cardapio(ambiente):
    como, ids = ambiente
    novo = {"restaurante_id": ids["burger"], "nome": "Batata", "preco": 15}
    assert como("outro_dono").post("/produtos", json=novo).status_code == 403
    assert como("cliente").post("/produtos", json=novo).status_code == 403
    criado = como("dono").post("/produtos", json=novo)
    assert criado.status_code == 201
    pid = criado.json()["id"]
    assert como("outro_dono").put(f"/produtos/{pid}", json={"preco": 1}).status_code == 403
    assert como("outro_dono").delete(f"/produtos/{pid}").status_code == 403
    assert como("admin").put(f"/produtos/{pid}", json={"preco": 16}).status_code == 200
    assert como("dono").delete(f"/produtos/{pid}").status_code == 204


def test_produtos_sem_login_401(ambiente):
    _, ids = ambiente
    cliente = _sem_login()
    assert cliente.post("/produtos", json={"restaurante_id": ids["burger"], "nome": "X", "preco": 1}).status_code == 401
    assert cliente.delete(f"/produtos/{ids['produto_Burger']}").status_code == 401


# ------------------------------------------------------------------- cesta
@pytest.mark.parametrize("nome, trecho", [("Cantina Pendente", "nao esta disponivel"),
                                          ("Sushi Pausado", "pausado"), ("Bar Fechado", "fechado")])
def test_cesta_recusa_restaurante_que_nao_recebe_pedidos(ambiente, nome, trecho):
    como, ids = ambiente
    r = como("cliente").post("/cesta/itens", json={"produto_id": ids[f"produto_{nome}"], "quantidade": 1})
    assert r.status_code == 400
    assert trecho in r.json()["detail"]


def test_cesta_aceita_restaurante_aberto(ambiente):
    como, ids = ambiente
    r = como("cliente").post("/cesta/itens", json={"produto_id": ids["produto_Burger"], "quantidade": 1})
    assert r.status_code == 201


# ---------------------------------------------------------- consulta / raio
def test_consulta_sem_endereco_lista_todos_os_aprovados(ambiente):
    nomes = [r["nome_fantasia"] for r in TestClient(app).get("/consultas/restaurantes").json()]
    assert "Pizzaria" in nomes and "Cantina Pendente" not in nomes
    assert all(r.get("distancia_km") is None for r in TestClient(app).get("/consultas/restaurantes").json())


def test_consulta_com_endereco_filtra_pelo_raio_e_ordena(ambiente):
    r = TestClient(app).get("/consultas/restaurantes", params=SE).json()
    nomes = [x["nome_fantasia"] for x in r]
    # Pizzaria tem raio de 2 km e fica a ~5 km da Se: nao entrega ali
    assert "Pizzaria" not in nomes
    assert nomes.index("Pastelaria") < nomes.index("Burger")  # a Liberdade fica mais perto da Se
    assert [x["distancia_km"] for x in r] == sorted(x["distancia_km"] for x in r)
    assert all(x["entrega_no_endereco"] for x in r)


def test_consulta_pode_incluir_quem_nao_entrega(ambiente):
    r = TestClient(app).get("/consultas/restaurantes", params={**SE, "incluir_fora_do_raio": True}).json()
    pizza = next(x for x in r if x["nome_fantasia"] == "Pizzaria")
    assert pizza["entrega_no_endereco"] is False


def test_consulta_longe_de_tudo_fica_vazia(ambiente):
    assert TestClient(app).get("/consultas/restaurantes", params=CAMPINAS).json() == []
