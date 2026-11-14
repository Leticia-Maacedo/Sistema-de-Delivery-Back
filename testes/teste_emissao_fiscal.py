"""Testes da emissao fiscal - Sprint 4 (modulo app/core/fiscal).

O provedor real (Focus NFe) conversa com um servico falso montado com
httpx.MockTransport, que responde no formato da documentacao da Focus NFe
(doc.focusnfe.com.br): autorizado, erro_autorizacao (rejeicao da SEFAZ),
422 com erros de validacao, 401, 429, 5xx e tempo esgotado.

Cobre: corpo da NFC-e enviado; autorizacao grava numero, chave e DANFCe e
copia o numero para pedido.cupom_fiscal; rejeicao nao tenta de novo sozinha;
servico fora do ar fica pendente e tenta de novo com espera crescente ate o
limite; referencia repetida consulta a nota existente; rotas de situacao, nova
emissao e reprocessamento com as permissoes; download devolve o DANFCe.

Executar:  python -m pytest testes/teste_emissao_fiscal.py -v
"""

import base64
import json
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.controllers import pagamento_controller
from app.core import nota_fiscal, notificacoes_pedido
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.fiscal import emissao
from app.core.fiscal.dados import DadosNota, ItemNota
from app.core.fiscal.provedores import AUTORIZADA, REJEITADA, ProvedorFocusNFe, ProvedorSimulado, ServicoFiscalIndisponivel
from app.core.security import obter_usuario_logado
from app.main import app
from app.models.entrega import Entrega
from app.models.item_pedido import ItemPedido
from app.models.local import Local
from app.models.nota_fiscal import NotaFiscal
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario

TOKEN = "token-de-homologacao"
CARTAO_OK = {"titular": "CLIENTE TESTE", "numero": "5162306219378829", "mes_validade": "05", "ano_validade": "2030", "cvv": "318"}


class FocusFalso:
    """Servico falso no formato da API v2 da Focus NFe."""

    def __init__(self):
        self.modo = "autorizar"
        self.recebidas = []
        self.notas = {}

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        esperado = "Basic " + base64.b64encode(f"{TOKEN}:".encode()).decode()
        if requisicao.headers.get("authorization") != esperado:
            return httpx.Response(401, text="HTTP Basic: Access denied.")
        if requisicao.method == "DELETE":
            ref = requisicao.url.path.rsplit("/", 1)[-1]
            justificativa = json.loads(requisicao.content).get("justificativa", "")
            if ref not in self.notas:
                return httpx.Response(404, json={"codigo": "nfce_nao_encontrada", "mensagem": "Nota fiscal não encontrada"})
            if len(justificativa) < 15:
                return httpx.Response(400, json={"codigo": "requisicao_invalida", "mensagem": "Justificativa deve ter de 15 a 255 caracteres"})
            if self.modo == "prazo_cancelamento":
                return httpx.Response(200, json={"status": "erro_cancelamento", "status_sefaz": "501",
                                                 "mensagem_sefaz": "Rejeição: Prazo de cancelamento superior ao previsto na Legislação"})
            self.notas[ref]["status"] = "cancelado"
            return httpx.Response(200, json={"status": "cancelado", "status_sefaz": "135", "mensagem_sefaz": "Evento registrado e vinculado a NF-e",
                                             "numero_protocolo": "135260000000099"})
        if requisicao.method == "GET":
            ref = requisicao.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=self.notas[ref]) if ref in self.notas else httpx.Response(404, json={"codigo": "nfce_nao_encontrada"})
        ref = requisicao.url.params["ref"]
        corpo = json.loads(requisicao.content)
        self.recebidas.append((ref, corpo))
        if self.modo == "fora_do_ar":
            return httpx.Response(503, text="Service Unavailable")
        if self.modo == "limite":
            return httpx.Response(429, json={"codigo": "limite_requisicoes"})
        if self.modo == "lento":
            raise httpx.ReadTimeout("tempo esgotado", request=requisicao)
        if self.modo == "validacao":
            return httpx.Response(422, json={"codigo": "erro_validacao_schema", "mensagem": "Erro de validação",
                                             "erros": [{"campo": "cnpj_emitente", "mensagem": "CNPJ inválido"}]})
        if ref in self.notas:
            return httpx.Response(422, json={"codigo": "already_processed", "mensagem": "Nota já processada"})
        if self.modo == "rejeitar":
            return httpx.Response(201, json={"ref": ref, "status": "erro_autorizacao", "status_sefaz": "704",
                                             "mensagem_sefaz": "Rejeição: NFC-e com Data-Hora de emissão atrasada"})
        numero = str(100 + len(self.notas))
        self.notas[ref] = {"ref": ref, "status": "autorizado", "status_sefaz": "100", "mensagem_sefaz": "Autorizado o uso da NF-e",
                           "numero": numero, "serie": "1", "chave_nfe": "NFe3526" + numero.zfill(38), "protocolo": "135260000000001",
                           "caminho_danfe": f"/notas_fiscais_consumidor/NFe{numero}.html"}
        return httpx.Response(201, json=self.notas[ref])


