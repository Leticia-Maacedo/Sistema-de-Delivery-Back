# EntregaFood — Backend

API REST da plataforma EntregaFood, construída em **Python 3.12 + FastAPI 0.115**, seguindo a arquitetura **MVC**, com persistência em **PostgreSQL** (16 no Docker local; Neon em produção).

**Sprint 1** — CRUD de Usuário e autenticação por e-mail/senha com JWT.
**Sprint 2** — Consulta de Restaurante e Cardápio pelo cliente.
**Sprint 3** — Cesta, fechamento do pedido, taxa de entrega pela distância, pagamento (cartão, PIX e dinheiro), nota fiscal simulada, acompanhamento da entrega, notificações push no navegador, Portal do Parceiro e minha conta.
**Sprint 4** — Cancelamento pelo cliente, push no app mobile (Firebase), relatórios de vendas e estoque dos produtos.
**Extra** — CRUD de Restaurante, Produto e Local (endereço, pré-requisito da cadeia).
**Grupo:** Amigos do Gilberto · Turma A · Faculdade Impacta
**Produção:** API em `https://entregafood-api.onrender.com` (Render) com banco no Neon — ver [Publicar a API no Render](#publicar-a-api-no-render).

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
| 9 | Login por telefone com código OTP + cadastro por telefone; o código chega por e-mail (Brevo) | `/auth/telefone/*` | ✅ |
| 10 | Login social (Google/Facebook) | `/auth/google`, `/auth/facebook` | ✅ implementado (ver Limitações sobre uso em modo de teste) |
| 11 | Coleção Postman com todos os endpoints acima | [`postman/EntregaFood.postman_collection.json`](postman/EntregaFood.postman_collection.json) | ✅ |
| 12 | Cesta (incluir, consultar, alterar quantidade, excluir) com limite de 99 unidades, estoque e restaurante único | `/cesta`, `/cesta/itens` | ✅ |
| 13 | Resumo da cesta: subtotal, taxa de entrega pela distância e total | `GET /cesta/resumo` | ✅ |
| 14 | Fechamento do pedido: valida cesta vazia, disponibilidade, quantidade, endereço e raio; copia os itens para `item_pedido`; esvazia a cesta | `POST /pedidos` | ✅ |
| 15 | Tipo de pagamento (cartão, PIX ou dinheiro na entrega), cobrança no Asaas sandbox (cartão e PIX, com gateway simulado sem chave) e nota fiscal em PDF por e-mail | `/pagamentos` | ✅ |
| 16 | Tipo de entrega no fechamento (delivery com taxa pela distância ou retirada no balcão sem taxa) | `POST /pedidos`, `GET /cesta/resumo` | ✅ |
| 17 | Acompanhamento do pedido: linha do tempo de status, painel do restaurante/entregador e conclusão com código de entrega | `/pedidos`, `/pedidos/painel`, `/pedidos/{id}/status`, `/pedidos/{id}/entrega/confirmar` | ✅ |
| 18 | Notificações push no navegador (Web Push) a cada etapa do pedido e rastreio do entregador | `/notificacoes`, `/pedidos/{id}/rastreio` | ✅ |
| 19 | Portal do Parceiro: o dono gerencia o restaurante (horário, pausa, raio) e o cardápio | `/parceiro` | ✅ |
| 20 | Minha conta: dados, senha e endereços; o pedido guarda uma cópia do endereço | `/usuarios/{id}`, `/locais` | ✅ |
| 21 | Cancelamento pelo cliente enquanto aguarda o aceite, com estorno no Asaas (RN04) | `POST /pedidos/{id}/cancelar` | ✅ Sprint 4 |
| 22 | Push no app mobile pelo Firebase Cloud Messaging | `/notificacoes/fcm` | ✅ Sprint 4 (o app ainda não registra o token) |
| 23 | Relatórios de receita, pedidos e formas de pagamento por período | `/relatorios` | ✅ Sprint 4 |
| 24 | Estoque dos produtos: validação na cesta, baixa no pedido e devolução no cancelamento | `/produtos/{id}/estoque` | ✅ Sprint 4 |
| 25 | Emissão fiscal real (NFC-e) | — | ❌ não implementado (nota simulada em PDF) |
| 26 | Avaliação | — | ❌ não implementado (só tabela no `sql/`) |

Essa tabela é o inventário de referência: toda vez que uma funcionalidade nova entrar no backend, adicione uma linha aqui.

---

## Arquitetura MVC

O padrão MVC separa a aplicação em três responsabilidades, e a estrutura de pastas reflete isso diretamente:

```
app/
├── models/          MODEL      → SQLAlchemy + regras de negócio
│   ├── usuario.py              (tabela usuario: e-mail único, tipo de perfil, encerrar conta)
│   ├── codigo_otp.py           (códigos de validação do login/cadastro por telefone)
│   ├── local.py                (endereço: do cliente ou do restaurante)
│   ├── restaurante.py          (CNPJ único, dono, horário, pausa e raio de entrega)
│   ├── produto.py              (cardápio e estoque: baixa e devolução atômicas)
│   ├── sacola.py               (cesta e itens da cesta)
│   ├── pedido.py               (cria o pedido a partir da cesta, muda status, devolve estoque)
│   ├── item_pedido.py          (itens com o preço do momento)
│   ├── pedido_status_historico.py (linha do tempo do pedido)
│   ├── entrega.py              (código de entrega, entregador e posição)
│   ├── pagamento.py            (status do pagamento e id da cobrança no Asaas)
│   ├── push_inscricao.py       (navegadores inscritos no Web Push)
│   └── push_token_fcm.py       (celulares inscritos no Firebase)
├── schemas/         VIEW       → Pydantic: formato do JSON de entrada e saída
│   └── usuario, local, restaurante, produto, consulta, sacola, pedido,
│       entrega, pagamento, parceiro e relatorio
├── controllers/     CONTROLLER → routers FastAPI: recebem HTTP e orquestram
│   ├── auth_controller.py      (login, OTP por telefone, login social e rota protegida)
│   ├── usuario_controller.py, local_controller.py, restaurante_controller.py
│   ├── produto_controller.py   (CRUD do produto e estoque)
│   ├── consulta_controller.py  (visão do cliente: restaurantes aprovados e cardápio)
│   ├── sacola_controller.py    (cesta, resumo e validações do fechamento)
│   ├── pedido_controller.py    (criar, acompanhar, mudar status, confirmar e cancelar)
│   ├── entrega_controller.py   (rastreio e posição do entregador)
│   ├── pagamento_controller.py (cartão, PIX, dinheiro, nota fiscal e estorno)
│   ├── notificacao_controller.py (inscrição do navegador e token do app)
│   ├── parceiro_controller.py  (Portal do Parceiro)
│   └── relatorio_controller.py (relatórios de vendas)
└── core/            Infraestrutura e regras compartilhadas
    ├── config.py, database.py, security.py (.env, sessão do banco, senha e JWT)
    ├── status_pedido.py        (fluxo de status e quem pode mudar cada etapa)
    ├── frete.py, geocoding.py  (distância, taxa de entrega e coordenadas do endereço)
    ├── pagamento_regras.py, pagamento_gateway.py, pagamento_asaas.py, pagamento_cartao.py
    ├── nota_fiscal.py, email.py, otp_envio.py
    ├── push.py, push_fcm.py, notificacoes_pedido.py (quem recebe cada aviso)
    └── relatorios.py           (cálculos dos relatórios)
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

O `docker-compose.yml` monta a pasta `sql/` em `/docker-entrypoint-initdb.d`, então os scripts `01` a `12` rodam em ordem e as 15 tabelas são criadas automaticamente na primeira subida (com um volume já existente, rode os scripts novos à mão — ver [Scripts do banco](#scripts-do-banco)).

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

**Consulta, status e cancelamento do pedido (Sprint 4).** A coleção [`postman/Teste_Consulta_Status_Cancelamento.postman_collection.json`](postman/Teste_Consulta_Status_Cancelamento.postman_collection.json) roda contra uma API local com banco SQLite de teste, sem tocar no Neon. O script [`postman/servidor_local_teste.py`](postman/servidor_local_teste.py) sobe essa API, cria as contas de teste com senhas aleatórias e grava o ambiente do Postman em `%TEMP%\entregafood-teste`:

```bash
python postman/servidor_local_teste.py 8011
postman collection run postman/Teste_Consulta_Status_Cancelamento.postman_collection.json --environment %TEMP%/entregafood-teste/ambiente_local.postman_environment.json
```

Rode a coleção logo depois de subir o script (o banco é recriado a cada vez e as asserções contam os pedidos da própria execução).

| Coleção (`postman/`) | O que testa |
|---|---|
| `Teste_Incluir_Produto_Cesta`, `Teste_Consultar_Itens_Cesta`, `Teste_Alterar_Quantidade_Cesta`, `Teste_Excluir_Produto_Cesta` | Operações da cesta |
| `Teste_Subtotal_Total_Cesta`, `Teste_Validacoes_Cesta`, `Teste_Tipo_Entrega` | Resumo, validações e tipo de entrega no fechamento |
| `Teste_Acompanhamento_Entrega` | Linha do tempo, painel e código de entrega |
| `Teste_Pagamento` | Cartão aprovado/recusado, PIX, dinheiro, nota fiscal e estorno |
| `Teste_Consulta_Status_Cancelamento` | Consulta, mudança de status e cancelamento (Sprint 4) |
| `Teste_Notificacoes_Push` | Envio, permissões, token inválido e dados do clique (Sprint 4) — precisa do `--push`, abaixo |
| `Teste_Emissao_Fiscal` | NFC-e pela Focus NFe: autorização, rejeição, serviço fora do ar e reenvio, cancelamento (Sprint 4) — precisa do `--fiscal`, abaixo |

**Notificações push (Sprint 4).** Com `--push`, o servidor de teste liga o push com chaves VAPID e conta do Firebase de teste geradas na hora e sobe, na porta seguinte (8012), um serviço de push falso ([`postman/servico_push_falso.py`](postman/servico_push_falso.py)). Ele faz o papel do navegador e do Firebase: recebe e **decifra** cada notificação e guarda tudo em `GET /capturas`, que a coleção consulta. Só o transporte é trocado; cifragem, VAPID, JWT e as regras de quem recebe são o código real.

```bash
python postman/servidor_local_teste.py 8011 --push
postman collection run postman/Teste_Notificacoes_Push.postman_collection.json --environment %TEMP%/entregafood-teste/ambiente_local.postman_environment.json
```

No Docker, use `HOST=0.0.0.0` e publique as portas 8011 e 8012 para o Postman do Windows enxergar a API e o serviço falso.

**Emissão fiscal (Sprint 4).** Com `--fiscal`, o servidor de teste liga o provedor fiscal **real** (`FISCAL_PROVEDOR=focusnfe`, ambiente de homologação) e sobe, duas portas acima (8013), um serviço no formato da API v2 da Focus NFe ([`postman/servico_fiscal_falso.py`](postman/servico_fiscal_falso.py)). Ele confere o token e os campos da NFC-e e responde autorizando, rejeitando (704), fora do ar (503), com limite (429), sem responder ou recusando o cancelamento, conforme `POST /controle/modo`; `GET /capturas` mostra o que a API enviou. Só o servidor da Focus é trocado; montagem da nota, reenvio e cancelamento são o código real.

```bash
python postman/servidor_local_teste.py 8011 --fiscal
postman collection run postman/Teste_Emissao_Fiscal.postman_collection.json --environment %TEMP%/entregafood-teste/ambiente_local.postman_environment.json
```

---

## Publicar a API no Render

A API roda no Render (plano gratuito, Docker) e o banco no **Neon** (PostgreSQL). O arquivo [`render.yaml`](render.yaml) descreve o serviço `entregafood-api`, que publica sozinho a cada merge na `DEV`.

1. Render → **New → Blueprint** → escolha este repositório → **Apply**.
2. O Render pede os valores das variáveis secretas (`sync: false`). Preencha:
   - `DATABASE_URL`: a URL do Neon no formato `postgresql+psycopg://usuario:senha@host/neondb?sslmode=require` (a mesma do `.env`).
   - `VAPID_PRIVATE_KEY`: a chave privada das notificações (a mesma do `.env`).
   - `ASAAS_API_KEY`: chave do Asaas sandbox (vazia = pagamento simulado).
   - `SMTP_HOST`, `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_REMETENTE`: e-mail da nota (Brevo: `smtp-relay.brevo.com`, porta 2525). Vazio = a nota não é enviada.
   - `GOOGLE_*` e `FACEBOOK_*`: opcionais; sem eles só o login social fica desligado.
3. Espere o primeiro deploy ficar **Live** e abra `https://entregafood-api.onrender.com/` (`{"status":"ok"}`).
4. No front, troque `VITE_API_URL` no `render.yaml` do front para a URL nova.
5. Login social: cadastre `https://entregafood-api.onrender.com/auth/google/callback` no Google Cloud e `.../auth/facebook/callback` no Meta for Developers.

Mudança de banco (`sql/NN_*.sql`): rode o script no Neon (SQL Editor) **antes** do merge que precisa dele — os scripts são idempotentes e só acrescentam colunas/tabelas.

### Scripts do banco

| Script | O que faz | No Neon |
|---|---|---|
| `01_create_tables.sql` | Cria as 11 tabelas base | ✅ |
| `02_sprint2_telefone.sql`, `03_create_codigo_otp.sql` | Telefone no cadastro e códigos OTP | ✅ |
| `04_seed_cardapio.sql` | Dados de exemplo (restaurantes e cardápio) | opcional |
| `05` a `10` (Sprint 3) | Acompanhamento, dono/entregador, push no navegador, pagamento e NF, endereço no pedido, Portal do Parceiro | ✅ |
| `11_sprint4_push_fcm.sql` | Tabela `push_token_fcm` (push no app) | ✅ 08/11/2026 |
| `12_sprint4_estoque.sql` | Coluna `produto.estoque` (NULL = sem controle) | ✅ 08/11/2026 |
| `13_sprint4_nota_fiscal.sql` | Tabela `nota_fiscal` (situação da emissão de cada pedido) | ⏳ rodar antes do deploy |

Ao criar um script novo, acrescente uma linha aqui e marque quando ele for aplicado no Neon.

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

Todas as rotas de Local e Restaurante e as de escrita de Produto exigem o token do login (`401` sem ele). Cada usuário mexe só no que é dele (`403` no que é de outro); o admin acessa tudo.

| Método | Rota | Operação | Quem pode | Retorno |
|---|---|---|---|---|
| `POST` | `/locais` | CREATE (`usuario_id` opcional: sem ele, vale o usuário logado) | o próprio usuário · admin | `201` · `403` |
| `GET` | `/locais` | READ (os próprios; o admin vê todos e filtra por `?usuario_id=`) | logado | `200` · `403` |
| `GET` | `/locais/{id}` | READ (por id) | dono do endereço · admin | `200` · `403` · `404` |
| `PUT` | `/locais/{id}` | UPDATE | dono do endereço · admin | `200` · `403` · `404` |
| `DELETE` | `/locais/{id}` | DELETE | dono do endereço · admin | `204` · `403` · `404` |
| `POST` | `/restaurantes` | CREATE (o endereço precisa ser da conta) | restaurante · admin | `201` · `403` · `409` se CNPJ duplicado |
| `GET` | `/restaurantes` | READ (lista, com os pendentes) | admin | `200` · `403` |
| `GET` | `/restaurantes/{id}` | READ (por id) | dono · admin | `200` · `403` · `404` |
| `PUT` | `/restaurantes/{id}` | UPDATE (`status_aprovacao` só o admin) | dono · admin | `200` · `403` · `404` · `409` |
| `DELETE` | `/restaurantes/{id}` | DELETE | dono · admin | `204` · `403` · `404` |
| `POST` | `/produtos` | CREATE | dono do restaurante · admin | `201` · `403` · `422` se restaurante não existe |
| `GET` | `/produtos` | READ (lista, filtra por `?restaurante_id=`) | público | `200` |
| `GET` | `/produtos/{id}` | READ (por id) | público | `200` · `404` |
| `PUT` | `/produtos/{id}` | UPDATE | dono do restaurante · admin | `200` · `403` · `404` |
| `DELETE` | `/produtos/{id}` | DELETE | dono do restaurante · admin | `204` · `403` · `404` |

Testes: `python -m pytest testes/teste_seguranca_cadastros.py -v`.

### Exemplo: cadastrar a cadeia inteira

```bash
# TOKEN = access_token do POST /auth/login de uma conta do tipo restaurante
# 1. Local (fica na conta de quem está logado)
curl -X POST http://localhost:8000/locais -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"endereco":"Rua das Flores, 123","tipo":"restaurante","latitude":"-23.550520","longitude":"-46.633308"}'

# 2. Restaurante (local_id = id devolvido acima; nasce pendente até o admin aprovar)
curl -X POST http://localhost:8000/restaurantes -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"local_id":1,"nome_fantasia":"Cantinho do Chef","cnpj":"12.345.678/0001-90","taxa_entrega_km":"2.50"}'

# 3. Produto (restaurante_id = id devolvido acima)
curl -X POST http://localhost:8000/produtos -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"restaurante_id":1,"nome":"X-Salada","preco":"24.90"}'
```

---

## Endpoints da Sprint 2 — consulta de Restaurante e Cardápio

As rotas de `/restaurantes` e `/produtos` acima são de **cadastro e administração**. A Sprint 2 adiciona a visão do **cliente** que navega no app — só o que ele pode pedir. São endpoints de leitura, agrupados sob `/consultas`.

| Método | Rota | O que devolve | Retorno |
|---|---|---|---|
| `GET` | `/consultas/restaurantes` | Só restaurantes `status_aprovacao = 'aprovado'`, com o endereço embutido. Filtra por nome com `?busca=`. Com `?latitude=&longitude=` do endereço do cliente, só vêm os que entregam ali (raio de entrega de cada restaurante; distância estimada em linha reta × `FRETE_FATOR_CIRCUITO`), do mais perto ao mais longe, com `distancia_km` e `entrega_no_endereco`; `incluir_fora_do_raio=true` lista também os que não entregam | `200` |
| `GET` | `/consultas/restaurantes/{id}` | Um restaurante aprovado + endereço (sem CNPJ) | `200` · `404` se pendente/recusado/inexistente |
| `GET` | `/consultas/restaurantes/{id}/cardapio` | Dados do restaurante + lista dos itens com `disponivel = true` e não esgotados (com o `estoque` restante; `null` = sem controle) + `total_itens` | `200` · `404` |

Diferenças em relação ao CRUD: a consulta **não** expõe CNPJ, **não** mostra restaurante não-aprovado e **não** lista item indisponível.

### Exemplo

```bash
curl "http://localhost:8000/consultas/restaurantes?busca=burger"
curl "http://localhost:8000/consultas/restaurantes?latitude=-23.550520&longitude=-46.633308"
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
| `POST` | `/cesta/itens` | Inclui produto (soma se já existir). Bloqueia indisponível, restaurante diferente, mais de 99 unidades e mais que o estoque | `201` · `400` · `404` |
| `PUT` | `/cesta/itens/{produto_id}` | Altera a quantidade (mesmas validações) | `200` · `400` · `404` |
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

### Push no app mobile — Firebase Cloud Messaging (Sprint 4)

O app Android recebe os mesmos avisos do site pelo Firebase (FCM). Antes de usar, rode `sql/11_sprint4_push_fcm.sql` no banco e coloque no Render a variável `FIREBASE_CREDENCIAIS` com o JSON da conta de serviço do projeto Firebase (Configurações do projeto → Contas de serviço → Gerar nova chave privada; o JSON inteiro numa linha ou em base64). Sem ela tudo funciona, só não envia para o app.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `POST` | `/notificacoes/fcm` | logado | Registra o token do celular (`{"token": "...", "plataforma": "android"}`). Token novo → 201; já conhecido → 200 (atualiza a conta e a plataforma) |
| `DELETE` | `/notificacoes/fcm` | logado | Remove o token (logout no app) |

- Tabela `push_token_fcm`: um token por celular (único), ligado ao usuário; as inscrições do navegador continuam em `push_inscricao`.
- `app/core/push_fcm.py` autentica com a conta de serviço (JWT RS256 → token OAuth2, reaproveitado até expirar) e envia pela API HTTP v1 (`/v1/projects/<projeto>/messages:send`).
- Cada aviso do pedido (`app/core/notificacoes_pedido.py`) vai pelos dois canais. No app a mensagem leva `pedido_id`, `status` e `destino` em `data`, para o toque abrir o pedido certo.
- Token que o Firebase diz que não vale mais (`UNREGISTERED`) é apagado sozinho. Falha do Firebase nunca afeta o pedido.

Testes: `python -m pytest testes/teste_push_fcm.py` (Google simulado, sem Firebase real) e a coleção `Teste_Notificacoes_Push` (ver [Testar com Postman](#6-testar-com-postman)).

**Clique na notificação:** no navegador, o `public/sw.js` do front abre a `url` da mensagem (`/` para o cliente, `/?painel=1` para restaurante e entregador) ou foca a aba do site se ela já estiver aberta. O teste da Sprint 4 apontou melhorias ainda não feitas: o cliente cai na tela inicial e não no acompanhamento do pedido, o front não lê o `?painel=1` e, com a aba aberta, ela só ganha foco sem navegar.

---

## Endpoints da Sprint 3 — pagamento e nota fiscal

Antes de usar, rode `sql/08_sprint3_pagamento_nf.sql` no banco e configure no `.env` (e no Render) as variáveis `ASAAS_*` e `SMTP_*` (ver [Variáveis de ambiente do pagamento](#variáveis-de-ambiente-do-pagamento)). Sem elas tudo funciona: o pagamento usa o gateway **simulado** e a nota é gerada sem ser enviada por e-mail.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `PUT` | `/pagamentos/pedidos/{id}/metodo` | cliente dono | Escolhe `cartao`, `pix` ou `dinheiro` (outro valor → 422). Dinheiro já fica `a_receber` |
| `POST` | `/pagamentos/cartao` | cliente dono | Cobra no cartão de crédito. Recusado → `status: "recusado"` com o motivo em `mensagem` e pode tentar de novo |
| `POST` | `/pagamentos/pix` | cliente dono | Gera o PIX: `pix_qrcode` (imagem base64), `pix_copia_cola` e `pix_expira_em` |
| `GET` | `/pagamentos/pedidos/{id}` | cliente dono, restaurante dono, admin | Consulta o pagamento; se pendente, atualiza o status no Asaas (é o "já paguei" do PIX) |
| `POST` | `/pagamentos/pedidos/{id}/pix/simular-pagamento` | cliente dono | Marca o PIX como pago (só no gateway simulado ou no Asaas **sandbox**) |
| `GET` | `/pagamentos/pedidos/{id}/nota-fiscal` | cliente dono, restaurante dono, admin | Baixa o PDF da nota fiscal (404 enquanto o pagamento não for aprovado) |

**Regras** (`app/core/pagamento_regras.py`):

- O mesmo tipo `MetodoPagamento = Literal["cartao", "pix", "dinheiro"]` vale em `POST /pedidos` (`forma_pagamento`) e em `PUT /pagamentos/pedidos/{id}/metodo`.
- Status do pagamento: `pendente` (PIX aguardando), `aprovado`, `recusado`, `a_receber` (dinheiro), `expirado`, `cancelado` (método trocado) e `estornado`.
- **Aceite do restaurante**: só com pagamento `aprovado` (cartão e PIX) ou `a_receber` (dinheiro na entrega — regra definida com o grupo).
- **Dinheiro**: não passa pelo gateway. Quando o entregador (ou o balcão) confirma a entrega com o código, o pagamento vira `aprovado` e a nota é emitida.
- Trocar o método só antes do aceite; a cobrança anterior ainda não paga (ex.: PIX pendente) é cancelada no Asaas.
- O número do cartão vai direto para o Asaas e **não é gravado** no banco nem no log.

**Asaas** (`app/core/pagamento_asaas.py`, cliente HTTP com `httpx`): busca/cria o cliente pelo CPF (`/customers`), cria a cobrança (`/payments`, `CREDIT_CARD` ou `PIX`), busca o QR Code (`/payments/{id}/pixQrCode`) e consulta o status (`/payments/{id}`). O id da cobrança fica em `pagamento.transacao_externa_id`. Com o Asaas ativo o cliente precisa informar CPF (e, no cartão, CEP, número do endereço e telefone; o e-mail vem do cadastro). `app/core/pagamento_gateway.py` escolhe Asaas ou simulado pela `ASAAS_API_KEY`.

Cartões de teste: `5162306219378829` (aprovado, qualquer validade futura e CVV) e `5184019740373151` (recusado). O gateway simulado também recusa o cartão `5184019740373151`, então o Postman testa os dois casos com ou sem o Asaas.

**Nota fiscal** (`app/core/nota_fiscal.py`): simulada (sem valor fiscal, não passa pela SEFAZ). Quando o pagamento é aprovado, o número (`NF-<ano>-<pedido>`) é gravado em `pedido.cupom_fiscal` e, em segundo plano (`BackgroundTasks`), o PDF é gerado com restaurante, cliente, itens com o preço do momento, taxa, total e forma de pagamento, e enviado por e-mail (`app/core/email.py`). Sem SMTP só registra no log; erro no e-mail nunca afeta o pagamento. O PDF é refeito a cada download a partir do banco.

Testes: `python -m pytest testes/teste_pagamento.py testes/teste_pagamento_api.py` (sem banco: o segundo usa SQLite em memória e o gateway simulado) e a coleção [`postman/Teste_Pagamento.postman_collection.json`](postman/Teste_Pagamento.postman_collection.json) (cartão aprovado e recusado, PIX, dinheiro, método inválido, outro cliente, nota fiscal e sem login).

### Cancelamento do pedido pelo cliente (Sprint 4 — RN04)

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `POST` | `/pedidos/{id}/cancelar` | cliente dono | Cancela o pedido **enquanto ele aguarda o aceite** do restaurante |

- Depois do aceite o cliente recebe 400 e só o restaurante cancela (`PATCH /pedidos/{id}/status` com `cancelado`, como antes).
- Pagamento do pedido cancelado (pelo cliente ou pelo restaurante): `aprovado` → **estorno no Asaas** (`estornado`); `pendente` (PIX não pago) → cobrança removida (`cancelado`); `a_receber` (dinheiro) → `cancelado`.
- Logo depois da aprovação o Asaas às vezes pede para tentar o estorno mais tarde: o pedido é cancelado na hora, o pagamento fica `estorno_pendente` e o estorno é refeito em segundo plano e a cada `GET /pagamentos/pedidos/{id}`.
- O cliente e o restaurante recebem push avisando do cancelamento.

Testes: `python -m pytest testes/teste_cancelamento_cliente.py testes/teste_pagamento_api.py` e a pasta CT-09 da coleção `Teste_Pagamento`.

### Variáveis de ambiente do pagamento

| Variável | Exemplo | Para que serve |
|---|---|---|
| `ASAAS_API_KEY` | `$aact_...` (sandbox) | Chave do Asaas (sandbox.asaas.com → Integrações → Chave de API). Vazia = gateway simulado |
| `ASAAS_BASE_URL` | `https://api-sandbox.asaas.com/v3` | API do Asaas (sandbox) |
| `SMTP_HOST` | `smtp.gmail.com` | Servidor de e-mail. Vazio = não envia a nota |
| `SMTP_PORTA` | `2525` | 2525 ou 587 (STARTTLS) ou 465 (SSL). No Render (Brevo) use 2525 |
| `SMTP_USUARIO` | `entregafood.grupo@gmail.com` | Login do SMTP |
| `SMTP_SENHA` | senha de app do Gmail | Senha do SMTP (no Gmail, "senha de app") |
| `SMTP_REMETENTE` | `EntregaFood <entregafood.grupo@gmail.com>` | Remetente do e-mail |

Nenhuma dessas chaves vai para o Git: só no `.env` local e nas variáveis de ambiente do Render.

---

## Endpoints da Sprint 3 — Portal do Parceiro (gestão do restaurante)

Antes de usar, rode `sql/10_sprint3_gestao_restaurante.sql` no banco (pode ser antes do deploy: só acrescenta colunas com padrão). Todas as rotas exigem login de **restaurante** (outro tipo → `403`) e só enxergam o restaurante do próprio dono.

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/parceiro/restaurante` | Meu restaurante, com endereço, raio, horário e se está aberto agora (`404` se ainda não cadastrou) |
| `POST` | `/parceiro/restaurante` | Cadastra o restaurante do dono (nasce **pendente**; o admin aprova em `PUT /restaurantes/{id}`). Um por dono; CNPJ único (`409`) |
| `PUT` | `/parceiro/restaurante` | Altera dados, endereço, `raio_entrega_km`, `horario_abertura`/`horario_fechamento` e `ativo` (pausar). `null` limpa raio e horário |
| `GET` | `/parceiro/resumo` | Números reais do dia: pedidos, faturamento, ticket médio, pendentes, em andamento, itens ativos |
| `GET` / `POST` | `/parceiro/produtos` | Cardápio do dono: listar e incluir item |
| `PUT` / `DELETE` | `/parceiro/produtos/{id}` | Alterar (preço, descrição, disponível) e excluir. Item que já aparece em pedidos não é excluído (`409`): desative |

Regras novas no fechamento da cesta: restaurante **pausado** ou **fora do horário** não recebe pedidos; o raio de entrega é o do restaurante (sem ele, `FRETE_RAIO_MAX_KM`). **Só conta de cliente compra**: cesta e `POST /pedidos` com restaurante ou entregador → `403`. Produto de restaurante não aprovado, pausado ou fechado já é recusado na inclusão na cesta (`400`). Testes: `python -m pytest testes/teste_gestao_restaurante.py -v`.

---

## Endpoints da Sprint 3 — minha conta e endereços

Antes de usar, rode `sql/09_sprint3_conta_enderecos.sql` no banco (junto com o deploy da API).

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `PUT` | `/usuarios/{id}` | o próprio usuário ou admin | Altera nome, e-mail e telefone (e-mail/telefone de outra conta → `409`) |
| `POST` | `/auth/telefone/cadastro/confirmar` | visitante | Agora também grava o `email` informado no cadastro (e-mail de outra conta → `409`), para entrar por e-mail e receber a nota fiscal |
| `PUT` | `/usuarios/{id}/senha` | o próprio usuário | Troca a senha: confere `senha_atual` (errada → `400`); conta do Google/Facebook sem senha define a primeira |
| `GET` | `/locais?usuario_id={id}` | — | Endereços do cliente ("Meus endereços") |
| `POST` / `PUT` / `DELETE` | `/locais` | — | Cadastrar, alterar e excluir endereço |
| `GET` | `/cesta/resumo?local_id={id}` | cliente | Taxa e total para o endereço escolhido na cesta |
| `POST` | `/pedidos` (`local_id`) | cliente | Fecha o pedido para o endereço escolhido |

O pedido de entrega **grava uma cópia do endereço** (`pedido.endereco_entrega`, `latitude_entrega`, `longitude_entrega`). Assim, se o cliente alterar ou excluir o endereço depois, o destino do pedido no rastreio e no painel do entregador continua o mesmo. Sem `local_id`, vale o último endereço cadastrado. Testes: `python -m pytest testes/teste_conta_enderecos.py -v`.

---

## Endpoints da Sprint 4 — relatórios de vendas

Três relatórios para o painel do administrador e do parceiro. Todos aceitam `data_inicio` e `data_fim` (AAAA-MM-DD, o último dia entra inteiro); sem datas, o período é todo o histórico.

| Método | Rota | O que responde |
|---|---|---|
| `GET` | `/relatorios/receita-por-restaurante` | Receita bruta de cada restaurante e participação % no total (maior primeiro), mais o total geral |
| `GET` | `/relatorios/pedidos-por-restaurante` | Quantidade de pedidos, faturamento e ticket médio por restaurante, mais os totais. Ordenação: `ordenar_por` = `quantidade_pedidos`, `faturamento` (padrão), `ticket_medio` ou `restaurante_nome`; `ordem` = `desc` (padrão) ou `asc` |
| `GET` | `/relatorios/pagamentos-por-tipo` | Cartão, PIX e dinheiro em quantidade e em valor, com o percentual de cada um (para o gráfico de pizza). Os três métodos sempre aparecem |

**Regras** (`app/core/relatorios.py`, iguais nos três):

- Entra no relatório o pedido **aceito pelo restaurante** (de `aceito` até `entregue`). Pedidos aguardando aceite e cancelados ficam de fora.
- Receita bruta = faturamento = soma do valor total dos pedidos (produtos + taxa de entrega).
- Ticket médio = faturamento ÷ quantidade de pedidos. Valores e percentuais com 2 casas.
- Quem vê: **admin** vê todos os restaurantes; **restaurante** vê só os seus; cliente e entregador recebem 403.
- Data inicial depois da final → 400. Período sem pedidos → listas vazias e totais zerados.
- Cada resposta traz o `periodo` aplicado e a `regra` em texto, para quem lê saber o que foi somado.

Exemplo — `GET /relatorios/receita-por-restaurante?data_inicio=2026-11-01&data_fim=2026-11-30`:

```json
{
  "periodo": {"data_inicio": "2026-11-01", "data_fim": "2026-11-30"},
  "regra": "Considera os pedidos aceitos pelo restaurante (de 'aceito' até 'entregue'). ...",
  "total_geral": "200.00",
  "restaurantes": [
    {"restaurante_id": 2, "restaurante_nome": "Sushi", "receita_bruta": "120.00", "participacao_percentual": "60.00"},
    {"restaurante_id": 1, "restaurante_nome": "Pizzaria", "receita_bruta": "80.00", "participacao_percentual": "40.00"}
  ]
}
```

MVC: a leitura do banco fica no Model (`Pedido.listar_vendas`), os cálculos em `app/core/relatorios.py`, o formato da resposta nos schemas (`app/schemas/relatorio.py`) e as rotas em `app/controllers/relatorio_controller.py`. Testes: `python -m pytest testes/teste_relatorios.py`.

---

## Endpoints da Sprint 4 — estoque dos produtos

Antes do deploy, rode `sql/12_sprint4_estoque.sql` no banco: o model já lê a coluna `produto.estoque` e, sem ela, as rotas de produto dão 500.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `GET` | `/produtos/{id}/estoque` | público | `estoque`, `controla_estoque` e `esgotado` |
| `PUT` | `/produtos/{id}/estoque` | dono do restaurante · admin | Define a contagem (`{"estoque": 30}`); `{"estoque": null}` desliga o controle |
| `PATCH` | `/produtos/{id}/estoque` | dono do restaurante · admin | Entrada (`{"ajuste": 10}`) ou saída (`{"ajuste": -2}`); não deixa ficar negativo (`400`) |

O campo `estoque` também é aceito em `POST`/`PUT /produtos` e `/parceiro/produtos` (omitir não mexe; `null` desliga).

**Regras** (`app/models/produto.py` e `app/models/pedido.py`):

- `estoque = NULL`: o restaurante não controla estoque daquele produto e ele vende sem limite, como antes. Os produtos que já existiam ficaram assim.
- Cesta (incluir e alterar) e fechamento (`GET /cesta/resumo`, `POST /pedidos`) recusam quantidade maior que o estoque (`"So ha 3 unidades de 'Lanche' em estoque."`).
- Criar o pedido **baixa o estoque na mesma transação**, com um `UPDATE` condicional: se outro pedido levou as últimas unidades depois do resumo, a API responde `409` e nada é gravado.
- Pedido **cancelado** (pelo cliente ou pelo restaurante) devolve as unidades. Como só dá para cancelar antes do preparo, nada foi produzido; um pedido nunca devolve duas vezes.
- Estoque `0` = esgotado: o produto some do cardápio do cliente.

Testes: `python -m pytest testes/teste_estoque.py -v` (15 testes).

---

## Endpoints da Sprint 4 — emissão fiscal (NFC-e)

Antes do deploy, rode `sql/13_sprint4_nota_fiscal.sql` no banco: a emissão da nota (pagamento aprovado) grava na tabela `nota_fiscal`.

A nota fica no pacote [`app/core/fiscal/`](app/core/fiscal): `dados.py` (o que vai na nota), `pdf_simulado.py` (PDF sem valor fiscal), `provedores.py` (provedor simulado e integração real com a **Focus NFe**, escolhida na pesquisa PSQ-FIS-01) e `emissao.py` (emissão, rejeição, serviço fora do ar e reenvio). O resto do sistema chama `app/core/nota_fiscal.py`.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `GET` | `/notas-fiscais/pedidos/{id}` | cliente dono, restaurante dono, admin | Situação da nota; se ela esperava o serviço voltar e a hora chegou, tenta de novo antes de responder |
| `POST` | `/notas-fiscais/pedidos/{id}/emitir` | restaurante dono, admin | Nova emissão depois de rejeição ou falha (`409` se já autorizada, `400` sem pagamento aprovado) |
| `POST` | `/notas-fiscais/reprocessar` | admin | Tenta de novo as pendentes cuja hora chegou (para um Cron Job em produção) |
| `GET` | `/pagamentos/pedidos/{id}/nota-fiscal` | cliente dono, restaurante dono, admin | DANFCe do serviço (`307`) ou PDF simulado; `409` se a nota não está autorizada |

Situações: `autorizada` (número também em `pedido.cupom_fiscal`) · `rejeitada` (código e motivo da SEFAZ; não tenta sozinha) · `pendente_reenvio` (serviço fora do ar, 429 ou tempo esgotado; esperas de 1, 5, 15, 60 e 240 min) · `falhou` (depois de 6 tentativas) · `cancelada` (pedido cancelado; a NFC-e só pode ser cancelada até 30 min após a emissão — se a SEFAZ recusar, o pedido é cancelado mesmo assim e o motivo fica na nota). A referência enviada é sempre `pedido-{id}`, então repetir a emissão nunca gera duas notas. A falha da nota nunca bloqueia o pagamento nem o pedido.

A NFC-e sai no CNPJ do restaurante, com presença 4 (delivery) ou 1 (retirada), a taxa de entrega rateada no frete dos itens (Resposta à Consulta SEFAZ-SP 31987/2025) e o EntregaFood como intermediador quando `FISCAL_CNPJ_INTERMEDIADOR` está preenchido.

| Variável | Padrão | Uso |
|---|---|---|
| `FISCAL_PROVEDOR` | `simulado` | `simulado` (PDF, como antes) ou `focusnfe` |
| `FOCUSNFE_TOKEN` / `FOCUSNFE_AMBIENTE` | (vazio) / `homologacao` | Token da empresa na Focus NFe e ambiente (`homologacao` ou `producao`); sem token, volta para o simulado |
| `FISCAL_NCM_PADRAO` / `FISCAL_CFOP` / `FISCAL_SITUACAO_ICMS` | `21069090` / `5102` / `102` | Códigos fiscais dos itens — confirmar com o contador do restaurante |
| `FISCAL_CNPJ_INTERMEDIADOR` | (vazio) | CNPJ do EntregaFood como intermediador (NT 2020.006) |

Testes: `python -m pytest testes/teste_emissao_fiscal.py -v` (27 testes) e a coleção `Teste_Emissao_Fiscal` (ver [Testar com Postman](#6-testar-com-postman)).

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

As baterias das Sprints 3 e 4 (cesta, fechamento, status, pagamento, cancelamento, push, Portal do Parceiro, conta, relatórios e estoque) usam **SQLite em memória** e não precisam de banco. Para rodar todas de uma vez (precisa do `pytest`):

```bash
python -m pytest testes/teste_*.py -q
```

Sem Python 3.12 instalado, dá para rodar no container do back: `docker run --rm -v "%cd%:/app" -w /app entregafood-backend sh -c "pip install -q -r requirements.txt pytest && python -m pytest testes/teste_*.py -q"`. (`python -m pytest testes` sozinho não acha nada: os arquivos começam com `teste_`, não `test_`.)

---

## Segurança

- Senhas armazenadas com **bcrypt**, nunca em texto puro (RNF03). `requirements.txt` trava `bcrypt<4.1` de propósito — versões mais novas quebram o `passlib` 1.7.4 (projeto sem atualização desde 2020), que não reconhece o novo esquema de versionamento do bcrypt e derruba qualquer cadastro com 500.
- `senha_hash` **não aparece em nenhuma resposta da API** — o schema `UsuarioOut` simplesmente não tem esse campo.
- Autenticação por **JWT Bearer**, com expiração configurável.
- O login devolve mensagem genérica ("E-mail ou senha incorretos") de propósito, para não revelar quais e-mails existem na base.
- CORS restrito às origens listadas no `.env`.
- Endereços, restaurantes e cardápios só são lidos e alterados pelo dono ou pelo admin; aprovar restaurante é só do admin.

---

## Limitações conhecidas

- **Login social (Google/Facebook)**: implementado (`/auth/google`, `/auth/facebook` + callback). Enquanto os apps OAuth ficam em modo de teste nos dois provedores, só e-mails cadastrados manualmente como "tester" conseguem logar — inviável pra qualquer colega ou o professor testar sem antes pedir acesso. Publicar os apps de verdade exigiria mais burocracia (política de privacidade, revisão) do que vale a pena pra esse projeto. Pra demonstração, o caminho garantido continua sendo e-mail/senha.
- **Código de validação (OTP)**: no login e no cadastro por telefone (`/auth/telefone/*`) o código de 6 dígitos é enviado **por e-mail** pelo mesmo SMTP da nota fiscal (`app/core/otp_envio.py`): no login vai para o e-mail da conta; no cadastro, para o e-mail informado na tela. A resposta mostra o e-mail mascarado e não traz mais o código. Sem `SMTP_HOST` (rodando local, testes) o código volta em `codigo_dev`, como antes; `OTP_MOSTRAR_CODIGO=true` devolve o código mesmo com o e-mail enviado (só para demonstração). Conta antiga sem e-mail entra com telefone e senha. SMS de verdade não foi feito: o Twilio trial e o SMS do Brevo exigem pagamento. Testes: `testes/teste_otp_email.py`.
- **Pagamento**: cartão e PIX vão para o Asaas **sandbox** (sem dinheiro de verdade). Não há webhook (o status do PIX é atualizado na consulta). O cancelamento de pedido pago pede o estorno ao gateway (`estorno_pendente` se ele falhar). Débito, parcelamento e Mercado Pago ficaram de fora.
- **Nota fiscal**: o padrão continua sendo a nota simulada em PDF. A integração real com a Focus NFe (NFC-e) está pronta e testada contra um serviço no formato da homologação da Focus; a homologação oficial exige um restaurante com CNPJ, inscrição estadual credenciada, certificado A1 e CSC. O CPF do cliente ainda não vai na nota (o pedido não guarda CPF).
- **Estoque**: opcional por produto (`NULL` = sem controle). Não há tela no front ainda: o dono ajusta pelo Swagger/Postman ou pelo campo `estoque` do Portal do Parceiro na API.
- **Push no app mobile**: a API está pronta e testada, mas o app ainda não chama `POST /notificacoes/fcm`.
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
main                    ← protegida, entra só via Pull Request (vindo da DEV)
DEV                     ← integração; o Render publica a API a cada merge aqui
feat/<assunto>          ← funcionalidade nova     (ex.: feat/estoque)
fix/<assunto>           ← correção                (ex.: fix/defeitos-professor)
test/<assunto>          ← testes e coleções       (ex.: test/notificacoes-push)
docs/<assunto>          ← documentação            (ex.: docs/readme-sprint4)
```

Cada branch sai da `DEV` atualizada e volta por Pull Request com 1 aprovação. Se o PR precisar de script novo no banco, rode-o no Neon antes do merge (ver [Scripts do banco](#scripts-do-banco)).

Na Sprint 1 as branches eram por pessoa (`sprint1/crud-usuario`, `sprint1/autenticacao`, `sprint1/infra-banco`, `sprint1/testes-api`).
