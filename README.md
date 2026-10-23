# EntregaFood — Backend

API REST da plataforma EntregaFood, construída em **Python 3.12 + FastAPI 0.115**, seguindo a arquitetura **MVC**, com persistência em **PostgreSQL 16**.

**Sprint 1** — CRUD de Usuário e autenticação por e-mail/senha com JWT.
**Sprint 2** — Consulta de Restaurante e Cardápio pelo cliente.
**Extra** — CRUD de Restaurante, Produto e Local (endereço, pré-requisito da cadeia).
**Grupo:** Amigos do Gilberto · Turma A · Faculdade Impacta

**📚 Documentação detalhada:** [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) (padrão MVC, ciclo de vida da requisição, autenticação, débitos técnicos) · [`docs/BANCO_DE_DADOS.md`](docs/BANCO_DE_DADOS.md) (schema completo, diagrama ER) · [`docs/API.md`](docs/API.md) (todos os endpoints e métodos de Model por trás de cada um).

---

## Funcionalidades implementadas

| # | Funcionalidade | Onde | Status |
|---|---|---|---|
| 1 | Autenticação por e-mail/senha com JWT | `POST /auth/login`, `GET /auth/eu` | ✅ |
| 2 | CRUD de Usuário (cadastro, consulta, edição, exclusão) | `/usuarios` | ✅ |
| 3 | CRUD de Restaurante | `/restaurantes` | ✅ |
| 4 | CRUD de Produto | `/produtos` | ✅ |
| 5 | Consulta de Restaurante (visão do cliente) | `GET /consultas/restaurantes`, `GET /consultas/restaurantes/{id}` | ✅ |
| 6 | Consulta de Itens/Cardápio (visão do cliente) | `GET /consultas/restaurantes/{id}/cardapio` | ✅ |
| 7 | Listagem e busca de Restaurantes (`?busca=`) | `GET /consultas/restaurantes?busca=` | ✅ |
| 8 | CRUD de Local (endereço) | `/locais` | ✅ |
| 9 | Login por telefone com código OTP + cadastro por telefone | `/auth/telefone/*` | ✅ |
| 10 | Login social (Google/Facebook) | `/auth/google`, `/auth/facebook` | ✅ implementado (ver Limitações sobre uso em modo de teste) |
| 11 | Coleção Postman com todos os endpoints acima | [`postman/EntregaFood.postman_collection.json`](postman/EntregaFood.postman_collection.json) | ✅ |
| 12 | Cesta (incluir, consultar, alterar quantidade, excluir) com limite de 99 unidades e restaurante único | `/cesta`, `/cesta/itens` | ✅ |
| 13 | Resumo da cesta: subtotal, taxa de entrega pela distância e total | `GET /cesta/resumo` | ✅ |
| 14 | Fechamento do pedido: valida cesta vazia, disponibilidade, quantidade, endereço e raio; copia os itens para `item_pedido`; esvazia a cesta | `POST /pedidos` | ✅ |
| 15 | Escolha do tipo de pagamento e pagamento por cartão (gateway simulado) | `/pagamentos` | ✅ simulado |
| 16 | Tipo de entrega no fechamento (delivery com taxa pela distância ou retirada no balcão sem taxa) | `POST /pedidos`, `GET /cesta/resumo` | ✅ |
| 17 | Acompanhamento do pedido: linha do tempo de status, painel do restaurante/entregador e conclusão com código de entrega | `/pedidos`, `/pedidos/painel`, `/pedidos/{id}/status`, `/pedidos/{id}/entrega/confirmar` | ✅ |
| 18 | Avaliação | — | ❌ não implementado (só tabela no `sql/`) |

Essa tabela é o inventário de referência: toda vez que uma funcionalidade nova entrar no backend, adicione uma linha aqui.

---

## Arquitetura MVC

O padrão MVC separa a aplicação em três responsabilidades, e a estrutura de pastas reflete isso diretamente:

