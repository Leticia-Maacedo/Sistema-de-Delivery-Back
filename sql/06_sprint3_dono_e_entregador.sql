-- ============================================================
-- EntregaFood - Sprint 3
-- Dono do restaurante e entregador num lugar so
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
--
-- 1. restaurante.usuario_id: liga o restaurante ao usuario dono, para o
--    painel de pedidos mostrar a cada restaurante so os pedidos dele.
--
-- 2. Remove pedido.entregador_id: o entregador passa a ficar so em
--    entrega.entregador_id (o professor apontou que os dois campos eram
--    redundantes). O pedido guarda a parte comercial (cliente, restaurante,
--    valores); a entrega guarda a logistica (quem leva, onde esta, codigo).


-- 1. Dono do restaurante ------------------------------------------------------

ALTER TABLE restaurante
    ADD COLUMN IF NOT EXISTS usuario_id INTEGER REFERENCES usuario(id);

-- Restaurantes que ja existem: o dono e o usuario do endereco (local) do
-- restaurante, quando esse usuario e do tipo "restaurante" (e o caso do
-- seed e do cadastro feito pela Area do Parceiro no front).
UPDATE restaurante r
SET    usuario_id = l.usuario_id
FROM   local l
JOIN   usuario u ON u.id = l.usuario_id
WHERE  r.local_id = l.id
  AND  r.usuario_id IS NULL
  AND  u.tipo = 'restaurante';

CREATE INDEX IF NOT EXISTS idx_restaurante_usuario
    ON restaurante(usuario_id);


-- 2. Entregador so na entrega -------------------------------------------------

-- Copia o que so estiver no pedido antes de apagar a coluna.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pedido' AND column_name = 'entregador_id'
    ) THEN
        UPDATE entrega e
        SET    entregador_id = p.entregador_id
        FROM   pedido p
        WHERE  e.pedido_id = p.id
          AND  e.entregador_id IS NULL
          AND  p.entregador_id IS NOT NULL;
    END IF;
END $$;

DROP INDEX IF EXISTS idx_pedido_entregador;

ALTER TABLE pedido
    DROP COLUMN IF EXISTS entregador_id;

CREATE INDEX IF NOT EXISTS idx_entrega_entregador
    ON entrega(entregador_id);
