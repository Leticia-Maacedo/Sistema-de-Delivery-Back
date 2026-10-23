"""Schemas de notificacoes push e do rastreio da entrega."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ChavesPushIn(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class InscricaoPushIn(BaseModel):
    """O objeto PushSubscription que o navegador devolve (subscription.toJSON())."""

    endpoint: str = Field(min_length=10, max_length=600, pattern=r"^https://")
    keys: ChavesPushIn


class CancelarPushIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=600)


class ChavePublicaOut(BaseModel):
    ativo: bool
    chave_publica: str | None


class LocalizacaoIn(BaseModel):
    """Posicao atual do entregador (navegador do celular)."""

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)


class PontoOut(BaseModel):
    endereco: str | None = None
    latitude: Decimal
    longitude: Decimal


class PosicaoEntregadorOut(BaseModel):
    latitude: Decimal
    longitude: Decimal
    atualizado_em: datetime


class RastreioOut(BaseModel):
    """Dados do mapa do acompanhamento."""

    pedido_id: int
    status: str
    status_rotulo: str
    tipo_entrega: str
    restaurante_nome: str | None
    restaurante: PontoOut | None
    destino: PontoOut | None
    entregador: PosicaoEntregadorOut | None
    mapa_url: str | None
