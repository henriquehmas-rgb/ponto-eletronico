"""Execução síncrona/assíncrona de relatórios, catálogo e progresso (T3, F11/A1).

`decidir_execucao_assincrona` + `executar_relatorio_pedido` implementam
`GET /v1/relatorios/{codigo}/executar`: decide o caminho (síncrono chama
`app.relatorios.motor.executar_dataset` direto e materializa o artefato no
próprio request; assíncrono cria `RelatorioExecucao(status='enfileirado')` e
enfileira `executar_relatorio` no worker) e sempre devolve um
`RelatorioExecucao` -- nunca a linha "crua" do resultado (§4 do PCF: as duas
únicas formas de resposta desta operação, tanto síncrona quanto assíncrona,
são `RelatorioExecucao`; o artefato em si é lido depois por
`conteudoRef`/`urlDownload`, mesmo em execução síncrona -- decisão de A1,
documentada abaixo).

## Por que o caminho síncrono também produz um artefato no MinIO

O contrato só declara UM schema de resposta para `executarRelatorio` (200),
`RelatorioExecucao` -- sem um campo de linhas embutidas. Em vez de inventar
uma forma de resposta fora do contrato para `formato=json` síncrono, o
caminho síncrono desta implementação grava o resultado (JSON, CSV, XLSX ou
PDF, conforme `formato`) no armazenamento de objetos como QUALQUER execução
concluída, e devolve `RelatorioExecucao(status='concluido', conteudoRef=...,
urlDownload=...)` de imediato -- sem passar por `'enfileirado'`/
`'processando'`. A tela genérica (T4) trata os dois caminhos de forma
idêntica: se `status='concluido'` já na primeira resposta, pula o polling e
mostra o botão de download direto. Julgamento de A1, documentado no
relatório de fechamento da fase.

Formatos CSV/XLSX/PDF reaproveitam `app.relatorios.exportadores.{csv,xlsx,
pdf}` (A3, T5) -- import tardio dentro da função que precisa, mesmo padrão
que o resto da base usa para dependência entre módulos de fases/agentes
diferentes (ver `app.workflow.fechamento.espelho._saldo_banco_horas`).
`formato=json` (o padrão) é serializado aqui mesmo: não há exportador JSON
em `app.relatorios.exportadores` porque o PCF só define os três formatos de
arquivo (§2.5); JSON nunca sai como arquivo para download num relatório
"pesado" de verdade (esses são sempre `assincrono=true`, formato de arquivo
real), só no caminho síncrono leve, onde serializar aqui é suficiente.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import RelatorioDefinicao, RelatorioExecucao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios import motor
from app.relatorios.catalogo import ColunaCatalogo, colunas_do_catalogo
from app.relatorios.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO: Final[str] = "PONTO-REC-001"
CODIGO_ARTEFATO_EXPIRADO: Final[str] = "PONTO-REC-002"
CODIGO_CONSULTA_INVALIDA: Final[str] = "PONTO-VAL-005"
CODIGO_TRANSICAO_INVALIDA: Final[str] = "PONTO-CONF-003"

#: Limiar de dias do intervalo pedido acima do qual a execução é sempre
#: assíncrona, mesmo que `RelatorioDefinicao.assincrono` seja falso e o
#: cliente não peça `assincrono=true` explicitamente. Decisão de A1,
#: documentada aqui por exigência do PCF (§6/T3: "documente o valor
#: escolhido e a justificativa"): 62 dias (~2 meses de intervalo) é o ponto
#: em que, mesmo restrito a UM colaborador, um dataset detalhado (uma linha
#: por dia, como `espelho-jornada`) já produz linhas suficientes para that
#: valer a pena acompanhar por progresso em vez de segurar a conexão HTTP
#: aberta -- abaixo disso, o relatório mais comum do dia a dia (um
#: colaborador, um ou dois meses) continua respondendo na hora.
LIMIAR_DIAS_ASSINCRONO: Final[int] = 62

#: Retenção do artefato de uma execução concluída -- nem o PCF nem o
#: contrato fixam um número; 7 dias é o mesmo prazo que outras áreas do
#: sistema já usam para link temporário (F10, comprovante de marcação por
#: e-mail), reaproveitado aqui para não inventar uma política nova sem
#: necessidade.
RETENCAO_ARTEFATO = dt.timedelta(days=7)

#: Campos aceitos em `ordenar` de `listarRelatorios` (contrato: "codigo, nome").
_CAMPOS_ORDENACAO_DEFINICAO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(RelatorioDefinicao.codigo, str),
    "nome": CampoOrdenacao(RelatorioDefinicao.nome, str),
}


@dataclass(frozen=True, slots=True)
class ParametrosExecucao:
    """Parâmetros crus de `GET /v1/relatorios/{codigo}/executar`, já
    convertidos dos tipos de query (ainda não validados contra o catálogo --
    isso é `motor.montar_contexto_consulta`)."""

    formato: str | None
    periodo_id: UUID | None
    de: date | None
    ate: date | None
    empresa_id: UUID | None
    unidade_id: UUID | None
    departamento_id: UUID | None
    colaborador_id: UUID | None
    agrupamento: str | None
    colunas: str | None
    filtros: str | None
    converter_decimal: bool | None
    incluir_inativos: bool | None
    assincrono: bool | None


# =============================================================================
# Catálogo (`listarRelatorios`, `obterRelatorio`)
# =============================================================================
async def obter_definicao(sessao: AsyncSession, tenant_id: UUID, codigo: str) -> RelatorioDefinicao:
    linha = (
        await sessao.execute(
            sa.select(RelatorioDefinicao).where(
                RelatorioDefinicao.tenant_id == tenant_id,
                RelatorioDefinicao.codigo == codigo,
                RelatorioDefinicao.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if linha is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe=f"Relatorio '{codigo}' nao encontrado."
        )
    return linha


async def listar_definicoes(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    categoria: str | None = None,
    sistema: bool | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[RelatorioDefinicao], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_DEFINICAO), padrao="codigo"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(RelatorioDefinicao).where(
        RelatorioDefinicao.tenant_id == tenant_id, RelatorioDefinicao.excluido_em.is_(None)
    )
    if categoria is not None:
        consulta = consulta.where(RelatorioDefinicao.categoria == categoria)
    if sistema is not None:
        consulta = consulta.where(RelatorioDefinicao.sistema == sistema)
    if ativo is not None:
        consulta = consulta.where(RelatorioDefinicao.ativo == ativo)

    campo = _CAMPOS_ORDENACAO_DEFINICAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=RelatorioDefinicao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, ordenacao.campo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


# =============================================================================
# Execução (`executarRelatorio`, `obterExecucaoRelatorio`)
# =============================================================================
def decidir_execucao_assincrona(
    definicao: RelatorioDefinicao,
    *,
    assincrono_pedido: bool | None,
    de: date | None,
    ate: date | None,
) -> bool:
    """Regra fixada por A1 (ver `LIMIAR_DIAS_ASSINCRONO`): `assincrono=true`
    explícito na query, OU `RelatorioDefinicao.assincrono=true`, OU
    intervalo de datas pedido acima do limiar."""
    intervalo_acima_do_limiar = (
        de is not None and ate is not None and (ate - de).days > LIMIAR_DIAS_ASSINCRONO
    )
    return bool(assincrono_pedido or definicao.assincrono or intervalo_acima_do_limiar)


def _montar_contexto(
    tenant_id: UUID, definicao: RelatorioDefinicao, parametros: ParametrosExecucao
) -> motor.ContextoConsulta:
    return motor.montar_contexto_consulta(
        tenant_id,
        periodo_id=parametros.periodo_id,
        de=parametros.de,
        ate=parametros.ate,
        empresa_id=parametros.empresa_id,
        unidade_id=parametros.unidade_id,
        departamento_id=parametros.departamento_id,
        colaborador_id=parametros.colaborador_id,
        incluir_inativos=bool(parametros.incluir_inativos),
        filtros_json=parametros.filtros,
    )


def _colunas_pedidas(bruto: str | None) -> list[str] | None:
    if not bruto:
        return None
    return [item.strip() for item in bruto.split(",") if item.strip()]


def _formato_efetivo(definicao: RelatorioDefinicao, pedido: str | None) -> str:
    formato = pedido or "json"
    if formato != "json" and formato not in (definicao.formatos or []):
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA,
            detalhe=f"Formato '{formato}' nao esta entre os formatos deste relatorio.",
        )
    return formato


def _serializar_json(colunas: Sequence[ColunaCatalogo], linhas: Sequence[dict[str, Any]]) -> bytes:
    payload = {
        "colunas": [
            {"chave": c.chave, "rotulo": c.rotulo, "tipo": c.tipo, "duracao": c.duracao}
            for c in colunas
        ],
        "linhas": list(linhas),
    }
    return json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")


def _exportar_bytes(
    formato: str,
    colunas: Sequence[ColunaCatalogo],
    linhas: Sequence[dict[str, Any]],
    *,
    converter_decimal: bool,
    titulo: str,
) -> tuple[bytes, str]:
    """Devolve `(bytes, content_type)`. CSV/XLSX/PDF reaproveitam os
    exportadores de A3 (T5); JSON é serializado aqui (ver docstring do
    módulo)."""
    if formato == "json":
        return _serializar_json(colunas, linhas), "application/json"

    from app.relatorios.exportadores import ColunaExportacao

    colunas_exportacao = [
        ColunaExportacao(chave=c.chave, rotulo=c.rotulo, duracao=c.duracao) for c in colunas
    ]
    buffer = io.BytesIO()
    if formato == "csv":
        from app.relatorios.exportadores.csv import exportar as exportar_csv

        exportar_csv(
            linhas, colunas_exportacao, destino=buffer, converter_decimal=converter_decimal
        )
        content_type = "text/csv"
    elif formato == "xlsx":
        from app.relatorios.exportadores.xlsx import exportar as exportar_xlsx

        exportar_xlsx(
            linhas, colunas_exportacao, destino=buffer, converter_decimal=converter_decimal
        )
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif formato == "pdf":
        from app.relatorios.exportadores.pdf import exportar as exportar_pdf

        exportar_pdf(
            linhas,
            colunas_exportacao,
            destino=buffer,
            converter_decimal=converter_decimal,
            titulo=titulo,
        )
        content_type = "application/pdf"
    else:  # pragma: no cover - `_formato_efetivo` ja valida o dominio
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA, detalhe=f"Formato '{formato}' desconhecido."
        )
    return buffer.getvalue(), content_type


async def _concluir_sincrono(
    sessao: AsyncSession,
    tenant_id: UUID,
    definicao: RelatorioDefinicao,
    *,
    usuario_id: UUID | None,
    formato: str,
    resultado: motor.ResultadoRelatorio,
    parametros_registrados: dict[str, Any],
    converter_decimal: bool,
) -> RelatorioExecucao:
    inicio = dt.datetime.now(tz=dt.UTC)
    conteudo, content_type = _exportar_bytes(
        formato,
        resultado.colunas,
        resultado.linhas,
        converter_decimal=converter_decimal,
        titulo=definicao.nome,
    )
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    execucao_id = uuid4()
    chave = f"relatorios/{tenant_id}/{execucao_id}.{formato}"
    from app.comum.armazenamento import salvar_objeto

    await salvar_objeto(chave, conteudo, content_type=content_type)

    concluido_em = dt.datetime.now(tz=dt.UTC)
    execucao = RelatorioExecucao(
        id=execucao_id,
        tenant_id=tenant_id,
        relatorio_definicao_id=definicao.id,
        usuario_id=usuario_id,
        parametros=parametros_registrados,
        formato=formato,
        status="concluido",
        progresso=100,
        total_linhas=resultado.total_linhas,
        conteudo_ref=chave,
        tamanho_bytes=len(conteudo),
        hash_sha256=hash_sha256,
        iniciado_em=inicio,
        concluido_em=concluido_em,
        duracao_ms=int((concluido_em - inicio).total_seconds() * 1000),
        expira_em=concluido_em + RETENCAO_ARTEFATO,
        criado_por=usuario_id,
    )
    sessao.add(execucao)
    await sessao.flush()
    return execucao


async def _criar_assincrona(
    sessao: AsyncSession,
    tenant_id: UUID,
    definicao: RelatorioDefinicao,
    *,
    usuario_id: UUID | None,
    formato: str,
    parametros_registrados: dict[str, Any],
    redis_url: str,
) -> RelatorioExecucao:
    """Cria `RelatorioExecucao(status='enfileirado')` e enfileira
    `executar_relatorio` no worker (`apps/worker/worker/tarefas/
    relatorios.py`, corpo preenchido em T6 -- fora do escopo de A1 nesta
    leva, ver `app/relatorios/motor.py`) com `default_queue_name=FILA_PADRAO`
    (§2.9 do PCF, mesmo padrão de `app.workflow.fechamento.espelho.
    criar_espelhos_assincrono`, F10, nunca `FILA_RELATORIOS` sozinho)."""
    execucao = RelatorioExecucao(
        id=uuid4(),
        tenant_id=tenant_id,
        relatorio_definicao_id=definicao.id,
        usuario_id=usuario_id,
        parametros=parametros_registrados,
        formato=formato,
        status="enfileirado",
        progresso=0,
        iniciado_em=dt.datetime.now(tz=dt.UTC),
        criado_por=usuario_id,
    )
    sessao.add(execucao)
    await sessao.flush()

    from arq import create_pool
    from arq.connections import RedisSettings

    from app.core.filas import FILA_PADRAO

    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            "executar_relatorio",
            tenant_id=str(tenant_id),
            execucao_id=str(execucao.id),
            codigo=definicao.codigo,
            parametros=parametros_registrados,
            formato=formato,
            solicitante_id=str(usuario_id) if usuario_id else None,
        )
    finally:
        await pool.aclose()

    return execucao


async def executar_relatorio_pedido(
    sessao: AsyncSession,
    tenant_id: UUID,
    codigo: str,
    parametros: ParametrosExecucao,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> RelatorioExecucao:
    """`executarRelatorio`: resolve `codigo`, decide síncrono/assíncrono e
    devolve o `RelatorioExecucao` resultante (ver docstring do módulo)."""
    definicao = await obter_definicao(sessao, tenant_id, codigo)
    formato = _formato_efetivo(definicao, parametros.formato)
    contexto = _montar_contexto(tenant_id, definicao, parametros)
    motor.validar_agrupamento(definicao, parametros.agrupamento)
    colunas_pedidas = _colunas_pedidas(parametros.colunas)
    # Valida colunas cedo (mesmo quando a execucao vai ser assincrona) para
    # nao enfileirar um job que vai falhar por parametro invalido -- mesmo
    # principio de "falha rapido" que o resto do contrato ja aplica.
    if colunas_pedidas and parametros.agrupamento is None:
        catalogo = colunas_do_catalogo(definicao)
        chaves_validas = {c.chave for c in catalogo}
        invalidas = [c for c in colunas_pedidas if c not in chaves_validas]
        if invalidas:
            raise ErroDeAplicacao(
                CODIGO_CONSULTA_INVALIDA,
                detalhe=f"Coluna(s) fora de colunasDisponiveis: {', '.join(invalidas)}.",
            )

    parametros_registrados: dict[str, Any] = {
        "periodoId": str(parametros.periodo_id) if parametros.periodo_id else None,
        "de": parametros.de.isoformat() if parametros.de else None,
        "ate": parametros.ate.isoformat() if parametros.ate else None,
        "empresaId": str(parametros.empresa_id) if parametros.empresa_id else None,
        "unidadeId": str(parametros.unidade_id) if parametros.unidade_id else None,
        "departamentoId": str(parametros.departamento_id) if parametros.departamento_id else None,
        "colaboradorId": str(parametros.colaborador_id) if parametros.colaborador_id else None,
        "agrupamento": parametros.agrupamento,
        "colunas": colunas_pedidas,
        "converterDecimal": bool(parametros.converter_decimal),
        "incluirInativos": bool(parametros.incluir_inativos),
    }

    if decidir_execucao_assincrona(
        definicao, assincrono_pedido=parametros.assincrono, de=parametros.de, ate=parametros.ate
    ):
        return await _criar_assincrona(
            sessao,
            tenant_id,
            definicao,
            usuario_id=usuario_id,
            formato=formato,
            parametros_registrados=parametros_registrados,
            redis_url=redis_url,
        )

    resultado = await motor.executar_dataset(
        sessao,
        tenant_id,
        definicao,
        filtros=contexto,
        colunas=colunas_pedidas,
        agrupamento=parametros.agrupamento,
        limite=motor.LIMITE_MAXIMO,
    )
    if resultado.tem_mais:
        # O relatorio acabou maior que o esperado para o caminho sincrono
        # (mais de `motor.LIMITE_MAXIMO` linhas): redireciona para
        # assincrono em vez de truncar a resposta silenciosamente.
        return await _criar_assincrona(
            sessao,
            tenant_id,
            definicao,
            usuario_id=usuario_id,
            formato=formato,
            parametros_registrados=parametros_registrados,
            redis_url=redis_url,
        )

    return await _concluir_sincrono(
        sessao,
        tenant_id,
        definicao,
        usuario_id=usuario_id,
        formato=formato,
        resultado=resultado,
        parametros_registrados=parametros_registrados,
        converter_decimal=bool(parametros.converter_decimal),
    )


async def obter_execucao(
    sessao: AsyncSession, tenant_id: UUID, execucao_id: UUID
) -> RelatorioExecucao:
    """`obterExecucaoRelatorio`. `PONTO-REC-001` quando a execução não
    existe; `PONTO-REC-002` quando o artefato já expirou (concluída, com
    `expiraEm` no passado)."""
    execucao = await sessao.get(RelatorioExecucao, execucao_id)
    if execucao is None or execucao.tenant_id != tenant_id:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Execucao de relatorio nao encontrada."
        )
    agora = dt.datetime.now(tz=dt.UTC)
    expira_em = execucao.expira_em
    if expira_em is not None and expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=dt.UTC)
    if execucao.status == "concluido" and expira_em is not None and expira_em < agora:
        raise ErroDeAplicacao(
            CODIGO_ARTEFATO_EXPIRADO, detalhe="O artefato desta execucao expirou."
        )
    return execucao


async def montar_execucao_resposta(
    execucao: RelatorioExecucao,
    *,
    sessao: AsyncSession | None = None,
    codigo: str | None = None,
) -> esquemas.RelatorioExecucao:
    """Converte a linha em `RelatorioExecucao` do contrato, resolvendo
    `urlDownload` sob demanda (nunca persistida -- mesmo padrão de
    `app.comum.armazenamento.obter_url_assinada`, F10). `relatorioCodigo` não
    é uma coluna de `relatorio_execucoes` (só `relatorio_definicao_id`): quem
    já tem o `codigo` à mão (`executarRelatorio`, que acabou de resolver a
    definição) passa direto; `obterExecucaoRelatorio` passa `sessao` para
    uma segunda consulta pequena, só quando precisa."""
    resposta = esquemas.RelatorioExecucao.model_validate(execucao, from_attributes=True)
    if codigo is not None:
        resposta.relatorio_codigo = codigo
    elif sessao is not None:
        definicao = await sessao.get(RelatorioDefinicao, execucao.relatorio_definicao_id)
        if definicao is not None:
            resposta.relatorio_codigo = definicao.codigo
    if execucao.conteudo_ref and execucao.status == "concluido":
        from app.comum.armazenamento import obter_url_assinada

        resposta.url_download = await obter_url_assinada(execucao.conteudo_ref)  # type: ignore[assignment]
    return resposta
