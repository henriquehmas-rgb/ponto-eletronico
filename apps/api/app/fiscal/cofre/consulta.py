"""Listagem, obtenção e download do cofre de arquivos fiscais (F12/A3, T12).

`listar_afd`/`obter_afd`/`baixar_afd` e `listar_aej`/`obter_aej` -- leitura
pura de `afd_arquivos`/`aej_arquivos`, nunca escrita (quem grava é
`app.fiscal.afd`/`app.fiscal.aej`, A1/A2). Confirmado lendo o `openapi.yaml`
por inteiro (não presumido): **não existe** `GET /v1/fiscal/aej/{arquivoId}/
download` -- só o AFD tem download bruto no contrato (`baixarAfd`), por
isso `baixar_aej` não é implementado aqui.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import AejArquivo, AfdArquivo, ArquivoAssinatura
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import obter_objeto
from app.core.erros import ErroDeAplicacao
from app.fiscal.cofre.paginacao import (
    CampoOrdenacao,
    Ordenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.identidade.auditoria.hash_chain import gravar_auditoria
from app.schemas.contrato import Paginacao as PaginacaoResposta

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_FALHA_GERACAO = "PONTO-FISC-006"

#: "Campos aceitos em ordenar: periodoInicio, geradoEm" (descrição de
#: `listarAfd`/`listarAej` no contrato, literal).
_CAMPOS_ORDENACAO_AFD: dict[str, CampoOrdenacao] = {
    "periodoInicio": CampoOrdenacao(coluna=AfdArquivo.periodo_inicio, conversor=date.fromisoformat),
    "geradoEm": CampoOrdenacao(coluna=AfdArquivo.gerado_em, conversor=datetime.fromisoformat),
}
_CAMPOS_ORDENACAO_AEJ: dict[str, CampoOrdenacao] = {
    "periodoInicio": CampoOrdenacao(coluna=AejArquivo.periodo_inicio, conversor=date.fromisoformat),
    "geradoEm": CampoOrdenacao(coluna=AejArquivo.gerado_em, conversor=datetime.fromisoformat),
}


async def listar_afd(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    rep_p_id: UUID | None = None,
    de: date | None = None,
    ate: date | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[AfdArquivo], PaginacaoResposta]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_AFD), padrao="geradoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(AfdArquivo).where(AfdArquivo.tenant_id == tenant_id)
    if empresa_id is not None:
        consulta = consulta.where(AfdArquivo.empresa_id == empresa_id)
    if rep_p_id is not None:
        consulta = consulta.where(AfdArquivo.rep_p_id == rep_p_id)
    if de is not None:
        consulta = consulta.where(AfdArquivo.periodo_fim >= de)
    if ate is not None:
        consulta = consulta.where(AfdArquivo.periodo_inicio <= ate)
    if status is not None:
        consulta = consulta.where(AfdArquivo.status == status)

    campo = _CAMPOS_ORDENACAO_AFD[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=AfdArquivo.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = _proximo_cursor(ordenacao, linhas, tem_mais)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def listar_aej(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    periodo_id: UUID | None = None,
    de: date | None = None,
    ate: date | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[AejArquivo], PaginacaoResposta]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_AEJ), padrao="geradoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(AejArquivo).where(AejArquivo.tenant_id == tenant_id)
    if empresa_id is not None:
        consulta = consulta.where(AejArquivo.empresa_id == empresa_id)
    if periodo_id is not None:
        consulta = consulta.where(AejArquivo.periodo_id == periodo_id)
    if de is not None:
        consulta = consulta.where(AejArquivo.periodo_fim >= de)
    if ate is not None:
        consulta = consulta.where(AejArquivo.periodo_inicio <= ate)
    if status is not None:
        consulta = consulta.where(AejArquivo.status == status)

    campo = _CAMPOS_ORDENACAO_AEJ[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=AejArquivo.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = _proximo_cursor(ordenacao, linhas, tem_mais)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


def _proximo_cursor(
    ordenacao: Ordenacao, linhas: Sequence[AfdArquivo | AejArquivo], tem_mais: bool
) -> str | None:
    if not tem_mais or not linhas:
        return None
    ultimo = linhas[-1]
    atributo = "gerado_em" if ordenacao.campo == "geradoEm" else "periodo_inicio"
    valor_cursor = getattr(ultimo, atributo)
    if valor_cursor is None:
        return None
    return codificar_cursor(ordenacao, valor_cursor, ultimo.id)


async def obter_afd(sessao: AsyncSession, tenant_id: UUID, arquivo_id: UUID) -> AfdArquivo:
    arquivo = await sessao.get(AfdArquivo, arquivo_id)
    if arquivo is None or arquivo.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="AFD nao encontrado.")
    return arquivo


async def obter_aej(sessao: AsyncSession, tenant_id: UUID, arquivo_id: UUID) -> AejArquivo:
    arquivo = await sessao.get(AejArquivo, arquivo_id)
    if arquivo is None or arquivo.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="AEJ nao encontrado.")
    return arquivo


async def _assinatura_mais_recente(
    sessao: AsyncSession, tenant_id: UUID, *, tipo_arquivo: str, arquivo_id: UUID
) -> ArquivoAssinatura | None:
    consulta = (
        sa.select(ArquivoAssinatura)
        .where(
            ArquivoAssinatura.tenant_id == tenant_id,
            ArquivoAssinatura.tipo_arquivo == tipo_arquivo,
            ArquivoAssinatura.arquivo_id == arquivo_id,
        )
        .order_by(ArquivoAssinatura.criado_em.desc())
        .limit(1)
    )
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def baixar_afd(
    sessao: AsyncSession,
    tenant_id: UUID,
    arquivo_id: UUID,
    *,
    incluir_assinatura: bool,
    usuario_id: UUID | None,
    ip: str | None,
    user_agent: str | None,
) -> tuple[bytes, str, str]:
    """Devolve `(conteudo, content_type, nome_arquivo)`.

    O conteudo do AFD e devolvido **exatamente como gravado**, em
    ISO-8859-1, sem qualquer reencodagem -- `obter_objeto` le bytes crus do
    MinIO, e nada neste caminho decodifica/recodifica a string (a descrição
    do contrato avisa explicitamente que converter para UTF-8 no caminho
    quebra o leiaute).

    Com `incluir_assinatura=True`, empacota o AFD e o `.p7s` destacado mais
    recente num `.zip` (formato de pacote escolhido por este módulo -- o
    contrato não define um formato de pacote, só pede "arquivo + .p7s
    destacado"; `zipfile` da biblioteca padrão, sem dependência nova). Se o
    arquivo ainda não tiver assinatura (`status='gerado'`, não
    `'assinado'`), a assinatura solicitada simplesmente não existe ainda:
    este módulo devolve o AFD isolado em vez de erro -- decisão de design
    documentada aqui, não um requisito do contrato (ver relatório da fase).
    """
    arquivo = await obter_afd(sessao, tenant_id, arquivo_id)
    if not arquivo.conteudo_ref:
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO, detalhe="AFD sem conteudo gravado no armazenamento ainda."
        )
    conteudo = await obter_objeto(arquivo.conteudo_ref)

    resultado_bytes = conteudo
    content_type = "text/plain; charset=iso-8859-1"
    nome_arquivo = arquivo.nome_arquivo

    if incluir_assinatura:
        assinatura = await _assinatura_mais_recente(
            sessao, tenant_id, tipo_arquivo="afd", arquivo_id=arquivo_id
        )
        if assinatura is not None:
            assinatura_bytes = await obter_objeto(assinatura.assinatura_ref)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as pacote:
                pacote.writestr(nome_arquivo, conteudo)
                pacote.writestr(f"{nome_arquivo}.p7s", assinatura_bytes)
            resultado_bytes = buffer.getvalue()
            content_type = "application/zip"
            nome_arquivo = f"{nome_arquivo}.zip"

    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="afd.baixado",
        entidade="afd_arquivos",
        acao="exportar",
        entidade_id=arquivo_id,
        usuario_id=usuario_id,
        ip=ip,
        user_agent=user_agent,
        valor_novo={"incluirAssinatura": incluir_assinatura, "bytes": len(resultado_bytes)},
    )

    return resultado_bytes, content_type, nome_arquivo