```
app/
├── models/          MODEL      → SQLAlchemy + regras de negócio
│   ├── usuario.py              (mapeia a tabela usuario, valida e-mail único, tipo de perfil)
│   ├── local.py                (mapeia a tabela local — endereço, pré-requisito de Restaurante)
│   ├── restaurante.py          (mapeia a tabela restaurante, valida CNPJ único)
│   └── produto.py              (mapeia a tabela produto, vinculado a um restaurante)
├── schemas/         VIEW       → Pydantic: formato do JSON de entrada e saída
│   ├── usuario.py              (define o que entra e — importante — o que NÃO sai)
│   ├── local.py
│   ├── restaurante.py
│   ├── produto.py
│   └── consulta.py             (formato de saída das consultas do cliente)
├── controllers/     CONTROLLER → routers FastAPI: recebem HTTP e orquestram
│   ├── usuario_controller.py   (as 4 operações do CRUD)
│   ├── auth_controller.py      (login, OTP por telefone, login social e rota protegida)
│   ├── local_controller.py     (as 4 operações do CRUD)
│   ├── restaurante_controller.py (as 4 operações do CRUD)
│   ├── produto_controller.py   (as 4 operações do CRUD)
│   └── consulta_controller.py  (leitura, visão do cliente: restaurantes aprovados e cardápio)
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

### 6. Testar com Postman

O arquivo [`postman/EntregaFood.postman_collection.json`](postman/EntregaFood.postman_collection.json) tem todos os endpoints prontos para importar (Postman → Import → arraste o arquivo). Ele já vem organizado em pastas (Autenticação, Usuários, Locais, Restaurantes, Produtos, Consultas) e os requests de criação (`POST`) salvam automaticamente o `id` retornado — e o login salva o `token` — em variáveis da coleção, então dá pra rodar a coleção inteira em sequência (Cadastrar usuário → Login → Local → Restaurante → Produto → Consultas) sem copiar/colar nada manualmente. A única variável que costuma precisar de ajuste é `base_url` (padrão `http://localhost:8000`).

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

Além do escopo mínimo da Sprint 1, os CRUDs de **Local**, **Restaurante** e **Produto** foram implementados por completo (com telas no front-end). Como `produto` exige um `restaurante_id`, e `restaurante` exige um `local_id`, a cadeia de pré-requisitos ficou assim:

**Usuário** (Sprint 1) → **Local** (CRUD completo, endereço) → **Restaurante** (CRUD completo) → **Produto** (CRUD completo)

| Método | Rota | Operação | Retorno |
|---|---|---|---|
| `POST` | `/locais` | CREATE | `201` |
| `GET` | `/locais` | READ (lista, filtra por `?usuario_id=`) | `200` |
| `GET` | `/locais/{id}` | READ (por id) | `200` · `404` |
| `PUT` | `/locais/{id}` | UPDATE | `200` · `404` |
| `DELETE` | `/locais/{id}` | DELETE | `204` · `404` |
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

## Endpoints da Sprint 2 — consulta de Restaurante e Cardápio

As rotas de `/restaurantes` e `/produtos` acima são de **administração**: devolvem tudo, sem filtro. A Sprint 2 adiciona a visão do **cliente** que navega no app — só o que ele pode pedir. São endpoints de leitura, agrupados sob `/consultas`.

| Método | Rota | O que devolve | Retorno |
|---|---|---|---|
| `GET` | `/consultas/restaurantes` | Só restaurantes `status_aprovacao = 'aprovado'`, com o endereço embutido. Filtra por nome com `?busca=` | `200` |
| `GET` | `/consultas/restaurantes/{id}` | Um restaurante aprovado + endereço (sem CNPJ) | `200` · `404` se pendente/recusado/inexistente |
| `GET` | `/consultas/restaurantes/{id}/cardapio` | Dados do restaurante + lista dos itens com `disponivel = true` + `total_itens` | `200` · `404` |

Diferenças em relação ao CRUD: a consulta **não** expõe CNPJ, **não** mostra restaurante não-aprovado e **não** lista item indisponível.

### Exemplo

```bash
curl "http://localhost:8000/consultas/restaurantes?busca=burger"
curl http://localhost:8000/consultas/restaurantes/1/cardapio
```

### Dados de exemplo

O script `sql/04_seed_cardapio.sql` popula a cadeia inteira (3 restaurantes — 2 aprovados, 1 pendente — e 7 produtos, 1 indisponível) para ter o que consultar. É idempotente:

```bash
psql -h localhost -U postgres -d entregafood -f sql/04_seed_cardapio.sql
```

---

## Endpoints da Sprint 3 — cesta e fechamento do pedido

