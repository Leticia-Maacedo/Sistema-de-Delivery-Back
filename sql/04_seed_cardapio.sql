-- ============================================================
-- EntregaFood - Sprint 2
-- Seed de dados para a consulta de Restaurante e Cardapio
--
-- Popula a cadeia usuario -> local -> restaurante -> produto com
-- dados de exemplo, pra dar o que consultar em:
--     GET /consultas/restaurantes
--     GET /consultas/restaurantes/{id}
--     GET /consultas/restaurantes/{id}/cardapio
--
-- Idempotente: pode rodar de novo sem duplicar (identifica os
-- restaurantes de exemplo pelo CNPJ).
--
-- Rodar:  psql -h localhost -U postgres -d entregafood -f sql/04_seed_cardapio.sql
-- ============================================================

BEGIN;

-- 1. Dono dos restaurantes de exemplo -------------------------------------------
INSERT INTO usuario (nome, email, tipo)
VALUES ('Dono Exemplo (seed)', 'seed-cardapio@entregafood.com', 'restaurante')
ON CONFLICT (email) DO NOTHING;

-- 2. Locais / enderecos --------------------------------------------------------
INSERT INTO local (usuario_id, endereco, tipo, latitude, longitude)
SELECT u.id, v.endereco, 'restaurante', v.lat, v.lng
FROM   usuario u
CROSS  JOIN (VALUES
    ('Av. Paulista, 1000 - Bela Vista, Sao Paulo',      -23.561414, -46.655881),
    ('Rua Aurora, 250 - Centro, Sao Paulo',             -23.539000, -46.640000),
    ('Rua dos Pinheiros, 500 - Pinheiros, Sao Paulo',   -23.564200, -46.681400)
) AS v(endereco, lat, lng)
WHERE  u.email = 'seed-cardapio@entregafood.com'
  AND  NOT EXISTS (SELECT 1 FROM local l WHERE l.endereco = v.endereco);

-- 3. Restaurantes (ja aprovados, pra aparecerem na consulta) ------------------
--    "Cantina" fica pendente de proposito: serve pra provar que a
--    consulta do cliente NAO devolve restaurante nao-aprovado.
INSERT INTO restaurante (local_id, nome_fantasia, cnpj, status_aprovacao, taxa_entrega_km)
SELECT l.id, v.nome, v.cnpj, v.stat, v.taxa
FROM (VALUES
    ('Burger da Paulista',  '11.111.111/0001-11', 'aprovado', 4.50,
     'Av. Paulista, 1000 - Bela Vista, Sao Paulo'),
    ('Sushi Aurora',        '22.222.222/0001-22', 'aprovado', 6.00,
     'Rua Aurora, 250 - Centro, Sao Paulo'),
    ('Cantina Pinheiros',   '33.333.333/0001-33', 'pendente', 5.00,
     'Rua dos Pinheiros, 500 - Pinheiros, Sao Paulo')
) AS v(nome, cnpj, stat, taxa, endereco)
JOIN local l ON l.endereco = v.endereco
WHERE NOT EXISTS (SELECT 1 FROM restaurante r WHERE r.cnpj = v.cnpj);

-- 4. Produtos / itens do cardapio -------------------------------------------------
--    O "Milk-shake" entra indisponivel de proposito: prova que o
--    cardapio so lista item com disponivel = true.
INSERT INTO produto (restaurante_id, nome, descricao, preco, disponivel)
SELECT r.id, v.nome, v.descricao, v.preco, v.disp
FROM (VALUES
    ('11.111.111/0001-11', 'X-Salada',        'Pao, hamburguer 150g, queijo, alface e tomate', 26.90, TRUE),
    ('11.111.111/0001-11', 'X-Bacon',         'Pao, hamburguer 150g, queijo e bacon',          31.90, TRUE),
    ('11.111.111/0001-11', 'Batata Frita',    'Porcao 400g',                                   19.90, TRUE),
    ('11.111.111/0001-11', 'Milk-shake',      'Chocolate, 500ml',                              18.00, FALSE),
    ('22.222.222/0001-22', 'Combo Sushi 20',  '20 pecas variadas',                             59.90, TRUE),
    ('22.222.222/0001-22', 'Temaki Salmao',   'Salmao, cream cheese e cebolinha',              32.00, TRUE),
    ('22.222.222/0001-22', 'Hot Roll (8un)',  'Empanado, recheio de salmao',                   28.00, TRUE)
) AS v(cnpj, nome, descricao, preco, disp)
JOIN restaurante r ON r.cnpj = v.cnpj
WHERE NOT EXISTS (
    SELECT 1 FROM produto p WHERE p.restaurante_id = r.id AND p.nome = v.nome
);

COMMIT;

-- Conferencia rapida:
--   SELECT nome_fantasia, status_aprovacao FROM restaurante ORDER BY id;
--   SELECT r.nome_fantasia, p.nome, p.disponivel
--   FROM produto p JOIN restaurante r ON r.id = p.restaurante_id
--   ORDER BY r.nome_fantasia, p.nome;
