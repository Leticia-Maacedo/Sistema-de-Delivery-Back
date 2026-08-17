# EntregaFood — Backend

API REST da plataforma EntregaFood, construída em **Python 3.12 + FastAPI 0.115**, seguindo a arquitetura **MVC**, com persistência em **PostgreSQL 16**.

**Sprint 1** — CRUD de Usuário e autenticação por e-mail/senha com JWT.
**Extra** — CRUD de Restaurante e Produto (Local só com criação, pré-requisito da cadeia).
**Grupo:** Amigos do Gilberto · Turma A · Faculdade Impacta

---

## Arquitetura MVC

O padrão MVC separa a aplicação em três responsabilidades, e a estrutura de pastas reflete isso diretamente:

```
app/
├── models/          MODEL      → SQLAlchemy + regras de negócio
│   ├── usuario.py              (mapeia a tabela usuario, valida e-mail único, tipo de perfil)
│   ├── local.py                (mapeia a tabela local — só criação, pré-requisito de Restaurante)
│   ├── restaurante.py          (mapeia a tabela restaurante, valida CNPJ único)
│   └── produto.py              (mapeia a tabela produto, vinculado a um restaurante)
├── schemas/         VIEW       → Pydantic: formato do JSON de entrada e saída
│   ├── usuario.py              (define o que entra e — importante — o que NÃO sai)
│   ├── local.py
│   ├── restaurante.py
│   └── produto.py
├── controllers/     CONTROLLER → routers FastAPI: recebem HTTP e orquestram
│   ├── usuario_controller.py   (as 4 operações do CRUD)
│   ├── auth_controller.py      (login e rota protegida)
│   ├── local_controller.py     (só CREATE)
│   ├── restaurante_controller.py (as 4 operações do CRUD)
│   └── produto_controller.py   (as 4 operações do CRUD)
└── core/            Infraestrutura de apoio
    ├── config.py               (lê o .env)
    ├── database.py             (engine e sessão do SQLAlchemy)
    └── security.py             (hash de senha, JWT, middleware)
```

**A regra que mantém o padrão honesto:** se aparecer `status_code` dentro de `models/`, a regra de negócio vazou para o lugar errado. Se aparecer `db.commit()` dentro de `controllers/`, a persistência vazou. O Controller conversa com o Model; o Model conversa com o banco.

---

## Como rodar

### Opção rápida — tudo em Docker (banco + API + front-end)

