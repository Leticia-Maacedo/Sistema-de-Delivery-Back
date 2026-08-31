"""VIEW — schemas Pydantic do dominio Usuario.

Camada View do MVC: define exatamente o JSON que entra e o JSON que sai
da API. E por isso que `senha` aparece na entrada e NUNCA na saida —
`senha_hash` jamais trafega para o cliente.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

TipoUsuario = Literal["cliente", "restaurante", "entregador", "admin"]


class UsuarioCreate(BaseModel):
    """Corpo do POST /usuarios (RF01)."""

    nome: str = Field(min_length=3, max_length=120, examples=["Geovane Soares"])
    email: EmailStr = Field(examples=["geovane@entregafood.com"])
    senha: str = Field(min_length=6, max_length=72, examples=["senha123"])
    telefone: str | None = Field(default=None, max_length=20, examples=["11999998888"])
    tipo: TipoUsuario = Field(default="cliente")


class UsuarioUpdate(BaseModel):
    """Corpo do PUT /usuarios/{id}. Todos os campos sao opcionais."""

    nome: str | None = Field(default=None, min_length=3, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=20)
    tipo: TipoUsuario | None = None


class UsuarioOut(BaseModel):
    """Resposta da API. Repare: nenhum campo de senha."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: EmailStr | None
    telefone: str | None
    tipo: str
    criado_em: datetime


class LoginRequest(BaseModel):
    """Corpo do POST /auth/login. Aceita e-mail ou telefone."""

    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=20)
    senha: str

    @model_validator(mode="after")
    def validar_identificador(self):
        if not self.email and not self.telefone:
            raise ValueError("Informe o e-mail ou o telefone.")

        if self.email and self.telefone:
            raise ValueError("Informe apenas o e-mail ou o telefone.")

        return self


class SolicitarOTPRequest(BaseModel):
    telefone: str = Field(
        min_length=10,
        max_length=20,
        examples=["11999998888"],
    )


class VerificarOTPRequest(BaseModel):
    telefone: str = Field(
        min_length=10,
        max_length=20,
        examples=["11999998888"],
    )
    codigo: str = Field(
        min_length=6,
        max_length=6,
        examples=["123456"],
    )


class OTPResponse(BaseModel):
    detalhe: str
    codigo_dev: str | None = None


class CadastroTelefoneRequest(BaseModel):
    nome: str = Field(
        min_length=3,
        max_length=120,
        examples=["Richard Ferreira"],
    )
    telefone: str = Field(
        min_length=10,
        max_length=20,
        examples=["11999998888"],
    )
    senha: str = Field(
        min_length=6,
        max_length=72,
        examples=["senha123"],
    )
    tipo: TipoUsuario = Field(default="cliente")


class ConfirmarCadastroTelefoneRequest(BaseModel):
    nome: str = Field(
        min_length=3,
        max_length=120,
    )
    telefone: str = Field(
        min_length=10,
        max_length=20,
    )
    senha: str = Field(
        min_length=6,
        max_length=72,
    )
    codigo: str = Field(
        min_length=6,
        max_length=6,
        examples=["123456"],
    )
    tipo: TipoUsuario = Field(default="cliente")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class MensagemResponse(BaseModel):
    detalhe: str