| Método | Rota | O que faz | Retorno |
|---|---|---|---|
| `GET` | `/cesta` | Cesta do usuário logado (itens, subtotais e total) | `200` |
| `POST` | `/cesta/itens` | Inclui produto (soma se já existir). Bloqueia indisponível, restaurante diferente e mais de 99 unidades | `201` · `400` · `404` |
| `PUT` | `/cesta/itens/{produto_id}` | Altera a quantidade | `200` · `400` · `404` |
| `DELETE` | `/cesta/itens/{produto_id}` | Remove o produto da cesta | `200` · `404` |
| `GET` | `/cesta/resumo?local_id=&tipo_entrega=` | Subtotal, taxa de entrega, total, distância e se o pedido pode ser fechado (`pode_fechar` + `motivo`) | `200` · `403` · `404` |
| `POST` | `/pedidos` | Cria o pedido a partir da cesta: recalcula os valores no servidor, copia os itens para `item_pedido` e esvazia a cesta | `201` · `400` |

**Taxa de entrega** (`app/core/frete.py`): `taxa = max(mínima, base + taxa_entrega_km do restaurante × km além dos incluídos)`, arredondada para cima em R$ 0,10. A distância vem do OpenRouteService (pela rua) quando `ORS_API_KEY` está no `.env`; sem a chave, usa a linha reta × `FRETE_FATOR_CIRCUITO` (1,6). Base, km incluídos, taxa mínima e raio máximo (8 km) também ficam no `.env`. Retirada no balcão (`tipo_entrega=retirada`) não tem taxa.

O `POST /pedidos` ignora `valor_total`, `taxa_entrega` e `restaurante_id` vindos do front: tudo é calculado a partir da cesta. Sem `local_id`, usa o último endereço cadastrado do cliente.

Testes: `python -m pytest testes/teste_cesta.py testes/teste_fechamento_cesta.py` e as coleções `postman/Teste_*_Cesta.postman_collection.json` (inclusão, consulta, alteração, exclusão, subtotal/total e validações).

## Endpoints da Sprint 3 — acompanhar entrega

Antes de usar, rode o script novo no banco (também roda sozinho num banco Docker criado do zero):

```bash
psql -h localhost -U postgres -d entregafood -f sql/05_sprint3_acompanhamento.sql
psql -h localhost -U postgres -d entregafood -f sql/06_sprint3_dono_e_entregador.sql
```

| Método | Rota | Quem | O que faz | Retorno |
|---|---|---|---|---|
| `GET` | `/pedidos` | cliente | Meus pedidos, do mais recente para o mais antigo | `200` |
| `GET` | `/pedidos/{id}` | dono do pedido, restaurante dono, entregador, admin | Itens, linha do tempo (`etapas`) e, só para o cliente, o `codigo_entrega` | `200` · `403` · `404` |
| `GET` | `/pedidos/painel?incluir_finalizados=` | restaurante, entregador, admin | Pedidos em andamento (o restaurante só vê os dele) | `200` · `403` |
| `PATCH` | `/pedidos/{id}/status` | restaurante, entregador, admin | Avança para a próxima etapa (ou `cancelado`) | `200` · `400` · `403` |
| `POST` | `/pedidos/{id}/entrega/confirmar` | entregador (delivery), restaurante (retirada), admin | Confere o código informado pelo cliente e marca `entregue` | `200` · `400` · `403` |

**Fluxo de status** (`app/core/status_pedido.py`):

- Delivery: `aguardando_aceite → aceito → em_preparacao → pronto_para_entrega → em_transito → entregue`
- Retirada: `aguardando_aceite → aceito → em_preparacao → pronto_para_retirada → entregue`

Regras: não dá para pular nem voltar etapas; o restaurante só aceita depois do pagamento aprovado; o restaurante aceita, prepara e deixa pronto; o entregador marca `em_transito`; `entregue` só com o código de 4 dígitos que o cliente vê na tela de acompanhamento; o pedido só pode ser cancelado em `aguardando_aceite` ou `aceito`. Cada mudança grava uma linha em `pedido_status_historico`, e o código fica em `entrega.codigo_validacao`.

**Dono do restaurante** (`restaurante.usuario_id`, script `06`): o usuário restaurante só vê e movimenta pedidos dos restaurantes dele. O dono é gravado no `POST /restaurantes` — é o usuário restaurante logado (Área do Parceiro) ou, quando quem cadastra é o admin, o usuário do endereço (`local`) se ele for do tipo restaurante. O script `06` preenche o dono dos restaurantes que já existiam da mesma forma.

