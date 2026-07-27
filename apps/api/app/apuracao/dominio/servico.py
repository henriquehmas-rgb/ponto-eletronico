"""`apurar_dia` -- a funcao publica desta fase (T4).

Assinatura FIXADA pelo PCF (secao 4): `apurar_dia(sessao, tenant_id,
vinculo_id, data) -> ApuracaoDia` (schema Pydantic gerado do contrato, nunca
um tipo novo). E a funcao que `apps/worker/worker/tarefas/apuracao.py`
chama e que `app.apuracao.tratamento.recalculo.recalcular_periodo` (A3) chama
para cada `(vinculo, dia)` do intervalo reprocessado -- ninguem duplica a
logica de pareamento/calculo, todos importam esta funcao.

Sequencia executada por chamada (ADR-004: funcao pura de insumos
versionados, materializada -- so a MATERIALIZACAO/leitura de banco e
impura; `app.apuracao.dominio.calculo.calcular_dia` continua pura):

1. Busca o `Vinculo` (empresa/unidade/departamento/centro de custo).
2. Chama `app.jornada.resolvedor.servico.resolver_jornada_do_dia` (F3). Em
   `PONTO-APUR-002` (sem jornada nem escala vigente), grava
   `tipo_dia='nao_apurado'`, todos os minutos zerados, `status =
   'com_ocorrencia'`, abre ocorrencia e devolve -- NUNCA propaga a excecao
   ao chamador de lote (decisao fixada no PCF, secao 2). **Achado de
   contrato, registrado no relatorio da fase**: o `CHECK` de
   `ocorrencias.codigo` nao tem nenhum valor que signifique "vinculo sem
   jornada/escala vigente" -- os 18 codigos fechados sao todos sobre
   marcacao/calculo/banco/terminal. Usa-se `sem_marcacao` (o mais proximo
   semanticamente: o dia realmente NAO tem apuracao de marcacao nenhuma),
   com `severidade='critica'` e `detalhes` explicando a causa real, ate que
   uma RFC acrescente um codigo dedicado.
3. Le a janela do dia (marcacoes + borda anterior/seguinte quando a jornada
   cruza a meia-noite) e os tratamentos aprovados/aplicados do dia.
4. Aplica `inclusao_marcacao` (marcacao ficticia no pareamento) e
   `desconsideracao_marcacao` (remove a marcacao referenciada) ANTES de
   parear; aplica `abono` como `abono_minutos`. As demais categorias
   (`justificativa`, `afastamento`, `ajuste_intervalo`, `compensacao`,
   `ajuste_saldo`) NAO tem efeito numerico nesta funcao -- `afastamento` ja
   e insumo de F3 (via `afastamentos`), `compensacao`/`ajuste_saldo` afetam
   o banco de horas (A2), nao a apuracao de minutos, e `ajuste_intervalo`/
   `justificativa` ficam registrados como achado no relatorio da fase (sem
   especificacao precisa o bastante no PCF para formalizar sem arriscar
   inventar regra).
5. Chama `app.apuracao.dominio.calculo.calcular_dia` (pura).
6. Calcula `hash_entrada` (SHA-256 de um dicionario canonico dos insumos:
   marcacoes, tratamentos consumidos, resolucao da jornada, configuracao de
   calculo efetiva). Se o hash bate com o gravado, e' *no-op*: nao
   reescreve `apuracoes_dia`/`apuracao_componentes`, nao sincroniza
   ocorrencias, nao publica evento, nao promove tratamento a `aplicado`.
7. Caso o hash mude, faz `INSERT ... ON CONFLICT (tenant_id, vinculo_id,
   data) DO UPDATE` (respeitando `uq_apuracoes_dia`), com a clausula
   `WHERE` do `ON CONFLICT` comparando o hash ja gravado -- e o proprio
   banco quem garante que a segunda chamada com o MESMO hash nao grava
   linha nenhuma (nao apenas "aplicacao decide nao escrever", o `UPDATE` do
   Postgres literalmente nao acontece).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from ponto_contracts import (
    ApuracaoComponente as ApuracaoComponenteOrm,
)
from ponto_contracts import (
    ApuracaoDia as ApuracaoDiaOrm,
)
from ponto_contracts import (
    Jornada,
    Marcacao,
    Ocorrencia,
    TipoTratamento,
    Tratamento,
    Vinculo,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio import eventos
from app.apuracao.dominio.calculo import (
    ConfiguracaoCalculo,
    ResultadoCalculoDia,
    calcular_dia,
    montar_faixas_extra,
)
from app.apuracao.dominio.pareamento import MarcacaoParaPareamento, parear_marcacoes
from app.core.erros import ErroDeAplicacao
from app.jornada.resolvedor.servico import CODIGO_SEM_REGRA, resolver_jornada_do_dia
from app.schemas import contrato

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"

#: Codigo de ocorrencia usado para `PONTO-APUR-002` -- ver ponto 2 do
#: docstring do modulo (achado de contrato: nenhum codigo do `CHECK`
#: significa "sem jornada/escala vigente").
CODIGO_OCORRENCIA_SEM_JORNADA_VIGENTE = "sem_marcacao"

#: Categorias de `tipos_tratamento.categoria` que este modulo consome
#: diretamente (ver ponto 4 do docstring). As demais sao lidas (contam para
#: `tem_tratamento`) mas nao alteram nenhum numero calculado aqui.
_CATEGORIA_INCLUSAO_MARCACAO = "inclusao_marcacao"
_CATEGORIA_DESCONSIDERACAO_MARCACAO = "desconsideracao_marcacao"
_CATEGORIA_ABONO = "abono"
#: Status de tratamento considerados "aplicaveis" na apuracao -- aprovado e
#: ainda nao consumido, ou ja aplicado por uma apuracao anterior (precisa
#: continuar sendo lido para o recalculo permanecer deterministico).
_STATUS_TRATAMENTO_APLICAVEIS = ("aprovado", "aplicado")

#: Configuracao de calculo usada quando a resolucao nao tem `jornada_id`
#: (vinculo dirigido por escala sem jornada vinculada -- `escalas.jornada_id`
#: e nullable). Os valores SAO os defaults de coluna de `jornadas` no
#: schema.sql, reaproveitados aqui em vez de inventar uma politica nova.
_CONFIG_PADRAO_SEM_JORNADA = ConfiguracaoCalculo(
    tolerancia_marcacao_minutos=5,
    tolerancia_diaria_minutos=10,
    descontar_tudo_se_exceder=False,
    intervalo_minimo_minutos=None,
    interjornada_minima_minutos=660,
    noturno_inicio=dt.time(22, 0),
    noturno_fim=dt.time(5, 0),
    hora_ficta_noturna=True,
    prorrogacao_noturna=True,
    limite_extra_diario_minutos=120,
    limite_jornada_diaria_minutos=600,
)


async def obter_vinculo(sessao: AsyncSession, vinculo_id: UUID) -> Vinculo:
    vinculo = await sessao.get(Vinculo, vinculo_id)
    if vinculo is None or vinculo.excluido_em is not None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


def _json_canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), default=str)


def _hash_insumos(dados: dict[str, Any]) -> str:
    """SHA-256 do dicionario canonico de insumos (ADR-004, ponto 4)."""
    return hashlib.sha256(_json_canonico(dados).encode("utf-8")).hexdigest()


def _janela_do_dia(
    resolucao: contrato.ResolucaoJornada, data: dt.date, fuso: ZoneInfo
) -> tuple[dt.datetime, dt.datetime]:
    """Janela prevista do dia: `entrada_prevista`/`saida_prevista`, ja
    resolvidas pela F3 no fuso efetivo (inclusive a borda seguinte quando
    `cruza_meia_noite`). Sem horario algum (folga/DSR puro sem turno), cai
    no dia civil completo `[00:00, 00:00 do dia seguinte)`."""
    inicio = resolucao.entrada_prevista or dt.datetime.combine(data, dt.time.min, tzinfo=fuso)
    fim = resolucao.saida_prevista or dt.datetime.combine(
        data + dt.timedelta(days=1), dt.time.min, tzinfo=fuso
    )
    return inicio, fim


def _parse_intervalos_previstos(
    resolucao: contrato.ResolucaoJornada, referencia: dt.datetime
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Reconstroi os intervalos previstos (ISO `HH:MM`, sem segundos --
    mesmo formato que `app.jornada.resolvedor.servico._montar_horario`
    grava) como datetimes com fuso, ancorados na data de `referencia`
    (normalmente `entrada_prevista`)."""
    bruto = resolucao.intervalos_previstos
    if not bruto:
        return []
    itens = bruto.get("intervalos")
    if not isinstance(itens, list):
        return []
    fuso = referencia.tzinfo
    dia_base = referencia.date()
    resultado: list[tuple[dt.datetime, dt.datetime]] = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        inicio_str = item.get("inicio")
        fim_str = item.get("fim")
        if not inicio_str or not fim_str:
            continue
        inicio_hora = dt.time.fromisoformat(inicio_str)
        fim_hora = dt.time.fromisoformat(fim_str)
        inicio_datahora = dt.datetime.combine(dia_base, inicio_hora, tzinfo=fuso)
        fim_datahora = dt.datetime.combine(dia_base, fim_hora, tzinfo=fuso)
        if fim_datahora <= inicio_datahora:
            fim_datahora += dt.timedelta(days=1)
        resultado.append((inicio_datahora, fim_datahora))
    return resultado


