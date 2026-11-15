"""Testes do código de barras dos produtos - Backlog (leitor de código de barras).

Cobre:
    - regra GTIN: tamanhos aceitos, só números, dígito verificador;
    - cadastro e alteração do item com código (normaliza espaços e traços);
    - código inválido -> 422; repetido no mesmo restaurante -> 409;
      outro restaurante pode usar o mesmo código;
    - null apaga o código; omitir não mexe;
    - busca pelo código (rota usada pelo leitor da tela Cardápio).

Executar:  python -m pytest testes/teste_codigo_barras.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import codigo_barras
from app.core.database import Base, get_db
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.local import Local
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

COCA = "7894900011517"  # EAN-13 real (dígito verificador 7)


# ------------------------------------------------------------ regra GTIN
@pytest.mark.parametrize("codigo", ["7894900011517", "96385074", "036000291452", "17894900011514"])
def test_gtin_validos(codigo):
    assert codigo_barras.problema(codigo) is None


@pytest.mark.parametrize("codigo,trecho", [("7894900011518", "verificador"), ("12345", "8, 12, 13 ou 14"), ("78949000115AB", "só números")])
def test_gtin_invalidos(codigo, trecho):
    assert trecho in codigo_barras.problema(codigo)


def test_normaliza_espacos_e_tracos():
    assert codigo_barras.validar(" 789-4900.011517 ") == COCA
    assert codigo_barras.validar("") is None and codigo_barras.validar(None) is None


# --------------------------------------------------------------- pela API
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
            u = db.get(Usuario, logado["id"])
            db.expunge(u)
            return u

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste
    with Sessao() as db:
        agora = datetime.now()
        donos = {t: Usuario(nome=t, email=f"{t}@teste.com", tipo="restaurante", criado_em=agora) for t in ("dono", "outro")}
        db.add_all(donos.values())
        db.flush()
        rest = {}
        for t, cnpj in (("dono", "11.111.111/0001-11"), ("outro", "22.222.222/0001-22")):
            loc = Local(usuario_id=donos[t].id, endereco="Rua A, 1", tipo="restaurante", latitude=Decimal("-23.5"), longitude=Decimal("-46.6"), criado_em=agora)
            db.add(loc)
            db.flush()
            rest[t] = Restaurante(local_id=loc.id, usuario_id=donos[t].id, nome_fantasia=f"Rest {t}", cnpj=cnpj, status_aprovacao="aprovado",
                                  taxa_entrega_km=Decimal("2.00"), ativo=True, criado_em=agora)
            db.add(rest[t])
        db.commit()
        ids = {t: u.id for t, u in donos.items()} | {f"rest_{t}": r.id for t, r in rest.items()}

    def logar(quem):
        logado["id"] = ids[quem]

    yield {"api": TestClient(app), "logar": logar, "ids": ids, "Sessao": Sessao}
    app.dependency_overrides.clear()


def _novo(api, nome, codigo=None):
    corpo = {"nome": nome, "preco": "6.50"}
    if codigo is not None:
        corpo["codigo_barras"] = codigo
    return api.post("/parceiro/produtos", json=corpo)


def test_cadastra_com_codigo_normalizado(ambiente):
    ambiente["logar"]("dono")
    r = _novo(ambiente["api"], "Refrigerante", " 789 4900 011517 ")
    assert r.status_code == 201, r.text
    assert r.json()["codigo_barras"] == COCA


def test_codigo_invalido_e_recusado(ambiente):
    ambiente["logar"]("dono")
    r = _novo(ambiente["api"], "Refrigerante", "7894900011518")
    assert r.status_code == 422
    assert "verificador" in r.text


def test_codigo_repetido_no_mesmo_restaurante(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    assert _novo(api, "Refrigerante", COCA).status_code == 201
    r = _novo(api, "Refri 2", COCA)
    assert r.status_code == 409
    assert "Refrigerante" in r.json()["detail"]
    ambiente["logar"]("outro")
    assert _novo(api, "Refrigerante", COCA).status_code == 201  # outro restaurante pode


def test_alterar_apagar_e_omitir(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    pid = _novo(api, "Suco").json()["id"]
    outro = _novo(api, "Refrigerante", COCA).json()["id"]
    assert api.put(f"/parceiro/produtos/{pid}", json={"codigo_barras": COCA}).status_code == 409
    assert api.put(f"/parceiro/produtos/{outro}", json={"codigo_barras": COCA}).status_code == 200  # o próprio item
    assert api.put(f"/parceiro/produtos/{pid}", json={"codigo_barras": "96385074"}).json()["codigo_barras"] == "96385074"
    assert api.put(f"/parceiro/produtos/{pid}", json={"preco": "7.00"}).json()["codigo_barras"] == "96385074"  # omitido
    assert api.put(f"/parceiro/produtos/{pid}", json={"codigo_barras": None}).json()["codigo_barras"] is None


def test_busca_pelo_codigo(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    pid = _novo(api, "Refrigerante", COCA).json()["id"]
    r = api.get(f"/parceiro/produtos/codigo-barras/{COCA}")
    assert r.status_code == 200 and r.json()["id"] == pid
    assert api.get("/parceiro/produtos/codigo-barras/96385074").status_code == 404
    ambiente["logar"]("outro")
    assert api.get(f"/parceiro/produtos/codigo-barras/{COCA}").status_code == 404  # não vê item de outro restaurante


def test_rota_de_produtos_do_admin_tambem_valida(ambiente):
    api = ambiente["api"]
    ambiente["logar"]("dono")
    rid = ambiente["ids"]["rest_dono"]
    r = api.post("/produtos", json={"restaurante_id": rid, "nome": "Água", "preco": "3.00", "codigo_barras": COCA})
    assert r.status_code == 201 and r.json()["codigo_barras"] == COCA
    assert api.post("/produtos", json={"restaurante_id": rid, "nome": "Água 2", "preco": "3.00", "codigo_barras": COCA}).status_code == 409
    assert api.put(f"/produtos/{r.json()['id']}", json={"codigo_barras": "123"}).status_code == 422
