"""Testes de "Minha conta" e "Meus enderecos" - Sprint 3 (backlog 10).

Roda a API de verdade (TestClient) com SQLite em memoria.

Cobre: o pedido grava o endereco escolhido na cesta; o rastreio continua
apontando para ele mesmo depois que o cliente exclui o endereco; troca de
senha (senha atual errada, certa e de outra conta); alteracao dos dados;
cadastro por telefone guardando o e-mail informado.

Executar:  python -m pytest testes/teste_conta_enderecos.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.controllers import auth_controller
from app.core import notificacoes_pedido
from app.core.database import Base, get_db
from app.core.security import gerar_hash_senha, obter_usuario_logado, verificar_senha
from app.main import app
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
        cliente = Usuario(nome="Cliente", email="cliente@teste.com", tipo="cliente",
                          senha_hash=gerar_hash_senha("senha123"), criado_em=agora)
        outro = Usuario(nome="Outro", email="outro@teste.com", tipo="cliente", criado_em=agora)
        dono = Usuario(nome="Dono", email="dono@teste.com", tipo="restaurante", criado_em=agora)
        db.add_all([cliente, outro, dono])
        db.flush()
        loja = Local(usuario_id=dono.id, endereco="Rua da Loja, 1", tipo="restaurante",
                     latitude=Decimal("-23.550000"), longitude=Decimal("-46.630000"), criado_em=agora)
        casa = Local(usuario_id=cliente.id, endereco="Rua de Casa, 10", tipo="Casa",
                     latitude=Decimal("-23.555000"), longitude=Decimal("-46.635000"), criado_em=agora)
        db.add_all([loja, casa])
        db.flush()
        restaurante = Restaurante(local_id=loja.id, usuario_id=dono.id, nome_fantasia="Lanchonete",
                                  cnpj="12.345.678/0001-90", status_aprovacao="aprovado",
                                  taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(restaurante)
        db.flush()
        produto = Produto(restaurante_id=restaurante.id, nome="Lanche", preco=Decimal("30.00"), disponivel=True)
        db.add(produto)
        db.commit()
        ids = {"cliente": cliente.id, "outro": outro.id, "casa": casa.id, "produto": produto.id}

    def logar(quem):
        logado["usuario_id"] = ids[quem]

    def ler(modelo, chave):
        with Sessao() as db:
            return db.get(modelo, chave)

    logar("cliente")
    yield {"api": TestClient(app), "ids": ids, "logar": logar, "ler": ler}
    app.dependency_overrides.clear()


def _novo_endereco(api, usuario_id):
    r = api.post("/locais", json={"usuario_id": usuario_id, "endereco": "Rua do Trabalho, 200",
                                   "tipo": "Trabalho", "latitude": -23.560000, "longitude": -46.640000})
    assert r.status_code == 201
    return r.json()["id"]


def test_resumo_usa_o_endereco_escolhido(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    trabalho = _novo_endereco(api, ids["cliente"])
    api.post("/cesta/itens", json={"produto_id": ids["produto"], "quantidade": 1})
    casa = api.get(f"/cesta/resumo?local_id={ids['casa']}").json()
    longe = api.get(f"/cesta/resumo?local_id={trabalho}").json()
    assert casa["local_entrega_id"] == ids["casa"] and longe["local_entrega_id"] == trabalho
    assert Decimal(str(longe["distancia_km"])) > Decimal(str(casa["distancia_km"]))


def test_pedido_grava_o_endereco_escolhido(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    _novo_endereco(api, ids["cliente"])  # o ultimo cadastrado NAO deve ser usado
    api.post("/cesta/itens", json={"produto_id": ids["produto"], "quantidade": 1})
    r = api.post("/pedidos", json={"forma_pagamento": "dinheiro", "tipo_entrega": "delivery", "local_id": ids["casa"]})
    assert r.status_code == 201
    pedido = ambiente["ler"](Pedido, r.json()["id"])
    assert pedido.endereco_entrega == "Rua de Casa, 10"
    assert pedido.latitude_entrega == Decimal("-23.555000")
    assert api.get(f"/pedidos/{pedido.id}").json()["endereco_entrega"] == "Rua de Casa, 10"


def test_retirada_nao_grava_endereco(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    api.post("/cesta/itens", json={"produto_id": ids["produto"], "quantidade": 1})
    r = api.post("/pedidos", json={"forma_pagamento": "dinheiro", "tipo_entrega": "retirada"})
    assert ambiente["ler"](Pedido, r.json()["id"]).endereco_entrega is None


def test_rastreio_mantem_o_destino_depois_de_excluir_o_endereco(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    trabalho = _novo_endereco(api, ids["cliente"])
    api.post("/cesta/itens", json={"produto_id": ids["produto"], "quantidade": 1})
    pid = api.post("/pedidos", json={"forma_pagamento": "dinheiro", "tipo_entrega": "delivery",
                                     "local_id": trabalho}).json()["id"]
    assert api.delete(f"/locais/{trabalho}").status_code == 204
    destino = api.get(f"/pedidos/{pid}/rastreio").json()["destino"]
    assert destino["endereco"] == "Rua do Trabalho, 200"
    assert Decimal(str(destino["latitude"])) == Decimal("-23.56")


def test_alterar_dados_cadastrais(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    r = api.put(f"/usuarios/{ids['cliente']}", json={"nome": "Cliente Novo", "telefone": "(11) 98888-7777"})
    assert r.status_code == 200
    assert r.json()["nome"] == "Cliente Novo" and r.json()["telefone"] == "11988887777"


def test_email_de_outra_conta_e_recusado(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    assert api.put(f"/usuarios/{ids['cliente']}", json={"email": "outro@teste.com"}).status_code == 409


def test_troca_de_senha_exige_a_senha_atual(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    r = api.put(f"/usuarios/{ids['cliente']}/senha", json={"senha_atual": "errada", "senha_nova": "nova123"})
    assert r.status_code == 400 and "incorreta" in r.json()["detail"]
    assert verificar_senha("senha123", ambiente["ler"](Usuario, ids["cliente"]).senha_hash)


def test_troca_de_senha(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    r = api.put(f"/usuarios/{ids['cliente']}/senha", json={"senha_atual": "senha123", "senha_nova": "nova123"})
    assert r.status_code == 204
    assert verificar_senha("nova123", ambiente["ler"](Usuario, ids["cliente"]).senha_hash)


def test_senha_nova_curta_e_recusada(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    r = api.put(f"/usuarios/{ids['cliente']}/senha", json={"senha_atual": "senha123", "senha_nova": "123"})
    assert r.status_code == 422


def test_nao_troca_senha_de_outra_conta(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    r = api.put(f"/usuarios/{ids['outro']}/senha", json={"senha_atual": "x", "senha_nova": "nova123"})
    assert r.status_code == 403


def test_conta_sem_senha_define_a_primeira(ambiente):
    api, ids = ambiente["api"], ambiente["ids"]
    ambiente["logar"]("outro")
    r = api.put(f"/usuarios/{ids['outro']}/senha", json={"senha_nova": "primeira1"})
    assert r.status_code == 204
    assert verificar_senha("primeira1", ambiente["ler"](Usuario, ids["outro"]).senha_hash)


class _RelogioSemFuso(datetime):
    """SQLite nao guarda fuso: o teste usa horas sem fuso no auth_controller."""

    @classmethod
    def now(cls, tz=None):
        return datetime.now()


def _cadastro_por_telefone(api, telefone, email):
    r = api.post("/auth/telefone/cadastro/solicitar-codigo",
                 json={"nome": "Nova Pessoa", "telefone": telefone, "senha": "senha123"})
    assert r.status_code == 200, r.text
    return api.post("/auth/telefone/cadastro/confirmar",
                    json={"nome": "Nova Pessoa", "telefone": telefone, "senha": "senha123",
                          "codigo": str(r.json()["codigo_dev"]), "email": email})


def test_cadastro_por_telefone_grava_o_email(ambiente, monkeypatch):
    monkeypatch.setattr(auth_controller, "datetime", _RelogioSemFuso)
    r = _cadastro_por_telefone(ambiente["api"], "11977776666", "nova@teste.com")
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["email"] == "nova@teste.com"
    login = ambiente["api"].post("/auth/login", json={"email": "nova@teste.com", "senha": "senha123"})
    assert login.status_code == 200


def test_cadastro_por_telefone_com_email_de_outra_conta(ambiente, monkeypatch):
    monkeypatch.setattr(auth_controller, "datetime", _RelogioSemFuso)
    r = _cadastro_por_telefone(ambiente["api"], "11966665555", "cliente@teste.com")
    assert r.status_code == 409 and "e-mail" in r.json()["detail"]
