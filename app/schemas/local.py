"""VIEW - schemas Pydantic do dominio Local."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LocalCreate(BaseModel):
    usuario_id: int

    endereco: str = Field(
        min_length=5,
        max_length=200,
        examples=["Rua das Flores, 123"],
    )

    tipo: str = Field(
        min_length=2,
        max_length=20,
        examples=["Casa"],
    )

    latitude: Decimal = Field(
        examples=["-23.550520"],
    )

    longitude: Decimal = Field(
        examples=["-46.633308"],
    )


class LocalUpdate(BaseModel):
    """Corpo do PUT /locais/{id}. Todos os campos sao opcionais."""

    endereco: str | None = Field(
        default=None,
        min_length=5,
        max_length=200,
    )

    tipo: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
    )

    latitude: Decimal | None = None
    longitude: Decimal | None = None


class LocalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    endereco: str
    tipo: str
    latitude: Decimal
    longitude: Decimal
    criado_em: datetime