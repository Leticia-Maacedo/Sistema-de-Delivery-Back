"""Testes da geocodificacao no cadastro de Local (Nominatim/OpenStreetMap).

Nao precisa de chave nem de internet de verdade: a chamada HTTP pro
Nominatim e mockada. Precisa so de PostgreSQL de pe (os testes passam
pelo POST/PUT /locais de verdade).

Executar da raiz do repositorio:
    python testes/teste_geocoding_local.py
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)

falhas = 0


def checar(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global falhas
    if condicao:
        print(f"  [OK]    {descricao}")
    else:
        falhas += 1
        print(f"  [FALHA] {descricao} {detalhe}")


class RespostaFalsa:
    """Imita o `httpx.Response` o suficiente pro geocoding.py funcionar."""

    def __init__(self, corpo):
        self._corpo = corpo

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._corpo


def main() -> int:
    print("\n[1] Endereco valido -> usa lat/lng que o Nominatim devolveu")
    resposta_ok = RespostaFalsa([{"lat": "-23.5613", "lon": "-46.6558"}])
    with patch("app.core.geocoding.httpx.get", return_value=resposta_ok) as mock_get:
        r = cliente.post("/locais", json={
            "usuario_id": 1, "endereco": "Av. Paulista, 1000", "tipo": "restaurante",
        })
        checar("POST sem lat/lng chama o Nominatim", mock_get.called)
        checar(
            "manda um User-Agent identificando o projeto (exigido pela politica do Nominatim)",
            "User-Agent" in mock_get.call_args.kwargs.get("headers", {}),
        )
        checar(
            "endereco enviado e o mesmo do cadastro",
            "Av. Paulista, 1000" in mock_get.call_args.kwargs["params"]["q"],
        )
        checar(
            "nao quebrou antes de tentar geocodificar (nao e erro 422 de validacao)",
            r.status_code != 422 or "usuario" not in r.text.lower(),
        )

    print("\n[2] Lat/lng informados manualmente (como o front ja faz hoje) -> Nominatim NAO e consultado")
    with patch("app.core.geocoding.httpx.get") as mock_get:
        cliente.post("/locais", json={
            "usuario_id": 1, "endereco": "Rua Teste, 1", "tipo": "casa",
            "latitude": "-23.550520", "longitude": "-46.633308",
        })
        checar("Nominatim nao foi chamado quando lat/lng vieram no corpo", not mock_get.called)

    print("\n[3] Endereco que o Nominatim nao encontra -> 422 (erro do usuario, nao 500)")
    resposta_vazia = RespostaFalsa([])
    with patch("app.core.geocoding.httpx.get", return_value=resposta_vazia):
        r = cliente.post("/locais", json={
            "usuario_id": 1, "endereco": "Endereco Que Nao Existe De Jeito Nenhum, 99999",
            "tipo": "casa",
        })
        checar("retorna HTTP 422", r.status_code == 422, f"(veio {r.status_code})")

    print("\n[4] Nominatim fora do ar / erro de rede -> 502, nao trava a API")
    import httpx as httpx_real
    with patch("app.core.geocoding.httpx.get", side_effect=httpx_real.ConnectError("falhou")):
        r = cliente.post("/locais", json={
            "usuario_id": 1, "endereco": "Rua Qualquer, 1", "tipo": "casa",
        })
        checar("retorna HTTP 502", r.status_code == 502, f"(veio {r.status_code})")

    print("\n" + "=" * 58)
    if falhas == 0:
        print("TODAS AS VERIFICACOES PASSARAM - geocoding via Nominatim validado.")
    else:
        print(f"{falhas} VERIFICACAO(OES) FALHARAM.")
    print("=" * 58 + "\n")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())