"""T6 -- pipeline de `criarMarcacao` (`app.marcacao.pipeline.ingestao`).

Cobre os 7 casos felizes do produto (cada canal aceito x REP-P ativo) e ao
menos um caso de cada codigo de erro real listado no PCF. Com o motor de
confianca stub de A3 (sempre `score=100`, `classificacao="alta"`), nenhum
teste desta tarefa produz `PONTO-SCORE-*` nem `marcacao.suspeita` -- essa
ausencia e a propria asserção positiva do stub permissivo.
"""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.eventos import BARRAMENTO_INTERNO
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f5.conftest import ContextoF5


def _sujeito(contexto: ContextoF5, *, usuario_id: UUID | None = None) -> Sujeito:
    return Sujeito(
        usuario_id=usuario_id or uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar", "marcacoes.ler"}),
    )


def _corpo(
    contexto: ContextoF5,
    *,
    canal: str,
    external_id: str | None = None,
    dispositivo_id: UUID | None = None,
    log_externo_id: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    precisao_metros: float | None = None,
) -> contrato.MarcacaoCriar:
    return contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": canal,
            "externalId": external_id,
            "dispositivoId": str(dispositivo_id) if dispositivo_id else None,
            "logExternoId": log_externo_id,
            "latitude": latitude,
            "longitude": longitude,
            "precisaoMetros": precisao_metros,
        }
    )


@pytest.mark.parametrize("canal", ["terminal", "mobile", "web", "totem", "api"])
async def test_todos_os_canais_aceitos_produzem_marcacao_pelo_mesmo_caminho(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5, canal: str
) -> None:
    usuario_id = uuid.uuid4()
    if canal == "web":
        await _seed_sessao_reautenticada(sessao_f5, contexto_f5, usuario_id=usuario_id)
    sujeito = _sujeito(contexto_f5, usuario_id=usuario_id)
    dispositivo_id = contexto_f5.dispositivo_id if canal == "mobile" else None
    corpo = _corpo(
        contexto_f5,
        canal=canal,
        external_id=f"ext-{canal}" if canal == "api" else None,
        dispositivo_id=dispositivo_id,
    )
    resultado = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"idem-{canal}-{uuid.uuid4()}",
        sujeito=sujeito,
    )
    assert resultado.replay is False
    assert resultado.resposta.duplicada is False
    assert resultado.resposta.marcacao is not None
    assert resultado.resposta.marcacao.nsr is not None and resultado.resposta.marcacao.nsr >= 1
    assert resultado.resposta.marcacao.canal == canal
    assert resultado.resposta.comprovante is not None
    # Score/classificacao/revisao NAO sao mais asserados aqui (eram `== 100`/
    # `alta`/`False` fixos quando o motor de confianca ainda era o stub de
    # F5): F14 substituiu o corpo por um motor real (`app.antifraude.motor`)
    # cuja politica DEFAULT (`exige_facial`/`exige_liveness` = `True`)
    # penaliza a ausencia de biometria em qualquer canal deste teste, que
    # nao envia foto -- o valor exato e territorio de
    # `tests/f14/antifraude/test_motor_composicao.py`, nao deste teste, cujo
    # proposito e so confirmar que todo canal produz marcacao pelo mesmo
    # caminho (NSR, comprovante, idempotencia), nao validar score.
    assert resultado.resposta.score_confianca is not None


async def _seed_sessao_reautenticada(
    sessao: AsyncSession, contexto: ContextoF5, *, usuario_id: UUID | None
) -> UUID:
    usuario_id = usuario_id or uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :email, 'Usuario de Teste F5', 'ativo') "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "id": usuario_id,
            "tenant_id": contexto.tenant_id,
            "email": f"{usuario_id}@teste.f5.local",
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO sessoes "
            "(id, tenant_id, usuario_id, canal, iniciada_em, ultima_atividade_em, "
            " expira_em, reautenticado_em) "
            "VALUES (:id, :tenant_id, :usuario_id, 'web', now(), now(), "
            " now() + interval '1 hour', now())"
        ),
        {"id": uuid.uuid4(), "tenant_id": contexto.tenant_id, "usuario_id": usuario_id},
    )
    await sessao.flush()
    return usuario_id


