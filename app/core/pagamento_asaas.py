"""Cliente HTTP do Asaas (gateway de pagamento real, backlog 19).

Documentacao: https://docs.asaas.com (ambiente sandbox:
https://api-sandbox.asaas.com/v3). A chave vem de `ASAAS_API_KEY` no .env
e vai no cabecalho `access_token`.

Fluxo usado:
    1. Cliente (customer): busca pelo CPF ou cria (POST /customers).
    2. Cobranca (POST /payments):
         - CREDIT_CARD: o Asaas cobra na hora; "CONFIRMED" = aprovado.
           Cartao recusado volta HTTP 400 com a mensagem em errors[].
         - PIX: depois busca o QR Code em GET /payments/{id}/pixQrCode.
    3. Consulta (GET /payments/{id}) para atualizar o status do PIX.

Os dados do cartao sao repassados ao Asaas e nao ficam em lugar nenhum
do EntregaFood (nem banco, nem log).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import httpx

from app.core.pagamento_cartao import ResultadoPagamento
from app.core.pagamento_regras import APROVADO, RECUSADO, somente_digitos, status_do_asaas

TIMEOUT_SEGUNDOS = 20.0


class AsaasErro(Exception):
    """Erro devolvido pelo Asaas (ex.: cartao recusado, CPF invalido)."""

    def __init__(self, mensagem: str, status_http: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_http = status_http


class AsaasIndisponivel(Exception):
    """Nao foi possivel falar com o Asaas (rede, timeout, chave errada)."""


@dataclass
class Pagador:
    """Quem paga a cobranca."""

    nome: str
    cpf: str
    email: str | None = None
    telefone: str | None = None
    cep: str | None = None
    numero_endereco: str | None = None
    referencia: str | None = None  # id do usuario no EntregaFood


@dataclass
class DadosCartao:
    titular: str
    numero: str
    mes_validade: str
    ano_validade: str
    cvv: str


def _mensagem_de_erro(resposta: httpx.Response) -> str:
    try:
        erros = resposta.json().get("errors") or []
    except ValueError:
        erros = []

    textos = [e.get("description") for e in erros if e.get("description")]
    return " ".join(textos) or f"Erro {resposta.status_code} no Asaas."


class ClienteAsaas:
    """Chamadas a API v3 do Asaas."""

    def __init__(self, api_key: str, base_url: str, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
        self._cabecalhos = {
            "access_token": api_key,
            "Content-Type": "application/json",
            "User-Agent": "EntregaFood/1.0",
        }

    def _chamar(self, metodo: str, caminho: str, **kwargs) -> dict:
        try:
            resposta = self._http.request(
                metodo,
                f"{self.base_url}{caminho}",
                headers=self._cabecalhos,
                **kwargs,
            )
        except httpx.HTTPError as erro:
            raise AsaasIndisponivel(f"Falha ao conectar no Asaas: {erro}") from erro

        if resposta.status_code in (401, 403):
            raise AsaasIndisponivel("Chave do Asaas invalida ou sem permissao.")

        if resposta.status_code >= 500:
            raise AsaasIndisponivel(f"Asaas fora do ar (HTTP {resposta.status_code}).")

        if resposta.status_code >= 400:
            raise AsaasErro(_mensagem_de_erro(resposta), resposta.status_code)

        return resposta.json() if resposta.content else {}

    # ------------------------------------------------------------ cliente

    def obter_cliente(self, pagador: Pagador) -> str:
        """Id do customer no Asaas para o CPF; cria se nao existir."""

        cpf = somente_digitos(pagador.cpf)
        existentes = self._chamar("GET", "/customers", params={"cpfCnpj": cpf})

        for cliente in existentes.get("data") or []:
            if not cliente.get("deleted"):
                return cliente["id"]

        corpo = {
            "name": pagador.nome,
            "cpfCnpj": cpf,
            "email": pagador.email,
            "mobilePhone": somente_digitos(pagador.telefone) or None,
            "externalReference": pagador.referencia,
            "notificationDisabled": True,
        }
        criado = self._chamar("POST", "/customers", json={k: v for k, v in corpo.items() if v})

        return criado["id"]

    # ------------------------------------------------------------ cobrancas

    def cobrar_cartao(
        self,
        *,
        pagador: Pagador,
        cartao: DadosCartao,
        valor: Decimal,
        descricao: str,
        referencia: str,
        ip_remoto: str | None,
    ) -> ResultadoPagamento:
        """Cobranca no cartao de credito. Recusa vira status "recusado"."""

        cliente_id = self.obter_cliente(pagador)
        corpo = {
            "customer": cliente_id,
            "billingType": "CREDIT_CARD",
            "value": float(valor),
            "dueDate": date.today().isoformat(),
            "description": descricao,
            "externalReference": referencia,
            "creditCard": {
                "holderName": cartao.titular,
                "number": cartao.numero,
                "expiryMonth": cartao.mes_validade,
                "expiryYear": cartao.ano_validade,
                "ccv": cartao.cvv,
            },
            "creditCardHolderInfo": {
                "name": pagador.nome,
                "email": pagador.email,
                "cpfCnpj": somente_digitos(pagador.cpf),
                "postalCode": somente_digitos(pagador.cep),
                "addressNumber": pagador.numero_endereco,
                "phone": somente_digitos(pagador.telefone),
            },
            "remoteIp": ip_remoto or "127.0.0.1",
        }

        try:
            cobranca = self._chamar("POST", "/payments", json=corpo)
        except AsaasErro as erro:
            # Cartao recusado: o Asaas nao cria a cobranca e explica o motivo.
            return ResultadoPagamento(
                aprovado=False,
                status=RECUSADO,
                transacao_externa_id=None,
                mensagem=erro.mensagem,
            )

        status = status_do_asaas(cobranca.get("status"))

        return ResultadoPagamento(
            aprovado=status == APROVADO,
            status=status,
            transacao_externa_id=cobranca.get("id"),
            mensagem="Pagamento aprovado." if status == APROVADO else "Pagamento em analise.",
        )

    def criar_pix(
        self,
        *,
        pagador: Pagador,
        valor: Decimal,
        descricao: str,
        referencia: str,
    ) -> ResultadoPagamento:
        """Cobranca PIX com QR Code e copia e cola."""

        cliente_id = self.obter_cliente(pagador)
        cobranca = self._chamar(
            "POST",
            "/payments",
            json={
                "customer": cliente_id,
                "billingType": "PIX",
                "value": float(valor),
                "dueDate": date.today().isoformat(),
                "description": descricao,
                "externalReference": referencia,
            },
        )
        qr = self._chamar("GET", f"/payments/{cobranca['id']}/pixQrCode")

        expira = None
        if qr.get("expirationDate"):
            try:
                expira = datetime.fromisoformat(qr["expirationDate"])
            except ValueError:
                expira = None

        imagem = qr.get("encodedImage")

        return ResultadoPagamento(
            aprovado=False,
            status=status_do_asaas(cobranca.get("status")),
            transacao_externa_id=cobranca["id"],
            mensagem="PIX gerado. Aguardando pagamento.",
            pix_copia_cola=qr.get("payload"),
            pix_qrcode=f"data:image/png;base64,{imagem}" if imagem else None,
            pix_expira_em=expira,
        )

    def consultar_status(self, cobranca_id: str) -> str:
        """Status atual da cobranca, ja no padrao do EntregaFood."""

        cobranca = self._chamar("GET", f"/payments/{cobranca_id}")

        return status_do_asaas(cobranca.get("status"))

    def cancelar(self, cobranca_id: str) -> None:
        """Remove uma cobranca ainda nao paga (ex.: cliente trocou o metodo)."""

        self._chamar("DELETE", f"/payments/{cobranca_id}")

    def confirmar_recebimento_em_dinheiro(self, cobranca_id: str, valor: Decimal) -> None:
        """Marca a cobranca como recebida. So usado no sandbox para simular o PIX pago."""

        self._chamar(
            "POST",
            f"/payments/{cobranca_id}/receiveInCash",
            json={
                "paymentDate": date.today().isoformat(),
                "value": float(valor),
                "notifyCustomer": False,
            },
        )
