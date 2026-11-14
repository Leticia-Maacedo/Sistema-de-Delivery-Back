"""CONTROLLER - Nota fiscal do pedido (situacao, nova emissao e reenvio).

    GET  /notas-fiscais/pedidos/{id}         situacao da nota (cliente dono, restaurante dono, admin);
                                             se ela estava esperando o servico voltar e a hora chegou,
                                             tenta de novo antes de responder
    POST /notas-fiscais/pedidos/{id}/emitir  nova emissao depois de rejeicao ou falha
                                             (restaurante dono ou admin)
    POST /notas-fiscais/reprocessar          tenta de novo todas as pendentes cuja hora chegou (admin)

O PDF ou o DANFCe continua em GET /pagamentos/pedidos/{id}/nota-fiscal.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers.pagamento_controller import buscar_pedido_para_consulta
from app.core.database import get_db
from app.core.fiscal import emissao
from app.core.nota_fiscal import enviar_nota_por_email
from app.core.security import exigir_admin, obter_usuario_logado
from app.models import nota_fiscal as situacao
from app.models.nota_fiscal import NotaFiscal
from app.models.pagamento import Pagamento
from app.models.usuario import Usuario
from app.schemas.nota_fiscal import NotaFiscalOut

router = APIRouter(prefix="/notas-fiscais", tags=["Nota fiscal"])


def _depois_de_emitir(nota: NotaFiscal, tarefas: BackgroundTasks) -> NotaFiscal:
    if nota.status == situacao.AUTORIZADA:
        tarefas.add_task(enviar_nota_por_email, nota.pedido_id)
    return nota


@router.get("/pedidos/{pedido_id}", response_model=NotaFiscalOut, summary="Situação da nota fiscal do pedido")
def situacao_da_nota(
    pedido_id: int,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> NotaFiscal:
    pedido = buscar_pedido_para_consulta(db, pedido_id, usuario_logado)
    nota = NotaFiscal.buscar_por_pedido(db, pedido.id)
    if nota is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A nota fiscal é emitida quando o pagamento é aprovado.")
    if nota.status == situacao.PENDENTE_REENVIO and nota.proxima_tentativa_em and nota.proxima_tentativa_em <= datetime.now():
        nota = _depois_de_emitir(emissao.emitir(db, pedido), tarefas)
    return nota


@router.post("/pedidos/{pedido_id}/emitir", response_model=NotaFiscalOut, summary="Emitir de novo a nota fiscal do pedido")
def emitir_de_novo(
    pedido_id: int,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> NotaFiscal:
    pedido = buscar_pedido_para_consulta(db, pedido_id, usuario_logado)
    if usuario_logado.tipo not in ("restaurante", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Somente o restaurante do pedido ou o administrador emite a nota.")
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)
    if pagamento is None or pagamento.status != "aprovado":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A nota só é emitida para pedido com pagamento aprovado.")
    nota = NotaFiscal.buscar_por_pedido(db, pedido.id)
    if nota is not None and nota.status == situacao.AUTORIZADA:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A nota {nota.numero} já está autorizada.")
    return _depois_de_emitir(emissao.emitir(db, pedido), tarefas)


@router.post("/reprocessar", response_model=list[NotaFiscalOut], summary="Tentar de novo as notas pendentes (admin)")
def reprocessar(
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: Usuario = Depends(exigir_admin),
) -> list[NotaFiscal]:
    return [_depois_de_emitir(nota, tarefas) for nota in emissao.reprocessar_pendentes(db)]
