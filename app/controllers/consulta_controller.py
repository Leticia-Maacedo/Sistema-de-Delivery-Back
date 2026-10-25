"""CONTROLLER — Consultas do cliente (Sprint 2).

Endpoints de *leitura* voltados a quem usa o app pra pedir comida —
distintos do CRUD de administracao em `restaurante_controller.py` e
`produto_controller.py`:

    GET /consultas/restaurantes                  -> restaurantes aprovados (com ?busca=)
    GET /consultas/restaurantes/{id}             -> detalhe de um restaurante aprovado
    GET /consultas/restaurantes/{id}/cardapio    -> restaurante + itens disponiveis

Regras de visibilidade:
    - so aparece restaurante com status_aprovacao = 'aprovado';
    - com latitude/longitude do endereco do cliente, so aparece quem entrega
      ali (raio de entrega do restaurante), do mais perto para o mais longe;
    - no cardapio, so item com disponivel = true.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.frete import distancia_linha_reta_km, entrega_no_raio
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.schemas.consulta import CardapioOut, RestauranteConsultaOut

router = APIRouter(prefix="/consultas", tags=["Consultas (Cliente)"])


@router.get(
    "/restaurantes",
    response_model=list[RestauranteConsultaOut],
    summary="Consultar restaurantes disponiveis",
)
def consultar_restaurantes(
    busca: str | None = Query(default=None, description="Filtra por trecho do nome fantasia"),
    latitude: Decimal | None = Query(default=None, ge=-90, le=90, description="Endereco do cliente"),
    longitude: Decimal | None = Query(default=None, ge=-180, le=180, description="Endereco do cliente"),
    incluir_fora_do_raio: bool = Query(default=False, description="Lista tambem quem nao entrega no endereco"),
    limite: int = Query(default=100, ge=1, le=200),
    pular: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Restaurante]:
    if latitude is None or longitude is None:
        return Restaurante.listar_aprovados(db, busca=busca, limite=limite, pular=pular)

    # A distancia da lista e a estimada (linha reta x fator), sem chamar o
    # servico de rotas para cada restaurante; a taxa final e calculada no
    # resumo da cesta.
    fator = Decimal(str(get_settings().FRETE_FATOR_CIRCUITO))
    restaurantes = []
    for restaurante in Restaurante.listar_aprovados(db, busca=busca, limite=1000):
        km = distancia_linha_reta_km(
            restaurante.local.latitude, restaurante.local.longitude, latitude, longitude
        ) * fator
        restaurante.distancia_km = km.quantize(Decimal("0.1"))
        restaurante.entrega_no_endereco = entrega_no_raio(km, restaurante.raio_entrega_km)
        if restaurante.entrega_no_endereco or incluir_fora_do_raio:
            restaurantes.append(restaurante)

    restaurantes.sort(key=lambda r: r.distancia_km)
    return restaurantes[pular:pular + limite]


@router.get(
    "/restaurantes/{restaurante_id}",
    response_model=RestauranteConsultaOut,
    summary="Consultar um restaurante",
)
def consultar_restaurante(restaurante_id: int, db: Session = Depends(get_db)) -> Restaurante:
    restaurante = Restaurante.buscar_aprovado_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurante nao encontrado ou indisponivel.",
        )
    return restaurante


@router.get(
    "/restaurantes/{restaurante_id}/cardapio",
    response_model=CardapioOut,
    summary="Consultar o cardapio de um restaurante",
)
def consultar_cardapio(restaurante_id: int, db: Session = Depends(get_db)) -> CardapioOut:
    restaurante = Restaurante.buscar_aprovado_por_id(db, restaurante_id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurante nao encontrado ou indisponivel.",
        )
    itens = Produto.listar_disponiveis(db, restaurante_id)
    return CardapioOut(
        restaurante=RestauranteConsultaOut.model_validate(restaurante),
        total_itens=len(itens),
        itens=itens,
    )
