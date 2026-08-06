"""Motor de composicao ponderada do score de confianca (ADR-008, PCF F14 A1).

Este e o "corpo real" que a docstring de `app.marcacao.confianca.motor`
(F5) reserva para a F14: `avaliar_confianca` (assinatura congelada daquele
modulo) delega para `compor_score` (aqui) por import tardio, dentro da
funcao, exatamente para nao criar import circular (`compor_score` importa
`SinaisRegistro`/`ResultadoConfianca` DAQUELE modulo em nivel de topo).

## Sinais decisivos (ADR-008 regra 7)

Antes de qualquer composicao ponderada, `compor_score` verifica os sinais que
sao evidencia de adulteracao, nao indicio: mock location, camera virtual,
emulador, root/jailbreak, modo desenvolvedor e attestation reprovado. Cada um
levanta o `ErroDeAplicacao` do catalogo correspondente (PONTO-GEO-003,
PONTO-SCORE-004, PONTO-DISP-003/004/005) e ABORTA a composicao -- nenhum
score e calculado, porque nenhum score alto de outros sinais deveria
compensar uma adulteracao comprovada. `politica_root`/
`politica_modo_desenvolvedor`/`politica_mock_location` (bloquear/sinalizar/
permitir, `politicas_registro`) decidem se o sinal e decisivo (`bloquear`) ou
apenas entra na composicao ponderada como um sinal a mais (`sinalizar`) ou e
ignorado (`permitir`). Camera virtual e ambiente comprometido (emulador) NAO
tem coluna de politica dedicada em `politicas_registro` -- tratados como
SEMPRE decisivos quando detectados (mesmo texto de `PONTO-DISP-005`,
"nao e configuravel para permitir: e bloqueio duro do produto").

Todo `ErroDeAplicacao` levantado aqui usa APENAS `contexto_log` (nunca
`detalhe`/`erros_campo`) para qualquer informacao que revele peso, limiar ou
politica vigente -- `contexto_log` vai para o log/auditoria, nunca para a
resposta HTTP (`app/core/erros.py::montar_problema`); os codigos usados
(PONTO-SCORE-001/004, PONTO-GEO-003, PONTO-DISP-003/004/005) ja tem
`expoe_regra` fixado no catalogo (`packages/contracts/errors.yaml`), a maioria
`false` -- este modulo nunca tenta contornar isso.

## Composicao ponderada

Sinais NAO decisivos (ou decisivos com politica `sinalizar`/`permitir`) se
combinam por categoria (`app.antifraude.politicas.PesosScore`: dispositivo,
biometria, geolocalizacao, comportamento). Sinal indisponivel
(`disponibilidade=NAO_APLICAVEL` -- ADR-014: nenhuma origem real hoje, ou o
cliente nao informou, E a politica do tenant nao exige aquele sinal) e
EXCLUIDO da media da categoria; categoria sem nenhum sinal disponivel e
EXCLUIDA do total (peso renormalizado pelas categorias que sobraram). Nenhum
valor e inventado para preencher a lacuna nesse caso.

**Excecao (achado da verificacao adversarial, F14/A4):** quando a politica do
tenant EXIGE um sinal de biometria (`exige_facial`/`exige_liveness`,
`politicas_registro`, default `TRUE`) e ele esta ausente, isso NAO conta como
"canal sem suporte" -- e a propria politica dizendo que era obrigatorio. Esse
caso pontua baixo (`_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE`) em vez de excluido,
tipicamente empurrando para a faixa de revisao (ADR-008: "grava e sinaliza"),
nunca um bloqueio duro so por ausencia de sinal -- `facial-svc` ainda e stub
501 desde a Fase 0 (achado registrado em `docs/backlog.md`), e bloquear todo
canal web por uma dependencia que ainda nao existe quebraria o check-in
inteiro. Fora desse caso, so o TENTAR e reprovar reduz o score.

Se NENHUMA categoria tiver sinal disponivel (nem geolocalizacao, caso raro:
canal sem lat/long e sem dispositivo), o score e `SCORE_SEM_SINAIS = 100` --
decisao documentada, nao lacuna, e consequencia DIRETA do paragrafo acima
("nenhum valor e inventado para preencher a lacuna"): se ausencia de sinal
nunca deve REDUZIR o score de um sinal que existe, ausencia de TODOS os
sinais tampouco pode. Esse caso hoje so acontece para canais que ja passaram
por um gate legal forte antes de chegar aqui (ex.: terminal com prova de vida
propria em hardware, fora deste sistema) ou quando o tenant optou por nao
exigir geocerca/dispositivo pessoal naquele canal -- decisao de politica do
proprio tenant, nao motivo para desconfiar por omissao.

## Explicabilidade (ADR-008 regra 4)

`ResultadoScore.explicabilidade` grava, por sinal individual: categoria,
disponibilidade, valor bruto, peso EFETIVO (peso da categoria dividido pelos
sinais disponiveis dela) e a contribuicao final ao score. `app.marcacao.
pipeline.ingestao` serializa esta tupla dentro de `marcacoes_meta.
flags_integridade["_antifraude"]["scoreExplicabilidade"]` -- ver aquele
modulo e `app.antifraude.explicabilidade` para o formato exato gravado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.antifraude.politicas import PoliticaAntifraude
from app.core.erros import ErroDeAplicacao
from app.marcacao.confianca.motor import ResultadoConfianca, SinaisRegistro

REAL = "real"
NAO_APLICAVEL = "nao_aplicavel"

CLASSIFICACAO_ALTA = "alta"
CLASSIFICACAO_MEDIA = "media"
CLASSIFICACAO_BAIXA = "baixa"
CLASSIFICACAO_BLOQUEADA = "bloqueada"

#: Score atribuido quando NENHUMA categoria tem sinal disponivel (ver
#: docstring do modulo). 100, nao um numero "cauteloso" menor: ausencia de
#: sinal nunca e tratada como evidencia de fraude (ADR-014/ADR-008) -- a
#: mesma regra que vale por sinal individual (indisponivel nunca reduz a
#: media da categoria) vale para o conjunto vazio de categorias.
SCORE_SEM_SINAIS = 100

_PONTUACAO_ATTESTATION_APROVADO = 100.0
_PONTUACAO_ATTESTATION_REPROVADO_SINALIZADO = 30.0
_PENALIDADE_ROOT_SINALIZADO = 40.0
_PENALIDADE_MODO_DEV_SINALIZADO = 30.0
_PONTUACAO_FORA_GEOCERCA_SINALIZADA = 35.0
#: Achado da verificacao adversarial (F14/A4, `test_prova_de_vida_facial.py`):
#: quando `politica.exige_facial`/`exige_liveness` e True mas o sinal esta
#: ausente, isso NAO e "canal sem suporte" (NAO_APLICAVEL, nunca penaliza) --
#: e a PROPRIA POLITICA do tenant dizendo que era obrigatorio. Pontua baixo o
#: bastante para tipicamente cair na faixa de revisao sob os limiares padrao,
#: nunca um bloqueio duro por si so (facial-svc `/verificar`/`/liveness`
#: seguem stub 501 desde a Fase 0 -- bloquear todo canal web por uma
#: dependencia que ainda nao existe quebraria o check-in inteiro; ver
#: docs/backlog.md).
_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE = 40.0
_PONTUACAO_CONFIANCA_TEMPORAL_BAIXA = 20.0
_ID_TENANT_LOG = "tenant_id"


@dataclass(frozen=True, slots=True)
class ContribuicaoSinal:
    """Uma linha da explicabilidade: um sinal, sua categoria, disponibilidade,
    valor observado, peso efetivo (0-100, ja renormalizado) e contribuicao
    final ao score composto (peso_efetivo * pontuacao / 100)."""

    sinal: str
    categoria: str
    disponibilidade: str
    valor: Any
    peso_efetivo: float
    pontuacao: float | None
    contribuicao: float | None

    def para_dict(self) -> dict[str, Any]:
        return {
            "sinal": self.sinal,
            "categoria": self.categoria,
            "disponibilidade": self.disponibilidade,
            "valor": self.valor,
            "pesoEfetivo": round(self.peso_efetivo, 2),
            "pontuacao": round(self.pontuacao, 2) if self.pontuacao is not None else None,
            "contribuicao": round(self.contribuicao, 2) if self.contribuicao is not None else None,
        }


@dataclass(frozen=True, slots=True)
class ContextoDecisao:
    """Sinais CALCULADOS PELO SERVIDOR (nao reportados pelo cliente) que
    `SinaisRegistro` nao carrega porque dependem de consulta ao banco --
    mantidos separados de proposito, para a explicabilidade distinguir "o
    que o cliente informou" (ADR-008 regra 1: nunca confiavel por si so) de
    "o que o servidor calculou" (`app.antifraude.reputacao`/`geografia`)."""

    reputacao_dispositivo: float | None = None
    velocidade_kmh: float | None = None
    velocidade_impossivel: bool = False
    #: Achado da verificacao adversarial (F14/A4, `test_confianca_temporal.py`):
    #: item offline com atraso implausivel (`app.marcacao.pipeline.offline`,
    #: ver constante `_LIMIAR_ATRASO_SUSPEITO_MINUTOS` la) processava com score
    #: normal -- a classificacao "alta"/"media"/"baixa" do ADR-007 era
    #: calculada mas nunca chegava ate aqui. Proxy HEURISTICO por atraso, nao
    #: a reconciliacao completa dos tres relogios que o ADR-007 descreve
    #: (servidor + monotonico + sincronizacao) -- essa reconciliacao completa
    #: continua pendente, registrada em docs/backlog.md.
    confianca_temporal_baixa: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoScore:
    score: int
    classificacao: str
    avisos: tuple[str, ...]
    explicabilidade: tuple[ContribuicaoSinal, ...]

    def para_resultado_confianca(self) -> ResultadoConfianca:
        """Projeta para o schema congelado de `marcacao.confianca.motor`."""
        return ResultadoConfianca(
            score=self.score,
            classificacao=self.classificacao,
            avisos=self.avisos,
        )


def _verificar_sinais_decisivos(
    sinais: SinaisRegistro,
    politica: PoliticaAntifraude,
    *,
    tenant_id: UUID | None,
) -> None:
    """ADR-008 regra 7. Levanta o `ErroDeAplicacao` do sinal decisivo e
    interrompe a composicao -- chamado ANTES de `_compor` no fluxo normal de
    `compor_score`."""
    contexto = {_ID_TENANT_LOG: str(tenant_id)} if tenant_id else {}

    if sinais.mock_location and politica.politica_mock_location == "bloquear":
        raise ErroDeAplicacao("PONTO-GEO-003", contexto_log={**contexto, "sinal": "mock_location"})
    if sinais.camera_virtual:
        raise ErroDeAplicacao(
            "PONTO-SCORE-004", contexto_log={**contexto, "sinal": "camera_virtual"}
        )
    if sinais.emulador_detectado:
        raise ErroDeAplicacao(
            "PONTO-DISP-005", contexto_log={**contexto, "sinal": "emulador_detectado"}
        )
    if sinais.root_detectado and politica.politica_root == "bloquear":
        raise ErroDeAplicacao(
            "PONTO-DISP-005", contexto_log={**contexto, "sinal": "root_detectado"}
        )
    if sinais.modo_desenvolvedor and politica.politica_modo_desenvolvedor == "bloquear":
        raise ErroDeAplicacao(
            "PONTO-DISP-004", contexto_log={**contexto, "sinal": "modo_desenvolvedor"}
        )
    if sinais.attestation_veredito == "reprovado" and politica.exige_attestation:
        raise ErroDeAplicacao(
            "PONTO-DISP-003", contexto_log={**contexto, "sinal": "attestation_veredito"}
        )


def _sinais_categoria_dispositivo(
    sinais: SinaisRegistro, politica: PoliticaAntifraude, contexto: ContextoDecisao
) -> list[ContribuicaoSinal]:
    resultado: list[ContribuicaoSinal] = []

    if sinais.attestation_veredito == "aprovado":
        resultado.append(
            _sinal(
                "attestation",
                "dispositivo",
                REAL,
                sinais.attestation_veredito,
                _PONTUACAO_ATTESTATION_APROVADO,
            )
        )
    elif sinais.attestation_veredito == "reprovado":
        # So chega aqui quando a politica NAO bloqueia attestation reprovado
        # (do contrario `_verificar_sinais_decisivos` ja recusou antes).
        resultado.append(
            _sinal(
                "attestation",
                "dispositivo",
                REAL,
                sinais.attestation_veredito,
                _PONTUACAO_ATTESTATION_REPROVADO_SINALIZADO,
            )
        )
    else:
        # 'indisponivel'/'nao_aplicavel': reservado para F7 (ADR-014) -- nunca
        # inventa pontuacao, exclui da media da categoria.
        resultado.append(
            _sinal("attestation", "dispositivo", NAO_APLICAVEL, sinais.attestation_veredito)
        )

    if contexto.reputacao_dispositivo is not None:
        resultado.append(
            _sinal(
                "reputacao_dispositivo",
                "dispositivo",
                REAL,
                round(contexto.reputacao_dispositivo, 2),
                contexto.reputacao_dispositivo,
            )
        )
    else:
        resultado.append(_sinal("reputacao_dispositivo", "dispositivo", NAO_APLICAVEL, None))

    if sinais.root_detectado is not None or sinais.modo_desenvolvedor is not None:
        pontuacao = 100.0
        if sinais.root_detectado and politica.politica_root == "sinalizar":
            pontuacao -= _PENALIDADE_ROOT_SINALIZADO
        if sinais.modo_desenvolvedor and politica.politica_modo_desenvolvedor == "sinalizar":
            pontuacao -= _PENALIDADE_MODO_DEV_SINALIZADO
        resultado.append(
            _sinal(
                "integridade_relatada",
                "dispositivo",
                REAL,
                {
                    "rootDetectado": sinais.root_detectado,
                    "modoDesenvolvedor": sinais.modo_desenvolvedor,
                },
                max(0.0, pontuacao),
            )
        )
    else:
        resultado.append(_sinal("integridade_relatada", "dispositivo", NAO_APLICAVEL, None))

    return resultado


def _sinais_categoria_biometria(
    sinais: SinaisRegistro, politica: PoliticaAntifraude
) -> list[ContribuicaoSinal]:
    resultado: list[ContribuicaoSinal] = []

    if sinais.score_facial is not None:
        limiar = politica.limiar_facial if politica.limiar_facial > 0 else 75.0
        pontuacao = max(0.0, min(100.0, 100.0 * (sinais.score_facial / limiar)))
        resultado.append(
            _sinal("similaridade_facial", "biometria", REAL, sinais.score_facial, pontuacao)
        )
    elif politica.exige_facial:
        # A politica do tenant EXIGE similaridade facial e nenhum sinal
        # chegou -- diferente de "canal sem suporte" (ver constante acima).
        resultado.append(
            _sinal(
                "similaridade_facial",
                "biometria",
                REAL,
                None,
                _PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE,
            )
        )
    else:
        # Reservado: `facial-svc` (`/verificar`) ainda e stub 501 desde a
        # Fase 0 -- ver achado em docs/backlog.md. nao_aplicavel, nunca
        # inventado (ADR-014), e a politica do tenant nao exige o sinal.
        resultado.append(_sinal("similaridade_facial", "biometria", NAO_APLICAVEL, None))

    if sinais.liveness_aprovado is not None:
        pontuacao = 100.0 if sinais.liveness_aprovado else 0.0
        resultado.append(
            _sinal("prova_de_vida", "biometria", REAL, sinais.liveness_aprovado, pontuacao)
        )
    elif politica.exige_liveness:
        resultado.append(
            _sinal(
                "prova_de_vida",
                "biometria",
                REAL,
                None,
                _PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE,
            )
        )
    else:
        resultado.append(_sinal("prova_de_vida", "biometria", NAO_APLICAVEL, None))

    return resultado


def _sinais_categoria_geolocalizacao(
    sinais: SinaisRegistro, politica: PoliticaAntifraude
) -> list[ContribuicaoSinal]:
    resultado: list[ContribuicaoSinal] = []

    if sinais.dentro_geocerca is None:
        resultado.append(_sinal("geocerca", "geolocalizacao", NAO_APLICAVEL, None))
    elif sinais.dentro_geocerca:
        resultado.append(
            _sinal(
                "geocerca",
                "geolocalizacao",
                REAL,
                {"dentro": True, "distanciaMetros": sinais.distancia_geocerca_metros},
                100.0,
            )
        )
    else:
        resultado.append(
            _sinal(
                "geocerca",
                "geolocalizacao",
                REAL,
                {"dentro": False, "distanciaMetros": sinais.distancia_geocerca_metros},
                _PONTUACAO_FORA_GEOCERCA_SINALIZADA,
            )
        )

    # `mock_location` so chega aqui quando a politica NAO bloqueia (ver
    # `_verificar_sinais_decisivos`): 'sinalizar' ainda deve empurrar o score
    # para baixo (ADR-008 regra 7 fala de "recusa direta", nao de "ignora
    # quando a empresa escolhe so sinalizar"); 'permitir' e neutro por
    # decisao explicita do tenant.
    if sinais.mock_location is None:
        resultado.append(_sinal("mock_location", "geolocalizacao", NAO_APLICAVEL, None))
    elif sinais.mock_location and politica.politica_mock_location == "sinalizar":
        resultado.append(_sinal("mock_location", "geolocalizacao", REAL, True, 0.0))
    else:
        resultado.append(
            _sinal("mock_location", "geolocalizacao", REAL, sinais.mock_location, 100.0)
        )

    return resultado


def _sinais_categoria_comportamento(contexto: ContextoDecisao) -> list[ContribuicaoSinal]:
    resultado: list[ContribuicaoSinal] = []

    if contexto.velocidade_kmh is None and not contexto.velocidade_impossivel:
        resultado.append(_sinal("velocidade_deslocamento", "comportamento", NAO_APLICAVEL, None))
    else:
        pontuacao = 0.0 if contexto.velocidade_impossivel else 100.0
        valor = (
            round(contexto.velocidade_kmh, 1)
            if contexto.velocidade_kmh is not None
            else "indeterminada"
        )
        resultado.append(_sinal("velocidade_deslocamento", "comportamento", REAL, valor, pontuacao))

    if contexto.confianca_temporal_baixa:
        resultado.append(
            _sinal(
                "confianca_temporal",
                "comportamento",
                REAL,
                "baixa",
                _PONTUACAO_CONFIANCA_TEMPORAL_BAIXA,
            )
        )
    else:
        resultado.append(_sinal("confianca_temporal", "comportamento", NAO_APLICAVEL, None))

    return resultado


def _sinal(
    nome: str,
    categoria: str,
    disponibilidade: str,
    valor: Any,
    pontuacao: float | None = None,
) -> ContribuicaoSinal:
    return ContribuicaoSinal(
        sinal=nome,
        categoria=categoria,
        disponibilidade=disponibilidade,
        valor=valor,
        peso_efetivo=0.0,
        pontuacao=pontuacao,
        contribuicao=None,
    )


def _classificar(score: int, *, limiar_bloqueio: int, limiar_revisao: int) -> str:
    if score < limiar_bloqueio:
        return CLASSIFICACAO_BLOQUEADA
    if score >= limiar_revisao:
        return CLASSIFICACAO_ALTA
    ponto_medio = (limiar_bloqueio + limiar_revisao) / 2
    return CLASSIFICACAO_MEDIA if score >= ponto_medio else CLASSIFICACAO_BAIXA


def _avisos_de(sinais_por_categoria: dict[str, list[ContribuicaoSinal]]) -> list[str]:
    avisos: list[str] = []
    for sinais in sinais_por_categoria.values():
        for sinal in sinais:
            if sinal.disponibilidade != REAL or sinal.pontuacao is None:
                continue
            if sinal.sinal == "reputacao_dispositivo" and sinal.pontuacao < 50:
                avisos.append("reputacao_dispositivo_baixa")
            elif sinal.sinal == "velocidade_deslocamento" and sinal.pontuacao == 0.0:
                avisos.append("velocidade_implausivel")
            elif sinal.sinal == "confianca_temporal" and sinal.pontuacao < 100:
                avisos.append("confianca_temporal_baixa")
            elif sinal.sinal == "integridade_relatada" and sinal.pontuacao < 100:
                avisos.append("integridade_dispositivo_sinalizada")
            elif sinal.sinal == "geocerca" and sinal.pontuacao < 100:
                avisos.append("fora_da_geocerca_sinalizada")
            elif sinal.sinal == "mock_location" and sinal.pontuacao < 100:
                avisos.append("mock_location_sinalizado")
            elif (
                sinal.sinal == "attestation"
                and sinal.pontuacao is not None
                and sinal.pontuacao < 100
            ):
                avisos.append("attestation_reprovado_sinalizado")
    return avisos


def compor_score(
    sinais: SinaisRegistro,
    *,
    politica: PoliticaAntifraude,
    limiar_bloqueio: int,
    limiar_revisao: int,
    contexto: ContextoDecisao | None = None,
    tenant_id: UUID | None = None,
) -> ResultadoScore:
    """Composicao ponderada completa (ADR-008): verifica sinais decisivos
    (pode levantar `ErroDeAplicacao`), compoe por categoria com renormalizacao
    de peso pelos sinais disponiveis, classifica pela politica de tres faixas
    e devolve a explicabilidade completa."""
    contexto = contexto or ContextoDecisao()

    _verificar_sinais_decisivos(sinais, politica, tenant_id=tenant_id)

    por_categoria: dict[str, list[ContribuicaoSinal]] = {
        "dispositivo": _sinais_categoria_dispositivo(sinais, politica, contexto),
        "biometria": _sinais_categoria_biometria(sinais, politica),
        "geolocalizacao": _sinais_categoria_geolocalizacao(sinais, politica),
        "comportamento": _sinais_categoria_comportamento(contexto),
    }

    peso_por_categoria = {
        "dispositivo": politica.pesos.dispositivo,
        "biometria": politica.pesos.biometria,
        "geolocalizacao": politica.pesos.geolocalizacao,
        "comportamento": politica.pesos.comportamento,
    }

    explicabilidade: list[ContribuicaoSinal] = []
    soma_peso_disponivel = 0.0
    soma_ponderada = 0.0

    for categoria, sinais_categoria in por_categoria.items():
        disponiveis = [s for s in sinais_categoria if s.disponibilidade == REAL]
        peso_categoria = float(peso_por_categoria[categoria])
        peso_por_sinal = peso_categoria / len(disponiveis) if disponiveis else 0.0

        for sinal in sinais_categoria:
            if sinal.disponibilidade != REAL:
                explicabilidade.append(sinal)
                continue
            contribuicao = peso_por_sinal * (sinal.pontuacao or 0.0) / 100.0
            sinal_com_peso = ContribuicaoSinal(
                sinal=sinal.sinal,
                categoria=sinal.categoria,
                disponibilidade=sinal.disponibilidade,
                valor=sinal.valor,
                peso_efetivo=peso_por_sinal,
                pontuacao=sinal.pontuacao,
                contribuicao=contribuicao,
            )
            explicabilidade.append(sinal_com_peso)
            soma_peso_disponivel += peso_por_sinal
            soma_ponderada += contribuicao

    if soma_peso_disponivel <= 0:
        score = SCORE_SEM_SINAIS
    else:
        # `soma_ponderada` ja esta na escala 0..soma_peso_disponivel (cada
        # contribuicao e peso*pontuacao/100); renormaliza para 0..100.
        score = round((soma_ponderada / soma_peso_disponivel) * 100.0)
        score = max(0, min(100, score))

    classificacao = _classificar(
        score, limiar_bloqueio=limiar_bloqueio, limiar_revisao=limiar_revisao
    )
    avisos = tuple(_avisos_de(por_categoria))

    return ResultadoScore(
        score=score,
        classificacao=classificacao,
        avisos=avisos,
        explicabilidade=tuple(explicabilidade),
    )
