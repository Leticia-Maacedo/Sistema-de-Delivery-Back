"""PDF da nota fiscal SIMULADA (sem valor fiscal).

Usado pelo provedor "simulado" (app/core/fiscal/provedores.py), que e o padrao
enquanto nao ha servico fiscal real configurado. O PDF e gerado de novo a cada
download a partir do banco, entao nenhum arquivo fica guardado. Com o provedor
real (Focus NFe), o documento valido e o DANFCe devolvido pelo servico.
"""

from decimal import Decimal

from fpdf import FPDF

from app.core.fiscal.dados import ENTREGAS, METODOS, DadosNota, reais


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
        valores = (item.nome, str(item.quantidade), reais(item.preco_unitario), reais(item.subtotal))
        for valor, w, alinhamento in zip(valores, colunas, "LCRR"):
            pdf.cell(w, 7, _latin1(valor)[:60], border=1, align=alinhamento)
        pdf.ln()
    pdf.ln(3)

    def total(rotulo_total: str, valor: Decimal, estilo: str = "") -> None:
        pdf.set_font("helvetica", estilo, 10)
        pdf.cell(largura * 0.75, 6, _latin1(rotulo_total), align="R")
        pdf.cell(largura * 0.25, 6, _latin1(reais(valor)), align="R", new_x="LMARGIN", new_y="NEXT")

    total("Subtotal", dados.subtotal)
    total("Taxa de entrega", dados.taxa_entrega)
    total("TOTAL", dados.total, "B")
    pdf.ln(4)

    linha(f"Forma de pagamento: {METODOS.get(dados.forma_pagamento, dados.forma_pagamento)}")
    linha(f"Tipo de entrega: {ENTREGAS.get(dados.tipo_entrega, dados.tipo_entrega)}")
    if dados.transacao:
        linha(f"Transação: {dados.transacao}", 8)

    return bytes(pdf.output())