def _montar_configuracao(jornada: Jornada | None) -> ConfiguracaoCalculo:
    if jornada is None:
        return _CONFIG_PADRAO_SEM_JORNADA
    return ConfiguracaoCalculo(
        tolerancia_marcacao_minutos=jornada.tolerancia_marcacao_minutos,
        tolerancia_diaria_minutos=jornada.tolerancia_diaria_minutos,
        descontar_tudo_se_exceder=jornada.descontar_tudo_se_exceder,
        intervalo_minimo_minutos=jornada.intervalo_minimo_minutos,
        interjornada_minima_minutos=jornada.interjornada_minima_minutos,
        noturno_inicio=jornada.noturno_inicio,
        noturno_fim=jornada.noturno_fim,
        hora_ficta_noturna=jornada.hora_ficta_noturna,
        prorrogacao_noturna=jornada.prorrogacao_noturna,
        limite_extra_diario_minutos=jornada.limite_extra_diario_minutos,
        limite_jornada_diaria_minutos=jornada.limite_jornada_diaria_minutos,
        faixas_extra=montar_faixas_extra(jornada.fatores_extra),
    )


def _config_para_hash(config: ConfiguracaoCalculo) -> dict[str, Any]:
    return {
        "toleranciaMarcacaoMinutos": config.tolerancia_marcacao_minutos,
        "toleranciaDiariaMinutos": config.tolerancia_diaria_minutos,
        "descontarTudoSeExceder": config.descontar_tudo_se_exceder,
        "intervaloMinimoMinutos": config.intervalo_minimo_minutos,
        "interjornadaMinimaMinutos": config.interjornada_minima_minutos,
        "noturnoInicio": config.noturno_inicio.isoformat(),
        "noturnoFim": config.noturno_fim.isoformat(),
        "horaFictaNoturna": config.hora_ficta_noturna,
        "prorrogacaoNoturna": config.prorrogacao_noturna,
        "limiteExtraDiarioMinutos": config.limite_extra_diario_minutos,
        "limiteJornadaDiariaMinutos": config.limite_jornada_diaria_minutos,
        "faixasExtra": [
            {"fator": str(faixa.fator), "ateMinutos": faixa.ate_minutos}
            for faixa in config.faixas_extra
        ],
    }


