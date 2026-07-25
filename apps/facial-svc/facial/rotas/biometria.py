"""As tres operacoes biometricas do servico. Stubs na Fase 0.

`POST /enroll`
    Extrai o vetor de uma foto e devolve o **template** para quem for persistir.
`POST /verificar`
    Compara uma captura ao vivo contra um ou mais templates e devolve veredito.
`POST /liveness`
    Julga se o que esta diante da camera e uma pessoa viva, e nao foto, video ou
    mascara.

Onde a implementacao vem
------------------------

Decisao **D4** de `PROJETO.md`: reaproveitar o projeto **`analise-facial-edge`**
(InsightFace / ArcFace ONNX), self-hosted. Nao ha chamada a servico de terceiro,
nao ha custo por chamada e — o que decide — **a biometria nao sai da
infraestrutura da SEEG**. Este pacote e o wrapper HTTP: recebe imagem, chama o
motor, devolve resultado. O motor entra na F2 (enrollment) e e exercitado pela
F7 (captura no app) e pela F8 (captura por webcam).

O que ADR-006 impoe a este arquivo
----------------------------------

1. **Imagem crua nunca e persistida.** Ela existe em memoria pelo tempo da
   extracao e e descartada. Nada de arquivo temporario em disco "so para
   depurar": em servico biometrico, arquivo temporario e vazamento com data
   marcada. Se a politica do cliente exigir reter a imagem para contestacao,
   quem guarda e o MinIO, cifrado, com prazo curto e expurgo automatico — e
   nunca por padrao.
2. **O vetor e versionado pelo modelo.** Toda resposta de `/enroll` carrega
   `modeloVersao`. Vetores de motores diferentes nao sao comparaveis, e sem esse
   carimbo trocar o motor invalidaria a base biometrica inteira em silencio.
3. **O vetor nunca vaza em log nem em erro.** Ele sai no corpo da resposta para
   quem cifra, e so.
4. **O limiar nunca aparece na resposta.** Os `PONTO-SCORE-*` sao
   `expoe_regra: false`: quem esta testando mascara nao pode descobrir quanto
   falta para passar.
5. **Consentimento e pre-requisito, e nao e verificado aqui.** Quem checa
   `consentimentos` e a API, que tem o banco; este servico nao tem credencial de
   banco de proposito. `PONTO-LGPD-001` esta no recorte do catalogo porque a API
   pode propagar a recusa, nao porque o julgamento acontece aqui.

Formato da imagem
-----------------

A imagem chega em base64 no corpo JSON, e nao como `multipart/form-data`. A
razao e pratica: o chamador e sempre outro servico nosso (a API ou o device-gw),
o payload e pequeno (uma foto de rosto recortada), e JSON mantem a requisicao
homogenea com o resto do sistema. O teto de tamanho e `FACIAL_TAMANHO_MAXIMO_BYTES`
e o tipo e conferido contra `FACIAL_TIPOS_ACEITOS` **antes** de qualquer
decodificacao — decodificar imagem vinda de fora sem conferir antes e superficie
de ataque classica.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, status

from facial.erros import RESPOSTAS_PADRAO, NaoImplementado
from facial.log import obter_logger

logger = obter_logger("biometria")

roteador = APIRouter(tags=["biometria"], responses=RESPOSTAS_PADRAO)

CorpoCaptura = Annotated[
    dict[str, Any],
    Body(
        description=(
            "Envelope da captura. A imagem vai em base64; o conteudo nunca e "
            "registrado em log nem devolvido em mensagem de erro."
        )
    ),
]


@roteador.post(
    "/enroll",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="enroll",
    summary="Extrai o template biometrico de uma imagem",
)
async def enroll(corpo: CorpoCaptura) -> dict[str, Any]:
    """Extrai o vetor de arquivo (*template*) de uma foto de rosto.

    **Requisicao prevista**::

        {"imagemBase64": "<jpeg em base64>",
         "mimeType": "image/jpeg",
         "referencia": "<id opaco da operacao, para correlacionar log>"}

    `referencia` e um identificador **opaco**, escolhido pelo chamador: serve
    para amarrar esta chamada ao registro em `acessos_dados_sensiveis` sem que o
    facial-svc precise saber quem e o titular. Este servico nao recebe CPF, nome
    nem identificador de colaborador — e nao precisa deles para extrair um vetor.

    **Resposta prevista**::

        {"template": "<vetor serializado>",
         "dimensao": 512,
         "modeloVersao": "arcface-r100-v1",
         "qualidade": {"nitidez": 0.87, "iluminacao": 0.79, "poseOk": true},
         "duracaoMs": 41}

    O bloco `qualidade` e o que permite ao app dizer "chegue mais perto" em vez
    de "falhou": recusar a foto por qualidade ruim no momento da captura custa
    dois segundos; descobrir isso meses depois, quando o reconhecimento falha
    todo dia com o colaborador, custa a confianca no sistema.

    **O que a implementacao fara** (F2): detectar o rosto, recusar imagem com
    zero ou mais de um rosto, alinhar, extrair o embedding com ArcFace, medir
    qualidade, descartar a imagem e devolver o vetor. O que ela **nao** fara:
    gravar a imagem, gravar o vetor, ou registrar qualquer um dos dois em log.
    """
    logger.info(
        "enroll recebido (stub)",
        # `sorted(corpo)` registra os NOMES dos campos, nunca os valores: o
        # valor de `imagemBase64` e a propria biometria.
        extra={"camposRecebidos": sorted(corpo)},
    )
    raise NaoImplementado("enroll", fase="F2")


@roteador.post(
    "/verificar",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="verificar",
    summary="Compara uma captura ao vivo contra templates conhecidos",
)
async def verificar(corpo: CorpoCaptura) -> dict[str, Any]:
    """Compara a captura contra um ou mais templates e devolve o veredito.

    **Requisicao prevista**::

        {"imagemBase64": "<jpeg em base64>",
         "mimeType": "image/jpeg",
         "templates": ["<vetor 1>", "<vetor 2>"],
         "modeloVersao": "arcface-r100-v1",
         "referencia": "<id opaco da operacao>"}

    A lista de `templates` existe porque um colaborador pode ter mais de um
    enrollment valido (reenrollment apos mudanca de aparencia, cadastro pelo app
    e pelo terminal). Comparar contra todos e devolver o melhor evita o falso
    negativo mais comum e mais irritante do sistema.

    `modeloVersao` e **obrigatorio** e conferido: comparar um vetor gerado por
    um motor com outro gerado por motor diferente nao devolve "menos parecido",
    devolve numero sem significado. Divergencia de versao e erro, nao aviso.

    **Resposta prevista**::

        {"aprovado": true,
         "indice": 0,
         "modeloVersao": "arcface-r100-v1",
         "duracaoMs": 33}

    Repare no que **nao** esta na resposta: o valor da similaridade e o limiar.
    `PONTO-SCORE-003` tem `expoe_regra: false`, e o motivo e concreto — quem
    esta testando mascara impressa nao pode receber o placar da tentativa e
    iterar ate acertar. O numero vai para a auditoria, nao para o chamador.

    Reprovacao **nao** e 200 com `aprovado: false` na borda: quando quem chamou
    e um fluxo de registro de ponto, a resposta correta e `403 PONTO-SCORE-003`,
    sem `detail`. O campo `aprovado` existe para o caso de uso interno de
    comparacao em lote (deduplicacao de cadastro, por exemplo).
    """
    logger.info("verificar recebido (stub)", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("verificar", fase="F2")


@roteador.post(
    "/liveness",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="liveness",
    summary="Julga prova de vida (passiva e desafio ativo)",
)
async def liveness(corpo: CorpoCaptura) -> dict[str, Any]:
    """Julga se ha uma pessoa viva diante da camera.

    **Requisicao prevista**::

        {"quadrosBase64": ["<quadro 1>", "<quadro 2>", "..."],
         "mimeType": "image/jpeg",
         "desafio": {"tipo": "piscar", "emitidoEm": "2026-07-25T09:00:00-03:00"},
         "referencia": "<id opaco da operacao>"}

    Sao **quadros**, no plural, e nao uma foto: prova de vida sobre imagem
    estatica unica e ilusao de seguranca. O criterio de aceite da F7 e explicito
    — *"foto impressa e video em tela reprovam na prova de vida"* —, e nenhum dos
    dois e detectavel de forma confiavel num unico quadro.

    Duas camadas, como `PROJETO.md` secao 3.2 descreve:

    * **Desafio ativo**: piscar, virar a cabeca. Barato e eficaz contra foto
      impressa. O desafio e emitido pelo servidor, tem prazo curto e nao pode
      ser reaproveitado — desafio previsivel e desafio derrotado.
    * **Analise passiva**: textura, reflexo, moire de tela, coerencia de
      profundidade. E o que pega video reproduzido em celular, que passa
      tranquilamente no desafio ativo.

    **Resposta prevista**::

        {"aprovado": true,
         "sinais": {"desafioCumprido": true, "texturaOk": true, "moireDetectado": false},
         "duracaoMs": 88}

    O bloco `sinais` **fica no servidor**: alimenta o score de confianca do
    ADR-008 e a auditoria. O que volta ao dispositivo e o veredito, ou
    `403 PONTO-SCORE-002` sem `detail` — dizer *qual* sinal reprovou ensina o
    fraudador a corrigir exatamente aquele.

    Camera virtual (OBS e similares) e um caso a parte, com codigo proprio
    (`PONTO-SCORE-004`) e deteccao no cliente, na F8: quando o quadro e injetado
    antes da camera, nao ha textura ruim para analisar.
    """
    logger.info("liveness recebido (stub)", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("liveness", fase="F7")
