-- ============================================================
-- EntregaFood - Sprint 3
-- Notificacoes push (Web Push)
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.

-- Cada navegador/celular em que o usuario ativou as notificacoes gera uma
-- inscricao (endpoint do servico de push do navegador + chaves publicas).
-- Um usuario pode ter varias (computador, celular...).
CREATE TABLE IF NOT EXISTS push_inscricao (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuario(id),
    endpoint        VARCHAR(600) NOT NULL UNIQUE,
    p256dh          VARCHAR(200) NOT NULL,
    auth            VARCHAR(100) NOT NULL,
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_push_inscricao_usuario
    ON push_inscricao(usuario_id);
