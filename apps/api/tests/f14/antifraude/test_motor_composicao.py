"""Teste de composicao do motor (`app.antifraude.motor.compor_score`), 100%
sintetico, sem banco -- cobre as tres faixas do ADR-008, os sinais decisivos
e a explicabilidade.

**Sinais sinteticos, documentados como tal (Aceite de A1, PCF F14 sec 5).**
Nenhum destes testes usa um SDK real de nenhuma plataforma: os valores de
`SinaisRegistro` sao construidos a mao, representando o que um cliente real
(web/terminal, unico canal com sinal real nesta fase) OU um app movel futuro
(F7, ADR-014) reportaria. Os testes que exercitam `score_facial`/
`liveness_aprovado` fazem isso porque a COMPOSICAO precisa ser provada
funcional quando a origem existir -- nao porque o `facial-svc` produz esse
dado hoje (nao produz: `/verificar`/`/liveness` sao stubs 501 desde a Fase 0,
achado em `docs/backlog.md`). Os testes que deixam `attestation_veredito`/
`score_facial`/`liveness_aprovado` no valor `nao_aplicavel`/`None` default
sao os que refletem o trafego REAL desta fase (ADR-014).
"""

from __future__ import annotations

import pytest

from app.antifraude.motor import (
    CLASSIFICACAO_ALTA,
    CLASSIFICACAO_BAIXA,
    CLASSIFICACAO_BLOQUEADA,
    CLASSIFICACAO_MEDIA,
    NAO_APLICAVEL,
    REAL,
    SCORE_SEM_SINAIS,
    ContextoDecisao,
    compor_score,
)
from app.antifraude.politicas import PesosScore, PoliticaAntifraude
from app.core.erros import ErroDeAplicacao
from app.marcacao.confianca.motor import SinaisRegistro

LIMIAR_BLOQUEIO = 40
LIMIAR_REVISAO = 70

_POLITICA_PADRAO = PoliticaAntifraude(
    pesos=PesosScore(dispositivo=25, biometria=25, geolocalizacao=25, comportamento=25),
    perfil_confianca="equilibrado",
    politica_root="bloquear",
    politica_modo_desenvolvedor="bloquear",
    politica_mock_location="bloquear",
    exige_attestation=True,
    exige_facial=True,
    exige_liveness=True,
    limiar_facial=75.0,
)


def _compor(
    sinais: SinaisRegistro, *, politica: PoliticaAntifraude = _POLITICA_PADRAO, contexto=None
):
    return compor_score(
        sinais,
        politica=politica,
        limiar_bloqueio=LIMIAR_BLOQUEIO,
        limiar_revisao=LIMIAR_REVISAO,
        contexto=contexto,
    )


# ---------------------------------------------------------------------------
# As tres faixas do ADR-008 (Aceite de A1: "teste de composicao cobre as
# tres faixas").
# ---------------------------------------------------------------------------


def test_faixa_alta_sinais_reais_todos_confiaveis() -> None:
    """Geocerca dentro (real, F8/web ja calcula isso hoje) + reputacao de
    dispositivo alta (real, calculada por consulta ao banco) + comportamento
    plausivel (real) -> score alto, classificacao 'alta', sem revisao."""
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0)
    resultado = _compor(
        sinais,
        contexto=ContextoDecisao(
            reputacao_dispositivo=95.0, velocidade_kmh=12.0, velocidade_impossivel=False
        ),
    )
    assert resultado.score >= LIMIAR_REVISAO
    assert resultado.classificacao == CLASSIFICACAO_ALTA


def test_faixa_media_ou_baixa_reputacao_dispositivo_fraca_aciona_revisao() -> None:
    """Reputacao de dispositivo pessima (sinal REAL, calculado por historico)
    puxa a media ponderada para a faixa de revisao (entre os dois limiares)
    sem bloquear -- ADR-008 regra 2: 'entre os limiares: grava e sinaliza'.
    Geocerca e velocidade continuam perfeitas (100): so a reputacao ruim
    (1 de 3 categorias disponiveis, peso igual) e capaz de derrubar a media
    de 100 para a faixa de revisao -- prova que o sinal pesa de verdade."""
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0)
    resultado = _compor(
        sinais,
        contexto=ContextoDecisao(
            reputacao_dispositivo=0.0, velocidade_kmh=5.0, velocidade_impossivel=False
        ),
    )
    assert LIMIAR_BLOQUEIO <= resultado.score < LIMIAR_REVISAO
    assert resultado.classificacao in (CLASSIFICACAO_MEDIA, CLASSIFICACAO_BAIXA)
    assert "reputacao_dispositivo_baixa" in resultado.avisos


