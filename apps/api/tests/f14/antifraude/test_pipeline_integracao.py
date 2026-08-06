"""Integracao real do score de confianca com `app.marcacao.pipeline.ingestao.
registrar_marcacao` (Postgres real, banco `ponto_f14_a1`).

Cobre o que `test_motor_composicao.py` nao pode (aquele e 100% sintetico,
sem banco): que o pipeline de fato CALCULA os sinais (geocerca, velocidade,
reputacao de dispositivo) em vez de receber tudo pronto, que a explicabilidade
GRAVADA em `marcacoes_meta.flags_integridade` sobrevive a uma consulta real
(Aceite de A1), e que o score composto nunca chega no corpo da requisicao
(ADR-008 regra 1: campo nao existe na entrada, cliente nao pode mandar).
"""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.antifraude.explicabilidade import CHAVE_EXPLICABILIDADE
from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f14.antifraude.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    LATITUDE_DISTANTE,
    LONGITUDE_DISTANTE,
    ContextoF14A1,
    gerar_idempotency_key,
)


def _sujeito(contexto: ContextoF14A1) -> Sujeito:
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar", "marcacoes.ler"}),
    )


def _corpo(
    contexto: ContextoF14A1,
    *,
    canal: str = "mobile",
    latitude: float | None = None,
    longitude: float | None = None,
    dispositivo_id: UUID | None = None,
    flags_integridade: dict[str, object] | None = None,
) -> contrato.MarcacaoCriar:
    return contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": canal,
            "dispositivoId": str(dispositivo_id or contexto.dispositivo_id)
            if canal == "mobile"
            else None,
            "latitude": latitude,
            "longitude": longitude,
            "precisaoMetros": 5.0 if latitude is not None else None,
            "flagsIntegridade": flags_integridade,
        }
    )


async def _registrar(
    sessao: AsyncSession, contexto: ContextoF14A1, corpo: contrato.MarcacaoCriar
) -> ingestao.ResultadoRegistro:
    return await ingestao.registrar_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=_sujeito(contexto),
        ip_origem="203.0.113.10",
    )


async def _flags_gravadas(sessao: AsyncSession, tenant_id: UUID, marcacao_id: UUID) -> dict:
    linha = (
        (
            await sessao.execute(
                text(
                    "SELECT flags_integridade, score_confianca, classificacao_confianca, "
                    "       dentro_geocerca, distancia_geocerca_metros, revisao_status "
                    "FROM marcacoes_meta WHERE tenant_id = :tenant AND marcacao_id = :marcacao"
                ),
                {"tenant": str(tenant_id), "marcacao": str(marcacao_id)},
            )
        )
        .mappings()
        .one()
    )
    return dict(linha)


