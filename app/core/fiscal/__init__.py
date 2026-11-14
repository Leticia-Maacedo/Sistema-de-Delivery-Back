"""Emissao fiscal do EntregaFood, separada em modulos:

- dados.py        o que vai na nota (montado a partir do pedido);
- pdf_simulado.py PDF da nota simulada, sem valor fiscal;
- provedores.py   provedor simulado e integracao real com a Focus NFe (NFC-e);
- emissao.py      emissao, rejeicao, servico fora do ar e reenvio.

O restante do sistema usa app/core/nota_fiscal.py, que chama estes modulos.
"""
