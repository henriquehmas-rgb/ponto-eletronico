"""Testes de `app.integracoes.folha.comum.servico` (F13/A5, T15) contra
banco real -- `listar_integracoes`/`criar_integracao` (CRUD puro, sem
Redis/arq) e a parte SINCRONA de `solicitar_exportacao` (com um
`enfileirar` falso injetado, mesmo padrao que `app.fiscal.afd.gerador`
usa para nao depender de Redis real em teste unitario)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.comum import servico
from app.schemas import contrato
from tests.f13.folha.conftest import ContextoFolhaF13, aplicar_tenant_teste

pytestmark = pytest.mark.asyncio


def _dados_criar(
    empresa_id: object, nome: str = "Integracao de teste"
) -> contrato.IntegracaoFolhaCriar:
    return contrato.IntegracaoFolhaCriar.model_validate(
        {
            "empresaId": empresa_id,
            "parceiro": "generico_csv",
            "nome": nome,
            "configuracao": {},
            "mapeamentoRubricas": {"he_50": "015"},
            "formato": "csv",
            "ativo": True,
        }
    )


async def test_criar_integracao_e_listar(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    criada = await servico.criar_integracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        dados=_dados_criar(contexto_folha_f13a5.empresa_id),
    )
    assert criada.id is not None
    assert criada.parceiro == "generico_csv"
    assert criada.nome == "Integracao de teste"

    pagina = await servico.listar_integracoes(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        cursor=None,
        limite_bruto=None,
        ordenar=None,
        empresa_id=contexto_folha_f13a5.empresa_id,
        parceiro=None,
        ativo=None,
    )
    assert any(item.id == criada.id for item in pagina.dados)


async def test_criar_integracao_empresa_inexistente_e_ponto_rec_001(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await servico.criar_integracao(
            sessao_f13a5, tenant_id=contexto_folha_f13a5.tenant_id, dados=_dados_criar(uuid4())
        )
    assert exc_info.value.codigo == "PONTO-REC-001"


async def test_criar_integracao_nome_duplicado_e_ponto_conf_001(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    dados = _dados_criar(contexto_folha_f13a5.empresa_id, nome="Duplicada")
    await servico.criar_integracao(
        sessao_f13a5, tenant_id=contexto_folha_f13a5.tenant_id, dados=dados
    )
    await sessao_f13a5.commit()
    # `SET LOCAL app.tenant_id` so vale ate o fim da transacao corrente --
    # commitar encerra a transacao, reaplica antes de continuar (mesmo
    # cuidado documentado por `tests/f12/conftest.py::aplicar_tenant_teste`).
    await aplicar_tenant_teste(sessao_f13a5, contexto_folha_f13a5.tenant_id)
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await servico.criar_integracao(
            sessao_f13a5, tenant_id=contexto_folha_f13a5.tenant_id, dados=dados
        )
    assert exc_info.value.codigo == "PONTO-CONF-001"


async def test_listar_filtra_por_parceiro_e_ativo(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    await servico.criar_integracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        dados=_dados_criar(contexto_folha_f13a5.empresa_id, nome="Filtro parceiro"),
    )
    pagina = await servico.listar_integracoes(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        cursor=None,
        limite_bruto=None,
        ordenar=None,
        empresa_id=None,
        parceiro="alterdata",
        ativo=None,
    )
    assert all(item.parceiro == "alterdata" for item in pagina.dados)

    pagina_ativos = await servico.listar_integracoes(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        cursor=None,
        limite_bruto=None,
        ordenar=None,
        empresa_id=None,
        parceiro=None,
        ativo=True,
    )
    assert all(item.ativo is True for item in pagina_ativos.dados)


async def test_solicitar_exportacao_enfileira_com_job_id_e_kwargs_corretos(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    integracao = await servico.criar_integracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        dados=_dados_criar(contexto_folha_f13a5.empresa_id, nome="Exportacao teste"),
    )
    await sessao_f13a5.commit()
    await aplicar_tenant_teste(sessao_f13a5, contexto_folha_f13a5.tenant_id)

    chamadas: list[dict[str, object]] = []

    async def _enfileirar_falso(**kwargs: object) -> None:
        chamadas.append(kwargs)

    pedido = contrato.ExportacaoFolhaRequisicao.model_validate(
        {
            "periodoId": str(contexto_folha_f13a5.periodo_id),
            "somenteFechados": True,
        }
    )
    resultado = await servico.solicitar_exportacao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        integracao_id=integracao.id,
        pedido=pedido,
        enfileirar=_enfileirar_falso,
    )
    assert resultado.status == "enfileirado"
    assert resultado.tipo == "exportacao_folha"
    assert len(chamadas) == 1
    kwargs = chamadas[0]
    assert kwargs["processamento_id"] == resultado.id
    assert kwargs["tenant_id"] == str(contexto_folha_f13a5.tenant_id)
    assert kwargs["integracao_id"] == str(integracao.id)
    assert kwargs["parceiro"] == "generico_csv"
    assert kwargs["somente_fechados"] is True


async def test_solicitar_exportacao_integracao_inexistente_e_ponto_rec_001(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    pedido = contrato.ExportacaoFolhaRequisicao.model_validate(
        {"competenciaFolha": contexto_folha_f13a5.competencia_folha}
    )
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await servico.solicitar_exportacao(
            sessao_f13a5,
            tenant_id=contexto_folha_f13a5.tenant_id,
            integracao_id=uuid4(),
            pedido=pedido,
        )
    assert exc_info.value.codigo == "PONTO-REC-001"
