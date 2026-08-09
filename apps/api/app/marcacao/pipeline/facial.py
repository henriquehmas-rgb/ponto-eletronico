"""Verificacao facial no momento da marcacao (`MarcacaoCriar.fotoBase64`).

Este modulo e o segundo dos dois callers reais do `facial-svc` (o primeiro e o
cadastro, em `app.routers.biometria`). Ate 08/08 o motor existia, estava
provado isoladamente e **nenhuma rota o chamava** (`docs/backlog.md`); o campo
`fotoBase64` do contrato chegava ate `registrar_marcacao` e era simplesmente
ignorado, com `score_facial=None` gravado em `marcacoes_meta`.

Tres desfechos, tres tratamentos
--------------------------------

======================================  =====================================
Situacao                                 O que acontece com a marcacao
======================================  =====================================
Rosto bate com o template do titular     Segue, com sinal de biometria REAL e
                                         positivo no score de confianca.
Rosto NAO bate                           `403 PONTO-SCORE-003`. Falha fechada,
                                         sem placar nem limiar na resposta
                                         (`expoe_regra: false`).
`facial-svc` fora do ar / lento          Segue SEM o sinal. Ver abaixo.
======================================  =====================================

Por que o motor fora do ar nao recusa a marcacao
------------------------------------------------

A intuicao ("biometria: na duvida, recusa") esta certa quando a duvida e sobre a
PESSOA. Nao e o caso aqui: o motor fora do ar nao produziu duvida nenhuma, ele
nao produziu nada. E ha decisao de produto registrada sobre exatamente isso,
anterior a esta implementacao, e ela e explicita:

* **ADR-008**, contexto: bloquear por sinal indisponivel "quebra na primeira
  semana de producao... o trabalhador nao registra jornada, o que e problema
  juridico da empresa, nao dele". Regra 2: entre os limiares, **grava e
  sinaliza**; so abaixo do limiar inferior recusa. Regra 7 lista os sinais
  decisivos que recusam sozinhos -- indisponibilidade de dependencia interna nao
  esta entre eles, e nao poderia estar: os tres sao evidencia de ADULTERACAO.
* **ADR-014 / `app.antifraude.motor`**: `SCORE_SEM_SINAIS = 100`, com a
  justificativa "ausencia de sinal nunca e tratada como evidencia de fraude".

Entao a resposta correta nao e inventar uma politica nova, e usar a que ja
existe: sem sinal, `app.antifraude.motor._sinais_categoria_biometria` ja
distingue os dois casos. Se a politica do tenant tem `exige_facial=true`, o sinal
ausente pontua `_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE = 40` e tipicamente joga a
marcacao na faixa de REVISAO; um tenant que queira de fato recusar so precisa
subir o proprio `limiar_bloqueio`, que e a alavanca que ADR-008 lhe deu. A
decisao continua sendo do cliente, calibrada por ele, em vez de ficar escondida
num `raise` deste modulo.

O caminho contrario tambem foi considerado e descartado: recusar a marcacao
inteira quando o NOSSO servico cai transforma um incidente de infraestrutura da
SEEG em ausencia de registro de ponto do trabalhador -- exatamente o dano que
ADR-008 existe para evitar, e sem nenhum ganho de seguranca, porque quem
fraudaria tem o caminho muito mais simples de nao enviar `fotoBase64`.

O aviso `facial_indisponivel` entra em `MarcacaoCriada.avisos` e na
explicabilidade, para que a ausencia do sinal seja visivel na auditoria em vez
de indistinguivel de uma captura que nunca foi enviada.

Prova de vida (`/liveness`): o mesmo modulo, uma decisao diferente
--------------------------------------------------------------------

Desde 09/08 este modulo tambem chama `facial-svc:/liveness`, e a tabela de tres
desfechos acima **nao** se aplica a ele. A diferenca nao e de gosto:

* `/verificar` responde "esta pessoa nao e o titular do template". Isso e
  evidencia direta de fraude de identidade, e ADR-008 regra 7 lista
  similaridade facial entre os sinais que recusam sozinhos.
* `/liveness` responde "estas heuristicas passivas nao convenceram". O proprio
  motor abre o modulo declarando o limite (`facial/motor/liveness.py`): o que
  roda ali sao heuristicas classicas multi-quadro (movimento, textura, moire),
  **nao** um classificador de anti-spoofing treinado -- pesos MiniFASNet em ONNX
  so circulam em espelhos de terceiros, e trocar risco tecnico por risco de
  cadeia de suprimentos foi recusado (`docs/backlog.md`, 08/08). A margem do
  sinal de textura, em particular, e estreita e esta medida no codigo.

Um sinal declarado falivel nao pode ser portao. Por isso a chamada usa
`exigirAprovacao: false` e a reprovacao volta como **valor** (`False`), que o
antifraude pondera na categoria `biometria` junto com os demais -- nunca como
excecao. O tenant que quiser, mesmo assim, recusar marcacao com prova de vida
reprovada tem a alavanca que ADR-008 lhe deu: subir o proprio `limiar_bloqueio`
(ou ligar `exige_liveness`, que ja penaliza a AUSENCIA do sinal). A decisao fica
com o cliente, calibrada e visivel, em vez de escondida num `raise` daqui.

De onde vem a sequencia de quadros
----------------------------------

Prova de vida sobre imagem estatica unica e ilusao de seguranca, e o motor diz
isso recusando direto abaixo de `FACIAL_LIVENESS_MIN_QUADROS` (padrao 2). Entao
`fotoBase64` -- a captura unica que alimenta `/verificar` -- **nao serve**: uma
foto so produziria `aprovado: false` estrutural, um sinal negativo sobre uma
integracao incompleta, que e exatamente o tipo de falso positivo de fraude que
ADR-014 proibe ("ausencia de sinal nunca e evidencia").

A sequencia vem de `MarcacaoCriar.livenessEvidencia`, o campo objeto de forma
livre que o contrato ja declara desde a Fase 0 com a descricao "Evidencia do
desafio de vivacidade executado" e que nenhum consumidor lia. A convencao e uma
chave `quadrosBase64` com a lista de quadros em ordem temporal, espelhando nome
por nome o corpo de `facial-svc:/liveness`. Nenhum campo NOVO foi acrescentado
ao `openapi.yaml`: declarar formalmente a sub-estrutura de `livenessEvidencia`
(ou promover `quadrosBase64` a campo de primeira classe) e decisao de contrato
do dono do produto, registrada em `docs/backlog.md` e nao tomada aqui.

Evidencia ausente, malformada ou curta demais nao penaliza ninguem: vira
"sem sinal" com aviso, pelo mesmo motivo de sempre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria import cliente_facial
from app.biometria import servico as servico_biometria
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger

logger = obter_logger("marcacao.facial")

#: Aviso acrescentado a `MarcacaoCriada.avisos` quando a foto veio mas o motor
#: nao respondeu. Nome no mesmo estilo dos avisos ja existentes do pipeline
#: (`fora_da_geocerca`).
AVISO_INDISPONIVEL = "facial_indisponivel"

#: Aviso para "a foto veio, o motor esta de pe, mas o colaborador nao tem
#: credencial biometrica ativa". Nao e falha de ninguem (ADR-006 regra 8: quem
#: recusa a biometria bate ponto pelo fallback), mas precisa aparecer -- sem
#: isso, um cadastro que nunca foi aprovado pelo RH ficaria invisivel.
AVISO_SEM_TEMPLATE = "facial_sem_template"


@dataclass(frozen=True, slots=True)
class ResultadoVerificacaoFacial:
    """`aprovado=True` so quando o motor respondeu e aprovou.

    `None` significa "sem sinal" -- e o unico valor que o modulo produz para
    motor indisponivel ou colaborador sem template. Reprovacao nunca volta como
    valor: ela sobe como `ErroDeAplicacao("PONTO-SCORE-003")` de dentro de
    `cliente_facial.verificar`.
    """

    aprovado: bool | None
    aviso: str | None = None


#: Instancia reutilizada para o caso "nao havia foto para verificar".
SEM_CAPTURA = ResultadoVerificacaoFacial(aprovado=None)


async def verificar_captura(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    foto_base64: str | None,
    usuario_id: UUID | None,
) -> ResultadoVerificacaoFacial:
    """Compara `foto_base64` contra os templates ativos do colaborador.

    Levanta `ErroDeAplicacao("PONTO-SCORE-003")` quando o motor reprova, e
    `ErroDeAplicacao("PONTO-VAL-001")` quando a captura nao tem exatamente um
    rosto -- os dois vem do proprio `facial-svc`, repassados por
    `cliente_facial`. Qualquer outra falha vira ausencia de sinal.
    """
    if not foto_base64:
        return SEM_CAPTURA

    templates = await servico_biometria.templates_ativos_do_colaborador(
        sessao, tenant_id=tenant_id, colaborador_id=colaborador_id, usuario_id=usuario_id
    )
    if templates is None:
        logger.info("marcacao_facial_sem_template", extra={"colaborador_id": str(colaborador_id)})
        return ResultadoVerificacaoFacial(aprovado=None, aviso=AVISO_SEM_TEMPLATE)

    try:
        aprovado = await cliente_facial.verificar(
            imagem_base64=foto_base64,
            templates=list(templates.vetores),
            versao_modelo=templates.versao_modelo,
            # Identificador OPACO (`facial/esquemas.py`): o facial-svc nao sabe
            # de quem e o rosto, so consegue amarrar a chamada a auditoria.
            referencia=f"marcacao:{colaborador_id}",
        )
    except cliente_facial.FacialSvcIndisponivel as exc:
        logger.warning(
            "marcacao_facial_indisponivel",
            extra={"colaborador_id": str(colaborador_id), "motivo": exc.motivo},
        )
        return ResultadoVerificacaoFacial(aprovado=None, aviso=AVISO_INDISPONIVEL)

    return ResultadoVerificacaoFacial(aprovado=aprovado)


# ---------------------------------------------------------------------------
# Prova de vida
# ---------------------------------------------------------------------------

#: Chave de `MarcacaoCriar.livenessEvidencia` que carrega a sequencia. Nome
#: identico ao do corpo de `facial-svc:/liveness` de proposito: dois nomes para
#: a mesma coisa e onde nasce o mapeamento errado silencioso.
CHAVE_QUADROS = "quadrosBase64"

#: Espelha `FACIAL_LIVENESS_MIN_QUADROS` (padrao 2) do `facial-svc`. Nao e
#: importado de la porque os dois servicos sao distribuiveis separados; a copia
#: existe para NAO chamar o motor com uma sequencia que ele ja recusaria por
#: tamanho -- a reprovacao estrutural resultante seria indistinguivel, no score,
#: de uma tentativa de fraude.
MINIMO_QUADROS = 2

#: `CorpoLiveness.quadrosBase64` tem `max_length=16`. Mandar mais viraria `422`
#: -- resposta fora do catalogo, que o cliente traduz para "motor indisponivel".
#: Truncar e melhor: os primeiros 16 quadros de uma captura sao uma sequencia
#: temporal valida, e o motor julga movimento entre quadros consecutivos.
MAXIMO_QUADROS = 16

#: Prova de vida pedida, motor sem resposta. Mesma familia de
#: `facial_indisponivel`, separado porque sao dois servicos... duas operacoes:
#: uma pode responder e a outra nao.
AVISO_LIVENESS_INDISPONIVEL = "liveness_indisponivel"

#: O motor respondeu e NAO se convenceu. Sinal negativo real -- que pontua zero
#: na categoria biometria e **nao** bloqueia a marcacao sozinho. O aviso existe
#: porque uma marcacao que passou apesar da prova de vida reprovada precisa ser
#: distinguivel, na fila de revisao, de uma que passou sem prova nenhuma.
AVISO_LIVENESS_REPROVADO = "liveness_reprovado"

#: `livenessEvidencia` veio, mas sem sequencia utilizavel (chave ausente, tipo
#: errado, ou menos de `MINIMO_QUADROS`). E defeito de integracao do cliente, e
#: nao evidencia de nada: sem sinal, com aviso para que apareca.
AVISO_LIVENESS_EVIDENCIA_INVALIDA = "liveness_evidencia_invalida"

#: Codigos que o motor pode levantar na prova de vida e que NAO podem derrubar a
#: marcacao. `PONTO-VAL-001`: um quadro ilegivel (base64 quebrado, mime fora da
#: lista) e captura ruim, nao fraude. `PONTO-SCORE-002`: reprovacao -- nao
#: deveria chegar aqui, ja que a chamada usa `exigirAprovacao: false`, mas se um
#: `facial-svc` de outra versao a levantasse, ela vira sinal negativo e nao 403.
#: Qualquer outro codigo (`PONTO-INT-001` de mTLS mal configurado, por exemplo)
#: sobe: configuracao errada precisa ser barulhenta, nao silenciosa.
_CODIGOS_SEM_BLOQUEIO = frozenset({"PONTO-VAL-001", "PONTO-SCORE-002"})


@dataclass(frozen=True, slots=True)
class ResultadoLiveness:
    """`aprovado` e `True`/`False` reais, ou `None` para "sem sinal".

    Diferente de `ResultadoVerificacaoFacial`, aqui `False` E um valor de
    retorno legitimo: prova de vida reprovada nao aborta a marcacao.
    `sinais` (booleanos por heuristica) segue para a explicabilidade do score,
    nunca para a resposta HTTP.
    """

    aprovado: bool | None
    aviso: str | None = None
    sinais: dict[str, bool] | None = None


#: "Nao havia evidencia de prova de vida para julgar" -- o caso da imensa
#: maioria das marcacoes hoje, e que nao gera aviso nenhum.
SEM_EVIDENCIA = ResultadoLiveness(aprovado=None)


def _quadros_da_evidencia(evidencia: dict[str, Any] | None) -> list[str] | None:
    """Extrai a sequencia de `livenessEvidencia`, ou `None` se nao houver.

    Objeto de forma livre vindo de cliente externo: cada suposicao e conferida
    antes de virar chamada de rede com biometria dentro.
    """
    if not evidencia:
        return None
    brutos = evidencia.get(CHAVE_QUADROS)
    if not isinstance(brutos, list):
        return None
    quadros = [q for q in brutos if isinstance(q, str) and q]
    if len(quadros) != len(brutos) or len(quadros) < MINIMO_QUADROS:
        return None
    return quadros[:MAXIMO_QUADROS]


async def julgar_prova_de_vida(
    *,
    colaborador_id: UUID,
    liveness_evidencia: dict[str, Any] | None,
) -> ResultadoLiveness:
    """Chama `facial-svc:/liveness` com os quadros de `livenessEvidencia`.

    **Nunca levanta por reprovacao** -- essa e a propriedade central desta
    funcao, e ela e testada. Reprovar volta como `aprovado=False`; motor fora do
    ar, quadro ilegivel ou evidencia malformada voltam como `aprovado=None`.
    Erros de CONFIGURACAO (mTLS incompleto) sobem, por desenho.
    """
    quadros = _quadros_da_evidencia(liveness_evidencia)
    if quadros is None:
        if liveness_evidencia:
            logger.info(
                "marcacao_liveness_evidencia_invalida",
                extra={"colaborador_id": str(colaborador_id)},
            )
            return ResultadoLiveness(aprovado=None, aviso=AVISO_LIVENESS_EVIDENCIA_INVALIDA)
        return SEM_EVIDENCIA

    try:
        laudo = await cliente_facial.liveness(
            quadros_base64=quadros,
            # Mesmo identificador OPACO da verificacao: o `facial-svc` nao sabe
            # de quem e o rosto, so consegue amarrar a chamada a auditoria.
            referencia=f"marcacao:{colaborador_id}",
        )
    except cliente_facial.FacialSvcIndisponivel as exc:
        logger.warning(
            "marcacao_liveness_indisponivel",
            extra={"colaborador_id": str(colaborador_id), "motivo": exc.motivo},
        )
        return ResultadoLiveness(aprovado=None, aviso=AVISO_LIVENESS_INDISPONIVEL)
    except ErroDeAplicacao as exc:
        if exc.codigo not in _CODIGOS_SEM_BLOQUEIO:
            raise
        logger.info(
            "marcacao_liveness_recusada_pelo_motor",
            extra={"colaborador_id": str(colaborador_id), "facial_codigo": exc.codigo},
        )
        if exc.codigo == "PONTO-SCORE-002":
            return ResultadoLiveness(aprovado=False, aviso=AVISO_LIVENESS_REPROVADO)
        return ResultadoLiveness(aprovado=None, aviso=AVISO_LIVENESS_EVIDENCIA_INVALIDA)

    return ResultadoLiveness(
        aprovado=laudo.aprovado,
        aviso=None if laudo.aprovado else AVISO_LIVENESS_REPROVADO,
        sinais=laudo.sinais,
    )
