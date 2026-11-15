"""Código de barras dos produtos (Backlog — Leitor de código de barras).

O restaurante lê com a câmera o código da embalagem (ou digita) e o item do
cardápio guarda esse número. Assim, para registrar entrada de estoque ou
achar um item, basta ler o código.

Aceita os códigos GTIN usados no varejo: EAN-8, UPC-A (12), EAN-13 (o padrão
no Brasil) e GTIN-14, sempre conferindo o dígito verificador (o último), para
recusar leitura ou digitação errada.
"""

TAMANHOS_GTIN = (8, 12, 13, 14)


def normalizar(texto: str | None) -> str | None:
    """Tira espaços, pontos e traços. Vazio vira None (item sem código)."""

    if texto is None:
        return None
    digitos = "".join(c for c in str(texto) if not c.isspace() and c not in ".-")
    return digitos or None


def digito_verificador(sem_dv: str) -> int:
    """Dígito verificador GTIN (módulo 10): da direita para a esquerda, pesos 3 e 1."""

    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(sem_dv)))
    return (10 - soma % 10) % 10


def problema(codigo: str) -> str | None:
    """Mensagem do erro, ou None se o código é um GTIN válido."""

    if not codigo.isdigit():
        return "O código de barras deve ter só números."
    if len(codigo) not in TAMANHOS_GTIN:
        return "O código de barras deve ter 8, 12, 13 ou 14 dígitos (EAN-8, UPC, EAN-13 ou GTIN-14)."
    if digito_verificador(codigo[:-1]) != int(codigo[-1]):
        return "Código de barras inválido: o dígito verificador não confere. Leia ou digite de novo."
    return None


def validar(texto: str | None) -> str | None:
    """Normaliza e valida (para os schemas). Levanta ValueError com a mensagem."""

    codigo = normalizar(texto)
    if codigo is None:
        return None
    erro = problema(codigo)
    if erro:
        raise ValueError(erro)
    return codigo
