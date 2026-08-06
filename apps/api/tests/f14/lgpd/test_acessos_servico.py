"""Testes de `app.lgpd.acessos` (F14/A3, `listarAcessosSensiveis`).

Confirma o achado do PCF ("confirme primeiro se ja grava"): a tabela
`acessos_dados_sensiveis` ja e' escrita por `app.biometria.servico` desde a
F2 -- este modulo so precisa EXPOR a leitura corretamente (filtros,
paginacao), o que estes testes verificam ponta a ponta contra banco real.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from ponto_contracts import AcessoDadoSensivel
from sqlalchemy.ext.asyncio import AsyncSession

from app.lgpd import acessos as servico
from tests.f14.lgpd.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


async def test_listar_acessos_sensiveis_filtra_por_categoria_e_colaborador(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_a = await criar_colaborador()
    colaborador_b = await criar_colaborador()

    sessao_f14.add_all(
        [
            AcessoDadoSensivel(
                tenant_id=contexto_organizacional.tenant_id,
                colaborador_id=colaborador_a,
                categoria="biometria",
                entidade="biometrias",
                finalidade="teste",
                base_legal="consentimento",
                acao="leitura",
                origem="api",
            ),
            AcessoDadoSensivel(
                tenant_id=contexto_organizacional.tenant_id,
                colaborador_id=colaborador_b,
                categoria="documento",
                entidade="documentos",
                finalidade="teste",
                base_legal="execucao_contrato",
                acao="leitura",
                origem="api",
            ),
        ]
    )
    await sessao_f14.flush()

    linhas, tem_mais, _ = await servico.listar_acessos_sensiveis(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        colaborador_id=colaborador_a,
        categoria="biometria",
        acao=None,
        de=None,
        ate=None,
        cursor=None,
        limite=None,
        ordenar=None,
    )
    assert not tem_mais
    assert len(linhas) == 1
    assert linhas[0].colaborador_id == colaborador_a
    assert linhas[0].categoria == "biometria"


async def test_biometria_servico_ja_grava_acesso_sensivel_de_verdade(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
) -> None:
    """Prova o achado do PCF: `app.biometria.servico.obter_biometria` (F2,
    ja existente, nao tocado por A3) grava `acessos_dados_sensiveis` sem
    nenhuma instrumentacao nova desta fase -- so a LEITURA via
    `listarAcessosSensiveis` e' trabalho de A3."""
    from app.biometria import servico as biometria_servico

    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="biometria_facial"
    )
    dados = biometria_servico.DadosBiometriaCriar(
        colaborador_id=colaborador_id,
        modalidade="facial",
        origem_cadastro="app",
        consentimento_id=consentimento_id,
        qualidade=90.0,
        identificador_cartao=None,
        vetor=b"vetor-de-teste",
        versao_modelo="v1",
        provedor="facial-svc",
        dimensao=128,
    )
    import os
    import secrets

    os.environ.setdefault("PONTO_BIOMETRIA_CHAVE_MESTRA", secrets.token_hex(32))
    biometria = await biometria_servico.criar_biometria(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, dados=dados, usuario_id=None
    )
    await biometria_servico.obter_biometria(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        biometria_id=biometria.id,
        usuario_id=None,
    )
    await sessao_f14.flush()

    linhas, _, _ = await servico.listar_acessos_sensiveis(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        colaborador_id=colaborador_id,
        categoria="biometria",
        acao="leitura",
        de=None,
        ate=None,
        cursor=None,
        limite=None,
        ordenar=None,
    )
    assert len(linhas) == 1
    assert linhas[0].entidade == "biometrias"
    assert linhas[0].entidade_id == biometria.id