def _resolucao_para_hash(resolucao: contrato.ResolucaoJornada) -> dict[str, Any]:
    return {
        "tipoDia": str(resolucao.tipo_dia) if resolucao.tipo_dia else None,
        "jornadaId": str(resolucao.jornada_id) if resolucao.jornada_id else None,
        "escalaId": str(resolucao.escala_id) if resolucao.escala_id else None,
        "turnoId": str(resolucao.turno_id) if resolucao.turno_id else None,
        "horarioId": str(resolucao.horario_id) if resolucao.horario_id else None,
        "feriadoId": str(resolucao.feriado_id) if resolucao.feriado_id else None,
        "afastamentoId": str(resolucao.afastamento_id) if resolucao.afastamento_id else None,
        "cargaPrevistaMinutos": resolucao.carga_prevista_minutos,
        "entradaPrevista": (
            resolucao.entrada_prevista.isoformat() if resolucao.entrada_prevista else None
        ),
        "saidaPrevista": (
            resolucao.saida_prevista.isoformat() if resolucao.saida_prevista else None
        ),
    }


@dataclass(frozen=True, slots=True)
class _InsumosDoDia:
    """Insumos lidos do banco para um `(vinculo, dia)`, ja com
    `inclusao_marcacao`/`desconsideracao_marcacao` aplicadas ao pareamento e
    `abono` resumido. Ver docstring de `_carregar_marcacoes_e_tratamentos`."""

    marcacoes_para_pareamento: list[MarcacaoParaPareamento]
    ultima_marcacao_dia_anterior: dt.datetime | None
    tratamentos_consumidos: list[Tratamento]
    abono_minutos_explicito: int
    abono_dia_inteiro: bool
    tem_tratamento: bool


