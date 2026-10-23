"""Testes do pagamento e da nota fiscal - Sprint 3 (backlog 18, 19 e 22).

Cobre, sem banco e sem internet:
    - regras do pagamento (aceite, status do Asaas, CPF, numero da nota);
    - tipo unico do metodo (cartao, pix, dinheiro) nas duas rotas;
    - gateway simulado (cartao aprovado/recusado e PIX);
    - cliente do Asaas com respostas falsas (httpx.MockTransport);
    - escolha do gateway pela ASAAS_API_KEY;
    - PDF da nota fiscal e e-mail sem SMTP configurado.

Executar:  python -m pytest testes/teste_pagamento.py -v
"""

import json
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.core import email, pagamento_gateway
from app.core import pagamento_regras as regras
from app.core.config import get_settings
from app.core.nota_fiscal import DadosNota, ItemNota, gerar_pdf
from app.core.pagamento_asaas import AsaasIndisponivel, ClienteAsaas, DadosCartao, Pagador
from app.core.pagamento_cartao import (
    CARTOES_RECUSADOS,
    criar_pix_simulado,
    processar_pagamento_cartao,
)
from app.schemas.pagamento import EscolhaPagamentoIn, PagamentoCartaoIn
from app.schemas.pedido import PedidoCriarIn


