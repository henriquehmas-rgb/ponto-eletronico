"""O motor facial ligado as rotas de verdade, de ponta a ponta.

Ate 08/08/2026 o `facial-svc` era infraestrutura provada isoladamente e sem
nenhum chamador (`docs/backlog.md`: "NENHUMA rota de `apps/api`/`device-gw` foi
conectada a este motor"). Estes testes provam que os dois caminhos que faltavam
existem e funcionam contra o motor REAL, nao contra um dublê:

1. `POST /v1/biometrias` com `fotoBase64` extrai o vetor no `facial-svc` e
   persiste o template CIFRADO em `biometria_templates`, com `versao_modelo`
   exatamente como o motor carimbou.
2. `POST /v1/marcacoes` com `fotoBase64` compara a captura ao vivo contra esse
   template: **a mesma pessoa aprova**, **outra pessoa reprova** com
   `403 PONTO-SCORE-003` e sem vazar placar nem limiar.
3. `facial-svc` fora do ar nao estoura excecao nao capturada em nenhum dos
   dois: o cadastro recusa (`503 PONTO-INT-003`, retentavel) e a marcacao segue
   sem o sinal, com aviso -- a assimetria e deliberada e esta justificada em
   `app.marcacao.pipeline.facial`.

Nenhum destes testes usa `monkeypatch` no cliente HTTP. O caminho de erro e
produzido do jeito que a producao o produz: uma porta fechada.
"""

from __future__ import annotations

import base64
import os
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obter_configuracao
from tests.f14.facial.conftest import ContextoFacial, Fotos, cabecalhos

pytestmark = pytest.mark.asyncio

#: Carimbo que `apps/facial-svc/facial/config.py` define como padrao e que
#: `infra/docker-compose.yml` injeta. Conferido literalmente: um carimbo que
#: mente invalida a base biometrica inteira em silencio (ADR-006 regra 3, e o
#: achado corrigido em 08/08 -- `arcface-r100-v1` para um ResNet50).
VERSAO_MODELO_ESPERADA = "buffalo_l-w600k_r50-v1"

#: ArcFace `w600k_r50` produz 512 floats de 32 bits.
DIMENSAO_ESPERADA = 512
BYTES_ESPERADOS = DIMENSAO_ESPERADA * 4


async def _cadastrar_e_ativar(
    cliente: AsyncClient,
    sessao: AsyncSession,
    ctx: ContextoFacial,
    foto: str,
) -> uuid.UUID:
    """`criarBiometria` (extrai no motor) + `validarBiometria` (RH aprova).

    Os dois passos sao necessarios porque o cadastro nasce `pendente` por
    desenho: so credencial `ativa` entra numa verificacao.
    """
    resposta = await cliente.post(
        "/v1/biometrias",
        headers=cabecalhos(ctx.tenant_slug),
        json={
            "colaboradorId": str(ctx.colaborador_id),
            "modalidade": "facial",
            "origemCadastro": "rh",
            "consentimentoId": str(ctx.consentimento_id),
            "fotoBase64": foto,
        },
    )
    assert resposta.status_code == 201, resposta.text
    biometria_id = uuid.UUID(resposta.json()["id"])

    aprovacao = await cliente.post(
        f"/v1/biometrias/{biometria_id}/validar",
        headers=cabecalhos(ctx.tenant_slug),
        json={"decisao": "aprovar", "comentario": "teste de ponta a ponta"},
    )
    assert aprovacao.status_code == 200, aprovacao.text
    assert aprovacao.json()["status"] == "ativa"
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)}
    )
    return biometria_id


async def _marcar_ponto(cliente: AsyncClient, ctx: ContextoFacial, foto: str | None) -> Any:
    corpo: dict[str, Any] = {
        "colaboradorId": str(ctx.colaborador_id),
        "empresaId": str(ctx.empresa_id),
        "canal": "totem",
    }
    if foto is not None:
        corpo["fotoBase64"] = foto
    return await cliente.post("/v1/marcacoes", headers=cabecalhos(ctx.tenant_slug), json=corpo)


