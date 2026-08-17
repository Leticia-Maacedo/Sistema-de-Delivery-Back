"""Bateria de testes do CRUD de Produto - EntregaFood.

Roda contra o PostgreSQL 16 real (o mesmo banco da aplicacao). A cada
operacao, consulta a tabela `produto` diretamente com SELECT pra provar
que o efeito chegou no banco - nao so que a API respondeu certo.

Pre-requisito: um Usuario ja cadastrado no banco (qualquer um serve -
o script usa o primeiro que encontrar) - Local e Restaurante o proprio
script cria, pois sao pre-requisito do Produto.

Executar da raiz do repositorio:
    python testes/teste_crud_produto.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.main import app

CNPJ_TESTE = "99.999.999/0001-99"
cliente = TestClient(app)

falhas = 0


def checar(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global falhas
    if condicao:
        print(f"  [OK]    {descricao}")
    else:
        falhas += 1
        print(f"  [FALHA] {descricao} {detalhe}")


def produto_no_banco(produto_id: int) -> dict | None:
    """Consulta o PostgreSQL diretamente - prova que o efeito chegou na tabela."""
    with SessionLocal() as db:
        linha = db.execute(
            text("SELECT nome, preco, disponivel FROM produto WHERE id = :i"), {"i": produto_id}
        ).fetchone()
    return dict(linha._mapping) if linha else None


def limpar() -> None:
    with SessionLocal() as db:
        db.execute(text("""
            DELETE FROM produto WHERE restaurante_id IN (
                SELECT id FROM restaurante WHERE cnpj = :cnpj
            )
        """), {"cnpj": CNPJ_TESTE})
        db.execute(text("DELETE FROM restaurante WHERE cnpj = :cnpj"), {"cnpj": CNPJ_TESTE})
        db.commit()


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

    print("\n[0] Pre-requisitos da cadeia (Local -> Restaurante)")
    r = cliente.post("/locais", json={
        "usuario_id": usuario_id, "endereco": "Rua de Teste, 1", "tipo": "restaurante",
        "latitude": "-23.550520", "longitude": "-46.633308",
    })
    checar("POST /locais retorna 201", r.status_code == 201, f"(veio {r.status_code})")
    local_id = r.json()["id"]

    r = cliente.post("/restaurantes", json={
        "local_id": local_id, "nome_fantasia": "Restaurante De Teste",
        "cnpj": CNPJ_TESTE, "taxa_entrega_km": "3.00",
    })
    checar("POST /restaurantes retorna 201", r.status_code == 201, f"(veio {r.status_code})")
    restaurante_id = r.json()["id"]

    print("\n[1] CREATE - cadastro de produto")
    r = cliente.post("/produtos", json={
        "restaurante_id": restaurante_id, "nome": "Produto De Teste",
        "descricao": "Descricao de teste", "preco": "19.90",
    })
    checar("retorna HTTP 201", r.status_code == 201, f"(veio {r.status_code})")
    produto_id = r.json()["id"]
    linha = produto_no_banco(produto_id)
    checar("registro existe na tabela produto", linha is not None)
    checar("nome gravado corretamente", linha and linha["nome"] == "Produto De Teste")
    checar("disponivel = true por padrao", linha and linha["disponivel"] is True)

    print("\n[2] READ - listagem e consulta por id")
    checar("GET /produtos retorna 200", cliente.get("/produtos").status_code == 200)
    r = cliente.get(f"/produtos?restaurante_id={restaurante_id}")
    checar("GET /produtos?restaurante_id filtra certo", any(p["id"] == produto_id for p in r.json()))
    checar("GET /produtos/{id} retorna 200", cliente.get(f"/produtos/{produto_id}").status_code == 200)
    checar("GET de id inexistente retorna 404", cliente.get("/produtos/999999").status_code == 404)

    print("\n[3] UPDATE - alteracao de preco e disponibilidade")
    r = cliente.put(f"/produtos/{produto_id}", json={"preco": "22.50", "disponivel": False})
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    linha = produto_no_banco(produto_id)
    checar("preco alterado no banco", linha and float(linha["preco"]) == 22.50, f"(veio {linha})")
    checar("disponivel alterado no banco", linha and linha["disponivel"] is False)

    print("\n[4] CREATE recusado - restaurante inexistente")
    r = cliente.post("/produtos", json={"restaurante_id": 999999, "nome": "X", "preco": "1.00"})
    checar("retorna HTTP 422", r.status_code == 422, f"(veio {r.status_code})")

    print("\n[5] DELETE - remocao do produto")
    r = cliente.delete(f"/produtos/{produto_id}")
    checar("retorna HTTP 204", r.status_code == 204, f"(veio {r.status_code})")
    checar("registro removido da tabela", produto_no_banco(produto_id) is None)
    checar("GET apos exclusao retorna 404", cliente.get(f"/produtos/{produto_id}").status_code == 404)

    limpar()

    print("\n" + "=" * 58)
    if falhas == 0:
        print("TODAS AS VERIFICACOES PASSARAM - CRUD de Produto validado no PostgreSQL.")
    else:
        print(f"{falhas} VERIFICACAO(OES) FALHARAM.")
    print("=" * 58 + "\n")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
