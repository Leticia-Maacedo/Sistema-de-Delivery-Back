"""VIEW — schemas Pydantic das consultas voltadas ao cliente.

Diferente de `restaurante.py` / `produto.py` (que servem o CRUD de
administracao), aqui o formato do JSON e o que o app do cliente precisa
pra montar a tela de navegacao e o cardapio: dados do restaurante ja
com o endereco embutido e a lista de itens disponiveis.
"""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class LocalResumoOut(BaseModel):
    """Endereco do restaurante, embutido na consulta (sem expor usuario_id)."""

    model_config = ConfigDict(from_attributes=True)

    endereco: str
    latitude: Decimal
    longitude: Decimal


class RestauranteConsultaOut(BaseModel):
    """Restaurante como o cliente ve: sem CNPJ, com o endereco junto."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome_fantasia: str
    status_aprovacao: str
    taxa_entrega_km: Decimal
    local: LocalResumoOut


class ItemCardapioOut(BaseModel):
    """Um item do cardapio. So os campos que interessam pra quem vai pedir."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    descricao: str | None
    preco: Decimal


class CardapioOut(BaseModel):
    """Resposta de GET /consultas/restaurantes/{id}/cardapio."""

    restaurante: RestauranteConsultaOut
    total_itens: int
    itens: list[ItemCardapioOut]
