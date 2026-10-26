-- ============================================================
-- EntregaFood - Sprint 3
-- Gestao do restaurante pelo parceiro (Portal do Parceiro)
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Pode rodar ANTES do deploy da API (so acrescenta colunas com padrao).

-- Aberto (TRUE) ou pausado pelo dono (FALSE). Pausado nao recebe pedidos.
ALTER TABLE restaurante ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;

-- Raio de entrega do restaurante em km. NULL = limite padrao da plataforma
-- (FRETE_RAIO_MAX_KM).
ALTER TABLE restaurante ADD COLUMN IF NOT EXISTS raio_entrega_km NUMERIC(5, 2);

-- Horario de funcionamento (todos os dias). NULL nos dois = sem horario
-- definido (aberto enquanto estiver ativo). Fechamento menor que a
-- abertura = vira a meia-noite (ex.: 18:00 as 02:00).
ALTER TABLE restaurante ADD COLUMN IF NOT EXISTS horario_abertura TIME;
ALTER TABLE restaurante ADD COLUMN IF NOT EXISTS horario_fechamento TIME;
