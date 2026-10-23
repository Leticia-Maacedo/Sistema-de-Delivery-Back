"""Nota fiscal (cupom) SIMULADA em PDF - backlog 22.

Quando o pagamento e aprovado:
    1. `emitir_nota` grava o numero da nota em `pedido.cupom_fiscal`.
    2. `enviar_nota_por_email` (em segundo plano, BackgroundTasks) gera o
       PDF e manda ao cliente por e-mail (app/core/email.py).

O PDF e gerado de novo a cada download a partir do banco (itens com o
preco do momento do pedido), entao nenhum arquivo fica guardado.
A nota e simulada: nao tem valor fiscal e nao passa pela SEFAZ.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from fastapi import BackgroundTasks
from fpdf import FPDF
from sqlalchemy.orm import Session

from app.core import email
from app.core.database import SessionLocal
from app.core.pagamento_regras import numero_nota_fiscal

log = logging.getLogger("entregafood.nota_fiscal")

METODOS = {"cartao": "Cartão de crédito", "pix": "PIX", "dinheiro": "Dinheiro na entrega"}
ENTREGAS = {"delivery": "Entrega no endereço", "retirada": "Retirada no balcão"}


@dataclass
class ItemNota:
    nome: str
    quantidade: int
    preco_unitario: Decimal

    @property
    def subtotal(self) -> Decimal:
        return (self.preco_unitario * self.quantidade).quantize(Decimal("0.01"))


@dataclass
class DadosNota:
    """Tudo o que aparece na nota (sem depender do banco, para testar)."""

    numero: str
    emitida_em: datetime
    pedido_id: int
    restaurante_nome: str
    restaurante_cnpj: str
    restaurante_endereco: str | None
    cliente_nome: str
    cliente_email: str | None
    forma_pagamento: str
    tipo_entrega: str
    taxa_entrega: Decimal
    transacao: str | None = None
    itens: list[ItemNota] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.itens), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.taxa_entrega


def _reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _latin1(texto: str | None) -> str:
    """As fontes padrao do PDF so tem Latin-1 (acentos do portugues ok)."""

    return (texto or "").encode("latin-1", "replace").decode("latin-1")


def gerar_pdf(dados: DadosNota) -> bytes:
    """Monta o PDF da nota e devolve os bytes."""

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title(_latin1(f"Nota fiscal {dados.numero}"))
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    def linha(texto: str, tamanho: int = 10, estilo: str = "", alinhamento: str = "L") -> None:
        pdf.set_font("helvetica", estilo, tamanho)
        pdf.cell(largura, 6, _latin1(texto), new_x="LMARGIN", new_y="NEXT", align=alinhamento)

    linha("EntregaFood", 18, "B", "C")
    linha("NOTA FISCAL DE CONSUMIDOR (SIMULADA)", 11, "B", "C")
    linha("Documento sem valor fiscal - projeto acadêmico", 8, "I", "C")
    pdf.ln(4)

    linha(f"Nota: {dados.numero}", 11, "B")
    linha(f"Emissão: {dados.emitida_em:%d/%m/%Y %H:%M}")
    linha(f"Pedido: #{dados.pedido_id}")
    pdf.ln(2)

    linha("EMITENTE", 10, "B")
    linha(dados.restaurante_nome)
    linha(f"CNPJ: {dados.restaurante_cnpj}")
    if dados.restaurante_endereco:
        linha(dados.restaurante_endereco, 9)
    pdf.ln(2)

    linha("CONSUMIDOR", 10, "B")
    linha(dados.cliente_nome)
    if dados.cliente_email:
        linha(dados.cliente_email, 9)
    pdf.ln(3)

    # Tabela de itens
    colunas = (largura * 0.52, largura * 0.12, largura * 0.18, largura * 0.18)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    for titulo, w, alinhamento in zip(("Item", "Qtd", "Unitário", "Subtotal"), colunas, "LCRR"):
        pdf.cell(w, 7, _latin1(titulo), border=1, align=alinhamento, fill=True)
    pdf.ln()

    pdf.set_font("helvetica", "", 9)
    for item in dados.itens:
        valores = (item.nome, str(item.quantidade), _reais(item.preco_unitario), _reais(item.subtotal))
        for valor, w, alinhamento in zip(valores, colunas, "LCRR"):
            pdf.cell(w, 7, _latin1(valor)[:60], border=1, align=alinhamento)
        pdf.ln()
    pdf.ln(3)

    def total(rotulo_total: str, valor: Decimal, estilo: str = "") -> None:
        pdf.set_font("helvetica", estilo, 10)
        pdf.cell(largura * 0.75, 6, _latin1(rotulo_total), align="R")
        pdf.cell(largura * 0.25, 6, _latin1(_reais(valor)), align="R", new_x="LMARGIN", new_y="NEXT")

    total("Subtotal", dados.subtotal)
    total("Taxa de entrega", dados.taxa_entrega)
    total("TOTAL", dados.total, "B")
    pdf.ln(4)

    linha(f"Forma de pagamento: {METODOS.get(dados.forma_pagamento, dados.forma_pagamento)}")
    linha(f"Tipo de entrega: {ENTREGAS.get(dados.tipo_entrega, dados.tipo_entrega)}")
    if dados.transacao:
        linha(f"Transação: {dados.transacao}", 8)

    return bytes(pdf.output())


# ------------------------------------------------------------------ banco


def montar_dados(db: Session, pedido) -> DadosNota:
    """Le pedido, restaurante, cliente, itens e pagamento para a nota."""

    from app.models.item_pedido import ItemPedido
    from app.models.pagamento import Pagamento
    from app.models.produto import Produto
    from app.models.restaurante import Restaurante
    from app.models.usuario import Usuario

    restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
    cliente = Usuario.buscar_por_id(db, pedido.cliente_id)
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    itens = []
    for item in ItemPedido.listar_por_pedido(db, pedido.id):
        produto = Produto.buscar_por_id(db, item.produto_id)
        itens.append(
            ItemNota(
                nome=produto.nome if produto else f"Produto #{item.produto_id}",
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario,
            )
        )

    emitida = (pagamento.atualizado_em or pagamento.criado_em) if pagamento else pedido.criado_em

    return DadosNota(
        numero=pedido.cupom_fiscal or numero_nota_fiscal(pedido.id, pedido.criado_em.year),
        emitida_em=emitida,
        pedido_id=pedido.id,
        restaurante_nome=restaurante.nome_fantasia if restaurante else "Restaurante",
        restaurante_cnpj=restaurante.cnpj if restaurante else "-",
        restaurante_endereco=restaurante.local.endereco if restaurante and restaurante.local else None,
        cliente_nome=cliente.nome if cliente else "Consumidor",
        cliente_email=cliente.email if cliente else None,
        forma_pagamento=pedido.forma_pagamento,
        tipo_entrega=pedido.tipo_entrega,
        taxa_entrega=pedido.taxa_entrega,
        transacao=pagamento.transacao_externa_id if pagamento else None,
        itens=itens,
    )


def emitir_nota(db: Session, pedido) -> str:
    """Numera a nota do pedido (uma vez so) e devolve o numero."""

    if not pedido.cupom_fiscal:
        pedido.cupom_fiscal = numero_nota_fiscal(pedido.id, pedido.criado_em.year)
        pedido.atualizado_em = datetime.now()
        db.commit()
        db.refresh(pedido)

    return pedido.cupom_fiscal


def ao_aprovar_pagamento(db: Session, pedido, tarefas: BackgroundTasks | None) -> str:
    """Chamado sempre que o pagamento do pedido fica "aprovado"."""

    numero = emitir_nota(db, pedido)

    if tarefas is not None:
        tarefas.add_task(enviar_nota_por_email, pedido.id)

    return numero


def enviar_nota_por_email(pedido_id: int) -> None:
    """Gera o PDF e manda ao cliente. Roda em segundo plano; nunca levanta erro."""

    from app.models.pagamento import Pagamento
    from app.models.pedido import Pedido

    db = SessionLocal()
    try:
        pedido = Pedido.buscar_por_id(db, pedido_id)
        if pedido is None or not pedido.cupom_fiscal:
            return

        pagamento = Pagamento.buscar_por_pedido(db, pedido_id)
        if pagamento is not None and pagamento.nota_enviada_em is not None:
            return  # ja enviada

        dados = montar_dados(db, pedido)
        pdf = gerar_pdf(dados)

        if not dados.cliente_email:
            log.info("Nota %s gerada; cliente sem e-mail, envio ignorado.", dados.numero)
            return

        enviado = email.enviar(
            para=dados.cliente_email,
            assunto=f"EntregaFood - Nota fiscal do pedido #{pedido_id}",
            texto=(
                f"Ola, {dados.cliente_nome}!\n\n"
                f"Seu pagamento do pedido #{pedido_id} foi aprovado.\n"
                f"Segue em anexo a nota fiscal {dados.numero} "
                f"(total {_reais(dados.total)}).\n\nBom apetite!\nEquipe EntregaFood"
            ),
            anexo=pdf,
            nome_anexo=f"{dados.numero}.pdf",
        )

        if enviado and pagamento is not None:
            pagamento.marcar_nota_enviada(db)
    except Exception:  # noqa: BLE001 - segundo plano: so registra
        log.exception("Falha ao enviar a nota fiscal do pedido %s", pedido_id)
    finally:
        db.close()
