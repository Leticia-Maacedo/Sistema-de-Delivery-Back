"""VIEW — schemas Pydantic do dominio Produto."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProdutoCreate(BaseModel):
    restaurante_id: int
    nome: str = Field(min_length=2, max_length=120, examples=["X-Salada"])
    descricao: str | None = Field(default=None, max_length=300, examples=["Pão, hambúrguer, queijo e salada"])
    preco: Decimal = Field(gt=0, examples=["24.90"])
    disponivel: bool = True


class ProdutoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=300)
    preco: Decimal | None = Field(default=None, gt=0)
    disponivel: bool | None = None


class ProdutoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurante_id: int
    nome: str
    descricao: str | None
    preco: Decimal
    disponivel: bool
