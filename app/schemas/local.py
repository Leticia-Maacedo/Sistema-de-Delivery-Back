"""VIEW — schemas Pydantic do dominio Local."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LocalCreate(BaseModel):
    usuario_id: int
    endereco: str = Field(min_length=5, max_length=200, examples=["Rua das Flores, 123"])
    tipo: str = Field(max_length=20, examples=["restaurante"])
    latitude: Decimal = Field(examples=["-23.550520"])
    longitude: Decimal = Field(examples=["-46.633308"])


class LocalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    endereco: str
    tipo: str
    latitude: Decimal
    longitude: Decimal
    criado_em: datetime
