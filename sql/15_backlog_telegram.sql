-- ============================================================
-- EntregaFood - Backlog
-- Avisos do pedido pelo Telegram
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon ANTES do deploy da API desta versao (o model ja le as
-- colunas; sem elas, qualquer consulta de usuario falha).

-- Chat do Telegram ligado a conta (NULL = nao recebe pelo Telegram).
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(32);

-- Codigo de uso unico do link https://t.me/<bot>?start=<codigo> e a validade
-- (15 minutos). Apagados quando a conta e ligada.
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telegram_codigo VARCHAR(64);
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telegram_codigo_expira TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_telegram_codigo ON usuario (telegram_codigo);
