-- ============================================================
-- EntregaFood - Sprint 3
-- Endereco de entrega gravado no pedido
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon JUNTO com o deploy da API desta versao.

-- O cliente escolhe o endereco na cesta. O pedido guarda uma copia dele:
-- se depois o cliente alterar ou excluir o endereco, o destino do pedido
-- (rastreio, painel do entregador) continua o mesmo.
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS endereco_entrega VARCHAR(200);
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS latitude_entrega NUMERIC(9, 6);
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS longitude_entrega NUMERIC(9, 6);

-- Pedidos de entrega ja existentes: copia o ultimo endereco do cliente
-- (era o que o sistema usava como destino ate esta versao).
UPDATE pedido p
SET    endereco_entrega  = l.endereco,
       latitude_entrega  = l.latitude,
       longitude_entrega = l.longitude
FROM   (
    SELECT DISTINCT ON (usuario_id) usuario_id, endereco, latitude, longitude
    FROM   local
    WHERE  tipo <> 'restaurante'
    ORDER  BY usuario_id, id DESC
) l
WHERE  p.cliente_id = l.usuario_id
  AND  p.tipo_entrega = 'delivery'
  AND  p.endereco_entrega IS NULL;
