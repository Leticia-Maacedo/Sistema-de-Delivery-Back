"""CONTROLLER — Portal do Parceiro.

O dono (usuario do tipo "restaurante") gerencia o PROPRIO restaurante:
cadastro (nasce aguardando aprovacao do admin), dados, endereco, raio de
entrega, horario de funcionamento, pausa (ativo/inativo), cardapio e os
numeros do dia. Todas as rotas exigem login de restaurante e so enxergam
o restaurante dele — diferente do CRUD de /restaurantes e /produtos, que
e a administracao da plataforma.
"""

from datetime import datetime, time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import status_pedido
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import exigir_restaurante
from app.models.item_pedido import ItemPedido
from app.models.local import Local
from app.models.pedido import Pedido
from app.models.produto import Produto
from app.models.restaurante import Restaurante
from app.models.sacola import ItemSacola
from app.models.usuario import Usuario
from app.schemas.parceiro import (
    ProdutoParceiroIn,
    ProdutoParceiroUpdate,
    RestauranteParceiroIn,
    RestauranteParceiroOut,
    RestauranteParceiroUpdate,
    ResumoParceiroOut,
)
from app.schemas.produto import ProdutoOut

router = APIRouter(prefix="/parceiro", tags=["Portal do Parceiro"])


def _meu_restaurante(db: Session, usuario: Usuario) -> Restaurante:
    restaurante = Restaurante.buscar_por_dono(db, usuario.id)
    if restaurante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Você ainda não cadastrou o seu restaurante.",
        )
    return restaurante


def _saida(restaurante: Restaurante) -> RestauranteParceiroOut:
    local = restaurante.local
    return RestauranteParceiroOut(
        id=restaurante.id,
        nome_fantasia=restaurante.nome_fantasia,
        cnpj=restaurante.cnpj,
        status_aprovacao=restaurante.status_aprovacao,
        taxa_entrega_km=restaurante.taxa_entrega_km,
        raio_entrega_km=restaurante.raio_entrega_km,
        raio_padrao_km=get_settings().FRETE_RAIO_MAX_KM,
        horario_abertura=restaurante.horario_abertura,
        horario_fechamento=restaurante.horario_fechamento,
        ativo=restaurante.ativo,
        aberto=restaurante.aberto_agora(),
        endereco=local.endereco,
        latitude=local.latitude,
        longitude=local.longitude,
        criado_em=restaurante.criado_em,
    )


