"""Testes de `app/biometria/servico.py` (T9 do PCF da F2).

Cobre os criterios de aceite 5 e 6 da secao 7 que dependem do banco: template
lido DIRETO da tabela e ilegivel; uma credencial ativa por colaborador e
modalidade; e toda leitura de template grava `acessos_dados_sensiveis`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from ponto_contracts import AcessoDadoSensivel, BiometriaTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria import servico
from app.core.erros import ErroDeAplicacao
from tests.f2.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


def _dados_criar(
    *,
    colaborador_id: UUID,
    consentimento_id: UUID | None,
    modalidade: str = "facial",
    origem_cadastro: str = "app",
    vetor: bytes | None = b"vetor-de-teste-nao-e-imagem-crua",
) -> servico.DadosBiometriaCriar:
    return servico.DadosBiometriaCriar(
        colaborador_id=colaborador_id,
        modalidade=modalidade,
        origem_cadastro=origem_cadastro,
        consentimento_id=consentimento_id,
        qualidade=91.5,
        identificador_cartao=None,
        vetor=vetor,
        versao_modelo="arcface-r100-v1",
        provedor="facial-svc",
        dimensao=512,
    )


async def test_criar_biometria_facial_sem_consentimento_e_lgpd_001(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    dados = _dados_criar(colaborador_id=colaborador_id, consentimento_id=None)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_biometria(
            sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-LGPD-001"


async def test_criar_biometria_cartao_nao_exige_consentimento(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    """So facial e digital exigem consentimento (PCF secao 2); cartao, pin e
    qrcode sao fallback e nao carregam vetor biometrico de verdade."""
    colaborador_id = await criar_colaborador()
    dados = servico.DadosBiometriaCriar(
        colaborador_id=colaborador_id,
        modalidade="cartao",
        origem_cadastro="rh",
        consentimento_id=None,
        qualidade=None,
        identificador_cartao="CARTAO-0001",
        vetor=None,
        versao_modelo=None,
        provedor="facial-svc",
        dimensao=None,
    )
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )
    assert biometria.status == "pendente"
    assert biometria.identificador_cartao == "CARTAO-0001"


async def test_criar_biometria_com_consentimento_cifra_o_template_no_banco(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(
        colaborador_id=colaborador_id, finalidade="biometria_facial"
    )
    vetor_original = b"\x00\x01ESTE-VETOR-NUNCA-PODE-APARECER-EM-CLARO\xff\xfe"
    dados = _dados_criar(
        colaborador_id=colaborador_id, consentimento_id=consentimento_id, vetor=vetor_original
    )

    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )
    assert biometria.status == "pendente"

    # Criterio 5: lido DIRETO da tabela `biometria_templates`, o conteudo nao
    # revela o vetor.
    template = (
        await sessao_f2.execute(
            sa.select(BiometriaTemplate).where(BiometriaTemplate.biometria_id == biometria.id)
        )
    ).scalar_one()
    assert template.template_cifrado != vetor_original
    assert vetor_original not in template.template_cifrado
    assert template.algoritmo_cifra == "AES-256-GCM"
    assert template.chave_id
    assert template.versao_modelo == "arcface-r100-v1"


async def test_validar_biometria_aprova_e_move_para_ativa(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)
    dados = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )

    validada = await servico.validar_biometria(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        decisao="aprovar",
        comentario=None,
        usuario_id=None,
    )
    assert validada.status == "ativa"
    assert validada.validada_em is not None


async def test_validar_biometria_reprovar_sem_comentario_e_val_001(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)
    dados = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.validar_biometria(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            biometria_id=biometria.id,
            decisao="reprovar",
            comentario=None,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_segunda_credencial_ativa_mesma_modalidade_e_recusada(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    """Criterio 6: uma credencial ativa por colaborador e modalidade. A
    SEGUNDA tentativa de ativar (via validarBiometria) e recusada pelo
    indice unico parcial `uq_biometrias_ativa`."""
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)

    dados_1 = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria_1 = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados_1, usuario_id=None
    )
    await servico.validar_biometria(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria_1.id,
        decisao="aprovar",
        comentario=None,
        usuario_id=None,
    )

    dados_2 = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria_2 = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados_2, usuario_id=None
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.validar_biometria(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            biometria_id=biometria_2.id,
            decisao="aprovar",
            comentario=None,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_obter_biometria_registra_acesso_a_dado_sensivel(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)
    dados = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )

    antes = (
        await sessao_f2.execute(
            sa.select(sa.func.count(AcessoDadoSensivel.id)).where(
                AcessoDadoSensivel.entidade_id == biometria.id
            )
        )
    ).scalar_one()

    await servico.obter_biometria(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        usuario_id=None,
    )

    depois = (
        await sessao_f2.execute(
            sa.select(sa.func.count(AcessoDadoSensivel.id)).where(
                AcessoDadoSensivel.entidade_id == biometria.id
            )
        )
    ).scalar_one()
    assert depois == antes + 1

    linha_acesso = (
        (
            await sessao_f2.execute(
                sa.select(AcessoDadoSensivel).where(AcessoDadoSensivel.entidade_id == biometria.id)
            )
        )
        .scalars()
        .first()
    )
    assert linha_acesso is not None
    assert linha_acesso.categoria == "biometria"
    assert linha_acesso.colaborador_id == colaborador_id


async def test_ler_template_decifrado_devolve_o_vetor_original_e_registra_acesso(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)
    vetor_original = b"vetor-facial-de-teste-512-floats-simulado"
    dados = _dados_criar(
        colaborador_id=colaborador_id, consentimento_id=consentimento_id, vetor=vetor_original
    )
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )

    decifrado = await servico.ler_template_decifrado(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        usuario_id=None,
        finalidade="teste_interno",
    )
    assert decifrado == vetor_original

    acessos = (
        await sessao_f2.execute(
            sa.select(sa.func.count(AcessoDadoSensivel.id)).where(
                AcessoDadoSensivel.entidade_id == biometria.id,
                AcessoDadoSensivel.finalidade == "teste_interno",
            )
        )
    ).scalar_one()
    assert acessos == 1


async def test_revogar_biometria_muda_status_e_grava_motivo(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento_biometrico: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento_biometrico(colaborador_id=colaborador_id)
    dados = _dados_criar(colaborador_id=colaborador_id, consentimento_id=consentimento_id)
    biometria = await servico.criar_biometria(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )

    await servico.revogar_biometria(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        usuario_id=None,
        motivo="Colaborador desligado",
    )

    atualizada = await servico.obter_biometria(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        usuario_id=None,
    )
    assert atualizada.status == "revogada"
    assert atualizada.motivo_revogacao == "Colaborador desligado"
    assert atualizada.revogada_em is not None


async def test_obter_biometria_inexistente_e_rec_001(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_biometria(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            biometria_id=uuid4(),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
