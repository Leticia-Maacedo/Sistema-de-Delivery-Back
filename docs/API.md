# Referência da API — EntregaFood

Base URL local: `http://localhost:8000`. Documentação interativa sempre
disponível em `/docs` (Swagger) e `/redoc` com o servidor rodando — este
documento é o complemento "para ler fora do navegador", com os métodos de
Model por trás de cada rota (o Swagger não mostra isso).

Convenção usada abaixo: **Auth** = `—` (pública), `JWT` (precisa de
`Authorization: Bearer <token>` válido) ou `JWT admin` (precisa de token
válido **e** `tipo == "admin"`).

---

## Status (`app/main.py`)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `GET` | `/` | — | Health check. Devolve `{"status":"ok","aplicacao":"EntregaFood API","versao":"1.0.0"}`. |

---

## Autenticação — `/auth` (`auth_controller.py`)

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `POST` | `/auth/login` | — | Login por e-mail **ou** telefone + senha. | `200`, `401` |
| `POST` | `/auth/telefone/solicitar-codigo` | — | Gera OTP de 6 dígitos para login por telefone (válido 5 min). | `200`, `400`, `404` |
| `POST` | `/auth/telefone/verificar-codigo` | — | Valida o OTP e devolve o JWT (uso único — o código é apagado após validar). | `200`, `400`, `401`, `429` |
| `POST` | `/auth/telefone/cadastro/solicitar-codigo` | — | Gera OTP para criar conta nova só com telefone. | `200`, `400`, `403`, `409`, `422` |
| `POST` | `/auth/telefone/cadastro/confirmar` | — | Valida o OTP e cria a conta. | `200`, `400`, `401`, `403`, `409`, `422`, `429` |
| `GET` | `/auth/eu` | JWT | Dados do usuário do token atual. Rota usada só para provar que o middleware funciona. | `200`, `401` |
| `GET` | `/auth/google` | — | Inicia o fluxo OAuth do Google (redirect). | `302` |
| `GET` | `/auth/google/callback` | — | Callback do Google; cria a conta no primeiro login e redireciona pro front com o JWT na URL. | `302`, `400` |
| `GET` | `/auth/facebook` | — | Inicia o fluxo OAuth do Facebook (redirect). | `302` |
| `GET` | `/auth/facebook/callback` | — | Callback do Facebook; mesmo comportamento do Google. | `302`, `400` |

**Corpo de `POST /auth/login`** (`LoginRequest`): exatamente um entre `email`
e `telefone`, mais `senha`. Enviar os dois ou nenhum dos dois devolve `422`
(validado no schema, antes de chegar no controller).

**Métodos de Model por trás:**
- `Usuario.buscar_por_email` / `Usuario.buscar_por_telefone` — localizam a conta.
- `verificar_senha` (`core/security.py`) — compara a senha enviada com o hash bcrypt.
- `criar_token_acesso` (`core/security.py`) — gera o JWT.
- `Usuario.telefone_ja_cadastrado`, `Usuario.tipo_e_valido`, `Usuario.criar` — usados no fluxo de cadastro por telefone.

**Fluxo de OTP** (login ou cadastro por telefone) usa a tabela `codigo_otp`
diretamente no controller (não tem Model próprio com métodos de negócio —
é `db.get`/`db.add`/`db.delete` direto no `CodigoOTP`, ver
`docs/BANCO_DE_DADOS.md`). Regras: código de 6 dígitos, expira em 5 minutos,
no máximo 5 tentativas erradas antes de invalidar, comparação com
`secrets.compare_digest` (evita timing attack).

---

## Usuários — `/usuarios` (`usuario_controller.py`)

CRUD completo. `tipo` aceita `cliente | restaurante | entregador | admin`;
autocadastro como `admin` é bloqueado (`403`) — conta admin é provisionada
manualmente no banco.

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `POST` | `/usuarios` | — | Cadastro (RF01). | `201`, `403`, `409`, `422` |
| `GET` | `/usuarios` | JWT admin | Lista todos, com filtro opcional `?tipo=` e paginação `?limite=&pular=`. | `200`, `401`, `403` |
| `GET` | `/usuarios/{id}` | JWT (dono ou admin) | Consulta uma conta. | `200`, `401`, `403`, `404` |
| `PUT` | `/usuarios/{id}` | JWT (dono ou admin) | Altera dados. Só admin pode alterar `tipo`. | `200`, `401`, `403`, `404`, `409` |
| `DELETE` | `/usuarios/{id}` | JWT (dono ou admin) | Encerra a conta (RF06). | `204`, `401`, `403`, `404` |

A checagem "dono ou admin" é a função `_exigir_dono_ou_admin` no topo do
controller — roda **antes** de checar se o `id` existe, de propósito, para
não revelar a um usuário não autorizado se aquele `id` existe ou não.

**Métodos de Model usados (`app/models/usuario.py`):**