# ------------------------------------------------------------ restaurante
@router.get("/restaurante", response_model=RestauranteParceiroOut, summary="Meu restaurante")
def obter_meu_restaurante(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> RestauranteParceiroOut:
    return _saida(_meu_restaurante(db, usuario))


@router.post(
    "/restaurante",
    response_model=RestauranteParceiroOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar meu restaurante",
)
def cadastrar_meu_restaurante(
    dados: RestauranteParceiroIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> RestauranteParceiroOut:
    """Cria o endereco e o restaurante do dono. Nasce "pendente": so aparece
    para os clientes depois que o admin aprovar."""

    if Restaurante.buscar_por_dono(db, usuario.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já tem um restaurante cadastrado. Altere os dados dele.",
        )
    if Restaurante.cnpj_ja_cadastrado(db, dados.cnpj.strip()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CNPJ já cadastrado.")

    local = Local.criar(
        db,
        usuario_id=usuario.id,
        endereco=dados.endereco,
        tipo="restaurante",
        latitude=dados.latitude,
        longitude=dados.longitude,
    )
    restaurante = Restaurante.criar(
        db,
        local_id=local.id,
        usuario_id=usuario.id,
        nome_fantasia=dados.nome_fantasia,
        cnpj=dados.cnpj,
        taxa_entrega_km=dados.taxa_entrega_km,
        raio_entrega_km=dados.raio_entrega_km,
        horario_abertura=dados.horario_abertura,
        horario_fechamento=dados.horario_fechamento,
        ativo=True,
    )
    return _saida(restaurante)


@router.put("/restaurante", response_model=RestauranteParceiroOut, summary="Alterar meu restaurante")
def alterar_meu_restaurante(
    dados: RestauranteParceiroUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> RestauranteParceiroOut:
    """Dados, endereco, raio, horario e pausa. A aprovacao continua com o admin."""

    restaurante = _meu_restaurante(db, usuario)
    campos = dados.model_dump(exclude_unset=True)

    if campos.get("cnpj") and Restaurante.cnpj_ja_cadastrado(db, campos["cnpj"].strip(), ignorar_id=restaurante.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CNPJ já cadastrado.")

    endereco = {k: campos.pop(k) for k in ("endereco", "latitude", "longitude") if k in campos}
    if endereco:
        restaurante.local.atualizar(db, **endereco)

    for campo, valor in campos.items():
        if campo in ("nome_fantasia", "cnpj", "taxa_entrega_km", "ativo") and valor is None:
            continue  # obrigatorios: null nao apaga
        setattr(restaurante, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(restaurante)
    return _saida(restaurante)


@router.get("/resumo", response_model=ResumoParceiroOut, summary="Números do dia")
def resumo_do_dia(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> ResumoParceiroOut:
    restaurante = _meu_restaurante(db, usuario)
    inicio_dia = datetime.combine(datetime.now().date(), time.min)

    pedidos = list(db.execute(
        select(Pedido).where(Pedido.restaurante_id == restaurante.id, Pedido.criado_em >= inicio_dia)
    ).scalars())
    validos = [p for p in pedidos if p.status != status_pedido.CANCELADO]
    faturamento = sum((p.valor_total for p in validos), Decimal("0.00"))

    abertos = list(db.execute(
        select(Pedido.status).where(Pedido.restaurante_id == restaurante.id)
    ).scalars())
    produtos = list(db.execute(select(Produto).where(Produto.restaurante_id == restaurante.id)).scalars())

    return ResumoParceiroOut(
        pedidos_hoje=len(validos),
        aguardando_aceite=sum(1 for s in abertos if s == status_pedido.AGUARDANDO_ACEITE),
        em_andamento=sum(
            1 for s in abertos
            if s != status_pedido.AGUARDANDO_ACEITE and not status_pedido.status_finalizado(s)
        ),
        faturamento_hoje=faturamento,
        ticket_medio_hoje=(faturamento / len(validos)).quantize(Decimal("0.01")) if validos else Decimal("0.00"),
        produtos_ativos=sum(1 for p in produtos if p.disponivel),
        produtos_total=len(produtos),
    )


# --------------------------------------------------------------- cardapio
def _meu_produto(db: Session, restaurante: Restaurante, produto_id: int) -> Produto:
    produto = Produto.buscar_por_id(db, produto_id)
    if produto is None or produto.restaurante_id != restaurante.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado no seu cardápio.")
    return produto


@router.get("/produtos", response_model=list[ProdutoOut], summary="Meu cardápio")
def listar_meus_produtos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> list[Produto]:
    restaurante = _meu_restaurante(db, usuario)
    return list(db.execute(
        select(Produto).where(Produto.restaurante_id == restaurante.id).order_by(Produto.nome)
    ).scalars())


@router.post("/produtos", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED, summary="Novo item do cardápio")
def criar_meu_produto(
    dados: ProdutoParceiroIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> Produto:
    restaurante = _meu_restaurante(db, usuario)
    return Produto.criar(
        db,
        restaurante_id=restaurante.id,
        nome=dados.nome,
        descricao=(dados.descricao or "").strip() or None,
        preco=dados.preco,
        disponivel=dados.disponivel,
    )


@router.put("/produtos/{produto_id}", response_model=ProdutoOut, summary="Alterar item do cardápio")
def alterar_meu_produto(
    produto_id: int,
    dados: ProdutoParceiroUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> Produto:
    produto = _meu_produto(db, _meu_restaurante(db, usuario), produto_id)
    campos = dados.model_dump(exclude_unset=True)
    if "descricao" in campos:
        produto.descricao = (campos.pop("descricao") or "").strip() or None
    return produto.atualizar(db, **campos)


@router.delete("/produtos/{produto_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir item do cardápio")
def excluir_meu_produto(
    produto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_restaurante),
) -> Response:
    """Item que ja foi vendido fica no historico dos pedidos: em vez de
    excluir, o restaurante desativa (indisponivel)."""

    produto = _meu_produto(db, _meu_restaurante(db, usuario), produto_id)
    vendido = db.execute(
        select(func.count()).select_from(ItemPedido).where(ItemPedido.produto_id == produto.id)
    ).scalar_one()
    if vendido:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este item já aparece em pedidos e não pode ser excluído. Desative-o para tirá-lo do cardápio.",
        )
    for item in db.execute(select(ItemSacola).where(ItemSacola.produto_id == produto.id)).scalars():
        db.delete(item)  # sai das cestas abertas dos clientes
    produto.remover(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