def test_faixa_bloqueada_multiplos_sinais_negativos_combinados() -> None:
    """Fora da geocerca (sinalizada, nao bloqueada na porta) + reputacao de
    dispositivo pessima + velocidade impossivel -- nenhum decisivo isolado,
    mas a COMBINACAO pondera abaixo do limiar de bloqueio. `compor_score`
    NUNCA levanta erro por score baixo isolado (isso e responsabilidade do
    chamador, `marcacao.pipeline.ingestao`) -- so classifica."""
    sinais = SinaisRegistro(dentro_geocerca=False, distancia_geocerca_metros=500.0)
    resultado = _compor(
        sinais,
        contexto=ContextoDecisao(
            reputacao_dispositivo=5.0, velocidade_kmh=None, velocidade_impossivel=True
        ),
    )
    assert resultado.score < LIMIAR_BLOQUEIO
    assert resultado.classificacao == CLASSIFICACAO_BLOQUEADA
    assert "velocidade_implausivel" in resultado.avisos


# ---------------------------------------------------------------------------
# Sinais decisivos (ADR-008 regra 7): recusa direta, independente do score.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sinais_kwargs", "codigo_esperado"),
    [
        ({"mock_location": True}, "PONTO-GEO-003"),
        ({"camera_virtual": True}, "PONTO-SCORE-004"),
        ({"emulador_detectado": True}, "PONTO-DISP-005"),
        ({"root_detectado": True}, "PONTO-DISP-005"),
        ({"modo_desenvolvedor": True}, "PONTO-DISP-004"),
        ({"attestation_veredito": "reprovado"}, "PONTO-DISP-003"),
    ],
)
def test_sinal_decisivo_recusa_direto_independente_do_score(
    sinais_kwargs: dict[str, object], codigo_esperado: str
) -> None:
    """Mesmo com TODOS os outros sinais perfeitos (score alto), um sinal
    decisivo recusa a marcacao -- prova que nao ha compensacao."""
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0, **sinais_kwargs)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        _compor(
            sinais,
            contexto=ContextoDecisao(
                reputacao_dispositivo=100.0, velocidade_kmh=1.0, velocidade_impossivel=False
            ),
        )
    assert excinfo.value.codigo == codigo_esperado


def test_sinal_decisivo_com_politica_sinalizar_nao_recusa_so_reduz_score() -> None:
    """A MESMA condicao (root detectado) que recusa com `politica_root=
    'bloquear'` so reduz o score quando a politica e 'sinalizar' -- prova
    que a decisao de bloquear-vs-sinalizar e do tenant (ADR-008), nao fixa
    no motor."""
    politica_tolerante = PoliticaAntifraude(
        pesos=_POLITICA_PADRAO.pesos,
        perfil_confianca="tolerante",
        politica_root="sinalizar",
        politica_modo_desenvolvedor="sinalizar",
        politica_mock_location="sinalizar",
        exige_attestation=False,
        exige_facial=False,
        exige_liveness=False,
        limiar_facial=75.0,
    )
    sinais = SinaisRegistro(
        dentro_geocerca=True, distancia_geocerca_metros=0.0, root_detectado=True
    )
    resultado = _compor(
        sinais,
        politica=politica_tolerante,
        contexto=ContextoDecisao(
            reputacao_dispositivo=90.0, velocidade_kmh=1.0, velocidade_impossivel=False
        ),
    )
    assert resultado.score < 100
    assert "integridade_dispositivo_sinalizada" in resultado.avisos


