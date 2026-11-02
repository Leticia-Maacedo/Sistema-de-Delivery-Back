"""Quem recebe notificacao push em cada momento do pedido.

Itens do Backlog: 21 (push ao cliente quando o pedido e feito) e 23 (push
a cada mudanca de status). As funcoes `notificar_*` rodam em segundo plano
(BackgroundTasks do FastAPI) com uma sessao de banco propria, depois que a
resposta ja foi enviada; erro aqui nunca afeta o pedido.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.core import status_pedido
from app.core.database import SessionLocal
from app.core.push import enviar_para_usuario, push_ativo
from app.core.push_fcm import enviar_para_usuario_fcm, fcm_ativo


@dataclass
class Aviso:
    """Uma notificacao para um destinatario."""

    para: str  # "cliente", "restaurante" ou "entregadores"
    titulo: str
    corpo: str


def avisos_pedido_criado(pedido_id: int, tipo_entrega: str) -> list[Aviso]:
    entrega = "retirada no balcão" if tipo_entrega == "retirada" else "entrega"
    return [
        Aviso("cliente", f"Pedido #{pedido_id} recebido",
              "Enviamos o seu pedido ao restaurante. Avisaremos a cada mudança."),
        Aviso("restaurante", f"Novo pedido #{pedido_id}",
              f"Pedido para {entrega} aguardando o seu aceite."),
    ]


def avisos_mudanca_status(pedido_id: int, status: str, tipo_entrega: str) -> list[Aviso]:
    """Mensagens de cada etapa; o cliente e avisado de todas."""

    textos = {
        status_pedido.ACEITO: "O restaurante aceitou o seu pedido.",
        status_pedido.EM_PREPARACAO: "Seu pedido está sendo preparado.",
        status_pedido.PRONTO_PARA_ENTREGA: "Seu pedido está pronto e aguarda o entregador.",
        status_pedido.PRONTO_PARA_RETIRADA: "Seu pedido está pronto. Retire no balcão com o código de entrega.",
        status_pedido.EM_TRANSITO: "Seu pedido saiu para entrega. Tenha o código de entrega em mãos.",
        status_pedido.ENTREGUE: "Pedido entregue. Bom apetite!",
        status_pedido.CANCELADO: "Seu pedido foi cancelado pelo restaurante.",
    }
    avisos = [Aviso("cliente", f"Pedido #{pedido_id}: {status_pedido.rotulo(status)}",
                    textos.get(status, status_pedido.rotulo(status)))]
    if status == status_pedido.PRONTO_PARA_ENTREGA and tipo_entrega == "delivery":
        avisos.append(Aviso("entregadores", f"Entrega disponível: pedido #{pedido_id}",
                            "Pedido pronto para sair. Abra o painel de entregas."))
    return avisos


def _destinatarios(db, pedido, para: str) -> list[int]:
    from app.models.restaurante import Restaurante
    from app.models.usuario import Usuario

    if para == "cliente":
        return [pedido.cliente_id]
    if para == "restaurante":
        restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
        return [restaurante.usuario_id] if restaurante and restaurante.usuario_id else []
    if para == "entregadores":
        return list(db.execute(select(Usuario.id).where(Usuario.tipo == "entregador")).scalars())
    return []


def _enviar(pedido_id: int, gerar) -> None:
    """Manda cada aviso pelos dois canais: navegador (Web Push) e app (FCM)."""

    web, app_mobile = push_ativo(), fcm_ativo()
    if not web and not app_mobile:
        return
    from app.models.pedido import Pedido

    db = SessionLocal()
    try:
        pedido = Pedido.buscar_por_id(db, pedido_id)
        if pedido is None:
            return
        for aviso in gerar(pedido):
            url = "/" if aviso.para == "cliente" else "/?painel=1"
            for usuario_id in _destinatarios(db, pedido, aviso.para):
                if web:
                    enviar_para_usuario(db, usuario_id, titulo=aviso.titulo, corpo=aviso.corpo,
                                        url=url, tag=f"pedido-{pedido_id}")
                if app_mobile:
                    # O app abre o pedido certo ao tocar na notificacao (dados.pedido_id).
                    enviar_para_usuario_fcm(db, usuario_id, titulo=aviso.titulo, corpo=aviso.corpo,
                                            dados={"pedido_id": pedido_id, "status": pedido.status,
                                                   "destino": aviso.para})
    finally:
        db.close()


def notificar_pedido_criado(pedido_id: int) -> None:
    _enviar(pedido_id, lambda p: avisos_pedido_criado(p.id, p.tipo_entrega))


def avisos_cancelamento_cliente(pedido_id: int) -> list[Aviso]:
    """RN04: o cliente cancelou enquanto o pedido aguardava o aceite."""

    return [
        Aviso("cliente", f"Pedido #{pedido_id} cancelado",
              "Você cancelou o pedido. Se já tinha pago, o valor será estornado."),
        Aviso("restaurante", f"Pedido #{pedido_id} cancelado pelo cliente",
              "O cliente desistiu antes do aceite. Não é preciso preparar."),
    ]


def notificar_cancelamento_cliente(pedido_id: int) -> None:
    _enviar(pedido_id, lambda p: avisos_cancelamento_cliente(p.id))


def notificar_mudanca_status(pedido_id: int) -> None:
    _enviar(pedido_id, lambda p: avisos_mudanca_status(p.id, p.status, p.tipo_entrega))
