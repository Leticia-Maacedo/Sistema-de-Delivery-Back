"""Emissao da nota fiscal de um pedido e tratamento de rejeicao e indisponibilidade.

Fluxo (chamado quando o pagamento fica aprovado):

1. Cria ou reaproveita a linha de `nota_fiscal` do pedido (uma por pedido;
   a referencia enviada ao servico e sempre "pedido-<id>", entao repetir a
   emissao nunca gera duas notas).
2. Chama o provedor configurado (simulado ou Focus NFe).
3. Autorizada: grava numero, serie, chave e DANFCe e copia o numero para
   `pedido.cupom_fiscal`.
4. Rejeitada: grava o motivo (codigo e mensagem da SEFAZ). Nao tenta de novo
   sozinha, porque o mesmo pedido seria recusado de novo; o restaurante ou o
   administrador corrige o cadastro e pede nova emissao.
5. Servico fora do ar: fica "pendente_reenvio" e tenta de novo depois, com
   espera crescente (1, 5, 15, 60 minutos...). Depois de MAX_TENTATIVAS vira
   "falhou" e precisa de emissao manual. O pedido segue normalmente: a falha
   da nota nunca bloqueia o pagamento nem a entrega.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.fiscal.dados import montar_dados
from app.core.fiscal.provedores import AUTORIZADA, ServicoFiscalIndisponivel, obter_provedor
from app.models import nota_fiscal as situacao
from app.models.nota_fiscal import NotaFiscal

log = logging.getLogger("entregafood.fiscal")

ESPERAS_MINUTOS = (1, 5, 15, 60, 240)
MAX_TENTATIVAS = len(ESPERAS_MINUTOS) + 1


def referencia_do_pedido(pedido_id: int) -> str:
    return f"pedido-{pedido_id}"


def _registro(db: Session, pedido, provedor) -> NotaFiscal:
    nota = NotaFiscal.buscar_por_pedido(db, pedido.id)
    if nota is None:
        nota = NotaFiscal(pedido_id=pedido.id, provedor=provedor.nome, ambiente=provedor.ambiente,
                          referencia=referencia_do_pedido(pedido.id), status=situacao.PROCESSANDO,
                          tentativas=0, criado_em=datetime.now())
        db.add(nota)
        db.flush()
    return nota


def emitir(db: Session, pedido, provedor=None, agora: datetime | None = None) -> NotaFiscal:
    """Emite (ou tenta de novo) a nota do pedido e devolve a linha atualizada."""

    provedor = provedor or obter_provedor()
    agora = agora or datetime.now()
    nota = _registro(db, pedido, provedor)
    if nota.status == situacao.AUTORIZADA:
        return nota

    nota.provedor, nota.ambiente = provedor.nome, provedor.ambiente
    nota.tentativas += 1
    nota.status = situacao.PROCESSANDO
    nota.atualizado_em = agora
    db.commit()

    try:
        resultado = provedor.emitir(montar_dados(db, pedido), nota.referencia)
    except ServicoFiscalIndisponivel as erro:
        if nota.tentativas >= MAX_TENTATIVAS:
            nota.status, nota.proxima_tentativa_em = situacao.FALHOU, None
            nota.mensagem = f"{erro} Limite de {MAX_TENTATIVAS} tentativas atingido; emita manualmente."
        else:
            espera = ESPERAS_MINUTOS[min(nota.tentativas, len(ESPERAS_MINUTOS)) - 1]
            nota.status = situacao.PENDENTE_REENVIO
            nota.proxima_tentativa_em = agora + timedelta(minutes=espera)
            nota.mensagem = f"{erro} Nova tentativa em {espera} min."
        log.warning("Nota do pedido %s: %s", pedido.id, nota.mensagem)
    else:
        nota.mensagem = (resultado.mensagem or "")[:500] or None
        nota.proxima_tentativa_em = None
        if resultado.status == AUTORIZADA:
            nota.status = situacao.AUTORIZADA
            nota.numero, nota.serie, nota.chave = resultado.numero, resultado.serie, resultado.chave
            nota.protocolo, nota.url_danfe = resultado.protocolo, resultado.url_danfe
            pedido.cupom_fiscal = resultado.numero
            pedido.atualizado_em = agora
        else:
            nota.status = situacao.REJEITADA
            log.warning("Nota do pedido %s rejeitada: %s", pedido.id, nota.mensagem)

    nota.atualizado_em = agora
    db.commit()
    db.refresh(nota)
    return nota


def cancelar(db: Session, pedido, justificativa: str = "Pedido cancelado antes da entrega ao consumidor.", provedor=None) -> NotaFiscal | None:
    """Pedido cancelado: cancela a nota autorizada na SEFAZ; nota que nao saiu deixa de ser tentada.

    Nunca impede o cancelamento do pedido. Se o servico recusar (por exemplo,
    passou o prazo de 30 minutos da NFC-e) ou estiver fora, a nota continua
    autorizada com o motivo registrado, para o restaurante tratar com o contador.
    """

    nota = NotaFiscal.buscar_por_pedido(db, pedido.id)
    if nota is None or nota.status in (situacao.CANCELADA, situacao.REJEITADA):
        return nota
    agora = datetime.now()
    if nota.status != situacao.AUTORIZADA:
        nota.status, nota.proxima_tentativa_em = situacao.CANCELADA, None
        nota.mensagem, nota.atualizado_em = "Pedido cancelado antes de a nota ser autorizada.", agora
        db.commit()
        return nota
    provedor = provedor or obter_provedor()
    try:
        resultado = provedor.cancelar(nota.referencia, justificativa)
    except ServicoFiscalIndisponivel as erro:
        nota.mensagem = f"Cancelamento na SEFAZ não realizado: {erro}"
    else:
        if resultado.status == "cancelada":
            nota.status = situacao.CANCELADA
            nota.mensagem = resultado.mensagem
        else:
            nota.mensagem = resultado.mensagem
    nota.atualizado_em = agora
    db.commit()
    log.info("Nota do pedido %s no cancelamento: %s (%s)", pedido.id, nota.status, nota.mensagem)
    return nota


def reprocessar_pendentes(db: Session, provedor=None, agora: datetime | None = None) -> list[NotaFiscal]:
    """Tenta de novo as notas que ficaram para depois e cuja hora ja chegou."""

    from app.models.pedido import Pedido

    agora = agora or datetime.now()
    processadas = []
    for nota in NotaFiscal.listar_para_reenvio(db, agora):
        pedido = Pedido.buscar_por_id(db, nota.pedido_id)
        if pedido is not None:
            processadas.append(emitir(db, pedido, provedor, agora))
    return processadas
