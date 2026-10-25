"""API local para rodar a colecao Teste_Consulta_Status_Cancelamento sem tocar no banco do Neon.

Sobe a API com um banco SQLite novo (apagado a cada execucao), cria as contas e os restaurantes de teste
e grava um ambiente do Postman com a URL e as senhas (aleatorias, geradas a cada execucao).
Pagamento, e-mail e push ficam no modo simulado (sem ASAAS_API_KEY, SMTP e VAPID).

Uso (na pasta Sistema-de-Delivery-Back, com o venv ativo):
    python postman/servidor_local_teste.py 8011
"""
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
PASTA = Path(tempfile.gettempdir()) / "entregafood-teste"
PASTA.mkdir(exist_ok=True)
BANCO = PASTA / "entregafood_teste.db"
AMBIENTE = PASTA / "ambiente_local.postman_environment.json"
BANCO.unlink(missing_ok=True)

# Precisa vir antes de importar o app: o config le essas variaveis na importacao
os.environ.update({"DATABASE_URL": f"sqlite:///{BANCO.as_posix()}", "CORS_ORIGINS": "http://localhost:5173",
                   "ASAAS_API_KEY": "", "SMTP_HOST": "", "VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": "",
                   "JWT_SECRET": secrets.token_urlsafe(32), "JWT_EXPIRE_MINUTES": "120"})
sys.path.insert(0, str(BACK))

import uvicorn  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import gerar_hash_senha  # noqa: E402
from app.main import app  # noqa: E402
from app.models.local import Local  # noqa: E402
from app.models.produto import Produto  # noqa: E402
from app.models.restaurante import Restaurante  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

Base.metadata.create_all(engine)

CONTAS = {
    "cliente_a": ("Ana Teste", "cliente"), "cliente_b": ("Bruno Teste", "cliente"),
    "dono_1": ("Dono Burger", "restaurante"), "dono_2": ("Dono Pizzaria", "restaurante"),
    "entregador": ("Carlos Entregador", "entregador"),
}
senhas = {k: "Tst" + secrets.token_urlsafe(9) for k in CONTAS}


def email(chave):
    return f"{chave.replace('_', '.')}@teste.entregafood.com"


with SessionLocal() as db:
    agora = datetime.now()
    u = {}
    for chave, (nome, tipo) in CONTAS.items():
        u[chave] = Usuario(nome=nome, email=email(chave), tipo=tipo, senha_hash=gerar_hash_senha(senhas[chave]), criado_em=agora)
        db.add(u[chave])
    db.flush()
    l1 = Local(usuario_id=u["dono_1"].id, endereco="Av. Paulista, 1000, Bela Vista, São Paulo - SP", tipo="restaurante",
               latitude=Decimal("-23.561414"), longitude=Decimal("-46.655881"), criado_em=agora)
    l2 = Local(usuario_id=u["dono_2"].id, endereco="Rua Augusta, 1500, Consolação, São Paulo - SP", tipo="restaurante",
               latitude=Decimal("-23.558300"), longitude=Decimal("-46.661500"), criado_em=agora)
    la = Local(usuario_id=u["cliente_a"].id, endereco="Praça da Sé, 1, Sé, São Paulo - SP", tipo="Casa",
               latitude=Decimal("-23.550520"), longitude=Decimal("-46.633308"), criado_em=agora)
    lb = Local(usuario_id=u["cliente_b"].id, endereco="Rua Vergueiro, 1000, Liberdade, São Paulo - SP", tipo="Casa",
               latitude=Decimal("-23.570000"), longitude=Decimal("-46.639000"), criado_em=agora)
    db.add_all([l1, l2, la, lb])
    db.flush()
    r1 = Restaurante(local_id=l1.id, usuario_id=u["dono_1"].id, nome_fantasia="Burger Teste", cnpj="11.111.111/0001-11",
                     status_aprovacao="aprovado", taxa_entrega_km=Decimal("2.00"), ativo=True, criado_em=agora)
    r2 = Restaurante(local_id=l2.id, usuario_id=u["dono_2"].id, nome_fantasia="Pizzaria Teste", cnpj="22.222.222/0001-22",
                     status_aprovacao="aprovado", taxa_entrega_km=Decimal("2.00"), ativo=True, criado_em=agora)
    db.add_all([r1, r2])
    db.flush()
    db.add_all([Produto(restaurante_id=r1.id, nome="X-Burger", descricao="Pão, carne e queijo", preco=Decimal("25.00"), disponivel=True),
                Produto(restaurante_id=r2.id, nome="Pizza Margherita", descricao="Média", preco=Decimal("45.00"), disponivel=True)])
    db.commit()

ambiente = {"name": "EntregaFood — teste local", "values":
            [{"key": "base_url", "value": f"http://127.0.0.1:{PORTA}", "enabled": True}]
            + [{"key": f"email_{k}", "value": email(k), "enabled": True} for k in CONTAS]
            + [{"key": f"senha_{k}", "value": v, "type": "secret", "enabled": True} for k, v in senhas.items()]}
AMBIENTE.write_text(json.dumps(ambiente, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Banco de teste: {BANCO}\nAmbiente do Postman: {AMBIENTE}\nAPI em http://127.0.0.1:{PORTA}", flush=True)
uvicorn.run(app, host="127.0.0.1", port=PORTA, log_level="warning")