def provedor(falso: FocusFalso, token: str = TOKEN) -> ProvedorFocusNFe:
    return ProvedorFocusNFe(token, "homologacao", "https://homologacao.focusnfe.test/v2", transporte=httpx.MockTransport(falso))


def dados(**extra) -> DadosNota:
    base = dict(numero="-", emitida_em=datetime(2026, 11, 14, 12, 0), pedido_id=7, restaurante_nome="Burger",
                restaurante_cnpj="12.345.678/0001-90", restaurante_endereco="Av. Paulista, 1000", cliente_nome="Ana",
                cliente_email="ana@teste.com", forma_pagamento="pix", tipo_entrega="delivery", taxa_entrega=Decimal("5.00"),
                itens=[ItemNota("X-Bacon", 2, Decimal("31.90"), produto_id=3)])
    base.update(extra)
    return DadosNota(**base)


# ------------------------------------------------------------------ provedor (sem banco)
def test_corpo_da_nfce_no_formato_da_focus():
    corpo = provedor(FocusFalso()).montar_requisicao(dados())
    assert corpo["cnpj_emitente"] == "12345678000190"
    assert corpo["presenca_comprador"] == "4" and corpo["modalidade_frete"] == "0" and corpo["local_destino"] == "1"
    (item,) = corpo["items"]
    assert item["codigo_produto"] == "P3" and item["quantidade_comercial"] == 2 and item["valor_bruto"] == 63.8
    assert item["codigo_ncm"] == "21069090" and item["cfop"] == "5102" and item["icms_situacao_tributaria"] == "102"
    assert item["valor_frete"] == 5.0 and corpo["valor_frete"] == 5.0
    assert corpo["formas_pagamento"] == [{"forma_pagamento": "17", "valor_pagamento": 68.8}]
    assert "indicador_intermediario" not in corpo  # sem CNPJ do intermediador configurado


def test_taxa_de_entrega_rateada_no_frete_com_arredondamento_no_ultimo_item():
    nota = dados(taxa_entrega=Decimal("10.00"), itens=[ItemNota("A", 1, Decimal("10.00"), 1), ItemNota("B", 1, Decimal("10.00"), 2),
                                                       ItemNota("C", 1, Decimal("10.00"), 3)])
    corpo = provedor(FocusFalso()).montar_requisicao(nota)
    fretes = [i["valor_frete"] for i in corpo["items"]]
    assert fretes == [3.33, 3.33, 3.34]
    total_itens = sum(Decimal(str(i["valor_bruto"])) + Decimal(str(i["valor_frete"])) for i in corpo["items"])
    assert total_itens == Decimal(str(corpo["formas_pagamento"][0]["valor_pagamento"])) == Decimal("40.00")


def test_entregafood_como_intermediador():
    p = ProvedorFocusNFe(TOKEN, "homologacao", "https://x.test/v2", cnpj_intermediador="98.765.432/0001-10")
    corpo = p.montar_requisicao(dados())
    assert corpo["indicador_intermediario"] == "1" and corpo["cnpj_intermediario"] == "98765432000110"
    assert corpo["id_cadastro_intermediario"] == "pedido-7"


def test_retirada_e_dinheiro():
    corpo = provedor(FocusFalso()).montar_requisicao(dados(tipo_entrega="retirada", forma_pagamento="dinheiro", taxa_entrega=Decimal("0")))
    assert corpo["presenca_comprador"] == "1" and corpo["modalidade_frete"] == "9"
    assert len(corpo["items"]) == 1 and corpo["formas_pagamento"][0]["forma_pagamento"] == "01"


