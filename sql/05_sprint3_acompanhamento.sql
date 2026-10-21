-- ============================================================
-- EntregaFood - Sprint 3
-- Acompanhamento da entrega
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.

-- Codigo que o cliente informa ao receber o pedido (entregador ou
-- balcao confere) e o momento em que a entrega foi concluida.
ALTER TABLE entrega
    ADD COLUMN IF NOT EXISTS codigo_validacao VARCHAR(6);

ALTER TABLE entrega
    ADD COLUMN IF NOT EXISTS entregue_em TIMESTAMP;

-- Linha do tempo do pedido: cada mudanca de status vira uma linha.
-- E o que a tela de acompanhamento do cliente mostra.
CREATE TABLE IF NOT EXISTS pedido_status_historico (
    id              SERIAL PRIMARY KEY,
    pedido_id       INTEGER NOT NULL REFERENCES pedido(id),
    status          VARCHAR(30) NOT NULL,
    alterado_por    INTEGER REFERENCES usuario(id),
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_status_historico_pedido
    ON pedido_status_historico(pedido_id);

CREATE INDEX IF NOT EXISTS idx_pedido_status
    ON pedido(status);
