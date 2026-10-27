"""Configuracao central da aplicacao, lida do arquivo .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/entregafood"
    )

    JWT_SECRET: str = "troque-esta-chave"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    # Autenticacao com Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # Autenticacao com Facebook
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""
    FACEBOOK_REDIRECT_URI: str = (
        "https://entregafood-back-dev.onrender.com/auth/facebook/callback"
    )

    FRONTEND_URL: str = "http://localhost:5173"

    # Taxa de entrega pela distancia (app/core/frete.py)
    ORS_API_KEY: str = ""  # vazio = distancia estimada em linha reta x fator
    FRETE_FATOR_CIRCUITO: float = 1.6
    FRETE_TAXA_BASE: float = 4.00
    FRETE_KM_INCLUSOS: float = 2.0
    FRETE_TAXA_MINIMA: float = 4.00
    FRETE_RAIO_MAX_KM: float = 8.0

    # Notificacoes push (Web Push / VAPID) - app/core/push.py
    # Sem as chaves, o sistema funciona normalmente e so nao envia push.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:contato@entregafood.com"

    # Push no app mobile (Firebase Cloud Messaging) - app/core/push_fcm.py
    # JSON da conta de servico do Firebase (uma linha ou base64). Vazio = sem FCM.
    FIREBASE_CREDENCIAIS: str = ""

    # Pagamento com Asaas - app/core/pagamento_asaas.py
    # Sem a chave, o pagamento usa o gateway simulado (app/core/pagamento_cartao.py).
    ASAAS_API_KEY: str = ""
    ASAAS_BASE_URL: str = "https://api-sandbox.asaas.com/v3"

    # E-mail da nota fiscal (SMTP) - app/core/email.py
    # Sem SMTP_HOST, a nota so e gerada e o envio fica registrado no log.
    SMTP_HOST: str = ""
    SMTP_PORTA: int = 587
    SMTP_USUARIO: str = ""
    SMTP_SENHA: str = ""
    SMTP_REMETENTE: str = ""

    # Codigo de validacao (OTP) do login e do cadastro - app/core/otp_envio.py
    # Com SMTP o codigo vai so por e-mail; true devolve tambem na resposta.
    OTP_MOSTRAR_CODIGO: bool = False

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()