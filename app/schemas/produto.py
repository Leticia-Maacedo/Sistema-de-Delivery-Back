"""VIEW — schemas Pydantic do dominio Produto."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# Estoque (Sprint 4): null = o restaurante nao controla estoque do produto.
DESCRICAO_ESTOQUE = "Unidades em estoque. null = sem controle de estoque (vende sem limite)."


class ProdutoCreate(BaseModel):
    restaurante_id: int
    nome: str = Field(min_length=2, max_length=120, examples=["X-Salada"])
    descricao: str | None = Field(default=None, max_length=300, examples=["Pão, hambúrguer, queijo e salada"])
    preco: Decimal = Field(gt=0, examples=["24.90"])
    disponivel: bool = True
    estoque: int | None = Field(default=None, ge=0, le=99999, description=DESCRICAO_ESTOQUE, examples=[20])


class ProdutoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=300)
    preco: Decimal | None = Field(default=None, gt=0)
    disponivel: bool | None = None
    estoque: int | None = Field(default=None, ge=0, le=99999, description=DESCRICAO_ESTOQUE)


class ProdutoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurante_id: int
    nome: str
    descricao: str | None
    preco: Decimal
    disponivel: bool
    estoque: int | None = None


# ------------------------------------------------------------------ estoque


class EstoqueDefinirIn(BaseModel):
    """Contagem do estoque: substitui o valor atual."""

    estoque: int | None = Field(ge=0, le=99999, description=DESCRICAO_ESTOQUE, examples=[30])


class EstoqueAjusteIn(BaseModel):
    """Entrada (positivo) ou saida (negativo) de unidades."""

    ajuste: int = Field(ge=-99999, le=99999, description="Ex.: 10 = chegou mercadoria; -2 = perda.", examples=[10])


class EstoqueOut(BaseModel):
    produto_id: int
    nome: str
    disponivel: bool
    controla_estoque: bool
    estoque: int | None
    esgotado: bool