def test_autorizada_devolve_numero_chave_e_danfe():
    r = provedor(FocusFalso()).emitir(dados(), "pedido-7")
    assert r.status == AUTORIZADA and r.numero == "100" and r.serie == "1" and r.chave.startswith("NFe")
    assert r.url_danfe == "https://homologacao.focusnfe.test/notas_fiscais_consumidor/NFe100.html"


def test_rejeicao_da_sefaz_traz_codigo_e_motivo():
    falso = FocusFalso(); falso.modo = "rejeitar"
    r = provedor(falso).emitir(dados(), "pedido-7")
    assert r.status == REJEITADA and r.mensagem.startswith("704 - Rejeição")


def test_erro_de_validacao_lista_os_campos():
    falso = FocusFalso(); falso.modo = "validacao"
    r = provedor(falso).emitir(dados(), "pedido-7")
    assert r.status == REJEITADA and "erro_validacao_schema" in r.mensagem and "cnpj_emitente: CNPJ inválido" in r.mensagem


def test_token_errado_e_rejeicao_de_configuracao():
    r = provedor(FocusFalso(), token="outro").emitir(dados(), "pedido-7")
    assert r.status == REJEITADA and "401" in r.mensagem


@pytest.mark.parametrize("modo", ["fora_do_ar", "limite", "lento"])
def test_servico_fora_do_ar_limite_e_tempo_esgotado_sao_indisponibilidade(modo):
    falso = FocusFalso(); falso.modo = modo
    with pytest.raises(ServicoFiscalIndisponivel):
        provedor(falso).emitir(dados(), "pedido-7")


def test_referencia_repetida_consulta_a_nota_ja_autorizada():
    falso = FocusFalso()
    p = provedor(falso)
    primeira = p.emitir(dados(), "pedido-7")
    segunda = p.emitir(dados(), "pedido-7")  # ex.: resposta anterior perdida na rede
    assert segunda.status == AUTORIZADA and segunda.numero == primeira.numero and len(falso.notas) == 1


def test_cancelamento_na_sefaz():
    falso = FocusFalso()
    p = provedor(falso)
    p.emitir(dados(), "pedido-7")
    r = p.cancelar("pedido-7", "Pedido cancelado antes da entrega ao consumidor.")
    assert r.status == "cancelada" and falso.notas["pedido-7"]["status"] == "cancelado"


def test_cancelamento_fora_do_prazo_e_recusado():
    falso = FocusFalso()
    p = provedor(falso)
    p.emitir(dados(), "pedido-7")
    falso.modo = "prazo_cancelamento"
    r = p.cancelar("pedido-7", "Pedido cancelado antes da entrega ao consumidor.")
    assert r.status == REJEITADA and "Prazo de cancelamento" in r.mensagem


def test_simulado_numera_como_antes():
    r = ProvedorSimulado().emitir(dados(), "pedido-7")
    assert r.status == AUTORIZADA and r.numero == "NF-2026-000007"


