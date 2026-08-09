"""As tres operacoes biometricas do servico.

`POST /enroll`
    Extrai o vetor de uma foto e devolve o **template** para quem for persistir.
`POST /verificar`
    Compara uma captura ao vivo contra um ou mais templates e devolve veredito.
`POST /liveness`
    Julga se o que esta diante da camera e uma pessoa viva, e nao foto, video ou
    mascara.

De onde vem a implementacao
---------------------------

Decisao **D4** de `PROJETO.md`: motor **self-hosted**, nao SaaS. O motor mora em
`facial/motor/` — InsightFace `buffalo_l` (RetinaFace `det_10g` + ArcFace
`w600k_r50`, 512-d) sobre ONNX Runtime **CPU**. Nao ha chamada a servico de
terceiro, nao ha custo por chamada e — o que decide — **a biometria nao sai da
infraestrutura da SEEG**. Este modulo e o wrapper HTTP: valida envelope, chama o
motor, traduz o resultado para o contrato.

Este arquivo **nao importa numpy, OpenCV nem InsightFace**. A fronteira e
`facial.motor`, e ela existe para que trocar o motor (decisao prevista, e a
razao de `modeloVersao` existir) nao encoste no contrato HTTP.

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
   `/verificar` **confere** a versao recebida contra a configurada e recusa a
   divergencia: e erro, nao aviso.
3. **O vetor nunca vaza em log nem em erro.** Ele sai no corpo da resposta para
   quem cifra, e so.
4. **O limiar nunca aparece na resposta.** Os `PONTO-SCORE-*` sao
   `expoe_regra: false`: quem esta testando mascara nao pode descobrir quanto
   falta para passar. Nem o limiar, nem a similaridade obtida.
5. **Consentimento e pre-requisito, e nao e verificado aqui.** Quem checa
   `consentimentos` e a API, que tem o banco; este servico nao tem credencial de
   banco de proposito.

Estado nao persistido
---------------------

Este servico continua **sem estado**: `/enroll` devolve o template, nao o grava.
Quem cifra e grava (`biometria_templates`) e `apps/api`, que tem banco e chave.
Um servico que nao tem credencial nao vaza credencial, mesmo comprometido.

Formato da imagem
-----------------

A imagem chega em base64 no corpo JSON, e nao como `multipart/form-data`. A
razao e pratica: o chamador e sempre outro servico nosso (a API ou o device-gw),
o payload e pequeno (uma foto de rosto recortada), e JSON mantem a requisicao
homogenea com o resto do sistema. O teto de tamanho e `FACIAL_TAMANHO_MAXIMO_BYTES`
e o tipo e conferido contra `FACIAL_TIPOS_ACEITOS` **antes** de qualquer
decodificacao — decodificar imagem vinda de fora sem conferir antes e superficie
de ataque classica.

Trabalho pesado fora do laco de eventos
---------------------------------------

Deteccao e embedding sao chamadas bloqueantes de ONNX Runtime, na casa das
dezenas de milissegundos. Rodar isso direto numa corrotina travaria o laco de
eventos do uvicorn para **todas** as requisicoes concorrentes; por isso cada
operacao vai para o pool de threads via `anyio.to_thread.run_sync`.
"""

from __future__ import annotations

import time

import anyio.to_thread
from fastapi import APIRouter, status

from facial.config import obter_configuracao
from facial.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from facial.esquemas import (
    CorpoEnroll,
    CorpoLiveness,
    CorpoVerificar,
    RespostaEnroll,
    RespostaLiveness,
    RespostaVerificar,
)
from facial.log import obter_logger
from facial.motor import (
    DIMENSAO_EMBEDDING,
    decodificar_imagem,
    desserializar_template,
    julgar_liveness,
    melhor_correspondencia,
    motor,
    serializar_template,
)

logger = obter_logger("biometria")

roteador = APIRouter(tags=["biometria"], responses=RESPOSTAS_PADRAO)


def _ms(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)