def test_sinal_decisivo_com_politica_permitir_nao_penaliza() -> None:
    """'permitir' e decisao explicita do tenant: nao recusa nem penaliza."""
    politica_permissiva = PoliticaAntifraude(
        pesos=_POLITICA_PADRAO.pesos,
        perfil_confianca="personalizado",
        politica_root="permitir",
        politica_modo_desenvolvedor="permitir",
        politica_mock_location="permitir",
        exige_attestation=False,
        exige_facial=False,
        exige_liveness=False,
        limiar_facial=75.0,
    )
    sinais = SinaisRegistro(
        dentro_geocerca=True, distancia_geocerca_metros=0.0, root_detectado=True
    )
    resultado = _compor(sinais, politica=politica_permissiva)
    assert resultado.score >= LIMIAR_REVISAO


# ---------------------------------------------------------------------------
# ADR-014: sinais reservados para F7 chegam nao_aplicavel/None, nunca um
# valor inventado -- e nunca puxam o score para baixo so por ausencia.
# ---------------------------------------------------------------------------


def test_sinais_reservados_para_f7_ficam_nao_aplicavel_e_nao_penalizam() -> None:
    """`attestation` e sempre reservado para F7 (nenhuma politica o torna
    disponivel sem um cliente real). `similaridade_facial`/`prova_de_vida`
    so ficam `nao_aplicavel` quando a politica do tenant NAO exige o sinal
    -- achado da verificacao adversarial F14/A4: com a politica DEFAULT
    (`exige_facial`/`exige_liveness` = `True`), a ausencia do sinal deveria
    contar como sinal real e penalizar (ver `test_biometria_exigida_e_
    ausente_penaliza_em_vez_de_excluir`), nao ficar nao_aplicavel -- por
    isso este teste passa explicitamente uma politica que NAO exige, para
    isolar o caso "canal sem suporte" do caso "politica nao cumprida"."""
    sinais = SinaisRegistro()  # tudo default: None/"nao_aplicavel" (nenhum cliente real F7 hoje)
    politica = PoliticaAntifraude(exige_attestation=False, exige_facial=False, exige_liveness=False)
    resultado = _compor(sinais, politica=politica)
    disponibilidades = {c.sinal: c.disponibilidade for c in resultado.explicabilidade}
    assert disponibilidades["attestation"] == NAO_APLICAVEL
    assert disponibilidades["similaridade_facial"] == NAO_APLICAVEL
    assert disponibilidades["prova_de_vida"] == NAO_APLICAVEL
    # Nenhum sinal disponivel em NENHUMA categoria -> fallback documentado,
    # nao penalizacao por ausencia de dado.
    assert resultado.score == SCORE_SEM_SINAIS


def test_biometria_exigida_e_ausente_penaliza_em_vez_de_excluir() -> None:
    """Achado da verificacao adversarial F14/A4, corrigido no mesmo
    fechamento: com a politica DEFAULT (`exige_facial`/`exige_liveness` =
    `True`, `politicas_registro`), a ausencia de sinal biometrico passa a
    contar como sinal REAL (nao `nao_aplicavel`) e penaliza o score -- a
    politica do tenant, quando exige o sinal, nao pode ser configuracao
    morta."""
    sinais = SinaisRegistro()  # nenhum sinal de biometria informado
    resultado = _compor(sinais)  # politica DEFAULT: exige_facial=exige_liveness=True
    por_sinal = {c.sinal: c for c in resultado.explicabilidade}
    assert por_sinal["similaridade_facial"].disponibilidade == REAL
    assert por_sinal["similaridade_facial"].pontuacao == 40.0
    assert por_sinal["prova_de_vida"].disponibilidade == REAL
    assert por_sinal["prova_de_vida"].pontuacao == 40.0


