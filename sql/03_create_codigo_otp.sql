-- ============================================================
-- EntregaFood - Sprint 2
-- Persistencia dos codigos OTP
-- ============================================================

CREATE TABLE IF NOT EXISTS codigo_otp (
    telefone   VARCHAR(20) NOT NULL,
    finalidade VARCHAR(20) NOT NULL,
    codigo     VARCHAR(6) NOT NULL,
    expira_em  TIMESTAMPTZ NOT NULL,
    tentativas INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (telefone, finalidade),

    CONSTRAINT ck_codigo_otp_finalidade
        CHECK (finalidade IN ('login', 'cadastro'))
);
