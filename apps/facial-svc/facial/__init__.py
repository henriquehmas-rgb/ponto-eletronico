"""Servico facial self-hosted do Ponto Eletronico.

Wrapper HTTP do motor `analise-facial-edge` (InsightFace / ArcFace ONNX), que a
decisao **D4** de `PROJETO.md` manda reaproveitar em vez de contratar servico de
terceiro. A razao e dupla e nao e economica apenas: nao ha custo por chamada, e
**a biometria nao sai da infraestrutura da SEEG** — mandar rosto de colaborador
para nuvem alheia e tratamento de dado pessoal sensivel por operador que o
titular nunca autorizou (LGPD art. 5, II, e ADR-006).

Por isso o servico e **interno por definicao**: `infra/docker-compose.yml` o
mantem so na rede `ponto-interna`, sem rota no Traefik e com
`traefik.enable: "false"` explicito. Nenhuma requisicao vinda da internet chega
aqui, nem deveria conseguir.

Tres invariantes que atravessam todo este pacote
------------------------------------------------

1. **Imagem crua nunca e persistida.** A foto entra, o vetor sai, a imagem e
   descartada (ADR-006, item 4). Quando a politica do cliente exigir retencao
   para contestacao, quem guarda e o MinIO, cifrado e com prazo curto — nunca
   este servico, nunca por padrao.
2. **O vetor sai cifrado ou nao sai.** O envelope AES-256-GCM com chave fora do
   banco e responsabilidade da F2; este servico entrega o vetor a quem cifra e
   nunca o expoe em log, em resposta de erro ou em metrica.
3. **O limiar nao aparece na resposta.** `PONTO-SCORE-003` tem
   `expoe_regra: false` em `errors.yaml`: dizer "sua similaridade foi 0,39 e o
   limiar e 0,42" entrega o mapa da fraude a quem esta testando mascara.

Por que o pacote se chama `facial`, e nao `app`
-----------------------------------------------

`apps/api` ja e dono do nome de modulo `app`. O CI roda `mypy apps packages` a
partir da raiz do monorepo, e dois pacotes de mesmo nome em arvores diferentes
fazem o mypy abortar a coleta inteira ("Duplicate module named 'app'"). Como
`apps/facial-svc` tem hifen no nome, nao ha `__init__.py` intermediario que
desempate.

O `command` de `infra/docker-compose.dev.yml` continua sendo
`uvicorn app.main:app`, como declarado e congelado: o `Dockerfile` instala um
alias `app.main` na imagem, que reexporta `facial.main:app`. O alias vive so na
imagem; o repositorio nunca tem dois pacotes `app`.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
