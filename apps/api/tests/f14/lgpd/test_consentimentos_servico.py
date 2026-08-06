"""Testes de `app.lgpd.consentimentos` (F14/A3).

Cobre: hash obrigatorio na pratica, versao vigente por (tenant, finalidade),
revogacao versionada e o expurgo REAL do template biometrico disparado pela
revogacao -- o criterio de aceite mais concreto de A3 ("revogacao de
consentimento de biometria dispara expurgo do template de verdade").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
import sqlalchemy as sa
from ponto_contracts import Biometria, BiometriaTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.lgpd import consentimentos as servico
from tests.f14.lgpd.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


def _dados(
    *,
    colaborador_id: UUID,
    finalidade: str = "biometria_facial",
    versao_termo: str = "v1",
    hash_termo: str | None = "b" * 64,
) -> servico.DadosConsentimentoCriar:
    return servico.DadosConsentimentoCriar(
        colaborador_id=colaborador_id,
        finalidade=finalidade,
        versao_termo=versao_termo,
        texto_termo_ref=None,
        hash_termo=hash_termo,
        canal="app",
        ip="203.0.113.10",
        evidencia_ref=None,
        user_agent="pytest",
    )


async def test_criar_consentimento_sem_hash_e_val_001(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_consentimento(
            sessao_f14,
            tenant_id=contexto_organizacional.tenant_id,
            dados=_dados(colaborador_id=colaborador_id, hash_termo=None),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_consentimento_colaborador_inexistente_e_rec_001(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    from uuid import uuid4

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_consentimento(
            sessao_f14,
            tenant_id=contexto_organizacional.tenant_id,
            dados=_dados(colaborador_id=uuid4()),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_primeiro_consentimento_da_finalidade_aceita_qualquer_versao(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento = await servico.criar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, versao_termo="v3-qualquer"),
        usuario_id=None,
    )
    assert consentimento.status == "concedido"
    assert consentimento.versao_termo == "v3-qualquer"
    assert consentimento.concedido_em is not None
    assert consentimento.texto_termo_ref  # gerado por convencao, nunca vazio


async def test_segunda_versao_diferente_da_vigente_e_lgpd_004(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_a = await criar_colaborador()
    colaborador_b = await criar_colaborador()

    await servico.criar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_a, finalidade="uso_imagem", versao_termo="v1"),
        usuario_id=None,
    )
    await sessao_f14.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_consentimento(
            sessao_f14,
            tenant_id=contexto_organizacional.tenant_id,
            dados=_dados(colaborador_id=colaborador_b, finalidade="uso_imagem", versao_termo="v2"),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-LGPD-004"


async def test_consentimento_concedido_duplicado_e_conf_001(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    await servico.criar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, finalidade="comunicacao", versao_termo="v1"),
        usuario_id=None,
    )
    await sessao_f14.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_consentimento(
            sessao_f14,
            tenant_id=contexto_organizacional.tenant_id,
            dados=_dados(
                colaborador_id=colaborador_id, finalidade="comunicacao", versao_termo="v1"
            ),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_listar_consentimentos_filtra_por_finalidade_e_status(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    await criar_consentimento(colaborador_id=colaborador_id, finalidade="biometria_facial")
    await criar_consentimento(colaborador_id=colaborador_id, finalidade="comunicacao")
    await sessao_f14.flush()

    linhas, tem_mais, _ = await servico.listar_consentimentos(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        colaborador_id=colaborador_id,
        finalidade="comunicacao",
        status=None,
        cursor=None,
        limite=None,
        ordenar=None,
    )
    assert not tem_mais
    assert len(linhas) == 1
    assert linhas[0].finalidade == "comunicacao"


async def test_revogar_consentimento_muda_status_e_e_idempotente(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="geolocalizacao"
    )
    await sessao_f14.flush()

    revogado = await servico.revogar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        consentimento_id=consentimento_id,
        usuario_id=None,
    )
    assert revogado.status == "revogado"
    assert revogado.revogado_em is not None

    # Chamar de novo (reentrega de Idempotency-Key) nao muda nada nem falha.
    revogado_de_novo = await servico.revogar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        consentimento_id=consentimento_id,
        usuario_id=None,
    )
    assert revogado_de_novo.status == "revogado"


async def test_revogar_consentimento_inexistente_e_rec_001(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    from uuid import uuid4

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.revogar_consentimento(
            sessao_f14,
            tenant_id=contexto_organizacional.tenant_id,
            consentimento_id=uuid4(),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


# =============================================================================
# Aceite central de A3: revogar consentimento biometrico expurga o template
# DE VERDADE (nao so muda um status).
# =============================================================================


async def test_revogar_consentimento_biometrico_apaga_o_template_do_banco(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="biometria_facial"
    )
    biometria_id = await criar_biometria_com_template(
        colaborador_id=colaborador_id, modalidade="facial", consentimento_id=consentimento_id
    )
    await sessao_f14.flush()

    # Confirma que o template existe ANTES da revogacao.
    total_antes = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_antes == 1

    await servico.revogar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        consentimento_id=consentimento_id,
        usuario_id=None,
    )
    await sessao_f14.flush()

    # O template SUMIU de verdade -- nao e so um status mudado.
    total_depois = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_depois == 0

    biometria = (
        await sessao_f14.execute(sa.select(Biometria).where(Biometria.id == biometria_id))
    ).scalar_one()
    assert biometria.status == "revogada"
    assert biometria.revogada_em is not None


async def test_revogar_consentimento_nao_biometrico_nao_toca_biometria(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
) -> None:
    """Revogar `uso_imagem` nao deve mexer em credencial biometrica alguma
    -- so `biometria_facial`/`biometria_digital` disparam o expurgo."""
    colaborador_id = await criar_colaborador()
    consentimento_facial_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="biometria_facial"
    )
    biometria_id = await criar_biometria_com_template(
        colaborador_id=colaborador_id, consentimento_id=consentimento_facial_id
    )
    consentimento_imagem_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="uso_imagem"
    )
    await sessao_f14.flush()

    await servico.revogar_consentimento(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        consentimento_id=consentimento_imagem_id,
        usuario_id=None,
    )
    await sessao_f14.flush()

    total_templates = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_templates == 1  # intacto
