"""VIEW — schemas Pydantic do dominio Restaurante."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusAprovacao = Literal["pendente", "aprovado", "recusado"]


class RestauranteCreate(BaseModel):
    local_id: int
    nome_fantasia: str = Field(min_length=2, max_length=120, examples=["Cantinho do Chef"])
    cnpj: str = Field(min_length=14, max_length=18, examples=["12.345.678/0001-90"])
    taxa_entrega_km: Decimal = Field(gt=0, examples=["2.50"])


class RestauranteUpdate(BaseModel):
    nome_fantasia: str | None = Field(default=None, min_length=2, max_length=120)
    cnpj: str | None = Field(default=None, min_length=14, max_length=18)
    taxa_entrega_km: Decimal | None = Field(default=None, gt=0)
    status_aprovacao: StatusAprovacao | None = None


class RestauranteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    local_id: int
    nome_fantasia: str
    cnpj: str
    status_aprovacao: str
    taxa_entrega_km: Decimal
    criado_em: datetime