async def _carregar_marcacoes_e_tratamentos(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    janela_inicio: dt.datetime,
    janela_fim: dt.datetime,
    data_referencia: dt.date,
) -> _InsumosDoDia:
    """Le marcacoes (dia + borda anterior, ate 1 dia antes de `janela_inicio`)
    e tratamentos aprovados/aplicados do dia, ja aplicando
    `inclusao_marcacao`/`desconsideracao_marcacao` e resumindo `abono`.

    `abono_minutos` final (que pode ser o dia inteiro) so e resolvido pelo
    chamador, depois que `previsto_minutos` e conhecido -- aqui so se
    devolve a soma explicita (`minutos_ajuste` positivos) e a flag de
    "abona o dia inteiro" (tratamento sem `minutos_ajuste`).
    """
    janela_consulta_inicio = janela_inicio - dt.timedelta(days=1)
    resultado_marcacoes = await sessao.execute(
        sa.select(Marcacao)
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.vinculo_id == vinculo_id,
            Marcacao.datahora_marcacao >= janela_consulta_inicio,
            Marcacao.datahora_marcacao < janela_fim,
        )
        .order_by(Marcacao.datahora_marcacao, Marcacao.nsr)
    )
    marcacoes_orm = list(resultado_marcacoes.scalars().all())

    marcacoes_do_dia = [m for m in marcacoes_orm if m.datahora_marcacao >= janela_inicio]
    marcacoes_anteriores = [m for m in marcacoes_orm if m.datahora_marcacao < janela_inicio]
    ultima_marcacao_dia_anterior = (
        marcacoes_anteriores[-1].datahora_marcacao if marcacoes_anteriores else None
    )

    marcacoes_para_pareamento: list[MarcacaoParaPareamento] = [
        MarcacaoParaPareamento(
            id=m.id,
            datahora=m.datahora_marcacao,
            nsr=m.nsr,
            sentido_informado=m.sentido_informado,  # type: ignore[arg-type]
            origem="marcacao",
        )
        for m in marcacoes_do_dia
    ]

    resultado_tratamentos = await sessao.execute(
        sa.select(Tratamento, TipoTratamento.categoria)
        .join(TipoTratamento, TipoTratamento.id == Tratamento.tipo_tratamento_id)
        .where(
            Tratamento.tenant_id == tenant_id,
            Tratamento.vinculo_id == vinculo_id,
            Tratamento.data_referencia == data_referencia,
            Tratamento.status.in_(_STATUS_TRATAMENTO_APLICAVEIS),
        )
    )
    linhas_tratamento = resultado_tratamentos.all()

    tem_tratamento = bool(linhas_tratamento)
    tratamentos_consumidos: list[Tratamento] = []
    ids_desconsiderados: set[UUID] = set()
    abono_explicito_minutos = 0
    abono_dia_inteiro = False

    for tratamento, categoria in linhas_tratamento:
        if categoria == _CATEGORIA_INCLUSAO_MARCACAO and tratamento.datahora_proposta is not None:
            marcacoes_para_pareamento.append(
                MarcacaoParaPareamento(
                    id=None,
                    datahora=tratamento.datahora_proposta,
                    nsr=-1,
                    sentido_informado=tratamento.sentido,
                    origem="tratamento",
                )
            )
            tratamentos_consumidos.append(tratamento)
        elif (
            categoria == _CATEGORIA_DESCONSIDERACAO_MARCACAO and tratamento.marcacao_id is not None
        ):
            ids_desconsiderados.add(tratamento.marcacao_id)
            tratamentos_consumidos.append(tratamento)
        elif categoria == _CATEGORIA_ABONO:
            if tratamento.minutos_ajuste is not None and tratamento.minutos_ajuste > 0:
                abono_explicito_minutos += tratamento.minutos_ajuste
            else:
                abono_dia_inteiro = True
            tratamentos_consumidos.append(tratamento)
        # Demais categorias (justificativa, afastamento, ajuste_intervalo,
        # compensacao, ajuste_saldo): sem efeito numerico aqui -- ver ponto 4
        # do docstring do modulo.

    if ids_desconsiderados:
        marcacoes_para_pareamento = [
            m for m in marcacoes_para_pareamento if m.id not in ids_desconsiderados
        ]

    return _InsumosDoDia(
        marcacoes_para_pareamento=marcacoes_para_pareamento,
        ultima_marcacao_dia_anterior=ultima_marcacao_dia_anterior,
        tratamentos_consumidos=tratamentos_consumidos,
        abono_minutos_explicito=abono_explicito_minutos,
        abono_dia_inteiro=abono_dia_inteiro,
        tem_tratamento=tem_tratamento,
    )


