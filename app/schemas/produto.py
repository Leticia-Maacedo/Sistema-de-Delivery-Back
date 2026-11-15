"""VIEW — schemas Pydantic do dominio Produto."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import codigo_barras

# Estoque (Sprint 4): null = o restaurante nao controla estoque do produto.
DESCRICAO_ESTOQUE = "Unidades em estoque. null = sem controle de estoque (vende sem limite)."
# Backlog: GTIN da embalagem; null = sem código. Enviar null no PUT apaga.
DESCRICAO_CODIGO = "Código de barras GTIN (EAN-8, UPC-A, EAN-13 ou GTIN-14), com dígito verificador conferido."


class ProdutoCreate(BaseModel):
    restaurante_id: int
    nome: str = Field(min_length=2, max_length=120, examples=["X-Salada"])
    descricao: str | None = Field(default=None, max_length=300, examples=["Pão, hambúrguer, queijo e salada"])
    preco: Decimal = Field(gt=0, examples=["24.90"])
    disponivel: bool = True
    estoque: int | None = Field(default=None, ge=0, le=99999, description=DESCRICAO_ESTOQUE, examples=[20])
    codigo_barras: str | None = Field(default=None, max_length=20, description=DESCRICAO_CODIGO, examples=["7894900011517"])

    @field_validator("codigo_barras")
    @classmethod
    def _codigo_barras(cls, v):
        return codigo_barras.validar(v)


class ProdutoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=300)
    preco: Decimal | None = Field(default=None, gt=0)
    disponivel: bool | None = None
    estoque: int | None = Field(default=None, ge=0, le=99999, description=DESCRICAO_ESTOQUE)
    codigo_barras: str | None = Field(default=None, max_length=20, description=DESCRICAO_CODIGO)

    @field_validator("codigo_barras")
    @classmethod
    def _codigo_barras(cls, v):
        return codigo_barras.validar(v)


class ProdutoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurante_id: int
    nome: str
    descricao: str | None
    preco: Decimal
    disponivel: bool
    estoque: int | None = None
    codigo_barras: str | None = None


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
