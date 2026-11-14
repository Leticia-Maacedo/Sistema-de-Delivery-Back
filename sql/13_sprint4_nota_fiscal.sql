-- ============================================================
-- EntregaFood - Sprint 4
-- Situacao da emissao da nota fiscal de cada pedido
-- ============================================================
-- Idempotente: pode rodar de novo sem erro.
-- Rodar no Neon ANTES do deploy da API desta versao: a emissao da nota
-- (pagamento aprovado) grava nesta tabela.
--
-- Uma linha por pedido. As tentativas de emissao atualizam a mesma linha:
--   processando      -> enviada ao servico fiscal, sem resposta ainda
--   autorizada       -> nota valida (o numero tambem vai para pedido.cupom_fiscal)
--   rejeitada        -> a SEFAZ recusou (mensagem com o codigo); precisa de correcao
--                       e nova emissao pelo restaurante ou pelo administrador
--   pendente_reenvio -> servico fiscal fora do ar; tenta de novo em proxima_tentativa_em
--   falhou           -> passou do limite de tentativas; emissao manual
--   cancelada        -> pedido cancelado e nota cancelada na SEFAZ
CREATE TABLE IF NOT EXISTS nota_fiscal (
    id                    SERIAL PRIMARY KEY,
    pedido_id             INTEGER NOT NULL UNIQUE REFERENCES pedido(id),
    provedor              VARCHAR(20) NOT NULL,
    ambiente              VARCHAR(15) NOT NULL,
    referencia            VARCHAR(50) NOT NULL,
    status                VARCHAR(20) NOT NULL DEFAULT 'processando',
    numero                VARCHAR(50),
    serie                 VARCHAR(5),
    chave                 VARCHAR(60),
    protocolo             VARCHAR(30),
    url_danfe             VARCHAR(300),
    mensagem              VARCHAR(500),
    tentativas            INTEGER NOT NULL DEFAULT 0,
    proxima_tentativa_em  TIMESTAMP,
    criado_em             TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em         TIMESTAMP,
    CONSTRAINT ck_nota_fiscal_status
        CHECK (status IN ('processando', 'autorizada', 'rejeitada', 'pendente_reenvio', 'falhou', 'cancelada'))
);

CREATE INDEX IF NOT EXISTS idx_nota_fiscal_reenvio
    ON nota_fiscal (status, proxima_tentativa_em);

-- Pedidos que ja tinham nota simulada antes desta versao ficam registrados
-- como autorizados no provedor simulado.
INSERT INTO nota_fiscal (pedido_id, provedor, ambiente, referencia, status, numero, tentativas, criado_em)
SELECT p.id, 'simulado', 'simulado', 'pedido-' || p.id, 'autorizada', p.cupom_fiscal, 1, NOW()
FROM pedido p
WHERE p.cupom_fiscal IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM nota_fiscal n WHERE n.pedido_id = p.id);
