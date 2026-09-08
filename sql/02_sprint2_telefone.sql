-- ============================================================
-- EntregaFood - Sprint 2
-- Cadastro e autenticacao por telefone
-- ============================================================

-- Permite cadastro sem e-mail.
-- Necessario para contas criadas somente com telefone.
ALTER TABLE usuario
    ALTER COLUMN email DROP NOT NULL;

-- O telefone passa a ser um identificador unico quando informado.
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_telefone
    ON usuario (telefone)
    WHERE telefone IS NOT NULL;

-- Todo usuario deve possuir pelo menos um meio de identificacao:
-- e-mail ou telefone.
ALTER TABLE usuario
    ADD CONSTRAINT ck_usuario_email_ou_telefone
    CHECK (email IS NOT NULL OR telefone IS NOT NULL);