@roteador.post(
    "/enroll",
    status_code=status.HTTP_200_OK,
    operation_id="enroll",
    summary="Extrai o template biometrico de uma imagem",
    response_model=RespostaEnroll,
)
async def enroll(corpo: CorpoEnroll) -> RespostaEnroll:
    """Extrai o vetor de arquivo (*template*) de uma foto de rosto.

    **Requisicao**::

        {"imagemBase64": "<jpeg em base64>",
         "mimeType": "image/jpeg",
         "referencia": "<id opaco da operacao, para correlacionar log>"}

    **Resposta**::

        {"template": "<512 float32 little-endian em base64>",
         "dimensao": 512,
         "modeloVersao": "buffalo_l-w600k_r50-v1",
         "qualidade": {"nitidez": 0.87, "iluminacao": 0.79, "poseOk": true,
                       "deteccao": 0.94},
         "duracaoMs": 41}

    O bloco `qualidade` e o que permite ao app dizer "chegue mais perto" em vez
    de "falhou": recusar a foto por qualidade ruim no momento da captura custa
    dois segundos; descobrir isso meses depois, quando o reconhecimento falha
    todo dia com o colaborador, custa a confianca no sistema.

    **Exatamente um rosto.** Zero rostos e `400 PONTO-VAL-001`; dois ou mais
    tambem. A exigencia parece dura, e e a que evita o pior defeito possivel
    nesta base: cadastrar em nome de um colaborador o rosto do colega que
    apareceu atras dele no enquadramento. Na verificacao a regra e outra — la o
    terceiro ao fundo nao pode reprovar quem esta marcando ponto.

    O que esta operacao **nao** faz: gravar a imagem, gravar o vetor, ou
    registrar qualquer um dos dois em log.
    """
    inicio = time.perf_counter()
    config = obter_configuracao()
    logger.info(
        "enroll recebido",
        # Os NOMES dos campos, nunca os valores: o valor de `imagemBase64` e a
        # propria biometria.
        extra={"referencia": corpo.referencia, "mimeType": corpo.mime_type},
    )

    def _trabalho() -> tuple[str, dict[str, float | bool]]:
        imagem = decodificar_imagem(corpo.imagem_base64, corpo.mime_type, config)
        rosto = motor().rosto_unico(imagem, exigir_unico=True)
        return serializar_template(rosto.embedding), rosto.qualidade

    template, qualidade = await anyio.to_thread.run_sync(_trabalho)

    duracao = _ms(inicio)
    logger.info(
        "enroll concluido",
        extra={
            "referencia": corpo.referencia,
            "modeloVersao": config.facial_model_versao,
            "duracaoMs": duracao,
            # Qualidade e agregado da captura, nao biometria: pode ser registrado
            # e e o que responde "as capturas do terminal 3 estao ruins?".
            "poseOk": qualidade.get("poseOk"),
        },
    )
    return RespostaEnroll(
        template=template,
        dimensao=DIMENSAO_EMBEDDING,
        modelo_versao=config.facial_model_versao,
        qualidade=dict(qualidade),
        duracao_ms=duracao,
    )