Precisa só do [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado. Clone os dois repositórios lado a lado (mesma pasta-pai):

```bash
git clone https://github.com/Leticia-Maacedo/Sistema-de-Delivery-Back.git
git clone https://github.com/Leticia-Maacedo/Sistema-de-Delivery-Front.git
cd Sistema-de-Delivery-Back
cp .env.example .env        # no Windows: copy .env.example .env
docker compose -f docker-compose.full.yml up -d --build
```

| Endereço | O que é |
|---|---|
| http://localhost:5173 | Front-end |
| http://localhost:8000/docs | Swagger da API |
| http://localhost:5432 | PostgreSQL (`postgres`/`postgres`, banco `entregafood`) |

O código de `app/` e de `src/` (front) fica montado como volume — editar os arquivos localmente recarrega os containers automaticamente (`--reload` no backend, Vite no front). Pra derrubar tudo: `docker compose -f docker-compose.full.yml down` (o `-v` no final apaga também os dados do banco).

Essa opção sobe os três serviços de uma vez; é a rota mais rápida pra só usar o sistema. Quem vai mexer no código Python ou quer rodar sem Docker, siga os passos manuais abaixo — eles dão mais controle (debugger, breakpoints, ambiente Python nativo).

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

O escopo da Sprint 1 é o domínio **Usuário**: cadastro, CRUD e autenticação.

### Tipos de conta

A coluna `tipo` do `usuario` aceita quatro valores: `cliente`, `entregador` (motoboy), `restaurante` e `admin`. Os três primeiros podem se autocadastrar via `POST /usuarios` — **`admin` não pode**: o controller devolve `403` se alguém tentar criar uma conta admin por esse endpoint. Conta admin é provisionada manualmente (direto no banco, por enquanto), exatamente pra evitar que qualquer autocadastro vire admin da plataforma.

| Método | Rota | Operação | Requisito | Quem pode | Retorno |
|---|---|---|---|---|---|
| `POST` | `/usuarios` | **CREATE** | RF01 | qualquer um (exceto tipo `admin`) | `201` · `409` · `403` |
| `GET` | `/usuarios` | **READ** (lista todo mundo) | — | só `admin` | `200` · `401` · `403` |
| `GET` | `/usuarios/{id}` | **READ** (por id) | — | o dono da conta ou `admin` | `200` · `401` · `403` · `404` |
| `PUT` | `/usuarios/{id}` | **UPDATE** | — | o dono da conta ou `admin`¹ | `200` · `401` · `403` · `404` · `409` |
| `DELETE` | `/usuarios/{id}` | **DELETE** | RF06 | o dono da conta ou `admin` | `204` · `401` · `403` · `404` |
| `POST` | `/auth/login` | Autenticação e-mail/senha | RF02 | qualquer um | `200` · `401` |
| `GET` | `/auth/eu` | Rota protegida | RF02 | quem estiver logado | `200` · `401` |

¹ Só um `admin` pode alterar o campo `tipo` de uma conta (promover/rebaixar um perfil) — o próprio dono pode editar nome/e-mail/telefone, mas não o próprio tipo.

Todas essas rotas (exceto `POST /usuarios` e `POST /auth/login`) exigem `Authorization: Bearer <token>`. Quem não é dono da conta nem admin recebe `403` sem descobrir se o `id` existe — a checagem de permissão roda antes da checagem de existência, de propósito, pra não vazar informação.

### Painel de administração

Um `admin` logado consegue listar, consultar, editar e excluir a conta de **qualquer** usuário — é o que sustenta a aba "Usuários" do front-end (`src/views/admin/UsuariosView.jsx` no repo do front), com CRUD completo: buscar, criar, editar e excluir qualquer conta. Como não existe autocadastro de admin, pra testar isso localmente você precisa provisionar um direto no banco:

```sql
-- depois de gerar um hash bcrypt (veja abaixo), rode algo assim:
INSERT INTO usuario (nome, email, senha_hash, tipo)
VALUES ('Admin', 'admin@entregafood.com', '<hash bcrypt aqui>', 'admin');
```

Gerar o hash com o próprio back-end (mesmo algoritmo que a API usa):

```bash
python -c "from app.core.security import gerar_hash_senha; print(gerar_hash_senha('sua-senha-aqui'))"
```

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

## Endpoints extras — Restaurante e Produto

Além do escopo mínimo da Sprint 1, o CRUD de **Produto** foi implementado por completo (com tela no front-end). Como `produto` exige um `restaurante_id`, e `restaurante` exige um `local_id`, a cadeia de pré-requisitos ficou assim:

**Usuário** (Sprint 1) → **Local** (só `POST`, o suficiente pra existir um endereço) → **Restaurante** (CRUD completo) → **Produto** (CRUD completo)

| Método | Rota | Operação | Retorno |
|---|---|---|---|
| `POST` | `/locais` | CREATE | `201` |
| `POST` | `/restaurantes` | CREATE | `201` · `409` se CNPJ duplicado |
| `GET` | `/restaurantes` | READ (lista) | `200` |
| `GET` | `/restaurantes/{id}` | READ (por id) | `200` · `404` |
| `PUT` | `/restaurantes/{id}` | UPDATE | `200` · `404` · `409` |
| `DELETE` | `/restaurantes/{id}` | DELETE | `204` · `404` |
| `POST` | `/produtos` | CREATE | `201` · `422` se restaurante não existe |
| `GET` | `/produtos` | READ (lista, filtra por `?restaurante_id=`) | `200` |
| `GET` | `/produtos/{id}` | READ (por id) | `200` · `404` |
| `PUT` | `/produtos/{id}` | UPDATE | `200` · `404` |
| `DELETE` | `/produtos/{id}` | DELETE | `204` · `404` |

### Exemplo: cadastrar a cadeia inteira

```bash
# 1. Local (usuario_id precisa existir)
curl -X POST http://localhost:8000/locais -H "Content-Type: application/json" \
  -d '{"usuario_id":1,"endereco":"Rua das Flores, 123","tipo":"restaurante","latitude":"-23.550520","longitude":"-46.633308"}'

# 2. Restaurante (local_id = id devolvido acima)
curl -X POST http://localhost:8000/restaurantes -H "Content-Type: application/json" \
  -d '{"local_id":1,"nome_fantasia":"Cantinho do Chef","cnpj":"12.345.678/0001-90","taxa_entrega_km":"2.50"}'

# 3. Produto (restaurante_id = id devolvido acima)
curl -X POST http://localhost:8000/produtos -H "Content-Type: application/json" \
  -d '{"restaurante_id":1,"nome":"X-Salada","preco":"24.90"}'
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

São 30 verificações cobrindo as 4 operações do CRUD, login válido e inválido, o middleware de sessão, a gravação do hash bcrypt e as regras de autorização (dono da conta vs. conta alheia vs. admin).

Da mesma forma, o CRUD de **Produto** tem sua própria bateria (cria a cadeia Local → Restaurante → Produto e verifica cada operação direto na tabela `produto`):

```bash
python testes/teste_crud_produto.py
```

---

## Segurança

- Senhas armazenadas com **bcrypt**, nunca em texto puro (RNF03). `requirements.txt` trava `bcrypt<4.1` de propósito — versões mais novas quebram o `passlib` 1.7.4 (projeto sem atualização desde 2020), que não reconhece o novo esquema de versionamento do bcrypt e derruba qualquer cadastro com 500.
- `senha_hash` **não aparece em nenhuma resposta da API** — o schema `UsuarioOut` simplesmente não tem esse campo.
- Autenticação por **JWT Bearer**, com expiração configurável.
- O login devolve mensagem genérica ("E-mail ou senha incorretos") de propósito, para não revelar quais e-mails existem na base.
- CORS restrito às origens listadas no `.env`.

---

## Limitações conhecidas

- **Login social (Google/Facebook)**: chegou a ser implementado (`/auth/{provedor}/login` + callback via Authlib), mas foi removido. Enquanto os apps OAuth ficam em modo de teste nos dois provedores, só e-mails cadastrados manualmente como "tester" conseguem logar — inviável pra qualquer colega ou o professor testar sem antes pedir acesso. Publicar os apps de verdade exigiria mais burocracia (política de privacidade, revisão) do que vale a pena pra esse projeto. Login continua só por e-mail/senha.
- **Verificação por SMS**: a etapa de celular no cadastro (front-end) usa um código de 4 dígitos **simulado** — não envia SMS de verdade. Integração real com Twilio foi avaliada, mas a conta trial não permite nem buscar números disponíveis sem upgrade (cartão de crédito).
- **Local**: só tem `POST` — não há edição/exclusão de endereço, pois não era o foco desta entrega (é só pré-requisito da cadeia até Produto).
- **Autorização em Restaurante e Produto**: só as rotas de `/usuarios` checam dono-ou-admin. `PUT`/`DELETE` de `/restaurantes/{id}` e `/produtos/{id}` ainda não exigem login — qualquer requisição altera qualquer registro pelo `id`. Funciona porque o front só deixa quem é `restaurante` chegar na tela de Produtos, mas a API em si confiaria em qualquer chamada — vale estender a mesma checagem de `usuario_controller.py` pra esses dois controllers numa próxima sprint.
- **Sacola, Pedido, Pagamento, Entrega, Avaliação**: as demais tabelas do schema continuam só no `sql/`, sem model/controller/endpoint.

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
