"""Geração do espelho de ponto: JSON congelado, hash e PDF (T7, F10/A2).

`gerar_espelho_do_vinculo` monta `conteudo` (JSON com dias, apuração,
tratamentos identificados como lançamento manual, totais) lendo
`apuracoes_dia`/`apuracao_componentes`/`tratamentos` do vínculo no intervalo
do período -- **só leitura**, nunca escreve nessas três tabelas (proibição 5
do PCF). O hash usa a MESMA canonicalização de `app.identidade.auditoria.
hash_chain._json_canonico` (§2.4 do PCF): reaproveitada por import direto,
não reimplementada, para impedir que as duas formas de canonicalizar JSON no
sistema divirjam silenciosamente.

**Retificação vira `tipo='retificado'` automaticamente** (PCF §2.4 item 5):
gerar um espelho `oficial` para um vínculo/período que já tem um `oficial`
ou `retificado` anterior produz uma versão nova com `tipo='retificado'`,
nunca sobrescreve nem reemite como `oficial` de novo -- `uq_espelhos_versao`
garante que a versão nova nunca colide com a antiga.

**`saldoBancoMinutos` reaproveita `app.apuracao.banco_horas.consulta.
obter_saldo_banco_horas`** (F4, módulo de leitura já testado e exposto por
rota própria, `tag banco-horas`): é o saldo HISTÓRICO da conta padrão do
vínculo na data de fim do período, não a soma dos `apuracoes_dia.
saldo_minutos` do intervalo (que seria só a *variação* dentro do período,
não o saldo acumulado da conta) -- vínculo sem conta de banco de horas
aberta devolve `0`, nunca erro (nem todo tenant usa banco de horas).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import (
    ApuracaoComponente,
    ApuracaoDia,
    Colaborador,
    Empresa,
    Espelho,
    Periodo,
    TipoTratamento,
    Tratamento,
    Vinculo,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.auditoria.hash_chain import _json_canonico
from app.schemas import contrato as esquemas
from app.workflow.fechamento.erros_bd import traduzir_integridade
from app.workflow.fechamento.escopo import dias_do_intervalo, resolver_vinculos_do_escopo
from app.workflow.fechamento.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"

#: `tratamentos.status` que já produziram (ou vão produzir) efeito na
#: apuração -- os únicos exibidos no espelho como "lançamento manual".
_STATUS_TRATAMENTO_VISIVEL = ("aprovado", "aplicado")

_CAMPOS_ORDENACAO_ESPELHO: dict[str, CampoOrdenacao] = {
    "geradoEm": CampoOrdenacao(Espelho.gerado_em, dt.datetime.fromisoformat),
    "versao": CampoOrdenacao(Espelho.versao, int),
}


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


def _hash_conteudo(conteudo: dict[str, Any]) -> str:
    """SHA-256 do `conteudo`, mesma canonicalização de `hash_chain.
    _json_canonico` (reaproveitada por import direto -- ver docstring do
    módulo)."""
    return hashlib.sha256(_json_canonico(conteudo).encode("utf-8")).hexdigest()


async def _carregar_vinculo(sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID) -> Vinculo:
    vinculo = await sessao.get(Vinculo, vinculo_id)
    if vinculo is None or vinculo.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


async def _saldo_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, vinculo: Vinculo, ate: dt.date
) -> int:
    from app.apuracao.banco_horas.consulta import obter_saldo_banco_horas

    try:
        saldo = await obter_saldo_banco_horas(
            sessao,
            tenant_id,
            vinculo.colaborador_id,
            vinculo_id=vinculo.id,
            data_referencia=ate,
        )
    except ErroDeAplicacao as exc:
        if exc.codigo == CODIGO_RECURSO_NAO_ENCONTRADO:
            return 0
        raise
    return saldo.saldo_minutos or 0


async def _montar_conteudo(
    sessao: AsyncSession, tenant_id: UUID, periodo: Periodo, vinculo: Vinculo
) -> dict[str, Any]:
    colaborador = await sessao.get(Colaborador, vinculo.colaborador_id)
    empresa = await sessao.get(Empresa, vinculo.empresa_id)
    if colaborador is None or empresa is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO,
            detalhe="Colaborador ou empresa do vinculo nao encontrado.",
        )

    apuracoes = list(
        (
            await sessao.execute(
                sa.select(ApuracaoDia)
                .where(
                    ApuracaoDia.tenant_id == tenant_id,
                    ApuracaoDia.vinculo_id == vinculo.id,
                    ApuracaoDia.data >= periodo.data_inicio,
                    ApuracaoDia.data <= periodo.data_fim,
                )
                .order_by(ApuracaoDia.data.asc())
            )
        )
        .scalars()
        .all()
    )
    apuracoes_por_id = {a.id: a for a in apuracoes}

    componentes_por_apuracao: dict[UUID, list[ApuracaoComponente]] = {}
    if apuracoes_por_id:
        linhas_componentes = (
            await sessao.execute(
                sa.select(ApuracaoComponente).where(
                    ApuracaoComponente.apuracao_dia_id.in_(apuracoes_por_id)
                )
            )
        ).scalars()
        for componente in linhas_componentes:
            componentes_por_apuracao.setdefault(componente.apuracao_dia_id, []).append(componente)

    tratamentos = list(
        (
            await sessao.execute(
                sa.select(Tratamento).where(
                    Tratamento.tenant_id == tenant_id,
                    Tratamento.vinculo_id == vinculo.id,
                    Tratamento.data_referencia >= periodo.data_inicio,
                    Tratamento.data_referencia <= periodo.data_fim,
                    Tratamento.status.in_(_STATUS_TRATAMENTO_VISIVEL),
                )
            )
        )
        .scalars()
        .all()
    )
    tipos_tratamento: dict[UUID, TipoTratamento] = {}
    if tratamentos:
        ids_tipo = {t.tipo_tratamento_id for t in tratamentos}
        linhas_tipo = (
            await sessao.execute(sa.select(TipoTratamento).where(TipoTratamento.id.in_(ids_tipo)))
        ).scalars()
        tipos_tratamento = {t.id: t for t in linhas_tipo}
    tratamentos_por_dia: dict[dt.date, list[dict[str, Any]]] = {}
    for tratamento in tratamentos:
        tipo = tipos_tratamento.get(tratamento.tipo_tratamento_id)
        tratamentos_por_dia.setdefault(tratamento.data_referencia, []).append(
            {
                "id": str(tratamento.id),
                "tipoTratamentoCodigo": tipo.codigo if tipo else None,
                "tipoTratamentoNome": tipo.nome if tipo else None,
                "motivo": tratamento.motivo,
                "status": tratamento.status,
                "origem": tratamento.origem,
            }
        )

    dias: list[dict[str, Any]] = []
    total_previsto = 0
    total_trabalhado = 0
    total_extras = 0
    total_faltas = 0
    total_noturno = 0

    apuracoes_por_data = {a.data: a for a in apuracoes}
    for data in dias_do_intervalo(periodo.data_inicio, periodo.data_fim):
        apuracao = apuracoes_por_data.get(data)
        if apuracao is None:
            dias.append(
                {
                    "data": data.isoformat(),
                    "tipoDia": "nao_apurado",
                    "previstoMinutos": 0,
                    "trabalhadoMinutos": 0,
                    "extrasMinutos": 0,
                    "faltaMinutos": 0,
                    "noturnoMinutos": 0,
                    "saldoMinutos": 0,
                    "marcacoesImpares": False,
                    "status": "pendente",
                    "componentes": [],
                    "tratamentos": tratamentos_por_dia.get(data, []),
                }
            )
            continue
        extras_dia = (apuracao.extras_minutos or 0) + (apuracao.extras_noturnas_minutos or 0)
        noturno_dia = (apuracao.noturno_minutos or 0) + (apuracao.noturno_ficta_minutos or 0)
        total_previsto += apuracao.previsto_minutos or 0
        total_trabalhado += apuracao.trabalhado_minutos or 0
        total_extras += extras_dia
        total_faltas += apuracao.falta_minutos or 0
        total_noturno += noturno_dia
        dias.append(
            {
                "data": data.isoformat(),
                "tipoDia": apuracao.tipo_dia,
                "previstoMinutos": apuracao.previsto_minutos or 0,
                "trabalhadoMinutos": apuracao.trabalhado_minutos or 0,
                "extrasMinutos": extras_dia,
                "faltaMinutos": apuracao.falta_minutos or 0,
                "noturnoMinutos": noturno_dia,
                "saldoMinutos": apuracao.saldo_minutos or 0,
                "marcacoesImpares": bool(apuracao.marcacoes_impares),
                "status": apuracao.status,
                "componentes": [
                    {
                        "codigo": c.codigo,
                        "categoria": c.categoria,
                        "minutos": c.minutos,
                        "fator": str(c.fator),
                        "minutosEquivalentes": c.minutos_equivalentes,
                        "origem": c.origem,
                    }
                    for c in componentes_por_apuracao.get(apuracao.id, [])
                ],
                "tratamentos": tratamentos_por_dia.get(data, []),
            }
        )

    saldo_banco = await _saldo_banco_horas(sessao, tenant_id, vinculo, periodo.data_fim)

    return {
        "empresa": {
            "id": str(empresa.id),
            "razaoSocial": empresa.razao_social,
            "cnpj": empresa.cnpj,
        },
        "colaborador": {
            "id": str(colaborador.id),
            "nomeCompleto": colaborador.nome_completo,
            "matricula": colaborador.matricula,
            "cpf": colaborador.cpf,
        },
        "vinculo": {"id": str(vinculo.id)},
        "periodo": {
            "id": str(periodo.id),
            "codigo": periodo.codigo,
            "dataInicio": periodo.data_inicio.isoformat(),
            "dataFim": periodo.data_fim.isoformat(),
        },
        "dias": dias,
        "totais": {
            "previstoMinutos": total_previsto,
            "trabalhadoMinutos": total_trabalhado,
            "extrasMinutos": total_extras,
            "faltasMinutos": total_faltas,
            "noturnoMinutos": total_noturno,
            "saldoBancoMinutos": saldo_banco,
        },
        "geradoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }


async def gerar_espelho_do_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    periodo: Periodo,
    vinculo_id: UUID,
    tipo: str,
    *,
    fechamento_id: UUID | None = None,
    gerar_pdf: bool = False,
    usuario_id: UUID | None = None,
) -> Espelho:
    """Monta o `conteudo`, calcula o hash, grava `Espelho` com `versao`
    incrementada e, se `gerar_pdf`, gera o PDF (`pdf.py`) e grava via
    `app.comum.armazenamento` (MinIO), preenchendo `conteudo_ref` com a
    chave do objeto."""
    tipo_pedido = _valor(tipo)
    vinculo = await _carregar_vinculo(sessao, tenant_id, vinculo_id)

    ultima_versao_linha = (
        await sessao.execute(
            sa.select(Espelho)
            .where(
                Espelho.tenant_id == tenant_id,
                Espelho.periodo_id == periodo.id,
                Espelho.vinculo_id == vinculo.id,
            )
            .order_by(Espelho.versao.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    nova_versao = (ultima_versao_linha.versao if ultima_versao_linha is not None else 0) + 1

    tipo_efetivo = tipo_pedido
    ja_havia_oficial = ultima_versao_linha is not None and ultima_versao_linha.tipo in (
        "oficial",
        "retificado",
    )
    if tipo_pedido == "oficial" and ja_havia_oficial:
        # Retificacao: PCF §2.4 item 5 -- versao nova nunca sobrescreve, e o
        # tipo vira 'retificado' automaticamente.
        tipo_efetivo = "retificado"

    conteudo = await _montar_conteudo(sessao, tenant_id, periodo, vinculo)
    hash_sha256 = _hash_conteudo(conteudo)

    espelho = Espelho(
        tenant_id=tenant_id,
        periodo_id=periodo.id,
        fechamento_id=fechamento_id,
        colaborador_id=vinculo.colaborador_id,
        vinculo_id=vinculo.id,
        versao=nova_versao,
        tipo=tipo_efetivo,
        conteudo=conteudo,
        hash_sha256=hash_sha256,
        total_previsto_minutos=conteudo["totais"]["previstoMinutos"],
        total_trabalhado_minutos=conteudo["totais"]["trabalhadoMinutos"],
        total_extras_minutos=conteudo["totais"]["extrasMinutos"],
        total_faltas_minutos=conteudo["totais"]["faltasMinutos"],
        total_noturno_minutos=conteudo["totais"]["noturnoMinutos"],
        saldo_banco_minutos=conteudo["totais"]["saldoBancoMinutos"],
        gerado_em=dt.datetime.now(tz=dt.UTC),
        gerado_por=usuario_id,
        criado_por=usuario_id,
    )
    sessao.add(espelho)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if gerar_pdf:
        from app.comum.armazenamento import salvar_objeto
        from app.workflow.fechamento.pdf import gerar_pdf_espelho

        pdf_bytes = gerar_pdf_espelho(
            conteudo, hash_sha256=hash_sha256, versao=nova_versao, tipo=tipo_efetivo
        )
        chave = f"espelhos/{tenant_id}/{espelho.id}.pdf"
        await salvar_objeto(chave, pdf_bytes, content_type="application/pdf")
        espelho.conteudo_ref = chave
        await sessao.flush()

    return espelho


async def obter_espelho(sessao: AsyncSession, tenant_id: UUID, espelho_id: UUID) -> Espelho:
    espelho = await sessao.get(Espelho, espelho_id)
    if espelho is None or espelho.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Espelho nao encontrado.")
    return espelho


async def listar_espelhos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    periodo_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    fechamento_id: UUID | None = None,
    tipo: str | None = None,
    assinado: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Espelho], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_ESPELHO), padrao="geradoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Espelho).where(Espelho.tenant_id == tenant_id)
    if periodo_id is not None:
        consulta = consulta.where(Espelho.periodo_id == periodo_id)
    if colaborador_id is not None:
        consulta = consulta.where(Espelho.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(Espelho.vinculo_id == vinculo_id)
    if fechamento_id is not None:
        consulta = consulta.where(Espelho.fechamento_id == fechamento_id)
    if tipo is not None:
        consulta = consulta.where(Espelho.tipo == tipo)
    if assinado is not None:
        from ponto_contracts import AssinaturaEspelho

        subconsulta = sa.select(AssinaturaEspelho.espelho_id).where(
            AssinaturaEspelho.tenant_id == tenant_id, AssinaturaEspelho.status == "assinado"
        )
        consulta = consulta.where(
            Espelho.id.in_(subconsulta) if assinado else Espelho.id.not_in(subconsulta)
        )

    campo = _CAMPOS_ORDENACAO_ESPELHO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Espelho.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "gerado_em" if ordenacao.campo == "geradoEm" else "versao"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def resolver_escopo_espelhos(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.EspelhoCriar,
) -> list[UUID]:
    """Resolve `EspelhoCriar` (vínculos explícitos OU escopo empresa/
    unidade) em vínculos concretos, para `gerarEspelhos` enfileirar **um
    job por vínculo** (mesmo padrão de fan-out no momento do
    enfileiramento que `app.apuracao.tratamento.recalculo.
    enfileirar_recalculo` já usa)."""
    if dados.vinculo_ids:
        return list(dados.vinculo_ids)
    if dados.empresa_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Informe vinculoIds ou empresaId (com unidadeId opcional) para delimitar "
            "o escopo.",
        )
    vinculos = await resolver_vinculos_do_escopo(
        sessao,
        tenant_id,
        escopo="unidade" if dados.unidade_id is not None else "empresa",
        empresa_id=dados.empresa_id,
        unidade_id=dados.unidade_id,
    )
    return [v.id for v in vinculos]


#: Nome de fila/tarefa: contrato com `apps/worker/worker/tarefas/fechamento.
#: py::gerar_espelhos` e `apps/worker/worker/filas.py`.
NOME_TAREFA_GERAR_ESPELHOS = "gerar_espelhos"


async def criar_espelhos_assincrono(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.EspelhoCriar,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.ProcessamentoAssincrono:
    """`gerarEspelhos` (T7): resolve o escopo, enfileira `gerar_espelhos`
    (worker) com os vínculos já resolvidos, devolve `202`/
    `ProcessamentoAssincrono` -- **sem preencher `tipo`** por consistência
    com `criarFechamento` (o enum de `ProcessamentoAssincrono.tipo` TEM o
    valor `espelho`, mas `tipo` não é `required`; deixamos de fora para não
    prometer um identificador de acompanhamento que a tag `espelhos` não
    expõe -- `GET /v1/espelhos` é como o cliente observa a conclusão)."""
    if dados.periodo_id is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="periodoId e obrigatorio.")
    periodo = await sessao.get(Periodo, dados.periodo_id)
    if periodo is None or periodo.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Periodo nao encontrado.")

    vinculo_ids = await resolver_escopo_espelhos(sessao, tenant_id, dados)
    tipo = _valor(dados.tipo) or "previo"

    from arq import create_pool
    from arq.connections import RedisSettings

    from app.core.filas import FILA_PADRAO

    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_GERAR_ESPELHOS,
            tenant_id=str(tenant_id),
            periodo_id=str(periodo.id),
            vinculo_ids=[str(v) for v in vinculo_ids],
            tipo=tipo,
            gerar_pdf=bool(dados.gerar_pdf),
            usuario_id=str(usuario_id) if usuario_id else None,
        )
    finally:
        await pool.aclose()

    # `.model_validate({...})` -- mesmo motivo documentado em `servico.py::
    # criar_fechamento` (alias vs. nome de campo na assinatura sintetizada
    # pelo plugin do mypy).
    return esquemas.ProcessamentoAssincrono.model_validate(
        {
            "id": uuid4(),
            "status": "enfileirado",
            "totalItens": len(vinculo_ids),
            "itensProcessados": 0,
        }
    )