async def test_reenvio_com_mesma_idempotency_key_devolve_original(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    chave = f"idem-replay-{uuid.uuid4()}"
    corpo = _corpo(contexto_f5, canal="api", external_id="ext-replay-1")

    primeiro = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=chave,
        sujeito=sujeito,
    )
    quantidade_antes = len(BARRAMENTO_INTERNO)

    segundo = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=chave,
        sujeito=sujeito,
    )

    assert primeiro.replay is False
    assert segundo.replay is True
    assert segundo.resposta.duplicada is True
    assert segundo.resposta.marcacao is not None
    assert primeiro.resposta.marcacao is not None
    assert segundo.resposta.marcacao.id == primeiro.resposta.marcacao.id
    assert segundo.resposta.marcacao.nsr == primeiro.resposta.marcacao.nsr
    # Nenhum evento novo publicado no replay puro.
    assert len(BARRAMENTO_INTERNO) == quantidade_antes


async def test_mesma_idempotency_key_com_corpo_diferente_responde_idem_002(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    chave = f"idem-conflito-{uuid.uuid4()}"
    corpo_1 = _corpo(contexto_f5, canal="api", external_id="ext-idem2-a")
    await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo_1,
        idempotency_key=chave,
        sujeito=sujeito,
    )
    corpo_2 = _corpo(contexto_f5, canal="api", external_id="ext-idem2-b")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo_2,
            idempotency_key=chave,
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-IDEM-002"


async def test_idempotency_key_ausente_responde_idem_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="api", external_id="ext-sem-idem")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=None,
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-IDEM-001"


async def test_colisao_de_external_id_sem_mesma_chave_responde_marc_003(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="api", external_id="ext-marc003")
    await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"idem-a-{uuid.uuid4()}",
        sujeito=sujeito,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-b-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-MARC-003"


async def test_colaborador_sem_vinculo_ativo_responde_marc_009(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    colaborador_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEMVINC', '19283746500', "
            "        'Sem Vinculo Ativo', 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": contexto_f5.tenant_id,
            "empresa_id": contexto_f5.empresa_id,
        },
    )
    await sessao_f5.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
            " data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, 'SEMVINC', "
            "        CURRENT_DATE - 10, FALSE, 'ativo')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f5.tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": contexto_f5.empresa_id,
        },
    )
    await sessao_f5.flush()

    sujeito = _sujeito(contexto_f5)
    corpo = contrato.MarcacaoCriar.model_validate(
        {"colaboradorId": str(colaborador_id), "canal": "api", "externalId": "ext-marc009"}
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-MARC-009"


async def test_empresa_sem_rep_p_ativo_responde_marc_010(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    empresa_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO empresas (id, tenant_id, tipo, cnpj, razao_social, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', '11222333000181', "
            " 'Empresa Sem REP-P Ltda', 'GO', '5208707')"
        ),
        {"id": empresa_id, "tenant_id": contexto_f5.tenant_id},
    )
    colaborador_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status, data_admissao) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEMREPP', '19283746501', "
            "        'Sem REP-P', 'ativo', CURRENT_DATE - 30)"
        ),
        {"id": colaborador_id, "tenant_id": contexto_f5.tenant_id, "empresa_id": empresa_id},
    )
    await sessao_f5.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
            " data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, 'SEMREPP', "
            "        CURRENT_DATE - 30, TRUE, 'ativo')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f5.tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
        },
    )
    await sessao_f5.flush()

    sujeito = _sujeito(contexto_f5)
    corpo = contrato.MarcacaoCriar.model_validate(
        {"colaboradorId": str(colaborador_id), "canal": "api", "externalId": "ext-marc010"}
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-MARC-010"


async def _definir_politica(
    sessao: AsyncSession,
    contexto: ContextoF5,
    *,
    unidade_id: UUID | None,
    canal: str | None,
    **campos: object,
) -> None:
    colunas = ", ".join(["id", "tenant_id", "empresa_id", "unidade_id", "canal", *campos.keys()])
    marcadores = ", ".join(
        [":id", ":tenant_id", ":empresa_id", ":unidade_id", ":canal"]
        + [f":{chave}" for chave in campos]
    )
    parametros: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": contexto.tenant_id,
        "empresa_id": contexto.empresa_id,
        "unidade_id": unidade_id,
        "canal": canal,
        **campos,
    }
    await sessao.execute(
        text(f"INSERT INTO politicas_registro ({colunas}) VALUES ({marcadores})"),  # noqa: S608
        parametros,
    )
    await sessao.flush()


