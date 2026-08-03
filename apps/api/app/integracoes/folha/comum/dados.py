"""Coleta da apuracao fechada de um periodo, materializada em
`LinhaApuracaoFolha` (F13/A5, T15). **Unico ponto** deste motor que fala
com `apuracoes_dia`/`apuracao_componentes`/`colaboradores`/`empresas`/
`periodos` -- nenhum exportador de parceiro (generico ou especifico)
consulta o banco por conta propria (ver docstring de `app.integracoes.
folha.comum`).

So leitura. Nunca escreve em `apuracoes_dia`/`bh_lancamentos`/nenhuma
tabela de calculo (PCF F13 secao 9, proibicao 8: "nenhuma linha desta fase
escreve em nsr_sequencias, apuracoes_dia, bh_lancamentos, afd_arquivos,
aej_arquivos").
"""

from __future__ import annotations

import calendar
import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    ApuracaoComponente,
    ApuracaoDia,
    Colaborador,
    Departamento,
    Empresa,
    Periodo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.comum.protocolo import LinhaApuracaoFolha

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"


def _competencia_para_intervalo(competencia_folha: str) -> tuple[dt.date, dt.date]:
    """`AAAA-MM` -> primeiro/ultimo dia do mes civil correspondente."""
    try:
        ano_str, mes_str = competencia_folha.split("-", 1)
        ano, mes = int(ano_str), int(mes_str)
    except ValueError as exc:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe=f"competenciaFolha invalida: {competencia_folha!r}."
        ) from exc
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return dt.date(ano, mes, 1), dt.date(ano, mes, ultimo_dia)


async def resolver_intervalo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    periodo_id: UUID | None,
    competencia_folha: str | None,
) -> tuple[dt.date, dt.date]:
    """Resolve `(inicio, fim)` a partir de `periodoId` (preferido, quando
    informado -- confere que o periodo pertence a mesma empresa/tenant) ou
    de `competenciaFolha` (mes civil `AAAA-MM`, quando nao ha `periodoId`).
    Nenhum dos dois informado e `PONTO-VAL-001`: a operacao nao tem como
    saber o que exportar."""
    if periodo_id is not None:
        periodo = (
            await sessao.execute(
                sa.select(Periodo).where(
                    Periodo.id == periodo_id,
                    Periodo.tenant_id == tenant_id,
                    Periodo.empresa_id == empresa_id,
                )
            )
        ).scalar_one_or_none()
        if periodo is None:
            raise ErroDeAplicacao(
                CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="periodoId nao encontrado para esta empresa."
            )
        return periodo.data_inicio, periodo.data_fim
    if competencia_folha:
        return _competencia_para_intervalo(competencia_folha)
    raise ErroDeAplicacao(
        CODIGO_CORPO_INVALIDO, detalhe="Informe periodoId ou competenciaFolha para a exportacao."
    )


async def coletar_linhas_apuracao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    unidade_id: UUID | None,
    somente_fechados: bool,
) -> list[LinhaApuracaoFolha]:
    """Uma linha por combinacao vinculo x dia x componente de apuracao
    (PCF T15), ja com os dados cadastrais do colaborador/empresa embutidos.
    `rubrica` sai sempre `None` aqui -- e resolvida por exportador, porque o
    de-para (`mapeamento_rubricas`) e por integracao, nao por linha bruta."""
    condicoes = [
        ApuracaoDia.tenant_id == tenant_id,
        ApuracaoDia.empresa_id == empresa_id,
        ApuracaoDia.data >= inicio,
        ApuracaoDia.data <= fim,
    ]
    if unidade_id is not None:
        condicoes.append(ApuracaoDia.unidade_id == unidade_id)
    if somente_fechados:
        condicoes.append(ApuracaoDia.status == "fechado")

    consulta = (
        sa.select(
            ApuracaoDia.vinculo_id,
            ApuracaoDia.colaborador_id,
            ApuracaoDia.empresa_id,
            ApuracaoDia.unidade_id,
            ApuracaoDia.departamento_id,
            ApuracaoDia.data,
            Colaborador.matricula,
            Colaborador.cpf,
            Colaborador.pis_nit,
            Colaborador.nome_completo,
            Empresa.cnpj,
            Departamento.codigo,
            ApuracaoComponente.codigo.label("componente_codigo"),
            ApuracaoComponente.descricao,
            ApuracaoComponente.categoria,
            ApuracaoComponente.minutos,
            ApuracaoComponente.fator,
            ApuracaoComponente.minutos_equivalentes,
            ApuracaoComponente.origem,
        )
        .join(ApuracaoComponente, ApuracaoComponente.apuracao_dia_id == ApuracaoDia.id)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .join(Empresa, Empresa.id == ApuracaoDia.empresa_id)
        .outerjoin(Departamento, Departamento.id == ApuracaoDia.departamento_id)
        .where(*condicoes)
        .order_by(Colaborador.matricula, ApuracaoDia.data, ApuracaoComponente.codigo)
    )
    linhas = list((await sessao.execute(consulta)).all())
    return [
        LinhaApuracaoFolha(
            vinculo_id=linha.vinculo_id,
            colaborador_id=linha.colaborador_id,
            empresa_id=linha.empresa_id,
            unidade_id=linha.unidade_id,
            departamento_id=linha.departamento_id,
            departamento_codigo=linha.codigo,
            matricula=linha.matricula,
            cpf=linha.cpf,
            pis_nit=linha.pis_nit,
            nome_completo=linha.nome_completo,
            empresa_cnpj=linha.cnpj,
            data=linha.data,
            componente_codigo=linha.componente_codigo,
            componente_descricao=linha.descricao,
            categoria=linha.categoria,
            minutos=linha.minutos,
            fator=linha.fator,
            minutos_equivalentes=linha.minutos_equivalentes,
            origem=linha.origem,
            rubrica=None,
        )
        for linha in linhas
    ]
