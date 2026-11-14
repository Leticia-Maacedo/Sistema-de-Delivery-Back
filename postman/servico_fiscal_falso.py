"""Servico fiscal falso no formato da API v2 da Focus NFe (NFC-e), para testar a emissao (Postman).

Usado por `servidor_local_teste.py --fiscal`. Faz o papel do ambiente de
homologacao da Focus NFe (https://homologacao.focusnfe.com.br/v2), que exige
empresa com CNPJ, inscricao estadual credenciada, certificado A1 e CSC:

- POST /v2/nfce?ref=<referencia>  emite (sincrono): confere o token (HTTP Basic),
  valida os campos obrigatorios da NFC-e e responde "autorizado" com numero,
  serie, chave e caminho do DANFCe; referencia repetida -> 422 already_processed;
- GET  /v2/nfce/<referencia>      consulta a nota;
- GET  /notas_fiscais_consumidor/<arquivo>.html  DANFCe simples.

O comportamento muda por POST /controle/modo {"modo": ...}:
  autorizar (padrao) | rejeitar (erro_autorizacao 704 da SEFAZ) |
  fora_do_ar (503) | limite (429) | lento (demora mais que o tempo limite da API).
GET /capturas devolve cada requisicao recebida (referencia, modo, corpo), para
o Postman conferir o que a API mandou. So o servico e trocado: a montagem da
NFC-e, o tratamento das respostas e o reenvio sao o codigo real do back.
"""

import base64
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

OBRIGATORIOS = ("cnpj_emitente", "data_emissao", "presenca_comprador", "modalidade_frete", "local_destino", "items", "formas_pagamento")
OBRIGATORIOS_ITEM = ("numero_item", "codigo_ncm", "codigo_produto", "descricao", "quantidade_comercial", "quantidade_tributavel", "cfop",
                     "valor_unitario_comercial", "valor_unitario_tributavel", "valor_bruto", "unidade_comercial", "unidade_tributavel",
                     "icms_origem", "icms_situacao_tributaria")

app = FastAPI(title="Focus NFe falso (homologação local)")
estado = {"modo": "autorizar", "token": "", "atraso": 20, "capturas": [], "notas": {}}


def configurar(token: str, atraso_lento: float) -> None:
    estado["token"], estado["atraso"] = token, atraso_lento


def _autorizado(request: Request) -> bool:
    esperado = "Basic " + base64.b64encode(f"{estado['token']}:".encode()).decode()
    return request.headers.get("authorization") == esperado


@app.post("/controle/modo")
async def mudar_modo(request: Request):
    estado["modo"] = (await request.json())["modo"]
    return {"modo": estado["modo"]}


@app.get("/capturas")
def capturas():
    return estado["capturas"]


@app.post("/v2/nfce")
async def emitir(request: Request, ref: str | None = None):
    if not _autorizado(request):
        return PlainTextResponse("HTTP Basic: Access denied.", status_code=401)
    if not ref:
        return JSONResponse({"codigo": "requisicao_invalida", "mensagem": "Parâmetro ref não informado"}, status_code=400)
    corpo = await request.json()
    modo = estado["modo"]
    estado["capturas"].append({"ref": ref, "modo": modo, "corpo": corpo})
    if modo == "fora_do_ar":
        return PlainTextResponse("Service Unavailable", status_code=503)
    if modo == "limite":
        return JSONResponse({"codigo": "limite_requisicoes", "mensagem": "Limite de requisições atingido"}, status_code=429)
    if modo == "lento":
        time.sleep(estado["atraso"])
    erros = [{"campo": c, "mensagem": "não pode ser vazio"} for c in OBRIGATORIOS if corpo.get(c) in (None, "", [])]
    for item in corpo.get("items") or []:
        erros += [{"campo": f"items.{c}", "mensagem": "não pode ser vazio"} for c in OBRIGATORIOS_ITEM if item.get(c) in (None, "")]
    if erros:
        return JSONResponse({"codigo": "erro_validacao_schema", "mensagem": "Erro de validação", "erros": erros}, status_code=422)
    if ref in estado["notas"]:
        return JSONResponse({"codigo": "already_processed", "mensagem": "Nota fiscal já processada"}, status_code=422)
    if modo == "rejeitar":
        return JSONResponse({"cnpj_emitente": corpo["cnpj_emitente"], "ref": ref, "status": "erro_autorizacao", "status_sefaz": "704",
                             "mensagem_sefaz": "Rejeição: NFC-e com Data-Hora de emissão atrasada"}, status_code=201)
    numero = str(1000 + len(estado["notas"]))
    nota = {"cnpj_emitente": corpo["cnpj_emitente"], "ref": ref, "status": "autorizado", "status_sefaz": "100",
            "mensagem_sefaz": "Autorizado o uso da NF-e", "numero": numero, "serie": "1",
            "chave_nfe": "NFe35" + "261112345678000190" + "65001" + numero.zfill(9) + "1234567890",
            "protocolo": "13526" + numero.zfill(10), "caminho_danfe": f"/notas_fiscais_consumidor/NFe{numero}.html",
            "qrcode_url": f"https://homologacao.nfce.fazenda.sp.gov.br/qrcode?p={numero}"}
    estado["notas"][ref] = nota
    return JSONResponse(nota, status_code=201)


@app.get("/v2/nfce/{ref}")
def consultar(ref: str, request: Request):
    if not _autorizado(request):
        return PlainTextResponse("HTTP Basic: Access denied.", status_code=401)
    if ref not in estado["notas"]:
        return JSONResponse({"codigo": "nfce_nao_encontrada", "mensagem": "Nota fiscal não encontrada"}, status_code=404)
    return estado["notas"][ref]


@app.delete("/v2/nfce/{ref}")
async def cancelar(ref: str, request: Request):
    if not _autorizado(request):
        return PlainTextResponse("HTTP Basic: Access denied.", status_code=401)
    justificativa = (await request.json()).get("justificativa", "")
    estado["capturas"].append({"ref": ref, "modo": estado["modo"], "cancelamento": justificativa})
    if ref not in estado["notas"]:
        return JSONResponse({"codigo": "nfce_nao_encontrada", "mensagem": "Nota fiscal não encontrada"}, status_code=404)
    if not 15 <= len(justificativa) <= 255:
        return JSONResponse({"codigo": "requisicao_invalida", "mensagem": "Justificativa deve ter de 15 a 255 caracteres"}, status_code=400)
    if estado["modo"] == "prazo_cancelamento":
        return JSONResponse({"status": "erro_cancelamento", "status_sefaz": "501",
                             "mensagem_sefaz": "Rejeição: Prazo de cancelamento superior ao previsto na Legislação"})
    estado["notas"][ref]["status"] = "cancelado"
    return JSONResponse({"status": "cancelado", "status_sefaz": "135", "mensagem_sefaz": "Evento registrado e vinculado a NF-e",
                         "numero_protocolo": "1352600009" + ref.split("-")[-1].zfill(5)})


@app.get("/notas_fiscais_consumidor/{arquivo}", response_class=HTMLResponse)
def danfce(arquivo: str):
    return f"<html><body><h1>DANFCe (homologação local)</h1><p>{arquivo}</p><p>EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO - SEM VALOR FISCAL</p></body></html>"


def iniciar(porta: int, host: str = "127.0.0.1") -> None:
    """Sobe o servico falso numa thread (daemon) ao lado da API."""

    config = uvicorn.Config(app, host=host, port=porta, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
