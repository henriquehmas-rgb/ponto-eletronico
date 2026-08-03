"""Execucao de fato de `exportar_folha` (F13/A5, T15) -- chamada pelo
worker (`apps/worker/worker/tarefas/integracoes.py::exportar_folha`) via
import tardio, mesmo padrao que `app.fiscal.afd.gerador.gerar_afd_arquivo`
ja estabelece (`apps/worker` instala `apps/api` como biblioteca na imagem
`runtime`, ADR-009 -- nunca o inverso).

Nenhuma linha desta fase escreve em `apuracoes_dia`/`bh_lancamentos`/etc.
(PCF F13 §9, proibicao 8): a UNICA escrita feita aqui e
`integracoes_folha.ultima_exportacao_em`, e o objeto no armazenamento.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Empresa, IntegracaoFolha
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import salvar_objeto
from app.core.erros import ErroDeAplicacao
from app.integracoes.folha import carregar_exportadores
from app.integracoes.folha.comum import dados as dados_mod
from app.integracoes.folha.comum import registro
from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha
from app.integracoes.folha.comum.rubricas import resolver_rubrica

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"


def _com_rubrica(
    linha: LinhaApuracaoFolha, mapeamento_rubricas: dict[str, Any]
) -> LinhaApuracaoFolha:
    return dataclasses.replace(
        linha, rubrica=resolver_rubrica(linha.componente_codigo, mapeamento_rubricas)
    )


async def executar_exportacao_folha(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    integracao_id: UUID,
    processamento_id: UUID,
    empresa_id: UUID,
    parceiro: str,
    periodo_id: UUID | None,
    competencia_folha: str,
    unidade_id: UUID | None,
    somente_fechados: bool,
) -> dict[str, Any]:
    """Consulta a apuracao fechada, gera o arquivo do parceiro e grava no
    armazenamento de objetos. Devolve `{"totalLinhas": int, "resultadoRef":
    str}` -- o dicionario que `arq` guarda como resultado do job e que
    `comum.processamento.obter_estado` le de volta (`processamentoId` =
    `_job_id` do arq, ver docstring daquele modulo)."""
    carregar_exportadores()
    gerador = registro.obter_gerador(parceiro)

    integracao = (
        await sessao.execute(
            sa.select(IntegracaoFolha).where(
                IntegracaoFolha.id == integracao_id, IntegracaoFolha.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if integracao is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="integracaoId nao encontrado durante a execucao."
        )

    empresa = (
        await sessao.execute(
            sa.select(Empresa).where(Empresa.id == empresa_id, Empresa.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if empresa is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="empresaId nao encontrado durante a execucao."
        )

    inicio, fim = await dados_mod.resolver_intervalo(
        sessao,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        periodo_id=periodo_id,
        competencia_folha=competencia_folha,
    )
    linhas_brutas = await dados_mod.coletar_linhas_apuracao(
        sessao,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        inicio=inicio,
        fim=fim,
        unidade_id=unidade_id,
        somente_fechados=somente_fechados,
    )
    mapeamento = dict(integracao.mapeamento_rubricas or {})
    linhas = tuple(_com_rubrica(linha, mapeamento) for linha in linhas_brutas)

    contexto = ContextoExportacaoFolha(
        tenant_id=tenant_id,
        integracao_id=integracao_id,
        processamento_id=processamento_id,
        empresa_id=empresa_id,
        empresa_cnpj=empresa.cnpj,
        parceiro=parceiro,
        competencia_folha=competencia_folha,
        periodo_id=periodo_id,
        unidade_id=unidade_id,
        somente_fechados=somente_fechados,
        periodo_inicio=inicio,
        periodo_fim=fim,
        configuracao=dict(integracao.configuracao or {}),
        mapeamento_rubricas=mapeamento,
        linhas=linhas,
        gerado_em=dt.datetime.now(dt.UTC),
    )
    arquivo = gerador(contexto)
    chave = await salvar_objeto(
        arquivo.nome_arquivo, arquivo.conteudo, content_type=arquivo.content_type
    )

    integracao.ultima_exportacao_em = dt.datetime.now(dt.UTC)
    await sessao.commit()

    return {"totalLinhas": len(linhas), "resultadoRef": chave}