def _tratamentos_para_hash(tratamentos: Sequence[Tratamento]) -> list[dict[str, Any]]:
    itens = [
        {
            "id": str(t.id),
            "status": t.status,
            "atualizadoEm": t.atualizado_em.isoformat() if t.atualizado_em else None,
        }
        for t in tratamentos
    ]
    return sorted(itens, key=lambda item: str(item["id"]))


def _marcacoes_para_hash(marcacoes: Sequence[MarcacaoParaPareamento]) -> list[dict[str, Any]]:
    itens = [
        {
            "id": str(m.id) if m.id is not None else None,
            "datahora": m.datahora.isoformat(),
            "nsr": m.nsr,
            "origem": m.origem,
        }
        for m in marcacoes
    ]
    return sorted(itens, key=lambda item: (str(item["datahora"]), item["nsr"]))


async def _gravar_nao_apurado(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo: Vinculo,
    data: dt.date,
) -> contrato.ApuracaoDia:
    """`PONTO-APUR-002`: sem jornada/escala vigente. Ver ponto 2 do docstring
    do modulo -- inclusive o achado de contrato sobre o codigo de
    ocorrencia."""
    novo_hash = _hash_insumos(
        {"erro": CODIGO_SEM_REGRA, "vinculoId": str(vinculo.id), "data": data.isoformat()}
    )
    linha, mudou = await _upsert_apuracao_dia(
        sessao,
        tenant_id=tenant_id,
        vinculo=vinculo,
        data=data,
        resolucao=None,
        resultado=None,
        novo_hash=novo_hash,
        status_forcado="com_ocorrencia",
        tipo_dia_forcado="nao_apurado",
    )
    if mudou:
        await _sincronizar_ocorrencia(
            sessao,
            tenant_id=tenant_id,
            vinculo=vinculo,
            apuracao_dia_id=linha.id,
            data=data,
            codigo=CODIGO_OCORRENCIA_SEM_JORNADA_VIGENTE,
            severidade="critica",
            descricao=(
                "Vinculo sem jornada nem escala vigente nesta data "
                "(PONTO-APUR-002); dia gravado como nao_apurado."
            ),
            detalhes={"motivo": CODIGO_SEM_REGRA},
        )
    return await _montar_schema_resposta(sessao, linha)


