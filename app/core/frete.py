"""Calculo da taxa de entrega pela distancia (Sprint 3).

A distancia entre o restaurante e o endereco do cliente vem de:

1. OpenRouteService (distancia pela rua), quando ORS_API_KEY estiver
   configurada no .env;
2. linha reta (Haversine) multiplicada por um fator de correcao, quando
   nao houver chave ou o servico falhar. No centro de Sao Paulo a rota
   real medida foi de 1,7 a 2,1 vezes a linha reta (ver
   docs/pesquisas/PESQUISA_Taxa_Entrega_Distancia), por isso o fator
   padrao e 1,6.

Regra da taxa (base + km adicional):

    taxa = max(taxa_minima, taxa_base + valor_km x max(0, distancia - km_inclusos))

arredondada para cima em R$ 0,10. O valor por km e o `taxa_entrega_km`
de cada restaurante; os demais parametros vem do .env.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

import httpx

from app.core.config import get_settings

RAIO_TERRA_KM = 6371.0088
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"

settings = get_settings()


@dataclass
class Distancia:
    km: Decimal
    metodo: str  # "rota" ou "estimada"


def distancia_linha_reta_km(lat1, lon1, lat2, lon2) -> Decimal:
    """Distancia em linha reta entre dois pontos (formula de Haversine)."""

    la1, lo1, la2, lo2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    km = 2 * RAIO_TERRA_KM * math.asin(math.sqrt(h))
    return Decimal(str(round(km, 3)))


def distancia_rota_km(lat1, lon1, lat2, lon2) -> Decimal:
    """Distancia pela rua no OpenRouteService. Levanta httpx.HTTPError se falhar."""

    resposta = httpx.post(
        ORS_URL,
        headers={"Authorization": settings.ORS_API_KEY},
        # O ORS recebe [longitude, latitude], ao contrario do banco.
        json={"coordinates": [[float(lon1), float(lat1)], [float(lon2), float(lat2)]]},
        timeout=5.0,
    )
    resposta.raise_for_status()
    metros = resposta.json()["routes"][0]["summary"]["distance"]
    return Decimal(str(round(metros / 1000, 3)))


def medir_distancia(origem, destino) -> Distancia:
    """Mede a distancia entre dois Locais (objetos com latitude/longitude)."""

    if settings.ORS_API_KEY:
        try:
            km = distancia_rota_km(
                origem.latitude, origem.longitude, destino.latitude, destino.longitude
            )
            return Distancia(km=km, metodo="rota")
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            pass  # cai para a estimativa em linha reta

    reta = distancia_linha_reta_km(
        origem.latitude, origem.longitude, destino.latitude, destino.longitude
    )
    fator = Decimal(str(settings.FRETE_FATOR_CIRCUITO))
    return Distancia(km=(reta * fator).quantize(Decimal("0.001")), metodo="estimada")


def entrega_no_raio(distancia_km: Decimal, raio_km: float | None = None) -> bool:
    """Dentro do raio do restaurante (ou do limite da plataforma)."""
    limite = raio_km if raio_km is not None else settings.FRETE_RAIO_MAX_KM
    return distancia_km <= Decimal(str(limite))


def calcular_taxa_entrega(distancia_km: Decimal, valor_km: Decimal) -> Decimal:
    """Aplica a regra base + km adicional e arredonda para cima em R$ 0,10."""

    base = Decimal(str(settings.FRETE_TAXA_BASE))
    inclusos = Decimal(str(settings.FRETE_KM_INCLUSOS))
    minima = Decimal(str(settings.FRETE_TAXA_MINIMA))

    valor = base + Decimal(valor_km) * max(Decimal("0"), distancia_km - inclusos)
    valor = max(minima, valor)

    subido = (valor * 10).quantize(Decimal("1"), rounding=ROUND_CEILING) / 10
    return subido.quantize(Decimal("0.01"))
