-- ============================================================
-- EntregaFood - Sprint 4
-- Estoque dos produtos
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon ANTES do deploy da API desta versao (o model ja le a
-- coluna `estoque`; sem ela, qualquer consulta de produto falha).

-- Quantidade em estoque. NULL = o restaurante nao controla estoque deste
-- produto (vende sem limite, como antes desta versao). Os produtos que ja
-- existem ficam NULL e continuam funcionando igual.
--
-- Regras (app/models/produto.py e app/models/pedido.py):
--   - cesta e fechamento recusam quantidade maior que o estoque;
--   - criar o pedido baixa o estoque na mesma transacao;
--   - pedido cancelado devolve as quantidades ao estoque;
--   - estoque 0 = esgotado: some do cardapio do cliente.
ALTER TABLE produto ADD COLUMN IF NOT EXISTS estoque INTEGER;

DO $$
BEGIN
    ALTER TABLE produto
        ADD CONSTRAINT ck_produto_estoque_nao_negativo CHECK (estoque IS NULL OR estoque >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
