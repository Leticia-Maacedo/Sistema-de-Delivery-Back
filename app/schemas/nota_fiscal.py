"""VIEW - formato da situacao da nota fiscal na API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotaFiscalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pedido_id: int
    provedor: str
    ambiente: str
    referencia: str
    status: str
    numero: str | None = None
    serie: str | None = None
    chave: str | None = None
    protocolo: str | None = None
    url_danfe: str | None = None
    mensagem: str | None = None
    tentativas: int
    proxima_tentativa_em: datetime | None = None
    atualizado_em: datetime | None = None
