-- ============================================================
-- EntregaFood - Sprint 4
-- Notificacoes push no app mobile (Firebase Cloud Messaging)
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon JUNTO com o deploy da API desta versao.

-- Cada celular em que o usuario abriu o app gera um token do Firebase.
-- Um usuario pode ter varios (celular novo, reinstalacao...). As inscricoes
-- do navegador (Web Push) continuam em push_inscricao (sql/07).
CREATE TABLE IF NOT EXISTS push_token_fcm (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuario(id),
    token           VARCHAR(512) NOT NULL UNIQUE,
    plataforma      VARCHAR(20) NOT NULL DEFAULT 'android',
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_push_token_fcm_usuario
    ON push_token_fcm(usuario_id);
