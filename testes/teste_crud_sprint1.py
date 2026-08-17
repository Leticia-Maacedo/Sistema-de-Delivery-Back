"""Bateria de testes do CRUD de Usuario - Sprint 1 - EntregaFood.

Roda contra o PostgreSQL 16 real (o mesmo banco da aplicacao), nao contra
banco de teste. Cobre os casos CT01, CT02 e CT04 do Documento do Projeto,
mais as regras de autorizacao (dono da conta ou admin).

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
from app.core.security import gerar_hash_senha
from app.main import app

EMAIL_TESTE = "teste.sprint1@entregafood.com"
EMAIL_OUTRO = "teste.sprint1.outro@entregafood.com"
EMAIL_ADMIN = "teste.sprint1.admin@entregafood.com"
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


def criar_admin_direto_no_banco(email: str) -> int:
    """Admin nao se autocadastra pela API (403 de proposito) - pra testar as
    rotas administrativas, provisiona um direto no banco, do jeito que
    aconteceria de verdade em producao."""
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO usuario (nome, email, senha_hash, tipo) "
                "VALUES (:nome, :email, :hash, 'admin') RETURNING id"
            ),
            {"nome": "Admin De Teste", "email": email, "hash": gerar_hash_senha("senha123")},
        )
        db.commit()
        return db.execute(
            text("SELECT id FROM usuario WHERE email = :e"), {"e": email}
        ).scalar_one()


def limpar() -> None:
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM usuario WHERE email IN (:e1, :e2, :e3)"),
            {"e1": EMAIL_TESTE, "e2": EMAIL_OUTRO, "e3": EMAIL_ADMIN},
        )
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

    print("\n[3] CREATE - autocadastro como admin e bloqueado")
    r = cliente.post(
        "/usuarios",
        json={"nome": "Tentando Ser Admin", "email": "nao.deveria@entregafood.com", "senha": "senha123", "tipo": "admin"},
    )
    checar("retorna HTTP 403", r.status_code == 403, f"(veio {r.status_code})")

    print("\n[4] LOGIN - credenciais corretas (RF02)")
    r = cliente.post("/auth/login", json={"email": EMAIL_TESTE, "senha": "senha123"})
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    token = r.json().get("access_token", "")
    checar("devolve token JWT", len(token.split(".")) == 3)
    cabecalho = {"Authorization": f"Bearer {token}"}

    print("\n[5] LOGIN - credenciais invalidas (CT02)")
    r = cliente.post("/auth/login", json={"email": EMAIL_TESTE, "senha": "senha_errada"})
    checar("retorna HTTP 401", r.status_code == 401, f"(veio {r.status_code})")

    print("\n[6] Middleware de sessao - rota protegida")
    checar("sem token retorna 401", cliente.get("/auth/eu").status_code == 401)
    r = cliente.get("/auth/eu", headers=cabecalho)
    checar("com token retorna 200", r.status_code == 200, f"(veio {r.status_code})")

    print("\n[7] READ - consulta autenticada, dono da conta")
    checar("GET /usuarios sem token retorna 401", cliente.get("/usuarios").status_code == 401)
    checar(
        "GET /usuarios com usuario comum retorna 403 (so admin lista todo mundo)",
        cliente.get("/usuarios", headers=cabecalho).status_code == 403,
    )
    r = cliente.get(f"/usuarios/{usuario_id}", headers=cabecalho)
    checar("GET /usuarios/{id} do proprio dono retorna 200", r.status_code == 200)
    checar(
        "GET de id alheio (nao admin) retorna 403, sem revelar se existe",
        cliente.get("/usuarios/999999", headers=cabecalho).status_code == 403,
    )

    print("\n[8] UPDATE - alteracao de dados pelo proprio dono")
    r = cliente.put(
        f"/usuarios/{usuario_id}",
        json={"nome": "Nome Alterado", "telefone": "11777776666"},
        headers=cabecalho,
    )
    checar("retorna HTTP 200", r.status_code == 200, f"(veio {r.status_code})")
    with SessionLocal() as db:
        nome_no_banco = db.execute(
            text("SELECT nome FROM usuario WHERE id = :i"), {"i": usuario_id}
        ).scalar_one()
    checar("alteracao refletida no banco", nome_no_banco == "Nome Alterado", f"(veio {nome_no_banco!r})")

    print("\n[9] Autorizacao - um usuario nao mexe na conta de outro")
    outro_id = cliente.post(
        "/usuarios",
        json={"nome": "Outro Usuario", "email": EMAIL_OUTRO, "senha": "senha123"},
    ).json()["id"]
    r = cliente.put(f"/usuarios/{outro_id}", json={"nome": "Hackeado"}, headers=cabecalho)
    checar("PUT na conta alheia retorna 403", r.status_code == 403, f"(veio {r.status_code})")
    r = cliente.delete(f"/usuarios/{outro_id}", headers=cabecalho)
    checar("DELETE na conta alheia retorna 403", r.status_code == 403, f"(veio {r.status_code})")

    print("\n[10] Painel admin - lista, edita e exclui qualquer usuario")
    admin_id = criar_admin_direto_no_banco(EMAIL_ADMIN)
    r = cliente.post("/auth/login", json={"email": EMAIL_ADMIN, "senha": "senha123"})
    token_admin = r.json().get("access_token", "")
    cabecalho_admin = {"Authorization": f"Bearer {token_admin}"}

    r = cliente.get("/usuarios", headers=cabecalho_admin)
    checar("GET /usuarios com admin retorna 200", r.status_code == 200, f"(veio {r.status_code})")
    checar("lista inclui o usuario de teste", any(u["id"] == outro_id for u in r.json()))
    checar(
        "GET de id inexistente pelo admin retorna 404",
        cliente.get("/usuarios/999999", headers=cabecalho_admin).status_code == 404,
    )

    r = cliente.put(f"/usuarios/{outro_id}", json={"nome": "Editado Pelo Admin"}, headers=cabecalho_admin)
    checar("admin edita conta alheia -> 200", r.status_code == 200, f"(veio {r.status_code})")
    with SessionLocal() as db:
        nome_editado = db.execute(
            text("SELECT nome FROM usuario WHERE id = :i"), {"i": outro_id}
        ).scalar_one()
    checar("edicao do admin refletida no banco", nome_editado == "Editado Pelo Admin")

    r = cliente.delete(f"/usuarios/{outro_id}", headers=cabecalho_admin)
    checar("admin exclui conta alheia -> 204", r.status_code == 204, f"(veio {r.status_code})")
    checar("registro removido da tabela", contar_no_banco(EMAIL_OUTRO) == 0)

    print("\n[11] DELETE - encerramento da propria conta (RF06)")
    r = cliente.delete(f"/usuarios/{usuario_id}", headers=cabecalho)
    checar("retorna HTTP 204", r.status_code == 204, f"(veio {r.status_code})")
    checar("registro removido da tabela", contar_no_banco(EMAIL_TESTE) == 0)
    checar(
        "GET apos exclusao retorna 404",
        cliente.get(f"/usuarios/{usuario_id}", headers=cabecalho_admin).status_code == 404,
    )

    limpar()

    print("\n" + "=" * 58)
    if falhas == 0:
        print("TODAS AS VERIFICACOES PASSARAM - CRUD validado no PostgreSQL.")
    else:
        print(f"{falhas} VERIFICACAO(OES) FALHARAM.")
    print("=" * 58 + "\n")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
