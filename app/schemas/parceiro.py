"""VIEW — schemas do Portal do Parceiro (o dono gerencia o proprio restaurante)."""
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _horario_completo(abertura: time | None, fechamento: time | None) -> None:
    if (abertura is None) != (fechamento is None):
        raise ValueError("Informe o horario de abertura e o de fechamento (ou nenhum dos dois).")
    if abertura is not None and abertura == fechamento:
        raise ValueError("O horario de abertura e o de fechamento nao podem ser iguais.")


class RestauranteParceiroIn(BaseModel):
    """Cadastro do restaurante pelo proprio dono (nasce aguardando aprovacao)."""

    nome_fantasia: str = Field(min_length=2, max_length=120, examples=["Cantinho do Chef"])
    cnpj: str = Field(min_length=14, max_length=18, examples=["12.345.678/0001-90"])
    taxa_entrega_km: Decimal = Field(gt=0, le=50, examples=["2.50"])
    raio_entrega_km: Decimal | None = Field(default=None, gt=0, le=50, examples=["10"])
    horario_abertura: time | None = Field(default=None, examples=["11:00"])
    horario_fechamento: time | None = Field(default=None, examples=["23:00"])
    endereco: str = Field(min_length=5, max_length=200, examples=["Rua Augusta, 1500, Consolação, São Paulo - SP"])
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _horarios(self):
        _horario_completo(self.horario_abertura, self.horario_fechamento)
        return self


class RestauranteParceiroUpdate(BaseModel):
    """Alteracao pelo dono. Campos ausentes nao mudam; `null` limpa raio e horario."""

    nome_fantasia: str | None = Field(default=None, min_length=2, max_length=120)
    cnpj: str | None = Field(default=None, min_length=14, max_length=18)
    taxa_entrega_km: Decimal | None = Field(default=None, gt=0, le=50)
    raio_entrega_km: Decimal | None = Field(default=None, gt=0, le=50)
    horario_abertura: time | None = None
    horario_fechamento: time | None = None
    ativo: bool | None = None
    endereco: str | None = Field(default=None, min_length=5, max_length=200)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _horarios(self):
        if "horario_abertura" in self.model_fields_set or "horario_fechamento" in self.model_fields_set:
            _horario_completo(self.horario_abertura, self.horario_fechamento)
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Informe latitude e longitude juntas.")
        return self


class RestauranteParceiroOut(BaseModel):
    """Restaurante do dono, com o endereco e a situacao de funcionamento."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome_fantasia: str
    cnpj: str
    status_aprovacao: str
    taxa_entrega_km: Decimal
    raio_entrega_km: Decimal | None
    raio_padrao_km: float
    horario_abertura: time | None
    horario_fechamento: time | None
    ativo: bool
    aberto: bool
    endereco: str
    latitude: Decimal
    longitude: Decimal
    criado_em: datetime


class ProdutoParceiroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120, examples=["X-Salada"])
    descricao: str | None = Field(default=None, max_length=300)
    preco: Decimal = Field(gt=0, le=9999, examples=["24.90"])
    disponivel: bool = True


class ProdutoParceiroUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=300)
    preco: Decimal | None = Field(default=None, gt=0, le=9999)
    disponivel: bool | None = None


class ResumoParceiroOut(BaseModel):
    """Numeros reais do dia para a tela "Meu restaurante"."""

    pedidos_hoje: int
    aguardando_aceite: int
    em_andamento: int
    faturamento_hoje: Decimal
    ticket_medio_hoje: Decimal
    produtos_ativos: int
    produtos_total: int
