-- ============================================================
-- EntregaFood - Script de criacao das tabelas (PostgreSQL 16)
-- Anexo A do Documento do Projeto
-- ATENCAO: banco RELACIONAL. Nao usar NoSQL.
-- ============================================================

CREATE TABLE usuario (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(120) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    senha_hash      VARCHAR(255),
    telefone        VARCHAR(20),
    tipo            VARCHAR(20) NOT NULL CHECK (tipo IN ('cliente','restaurante','entregador','admin')),
    oauth_provider  VARCHAR(20),
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE local (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuario(id),
    endereco        VARCHAR(200) NOT NULL,
    tipo            VARCHAR(20) NOT NULL,
    latitude        DECIMAL(9,6) NOT NULL,
    longitude       DECIMAL(9,6) NOT NULL,
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE restaurante (
    id                  SERIAL PRIMARY KEY,
    local_id            INTEGER NOT NULL REFERENCES local(id),
    nome_fantasia       VARCHAR(120) NOT NULL,
    cnpj                VARCHAR(18) NOT NULL UNIQUE,
    status_aprovacao    VARCHAR(20) NOT NULL DEFAULT 'pendente',
    taxa_entrega_km     DECIMAL(6,2) NOT NULL,
    criado_em           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE produto (
    id              SERIAL PRIMARY KEY,
    restaurante_id  INTEGER NOT NULL REFERENCES restaurante(id),
    nome            VARCHAR(120) NOT NULL,
    descricao       VARCHAR(300),
    preco           DECIMAL(8,2) NOT NULL,
    disponivel      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sacola (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES usuario(id),
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMP
);

CREATE TABLE item_sacola (
    id              SERIAL PRIMARY KEY,
    sacola_id       INTEGER NOT NULL REFERENCES sacola(id),
    produto_id      INTEGER NOT NULL REFERENCES produto(id),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0)
);

CREATE TABLE pedido (
    id                  SERIAL PRIMARY KEY,
    cliente_id          INTEGER NOT NULL REFERENCES usuario(id),
    restaurante_id      INTEGER NOT NULL REFERENCES restaurante(id),
    entregador_id       INTEGER REFERENCES usuario(id),
    status              VARCHAR(30) NOT NULL DEFAULT 'aguardando_aceite',
    tipo_entrega        VARCHAR(20) NOT NULL,
    forma_pagamento     VARCHAR(20) NOT NULL,
    valor_total         DECIMAL(8,2) NOT NULL,
    taxa_entrega        DECIMAL(6,2) NOT NULL,
    cupom_fiscal        VARCHAR(50),
    criado_em           TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMP
);

CREATE TABLE item_pedido (
    id              SERIAL PRIMARY KEY,
    pedido_id       INTEGER NOT NULL REFERENCES pedido(id),
    produto_id      INTEGER NOT NULL REFERENCES produto(id),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario  DECIMAL(8,2) NOT NULL
);

CREATE TABLE pagamento (
    id                      SERIAL PRIMARY KEY,
    pedido_id               INTEGER NOT NULL UNIQUE REFERENCES pedido(id),
    metodo                  VARCHAR(20) NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pendente',
    valor                   DECIMAL(8,2) NOT NULL,
    transacao_externa_id    VARCHAR(100),
    criado_em               TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE entrega (
    id                  SERIAL PRIMARY KEY,
    pedido_id           INTEGER NOT NULL UNIQUE REFERENCES pedido(id),
    entregador_id       INTEGER REFERENCES usuario(id),
    status              VARCHAR(20) NOT NULL DEFAULT 'aguardando',
    latitude_atual      DECIMAL(9,6),
    longitude_atual     DECIMAL(9,6),
    recusada_por        VARCHAR(200),
    atualizado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE avaliacao (
    id              SERIAL PRIMARY KEY,
    pedido_id       INTEGER NOT NULL REFERENCES pedido(id),
    avaliador_id    INTEGER NOT NULL REFERENCES usuario(id),
    avaliado_id     INTEGER NOT NULL REFERENCES usuario(id),
    nota            SMALLINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario      VARCHAR(300),
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indices de apoio para consultas frequentes
CREATE INDEX idx_produto_restaurante ON produto(restaurante_id);
CREATE INDEX idx_pedido_cliente      ON pedido(cliente_id);
CREATE INDEX idx_pedido_restaurante  ON pedido(restaurante_id);
CREATE INDEX idx_pedido_entregador   ON pedido(entregador_id);
CREATE INDEX idx_local_usuario       ON local(usuario_id);
