"""Testes de `app.workflow.fechamento.assinatura` (T8, F10/A2).

Cobre os critérios "pronto quando": recusa de assinatura com hash
divergente; `UPDATE`/`DELETE` direto em `assinaturas_espelho` falha com
`ERRCODE 42501` (role de aplicação real, mesmo padrão de evidência que F4
exigiu para `bh_lancamentos`); recomputar `SHA256` do `conteudo` do espelho
e comparar com `hash_assinado` confirma a assinatura, e uma alteração
hipotética do `conteudo` (via SQL direto) quebra essa conferência.
"""

from __future__ import annotations

import pytest
from ponto_contracts import Espelho, Periodo
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento.assinatura import assinar_espelho, verificar_assinatura
from app.workflow.fechamento.espelho import gerar_espelho_do_vinculo
from app.workflow.fechamento.eventos import BARRAMENTO_INTERNO, limpar_barramento
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


async def _espelho_previo(sessao, contexto: ContextoF10) -> Espelho:
    periodo = await _periodo(sessao, contexto)
    return await gerar_espelho_do_vinculo(
        sessao,
        contexto.tenant_id,
        periodo,
        contexto.vinculo_id,
        "previo",
        usuario_id=contexto.rh_usuario_id,
    )


@pytest.fixture(autouse=True)
def _barramento_limpo():
    limpar_barramento()
    yield
    limpar_barramento()


@pytest.mark.asyncio
async def test_assinar_com_hash_divergente_e_conf_002(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await assinar_espelho(
            sessao_f10,
            contexto_f10.tenant_id,
            espelho.id,
            esquemas.AssinaturaEspelhoRequisicao(hashSha256="0" * 64, aceite=True),
            usuario_id=contexto_f10.colaborador_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-002"


@pytest.mark.asyncio
async def test_assinar_com_hash_correto_grava_e_publica_evento(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)

    assinatura = await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
        ip="203.0.113.10",
        user_agent="pytest",
    )
    assert assinatura.status == "assinado"
    assert assinatura.metodo == "aceite_eletronico"
    assert assinatura.hash_assinado == espelho.hash_sha256
    assert assinatura.signatario_colaborador_id == contexto_f10.colaborador_id

    eventos = [e for e in BARRAMENTO_INTERNO if e["tipo"] == "espelho.assinado"]
    assert len(eventos) == 1
    dados = eventos[0]["dados"]
    assert dados["espelhoId"] == str(espelho.id)
    assert dados["metodo"] == "aceiteEletronico"  # camelCase no payload do evento
    assert dados["hashAssinado"] == espelho.hash_sha256


@pytest.mark.asyncio
async def test_assinar_de_novo_o_mesmo_espelho_e_fisc_007(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)
    await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await assinar_espelho(
            sessao_f10,
            contexto_f10.tenant_id,
            espelho.id,
            esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
            usuario_id=contexto_f10.colaborador_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-FISC-007"


@pytest.mark.asyncio
async def test_recusa_nao_publica_evento_e_exige_motivo(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await assinar_espelho(
            sessao_f10,
            contexto_f10.tenant_id,
            espelho.id,
            esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=False),
            usuario_id=contexto_f10.colaborador_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"

    assinatura = await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(
            hashSha256=espelho.hash_sha256, aceite=False, recusaMotivo="Nao concordo com um dia."
        ),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    assert assinatura.status == "recusado"
    assert not [e for e in BARRAMENTO_INTERNO if e["tipo"] == "espelho.assinado"]


@pytest.mark.asyncio
async def test_update_direto_em_assinaturas_espelho_falha_42501(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)
    assinatura = await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    await sessao_f10.flush()

    with pytest.raises(DBAPIError) as excinfo:
        await sessao_f10.execute(
            text("UPDATE assinaturas_espelho SET status = 'expirado' WHERE id = :id"),
            {"id": assinatura.id},
        )
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    await sessao_f10.rollback()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)


@pytest.mark.asyncio
async def test_delete_direto_em_assinaturas_espelho_falha_42501(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)
    assinatura = await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    await sessao_f10.flush()

    with pytest.raises(DBAPIError) as excinfo:
        await sessao_f10.execute(
            text("DELETE FROM assinaturas_espelho WHERE id = :id"), {"id": assinatura.id}
        )
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    await sessao_f10.rollback()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)


@pytest.mark.asyncio
async def test_verificacao_e_recomputacao(sessao_f10, contexto_f10: ContextoF10) -> None:
    espelho = await _espelho_previo(sessao_f10, contexto_f10)
    assinatura = await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    await sessao_f10.flush()

    assert await verificar_assinatura(sessao_f10, contexto_f10.tenant_id, assinatura.id) is True

    # Adulteracao hipotetica do conteudo via SQL direto (simulando fraude) --
    # `espelhos` NAO tem gatilho de imutabilidade (PCF §2.4 item 5), entao o
    # UPDATE aqui e permitido pelo banco; e a APLICACAO que nunca faz isso em
    # operacao normal (`espelho.py` so cria linha nova). A verificacao deve
    # detectar a divergencia.
    await sessao_f10.execute(
        text(
            "UPDATE espelhos SET conteudo = conteudo || '{\"adulterado\": true}'::jsonb "
            "WHERE id = :id"
        ),
        {"id": espelho.id},
    )
    await sessao_f10.flush()
    # `sessao.get()` dentro de `verificar_assinatura` devolveria o objeto do
    # identity map (ainda com o `conteudo` antigo em memoria) sem isto --
    # gotcha do ORM ao misturar SQL cru com objeto ja carregado na MESMA
    # sessao, não um comportamento de producao (um auditor real abriria uma
    # sessao propria, sempre fresca). `refresh` (não `expire_all`) porque
    # precisa ser awaited: expirar `assinatura` também faria o acesso
    # síncrono a `assinatura.id` mais abaixo tentar um lazy-load fora de
    # contexto assíncrono (`MissingGreenlet`).
    await sessao_f10.refresh(espelho)

    assert await verificar_assinatura(sessao_f10, contexto_f10.tenant_id, assinatura.id) is False
