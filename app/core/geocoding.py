"""Geocodificação de endereços — cadastro de Local.

Usa o Nominatim (OpenStreetMap), gratuito e sem chave, a mesma escolha
que já foi feita no front (ver `src/api/geo.js`, função
`geocodificarEndereco`). Mantemos os dois no mesmo provedor pra não ter
dois fornecedores de coordenadas diferentes no mesmo cadastro.

Diferença importante em relação a chamar o Nominatim direto do
navegador: a política de uso do Nominatim exige identificar quem está
chamando com um cabeçalho `User-Agent` real (ou parâmetro `email`) [1].
O navegador NÃO deixa JavaScript sobrescrever o `User-Agent` da
requisição (é um cabeçalho protegido) então uma chamada client-side
nunca consegue cumprir essa regra direito. Aqui no back-end, sem essa
limitação, mandamos um `User-Agent` de verdade identificando o projeto.

Isso também serve de rede de segurança: se o front não mandar
latitude/longitude (ex.: alguém chamando a API direto pelo Swagger, ou
uma tela futura que não faça mais o geocoding no navegador), o
cadastro de Local continua funcionando, porque o back-end geocodifica
sozinho a partir do endereço.

[1] https://operations.osmfoundation.org/policies/nominatim/
"""

from decimal import Decimal

import httpx
from fastapi import HTTPException, status

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Exigido pela politica de uso do Nominatim — identifica o projeto que
# esta chamando. Trocar o e-mail pelo do time se for usar em producao.
USER_AGENT = "EntregaFood/1.0 (projeto academico; contato: equipe@entregafood.example)"


def geocodificar_endereco(endereco: str) -> tuple[Decimal, Decimal]:
    """Consulta o Nominatim e devolve `(latitude, longitude)` para o
    endereço informado.

    Levanta `HTTPException` quando:
      - o endereço não é encontrado (422 — erro do usuário: endereço
        incompleto ou digitado errado);
      - a chamada ao Nominatim falha, dá timeout ou devolve algo
        inesperado (502).
    """
    try:
        resposta = httpx.get(
            NOMINATIM_URL,
            params={
                "q": f"{endereco}, Brasil",
                "format": "json",
                "limit": "1",
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR",
            },
            timeout=10.0,
        )
        resposta.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível consultar o serviço de geocodificação agora. Tente novamente.",
        )

    resultados = resposta.json()

    if not resultados:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Endereço não encontrado. Confira e tente novamente (inclua rua, número, bairro e cidade).",
        )

    primeiro = resultados[0]

    return Decimal(str(primeiro["lat"])), Decimal(str(primeiro["lon"]))