"""Controller de pagamento do EntregaFood.

Sprint 3 - Fechar Pedido:
    - 18: tipo de pagamento (cartao, PIX ou dinheiro na entrega).
    - 19: cobranca no Asaas sandbox (cartao e PIX) e consulta do status.
    - 22: nota fiscal em PDF (emitida quando o pagamento e aprovado).

Fluxo: POST /pedidos -> PUT /pagamentos/pedidos/{id}/metodo ->
    cartao:   POST /pagamentos/cartao
    pix:      POST /pagamentos/pix e GET /pagamentos/pedidos/{id} ate "aprovado"
    dinheiro: nada; fica "a_receber" e vira "aprovado" quando o pedido e entregue.

As regras ficam em app/core/pagamento_regras.py e o gateway (Asaas ou
simulado) em app/core/pagamento_gateway.py.
"""

from datetime import datetime

import segno
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import pagamento_gateway as gateway
from app.core import pagamento_regras as regras
from app.core.database import get_db
from app.core.nota_fiscal import ao_aprovar_pagamento, gerar_pdf, montar_dados
from app.core.security import obter_usuario_logado
from app.core.status_pedido import AGUARDANDO_ACEITE, status_finalizado
from app.models.pagamento import Pagamento
from app.models.pedido import Pedido
from app.models.restaurante import Restaurante
from app.models.usuario import Usuario
from app.schemas.pagamento import (
    EscolhaPagamentoIn,
    PagadorIn,
    PagamentoCartaoIn,
    PagamentoOut,
    PagamentoPixIn,
)

router = APIRouter(prefix="/pagamentos", tags=["Pagamento"])


# ------------------------------------------------------------------ apoio


def buscar_pedido_do_usuario(
    db: Session,
    pedido_id: int,
    usuario_logado: Usuario,
) -> Pedido:
    """Busca o pedido e garante que ele pertence ao usuario autenticado."""

    pedido = Pedido.buscar_por_id(db, pedido_id)

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido nao encontrado.",
        )

    if pedido.cliente_id != usuario_logado.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao possui acesso a este pedido.",
        )

    return pedido


def buscar_pedido_para_consulta(
    db: Session,
    pedido_id: int,
    usuario_logado: Usuario,
) -> Pedido:
    """Pagamento e nota: cliente dono do pedido, restaurante dono ou admin."""

    pedido = Pedido.buscar_por_id(db, pedido_id)

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido nao encontrado.",
        )

    if pedido.cliente_id == usuario_logado.id or usuario_logado.tipo == "admin":
        return pedido

    if usuario_logado.tipo == "restaurante":
        restaurante = Restaurante.buscar_por_id(db, pedido.restaurante_id)
        if restaurante is not None and restaurante.pertence_a(usuario_logado.id):
            return pedido

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Voce nao possui acesso a este pedido.",
    )


def exigir_pedido_aguardando_pagamento(db: Session, pedido: Pedido) -> Pagamento | None:
    """O pedido precisa estar aberto e sem pagamento aprovado."""

    if status_finalizado(pedido.status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O pedido ja foi finalizado e nao aceita pagamento.",
        )

    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    if pagamento is not None and not regras.pode_refazer(pagamento.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido ja possui um pagamento.",
        )

    return pagamento


def montar_pagador(dados: PagadorIn, usuario: Usuario, *, cartao: bool) -> gateway.Pagador:
    """Dados do pagador. O Asaas exige CPF (e endereco/telefone no cartao)."""

    pagador = gateway.Pagador(
        nome=usuario.nome,
        cpf=regras.somente_digitos(dados.cpf),
        email=usuario.email,
        telefone=dados.telefone or usuario.telefone,
        cep=dados.cep,
        numero_endereco=dados.numero_endereco,
        referencia=str(usuario.id),
    )

    if not gateway.asaas_ativo():
        return pagador

    faltando = []
    if not regras.cpf_valido(dados.cpf):
        faltando.append("CPF valido")
    if cartao:
        if not dados.cep:
            faltando.append("CEP")
        if not dados.numero_endereco:
            faltando.append("numero do endereco")
        if not pagador.telefone:
            faltando.append("telefone")
        if not pagador.email:
            faltando.append("e-mail no cadastro")

    if faltando:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para pagar informe: " + ", ".join(faltando) + ".",
        )

    return pagador