| Método | Assinatura | Para quê |
|---|---|---|
| `tipo_e_valido(tipo)` | `staticmethod(str) -> bool` | Valida contra `TIPOS_VALIDOS` |
| `email_ja_cadastrado(db, email, ignorar_id=None)` | `staticmethod` | Unicidade de e-mail (CT04); `ignorar_id` evita falso-positivo no próprio UPDATE |
| `telefone_ja_cadastrado(db, telefone, ignorar_id=None)` | `staticmethod` | Unicidade de telefone |
| `buscar_por_email(db, email)` | `staticmethod -> Usuario \| None` | Usado no login |
| `buscar_por_telefone(db, telefone)` | `staticmethod -> Usuario \| None` | Usado no login por telefone |
| `buscar_por_id(db, id)` | `staticmethod -> Usuario \| None` | Usado em quase todo controller que recebe um `usuario_id` |
| `listar(db, tipo=None, limite=100, pular=0)` | `staticmethod -> list[Usuario]` | Paginação simples via `OFFSET`/`LIMIT` |
| `criar(db, *, nome, email, senha_hash, telefone, tipo, oauth_provider=None)` | `classmethod -> Usuario` | Normaliza e-mail (lowercase/strip) e telefone (só dígitos) antes de gravar |
| `atualizar(self, db, **campos)` | `instance -> Usuario` | Aceita campos parciais (`exclude_unset`); ignora valores `None` |
| `remover(self, db)` | `instance -> None` | `DELETE` físico (RF06) |

---

## Locais — `/locais` (`local_controller.py`)

CRUD completo, **sem autenticação** — qualquer chamada com um `usuario_id`
válido cria/altera/remove um local. Pré-requisito para cadastrar um
`restaurante` (todo restaurante precisa de um `local_id`).

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `POST` | `/locais` | — | Cadastra um endereço vinculado a `usuario_id`. | `201`, `422` |
| `GET` | `/locais` | — | Lista, com filtro opcional `?usuario_id=`. | `200` |
| `GET` | `/locais/{id}` | — | Consulta por id. | `200`, `404` |
| `PUT` | `/locais/{id}` | — | Altera campos parciais. | `200`, `404` |
| `DELETE` | `/locais/{id}` | — | Remove. | `204`, `404` |

**Métodos de Model (`app/models/local.py`):** `buscar_por_id`, `listar(db, usuario_id=None)`,
`criar(db, usuario_id, endereco, tipo, latitude, longitude)`,
`atualizar(self, db, endereco=None, tipo=None, latitude=None, longitude=None)`
(cada campo é opcional individualmente, não usa `**campos` genérico como os
outros models), `excluir(self, db)`.

---

## Restaurantes — `/restaurantes` (`restaurante_controller.py`)

CRUD de **administração** — devolve todos os restaurantes, independente de
`status_aprovacao`. Sem autenticação (ver débito técnico em
`docs/ARQUITETURA.md`, §9). Para a visão filtrada do cliente, ver `/consultas`
abaixo.

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `POST` | `/restaurantes` | — | Cadastra (`status_aprovacao` nasce `'pendente'`). | `201`, `409` |
| `GET` | `/restaurantes` | — | Lista com paginação `?limite=&pular=`. | `200` |
| `GET` | `/restaurantes/{id}` | — | Consulta por id. | `200`, `404` |
| `PUT` | `/restaurantes/{id}` | — | Altera, inclusive `status_aprovacao` (é assim que um restaurante vira `'aprovado'`). | `200`, `404`, `409` |
| `DELETE` | `/restaurantes/{id}` | — | Remove. | `204`, `404` |

**Métodos de Model (`app/models/restaurante.py`):**

| Método | Para quê |
|---|---|
| `cnpj_ja_cadastrado(db, cnpj, ignorar_id=None)` | Unicidade de CNPJ |
| `buscar_por_id(db, id)` | Consulta simples (qualquer status) |
| `listar(db, limite=100, pular=0)` | Listagem de administração, sem filtro |
| `listar_aprovados(db, busca=None, limite=100, pular=0)` | **Usado só por `/consultas`** — filtra `status_aprovacao = 'aprovado'` e, opcionalmente, nome (`ILIKE`) |
| `buscar_aprovado_por_id(db, id)` | **Usado só por `/consultas`** — igual `buscar_por_id`, mas só devolve se aprovado |
| `criar(db, *, local_id, nome_fantasia, cnpj, taxa_entrega_km, status_aprovacao="pendente")` | Grava, normalizando nome/CNPJ (strip) |
| `atualizar(self, db, **campos)` | Parcial |
| `remover(self, db)` | `DELETE` físico |

O relacionamento `local` é carregado com `lazy="joined"` — toda consulta a
`Restaurante` já traz o `Local` no mesmo `SELECT` (sem N+1 queries).

---

## Produtos — `/produtos` (`produto_controller.py`)

