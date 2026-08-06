"""Testes de `app.lgpd.solicitacoes` (F14/A3).

Cobre os dois criterios de aceite mais concretos de A3:

* exportacao de dados do titular funciona ponta a ponta (criar solicitacao
  -> dado correto devolvido, testado contra banco E MinIO reais);
* eliminacao nunca apaga marcacao e sempre produz relatorio do que foi
  feito/nao pode ser feito.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum import armazenamento
from app.lgpd import solicitacoes as servico
from tests.f14.lgpd.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


def _dados(
    *,
    colaborador_id: UUID | None,
    tipo: str,
    requerente_nome: str = "Titular de Teste",
    status_informado: str | None = None,
    resposta_informada: str | None = None,
) -> servico.DadosSolicitacaoCriar:
    return servico.DadosSolicitacaoCriar(
        colaborador_id=colaborador_id,
        usuario_id=None,
        requerente_nome=requerente_nome,
        requerente_cpf=None,
        requerente_email=None,
        tipo=tipo,
        descricao="Solicitacao de teste automatizado",
        status_informado=status_informado,
        resposta_informada=resposta_informada,
        resposta_ref_informada=None,
    )


@pytest.fixture(autouse=True, scope="module")
def _garantir_bucket_minio() -> None:
    import asyncio

    asyncio.run(armazenamento.garantir_bucket())


async def test_criar_solicitacao_gera_protocolo_e_prazo(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="correcao"),
        usuario_id=None,
    )
    assert solicitacao.protocolo.startswith("LGPD-")
    assert solicitacao.prazo_em is not None
    # correcao exige julgamento humano: fica recebida, aguardando triagem.
    assert solicitacao.status == "recebida"


async def test_acesso_sem_colaborador_e_recusado_com_explicacao(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=None, tipo="acesso"),
        usuario_id=None,
    )
    assert solicitacao.status == "recusada"
    assert solicitacao.resposta
    assert "colaboradorId" in solicitacao.resposta


async def test_acesso_ponta_a_ponta_exporta_dado_correto_do_titular(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_vinculo: Callable[..., Awaitable[UUID]],
    criar_marcacao: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
) -> None:
    """Criterio de aceite central de A3: criar solicitacao -> dado CORRETO
    devolvido, verificado lendo de volta o objeto gravado no MinIO real."""
    colaborador_id = await criar_colaborador()
    vinculo_id = await criar_vinculo(colaborador_id=colaborador_id)
    cpf_real = await _cpf_do_colaborador(sessao_f14, colaborador_id)
    await criar_marcacao(colaborador_id=colaborador_id, vinculo_id=vinculo_id, cpf=cpf_real)
    await criar_marcacao(colaborador_id=colaborador_id, vinculo_id=vinculo_id, cpf=cpf_real)
    consentimento_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="comunicacao"
    )
    await criar_biometria_com_template(
        colaborador_id=colaborador_id, consentimento_id=consentimento_id
    )
    await sessao_f14.flush()

    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="acesso"),
        usuario_id=None,
    )
    assert solicitacao.status == "atendida"
    assert solicitacao.resposta_ref

    bruto = await armazenamento.obter_objeto(solicitacao.resposta_ref)
    pacote = json.loads(bruto)

    assert pacote["titular"]["id"] == str(colaborador_id)
    assert pacote["titular"]["cpf"] == cpf_real
    assert pacote["marcacoes"]["totalReal"] == 2
    assert len(pacote["marcacoes"]["itens"]) == 2
    assert not pacote["marcacoes"]["truncado"]
    assert any(c["finalidade"] == "comunicacao" for c in pacote["consentimentos"])
    assert len(pacote["biometrias"]) == 1
    # Vetor biometrico NUNCA sai, mesmo indiretamente (ADR-006 regra 5): a
    # exportacao so tem metadado de ciclo de vida, nenhuma chave carrega
    # bytes de template.
    chaves_biometria = set(pacote["biometrias"][0])
    assert chaves_biometria.isdisjoint({"vetor", "templateCifrado", "template_cifrado"})


async def test_eliminacao_de_titular_sem_marcacao_e_sem_dado_e_atendida(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="eliminacao"),
        usuario_id=None,
    )
    assert solicitacao.status == "atendida"
    assert solicitacao.resposta
    assert "Nenhum dado pessoal elegivel" in solicitacao.resposta


async def test_eliminacao_com_marcacao_nunca_apaga_e_produz_relatorio_parcial(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_vinculo: Callable[..., Awaitable[UUID]],
    criar_marcacao: Callable[..., Awaitable[UUID]],
) -> None:
    """Criterio inegociavel do ADR-002: eliminacao nunca apaga marcacao.
    A solicitacao e sempre criada e processada, nunca um 409 duro (ver
    docstring de `app.lgpd.solicitacoes` para a decisao de interpretacao),
    e o relatorio cita a base legal da retencao."""
    colaborador_id = await criar_colaborador()
    vinculo_id = await criar_vinculo(colaborador_id=colaborador_id)
    await criar_marcacao(colaborador_id=colaborador_id, vinculo_id=vinculo_id, cpf="11122233344")
    await sessao_f14.flush()

    total_marcacoes_antes = await _contar_marcacoes(sessao_f14, colaborador_id)
    assert total_marcacoes_antes == 1

    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="eliminacao"),
        usuario_id=None,
    )
    assert solicitacao.status == "parcialmente_atendida"
    assert "PONTO-LGPD-003" in solicitacao.resposta
    assert "5 anos" in solicitacao.resposta

    total_marcacoes_depois = await _contar_marcacoes(sessao_f14, colaborador_id)
    assert total_marcacoes_depois == total_marcacoes_antes  # NADA foi apagado


async def test_eliminacao_expurga_biometria_e_revoga_consentimentos(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
) -> None:
    import sqlalchemy as sa
    from ponto_contracts import BiometriaTemplate

    colaborador_id = await criar_colaborador()
    consentimento_id = await criar_consentimento(
        colaborador_id=colaborador_id, finalidade="biometria_facial"
    )
    biometria_id = await criar_biometria_com_template(
        colaborador_id=colaborador_id, consentimento_id=consentimento_id
    )
    await sessao_f14.flush()

    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="eliminacao"),
        usuario_id=None,
    )
    assert solicitacao.status == "atendida"  # sem marcacao, tudo elegivel foi eliminado
    assert "template" in solicitacao.resposta.lower()

    total_templates = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_templates == 0


async def test_revogacao_consentimento_via_solicitacao_revoga_tudo(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_consentimento: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    await criar_consentimento(colaborador_id=colaborador_id, finalidade="comunicacao")
    await criar_consentimento(colaborador_id=colaborador_id, finalidade="uso_imagem")
    await sessao_f14.flush()

    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(colaborador_id=colaborador_id, tipo="revogacao_consentimento"),
        usuario_id=None,
    )
    assert solicitacao.status == "atendida"
    assert "2 consentimento" in solicitacao.resposta

    linhas, _, _ = await _listar_consentimentos_do_colaborador(
        sessao_f14, contexto_organizacional.tenant_id, colaborador_id
    )
    assert all(c.status == "revogado" for c in linhas)


async def test_backfill_manual_respeita_status_informado_e_nao_reprocessa(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    """RH registrando um pedido em papel ja atendido manualmente: o
    processamento automatico NAO deve rodar por cima."""
    colaborador_id = await criar_colaborador()
    solicitacao = await servico.criar_solicitacao_titular(
        sessao_f14,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados(
            colaborador_id=colaborador_id,
            tipo="eliminacao",
            status_informado="atendida",
            resposta_informada="Atendido manualmente por carta, protocolo dos Correios 123.",
        ),
        usuario_id=None,
    )
    assert solicitacao.status == "atendida"
    assert "Correios" in solicitacao.resposta
    assert solicitacao.respondido_em is not None


async def _cpf_do_colaborador(sessao: AsyncSession, colaborador_id: UUID) -> str:
    import sqlalchemy as sa
    from ponto_contracts import Colaborador

    resultado = await sessao.execute(
        sa.select(Colaborador.cpf).where(Colaborador.id == colaborador_id)
    )
    return resultado.scalar_one()


async def _contar_marcacoes(sessao: AsyncSession, colaborador_id: UUID) -> int:
    import sqlalchemy as sa
    from ponto_contracts import Marcacao

    resultado = await sessao.execute(
        sa.select(sa.func.count(Marcacao.id)).where(Marcacao.colaborador_id == colaborador_id)
    )
    return resultado.scalar_one()


async def _listar_consentimentos_do_colaborador(
    sessao: AsyncSession, tenant_id: UUID, colaborador_id: UUID
) -> tuple[list, bool, str | None]:
    from app.lgpd.consentimentos import listar_consentimentos

    return await listar_consentimentos(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        finalidade=None,
        status=None,
        cursor=None,
        limite=None,
        ordenar=None,
    )
