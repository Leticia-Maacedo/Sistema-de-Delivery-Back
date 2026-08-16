"""Bateria de testes do CRUD de Usuario - Sprint 1 - EntregaFood.

Roda contra o PostgreSQL 16 real (o mesmo banco da aplicacao), nao contra
banco de teste. Cobre os casos CT01, CT02 e CT04 do Documento do Projeto.

Pre-requisito:
    docker compose up -d          (banco no ar)
    tabelas criadas via sql/01_create_tables.sql

Executar da raiz do repositorio:
    python testes/teste_crud_sprint1.py
"""
import os
import sys

# permite executar o arquivo direto, a partir da raiz do repositorio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.main import app

EMAIL_TESTE = "teste.sprint1@entregafood.com"
cliente = TestClient(app)

falhas = 0


def checar(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global falhas
    if condicao:
        print(f"  [OK]    {descricao}")
    else:
        falhas += 1
        print(f"  [FALHA] {descricao} {detalhe}")


def contar_no_banco(email: str) -> int:
    """Consulta o PostgreSQL diretamente - prova que o efeito chegou na tabela."""
    with SessionLocal() as db:
        return db.execute(
            text("SELECT COUNT(*) FROM usuario WHERE email = :e"), {"e": email}
        ).scalar_one()


def limpar() -> None:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM usuario WHERE email = :e"), {"e": EMAIL_TESTE})
        db.commit()


def main() -> int:
    print(f"\nBanco em uso: {engine.url.render_as_string(hide_password=True)}")
    if not engine.url.drivername.startswith("postgresql"):
        print("ERRO: a aplicacao nao esta apontando para o PostgreSQL. Verifique o .env.")
        return 1

    limpar()

    print("\n[1] CREATE - cadastro com e-mail valido (CT01)")
    r = cliente.post(
        "/usuarios",
        json={
            "nome": "Usuario De Teste",
            "email": EMAIL_TESTE,
            "senha": "senha123",
            "telefone": "11999998888",
            "tipo": "cliente",
        },
    )
    checar("retorna HTTP 201", r.status_code == 201, f"(veio {r.status_code})")
    corpo = r.json()
    usuario_id = corpo.get("id")
    checar("registro existe na tabela usuario", contar_no_banco(EMAIL_TESTE) == 1)
    checar("resposta nao expoe senha", "senha" not in corpo and "senha_hash" not in corpo)

    with SessionLocal() as db:
        hash_gravado = db.execute(
            text("SELECT senha_hash FROM usuario WHERE id = :i"), {"i": usuario_id}
        ).scalar_one()
    checar("senha gravada com hash bcrypt (RNF03)", hash_gravado.startswith("$2"))

    print("\n[2] CREATE - e-mail ja existente (CT04)")
    r = cliente.post(
        "/usuarios", json={"nome": "Outro Nome", "email": EMAIL_TESTE, "senha": "outra123"}
    )
    checar("retorna HTTP 409", r.status_code == 409, f"(veio {r.status_code})")
    checar("nao duplicou no banco", contar_no_banco(EMAIL_TESTE) == 1)

    print("\n[3] READ - listagem e consulta por id")
    checar("GET /usuarios retorna 200", cliente.get("/usuarios").status_code == 200)
    r = cliente.get(f"/usuarios/{usuario_id}")
    checar("GET /usuarios/{id} retorna 200", r.status_code == 200)
    checar("GET de id inexistente retorna 404", cliente.get("/usuarios/999999").status_code == 404)

    print("\n[4] UPDATE - alteracao de dados")
    r = cliente.put(
        f"/usuarios/{usuario_id}", json={"nome": "Nome Alterado", "telefone": "11777776666"}
    )
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    with SessionLocal() as db:
        nome_no_banco = db.execute(
            text("SELECT nome FROM usuario WHERE id = :i"), {"i": usuario_id}
        ).scalar_one()
    checar("alteracao refletida no banco", nome_no_banco == "Nome Alterado", f"(veio {nome_no_banco!r})")

    print("\n[5] LOGIN - credenciais corretas (RF02)")
    r = cliente.post("/auth/login", json={"email": EMAIL_TESTE, "senha": "senha123"})
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    token = r.json().get("access_token", "")
    checar("devolve token JWT", len(token.split(".")) == 3)

    print("\n[6] LOGIN - credenciais invalidas (CT02)")
    r = cliente.post("/auth/login", json={"email": EMAIL_TESTE, "senha": "senha_errada"})
    checar("retorna HTTP 401", r.status_code == 401, f"(veio {r.status_code})")

    print("\n[7] Middleware de sessao - rota protegida")
    checar("sem token retorna 401", cliente.get("/auth/eu").status_code == 401)
    r = cliente.get("/auth/eu", headers={"Authorization": f"Bearer {token}"})
    checar("com token retorna 200", r.status_code == 200, f"(veio {r.status_code})")

    print("\n[8] DELETE - encerramento de conta (RF06)")
    r = cliente.delete(f"/usuarios/{usuario_id}")
    checar("retorna HTTP 204", r.status_code == 204, f"(veio {r.status_code})")
    checar("registro removido da tabela", contar_no_banco(EMAIL_TESTE) == 0)
    checar("GET apos exclusao retorna 404", cliente.get(f"/usuarios/{usuario_id}").status_code == 404)

    print("\n" + "=" * 58)
    if falhas == 0:
        print("TODAS AS VERIFICACOES PASSARAM - CRUD validado no PostgreSQL.")
    else:
        print(f"{falhas} VERIFICACAO(OES) FALHARAM.")
    print("=" * 58 + "\n")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