async def _upsert_apuracao_dia(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    vinculo: Vinculo,
    data: dt.date,
    resolucao: contrato.ResolucaoJornada | None,
    resultado: ResultadoCalculoDia | None,
    novo_hash: str,
    tem_tratamento: bool = False,
    status_forcado: str | None = None,
    tipo_dia_forcado: str | None = None,
) -> tuple[ApuracaoDiaOrm, bool]:
    """`INSERT ... ON CONFLICT (tenant_id, vinculo_id, data) DO UPDATE`
    (`uq_apuracoes_dia`), com o `UPDATE` condicionado a `hash_entrada`
    diferente -- e o que torna a segunda chamada com o mesmo hash um NO-OP
    real no banco (nao so uma decisao da aplicacao). Devolve
    `(linha, mudou)`."""
    agora = dt.datetime.now(tz=dt.UTC)
    r = resultado
    if tipo_dia_forcado is not None:
        tipo_dia = tipo_dia_forcado
    elif resolucao is not None and resolucao.tipo_dia is not None:
        tipo_dia = str(resolucao.tipo_dia)
    else:
        tipo_dia = "util"
    previsto_minutos = (resolucao.carga_prevista_minutos or 0) if resolucao is not None else 0
    saldo_minutos = 0
    if r is not None:
        saldo_minutos = (
            r.extras_minutos + r.dsr_credito_minutos - r.falta_minutos - r.dsr_debito_minutos
        )
    if status_forcado is not None:
        status_final = status_forcado
    elif r is not None and r.ocorrencias:
        status_final = "com_ocorrencia"
    else:
        status_final = "apurado"

    valores: dict[str, Any] = {
        "tenant_id": tenant_id,
        "vinculo_id": vinculo.id,
        "colaborador_id": vinculo.colaborador_id,
        "data": data,
        "empresa_id": vinculo.empresa_id,
        "unidade_id": vinculo.unidade_id,
        "departamento_id": vinculo.departamento_id,
        "centro_custo_id": vinculo.centro_custo_id,
        "jornada_id": resolucao.jornada_id if resolucao is not None else None,
        "escala_id": resolucao.escala_id if resolucao is not None else None,
        "turno_id": resolucao.turno_id if resolucao is not None else None,
        "horario_id": resolucao.horario_id if resolucao is not None else None,
        "feriado_id": resolucao.feriado_id if resolucao is not None else None,
        "afastamento_id": resolucao.afastamento_id if resolucao is not None else None,
        "tipo_dia": tipo_dia,
        "previsto_minutos": previsto_minutos,
        "trabalhado_minutos": r.trabalhado_minutos if r is not None else 0,
        "normais_minutos": r.normais_minutos if r is not None else 0,
        "extras_minutos": r.extras_minutos if r is not None else 0,
        "extras_noturnas_minutos": r.extras_noturnas_minutos if r is not None else 0,
        "noturno_minutos": r.noturno_minutos if r is not None else 0,
        "noturno_ficta_minutos": r.noturno_ficta_minutos if r is not None else 0,
        "intervalo_minutos": r.intervalo_minutos if r is not None else 0,
        "intervalo_previsto_minutos": r.intervalo_previsto_minutos if r is not None else 0,
        "intrajornada_suprimida_minutos": (
            r.intrajornada_suprimida_minutos if r is not None else 0
        ),
        "interjornada_minutos": r.interjornada_minutos if r is not None else None,
        "interjornada_violada": r.interjornada_violada if r is not None else False,
        "atraso_minutos": r.atraso_minutos if r is not None else 0,
        "saida_antecipada_minutos": r.saida_antecipada_minutos if r is not None else 0,
        "falta_minutos": r.falta_minutos if r is not None else 0,
        "abono_minutos": r.abono_minutos if r is not None else 0,
        "sobreaviso_minutos": 0,
        "prontidao_minutos": 0,
        "pausas_nr17_minutos": 0,
        "dsr_credito_minutos": r.dsr_credito_minutos if r is not None else 0,
        "dsr_debito_minutos": r.dsr_debito_minutos if r is not None else 0,
        "banco_credito_minutos": max(0, saldo_minutos),
        "banco_debito_minutos": max(0, -saldo_minutos),
        "tolerancia_aplicada_minutos": r.tolerancia_aplicada_minutos if r is not None else 0,
        "saldo_minutos": saldo_minutos,
        "quantidade_marcacoes": r.quantidade_marcacoes if r is not None else 0,
        "marcacoes_impares": r.marcacoes_impares if r is not None else False,
        "tem_tratamento": tem_tratamento,
        "status": status_final,
        "hash_entrada": novo_hash,
        "apurado_em": agora,
        "apurado_por": None,
        "versao": 1,
    }

    insercao = pg_insert(ApuracaoDiaOrm).values(**valores)
    campos_atualizaveis = {
        chave: getattr(insercao.excluded, chave)
        for chave in valores
        if chave not in ("tenant_id", "vinculo_id", "data")
    }
    campos_atualizaveis["versao"] = ApuracaoDiaOrm.versao + 1
    upsert = insercao.on_conflict_do_update(
        constraint="uq_apuracoes_dia",
        set_=campos_atualizaveis,
        where=sa.or_(
            ApuracaoDiaOrm.hash_entrada != insercao.excluded.hash_entrada,
            ApuracaoDiaOrm.hash_entrada.is_(None),
        ),
    ).returning(ApuracaoDiaOrm.id)

    resultado_execucao = await sessao.execute(upsert)
    linha_id = resultado_execucao.scalar_one_or_none()
    mudou = linha_id is not None
    await sessao.flush()

    if not mudou:
        linha_existente = (
            await sessao.execute(
                sa.select(ApuracaoDiaOrm).where(
                    ApuracaoDiaOrm.tenant_id == tenant_id,
                    ApuracaoDiaOrm.vinculo_id == vinculo.id,
                    ApuracaoDiaOrm.data == data,
                )
            )
        ).scalar_one()
        return linha_existente, False

    # `scalar_one()` (nao `sessao.get`, que devolveria `Any | None` sem
    # estreitar o tipo): a INSERT/UPDATE acima, na MESMA transacao, acabou
    # de gravar esta linha -- nao encontra-la aqui e um bug, nao um caminho
    # esperado, e `scalar_one()` levanta por si so nesse caso.
    linha = (
        await sessao.execute(sa.select(ApuracaoDiaOrm).where(ApuracaoDiaOrm.id == linha_id))
    ).scalar_one()
    return linha, True