# ---------------------------------------------------------------------------
# 1. Enroll
# ---------------------------------------------------------------------------
async def test_enroll_persiste_template_real_extraido_da_foto(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc: str,
) -> None:
    """A rota extrai o vetor no motor e grava o template cifrado.

    Tres coisas sao conferidas, e as tres ja falharam em sistemas reais:
    a linha existe, o carimbo de versao e o do MOTOR (nao um valor que o
    cliente mandou), e o que esta no banco **nao** e o vetor em claro.
    """
    biometria_id = await _cadastrar_e_ativar(
        cliente_facial_http, sessao_facial, contexto_facial, fotos.pessoa_a_cadastro
    )

    linha = (
        await sessao_facial.execute(
            text(
                "SELECT versao_modelo, provedor, dimensao, template_cifrado, iv, "
                "       tag_autenticacao, ativo "
                "  FROM biometria_templates "
                " WHERE tenant_id = :t AND biometria_id = :b"
            ),
            {"t": str(contexto_facial.tenant_id), "b": str(biometria_id)},
        )
    ).one()

    assert linha.versao_modelo == VERSAO_MODELO_ESPERADA
    assert linha.provedor == "facial-svc"
    assert linha.dimensao == DIMENSAO_ESPERADA
    assert linha.ativo is True
    # AES-256-GCM: texto cifrado do mesmo tamanho do claro, com nonce e tag
    # fora (ADR-006 regra 1 e 2).
    assert len(bytes(linha.template_cifrado)) == BYTES_ESPERADOS
    assert len(bytes(linha.iv)) == 12
    assert len(bytes(linha.tag_autenticacao)) == 16

    # O vetor NUNCA sai pela API, nem para quem acabou de cadastra-lo
    # (ADR-006 regra 5).
    detalhe = await cliente_facial_http.get(
        f"/v1/biometrias/{biometria_id}", headers=cabecalhos(contexto_facial.tenant_slug)
    )
    assert detalhe.status_code == 200
    assert detalhe.json()["versaoModelo"] == VERSAO_MODELO_ESPERADA
    assert "vetor" not in detalhe.text
    assert "template" not in detalhe.text