@roteador.post(
    "/verificar",
    status_code=status.HTTP_200_OK,
    operation_id="verificar",
    summary="Compara uma captura ao vivo contra templates conhecidos",
    response_model=RespostaVerificar,
)
async def verificar(corpo: CorpoVerificar) -> RespostaVerificar:
    """Compara a captura contra um ou mais templates e devolve o veredito.

    **Requisicao**::

        {"imagemBase64": "<jpeg em base64>",
         "mimeType": "image/jpeg",
         "templates": ["<vetor 1>", "<vetor 2>"],
         "modeloVersao": "buffalo_l-w600k_r50-v1",
         "referencia": "<id opaco da operacao>",
         "exigirAprovacao": false}

    A lista de `templates` existe porque um colaborador pode ter mais de um
    enrollment valido (reenrollment apos mudanca de aparencia, cadastro pelo app
    e pelo terminal). Comparar contra todos e devolver o melhor evita o falso
    negativo mais comum e mais irritante do sistema.

    `modeloVersao` e **obrigatorio** e conferido: comparar um vetor gerado por
    um motor com outro gerado por motor diferente nao devolve "menos parecido",
    devolve numero sem significado. Divergencia de versao e erro, nao aviso.

    **Resposta**::

        {"aprovado": true, "indice": 0,
         "modeloVersao": "buffalo_l-w600k_r50-v1", "duracaoMs": 33}

    Repare no que **nao** esta na resposta: o valor da similaridade e o limiar.
    `PONTO-SCORE-003` tem `expoe_regra: false`, e o motivo e concreto — quem
    esta testando mascara impressa nao pode receber o placar da tentativa e
    iterar ate acertar. O numero vai para a auditoria, nao para o chamador.

    Com `exigirAprovacao: true` — que e como um fluxo de registro de ponto deve
    chamar —, reprovacao vira `403 PONTO-SCORE-003` sem `detail`. O 200 com
    `aprovado: false` existe para o caso de uso interno de comparacao em lote
    (deduplicacao de cadastro, por exemplo).

    A similaridade e comparada com `FACIAL_LIMIAR_SIMILARIDADE` (padrao 0,42).
    Para ArcFace, a faixa util de 1:1 com FAR baixo fica entre 0,30 e 0,45 em
    cosseno; 0,42 fica no lado conservador dela de proposito. Falso positivo em
    biometria de ponto e fraude trabalhista; falso negativo e um segundo pedido
    de nova captura. Os dois erros nao custam a mesma coisa, e o limiar reflete
    isso. Ele e por cliente: a relacao entre os dois nao e a mesma numa portaria
    com 30 pessoas e num chao de fabrica com 3.000.
    """
    inicio = time.perf_counter()
    config = obter_configuracao()
    logger.info(
        "verificar recebido",
        extra={"referencia": corpo.referencia, "templates": len(corpo.templates)},
    )

    if corpo.modelo_versao != config.facial_model_versao:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=(
                f"`modeloVersao` divergente: os templates foram gerados por "
                f"'{corpo.modelo_versao}' e este servico roda "
                f"'{config.facial_model_versao}'. Vetores de motores diferentes "
                f"nao sao comparaveis; e preciso reenrollment."
            ),
            contexto_log={
                "etapa": "versao",
                "recebida": corpo.modelo_versao,
                "configurada": config.facial_model_versao,
            },
        )

    def _trabalho() -> tuple[int, float]:
        referencias = [
            desserializar_template(bruto, indice=i) for i, bruto in enumerate(corpo.templates)
        ]
        imagem = decodificar_imagem(corpo.imagem_base64, corpo.mime_type, config)
        # `exigir_unico=False`: um terceiro passando ao fundo do terminal nao pode
        # reprovar quem esta marcando ponto. Vale o rosto de maior area, que e o
        # de quem esta na frente da camera.
        rosto = motor().rosto_unico(imagem, exigir_unico=False)
        return melhor_correspondencia(rosto.embedding, referencias)

    indice, similaridade = await anyio.to_thread.run_sync(_trabalho)
    aprovado = similaridade >= config.facial_limiar_similaridade
    duracao = _ms(inicio)

    # O log registra o VEREDITO, nunca o escore nem o limiar (ADR-006, regra 4).
    # Quem precisar auditar o caso concreto vai a `acessos_dados_sensiveis`.
    logger.info(
        "verificar concluido",
        extra={
            "referencia": corpo.referencia,
            "aprovado": aprovado,
            "indice": indice if aprovado else -1,
            "modeloVersao": config.facial_model_versao,
            "duracaoMs": duracao,
        },
    )

    if not aprovado and corpo.exigir_aprovacao:
        raise ErroDeAplicacao(
            "PONTO-SCORE-003",
            # `detalhe` e montado, mas `PONTO-SCORE-003` tem `expoe_regra: false`
            # e `montar_problema` o descarta da resposta. Ele existe para o log.
            detalhe="Similaridade abaixo do limiar configurado.",
            contexto_log={"referencia": corpo.referencia, "etapa": "comparacao"},
        )

    return RespostaVerificar(
        aprovado=aprovado,
        # Indice de um no-match nao diz nada e insinua "voce quase bateu com este
        # aqui". -1 quando reprovado.
        indice=indice if aprovado else -1,
        modelo_versao=config.facial_model_versao,
        duracao_ms=duracao,
    )