def ip_do_cliente(requisicao: Request) -> str | None:
    """IP real do comprador (o Render fica na frente como proxy)."""

    encaminhado = requisicao.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()

    return requisicao.client.host if requisicao.client else None


def montar_saida(pagamento: Pagamento, pedido: Pedido) -> PagamentoOut:
    """Pagamento no formato da API (com o QR Code do PIX quando pendente)."""

    qrcode = None
    if pagamento.metodo == "pix" and pagamento.status == regras.PENDENTE and pagamento.pix_copia_cola:
        qrcode = segno.make(pagamento.pix_copia_cola, error="m").png_data_uri(scale=6, border=2)

    return PagamentoOut(
        id=pagamento.id,
        pedido_id=pagamento.pedido_id,
        metodo=pagamento.metodo,
        status=pagamento.status,
        status_rotulo=regras.rotulo(pagamento.status),
        valor=pagamento.valor,
        transacao_externa_id=pagamento.transacao_externa_id,
        mensagem=pagamento.mensagem,
        gateway="nenhum" if pagamento.metodo == "dinheiro" else gateway.nome_gateway(pagamento.transacao_externa_id),
        criado_em=pagamento.criado_em,
        atualizado_em=pagamento.atualizado_em,
        pix_qrcode=qrcode,
        pix_copia_cola=pagamento.pix_copia_cola if pagamento.status == regras.PENDENTE else None,
        pix_expira_em=pagamento.pix_expira_em,
        nota_fiscal=pedido.cupom_fiscal,
    )


def erro_do_gateway(erro: Exception) -> HTTPException:
    if isinstance(erro, gateway.AsaasIndisponivel):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de pagamento indisponivel. Tente novamente em instantes.",
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Pagamento nao realizado: {erro}",
    )


def receber_pagamento_na_entrega(
    db: Session,
    pedido: Pedido,
    tarefas: BackgroundTasks | None,
) -> None:
    """Dinheiro: ao confirmar a entrega, o pagamento "a_receber" vira "aprovado".

    Chamado por pedido_controller.confirmar_entrega.
    """

    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    if pagamento is None or pagamento.metodo != "dinheiro" or pagamento.status != regras.A_RECEBER:
        return

    pagamento.atualizar_status(db, status=regras.APROVADO, mensagem="Recebido em dinheiro na entrega.")
    ao_aprovar_pagamento(db, pedido, tarefas)


# ------------------------------------------------------------------ rotas


@router.put(
    "/pedidos/{pedido_id}/metodo",
    summary="Escolher tipo de pagamento",
)
def escolher_tipo_pagamento(
    pedido_id: int,
    dados: EscolhaPagamentoIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> dict[str, str | int | None]:
    """Define o tipo de pagamento do pedido: cartao, pix ou dinheiro.

    Dinheiro na entrega nao passa pelo gateway: o pagamento ja fica
    "a_receber" e o restaurante pode aceitar o pedido. Trocar de metodo
    cancela a cobranca anterior ainda nao paga (ex.: um PIX pendente).
    """

    pedido = buscar_pedido_do_usuario(db, pedido_id, usuario_logado)
    pagamento = exigir_pedido_aguardando_pagamento(db, pedido)

    if pedido.status != AGUARDANDO_ACEITE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O metodo so pode ser trocado antes do restaurante aceitar o pedido.",
        )

    pedido.definir_forma_pagamento(db, dados.metodo)
    trocou = pagamento is not None and pagamento.metodo != dados.metodo

    if trocou and pagamento.status == regras.PENDENTE:
        gateway.cancelar(pagamento.transacao_externa_id)

    if dados.metodo == "dinheiro":
        pagamento = Pagamento.registrar_tentativa(
            db,
            pedido_id=pedido.id,
            metodo="dinheiro",
            valor=pedido.valor_total,
            status=regras.A_RECEBER,
            mensagem="Pagamento em dinheiro na entrega.",
        )
    elif trocou:
        pagamento = Pagamento.registrar_tentativa(
            db,
            pedido_id=pedido.id,
            metodo=dados.metodo,
            valor=pedido.valor_total,
            status=regras.CANCELADO,
            mensagem="Metodo de pagamento alterado pelo cliente.",
        )

    return {
        "pedido_id": pedido.id,
        "metodo": pedido.forma_pagamento,
        "pagamento_status": pagamento.status if pagamento else None,
        "mensagem": "Tipo de pagamento definido com sucesso.",
    }


