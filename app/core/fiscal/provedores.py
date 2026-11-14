"""Provedores de emissao da nota fiscal.

Todos recebem o mesmo `DadosNota` e devolvem um `ResultadoEmissao`. A escolha
vem de FISCAL_PROVEDOR no .env:

- "simulado" (padrao): numera a nota (NF-AAAA-NNNNNN) e o documento e o PDF
  simulado de app/core/fiscal/pdf_simulado.py. Nao passa pela SEFAZ.
- "focusnfe": emite NFC-e (modelo 65) pela API v2 da Focus NFe
  (https://doc.focusnfe.com.br), em homologacao ou producao. A emissao de
  NFC-e e sincrona: a nota e autorizada ou rejeitada na mesma requisicao.

Tres resultados possiveis:
- autorizada: a nota vale (numero, serie, chave, DANFCe);
- rejeitada: a SEFAZ ou a validacao do servico recusou; tentar de novo sem
  corrigir nao adianta (mensagem com o codigo e o motivo);
- `ServicoFiscalIndisponivel`: fora do ar, tempo esgotado ou limite de
  requisicoes; a emissao e repetida depois com a mesma referencia.

Regras da NFC-e de delivery seguidas na montagem (PESQUISA_Emissao_Fiscal):
o emitente e o restaurante (CNPJ dele); a taxa de entrega entra rateada no
frete dos itens (Resposta a Consulta SEFAZ-SP 31987/2025), com a diferenca de
arredondamento no ultimo item; o EntregaFood e o intermediador (NT 2020.006),
quando FISCAL_CNPJ_INTERMEDIADOR esta preenchido.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.core.fiscal.dados import DadosNota
from app.core.pagamento_regras import numero_nota_fiscal

log = logging.getLogger("entregafood.fiscal")

AUTORIZADA = "autorizada"
REJEITADA = "rejeitada"
CANCELADA = "cancelada"

URLS_FOCUS = {"homologacao": "https://homologacao.focusnfe.com.br/v2", "producao": "https://api.focusnfe.com.br/v2"}

# Codigos de forma de pagamento da NFC-e (tPag). PIX = 17 (pagamento instantaneo).
FORMAS_PAGAMENTO = {"dinheiro": "01", "cartao": "03", "pix": "17"}


class ServicoFiscalIndisponivel(Exception):
    """O servico fiscal nao respondeu (rede, tempo esgotado, 5xx ou 429). Tentar de novo depois."""


@dataclass
class ResultadoEmissao:
    status: str  # AUTORIZADA ou REJEITADA
    numero: str | None = None
    serie: str | None = None
    chave: str | None = None
    protocolo: str | None = None
    url_danfe: str | None = None
    mensagem: str | None = None


def somente_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


# ------------------------------------------------------------------ simulado
class ProvedorSimulado:
    nome = "simulado"
    ambiente = "simulado"

    def emitir(self, dados: DadosNota, referencia: str) -> ResultadoEmissao:
        numero = numero_nota_fiscal(dados.pedido_id, dados.emitida_em.year)
        return ResultadoEmissao(status=AUTORIZADA, numero=numero, mensagem="Nota simulada, sem valor fiscal.")

    def cancelar(self, referencia: str, justificativa: str) -> ResultadoEmissao:
        return ResultadoEmissao(status=CANCELADA, mensagem="Nota simulada cancelada.")


# ------------------------------------------------------------------ Focus NFe
class ProvedorFocusNFe:
    """Cliente da API v2 da Focus NFe para NFC-e (autenticacao HTTP Basic com o token)."""

    nome = "focusnfe"

    def __init__(self, token: str, ambiente: str = "homologacao", base_url: str | None = None, timeout: float = 15.0,
                 ncm: str = "21069090", cfop: str = "5102", situacao_icms: str = "102", cnpj_intermediador: str = "",
                 transporte=None):
        self.token = token
        self.cnpj_intermediador = somente_digitos(cnpj_intermediador)
        self.ambiente = ambiente
        self.base_url = (base_url or URLS_FOCUS[ambiente]).rstrip("/")
        self.timeout = timeout
        self.ncm, self.cfop, self.situacao_icms = ncm, cfop, situacao_icms
        self.transporte = transporte  # httpx.MockTransport nos testes

    # -------------------------------------------------------------- envio
    def _cliente(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, auth=(self.token, ""), timeout=self.timeout, transport=self.transporte)

    def _requisicao(self, metodo: str, caminho: str, **kwargs) -> httpx.Response:
        try:
            with self._cliente() as cliente:
                resposta = cliente.request(metodo, caminho, **kwargs)
        except httpx.TimeoutException as erro:
            raise ServicoFiscalIndisponivel("O serviço fiscal não respondeu a tempo.") from erro
        except httpx.HTTPError as erro:
            raise ServicoFiscalIndisponivel(f"Falha de conexão com o serviço fiscal: {erro.__class__.__name__}.") from erro
        if resposta.status_code == 429:
            raise ServicoFiscalIndisponivel("Limite de requisições do serviço fiscal atingido.")
        if resposta.status_code >= 500:
            raise ServicoFiscalIndisponivel(f"Serviço fiscal fora do ar (HTTP {resposta.status_code}).")
        return resposta

    def montar_requisicao(self, dados: DadosNota) -> dict:
        """Corpo da NFC-e no formato da Focus NFe (campos de doc.focusnfe.com.br/reference/emitir_nfce)."""

        # Taxa de entrega rateada no frete dos itens, proporcional ao valor de cada um;
        # o arredondamento que sobrar vai para o ultimo item, para o total bater.
        frete_total = Decimal(dados.taxa_entrega or 0).quantize(Decimal("0.01"))
        fretes, distribuido = [], Decimal("0.00")
        for indice, item in enumerate(dados.itens):
            if indice == len(dados.itens) - 1:
                parte = frete_total - distribuido
            else:
                parte = (frete_total * item.subtotal / dados.subtotal).quantize(Decimal("0.01")) if dados.subtotal else Decimal("0.00")
            fretes.append(parte)
            distribuido += parte

        itens = []
        for numero, (item, frete) in enumerate(zip(dados.itens, fretes), start=1):
            linha = {
                "numero_item": str(numero), "codigo_produto": f"P{item.produto_id or numero}", "descricao": item.nome[:120],
                "codigo_ncm": self.ncm, "cfop": self.cfop,
                "quantidade_comercial": float(item.quantidade), "quantidade_tributavel": float(item.quantidade),
                "valor_unitario_comercial": float(item.preco_unitario), "valor_unitario_tributavel": float(item.preco_unitario),
                "valor_bruto": float(item.subtotal), "unidade_comercial": "un", "unidade_tributavel": "un",
                "icms_origem": "0", "icms_situacao_tributaria": self.situacao_icms,
            }
            if frete:
                linha["valor_frete"] = float(frete)
            itens.append(linha)
        agora = datetime.now(timezone(timedelta(hours=-3)))
        corpo = {
            "cnpj_emitente": somente_digitos(dados.restaurante_cnpj),
            "data_emissao": agora.isoformat(timespec="seconds"),
            "natureza_operacao": "VENDA AO CONSUMIDOR",
            "presenca_comprador": "4" if dados.tipo_entrega == "delivery" else "1",
            "modalidade_frete": "0" if dados.tipo_entrega == "delivery" else "9",
            "local_destino": "1",
            "nome_destinatario": dados.cliente_nome[:60] if dados.cliente_nome else None,
            "valor_frete": float(frete_total) if frete_total else None,
            "indicador_intermediario": "1" if self.cnpj_intermediador else None,
            "cnpj_intermediario": self.cnpj_intermediador or None,
            "id_cadastro_intermediario": f"pedido-{dados.pedido_id}" if self.cnpj_intermediador else None,
            "items": itens,
            "formas_pagamento": [{"forma_pagamento": FORMAS_PAGAMENTO.get(dados.forma_pagamento, "99"),
                                  "valor_pagamento": float(dados.total)}],
        }
        return {chave: valor for chave, valor in corpo.items() if valor is not None}

    def _resultado(self, corpo: dict) -> ResultadoEmissao:
        status = corpo.get("status")
        if status == "autorizado":
            caminho = corpo.get("caminho_danfe")
            host = self.base_url.rsplit("/v2", 1)[0]
            aviso = " Emitida em contingência offline; será transmitida à SEFAZ pelo serviço." if corpo.get("contingencia_offline") else ""
            return ResultadoEmissao(
                status=AUTORIZADA, numero=str(corpo.get("numero") or ""), serie=str(corpo.get("serie") or "") or None,
                chave=corpo.get("chave_nfe"), protocolo=str(corpo.get("protocolo") or corpo.get("numero_protocolo") or "") or None,
                url_danfe=(host + caminho) if caminho and caminho.startswith("/") else caminho,
                mensagem=(corpo.get("mensagem_sefaz") or "Autorizado o uso da NFC-e.") + aviso,
            )
        if status in ("erro_autorizacao", "denegado"):
            codigo = corpo.get("status_sefaz")
            motivo = corpo.get("mensagem_sefaz") or "Nota recusada pela SEFAZ."
            return ResultadoEmissao(status=REJEITADA, mensagem=f"{codigo} - {motivo}" if codigo else motivo)
        return ResultadoEmissao(status=REJEITADA, mensagem=f"Resposta inesperada do serviço fiscal: status {status!r}.")

    # -------------------------------------------------------------- API publica
    def cancelar(self, referencia: str, justificativa: str) -> ResultadoEmissao:
        """Cancela na SEFAZ (a NFC-e so pode ser cancelada ate 30 minutos depois da emissao)."""

        resposta = self._requisicao("DELETE", f"/nfce/{referencia}", json={"justificativa": justificativa[:255]})
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        if resposta.status_code == 200 and corpo.get("status") == "cancelado":
            return ResultadoEmissao(status=CANCELADA, protocolo=corpo.get("numero_protocolo"),
                                    mensagem=corpo.get("mensagem_sefaz") or "Cancelamento homologado.")
        motivo = corpo.get("mensagem_sefaz") or corpo.get("mensagem") or f"HTTP {resposta.status_code}"
        return ResultadoEmissao(status=REJEITADA, mensagem=f"Cancelamento não aceito: {motivo}")

    def consultar(self, referencia: str) -> ResultadoEmissao:
        resposta = self._requisicao("GET", f"/nfce/{referencia}")
        if resposta.status_code == 404:
            return ResultadoEmissao(status=REJEITADA, mensagem="Nota não encontrada no serviço fiscal.")
        return self._resultado(resposta.json())

    def emitir(self, dados: DadosNota, referencia: str) -> ResultadoEmissao:
        resposta = self._requisicao("POST", "/nfce", params={"ref": referencia}, json=self.montar_requisicao(dados))
        if resposta.status_code == 401:
            return ResultadoEmissao(status=REJEITADA, mensagem="Token do serviço fiscal inválido (HTTP 401). Confira FOCUSNFE_TOKEN.")
        try:
            corpo = resposta.json()
        except ValueError:
            return ResultadoEmissao(status=REJEITADA, mensagem=f"Resposta inválida do serviço fiscal (HTTP {resposta.status_code}).")
        if resposta.status_code in (200, 201):
            return self._resultado(corpo)
        codigo = corpo.get("codigo")
        if codigo in ("already_processed", "pending_operation"):
            # Mesma referencia ja enviada antes (ex.: resposta perdida na rede): vale o que esta no servico.
            return self.consultar(referencia)
        erros = "; ".join(f"{e.get('campo')}: {e.get('mensagem')}" for e in corpo.get("erros") or [] if isinstance(e, dict))
        mensagem = corpo.get("mensagem") or "Requisição recusada pelo serviço fiscal."
        return ResultadoEmissao(status=REJEITADA, mensagem=f"{codigo or resposta.status_code} - {mensagem}" + (f" ({erros})" if erros else ""))


def obter_provedor():
    """Provedor configurado no .env (FISCAL_PROVEDOR)."""

    s = get_settings()
    if s.FISCAL_PROVEDOR == "focusnfe" and s.FOCUSNFE_TOKEN:
        return ProvedorFocusNFe(s.FOCUSNFE_TOKEN, s.FOCUSNFE_AMBIENTE, s.FOCUSNFE_BASE_URL or None, s.FISCAL_TIMEOUT,
                                s.FISCAL_NCM_PADRAO, s.FISCAL_CFOP, s.FISCAL_SITUACAO_ICMS, s.FISCAL_CNPJ_INTERMEDIADOR)
    if s.FISCAL_PROVEDOR == "focusnfe":
        log.warning("FISCAL_PROVEDOR=focusnfe sem FOCUSNFE_TOKEN: usando o provedor simulado.")
    return ProvedorSimulado()
