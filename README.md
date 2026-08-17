# EntregaFood — Backend

API REST da plataforma EntregaFood, construída em **Python 3.12 + FastAPI 0.115**, seguindo a arquitetura **MVC**, com persistência em **PostgreSQL 16**.

**Sprint 1** — CRUD de Usuário e autenticação por e-mail/senha com JWT.
**Grupo:** Amigos do Gilberto · Turma A · Faculdade Impacta

---

## Arquitetura MVC

O padrão MVC separa a aplicação em três responsabilidades, e a estrutura de pastas reflete isso diretamente:

```
app/
├── models/          MODEL      → SQLAlchemy + regras de negócio
│   └── usuario.py              (mapeia a tabela usuario, valida e-mail único, tipo de perfil)
├── schemas/         VIEW       → Pydantic: formato do JSON de entrada e saída
│   └── usuario.py              (define o que entra e — importante — o que NÃO sai)
├── controllers/     CONTROLLER → routers FastAPI: recebem HTTP e orquestram
│   ├── usuario_controller.py   (as 4 operações do CRUD)
│   └── auth_controller.py      (login e rota protegida)
└── core/            Infraestrutura de apoio
    ├── config.py               (lê o .env)
    ├── database.py             (engine e sessão do SQLAlchemy)
    └── security.py             (hash de senha, JWT, middleware)
```

**A regra que mantém o padrão honesto:** se aparecer `status_code` dentro de `models/`, a regra de negócio vazou para o lugar errado. Se aparecer `db.commit()` dentro de `controllers/`, a persistência vazou. O Controller conversa com o Model; o Model conversa com o banco.

---

## Como rodar

### 1. Subir o banco (Docker)

```bash
docker compose up -d
docker compose ps          # confirmar que o container está saudável
```

O `docker-compose.yml` monta a pasta `sql/` em `/docker-entrypoint-initdb.d`, então as 11 tabelas são criadas automaticamente na primeira subida.

### 2. Criar o ambiente virtual e instalar as dependências

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar as variáveis de ambiente

```bash
cp .env.example .env        # no Windows: copy .env.example .env
```

Abra o `.env` e troque o `JWT_SECRET` por um valor aleatório e longo. O `.env` está no `.gitignore` e **nunca deve ser commitado**.

### 4. Subir a API

```bash
uvicorn app.main:app --reload
```

| Endereço | O que é |
|---|---|
| http://localhost:8000 | Verificação de saúde |
| http://localhost:8000/docs | Swagger (documentação interativa) |
| http://localhost:8000/redoc | ReDoc |

---

## Endpoints da Sprint 1

| Método | Rota | Operação | Requisito | Retorno |
|---|---|---|---|---|
| `POST` | `/usuarios` | **CREATE** | RF01 | `201` · `409` se e-mail duplicado |
| `GET` | `/usuarios` | **READ** (lista) | — | `200` |
| `GET` | `/usuarios/{id}` | **READ** (por id) | — | `200` · `404` |
| `PUT` | `/usuarios/{id}` | **UPDATE** | — | `200` · `404` · `409` |
| `DELETE` | `/usuarios/{id}` | **DELETE** | RF06 | `204` · `404` |
| `POST` | `/auth/login` | Autenticação | RF02 | `200` · `401` |
| `GET` | `/auth/eu` | Rota protegida | RF02 | `200` · `401` |

### Exemplo de cadastro

```bash
curl -X POST http://localhost:8000/usuarios \
  -H "Content-Type: application/json" \
  -d '{"nome":"Geovane Soares","email":"geovane@entregafood.com","senha":"senha123","telefone":"11999998888","tipo":"cliente"}'
```

### Exemplo de login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"geovane@entregafood.com","senha":"senha123"}'
```

---

## Casos de teste cobertos

| ID | Caso | Verificação |
|---|---|---|
| **CT01** | Cadastro com e-mail válido | `POST /usuarios` → `201` e registro na tabela |
| **CT02** | Login com credenciais inválidas | `POST /auth/login` → `401` |
| **CT04** | Cadastro com e-mail já existente | `POST /usuarios` → `409` |

Execute a bateria completa. **Ela roda contra o PostgreSQL real**, o mesmo banco da aplicação — cada verificação consulta a tabela `usuario` diretamente com `SELECT` para provar que o efeito chegou ao banco:

```bash
python testes/teste_crud_sprint1.py
```

São 20 verificações cobrindo as 4 operações do CRUD, o login válido e inválido, o middleware de sessão e a gravação do hash bcrypt.

---

## Segurança

- Senhas armazenadas com **bcrypt**, nunca em texto puro (RNF03).
- `senha_hash` **não aparece em nenhuma resposta da API** — o schema `UsuarioOut` simplesmente não tem esse campo.
- Autenticação por **JWT Bearer**, com expiração configurável.
- O login devolve mensagem genérica ("E-mail ou senha incorretos") de propósito, para não revelar quais e-mails existem na base.
- CORS restrito às origens listadas no `.env`.

---

## Limitações conhecidas

- **Verificação por SMS**: a etapa de celular no cadastro (front-end) usa um código de 4 dígitos **simulado** — não envia SMS de verdade. Integração real com Twilio foi avaliada, mas a conta trial não permite nem buscar números disponíveis sem upgrade (cartão de crédito). Fica pendente para quando o grupo decidir assinar um plano pago.
- **Login social (Google/Facebook)**: os botões existem na UI mas ainda não estão funcionais — dependem de credenciais OAuth (Client ID/Secret) que precisam ser criadas no Google Cloud Console e no Meta for Developers.

---

## Divisão de responsabilidades — Sprint 1

| Arquivo | Responsável |
|---|---|
| `app/core/config.py`, `database.py`, `main.py` | Geovane |
| `app/models/usuario.py` | Geovane |
| `app/schemas/usuario.py` | Geovane |
| `app/controllers/usuario_controller.py` | Geovane |
| `app/core/security.py` | Letícia |
| `app/controllers/auth_controller.py` | Letícia |
| `docker-compose.yml`, `sql/` | Richard |
| `testes/` e coleção Postman | Anna |

---

## Convenção de branches

```
main                    ← protegida, entra só via Pull Request
sprint1/crud-usuario    ← Geovane
sprint1/autenticacao    ← Letícia
sprint1/infra-banco     ← Richard
sprint1/testes-api      ← Anna
```