**Entregador**: fica só em `entrega.entregador_id` (a coluna `pedido.entregador_id` foi removida no script `06`, por ser redundante). Quem marca `em_transito` vira o entregador do pedido, e só ele confirma a entrega.

Para testar o painel, crie usuários com `"tipo": "restaurante"` e `"tipo": "entregador"` pelo `POST /usuarios` e cadastre o restaurante logado com o usuário restaurante.

Testes: `python -m pytest testes/teste_status_pedido.py`.

---

## Endpoints da Sprint 3 — notificações push e rastreio da entrega

Antes de usar, rode `sql/07_sprint3_push.sql` no banco e configure `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` e `VAPID_SUBJECT` no `.env` (e no Render). Sem as chaves, tudo funciona, só não envia push.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `GET` | `/notificacoes/chave-publica` | qualquer um | Chave pública VAPID para o navegador se inscrever |
| `POST` | `/notificacoes/inscricao` | logado | Ativa as notificações neste navegador (`PushSubscription` do navegador) |
| `DELETE` | `/notificacoes/inscricao` | logado | Desativa as notificações neste navegador |
| `GET` | `/pedidos/{id}/rastreio` | dono, restaurante dono, entregador, admin | Restaurante, destino e posição do entregador, com link do Google Maps |
| `PATCH` | `/pedidos/{id}/entrega/localizacao` | entregador que saiu com o pedido | Envia a posição atual (só com o pedido em trânsito) |

**Quem recebe push** (`app/core/notificacoes_pedido.py`, enviado em segundo plano, nunca quebra o pedido): pedido criado → cliente e restaurante dono; cada mudança de status → cliente; `pronto_para_entrega` (delivery) → todos os entregadores. Usa Web Push padrão (`pywebpush`), sem depender de conta em serviço externo.

Testes: `python -m pytest testes/teste_notificacoes_rastreio.py`.

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

A consulta da Sprint 2 tem a bateria `teste_consulta_cardapio.py` — monta um restaurante aprovado, um pendente e um item indisponível, e verifica as regras de visibilidade (só aprovado aparece na lista/detalhe; só item disponível entra no cardápio; `?busca=` filtra por nome):

```bash
python testes/teste_consulta_cardapio.py
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

- **Login social (Google/Facebook)**: implementado (`/auth/google`, `/auth/facebook` + callback). Enquanto os apps OAuth ficam em modo de teste nos dois provedores, só e-mails cadastrados manualmente como "tester" conseguem logar — inviável pra qualquer colega ou o professor testar sem antes pedir acesso. Publicar os apps de verdade exigiria mais burocracia (política de privacidade, revisão) do que vale a pena pra esse projeto. Pra demonstração, o caminho garantido continua sendo e-mail/senha.
- **Verificação por SMS**: o OTP de telefone (`/auth/telefone/*`) gera e valida o código no próprio backend, mas não envia SMS de verdade — o endpoint devolve o código em `codigo_dev` pra facilitar teste/demonstração. Integração real com Twilio foi avaliada, mas a conta trial não permite nem buscar números disponíveis sem upgrade (cartão de crédito).
- **Autorização em Restaurante e Produto**: só as rotas de `/usuarios` checam dono-ou-admin. `PUT`/`DELETE` de `/restaurantes/{id}` e `/produtos/{id}` ainda não exigem login — qualquer requisição altera qualquer registro pelo `id`. Funciona porque o front só deixa quem é `restaurante` chegar na tela de Produtos, mas a API em si confiaria em qualquer chamada — vale estender a mesma checagem de `usuario_controller.py` pra esses dois controllers numa próxima sprint.
- **Pagamento**: o gateway de cartão é simulado (`app/core/pagamento_cartao.py`); ver `docs/pesquisas` para a integração real recomendada (Mercado Pago em modo de teste).
- **Estoque**: não há coluna de estoque; no fechamento são revalidados disponibilidade e o limite de 99 unidades por produto.
- **Dono do restaurante**: a tabela `restaurante` não tem o usuário dono, então no painel de pedidos qualquer usuário do tipo `restaurante` vê e movimenta os pedidos de todos os restaurantes. Ligar restaurante ↔ usuário resolve isso e permite filtrar o painel por restaurante.
- **Notificação ao cliente**: a tela de acompanhamento consulta o pedido a cada 10 s; não há push/e-mail a cada mudança de status (itens 21 e 23 do Backlog).
- **Avaliação**: tabela só no `sql/`, sem model/controller/endpoint.

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
