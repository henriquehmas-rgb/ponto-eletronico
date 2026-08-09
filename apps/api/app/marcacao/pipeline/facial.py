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
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria import cliente_facial
from app.biometria import servico as servico_biometria
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
