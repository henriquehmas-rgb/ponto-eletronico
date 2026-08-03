"""Servico de `integracoes` (subarvore folha, F13/A5, T15): CRUD de
`IntegracaoFolha` (`listarIntegracoesFolha`/`criarIntegracaoFolha`) e
orquestracao de `exportarFolha`/`obterExportacaoFolha` (RFC-017). Chamado
pelo router (`app/routers/integracoes.py`), que so cuida de HTTP
(cabecalhos, status code, idempotencia) -- toda regra de negocio vive aqui.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import Empresa, IntegracaoFolha
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import obter_url_assinada
from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.integracoes.folha.comum import dados as dados_mod
from app.integracoes.folha.comum import paginacao as pag
from app.integracoes.folha.comum import processamento as proc_mod
from app.schemas import contrato

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_REGISTRO_DUPLICADO = "PONTO-CONF-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: Nome exato da tarefa do worker (PCF §5.3, arquivo compartilhado
#: `apps/worker/worker/tarefas/integracoes.py`, bloco de A5).
NOME_TAREFA_EXPORTAR_FOLHA = "exportar_folha"

#: Python attribute (snake_case) de cada campo aceito em `ordenar`
#: (camelCase, contrato) -- usado so para extrair o valor do cursor.
_ATRIBUTO_PYTHON: dict[str, str] = {"nome": "nome", "ultimaExportacaoEm": "ultima_exportacao_em"}

_CAMPOS_ORDENACAO: dict[str, pag.CampoOrdenacao] = {
    "nome": pag.CampoOrdenacao(coluna=IntegracaoFolha.nome, conversor=str),
    "ultimaExportacaoEm": pag.CampoOrdenacao(
        coluna=IntegracaoFolha.ultima_exportacao_em,
        conversor=lambda v: dt.datetime.fromisoformat(v) if isinstance(v, str) else v,
    ),
}


def _para_schema(linha: IntegracaoFolha) -> contrato.IntegracaoFolha:
    # `model_validate` (nao o construtor direto) de proposito: coerce
    # string -> enum (`Parceiro`/`Formato1`) sozinho, mesmo padrao ja usado
    # por `app.fiscal.afd.gerador`/`app.fiscal.aej.gerador` (F12) para
    # `ProcessamentoAssincrono` e por `app.routers.admin._para_schema` (A1,
    # T2) para os schemas de `admin` -- evita repetir os 16 campos por
    # extenso e mypy sem o plugin do pydantic nao entende `Field(None,
    # alias=...)` como argumento opcional do construtor.
    return contrato.IntegracaoFolha.model_validate(
        {
            "id": linha.id,
            "tenantId": linha.tenant_id,
            "empresaId": linha.empresa_id,
            "parceiro": linha.parceiro,
            "nome": linha.nome,
            "configuracao": linha.configuracao,
            "mapeamentoRubricas": linha.mapeamento_rubricas,
            "formato": linha.formato,
            "ativo": linha.ativo,
            "ultimaExportacaoEm": linha.ultima_exportacao_em,
            "criadoEm": linha.criado_em,
            "criadoPor": linha.criado_por,
            "atualizadoEm": linha.atualizado_em,
            "atualizadoPor": linha.atualizado_por,
            "excluidoEm": linha.excluido_em,
            "excluidoPor": linha.excluido_por,
        }
    )


async def listar_integracoes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite_bruto: int | None,
    ordenar: str | None,
    empresa_id: UUID | None,
    parceiro: str | None,
    ativo: bool | None,
) -> contrato.ListaIntegracaoFolha:
    limite = pag.normalizar_limite(limite_bruto)
    ordenacao = pag.interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="nome"
    )
    consulta = sa.select(IntegracaoFolha).where(
        IntegracaoFolha.tenant_id == tenant_id, IntegracaoFolha.excluido_em.is_(None)
    )
    if empresa_id is not None:
        consulta = consulta.where(IntegracaoFolha.empresa_id == empresa_id)
    if parceiro is not None:
        consulta = consulta.where(IntegracaoFolha.parceiro == parceiro)
    if ativo is not None:
        consulta = consulta.where(IntegracaoFolha.ativo == ativo)

    linhas, tem_mais = await pag.executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=_CAMPOS_ORDENACAO[ordenacao.campo],
        coluna_id=IntegracaoFolha.id,
        cursor=cursor,
        limite=limite,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        atributo = _ATRIBUTO_PYTHON[ordenacao.campo]
        proximo_cursor = pag.codificar_cursor(ordenacao, getattr(ultima, atributo), ultima.id)
    return contrato.ListaIntegracaoFolha(
        dados=[_para_schema(linha) for linha in linhas],
        paginacao=pag.montar_paginacao(
            proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite
        ),
    )


async def criar_integracao(
    sessao: AsyncSession, *, tenant_id: UUID, dados: contrato.IntegracaoFolhaCriar
) -> contrato.IntegracaoFolha:
    empresa = (
        await sessao.execute(
            sa.select(Empresa).where(
                Empresa.id == dados.empresa_id,
                Empresa.tenant_id == tenant_id,
                Empresa.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if empresa is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="empresaId nao encontrado.")

    agora = dt.datetime.now(dt.UTC)
    linha = IntegracaoFolha(
        id=uuid4(),
        tenant_id=tenant_id,
        empresa_id=dados.empresa_id,
        parceiro=str(dados.parceiro),
        nome=dados.nome,
        configuracao=dados.configuracao or {},
        mapeamento_rubricas=dados.mapeamento_rubricas,
        formato=str(dados.formato) if dados.formato else "csv",
        ativo=dados.ativo if dados.ativo is not None else True,
        ultima_exportacao_em=dados.ultima_exportacao_em,
        criado_em=agora,
    )
    sessao.add(linha)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise ErroDeAplicacao(
            CODIGO_REGISTRO_DUPLICADO,
            detalhe="Ja existe uma integracao de folha com este nome para esta empresa.",
        ) from exc
    return _para_schema(linha)


async def _obter_integracao(
    sessao: AsyncSession, *, tenant_id: UUID, integracao_id: UUID
) -> IntegracaoFolha:
    linha = (
        await sessao.execute(
            sa.select(IntegracaoFolha).where(
                IntegracaoFolha.id == integracao_id,
                IntegracaoFolha.tenant_id == tenant_id,
                IntegracaoFolha.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if linha is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="integracaoId nao encontrado.")
    return linha


async def _enfileirar_exportacao(*, redis_url: str, processamento_id: UUID, **kwargs: Any) -> None:
    """Isolado numa funcao propria para o teste poder substituir por um
    `pool` falso sem depender de Redis real (mesmo padrao que `app.fiscal.
    afd.gerador._enfileirar_gerar_afd` ja usa)."""
    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(NOME_TAREFA_EXPORTAR_FOLHA, _job_id=str(processamento_id), **kwargs)
    finally:
        await pool.aclose()


async def solicitar_exportacao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    integracao_id: UUID,
    pedido: contrato.ExportacaoFolhaRequisicao,
    enfileirar: Callable[..., Any] | None = None,
) -> contrato.ProcessamentoAssincrono:
    """Parte SINCRONA de `exportarFolha`: valida a integracao/periodo e
    enfileira a tarefa do worker (`exportar_folha`) com `_job_id` igual ao
    `processamentoId` devolvido -- ver `app.integracoes.folha.comum.
    processamento` para o porque desta escolha (nenhuma tabela nova
    autorizada). O trabalho pesado (consultar apuracao, gerar o arquivo,
    subir no MinIO) acontece inteiramente no worker."""
    integracao = await _obter_integracao(sessao, tenant_id=tenant_id, integracao_id=integracao_id)
    if not integracao.ativo:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="Integracao de folha esta inativa.")

    inicio, _fim = await dados_mod.resolver_intervalo(
        sessao,
        tenant_id=tenant_id,
        empresa_id=integracao.empresa_id,
        periodo_id=pedido.periodo_id,
        competencia_folha=pedido.competencia_folha,
    )
    competencia_folha = pedido.competencia_folha or f"{inicio.year:04d}-{inicio.month:02d}"

    processamento_id = uuid4()
    config = obter_configuracao()
    chamada_enfileirar = enfileirar or _enfileirar_exportacao
    await chamada_enfileirar(
        redis_url=config.redis_url,
        processamento_id=processamento_id,
        tenant_id=str(tenant_id),
        integracao_id=str(integracao_id),
        empresa_id=str(integracao.empresa_id),
        parceiro=integracao.parceiro,
        periodo_id=str(pedido.periodo_id) if pedido.periodo_id else None,
        competencia_folha=competencia_folha,
        unidade_id=str(pedido.unidade_id) if pedido.unidade_id else None,
        somente_fechados=(pedido.somente_fechados if pedido.somente_fechados is not None else True),
    )

    return contrato.ProcessamentoAssincrono.model_validate(
        {
            "id": processamento_id,
            "tipo": "exportacao_folha",
            "status": "enfileirado",
            "progresso": 0,
        }
    )


async def obter_exportacao(
    *, tenant_id: UUID, integracao_id: UUID, processamento_id: UUID
) -> contrato.ProcessamentoAssincrono:
    """Parte de `obterExportacaoFolha` (RFC-017): le o estado no Redis (via
    `comum.processamento`) e, quando concluido, resolve `resultadoRef` para
    uma URL assinada temporaria (`app.comum.armazenamento.
    obter_url_assinada` -- a chave crua nunca e devolvida na resposta,
    mesmo padrao de `RelatorioExecucao.urlDownload`/`espelhos`)."""
    config = obter_configuracao()
    redis = Redis.from_url(config.redis_url)
    try:
        estado = await proc_mod.obter_estado(
            redis,
            processamento_id=processamento_id,
            tenant_id=tenant_id,
            integracao_id=integracao_id,
        )
    finally:
        await redis.aclose()

    if estado is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="processamentoId nao encontrado."
        )

    resultado_ref: str | None = None
    if estado.status == "concluido" and estado.resultado_ref:
        resultado_ref = await obter_url_assinada(estado.resultado_ref)

    return contrato.ProcessamentoAssincrono.model_validate(
        {
            "id": estado.id,
            "tipo": proc_mod.TIPO,
            "status": estado.status,
            "progresso": estado.progresso,
            "totalItens": estado.total_itens,
            "itensProcessados": estado.itens_processados,
            "resultadoRef": resultado_ref,
            "iniciadoEm": estado.iniciado_em,
            "concluidoEm": estado.concluido_em,
            "erro": estado.erro,
            "codigoErro": estado.codigo_erro,
        }
    )
