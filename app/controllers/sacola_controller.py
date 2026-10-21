
"""Controller da cesta de compras do EntregaFood."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.frete import calcular_taxa_entrega, entrega_no_raio, medir_distancia
from app.core.security import obter_usuario_logado
from app.models.local import Local
from app.models.produto import Produto
from app.models.restaurante import APROVADO, Restaurante
from app.models.sacola import ItemSacola, Sacola
from app.models.usuario import Usuario
from app.schemas.sacola import (
    ItemSacolaAdicionar,
    ItemSacolaOut,
    ItemSacolaQuantidade,
    ResumoCestaOut,
    SacolaOut,
)

router = APIRouter(prefix="/cesta", tags=["Cesta"])

# Regra provisoria do projeto: limite por produto, nao representa estoque.
QUANTIDADE_MAXIMA_POR_PRODUTO = 99


def validar_quantidade(quantidade: int) -> None:
    """Valida a quantidade total permitida por produto."""

    if quantidade < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A quantidade deve ser maior que zero.",
        )

    if quantidade > QUANTIDADE_MAXIMA_POR_PRODUTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Quantidade maxima permitida por produto: "
                f"{QUANTIDADE_MAXIMA_POR_PRODUTO} unidades."
            ),
        )


def validar_disponibilidade(produto: Produto) -> None:
    """Impede adicionar ou alterar produtos indisponiveis."""

    if not produto.disponivel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto indisponivel.",
        )


def validar_restaurante_cesta(
    db: Session,
    sacola: Sacola,
    produto: Produto,
) -> None:
    """Impede produtos de restaurantes diferentes na mesma cesta."""

    for item in ItemSacola.listar_por_sacola(db, sacola.id):
        produto_existente = Produto.buscar_por_id(db, item.produto_id)

        if produto_existente is None:
            continue

        if produto_existente.restaurante_id != produto.restaurante_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Nao e permitido adicionar produtos de "
                    "restaurantes diferentes na mesma cesta."
                ),
            )


def calcular_subtotal(
    preco_unitario: Decimal,
    quantidade: int,
) -> Decimal:
    """Calcula o subtotal de um produto."""

    return preco_unitario * quantidade


def calcular_total(subtotais: list[Decimal]) -> Decimal:
    """Calcula o valor total da cesta."""

    return sum(subtotais, Decimal("0.00"))


# ----------------------------------------------------------------------
# Fechamento da cesta (Sprint 3): subtotal, taxa de entrega e validacoes
# ----------------------------------------------------------------------


@dataclass
class Fechamento:
    """Tudo o que o resumo da cesta e a criacao do pedido precisam saber."""

    sacola: Sacola | None
    tipo_entrega: str
    itens: list[tuple[ItemSacola, Produto]] = field(default_factory=list)
    restaurante: Restaurante | None = None
    local: Local | None = None
    subtotal: Decimal = Decimal("0.00")
    distancia_km: Decimal | None = None
    metodo_distancia: str | None = None
    taxa_entrega: Decimal = Decimal("0.00")
    problema: str | None = None  # primeiro motivo que impede fechar

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.taxa_entrega


def obter_local_entrega(
    db: Session,
    usuario: Usuario,
    local_id: int | None,
) -> Local | None:
    """Endereco de entrega: o informado ou, se nenhum, o ultimo do cliente."""

    if local_id is not None:
        local = Local.buscar_por_id(db, local_id)

        if local is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endereco de entrega nao encontrado.",
            )

        if local.usuario_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este endereco nao pertence ao usuario logado.",
            )

        return local

    enderecos = [
        local for local in Local.listar(db, usuario_id=usuario.id)
        if local.tipo != "restaurante"
    ]
    return enderecos[-1] if enderecos else None


def validar_itens_para_fechamento(
    itens: list[tuple[ItemSacola, Produto | None]],
) -> str | None:
    """Revalida cada item no momento do fechamento ("estoque").

    O banco nao tem coluna de estoque: o produto precisa existir, estar
    disponivel e respeitar o limite de quantidade por produto.
    """

    for item, produto in itens:
        if produto is None:
            return "Um produto da cesta nao existe mais. Remova-o para continuar."

        if not produto.disponivel:
            return (
                f"O produto '{produto.nome}' esta indisponivel. "
                "Remova-o da cesta para continuar."
            )

        if item.quantidade > QUANTIDADE_MAXIMA_POR_PRODUTO:
            return (
                f"O produto '{produto.nome}' passou do limite de "
                f"{QUANTIDADE_MAXIMA_POR_PRODUTO} unidades."
            )

    restaurantes = {produto.restaurante_id for _, produto in itens}

    if len(restaurantes) > 1:
        return "A cesta tem produtos de restaurantes diferentes."

    return None


def preparar_fechamento(
    db: Session,
    usuario: Usuario,
    local_id: int | None,
    tipo_entrega: str,
) -> Fechamento:
    """Calcula subtotal, distancia e taxa e aponta o que impede o fechamento."""

    sacola = Sacola.buscar_por_cliente(db, usuario.id)
    fechamento = Fechamento(sacola=sacola, tipo_entrega=tipo_entrega)

    itens_sacola = ItemSacola.listar_por_sacola(db, sacola.id) if sacola else []

    if not itens_sacola:
        fechamento.problema = "A cesta esta vazia."
        return fechamento

    itens = [(item, Produto.buscar_por_id(db, item.produto_id)) for item in itens_sacola]

    # O subtotal aparece no resumo mesmo quando algo impede o fechamento.
    fechamento.itens = [(item, produto) for item, produto in itens if produto is not None]
    fechamento.subtotal = calcular_total(
        [calcular_subtotal(produto.preco, item.quantidade) for item, produto in fechamento.itens]
    )

    fechamento.problema = validar_itens_para_fechamento(itens)

    if fechamento.problema is not None:
        return fechamento

    restaurante = Restaurante.buscar_por_id(db, itens[0][1].restaurante_id)
    fechamento.restaurante = restaurante

    if restaurante is None or restaurante.status_aprovacao != APROVADO:
        fechamento.problema = "O restaurante desta cesta nao esta disponivel para pedidos."
        return fechamento

    if tipo_entrega == "retirada":
        return fechamento  # retirada no balcao: sem taxa de entrega

    local = obter_local_entrega(db, usuario, local_id)
    fechamento.local = local

    if local is None:
        fechamento.problema = "Cadastre um endereco de entrega para continuar."
        return fechamento

    distancia = medir_distancia(restaurante.local, local)
    fechamento.distancia_km = distancia.km
    fechamento.metodo_distancia = distancia.metodo

    if not entrega_no_raio(distancia.km):
        fechamento.problema = (
            f"O restaurante nao entrega neste endereco ({distancia.km} km)."
        )
        return fechamento

    fechamento.taxa_entrega = calcular_taxa_entrega(distancia.km, restaurante.taxa_entrega_km)
    return fechamento


def montar_resposta_cesta(
    db: Session,
    sacola: Sacola,
) -> SacolaOut:
    """Monta a resposta completa da cesta."""

    itens_saida: list[ItemSacolaOut] = []
    subtotais: list[Decimal] = []

    for item in ItemSacola.listar_por_sacola(db, sacola.id):
        produto = Produto.buscar_por_id(db, item.produto_id)

        if produto is None:
            continue

        subtotal = calcular_subtotal(
            produto.preco,
            item.quantidade,
        )
        subtotais.append(subtotal)

        itens_saida.append(
            ItemSacolaOut(
                id=item.id,
                produto_id=produto.id,
                nome=produto.nome,
                quantidade=item.quantidade,
                preco_unitario=produto.preco,
                subtotal=subtotal,
            )
        )

    return SacolaOut(
        id=sacola.id,
        cliente_id=sacola.cliente_id,
        criado_em=sacola.criado_em,
        atualizado_em=sacola.atualizado_em,
        itens=itens_saida,
        total=calcular_total(subtotais),
    )


@router.get(
    "",
    response_model=SacolaOut,
    summary="Consultar cesta do usuario logado",
)
def consultar_cesta(
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Consulta a cesta do usuario autenticado."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        return SacolaOut(
            id=None,
            cliente_id=usuario_logado.id,
            criado_em=None,
            atualizado_em=None,
            itens=[],
            total=Decimal("0.00"),
        )

    return montar_resposta_cesta(db, sacola)


@router.get(
    "/resumo",
    response_model=ResumoCestaOut,
    summary="Subtotal, taxa de entrega e total da cesta",
)
def resumo_cesta(
    local_id: int | None = Query(
        default=None,
        description="Endereco de entrega do cliente. Se omitido, usa o ultimo cadastrado.",
    ),
    tipo_entrega: Literal["delivery", "retirada"] = Query(default="delivery"),
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> ResumoCestaOut:
    """Mostra quanto o cliente vai pagar antes de fechar o pedido.

    Nao altera nada. `pode_fechar` indica se o pedido pode ser criado e
    `motivo` explica o que falta (cesta vazia, item indisponivel, sem
    endereco, fora do raio de entrega...).
    """

    fechamento = preparar_fechamento(db, usuario_logado, local_id, tipo_entrega)

    return ResumoCestaOut(
        cesta_id=fechamento.sacola.id if fechamento.sacola else None,
        restaurante_id=fechamento.restaurante.id if fechamento.restaurante else None,
        quantidade_itens=sum(item.quantidade for item, _ in fechamento.itens),
        subtotal=fechamento.subtotal,
        tipo_entrega=tipo_entrega,
        local_entrega_id=fechamento.local.id if fechamento.local else None,
        distancia_km=fechamento.distancia_km,
        metodo_distancia=fechamento.metodo_distancia,
        taxa_entrega=fechamento.taxa_entrega,
        total=fechamento.total,
        pode_fechar=fechamento.problema is None,
        motivo=fechamento.problema,
    )


@router.post(
    "/itens",
    response_model=SacolaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar produto a cesta",
)
def adicionar_produto_cesta(
    dados: ItemSacolaAdicionar,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Adiciona um produto a cesta do usuario autenticado."""

    produto = Produto.buscar_por_id(db, dados.produto_id)

    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado.",
        )

    validar_disponibilidade(produto)
    validar_quantidade(dados.quantidade)

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is not None:
        validar_restaurante_cesta(db, sacola, produto)

        item_existente = ItemSacola.buscar_por_produto(
            db,
            sacola.id,
            produto.id,
        )

        if item_existente is not None:
            nova_quantidade = (
                item_existente.quantidade + dados.quantidade
            )

            validar_quantidade(nova_quantidade)

            item_existente.quantidade = nova_quantidade
            sacola.atualizado_em = datetime.now()

            db.commit()
            db.refresh(item_existente)
            db.refresh(sacola)

            return montar_resposta_cesta(db, sacola)

    else:
        sacola = Sacola(
            cliente_id=usuario_logado.id,
            criado_em=datetime.now(),
            atualizado_em=None,
        )

        db.add(sacola)
        db.commit()
        db.refresh(sacola)

    ItemSacola.adicionar(
        db,
        sacola_id=sacola.id,
        produto_id=produto.id,
        quantidade=dados.quantidade,
    )

    sacola.atualizado_em = datetime.now()
    db.commit()
    db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)


