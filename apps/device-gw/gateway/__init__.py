"""Gateway dos terminais coletores Control iD (iDFace / iDBlock).

Servico HTTP separado da API principal de proposito (PROJETO.md secao 11.1):
uma rajada de terminal — 40 equipamentos religando depois de uma queda de rede e
despejando o *backlog* de `access_logs` ao mesmo tempo — nao pode derrubar a API
que o RH esta usando. O isolamento e de processo, de container e de rota
(`dev.ponto.<dominio>`, separada de `api.ponto.<dominio>`).

O que este servico e, e o que ele nao e
---------------------------------------

O iDFace **nao** e o REP-P. O REP-P e o nosso software. O terminal identifica a
pessoa e produz um `access_log`; este gateway recebe (por Push ou Monitor),
converte para marcacao canonica e entrega a API, e **e o servidor** quem atribui
o NSR e grava. Nenhuma linha deste servico atribui NSR, grava marcacao ou toca
no AFD.

Por que o pacote se chama `gateway`, e nao `app`
------------------------------------------------

`apps/api` ja e dono do nome de modulo `app`. O CI roda `mypy apps packages` a
partir da raiz do monorepo, e dois pacotes de mesmo nome em arvores diferentes
fazem o mypy abortar a coleta inteira ("Duplicate module named 'app'") — nao e
um aviso, e uma parada. Como `apps/device-gw` tem hifen no nome, nao ha
`__init__.py` intermediario que desempate. O nome unico resolve isso na origem.

O `command` de `infra/docker-compose.dev.yml` continua sendo
`uvicorn app.main:app`, como declarado e congelado: o `Dockerfile` deste
servico instala um alias `app.main` na imagem, que reexporta
`gateway.main:app`. O alias vive so na imagem; o repositorio nunca tem dois
pacotes `app`.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
