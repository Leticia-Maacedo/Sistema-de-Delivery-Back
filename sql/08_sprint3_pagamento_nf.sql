-- ============================================================
-- EntregaFood - Sprint 3
-- Pagamento (cartao, PIX e dinheiro com Asaas) e nota fiscal
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon JUNTO com o deploy da API desta versao.

-- Motivo da recusa / mensagem do gateway (ex.: "Transacao nao autorizada").
ALTER TABLE pagamento ADD COLUMN IF NOT EXISTS mensagem VARCHAR(300);

-- PIX: "copia e cola" (o QR Code e gerado a partir dele) e validade.
ALTER TABLE pagamento ADD COLUMN IF NOT EXISTS pix_copia_cola TEXT;
ALTER TABLE pagamento ADD COLUMN IF NOT EXISTS pix_expira_em TIMESTAMP;

-- Ultima mudanca de status (consulta no Asaas, entrega do dinheiro...).
ALTER TABLE pagamento ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP;

-- Quando a nota fiscal foi enviada por e-mail ao cliente (NULL = nao enviada).
ALTER TABLE pagamento ADD COLUMN IF NOT EXISTS nota_enviada_em TIMESTAMP;

-- O numero da nota fica em pedido.cupom_fiscal (coluna ja existente).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pedido_cupom_fiscal
    ON pedido(cupom_fiscal)
    WHERE cupom_fiscal IS NOT NULL;
