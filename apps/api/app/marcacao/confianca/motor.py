"""Motor de score de confianca do registro de ponto. CONTRATO ENTRE FASES.

A assinatura publica de `avaliar_confianca` esta fixada neste PCF (F5) e NAO
muda sem RFC. A implementacao real -- composicao ponderada de attestation,
RASP, modo desenvolvedor, mock location, coerencia geografica, velocidade
implicita e reputacao do dispositivo -- e da F14.

**F14/A1 implementou o corpo (ADR-008), sem tocar a assinatura acima.** Dois
parametros NOVOS foram acrescentados -- `politica` e `contexto`, ambos
`keyword-only` e `= None` por padrao -- porque nem a politica de pesos por
sinal (ADR-008: "score composto... por sinais ponderados") nem os sinais que
so o SERVIDOR pode calcular por consulta ao banco (reputacao de dispositivo,
classificacao de velocidade impossivel) cabiam nos tres parametros originais.
Parametro novo com default nao quebra NENHUM chamador existente:
`sinais`/`limiar_bloqueio`/`limiar_revisao` continuam funcionando exatamente
como antes, posicional ou por nome, para quem nao sabe que `politica`/
`contexto` existem. `ResultadoConfianca` ganhou o mesmo tratamento: um campo
novo (`explicabilidade`) com default `()`, cauda da dataclass, sem mexer nos
tres campos originais. Ver `app.antifraude.motor` para a implementacao real e
a justificativa completa desta decisao (nao estava explicita no PCF --
documentada la e no relatorio de fechamento de A1).

O import de `app.antifraude.motor` e FEITO DENTRO da funcao (nao no topo do
modulo) de proposito: `app.antifraude.motor` importa `SinaisRegistro`/
`ResultadoConfianca` DESTE modulo em nivel de topo, e um import circular
nivel-de-modulo quebraria a inicializacao do pacote. Import tardio dentro de
funcao para evitar ciclo e padrao ja usado em `app.marcacao.pipeline.
ingestao` (`emitir_comprovante`/`publicar_comprovante_emitido`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.antifraude.motor import ContextoDecisao
    from app.antifraude.politicas import PoliticaAntifraude


@dataclass(frozen=True, slots=True)
class SinaisRegistro:
    """Sinais brutos coletados no momento do registro, tal como informados
    pelo cliente (nenhum e verificado criptograficamente nesta fase)."""

    dentro_geocerca: bool | None = None
    distancia_geocerca_metros: float | None = None
    precisao_insuficiente: bool = False
    score_facial: float | None = None
    liveness_aprovado: bool | None = None
    attestation_veredito: str = "indisponivel"
    root_detectado: bool | None = None
    emulador_detectado: bool | None = None
    modo_desenvolvedor: bool | None = None
    mock_location: bool | None = None
    camera_virtual: bool | None = None
    velocidade_desde_ultima_kmh: float | None = None
    flags_integridade: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoConfianca:
    """Resultado da avaliacao. `avisos` alimenta `MarcacaoCriada.avisos` e
    `marcacao.suspeita.sinais`. `explicabilidade` (F14): a mesma informacao
    em forma estruturada, serializavel para `marcacoes_meta.flags_integridade`
    (ver `app.antifraude.explicabilidade`) -- `avisos` continua existindo
    porque e o que os CONSUMIDORES ja existentes de F5 (eventos, resposta
    HTTP) leem; `explicabilidade` e o detalhe fino que so a auditoria/painel
    de revisao precisa."""

    score: int = 100
    classificacao: str = "alta"
    avisos: tuple[str, ...] = ()
    explicabilidade: tuple[Any, ...] = ()


def avaliar_confianca(
    sinais: SinaisRegistro,
    *,
    limiar_bloqueio: int,
    limiar_revisao: int,
    politica: PoliticaAntifraude | None = None,
    contexto: ContextoDecisao | None = None,
) -> ResultadoConfianca:
    """Composicao ponderada real (ADR-008), delegada a `app.antifraude.motor.
    compor_score`.

    `politica=None` usa `app.antifraude.politicas.POLITICA_NEUTRA` -- perfil
    "equilibrado", todas as politicas de sinal decisivo em 'bloquear' (o
    default mais seguro, nunca permissivo por omissao). `contexto=None`
    equivale a nenhum sinal calculado pelo servidor disponivel (reputacao de
    dispositivo `nao_aplicavel`, velocidade tomada literalmente de
    `sinais.velocidade_desde_ultima_kmh` sem classificacao de
    "impossivel" -- quem precisa dessa classificacao, como
    `app.marcacao.pipeline.ingestao`, monta `ContextoDecisao` com
    `app.antifraude.geografia.calcular_deslocamento` e passa aqui).

    Pode levantar `app.core.erros.ErroDeAplicacao` (PONTO-GEO-003,
    PONTO-SCORE-004, PONTO-DISP-003/004/005) quando um sinal DECISIVO reprova
    (ADR-008 regra 7) -- ver docstring de `app.antifraude.motor` para a lista
    completa. Isto e uma mudanca de comportamento em relacao ao stub
    permissivo anterior (que nunca levantava nada); e exatamente o que este
    PCF pede.
    """
    from app.antifraude.motor import ContextoDecisao as _ContextoDecisao
    from app.antifraude.motor import compor_score
    from app.antifraude.politicas import POLITICA_NEUTRA

    contexto_efetivo = contexto or _ContextoDecisao(
        velocidade_kmh=sinais.velocidade_desde_ultima_kmh
    )
    resultado = compor_score(
        sinais,
        politica=politica or POLITICA_NEUTRA,
        limiar_bloqueio=limiar_bloqueio,
        limiar_revisao=limiar_revisao,
        contexto=contexto_efetivo,
    )
    return ResultadoConfianca(
        score=resultado.score,
        classificacao=resultado.classificacao,
        avisos=resultado.avisos,
        explicabilidade=resultado.explicabilidade,
    )