async def _sincronizar_componentes(
    sessao: AsyncSession, apuracao_dia_id: UUID, tenant_id: UUID, resultado: ResultadoCalculoDia
) -> None:
    """Substitui a decomposicao anterior pela nova -- `apuracao_componentes`
    e derivada, sem ciclo de vida proprio (ao contrario de `ocorrencias`),
    entao apagar e reinserir e seguro."""
    await sessao.execute(
        sa.delete(ApuracaoComponenteOrm).where(
            ApuracaoComponenteOrm.apuracao_dia_id == apuracao_dia_id
        )
    )
    for componente in resultado.componentes:
        sessao.add(
            ApuracaoComponenteOrm(
                tenant_id=tenant_id,
                apuracao_dia_id=apuracao_dia_id,
                codigo=componente.codigo,
                categoria=componente.categoria,
                minutos=componente.minutos,
                fator=componente.fator,
                minutos_equivalentes=componente.minutos_equivalentes,
                origem=componente.origem,
                inicio=componente.inicio,
                fim=componente.fim,
                detalhes=componente.detalhes,
            )
        )
    await sessao.flush()


async def _sincronizar_ocorrencia(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    vinculo: Vinculo,
    apuracao_dia_id: UUID,
    data: dt.date,
    codigo: str,
    severidade: str,
    descricao: str,
    detalhes: dict[str, Any] | None = None,
) -> None:
    """Abre uma ocorrencia nova se nao houver uma ja ABERTA/EM_TRATAMENTO
    igual (mesmo `apuracao_dia_id` + `codigo`) -- ocorrencia nunca e
    corrigida sozinha (nem por este modulo), so o humano resolve; por isso
    nunca fechamos/atualizamos uma ocorrencia existente aqui."""
    existente = (
        await sessao.execute(
            sa.select(Ocorrencia.id).where(
                Ocorrencia.tenant_id == tenant_id,
                Ocorrencia.apuracao_dia_id == apuracao_dia_id,
                Ocorrencia.codigo == codigo,
                Ocorrencia.status.in_(("aberta", "em_tratamento")),
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return

    nova = Ocorrencia(
        tenant_id=tenant_id,
        colaborador_id=vinculo.colaborador_id,
        vinculo_id=vinculo.id,
        apuracao_dia_id=apuracao_dia_id,
        data=data,
        codigo=codigo,
        severidade=severidade,
        descricao=descricao,
        detalhes=detalhes,
        status="aberta",
    )
    sessao.add(nova)
    await sessao.flush()

    eventos.publicar_ocorrencia_aberta(
        tenant_id=tenant_id,
        ocorrencia_id=nova.id,
        colaborador_id=vinculo.colaborador_id,
        data=data,
        codigo=codigo,
        severidade=severidade,
        vinculo_id=vinculo.id,
        apuracao_dia_id=apuracao_dia_id,
        descricao=descricao,
    )


async def _promover_tratamentos_aplicados(
    sessao: AsyncSession, tratamentos: Sequence[Tratamento]
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    for tratamento in tratamentos:
        if tratamento.status == "aprovado":
            tratamento.status = "aplicado"
            tratamento.aplicado_em = agora
    if tratamentos:
        await sessao.flush()


async def _montar_schema_resposta(
    sessao: AsyncSession, linha: ApuracaoDiaOrm
) -> contrato.ApuracaoDia:
    componentes_orm = list(
        (
            await sessao.execute(
                sa.select(ApuracaoComponenteOrm).where(
                    ApuracaoComponenteOrm.apuracao_dia_id == linha.id
                )
            )
        )
        .scalars()
        .all()
    )
    componentes = [
        contrato.ApuracaoComponente.model_validate(c, from_attributes=True) for c in componentes_orm
    ]
    dados = contrato.ApuracaoDia.model_validate(linha, from_attributes=True)
    return dados.model_copy(update={"componentes": componentes})


async def apurar_dia(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, data: dt.date
) -> contrato.ApuracaoDia:
    """Assinatura fixada no PCF da fase (secao 4). Ver docstring do modulo
    para a sequencia completa."""
    vinculo = await obter_vinculo(sessao, vinculo_id)

    try:
        resolucao = await resolver_jornada_do_dia(sessao, tenant_id, vinculo_id, data)
    except ErroDeAplicacao as exc:
        if exc.codigo != CODIGO_SEM_REGRA:
            raise
        return await _gravar_nao_apurado(sessao, tenant_id, vinculo, data)

    fuso = ZoneInfo(resolucao.fuso_horario or "America/Sao_Paulo")
    janela_inicio, janela_fim = _janela_do_dia(resolucao, data, fuso)
    referencia_intervalos = resolucao.entrada_prevista or janela_inicio
    intervalos_previstos = _parse_intervalos_previstos(resolucao, referencia_intervalos)

    insumos = await _carregar_marcacoes_e_tratamentos(
        sessao, tenant_id, vinculo_id, janela_inicio, janela_fim, data
    )

    previsto_minutos = resolucao.carga_prevista_minutos or 0
    abono_minutos = (
        previsto_minutos if insumos.abono_dia_inteiro else insumos.abono_minutos_explicito
    )

    jornada: Jornada | None = None
    if resolucao.jornada_id is not None:
        jornada = await sessao.get(Jornada, resolucao.jornada_id)
    config = _montar_configuracao(jornada)

    resultado_pareamento = parear_marcacoes(insumos.marcacoes_para_pareamento)
    resultado = calcular_dia(
        tipo_dia=str(resolucao.tipo_dia) if resolucao.tipo_dia else "util",
        entrada_prevista=resolucao.entrada_prevista,
        saida_prevista=resolucao.saida_prevista,
        intervalos_previstos=intervalos_previstos,
        previsto_minutos=previsto_minutos,
        resultado_pareamento=resultado_pareamento,
        ultima_marcacao_dia_anterior=insumos.ultima_marcacao_dia_anterior,
        config=config,
        abono_minutos=abono_minutos,
    )

    novo_hash = _hash_insumos(
        {
            "marcacoes": _marcacoes_para_hash(insumos.marcacoes_para_pareamento),
            "tratamentos": _tratamentos_para_hash(insumos.tratamentos_consumidos),
            "resolucao": _resolucao_para_hash(resolucao),
            "config": _config_para_hash(config),
            "abonoMinutos": abono_minutos,
        }
    )

    linha, mudou = await _upsert_apuracao_dia(
        sessao,
        tenant_id=tenant_id,
        vinculo=vinculo,
        data=data,
        resolucao=resolucao,
        resultado=resultado,
        novo_hash=novo_hash,
        tem_tratamento=insumos.tem_tratamento,
    )

    if mudou:
        await _sincronizar_componentes(sessao, linha.id, tenant_id, resultado)
        for ocorrencia_detectada in resultado.ocorrencias:
            await _sincronizar_ocorrencia(
                sessao,
                tenant_id=tenant_id,
                vinculo=vinculo,
                apuracao_dia_id=linha.id,
                data=data,
                codigo=ocorrencia_detectada.codigo,
                severidade=ocorrencia_detectada.severidade,
                descricao=ocorrencia_detectada.descricao,
                detalhes=ocorrencia_detectada.detalhes,
            )
        await _promover_tratamentos_aplicados(sessao, insumos.tratamentos_consumidos)

    return await _montar_schema_resposta(sessao, linha)