@pytest.mark.usefixtures("contexto_f14a1")
async def test_marcacao_dentro_da_geocerca_score_alto_sem_revisao(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    corpo = _corpo(contexto_f14a1, latitude=GEOCERCA_LATITUDE, longitude=GEOCERCA_LONGITUDE)
    resultado = await _registrar(sessao_f14a1, contexto_f14a1, corpo)

    assert resultado.resposta.revisao_requerida is False
    assert resultado.resposta.score_confianca >= 70
    assert resultado.resposta.classificacao_confianca == contrato.ClassificacaoConfianca1.alta

    linha = await _flags_gravadas(
        sessao_f14a1, contexto_f14a1.tenant_id, resultado.resposta.marcacao.id
    )
    assert linha["dentro_geocerca"] is True
    assert linha["revisao_status"] == "nao_requer"


async def test_mock_location_bloqueia_direto_independente_de_outros_sinais_bons(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """Sinal decisivo (ADR-008 regra 7) via HTTP body real -- mesmo com
    geocerca perfeita, mock location comprovado recusa direto."""
    corpo = _corpo(
        contexto_f14a1,
        latitude=GEOCERCA_LATITUDE,
        longitude=GEOCERCA_LONGITUDE,
        flags_integridade={"mockLocation": True},
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _registrar(sessao_f14a1, contexto_f14a1, corpo)
    assert excinfo.value.codigo == "PONTO-GEO-003"


async def test_mensagem_de_erro_nao_vaza_limiar_peso_ou_raio(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """`expoe_regra: false` (errors.yaml, PONTO-DISP-005: "ambiente
    comprometido" -- emulador detectado, o unico sinal decisivo desta fase
    sem toggle de politica, sempre bloqueia): o `ErroDeAplicacao` levantado
    pelo pipeline nunca carrega `detalhe`/`erros_campo` com informacao de
    peso/limiar/raio -- confirma pela ausencia de `detalhe`/`erros_campo` e
    pela leitura do proprio catalogo."""
    corpo = _corpo(
        contexto_f14a1,
        latitude=GEOCERCA_LATITUDE,
        longitude=GEOCERCA_LONGITUDE,
        flags_integridade={"emuladorDetectado": True},
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _registrar(sessao_f14a1, contexto_f14a1, corpo)

    erro = excinfo.value
    assert erro.codigo == "PONTO-DISP-005"
    assert erro.detalhe is None
    assert erro.erros_campo is None
    from app.core.catalogo_erros import entrada

    assert entrada(erro.codigo).expoe_regra is False
    # `contexto_log` e o UNICO lugar onde o sinal aparece -- vai para o log/
    # auditoria, nunca para a resposta HTTP (`app/core/erros.py::montar_problema`
    # so promove `detalhe`/`erros_campo`, nunca `contexto_log`).
    assert "sinal" in erro.contexto_log

    # Defesa em profundidade: monta a resposta HTTP real
    # (`app.core.erros.montar_problema`) e confirma que nenhum campo de
    # configuracao (peso, limiar, raio) aparece no corpo entregue ao cliente.
    from app.core.erros import montar_problema

    _status, corpo_resposta = montar_problema(
        codigo=erro.codigo,
        caminho="/v1/marcacoes",
        detalhe=erro.detalhe,
        erros_campo=erro.erros_campo,
    )
    assert "detail" not in corpo_resposta
    assert "errosCampo" not in corpo_resposta


async def test_cliente_nao_pode_forcar_score_alto_campo_nao_existe_na_entrada(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """ADR-008 regra 1: 'cliente que manda score: 100 e ignorado por
    construcao -- o campo nao existe na entrada'. `MarcacaoCriar` (contrato)
    nao tem `scoreConfianca` -- mesmo que o corpo bruto contenha a chave, o
    schema Pydantic a descarta antes de qualquer logica de negocio ver."""
    assert not hasattr(contrato.MarcacaoCriar.model_fields, "score_confianca")
    corpo_bruto = {
        "colaboradorId": str(contexto_f14a1.colaborador_id),
        "empresaId": str(contexto_f14a1.empresa_id),
        "unidadeId": str(contexto_f14a1.unidade_id),
        "canal": "mobile",
        "dispositivoId": str(contexto_f14a1.dispositivo_id),
        "scoreConfianca": 100,
        "flagsIntegridade": {"mockLocation": True},
    }
    corpo = contrato.MarcacaoCriar.model_validate(corpo_bruto)
    # O campo extra simplesmente nao existe no objeto validado.
    assert not hasattr(corpo, "score_confianca") and not hasattr(corpo, "scoreConfianca")
    # E o mock_location (sinal decisivo, real) ainda recusa -- prova que o
    # "scoreConfianca: 100" injetado no corpo bruto nao teve nenhum efeito.
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _registrar(sessao_f14a1, contexto_f14a1, corpo)
    assert excinfo.value.codigo == "PONTO-GEO-003"


async def test_velocidade_impossivel_entre_marcacoes_consecutivas_aciona_revisao(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """Duas marcacoes do MESMO colaborador, poucos minutos de diferenca,
    ~2000km de distancia (sede em Goiania -> Manaus): velocidade implicita
    muito acima de `VELOCIDADE_IMPOSSIVEL_KMH` -- sinal REAL, calculado por
    `app.antifraude.geografia.calcular_deslocamento` a partir de duas
    marcacoes reais no banco, nao sintetico."""
    primeira = await _registrar(
        sessao_f14a1,
        contexto_f14a1,
        _corpo(contexto_f14a1, latitude=GEOCERCA_LATITUDE, longitude=GEOCERCA_LONGITUDE),
    )
    assert primeira.resposta.revisao_requerida is False

    segunda = await _registrar(
        sessao_f14a1,
        contexto_f14a1,
        _corpo(contexto_f14a1, latitude=LATITUDE_DISTANTE, longitude=LONGITUDE_DISTANTE),
    )
    linha = await _flags_gravadas(
        sessao_f14a1, contexto_f14a1.tenant_id, segunda.resposta.marcacao.id
    )
    explicabilidade = linha["flags_integridade"][CHAVE_EXPLICABILIDADE]["scoreExplicabilidade"]
    velocidade = next(s for s in explicabilidade if s["sinal"] == "velocidade_deslocamento")
    assert velocidade["disponibilidade"] == "real"
    assert velocidade["pontuacao"] == 0.0
    assert "velocidade_implausivel" in (segunda.resposta.avisos or [])


async def test_explicabilidade_gravada_sobrevive_a_consulta_direta_do_banco(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """Aceite de A1: 'explicabilidade gravada em marcacoes_meta sobrevive a
    consulta por API'. Este teste verifica a camada de PERSISTENCIA (a
    consulta HTTP real e `test_explicabilidade_http.py`, no mesmo diretorio):
    depois do commit, uma nova leitura (`SELECT` cru, equivalente ao que
    `app.marcacao.consulta.marcacoes._mapa_meta_por_marcacao` faz) devolve o
    bloco `_antifraude` com sinal, peso e contribuicao intactos."""
    corpo = _corpo(contexto_f14a1, latitude=GEOCERCA_LATITUDE, longitude=GEOCERCA_LONGITUDE)
    resultado = await _registrar(sessao_f14a1, contexto_f14a1, corpo)
    await sessao_f14a1.commit()
    from tests.f14.antifraude.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f14a1, contexto_f14a1.tenant_id)

    linha = await _flags_gravadas(
        sessao_f14a1, contexto_f14a1.tenant_id, resultado.resposta.marcacao.id
    )
    bloco = linha["flags_integridade"][CHAVE_EXPLICABILIDADE]
    assert bloco["limiarBloqueio"] == 40
    assert bloco["limiarRevisao"] == 70
    assert bloco["perfilConfianca"] == "equilibrado"
    sinais_gravados = {s["sinal"] for s in bloco["scoreExplicabilidade"]}
    assert "geocerca" in sinais_gravados
    assert "reputacao_dispositivo" in sinais_gravados


async def test_reputacao_de_dispositivo_com_historico_suspeito_reduz_score(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """Reputacao de dispositivo (`app.antifraude.reputacao`) e sinal REAL
    calculado por consulta ao banco -- este teste prova isso marcando o
    dispositivo com `root_detectado=true` na propria tabela `dispositivos`
    (estado persistido, nao o self-report do corpo da requisicao) e
    verificando que a marcacao seguinte reflete a penalidade."""
    await sessao_f14a1.execute(
        text("UPDATE dispositivos SET root_detectado = TRUE WHERE id = :id"),
        {"id": str(contexto_f14a1.dispositivo_id)},
    )
    await sessao_f14a1.flush()

    resultado = await _registrar(
        sessao_f14a1,
        contexto_f14a1,
        _corpo(contexto_f14a1, latitude=GEOCERCA_LATITUDE, longitude=GEOCERCA_LONGITUDE),
    )
    linha = await _flags_gravadas(
        sessao_f14a1, contexto_f14a1.tenant_id, resultado.resposta.marcacao.id
    )
    bloco = linha["flags_integridade"][CHAVE_EXPLICABILIDADE]["scoreExplicabilidade"]
    reputacao = next(s for s in bloco if s["sinal"] == "reputacao_dispositivo")
    assert reputacao["disponibilidade"] == "real"
    assert reputacao["pontuacao"] < 100.0
