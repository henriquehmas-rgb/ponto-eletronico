"""`facial-svc:/liveness` ligado ao registro de ponto, contra o motor REAL.

Em 09/08 a verificacao facial (`/verificar`) ganhou chamador e a prova de vida
nao: `docs/backlog.md` registrou "`/liveness` continua sem chamador" como gap
aberto. Estes testes fecham esse gap e, mais importante, fixam a propriedade que
o distingue da verificacao -- **prova de vida reprovada nao bloqueia marcacao**.

Por que essa propriedade precisa de teste proprio
--------------------------------------------------

Porque a intuicao empurra para o contrario, e o codigo que a implementa e uma
unica palavra (`exigirAprovacao: false` em `app.biometria.cliente_facial`).
Trocar essa palavra por `true` continuaria passando em qualquer teste que so
verificasse "o sinal foi gravado" -- e transformaria uma heuristica
declaradamente falivel (`facial/motor/liveness.py` abre o modulo dizendo que
nao e classificador treinado) em portao sobre a jornada do trabalhador, contra
ADR-008. O teste que protege isso e o que exige `201` COM `liveness_aprovado`
falso no banco.

Os quatro desfechos exercitados
-------------------------------

======================================  =====================================
Situacao                                 Efeito na marcacao
======================================  =====================================
Sequencia real com movimento             `201`, sinal REAL positivo no score.
Simulacao de tela / foto impressa /      `201` **mesmo assim**, sinal REAL
quadro congelado                         negativo + aviso `liveness_reprovado`.
`facial-svc` fora do ar                  `201`, sem sinal + aviso.
Evidencia sem sequencia utilizavel       `201`, sem sinal + aviso; nunca um
                                         `False` inventado (ADR-014).
======================================  =====================================

Nenhum `monkeypatch` no cliente HTTP: o motor e real (pesos ONNX), e o caminho
de indisponibilidade e produzido por uma porta fechada, como em producao.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obter_configuracao
from tests.f14.facial.conftest import ContextoFacial, Fotos, Quadros, cabecalhos

pytestmark = pytest.mark.asyncio


async def _marcar_ponto(
    cliente: AsyncClient,
    ctx: ContextoFacial,
    *,
    quadros: list[str] | None = None,
    evidencia: dict[str, Any] | None = None,
    foto: str | None = None,
) -> Any:
    """`POST /v1/marcacoes` no canal `totem`.

    Os quadros viajam em `livenessEvidencia.quadrosBase64` -- o campo objeto de
    forma livre que o contrato ja declarava ("Evidencia do desafio de vivacidade
    executado") e que ninguem lia. Nenhum campo novo foi acrescentado ao
    `openapi.yaml` para esta integracao.
    """
    corpo: dict[str, Any] = {
        "colaboradorId": str(ctx.colaborador_id),
        "empresaId": str(ctx.empresa_id),
        "canal": "totem",
    }
    if quadros is not None:
        corpo["livenessMetodo"] = "passivo"
        corpo["livenessEvidencia"] = {"quadrosBase64": quadros}
    if evidencia is not None:
        corpo["livenessEvidencia"] = evidencia
    if foto is not None:
        corpo["fotoBase64"] = foto
    return await cliente.post("/v1/marcacoes", headers=cabecalhos(ctx.tenant_slug), json=corpo)


async def _meta(sessao: AsyncSession, ctx: ContextoFacial, marcacao_id: str) -> Any:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)}
    )
    return (
        await sessao.execute(
            text(
                "SELECT liveness_aprovado, liveness_metodo, flags_integridade "
                "  FROM marcacoes_meta WHERE tenant_id = :t AND marcacao_id = :m"
            ),
            {"t": str(ctx.tenant_id), "m": marcacao_id},
        )
    ).one()


def _sinal_prova_de_vida(flags: Any) -> dict[str, Any]:
    """A contribuicao do sinal `prova_de_vida` na explicabilidade do score."""
    sinais = [
        s for s in flags["_antifraude"]["scoreExplicabilidade"] if s["sinal"] == "prova_de_vida"
    ]
    assert len(sinais) == 1, sinais
    resultado: dict[str, Any] = sinais[0]
    return resultado


# ---------------------------------------------------------------------------
# 1. Sequencia viva
# ---------------------------------------------------------------------------
async def test_sequencia_com_movimento_aprova_e_grava_o_sinal(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    quadros: Quadros,
    apontar_para_facial_svc: str,
) -> None:
    """Tres quadros da mesma pessoa com a janela deslocando alguns pixels.

    Sem este teste, a heuristica poderia estar reprovando tudo -- e uma prova de
    vida que reprova todo mundo passaria em todos os testes negativos abaixo sem
    servir para nada.
    """
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, quadros=quadros.vivos)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    avisos = corpo.get("avisos") or []
    assert "liveness_reprovado" not in avisos
    assert "liveness_indisponivel" not in avisos

    linha = await _meta(sessao_facial, contexto_facial, corpo["marcacao"]["id"])
    assert linha.liveness_aprovado is True
    assert linha.liveness_metodo == "passivo"

    sinal = _sinal_prova_de_vida(linha.flags_integridade)
    assert sinal["disponibilidade"] == "real"
    assert sinal["valor"] is True


# ---------------------------------------------------------------------------
# 2. Reprovacao NAO bloqueia -- o coracao desta tarefa
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ataque", ["tela", "papel", "congelado"])
async def test_liveness_reprovado_nao_impede_a_marcacao(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    quadros: Quadros,
    apontar_para_facial_svc: str,
    ataque: str,
) -> None:
    """As tres simulacoes reprovam no motor -- e a marcacao acontece do mesmo jeito.

    `201` e a assercao que importa. Prova de vida por heuristica e sinal de
    confianca (ADR-008 + a decisao de 08/08 sobre a heuristica nao ser modelo
    treinado); um falso positivo dela viraria trabalhador sem registro de
    jornada, que e problema juridico da empresa. O sinal negativo entra no score
    e a politica do tenant decide -- por `limiar_bloqueio`, calibravel -- se
    aquilo vira revisao.
    """
    sequencia: list[str] = getattr(quadros, ataque)
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, quadros=sequencia)

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert "liveness_reprovado" in corpo["avisos"]

    linha = await _meta(sessao_facial, contexto_facial, corpo["marcacao"]["id"])
    assert linha.liveness_aprovado is False

    sinal = _sinal_prova_de_vida(linha.flags_integridade)
    assert sinal["disponibilidade"] == "real"
    assert sinal["valor"] is False
    # Zero na categoria biometria, e nao recusa: e essa a diferenca entre
    # "pontuar" e "bloquear".
    assert sinal["pontuacao"] == 0


async def test_liveness_reprovado_com_facial_aprovado_ainda_marca(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    quadros: Quadros,
    apontar_para_facial_svc: str,
) -> None:
    """Os dois sinais na MESMA marcacao, discordando: facial aprova, vida reprova.

    E o caso que separa os dois regimes de decisao no mesmo pipeline --
    `/verificar` recusaria (403) se discordasse, `/liveness` nao recusa nunca.
    """
    cadastro = await cliente_facial_http.post(
        "/v1/biometrias",
        headers=cabecalhos(contexto_facial.tenant_slug),
        json={
            "colaboradorId": str(contexto_facial.colaborador_id),
            "modalidade": "facial",
            "origemCadastro": "rh",
            "consentimentoId": str(contexto_facial.consentimento_id),
            "fotoBase64": fotos.pessoa_a_cadastro,
        },
    )
    assert cadastro.status_code == 201, cadastro.text
    aprovacao = await cliente_facial_http.post(
        f"/v1/biometrias/{cadastro.json()['id']}/validar",
        headers=cabecalhos(contexto_facial.tenant_slug),
        json={"decisao": "aprovar", "comentario": "teste de prova de vida"},
    )
    assert aprovacao.status_code == 200, aprovacao.text

    resposta = await _marcar_ponto(
        cliente_facial_http,
        contexto_facial,
        quadros=quadros.tela,
        foto=fotos.pessoa_a_marcacao,
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert "liveness_reprovado" in corpo["avisos"]
    assert "facial_indisponivel" not in corpo["avisos"]
    assert "facial_sem_template" not in corpo["avisos"]

    linha = await _meta(sessao_facial, contexto_facial, corpo["marcacao"]["id"])
    assert linha.liveness_aprovado is False
    explicabilidade = linha.flags_integridade["_antifraude"]["scoreExplicabilidade"]
    por_sinal = {s["sinal"]: s for s in explicabilidade}
    assert por_sinal["similaridade_facial"]["valor"] is True
    assert por_sinal["prova_de_vida"]["valor"] is False


# ---------------------------------------------------------------------------
# 3. Sem sinal: nem aprovado, nem reprovado
# ---------------------------------------------------------------------------
async def test_facial_svc_fora_do_ar_segue_com_aviso_e_sem_sinal(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    quadros: Quadros,
    apontar_para_facial_svc_fora_do_ar: str,
) -> None:
    """Porta fechada: `ConnectError` real, tratado antes de virar `500`.

    `liveness_aprovado` fica NULO, e nao `false`: ausencia de sinal nunca e
    evidencia de fraude (`SCORE_SEM_SINAIS = 100`, ADR-014).
    """
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, quadros=quadros.vivos)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert "liveness_indisponivel" in corpo["avisos"]

    linha = await _meta(sessao_facial, contexto_facial, corpo["marcacao"]["id"])
    assert linha.liveness_aprovado is None
    # A politica deste tenant nao exige prova de vida, entao o sinal ausente e
    # `nao_aplicavel` e o peso da categoria e renormalizado -- nao penalizado.
    assert _sinal_prova_de_vida(linha.flags_integridade)["disponibilidade"] == "nao_aplicavel"


@pytest.mark.parametrize(
    ("rotulo", "evidencia"),
    [
        ("quadro_unico", "UNICO"),
        ("chave_ausente", {"desafio": "piscar", "resultado": "ok"}),
        ("tipo_errado", {"quadrosBase64": "nao_e_lista"}),
        ("item_nao_string", {"quadrosBase64": [1, 2]}),
    ],
)
async def test_evidencia_sem_sequencia_utilizavel_nao_vira_reprovacao(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    quadros: Quadros,
    apontar_para_facial_svc: str,
    rotulo: str,
    evidencia: Any,
) -> None:
    """Integracao incompleta do cliente e defeito dele, nao evidencia de fraude.

    O caso `quadro_unico` e o mais importante: uma unica imagem faria o motor
    reprovar por construcao (prova de vida sobre imagem estatica e ilusao de
    seguranca), e gravar esse `false` seria transformar "o app so mandou uma
    foto" em "o colaborador tentou fraudar". A API nem chega a chamar.
    """
    corpo_evidencia = {"quadrosBase64": quadros.vivos[:1]} if evidencia == "UNICO" else evidencia
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, evidencia=corpo_evidencia)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert "liveness_evidencia_invalida" in corpo["avisos"]
    assert "liveness_reprovado" not in corpo["avisos"]

    linha = await _meta(sessao_facial, contexto_facial, corpo["marcacao"]["id"])
    assert linha.liveness_aprovado is None


async def test_marcacao_sem_evidencia_nenhuma_nao_gera_aviso(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    apontar_para_facial_svc: str,
) -> None:
    """O caso da imensa maioria das marcacoes: nada muda, nenhum aviso novo.

    Uma integracao que passa a avisar em todo registro treina o operador a
    ignorar avisos, e o dia em que um importar ele nao vai ler.
    """
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial)
    assert resposta.status_code == 201, resposta.text
    avisos = resposta.json()["avisos"]
    assert not [a for a in avisos if a.startswith("liveness_")]

    linha = await _meta(sessao_facial, contexto_facial, resposta.json()["marcacao"]["id"])
    assert linha.liveness_aprovado is None


# ---------------------------------------------------------------------------
# 4. Controle negativo do proprio ambiente
# ---------------------------------------------------------------------------
async def test_o_motor_desta_suite_e_o_real(
    contexto_facial: ContextoFacial,
    cliente_facial_http: AsyncClient,
    quadros: Quadros,
    url_facial_svc: str,
    apontar_para_facial_svc: str,
) -> None:
    """Guarda contra a suite inteira "passar" falando com o servico errado.

    Se `FACIAL_SVC_URL` apontasse para qualquer outra coisa, os testes acima
    cairiam todos no caminho de indisponibilidade -- que aprova a marcacao e
    portanto nao falharia sozinho.
    """
    assert obter_configuracao().facial_svc_url == url_facial_svc
    assert os.environ["FACIAL_SVC_URL"] == url_facial_svc
    # Sequencias diferentes precisam produzir vereditos diferentes: um servico
    # que responde sempre a mesma coisa nao esta julgando nada.
    viva = await _marcar_ponto(cliente_facial_http, contexto_facial, quadros=quadros.vivos)
    morta = await _marcar_ponto(cliente_facial_http, contexto_facial, quadros=quadros.congelado)
    assert viva.status_code == 201 and morta.status_code == 201
    assert "liveness_reprovado" not in (viva.json()["avisos"] or [])
    assert "liveness_reprovado" in morta.json()["avisos"]


async def test_o_cliente_nunca_pede_aprovacao_ao_liveness() -> None:
    """Le o codigo-fonte do cliente e exige `exigirAprovacao: False` no `/liveness`.

    Assercao sobre texto e feia, e aqui ela e o ponto: `exigirAprovacao: True`
    faria o motor devolver `403 PONTO-SCORE-002` e a marcacao seria RECUSADA por
    prova de vida heuristica -- contradizendo ADR-008 e a decisao de 08/08.
    Nenhum dos testes de comportamento acima falharia de imediato num ambiente
    onde o motor por acaso aprovasse; este falha sempre.
    """
    import inspect

    from app.biometria import cliente_facial

    fonte = inspect.getsource(cliente_facial.liveness)
    assert '"exigirAprovacao": False' in fonte
    assert '"exigirAprovacao": True' not in fonte


async def test_uuid_do_modulo_nao_vaza_identidade_para_o_facial_svc() -> None:
    """A `referencia` enviada ao motor e opaca: `marcacao:<uuid>`, nunca CPF/nome.

    O `facial-svc` nao tem credencial de banco de proposito (ADR-006); mandar
    identificador de negocio para la desfaria essa separacao em uma linha.
    """
    import inspect

    from app.marcacao.pipeline import facial

    fonte = inspect.getsource(facial.julgar_prova_de_vida)
    assert 'referencia=f"marcacao:{colaborador_id}"' in fonte
    assert str(uuid.uuid4()) not in fonte  # sanidade: nada fixo aqui
