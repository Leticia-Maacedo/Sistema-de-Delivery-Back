"""Nota fiscal do pedido - ponto de entrada usado pelos controllers.

Quando o pagamento e aprovado:
    1. `ao_aprovar_pagamento` emite a nota pelo provedor configurado
       (app/core/fiscal: simulado ou Focus NFe), com tratamento de rejeicao e
       de servico fora do ar.
    2. Se a nota foi autorizada, `enviar_nota_por_email` (em segundo plano)
       manda ao cliente o PDF simulado ou o link do DANFCe.

A falha da nota nunca bloqueia o pagamento nem o pedido.
"""

import logging

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core import email
from app.core.database import SessionLocal
from app.core.fiscal import emissao
from app.core.fiscal.dados import ENTREGAS, METODOS, DadosNota, ItemNota, montar_dados, reais
from app.core.fiscal.pdf_simulado import gerar_pdf
from app.models import nota_fiscal as situacao

__all__ = ["DadosNota", "ItemNota", "ENTREGAS", "METODOS", "gerar_pdf", "montar_dados", "ao_aprovar_pagamento",
           "emitir_nota", "enviar_nota_por_email"]

log = logging.getLogger("entregafood.nota_fiscal")


def emitir_nota(db: Session, pedido) -> str | None:
    """Emite a nota do pedido (uma vez so) e devolve o numero, ou None se nao foi autorizada."""

    try:
        nota = emissao.emitir(db, pedido)
    except Exception:  # noqa: BLE001 - a nota nunca derruba o pagamento
        db.rollback()
        log.exception("Erro inesperado ao emitir a nota do pedido %s", pedido.id)
        return None
    return nota.numero if nota.status == situacao.AUTORIZADA else None


def ao_aprovar_pagamento(db: Session, pedido, tarefas: BackgroundTasks | None) -> str | None:
    """Chamado sempre que o pagamento do pedido fica "aprovado"."""

    numero = emitir_nota(db, pedido)
    if numero and tarefas is not None:
        tarefas.add_task(enviar_nota_por_email, pedido.id)
    return numero


def enviar_nota_por_email(pedido_id: int) -> None:
    """Manda a nota autorizada ao cliente. Roda em segundo plano; nunca levanta erro."""

    from app.models.nota_fiscal import NotaFiscal
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
        if not dados.cliente_email:
            log.info("Nota %s autorizada; cliente sem e-mail, envio ignorado.", dados.numero)
            return

        nota = NotaFiscal.buscar_por_pedido(db, pedido_id)
        texto = (f"Ola, {dados.cliente_nome}!\n\nSeu pagamento do pedido #{pedido_id} foi aprovado.\n"
                 f"Nota fiscal {dados.numero} (total {reais(dados.total)})")
        if nota is not None and nota.url_danfe:
            enviado = email.enviar(para=dados.cliente_email, assunto=f"EntregaFood - Nota fiscal do pedido #{pedido_id}",
                                   texto=f"{texto}: {nota.url_danfe}\n\nBom apetite!\nEquipe EntregaFood")
        else:
            enviado = email.enviar(
                para=dados.cliente_email,
                assunto=f"EntregaFood - Nota fiscal do pedido #{pedido_id}",
                texto=f"{texto} em anexo.\n\nBom apetite!\nEquipe EntregaFood",
                anexo=gerar_pdf(dados),
                nome_anexo=f"{dados.numero}.pdf",
            )

        if enviado and pagamento is not None:
            pagamento.marcar_nota_enviada(db)
    except Exception:  # noqa: BLE001 - segundo plano: so registra
        log.exception("Falha ao enviar a nota fiscal do pedido %s", pedido_id)
    finally:
        db.close()