@router.put(
    "/itens/{produto_id}",
    response_model=SacolaOut,
    summary="Alterar quantidade de produto da cesta",
)
def alterar_quantidade_cesta(
    produto_id: int,
    dados: ItemSacolaQuantidade,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Altera a quantidade de um produto da cesta."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cesta nao encontrada.",
        )

    item = ItemSacola.buscar_por_produto(
        db,
        sacola.id,
        produto_id,
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado na cesta.",
        )

    produto = Produto.buscar_por_id(db, produto_id)

    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado.",
        )

    validar_disponibilidade(produto)
    validar_quantidade(dados.quantidade)
    validar_restaurante_cesta(db, sacola, produto)

    item.quantidade = dados.quantidade
    sacola.atualizado_em = datetime.now()

    db.commit()
    db.refresh(item)
    db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)


@router.delete(
    "/itens/{produto_id}",
    response_model=SacolaOut,
    summary="Excluir produto da cesta",
)
def excluir_produto_cesta(
    produto_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> SacolaOut:
    """Exclui um produto da cesta do usuario autenticado."""

    sacola = Sacola.buscar_por_cliente(db, usuario_logado.id)

    if sacola is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cesta nao encontrada.",
        )

    item = ItemSacola.buscar_por_produto(
        db,
        sacola.id,
        produto_id,
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado na cesta.",
        )

    item.remover(db)

    sacola.atualizado_em = datetime.now()
    db.commit()
    db.refresh(sacola)

    return montar_resposta_cesta(db, sacola)