@router.post(
    "/cartao",
    response_model=PagamentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pagar com cartao de credito",
)
def pagar_com_cartao(
    dados: PagamentoCartaoIn,
    requisicao: Request,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PagamentoOut:
    """Cobra o pedido no cartao (Asaas sandbox ou gateway simulado).

    Cartao recusado devolve o pagamento com status "recusado" e o motivo
    em `mensagem`; o pedido continua aguardando pagamento e o cliente pode
    tentar de novo. Os dados do cartao nao sao gravados.
    """

    pedido = buscar_pedido_do_usuario(db, dados.pedido_id, usuario_logado)

    if pedido.forma_pagamento != "cartao":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O tipo de pagamento do pedido deve ser cartao.",
        )

    exigir_pedido_aguardando_pagamento(db, pedido)

    if gateway.asaas_ativo() and dados.cartao is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe os dados do cartao.",
        )

    pagador = montar_pagador(dados, usuario_logado, cartao=True)
    cartao = None
    if dados.cartao is not None:
        cartao = gateway.DadosCartao(**dados.cartao.model_dump())

    try:
        resultado = gateway.cobrar_cartao(
            valor=pedido.valor_total,
            pagador=pagador,
            cartao=cartao,
            descricao=f"EntregaFood - pedido #{pedido.id}",
            referencia=f"pedido-{pedido.id}",
            ip_remoto=ip_do_cliente(requisicao),
        )
    except (gateway.AsaasErro, gateway.AsaasIndisponivel) as erro:
        raise erro_do_gateway(erro) from erro

    pagamento = Pagamento.registrar_tentativa(
        db,
        pedido_id=pedido.id,
        metodo="cartao",
        valor=pedido.valor_total,
        status=resultado.status,
        transacao_externa_id=resultado.transacao_externa_id,
        mensagem=resultado.mensagem,
    )

    if pagamento.status == regras.APROVADO:
        ao_aprovar_pagamento(db, pedido, tarefas)

    return montar_saida(pagamento, pedido)


@router.post(
    "/pix",
    response_model=PagamentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar cobranca PIX",
)
def pagar_com_pix(
    dados: PagamentoPixIn,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PagamentoOut:
    """Gera o QR Code e o "copia e cola" do PIX do pedido.

    O pagamento fica "pendente" ate o cliente pagar; consulte em
    GET /pagamentos/pedidos/{pedido_id}. Chamar de novo gera um PIX novo.
    """

    pedido = buscar_pedido_do_usuario(db, dados.pedido_id, usuario_logado)

    if pedido.forma_pagamento != "pix":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O tipo de pagamento do pedido deve ser pix.",
        )

    anterior = exigir_pedido_aguardando_pagamento(db, pedido)
    pagador = montar_pagador(dados, usuario_logado, cartao=False)

    if anterior is not None and anterior.status == regras.PENDENTE:
        gateway.cancelar(anterior.transacao_externa_id)

    try:
        resultado = gateway.criar_pix(
            valor=pedido.valor_total,
            pedido_id=pedido.id,
            pagador=pagador,
            descricao=f"EntregaFood - pedido #{pedido.id}",
            referencia=f"pedido-{pedido.id}",
        )
    except (gateway.AsaasErro, gateway.AsaasIndisponivel) as erro:
        raise erro_do_gateway(erro) from erro

    pagamento = Pagamento.registrar_tentativa(
        db,
        pedido_id=pedido.id,
        metodo="pix",
        valor=pedido.valor_total,
        status=resultado.status,
        transacao_externa_id=resultado.transacao_externa_id,
        mensagem=resultado.mensagem,
        pix_copia_cola=resultado.pix_copia_cola,
        pix_expira_em=resultado.pix_expira_em,
    )

    saida = montar_saida(pagamento, pedido)
    if resultado.pix_qrcode:
        saida.pix_qrcode = resultado.pix_qrcode  # imagem oficial do Asaas

    return saida


