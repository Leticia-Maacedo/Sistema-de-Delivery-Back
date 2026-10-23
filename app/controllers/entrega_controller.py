"""Controller do rastreio da entrega (Backlog 25).

- O entregador que saiu com o pedido envia a posicao do celular.
- Cliente, restaurante dono, entregador e admin consultam o rastreio:
  restaurante, destino e posicao do entregador, com o link do Google Maps.
"""

from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers.pedido_controller import buscar_pedido_visivel
from app.controllers.sacola_controller import obter_local_entrega
from app.core import status_pedido
from app.core.database import get_db
from app.core.security import obter_usuario_logado
from app.models.entrega import Entrega
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario
from app.schemas.entrega import LocalizacaoIn, PontoOut, PosicaoEntregadorOut, RastreioOut

router = APIRouter(prefix="/pedidos", tags=["Pedido"])


def link_google_maps(origem: tuple | None, destino: tuple | None) -> str | None:
    """Link de rota do Google Maps (abre no app/site do Google Maps)."""

    if destino is None:
        return None
    params = {"api": "1", "destination": f"{destino[0]},{destino[1]}", "travelmode": "driving"}
    if origem is not None:
        params["origin"] = f"{origem[0]},{origem[1]}"
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def montar_rastreio(db: Session, pedido) -> RastreioOut:
    restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
    ponto_rest = None
    if restaurante and restaurante.local:
        ponto_rest = PontoOut(endereco=restaurante.local.endereco,
                              latitude=restaurante.local.latitude, longitude=restaurante.local.longitude)

    destino = None
    if pedido.tipo_entrega == "delivery":
        cliente = Usuario.buscar_por_id(db, pedido.cliente_id)
        local = obter_local_entrega(db, cliente, None) if cliente else None
        if local is not None:
            destino = PontoOut(endereco=local.endereco, latitude=local.latitude, longitude=local.longitude)

    entrega = Entrega.obter_ou_criar(db, pedido.id)
    posicao = None
    if (pedido.status == status_pedido.EM_TRANSITO and entrega.latitude_atual is not None
            and entrega.longitude_atual is not None):
        posicao = PosicaoEntregadorOut(latitude=entrega.latitude_atual, longitude=entrega.longitude_atual,
                                       atualizado_em=entrega.atualizado_em)

    origem = (posicao.latitude, posicao.longitude) if posicao else (
        (ponto_rest.latitude, ponto_rest.longitude) if ponto_rest else None)
    alvo = (destino.latitude, destino.longitude) if destino else (
        (ponto_rest.latitude, ponto_rest.longitude) if ponto_rest and pedido.tipo_entrega == "retirada" else None)

    return RastreioOut(
        pedido_id=pedido.id,
        status=pedido.status,
        status_rotulo=status_pedido.rotulo(pedido.status),
        tipo_entrega=pedido.tipo_entrega,
        restaurante_nome=restaurante.nome_fantasia if restaurante else None,
        restaurante=ponto_rest,
        destino=destino,
        entregador=posicao,
        mapa_url=link_google_maps(origem if pedido.tipo_entrega == "delivery" else None, alvo),
    )


@router.get("/{pedido_id}/rastreio", response_model=RastreioOut, summary="Rastreio da entrega (mapa)")
def obter_rastreio(
    pedido_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> RastreioOut:
    """Restaurante, destino e posição do entregador (quando em trânsito).

    Mesma regra de acesso do acompanhamento: cliente dono, restaurante dono,
    entregador e admin.
    """

    pedido = buscar_pedido_visivel(db, pedido_id, usuario_logado)
    return montar_rastreio(db, pedido)


@router.patch("/{pedido_id}/entrega/localizacao", response_model=RastreioOut,
              summary="Entregador envia a posição atual")
def atualizar_localizacao(
    pedido_id: int,
    dados: LocalizacaoIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> RastreioOut:
    """Só o entregador que saiu com o pedido (ou admin), com o pedido em trânsito."""

    if usuario_logado.tipo not in ("entregador", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Somente o entregador pode enviar a localização.")

    pedido = buscar_pedido_visivel(db, pedido_id, usuario_logado)

    if pedido.status != status_pedido.EM_TRANSITO:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="A localização só é enviada com o pedido em trânsito.")

    entrega = Entrega.obter_ou_criar(db, pedido.id)

    if usuario_logado.tipo == "entregador" and entrega.entregador_id != usuario_logado.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Este pedido está com outro entregador.")

    entrega.latitude_atual = dados.latitude
    entrega.longitude_atual = dados.longitude
    entrega.atualizado_em = datetime.now()
    db.commit()

    return montar_rastreio(db, pedido)