@pytest.fixture
def sem_asaas(monkeypatch):
    monkeypatch.setenv("ASAAS_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def com_asaas(monkeypatch):
    monkeypatch.setenv("ASAAS_API_KEY", "chave-de-teste")
    monkeypatch.setenv("ASAAS_BASE_URL", "https://api-sandbox.asaas.com/v3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ------------------------------------------------------------------ regras


def test_cartao_e_pix_so_liberam_aceite_aprovados():
    assert regras.permite_aceite("cartao", regras.APROVADO)
    assert regras.permite_aceite("pix", regras.APROVADO)
    assert not regras.permite_aceite("cartao", regras.RECUSADO)
    assert not regras.permite_aceite("pix", regras.PENDENTE)


def test_dinheiro_libera_aceite_a_receber():
    assert regras.permite_aceite("dinheiro", regras.A_RECEBER)
    assert not regras.permite_aceite("cartao", regras.A_RECEBER)


def test_pode_refazer_menos_quando_aprovado():
    assert regras.pode_refazer(None)
    assert regras.pode_refazer(regras.RECUSADO)
    assert regras.pode_refazer(regras.PENDENTE)
    assert not regras.pode_refazer(regras.APROVADO)


@pytest.mark.parametrize(
    "asaas, esperado",
    [
        ("CONFIRMED", regras.APROVADO),
        ("RECEIVED", regras.APROVADO),
        ("RECEIVED_IN_CASH", regras.APROVADO),
        ("PENDING", regras.PENDENTE),
        ("OVERDUE", regras.EXPIRADO),
        ("REFUNDED", regras.ESTORNADO),
        ("QUALQUER", regras.PENDENTE),
        (None, regras.PENDENTE),
    ],
)
def test_status_do_asaas(asaas, esperado):
    assert regras.status_do_asaas(asaas) == esperado


def test_cpf_valido():
    assert regras.cpf_valido("529.982.247-25")
    assert regras.cpf_valido("52998224725")
    assert not regras.cpf_valido("529.982.247-24")
    assert not regras.cpf_valido("111.111.111-11")
    assert not regras.cpf_valido(None)


def test_numero_da_nota():
    assert regras.numero_nota_fiscal(42, 2026) == "NF-2026-000042"


def test_rotulos():
    assert regras.rotulo(regras.A_RECEBER) == "Pagar na entrega"
    assert regras.rotulo("desconhecido") == "desconhecido"


# ------------------------------------------------------------------ schemas


@pytest.mark.parametrize("metodo", ["cartao", "pix", "dinheiro"])
def test_metodos_aceitos_nas_duas_rotas(metodo):
    assert EscolhaPagamentoIn(metodo=metodo).metodo == metodo
    assert PedidoCriarIn(forma_pagamento=metodo).forma_pagamento == metodo


@pytest.mark.parametrize("metodo", ["boleto", "CARTAO", "", "cheque"])
def test_metodo_invalido_e_recusado(metodo):
    with pytest.raises(ValidationError):
        EscolhaPagamentoIn(metodo=metodo)
    with pytest.raises(ValidationError):
        PedidoCriarIn(forma_pagamento=metodo)


def test_cartao_com_numero_invalido_e_recusado():
    with pytest.raises(ValidationError):
        PagamentoCartaoIn(
            pedido_id=1,
            cartao={"titular": "Fulano", "numero": "1234", "mes_validade": "12",
                    "ano_validade": "2030", "cvv": "123"},
        )


def test_cartao_sem_dados_continua_valido_para_o_simulado():
    assert PagamentoCartaoIn(pedido_id=1).cartao is None


# ------------------------------------------------------------------ simulado


def test_simulado_aprova_valor_positivo():
    resultado = processar_pagamento_cartao(valor=Decimal("50.00"))
    assert resultado.aprovado
    assert resultado.status == regras.APROVADO
    assert resultado.transacao_externa_id.startswith("SIM-")


def test_simulado_recusa_cartao_de_teste_de_recusa():
    numero = sorted(CARTOES_RECUSADOS)[0]
    resultado = processar_pagamento_cartao(valor=Decimal("50.00"), numero_cartao=numero)
    assert not resultado.aprovado
    assert resultado.status == regras.RECUSADO
    assert "nao autorizada" in resultado.mensagem


def test_simulado_recusa_valor_zero():
    assert processar_pagamento_cartao(valor=Decimal("0.00")).status == regras.RECUSADO


def test_pix_simulado_fica_pendente_com_copia_e_cola():
    resultado = criar_pix_simulado(valor=Decimal("37.90"), pedido_id=7)
    assert resultado.status == regras.PENDENTE
    assert resultado.pix_copia_cola.startswith("000201")
    assert resultado.pix_expira_em > datetime.now()


# ------------------------------------------------------------------ gateway


def test_sem_chave_usa_simulado(sem_asaas):
    assert not pagamento_gateway.asaas_ativo()
    assert pagamento_gateway.nome_gateway() == "simulado"
    resultado = pagamento_gateway.cobrar_cartao(
        valor=Decimal("10.00"), pagador=Pagador(nome="A", cpf=""), cartao=None,
        descricao="x", referencia="pedido-1",
    )
    assert resultado.status == regras.APROVADO
    assert pagamento_gateway.consultar_status(resultado.transacao_externa_id) is None


def test_com_chave_usa_asaas(com_asaas):
    assert pagamento_gateway.asaas_ativo()
    assert pagamento_gateway.nome_gateway("pay_123") == "asaas"
    # Pagamentos antigos do simulado continuam sendo do simulado.
    assert pagamento_gateway.nome_gateway("SIM-abc") == "simulado"
    assert pagamento_gateway.simulacao_permitida()


# ------------------------------------------------------------------ Asaas (respostas falsas)


PAGADOR = Pagador(nome="Cliente Teste", cpf="529.982.247-25", email="c@teste.com",
                  telefone="11999998888", cep="01310-100", numero_endereco="100")
CARTAO = DadosCartao(titular="CLIENTE TESTE", numero="5162306219378829",
                     mes_validade="05", ano_validade="2030", cvv="318")


def cliente_falso(respostas):
    """ClienteAsaas que responde pela tabela {(metodo, caminho): (status, json)}."""

    chamadas = []

    def tratar(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        caminho = requisicao.url.path.replace("/v3", "", 1)
        codigo, corpo = respostas[(requisicao.method, caminho)]
        return httpx.Response(codigo, json=corpo)

    http = httpx.Client(transport=httpx.MockTransport(tratar))
    return ClienteAsaas("chave", "https://api-sandbox.asaas.com/v3", http=http), chamadas


def test_asaas_cartao_aprovado_e_cartao_nao_vai_para_lugar_nenhum_alem_do_asaas():
    cliente, chamadas = cliente_falso({
        ("GET", "/customers"): (200, {"data": []}),
        ("POST", "/customers"): (200, {"id": "cus_1"}),
        ("POST", "/payments"): (200, {"id": "pay_1", "status": "CONFIRMED"}),
    })
    resultado = cliente.cobrar_cartao(pagador=PAGADOR, cartao=CARTAO, valor=Decimal("45.50"),
                                      descricao="Pedido 1", referencia="pedido-1", ip_remoto="1.2.3.4")

    assert resultado.status == regras.APROVADO
    assert resultado.transacao_externa_id == "pay_1"
    cobranca = json.loads(chamadas[-1].content)
    assert cobranca["billingType"] == "CREDIT_CARD"
    assert cobranca["customer"] == "cus_1"
    assert cobranca["creditCardHolderInfo"]["cpfCnpj"] == "52998224725"
    assert chamadas[-1].headers["access_token"] == "chave"


def test_asaas_cartao_recusado_vira_status_recusado_com_motivo():
    cliente, _ = cliente_falso({
        ("GET", "/customers"): (200, {"data": [{"id": "cus_1", "deleted": False}]}),
        ("POST", "/payments"): (400, {"errors": [{"code": "invalid_creditCard",
                                                  "description": "Transação não autorizada."}]}),
    })
    resultado = cliente.cobrar_cartao(pagador=PAGADOR, cartao=CARTAO, valor=Decimal("45.50"),
                                      descricao="Pedido 1", referencia="pedido-1", ip_remoto=None)

    assert resultado.status == regras.RECUSADO
    assert not resultado.aprovado
    assert resultado.mensagem == "Transação não autorizada."


def test_asaas_pix_devolve_qrcode_e_copia_e_cola():
    cliente, _ = cliente_falso({
        ("GET", "/customers"): (200, {"data": [{"id": "cus_1"}]}),
        ("POST", "/payments"): (200, {"id": "pay_pix", "status": "PENDING"}),
        ("GET", "/payments/pay_pix/pixQrCode"): (200, {
            "encodedImage": "iVBORw0KGgo=", "payload": "00020101021226...",
            "expirationDate": "2026-10-27 23:59:59",
        }),
    })
    resultado = cliente.criar_pix(pagador=PAGADOR, valor=Decimal("30.00"),
                                  descricao="Pedido 2", referencia="pedido-2")

    assert resultado.status == regras.PENDENTE
    assert resultado.transacao_externa_id == "pay_pix"
    assert resultado.pix_copia_cola == "00020101021226..."
    assert resultado.pix_qrcode == "data:image/png;base64,iVBORw0KGgo="
    assert resultado.pix_expira_em == datetime(2026, 10, 27, 23, 59, 59)


def test_asaas_consulta_pix_pago():
    cliente, _ = cliente_falso({("GET", "/payments/pay_pix"): (200, {"status": "RECEIVED"})})
    assert cliente.consultar_status("pay_pix") == regras.APROVADO


def test_asaas_chave_invalida_e_indisponivel():
    cliente, _ = cliente_falso({("GET", "/payments/x"): (401, {})})
    with pytest.raises(AsaasIndisponivel):
        cliente.consultar_status("x")


# ------------------------------------------------------------------ nota fiscal


def nota_exemplo() -> DadosNota:
    return DadosNota(
        numero="NF-2026-000001",
        emitida_em=datetime(2026, 10, 22, 20, 30),
        pedido_id=1,
        restaurante_nome="Pizzaria São João",
        restaurante_cnpj="12.345.678/0001-90",
        restaurante_endereco="Rua das Flores, 10",
        cliente_nome="José da Silva",
        cliente_email="jose@teste.com",
        forma_pagamento="pix",
        tipo_entrega="delivery",
        taxa_entrega=Decimal("5.50"),
        itens=[
            ItemNota("Pizza Calabresa", 2, Decimal("39.90")),
            ItemNota("Refrigerante 2L", 1, Decimal("12.00")),
        ],
    )


def test_totais_da_nota_usam_o_preco_do_pedido():
    nota = nota_exemplo()
    assert nota.subtotal == Decimal("91.80")
    assert nota.total == Decimal("97.30")


def test_pdf_da_nota_e_gerado():
    pdf = gerar_pdf(nota_exemplo())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_email_sem_smtp_nao_quebra(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
    try:
        assert email.enviar(para="a@b.com", assunto="x", texto="y", anexo=b"%PDF") is False
    finally:
        get_settings.cache_clear()


def test_email_leva_o_pdf_em_anexo():
    mensagem = email.montar_mensagem(remetente="r@x.com", para="a@b.com", assunto="NF",
                                     texto="segue", anexo=b"%PDF-1.4", nome_anexo="NF-1.pdf")
    anexos = list(mensagem.iter_attachments())
    assert len(anexos) == 1
    assert anexos[0].get_filename() == "NF-1.pdf"
    assert anexos[0].get_content_type() == "application/pdf"