@router.get(
    "/pedidos/{pedido_id}",
    response_model=PagamentoOut,
    summary="Consultar pagamento do pedido",
)
def consultar_pagamento(
    pedido_id: int,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PagamentoOut:
    """Pagamento do pedido. Se estiver pendente, atualiza o status no Asaas.

    E o "ja paguei" da tela do PIX: quando o Asaas confirma, o pagamento
    vira "aprovado" e a nota fiscal e emitida.
    """

    pedido = buscar_pedido_para_consulta(db, pedido_id, usuario_logado)
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    if pagamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este pedido ainda nao possui pagamento.",
        )

    if pagamento.status == regras.PENDENTE:
        try:
            novo_status = gateway.consultar_status(pagamento.transacao_externa_id)
        except (gateway.AsaasErro, gateway.AsaasIndisponivel) as erro:
            raise erro_do_gateway(erro) from erro

        if novo_status is None and pagamento.pix_expira_em and pagamento.pix_expira_em < datetime.now():
            novo_status = regras.EXPIRADO  # PIX simulado vencido

        if novo_status and novo_status != pagamento.status:
            pagamento.atualizar_status(db, status=novo_status, mensagem=regras.rotulo(novo_status))
            if novo_status == regras.APROVADO:
                ao_aprovar_pagamento(db, pedido, tarefas)

    return montar_saida(pagamento, pedido)


@router.post(
    "/pedidos/{pedido_id}/pix/simular-pagamento",
    response_model=PagamentoOut,
    summary="Simular PIX pago (somente sandbox / gateway simulado)",
)
def simular_pix_pago(
    pedido_id: int,
    tarefas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> PagamentoOut:
    """Marca o PIX como pago, para testar sem um app de banco.

    No Asaas sandbox registra o recebimento da cobranca; no gateway
    simulado aprova direto. Desligada com o Asaas de producao.
    """

    if not gateway.simulacao_permitida():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulacao indisponivel neste ambiente.",
        )

    pedido = buscar_pedido_do_usuario(db, pedido_id, usuario_logado)
    pagamento = Pagamento.buscar_por_pedido(db, pedido.id)

    if pagamento is None or pagamento.metodo != "pix" or pagamento.status != regras.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O pedido nao possui um PIX pendente.",
        )

    try:
        novo_status = gateway.simular_pagamento_pix(pagamento.transacao_externa_id, pagamento.valor)
    except (gateway.AsaasErro, gateway.AsaasIndisponivel) as erro:
        raise erro_do_gateway(erro) from erro

    pagamento.atualizar_status(db, status=novo_status, mensagem=regras.rotulo(novo_status))
    if novo_status == regras.APROVADO:
        ao_aprovar_pagamento(db, pedido, tarefas)

    return montar_saida(pagamento, pedido)


@router.get(
    "/pedidos/{pedido_id}/nota-fiscal",
    summary="Baixar a nota fiscal (PDF) do pedido",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def baixar_nota_fiscal(
    pedido_id: int,
    db: Session = Depends(get_db),
    usuario_logado: Usuario = Depends(obter_usuario_logado),
) -> Response:
    """PDF da nota fiscal simulada. So o cliente dono, o restaurante dono e o admin."""

    pedido = buscar_pedido_para_consulta(db, pedido_id, usuario_logado)

    if not pedido.cupom_fiscal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A nota fiscal e emitida quando o pagamento e aprovado.",
        )

    pdf = gerar_pdf(montar_dados(db, pedido))

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pedido.cupom_fiscal}.pdf"'},
    )