CRUD de administração, mesmo padrão do Restaurante: sem filtro de
visibilidade, sem autenticação.

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `POST` | `/produtos` | — | Cadastra, vinculado a `restaurante_id` existente. | `201`, `422` |
| `GET` | `/produtos` | — | Lista, filtro opcional `?restaurante_id=`, paginação. | `200` |
| `GET` | `/produtos/{id}` | — | Consulta por id. | `200`, `404` |
| `PUT` | `/produtos/{id}` | — | Altera campos parciais (nome, descrição, preço, disponibilidade). | `200`, `404` |
| `DELETE` | `/produtos/{id}` | — | Remove. | `204`, `404` |

**Métodos de Model (`app/models/produto.py`):**

| Método | Para quê |
|---|---|
| `buscar_por_id(db, id)` | Consulta simples |
| `listar(db, restaurante_id=None, limite=100, pular=0)` | Listagem de administração |
| `listar_disponiveis(db, restaurante_id)` | **Usado só por `/consultas`** — só `disponivel = true`, ordenado por nome |
| `criar(db, *, restaurante_id, nome, preco, descricao=None, disponivel=True)` | Grava |
| `atualizar(self, db, **campos)` | Parcial |
| `remover(self, db)` | `DELETE` físico |

---

## Consultas do cliente — `/consultas` (`consulta_controller.py`)

Camada de **leitura** pensada para o app do cliente final — só o que ele
pode efetivamente pedir. Ver comparação completa com o CRUD de administração
em `docs/ARQUITETURA.md`, §5.

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `GET` | `/consultas/restaurantes` | — | Só restaurantes `aprovado`, endereço embutido, sem CNPJ. Filtro `?busca=` (nome, case-insensitive) + paginação. | `200` |
| `GET` | `/consultas/restaurantes/{id}` | — | Um restaurante aprovado. `404` se pendente/recusado/inexistente. | `200`, `404` |
| `GET` | `/consultas/restaurantes/{id}/cardapio` | — | Dados do restaurante + itens `disponivel = true` + `total_itens`. | `200`, `404` |

Reaproveita os métodos `Restaurante.listar_aprovados`,
`Restaurante.buscar_aprovado_por_id` e `Produto.listar_disponiveis` descritos
acima — este controller não tem lógica de negócio própria, só monta a
resposta no formato de `app/schemas/consulta.py`.

---

## Cesta — `/cesta` (`sacola_controller.py`)

Ainda **só leitura**: mostra a cesta atual do cliente logado com o total já
calculado. Não existem endpoints para adicionar/remover item da cesta —
são o próximo passo natural (junto com fechar pedido a partir dela).

| Método | Rota | Auth | Descrição | Códigos |
|---|---|---|---|---|
| `GET` | `/cesta` | JWT | Cesta + itens + subtotal por item + total do usuário logado. Se não existe cesta ainda, devolve uma estrutura vazia com `total = 0.00` (não é `404`). | `200`, `401` |

**Métodos de Model:**
- `Sacola.buscar_por_cliente(db, cliente_id)` (`app/models/sacola.py`) — pega a cesta mais recente do cliente.
- `ItemSacola.listar_por_sacola(db, sacola_id)` — itens daquela cesta.
- `Produto.buscar_por_id` é chamado por item, para montar nome/preço atual e calcular o subtotal (`preco * quantidade`) no momento da consulta — o preço não fica "congelado" na cesta, é sempre o preço vigente do produto.

---

## Referência rápida de todos os métodos de Model

Para quem quer o inventário completo num único lugar (em vez de navegar
seção por seção acima):

| Model | Arquivo | Métodos |
|---|---|---|
| `Usuario` | `app/models/usuario.py` | `tipo_e_valido`, `email_ja_cadastrado`, `telefone_ja_cadastrado`, `buscar_por_email`, `buscar_por_telefone`, `buscar_por_id`, `listar`, `criar`, `atualizar`, `remover` |
| `Local` | `app/models/local.py` | `buscar_por_id`, `listar`, `criar`, `atualizar`, `excluir` |
| `Restaurante` | `app/models/restaurante.py` | `cnpj_ja_cadastrado`, `buscar_por_id`, `listar`, `listar_aprovados`, `buscar_aprovado_por_id`, `criar`, `atualizar`, `remover` |
| `Produto` | `app/models/produto.py` | `buscar_por_id`, `listar`, `listar_disponiveis`, `criar`, `atualizar`, `remover` |
| `Sacola` | `app/models/sacola.py` | `buscar_por_cliente` |
| `ItemSacola` | `app/models/sacola.py` | `listar_por_sacola` |
| `CodigoOTP` | `app/models/codigo_otp.py` | Nenhum (manipulado direto pelo controller via `db.get`/`db.add`/`db.delete`) |

E as funções de segurança usadas por praticamente todo controller protegido
(`app/core/security.py`): `gerar_hash_senha`, `verificar_senha`,
`criar_token_acesso`, `decodificar_token`, `obter_usuario_logado` (dependência
FastAPI), `exigir_admin` (dependência FastAPI).