async def test_fora_da_geocerca_com_politica_bloquear_responde_geo_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _definir_politica(
        sessao_f5,
        contexto_f5,
        unidade_id=None,
        canal=None,
        politica_fora_geocerca="bloquear",
    )
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(
        contexto_f5,
        canal="mobile",
        dispositivo_id=contexto_f5.dispositivo_id,
        latitude=contexto_f5.geocerca_latitude + 5.0,
        longitude=contexto_f5.geocerca_longitude + 5.0,
        precisao_metros=10.0,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-GEO-001"


async def test_fora_da_geocerca_com_politica_sinalizar_grava_e_avisa(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    # Sem override: DEFAULT de coluna e 'sinalizar'.
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(
        contexto_f5,
        canal="mobile",
        dispositivo_id=contexto_f5.dispositivo_id,
        latitude=contexto_f5.geocerca_latitude + 5.0,
        longitude=contexto_f5.geocerca_longitude + 5.0,
        precisao_metros=10.0,
    )
    resultado = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"idem-{uuid.uuid4()}",
        sujeito=sujeito,
    )
    assert resultado.resposta.dentro_geocerca is False
    assert "fora_da_geocerca" in (resultado.resposta.avisos or [])


async def test_precisao_insuficiente_responde_geo_002(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(
        contexto_f5,
        canal="mobile",
        dispositivo_id=contexto_f5.dispositivo_id,
        latitude=contexto_f5.geocerca_latitude,
        longitude=contexto_f5.geocerca_longitude,
        precisao_metros=float(contexto_f5.geocerca_tolerancia_metros * 10),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-GEO-002"


async def test_ip_fora_da_allowlist_com_exige_rede_responde_rede_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _definir_politica(
        sessao_f5,
        contexto_f5,
        unidade_id=None,
        canal=None,
        exige_rede_permitida=True,
    )
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="web")
    await _seed_sessao_reautenticada(sessao_f5, contexto_f5, usuario_id=sujeito.usuario_id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
            ip_origem="8.8.8.8",
        )
    assert excinfo.value.codigo == "PONTO-REDE-001"


async def test_ip_dentro_da_allowlist_com_exige_rede_passa(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _definir_politica(
        sessao_f5,
        contexto_f5,
        unidade_id=None,
        canal=None,
        exige_rede_permitida=True,
    )
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="web")
    await _seed_sessao_reautenticada(sessao_f5, contexto_f5, usuario_id=sujeito.usuario_id)
    resultado = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"idem-{uuid.uuid4()}",
        sujeito=sujeito,
        ip_origem="203.0.113.42",
    )
    assert resultado.resposta.marcacao is not None


async def test_mobile_sem_vinculo_de_dispositivo_responde_disp_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="mobile", dispositivo_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-DISP-001"


async def test_mobile_com_dispositivo_bloqueado_responde_disp_002(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await sessao_f5.execute(
        text("UPDATE dispositivos SET status = 'bloqueado' WHERE id = :id"),
        {"id": contexto_f5.dispositivo_id},
    )
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="mobile", dispositivo_id=contexto_f5.dispositivo_id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-DISP-002"


async def test_web_sem_reautenticacao_recente_responde_auth_011(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="web")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            corpo=corpo,
            idempotency_key=f"idem-{uuid.uuid4()}",
            sujeito=sujeito,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-011"


async def test_score_stub_nunca_bloqueia_nem_gera_revisao(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    """Historico: asserção positiva exigida pelo PCF de F5 (T6) para a epoca
    em que o motor de confianca era stub -- "com o motor stub de A3, NENHUM
    caso desta suite produz `PONTO-SCORE-*` nem `revisaoRequerida=true`".

    F14 substituiu o corpo do motor por composicao real
    (`app.antifraude.motor`, ADR-008); a garantia que sobrevive nao e mais
    "nunca gera revisao" (a politica DEFAULT exige biometria e este teste
    nao envia foto, entao HOJE gera revisao de proposito) e sim a original
    e mais forte, ja coberta por `test_todos_os_canais_aceitos_produzem_
    marcacao_pelo_mesmo_caminho`: uma marcacao sem nenhum sinal decisivo de
    fraude (mock location, camera virtual, emulador, root/dev bloqueado)
    NUNCA levanta `PONTO-SCORE-*`/`PONTO-DISP-*`/`PONTO-GEO-003` -- sinaliza
    para revisao humana, nunca bloqueia o registro."""
    sujeito = _sujeito(contexto_f5)
    corpo = _corpo(contexto_f5, canal="api", external_id="ext-score-stub")
    resultado = await ingestao.registrar_marcacao(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"idem-{uuid.uuid4()}",
        sujeito=sujeito,
    )
    assert resultado.resposta.marcacao is not None, "nao deveria bloquear o registro."
