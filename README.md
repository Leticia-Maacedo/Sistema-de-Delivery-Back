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

### 1. Subir o banco PostgreSQL

Duas formas — use a que funcionar melhor na sua máquina.

**Opção A — Docker (padrão do projeto):**

```bash
docker compose up -d
docker compose ps          # confirmar que o container está saudável
```

O `docker-compose.yml` monta a pasta `sql/` em `/docker-entrypoint-initdb.d`, então as 11 tabelas são criadas automaticamente na primeira subida.

**Opção B — [Postgres.app](https://postgresapp.com) (macOS, sem Docker):**

Se não tiver o Docker Desktop instalado (ou, como no caso desta máquina, o Docker via Homebrew/Colima exigir compilar tudo do zero por falta de binários para a versão do macOS), o Postgres.app é um Postgres nativo, sem VM e sem compilar nada:

```bash
# depois de instalar o Postgres.app e abrir ele pelo menos uma vez
# (ou inicializar via linha de comando com initdb + pg_ctl start)
createdb -h localhost -p 5432 -U postgres entregafood
psql -h localhost -p 5432 -U postgres -d entregafood -f sql/01_create_tables.sql
```

Ajuste o `DATABASE_URL` no `.env` para apontar pro usuário/porta que o Postgres.app estiver usando.

### 2. Criar o ambiente virtual e instalar as dependências

Use **Python 3.12** — algumas dependências (`pydantic-core`, `bcrypt`) ainda não têm wheels prontos para versões mais novas do Python em todas as plataformas.

```bash
python3.12 -m venv .venv

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

### 5. Subir o front-end (opcional, mas é pra isso que a API existe)

O front-end mora num repositório separado: [Sistema-de-Delivery-Front](https://github.com/Leticia-Maacedo/Sistema-de-Delivery-Front).

```bash
git clone https://github.com/Leticia-Maacedo/Sistema-de-Delivery-Front.git
cd Sistema-de-Delivery-Front
npm install
npm run dev
```

Fica em http://localhost:5173 — já vem configurado pra falar com a API em `http://localhost:8000` (o CORS do back já libera essa origem por padrão).

---

## Endpoints da Sprint 1

O escopo da Sprint 1 é só o domínio **Usuário**: cadastro, CRUD e autenticação. As outras 10 tabelas do `sql/` (restaurante, produto, pedido, entrega...) já existem no banco, mas não têm model/controller/endpoint ainda — ficam para as próximas sprints.

| Método | Rota | Operação | Requisito | Retorno |
|---|---|---|---|---|
| `POST` | `/usuarios` | **CREATE** | RF01 | `201` · `409` se e-mail duplicado |
| `GET` | `/usuarios` | **READ** (lista) | — | `200` |
| `GET` | `/usuarios/{id}` | **READ** (por id) | — | `200` · `404` |
| `PUT` | `/usuarios/{id}` | **UPDATE** | — | `200` · `404` · `409` |
| `DELETE` | `/usuarios/{id}` | **DELETE** | RF06 | `204` · `404` |
| `POST` | `/auth/login` | Autenticação e-mail/senha | RF02 | `200` · `401` |
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

- **Login social (Google/Facebook)**: chegou a ser implementado (`/auth/{provedor}/login` + callback via Authlib), mas foi removido. Enquanto os apps OAuth ficam em modo de teste nos dois provedores, só e-mails cadastrados manualmente como "tester" conseguem logar — inviável pra qualquer colega ou o professor testar sem antes pedir acesso. Publicar os apps de verdade exigiria mais burocracia (política de privacidade, revisão) do que vale a pena pra esse projeto. Login continua só por e-mail/senha.
- **Verificação por SMS**: a etapa de celular no cadastro (front-end) usa um código de 4 dígitos **simulado** — não envia SMS de verdade. Integração real com Twilio foi avaliada, mas a conta trial não permite nem buscar números disponíveis sem upgrade (cartão de crédito).
- **Endereço de entrega**: ainda não existe endpoint pra tabela `local`.
- **Autorização por dono do recurso**: `PUT /usuarios/{id}` e `DELETE /usuarios/{id}` não checam se quem está chamando é o dono da conta (não exigem o JWT). Funciona porque o front só deixa o usuário editar/excluir a própria conta, mas a API em si confiaria em qualquer `id` — vale endurecer isso numa próxima sprint.

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
