-- ============================================================
-- EntregaFood - Backlog
-- Codigo de barras dos produtos (leitor de codigo de barras)
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon ANTES do deploy da API desta versao (o model ja le a
-- coluna `codigo_barras`; sem ela, qualquer consulta de produto falha).

-- GTIN da embalagem (EAN-8, UPC-A, EAN-13 ou GTIN-14). NULL = item sem
-- codigo (pratos feitos na cozinha). A API confere o digito verificador.
ALTER TABLE produto ADD COLUMN IF NOT EXISTS codigo_barras VARCHAR(14);

-- O mesmo codigo nao pode estar em dois itens do mesmo restaurante
-- (restaurantes diferentes podem vender o mesmo produto). NULLs nao contam.
CREATE UNIQUE INDEX IF NOT EXISTS uq_produto_restaurante_codigo_barras
    ON produto (restaurante_id, codigo_barras);