# ------------------------------------------------------------------ banco e rotas
@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("ASAAS_API_KEY", "")
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    for modulo in (nota_fiscal, pagamento_controller, notificacoes_pedido):
        monkeypatch.setattr(modulo, "SessionLocal", Sessao)
    falso = FocusFalso()
    monkeypatch.setattr(emissao, "obter_provedor", lambda: provedor(falso))
    logado = {"id": None}

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    def usuario_de_teste():
        with Sessao() as db:
            u = db.get(Usuario, logado["id"]); db.expunge(u); return u

    app.dependency_overrides[get_db] = db_de_teste
    app.dependency_overrides[obter_usuario_logado] = usuario_de_teste
    with Sessao() as db:
        agora = datetime.now()
        pessoas = {k: Usuario(nome=k.title(), email=f"{k}@teste.com", tipo=t, criado_em=agora)
                   for k, t in (("cliente", "cliente"), ("dono", "restaurante"), ("outro_dono", "restaurante"), ("admin", "admin"))}
        db.add_all(pessoas.values()); db.flush()
        local = Local(usuario_id=pessoas["dono"].id, endereco="Av. Paulista, 1000", tipo="restaurante",
                      latitude=Decimal("-23.56"), longitude=Decimal("-46.65"), criado_em=agora)
        db.add(local); db.flush()
        rest = Restaurante(local_id=local.id, usuario_id=pessoas["dono"].id, nome_fantasia="Burger", cnpj="12.345.678/0001-90",
                           status_aprovacao="aprovado", taxa_entrega_km=Decimal("2.00"), criado_em=agora)
        db.add(rest); db.flush()
        prod = Produto(restaurante_id=rest.id, nome="X-Bacon", preco=Decimal("31.90"), disponivel=True)
        db.add(prod); db.commit()
        ids = {k: v.id for k, v in pessoas.items()} | {"restaurante": rest.id, "produto": prod.id}

    def novo_pedido():
        with Sessao() as db:
            pedido = Pedido(cliente_id=ids["cliente"], restaurante_id=ids["restaurante"], status="aguardando_aceite",
                            tipo_entrega="delivery", forma_pagamento="cartao", valor_total=Decimal("68.80"),
                            taxa_entrega=Decimal("5.00"), criado_em=datetime.now())
            db.add(pedido); db.flush()
            db.add(ItemPedido(pedido_id=pedido.id, produto_id=ids["produto"], quantidade=2, preco_unitario=Decimal("31.90")))
            db.add(Entrega.nova(pedido.id)); db.commit()
            return pedido.id

    def pagar(pedido_id):
        logado["id"] = ids["cliente"]
        api.put(f"/pagamentos/pedidos/{pedido_id}/metodo", json={"metodo": "cartao"})
        return api.post("/pagamentos/cartao", json={"pedido_id": pedido_id, "cartao": CARTAO_OK})

    def como(quem):
        logado["id"] = ids[quem]
        return api

    def ler(pedido_id):
        with Sessao() as db:
            return db.query(NotaFiscal).filter_by(pedido_id=pedido_id).first(), db.get(Pedido, pedido_id)

    api = TestClient(app)
    yield {"falso": falso, "novo_pedido": novo_pedido, "pagar": pagar, "como": como, "ler": ler, "Sessao": Sessao}
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_pagamento_aprovado_emite_a_nfce(ambiente):
    pid = ambiente["novo_pedido"]()
    r = ambiente["pagar"](pid)
    assert r.status_code == 201 and r.json()["status"] == "aprovado" and r.json()["nota_fiscal"] == "100"
    nota, pedido = ambiente["ler"](pid)
    assert nota.status == "autorizada" and nota.provedor == "focusnfe" and nota.ambiente == "homologacao"
    assert nota.referencia == f"pedido-{pid}" and nota.chave and nota.tentativas == 1 and pedido.cupom_fiscal == "100"
    ref, corpo = ambiente["falso"].recebidas[0]
    assert ref == f"pedido-{pid}" and corpo["formas_pagamento"][0]["forma_pagamento"] == "03"


def test_rejeitada_nao_bloqueia_o_pagamento_e_nao_tenta_sozinha(ambiente):
    ambiente["falso"].modo = "rejeitar"
    pid = ambiente["novo_pedido"]()
    r = ambiente["pagar"](pid)
    assert r.status_code == 201 and r.json()["status"] == "aprovado" and r.json()["nota_fiscal"] is None
    nota, pedido = ambiente["ler"](pid)
    assert nota.status == "rejeitada" and nota.mensagem.startswith("704") and nota.proxima_tentativa_em is None
    assert pedido.cupom_fiscal is None
    s = ambiente["como"]("cliente").get(f"/notas-fiscais/pedidos/{pid}").json()
    assert s["status"] == "rejeitada" and "Data-Hora" in s["mensagem"]
    assert ambiente["como"]("cliente").get(f"/pagamentos/pedidos/{pid}/nota-fiscal").status_code == 409


def test_restaurante_emite_de_novo_depois_da_correcao(ambiente):
    ambiente["falso"].modo = "rejeitar"
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    ambiente["falso"].modo = "autorizar"
    assert ambiente["como"]("cliente").post(f"/notas-fiscais/pedidos/{pid}/emitir").status_code == 403
    assert ambiente["como"]("outro_dono").post(f"/notas-fiscais/pedidos/{pid}/emitir").status_code == 403
    r = ambiente["como"]("dono").post(f"/notas-fiscais/pedidos/{pid}/emitir")
    assert r.status_code == 200 and r.json()["status"] == "autorizada" and r.json()["tentativas"] == 2
    assert ambiente["como"]("dono").post(f"/notas-fiscais/pedidos/{pid}/emitir").status_code == 409


