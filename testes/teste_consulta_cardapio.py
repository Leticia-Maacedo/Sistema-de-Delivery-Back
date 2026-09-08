"""Bateria de testes das consultas de Restaurante e Cardapio - EntregaFood (Sprint 2).

Roda contra o PostgreSQL 16 real (o mesmo banco da aplicacao). O script
monta a propria cadeia Local -> Restaurante -> Produto (com um restaurante
APROVADO, um PENDENTE e um item indisponivel) e verifica, direto na tabela
e pela API, as regras de visibilidade da consulta do cliente:

    - GET /consultas/restaurantes            -> so restaurantes 'aprovado'
    - ?busca=                                -> filtra por nome fantasia
    - GET /consultas/restaurantes/{id}       -> 404 se pendente/inexistente
    - GET /consultas/restaurantes/{id}/cardapio -> so itens disponivel = true

Pre-requisito: um Usuario ja cadastrado no banco (usa o primeiro que achar).

Executar da raiz do repositorio:
    python testes/teste_consulta_cardapio.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.main import app

CNPJ_APROVADO = "88.880.000/0001-01"
CNPJ_PENDENTE = "88.880.000/0001-02"
cliente = TestClient(app)

falhas = 0


def checar(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global falhas
    if condicao:
        print(f"  [OK]    {descricao}")
    else:
        falhas += 1
        print(f"  [FALHA] {descricao} {detalhe}")


def limpar() -> None:
    with SessionLocal() as db:
        db.execute(text("""
            DELETE FROM produto WHERE restaurante_id IN (
                SELECT id FROM restaurante WHERE cnpj IN (:a, :p)
            )
        """), {"a": CNPJ_APROVADO, "p": CNPJ_PENDENTE})
        db.execute(text("DELETE FROM restaurante WHERE cnpj IN (:a, :p)"),
                   {"a": CNPJ_APROVADO, "p": CNPJ_PENDENTE})
        db.commit()


def criar_restaurante(local_id: int, nome: str, cnpj: str, status_aprovacao: str) -> int:
    """Cria o restaurante pelo CRUD e ja ajusta o status direto no banco
    (o POST /restaurantes nasce sempre 'pendente')."""
    r = cliente.post("/restaurantes", json={
        "local_id": local_id, "nome_fantasia": nome, "cnpj": cnpj, "taxa_entrega_km": "3.00",
    })
    assert r.status_code == 201, r.text
    restaurante_id = r.json()["id"]
    with SessionLocal() as db:
        db.execute(text("UPDATE restaurante SET status_aprovacao = :s WHERE id = :i"),
                   {"s": status_aprovacao, "i": restaurante_id})
        db.commit()
    return restaurante_id


def main() -> int:
    print(f"\nBanco em uso: {engine.url.render_as_string(hide_password=True)}")
    if not engine.url.drivername.startswith("postgresql"):
        print("ERRO: a aplicacao nao esta apontando para o PostgreSQL. Verifique o .env.")
        return 1

    limpar()

    with SessionLocal() as db:
        usuario_id = db.execute(text("SELECT id FROM usuario LIMIT 1")).scalar_one_or_none()
    if usuario_id is None:
        print("ERRO: nenhum usuario no banco - cadastre um usuario antes de rodar este teste.")
        return 1

    print("\n[0] Pre-requisitos (Local -> 2 Restaurantes: 1 aprovado, 1 pendente)")
    r = cliente.post("/locais", json={
        "usuario_id": usuario_id, "endereco": "Rua da Consulta, 10", "tipo": "restaurante",
        "latitude": "-23.550520", "longitude": "-46.633308",
    })
    checar("POST /locais retorna 201", r.status_code == 201, f"(veio {r.status_code})")
    local_id = r.json()["id"]

    id_aprovado = criar_restaurante(local_id, "Cozinha Do Teste Aprovada", CNPJ_APROVADO, "aprovado")
    id_pendente = criar_restaurante(local_id, "Cozinha Do Teste Pendente", CNPJ_PENDENTE, "pendente")

    # itens: 2 disponiveis + 1 indisponivel no restaurante aprovado
    for nome, preco, disp in [("Prato A", "20.00", True), ("Prato B", "30.00", True),
                              ("Prato Fora", "40.00", False)]:
        r = cliente.post("/produtos", json={
            "restaurante_id": id_aprovado, "nome": nome, "preco": preco, "disponivel": disp,
        })
        assert r.status_code == 201, r.text

    print("\n[1] GET /consultas/restaurantes - so aparecem os aprovados")
    r = cliente.get("/consultas/restaurantes")
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    ids = [x["id"] for x in r.json()]
    checar("restaurante aprovado aparece na lista", id_aprovado in ids)
    checar("restaurante pendente NAO aparece na lista", id_pendente not in ids)
    aprovado = next((x for x in r.json() if x["id"] == id_aprovado), {})
    checar("resposta traz o endereco embutido (local)", "local" in aprovado and "endereco" in aprovado.get("local", {}))
    checar("resposta NAO expoe o CNPJ", "cnpj" not in aprovado)

    print("\n[2] GET /consultas/restaurantes?busca= - filtro por nome")
    r = cliente.get("/consultas/restaurantes", params={"busca": "aprovada"})
    ids = [x["id"] for x in r.json()]
    checar("busca 'aprovada' acha o restaurante certo", id_aprovado in ids)
    r = cliente.get("/consultas/restaurantes", params={"busca": "zzz-nao-existe"})
    checar("busca sem match retorna lista vazia", r.json() == [])

    print("\n[3] GET /consultas/restaurantes/{id}")
    checar("id aprovado retorna 200", cliente.get(f"/consultas/restaurantes/{id_aprovado}").status_code == 200)
    checar("id pendente retorna 404", cliente.get(f"/consultas/restaurantes/{id_pendente}").status_code == 404)
    checar("id inexistente retorna 404", cliente.get("/consultas/restaurantes/999999").status_code == 404)

    print("\n[4] GET /consultas/restaurantes/{id}/cardapio")
    r = cliente.get(f"/consultas/restaurantes/{id_aprovado}/cardapio")
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    corpo = r.json()
    nomes = [i["nome"] for i in corpo.get("itens", [])]
    checar("cardapio traz os 2 itens disponiveis", set(nomes) == {"Prato A", "Prato B"}, f"(veio {nomes})")
    checar("item indisponivel NAO aparece no cardapio", "Prato Fora" not in nomes)
    checar("total_itens confere com a lista", corpo.get("total_itens") == len(corpo.get("itens", [])))
    checar("cardapio identifica o restaurante", corpo.get("restaurante", {}).get("id") == id_aprovado)
    checar("cardapio de restaurante pendente retorna 404",
           cliente.get(f"/consultas/restaurantes/{id_pendente}/cardapio").status_code == 404)

    limpar()

    print("\n" + "=" * 58)
    if falhas == 0:
        print("TODAS AS VERIFICACOES PASSARAM - consulta de Restaurante e Cardapio validada.")
    else:
        print(f"{falhas} VERIFICACAO(OES) FALHARAM.")
    print("=" * 58 + "\n")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