def test_biometria_real_quando_disponivel_sinal_sintetico_documentado() -> None:
    """Sinal SINTETICO documentado (nao vem de nenhum SDK real -- ver
    docstring do modulo): prova que a composicao usa `score_facial`/
    `liveness_aprovado` corretamente QUANDO a origem existir (F7, ou um
    facial-svc real no futuro)."""
    sinais = SinaisRegistro(score_facial=95.0, liveness_aprovado=True)
    resultado = _compor(sinais)
    por_sinal = {c.sinal: c for c in resultado.explicabilidade}
    assert por_sinal["similaridade_facial"].disponibilidade == REAL
    assert por_sinal["similaridade_facial"].pontuacao == pytest.approx(100.0, abs=1.0)
    assert por_sinal["prova_de_vida"].disponibilidade == REAL
    assert por_sinal["prova_de_vida"].pontuacao == 100.0


# ---------------------------------------------------------------------------
# Explicabilidade (ADR-008 regra 4): sinal, peso, contribuicao.
# ---------------------------------------------------------------------------


def test_explicabilidade_registra_peso_e_contribuicao_de_cada_sinal() -> None:
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0)
    resultado = _compor(
        sinais,
        contexto=ContextoDecisao(
            reputacao_dispositivo=80.0, velocidade_kmh=5.0, velocidade_impossivel=False
        ),
    )
    disponiveis = [c for c in resultado.explicabilidade if c.disponibilidade == REAL]
    assert disponiveis, "esperava ao menos um sinal disponivel"
    for contribuicao in disponiveis:
        assert contribuicao.peso_efetivo > 0
        assert contribuicao.pontuacao is not None
        assert contribuicao.contribuicao is not None
        assert contribuicao.contribuicao == pytest.approx(
            contribuicao.peso_efetivo * contribuicao.pontuacao / 100.0
        )
    # Soma das contribuicoes disponiveis, renormalizada, bate com o score.
    soma_peso = sum(c.peso_efetivo for c in disponiveis)
    soma_contrib = sum(c.contribuicao for c in disponiveis)
    assert round((soma_contrib / soma_peso) * 100.0) == resultado.score


def test_categoria_sem_sinal_disponivel_e_renormalizada_nao_inventa_valor() -> None:
    """So geolocalizacao disponivel (dispositivo/comportamento nao_
    aplicaveis; biometria nao exigida pela politica passada explicitamente
    -- ver `test_biometria_exigida_e_ausente_penaliza_em_vez_de_excluir`
    para o caso em que a politica exige e a categoria deixa de ser
    excluida): o peso das outras categorias e redistribuido, e o score
    reflete SO o sinal real -- nunca uma media que finge dado ausente."""
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0)
    politica = PoliticaAntifraude(exige_attestation=False, exige_facial=False, exige_liveness=False)
    resultado = _compor(sinais, politica=politica)
    disponiveis = [c for c in resultado.explicabilidade if c.disponibilidade == REAL]
    categorias_disponiveis = {c.categoria for c in disponiveis}
    assert categorias_disponiveis == {"geolocalizacao"}
    # Unico sinal real disponivel (geocerca dentro=True, pontuacao 100) e
    # mock_location (nao reportado -> tambem contribui, pontuacao 100).
    assert resultado.score == 100


def test_pesos_por_categoria_influenciam_o_score_final() -> None:
    """Duas categorias disponiveis com pontuacoes bem diferentes: o peso
    maior domina o resultado -- prova que os pesos de `politicas_registro`
    (via `PesosScore`) realmente entram na conta."""
    pesos_geo_dominante = PesosScore(
        dispositivo=90, biometria=0, geolocalizacao=10, comportamento=0
    )
    politica = PoliticaAntifraude(
        pesos=pesos_geo_dominante,
        perfil_confianca="personalizado",
        politica_root="bloquear",
        politica_modo_desenvolvedor="bloquear",
        politica_mock_location="bloquear",
        exige_attestation=False,
        exige_facial=False,
        exige_liveness=False,
        limiar_facial=75.0,
    )
    # Geocerca (peso 10) perfeita, reputacao de dispositivo (peso 90) pessima.
    sinais = SinaisRegistro(dentro_geocerca=True, distancia_geocerca_metros=0.0)
    resultado = _compor(
        sinais, politica=politica, contexto=ContextoDecisao(reputacao_dispositivo=5.0)
    )
    # Dominado pela reputacao ruim (peso 90) apesar da geocerca perfeita.
    assert resultado.score < 40