@roteador.post(
    "/liveness",
    status_code=status.HTTP_200_OK,
    operation_id="liveness",
    summary="Julga prova de vida (analise passiva multi-quadro)",
    response_model=RespostaLiveness,
)
async def liveness(corpo: CorpoLiveness) -> RespostaLiveness:
    """Julga se ha uma pessoa viva diante da camera.

    **Requisicao**::

        {"quadrosBase64": ["<quadro 1>", "<quadro 2>", "..."],
         "mimeType": "image/jpeg",
         "desafio": {"tipo": "piscar", "emitidoEm": "2026-07-25T09:00:00-03:00"},
         "referencia": "<id opaco da operacao>",
         "exigirAprovacao": false}

    Sao **quadros**, no plural, e nao uma foto: prova de vida sobre imagem
    estatica unica e ilusao de seguranca. Menos de `FACIAL_LIVENESS_MIN_QUADROS`
    (padrao 2) reprova direto.

    **Resposta**::

        {"aprovado": true,
         "sinais": {"rostoEmTodos": true, "desafioCumprido": true,
                    "texturaOk": true, "moireDetectado": false},
         "quadrosAnalisados": 3,
         "duracaoMs": 88}

    O bloco `sinais` alimenta o score de confianca do ADR-008 e a auditoria; ele
    e booleano de ponta a ponta, sem nenhum numero — dizer *por quanto* um sinal
    reprovou ensina o fraudador a corrigir exatamente aquele. Com
    `exigirAprovacao: true`, reprovacao vira `403 PONTO-SCORE-002` sem `detail`.

    **Limitacao declarada, e ela e normativa.** O que roda aqui e um conjunto de
    heuristicas classicas multi-quadro (movimento entre quadros, textura de alta
    frequencia, moire de tela), e **nao** um classificador de anti-spoofing
    treinado. Ele pega foto impressa parada, quadro repetido e tela com moire
    visivel; nao substitui um modelo dedicado contra mascara ou tela de alta
    densidade. Enquanto for a unica prova de vida do sistema, o resultado e
    **sinal de confianca** (peso `peso_biometria` do ADR-008) e nao portao
    suficiente sozinho. Ver `facial/motor/liveness.py` para o porque de o
    classificador dedicado nao ter entrado nesta rodada.

    Camera virtual (OBS e similares) e um caso a parte, com codigo proprio
    (`PONTO-SCORE-004`) e deteccao no cliente, na F8: quando o quadro e injetado
    antes da camera, nao ha textura ruim para analisar.
    """
    inicio = time.perf_counter()
    config = obter_configuracao()
    logger.info(
        "liveness recebido",
        extra={
            "referencia": corpo.referencia,
            "quadros": len(corpo.quadros_base64),
            "desafio": corpo.desafio.tipo if corpo.desafio else None,
        },
    )

    def _trabalho() -> tuple[bool, dict[str, bool], int, str]:
        quadros = [
            decodificar_imagem(bruto, corpo.mime_type, config) for bruto in corpo.quadros_base64
        ]
        laudo = julgar_liveness(quadros, motor(), config)
        return laudo.aprovado, laudo.sinais, laudo.quadros_analisados, laudo.motivo_interno

    aprovado, sinais, analisados, motivo = await anyio.to_thread.run_sync(_trabalho)
    duracao = _ms(inicio)

    logger.info(
        "liveness concluido",
        extra={
            "referencia": corpo.referencia,
            "aprovado": aprovado,
            "quadrosAnalisados": analisados,
            "duracaoMs": duracao,
        },
    )

    if not aprovado and corpo.exigir_aprovacao:
        raise ErroDeAplicacao(
            "PONTO-SCORE-002",
            detalhe="Prova de vida reprovada.",
            contexto_log={"referencia": corpo.referencia, "motivo": motivo},
        )

    return RespostaLiveness(
        aprovado=aprovado,
        sinais=sinais,
        quadros_analisados=analisados,
        duracao_ms=duracao,
    )
