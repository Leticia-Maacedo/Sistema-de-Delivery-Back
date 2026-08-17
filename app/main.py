"""Ponto de entrada da API EntregaFood.

Arquitetura MVC:
    app/models/       -> MODEL      (SQLAlchemy + regras de negocio)
    app/schemas/      -> VIEW       (Pydantic: formato do JSON)
    app/controllers/  -> CONTROLLER (routers FastAPI)

Executar:  uvicorn app.main:app --reload
Swagger:   http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.controllers import auth_controller, oauth_controller, usuario_controller
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="EntregaFood API",
    description=(
        "API REST da plataforma EntregaFood. "
        "Sprint 1 — CRUD de Usuário e autenticação por e-mail/senha."
    ),
    version="1.0.0",
)

# CORS: libera o front (Vite roda em 5173) a chamar a API em 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exigido pelo Authlib para guardar o "state" do OAuth entre o redirect
# de ida e o de volta (login social do Google/Facebook).
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)

app.include_router(usuario_controller.router)
app.include_router(auth_controller.router)
app.include_router(oauth_controller.router)


@app.get("/", tags=["Status"], summary="Verificação de saúde da API")
def raiz() -> dict[str, str]:
    return {"status": "ok", "aplicacao": "EntregaFood API", "versao": "1.0.0"}