async def test_enroll_recusa_foto_e_vetor_no_mesmo_corpo(
    cliente_facial_http: AsyncClient,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc: str,
) -> None:
    """Escolher em silencio entre os dois grava biometria da pessoa errada."""
    resposta = await cliente_facial_http.post(
        "/v1/biometrias",
        headers=cabecalhos(contexto_facial.tenant_slug),
        json={
            "colaboradorId": str(contexto_facial.colaborador_id),
            "modalidade": "facial",
            "origemCadastro": "rh",
            "consentimentoId": str(contexto_facial.consentimento_id),
            "fotoBase64": fotos.pessoa_a_cadastro,
            "vetor": base64.b64encode(b"\x00" * BYTES_ESPERADOS).decode("ascii"),
        },
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


async def test_enroll_sem_rosto_devolve_erro_tratado(
    cliente_facial_http: AsyncClient,
    contexto_facial: ContextoFacial,
    apontar_para_facial_svc: str,
) -> None:
    """Imagem sem rosto vem do motor como `PONTO-VAL-001` e chega assim ao
    cliente -- `problem+json`, nunca 500 nem stack trace."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    chapada = np.full((240, 240, 3), 127, dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", chapada)
    assert ok

    resposta = await cliente_facial_http.post(
        "/v1/biometrias",
        headers=cabecalhos(contexto_facial.tenant_slug),
        json={
            "colaboradorId": str(contexto_facial.colaborador_id),
            "modalidade": "facial",
            "origemCadastro": "rh",
            "consentimentoId": str(contexto_facial.consentimento_id),
            "fotoBase64": base64.b64encode(buffer.tobytes()).decode("ascii"),
        },
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# 2. Verificacao no registro de ponto
# ---------------------------------------------------------------------------
async def test_marcacao_com_a_mesma_pessoa_aprova(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc: str,
) -> None:
    """Cadastro com um recorte, marcacao com OUTRO recorte da mesma pessoa.

    Nao sao duas copias do mesmo arquivo: margens, escalas e qualidade JPEG
    diferentes -- o caso real do colaborador cadastrado em marco e batendo
    ponto em agosto.
    """
    await _cadastrar_e_ativar(
        cliente_facial_http, sessao_facial, contexto_facial, fotos.pessoa_a_cadastro
    )

    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, fotos.pessoa_a_marcacao)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert "facial_indisponivel" not in (corpo.get("avisos") or [])
    assert "facial_sem_template" not in (corpo.get("avisos") or [])

    # A explicabilidade tem que registrar que o sinal foi REAL e positivo --
    # sem isso o gestor nao sabe se a marcacao passou POR causa do facial ou
    # apesar da ausencia dele (ADR-008 regra 4).
    await sessao_facial.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(contexto_facial.tenant_id)},
    )
    flags = (
        await sessao_facial.execute(
            text(
                "SELECT flags_integridade, score_facial FROM marcacoes_meta "
                " WHERE tenant_id = :t AND marcacao_id = :m"
            ),
            {"t": str(contexto_facial.tenant_id), "m": corpo["marcacao"]["id"]},
        )
    ).one()
    sinais = [
        s
        for s in flags.flags_integridade["_antifraude"]["scoreExplicabilidade"]
        if s["sinal"] == "similaridade_facial"
    ]
    assert len(sinais) == 1
    assert sinais[0]["disponibilidade"] == "real"
    assert sinais[0]["valor"] is True
    # `score_facial` continua nulo de proposito: `/verificar` nao devolve
    # similaridade nem limiar (`PONTO-SCORE-003` tem `expoe_regra: false`), e
    # inventar um numero seria pior que nao ter.
    assert flags.score_facial is None


async def test_marcacao_com_pessoa_diferente_reprova(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc: str,
) -> None:
    """Outra pessoa da mesma foto de grupo -> `403 PONTO-SCORE-003`.

    E o teste que nao se prova com rosto sintetico: rosto gerado nao se parece
    com ninguem por construcao, entao reprovaria mesmo que a comparacao
    estivesse quebrada.
    """
    await _cadastrar_e_ativar(
        cliente_facial_http, sessao_facial, contexto_facial, fotos.pessoa_a_cadastro
    )

    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, fotos.pessoa_b)
    assert resposta.status_code == 403, resposta.text
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-SCORE-003"
    # `expoe_regra: false`: nem similaridade, nem valor de limiar, nem `detail`
    # do motor. (O TITULO do catalogo cita a palavra "limiar" -- "Similaridade
    # facial abaixo do limiar" --, o que e proposital e nao vaza nada: o que
    # nao pode aparecer e NUMERO nenhum que permita iterar ate acertar.)
    assert "detail" not in corpo
    assert "0.42" not in resposta.text
    assert "similaridade" not in {c.lower() for c in corpo}

    # E nenhuma marcacao foi gravada.
    await sessao_facial.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(contexto_facial.tenant_id)},
    )
    total = (
        await sessao_facial.execute(
            text("SELECT count(*) FROM marcacoes WHERE tenant_id = :t"),
            {"t": str(contexto_facial.tenant_id)},
        )
    ).scalar_one()
    assert total == 0


async def test_marcacao_sem_credencial_ativa_segue_com_aviso(
    cliente_facial_http: AsyncClient,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc: str,
) -> None:
    """Colaborador sem biometria ativa nao e reprovado por isso.

    ADR-006 regra 8: quem recusa a biometria registra ponto do mesmo jeito. O
    aviso existe para que a ausencia seja visivel na auditoria em vez de
    indistinguivel de uma captura que nunca foi enviada.
    """
    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, fotos.pessoa_a_marcacao)
    assert resposta.status_code == 201, resposta.text
    assert "facial_sem_template" in resposta.json()["avisos"]


# ---------------------------------------------------------------------------
# 3. facial-svc fora do ar
# ---------------------------------------------------------------------------
async def test_enroll_com_facial_svc_fora_do_ar_recusa_sem_gravar(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    apontar_para_facial_svc_fora_do_ar: str,
) -> None:
    """Falha FECHADA no cadastro: `503 PONTO-INT-003`, e nada persistido.

    Uma `biometrias` gravada sem template pareceria pronta para o RH aprovar e
    nao verificaria ninguem depois -- pior que a ausencia dela.
    """
    resposta = await cliente_facial_http.post(
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
    assert resposta.status_code == 503, resposta.text
    assert resposta.json()["codigo"] == "PONTO-INT-003"

    await sessao_facial.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(contexto_facial.tenant_id)},
    )
    total = (
        await sessao_facial.execute(
            text("SELECT count(*) FROM biometrias WHERE tenant_id = :t"),
            {"t": str(contexto_facial.tenant_id)},
        )
    ).scalar_one()
    assert total == 0


async def test_marcacao_com_facial_svc_fora_do_ar_segue_sem_o_sinal(
    cliente_facial_http: AsyncClient,
    sessao_facial: AsyncSession,
    contexto_facial: ContextoFacial,
    fotos: Fotos,
    url_facial_svc: str,
    apontar_para_facial_svc: str,
) -> None:
    """Cadastra com o motor de pe, verifica com ele fora do ar.

    A marcacao NAO e recusada -- decisao de produto ja registrada em ADR-008
    (bloquear por sinal indisponivel tira o registro de jornada do trabalhador
    por causa de um incidente de infraestrutura da SEEG). O que acontece e o
    aviso + a queda de pontuacao da categoria biometria, que a politica do
    tenant converte, ou nao, em revisao.

    O importante para esta tarefa: **nenhuma excecao nao capturada**. Antes do
    tratamento em `cliente_facial`, um `ConnectError` do httpx subiria pelo
    pipeline inteiro e viraria `500`.
    """
    await _cadastrar_e_ativar(
        cliente_facial_http, sessao_facial, contexto_facial, fotos.pessoa_a_cadastro
    )

    # Agora sim: derruba o alvo, sem tocar em nenhum modulo da aplicacao. A
    # fixture `apontar_para_facial_svc` restaura o valor anterior no teardown.
    os.environ["FACIAL_SVC_URL"] = "http://127.0.0.1:9"
    obter_configuracao.cache_clear()

    resposta = await _marcar_ponto(cliente_facial_http, contexto_facial, fotos.pessoa_a_marcacao)
    assert resposta.status_code == 201, resposta.text
    assert "facial_indisponivel" in resposta.json()["avisos"]