def test_servico_fora_do_ar_fica_pendente_e_tenta_de_novo(ambiente):
    ambiente["falso"].modo = "fora_do_ar"
    pid = ambiente["novo_pedido"]()
    assert ambiente["pagar"](pid).json()["status"] == "aprovado"
    nota, _ = ambiente["ler"](pid)
    assert nota.status == "pendente_reenvio" and nota.tentativas == 1 and "Nova tentativa em 1 min" in nota.mensagem
    ambiente["falso"].modo = "autorizar"
    with ambiente["Sessao"]() as db:  # antes da hora: nada a fazer
        assert emissao.reprocessar_pendentes(db) == []
        depois = emissao.reprocessar_pendentes(db, agora=datetime.now() + timedelta(minutes=2))
        assert [n.status for n in depois] == ["autorizada"]


def test_espera_crescente_e_limite_de_tentativas(ambiente):
    ambiente["falso"].modo = "fora_do_ar"
    pid = ambiente["novo_pedido"]()
    ambiente["pagar"](pid)
    esperas, agora = [], datetime.now()
    with ambiente["Sessao"]() as db:
        for _ in range(emissao.MAX_TENTATIVAS - 1):
            nota = db.query(NotaFiscal).filter_by(pedido_id=pid).one()
            if nota.status == "falhou":
                break
            esperas.append(round((nota.proxima_tentativa_em - agora).total_seconds() / 60))
            agora = nota.proxima_tentativa_em + timedelta(seconds=1)
            emissao.reprocessar_pendentes(db, agora=agora)
        nota = db.query(NotaFiscal).filter_by(pedido_id=pid).one()
    assert esperas[:3] == [1, 5, 15]
    assert nota.status == "falhou" and nota.tentativas == emissao.MAX_TENTATIVAS and "emita manualmente" in nota.mensagem


def test_situacao_tenta_de_novo_quando_a_hora_chegou(ambiente):
    ambiente["falso"].modo = "lento"
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    with ambiente["Sessao"]() as db:
        nota = db.query(NotaFiscal).filter_by(pedido_id=pid).one()
        nota.proxima_tentativa_em = datetime.now() - timedelta(seconds=1)
        db.commit()
    ambiente["falso"].modo = "autorizar"
    r = ambiente["como"]("cliente").get(f"/notas-fiscais/pedidos/{pid}")
    assert r.json()["status"] == "autorizada"


def test_reprocessar_e_so_do_admin(ambiente):
    assert ambiente["como"]("dono").post("/notas-fiscais/reprocessar").status_code == 403
    assert ambiente["como"]("admin").post("/notas-fiscais/reprocessar").json() == []


def test_download_redireciona_para_o_danfce(ambiente):
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    r = ambiente["como"]("cliente").get(f"/pagamentos/pedidos/{pid}/nota-fiscal", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith(".html")


def test_situacao_de_pedido_sem_pagamento_e_404(ambiente):
    pid = ambiente["novo_pedido"]()
    assert ambiente["como"]("cliente").get(f"/notas-fiscais/pedidos/{pid}").status_code == 404


def test_pedido_cancelado_cancela_a_nota(ambiente):
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    r = ambiente["como"]("cliente").post(f"/pedidos/{pid}/cancelar")
    assert r.status_code == 200, r.text
    nota, _ = ambiente["ler"](pid)
    assert nota.status == "cancelada" and ambiente["falso"].notas[f"pedido-{pid}"]["status"] == "cancelado"


def test_cancelamento_recusado_pela_sefaz_nao_impede_o_pedido(ambiente):
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    ambiente["falso"].modo = "prazo_cancelamento"
    assert ambiente["como"]("cliente").post(f"/pedidos/{pid}/cancelar").status_code == 200
    nota, pedido = ambiente["ler"](pid)
    assert pedido.status == "cancelado" and nota.status == "autorizada" and "Prazo de cancelamento" in nota.mensagem


def test_pedido_cancelado_com_nota_pendente_para_de_tentar(ambiente):
    ambiente["falso"].modo = "fora_do_ar"
    pid = ambiente["novo_pedido"](); ambiente["pagar"](pid)
    ambiente["como"]("cliente").post(f"/pedidos/{pid}/cancelar")
    nota, _ = ambiente["ler"](pid)
    assert nota.status == "cancelada" and nota.proxima_tentativa_em is None
