"""Teste de ponta a ponta de `app.integracoes.folha.comum.execucao` (F13/
A5, T15) -- a funcao que o worker chama de verdade: consulta apuracao
fechada, gera o arquivo (`generico_csv`) e grava no MinIO real (via
`app.comum.armazenamento`, reaproveitado por leitura -- nunca um segundo
cliente)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import garantir_bucket, obter_objeto
from app.integracoes.folha.comum import servico
from app.integracoes.folha.comum.execucao import executar_exportacao_folha
from app.schemas import contrato
from tests.f13.folha.conftest import ContextoFolhaF13, aplicar_tenant_teste

pytestmark = pytest.mark.asyncio


def _dados_criar(empresa_id: object) -> contrato.IntegracaoFolhaCriar:
    return contrato.IntegracaoFolhaCriar.model_validate(
        {
            "empresaId": empresa_id,
            "parceiro": "generico_csv",
            "nome": "Integracao execucao end-to-end",
            "configuracao": {},
            "mapeamentoRubricas": {"he_50": "015", "adicional_noturno": "020"},
            "formato": "csv",
            "ativo": True,
        }
    )


async def test_executar_exportacao_folha_ponta_a_ponta(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    await garantir_bucket()

    integracao = await servico.criar_integracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        dados=_dados_criar(contexto_folha_f13a5.empresa_id),
    )
    await sessao_f13a5.commit()
    await aplicar_tenant_teste(sessao_f13a5, contexto_folha_f13a5.tenant_id)

    processamento_id_ficticio = (
        integracao.id
    )  # so precisa ser um UUID estavel para o nome do arquivo

    resultado = await executar_exportacao_folha(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        integracao_id=integracao.id,
        processamento_id=processamento_id_ficticio,
        empresa_id=contexto_folha_f13a5.empresa_id,
        parceiro="generico_csv",
        periodo_id=contexto_folha_f13a5.periodo_id,
        competencia_folha=contexto_folha_f13a5.competencia_folha,
        unidade_id=None,
        somente_fechados=True,
    )

    assert resultado["totalLinhas"] == len(contexto_folha_f13a5.linhas)
    chave = resultado["resultadoRef"]
    assert chave.startswith("integracoes-folha/")

    conteudo = await obter_objeto(chave)
    texto = conteudo.decode("utf-8-sig")
    linhas_arquivo = texto.strip().splitlines()
    # cabecalho + uma linha por (dia x componente) semeado pela fixture
    assert len(linhas_arquivo) == 1 + len(contexto_folha_f13a5.linhas)
    # de-para de rubrica aplicado de verdade (nao ficou vazio)
    assert "015" in texto or "020" in texto

    # `ultima_exportacao_em` atualizado na integracao (mesma sessao, apos
    # o commit interno de `executar_exportacao_folha`).
    await aplicar_tenant_teste(sessao_f13a5, contexto_folha_f13a5.tenant_id)
    pagina = await servico.listar_integracoes(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        cursor=None,
        limite_bruto=None,
        ordenar=None,
        empresa_id=None,
        parceiro=None,
        ativo=None,
    )
    atualizada = next(item for item in pagina.dados if item.id == integracao.id)
    assert atualizada.ultima_exportacao_em is not None
