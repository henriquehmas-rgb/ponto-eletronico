"""Resolvedor de jornada do dia: `resolver_jornada_do_dia`.

Segue **exatamente** o algoritmo de precedencia fixado no PCF da fase
(`docs/fases/F03-motor-de-jornada.md`, secao 2):

1. Existe `escala_atribuicoes` vigente para o vinculo na data? A escala
   manda: o dia vem de `escala_ciclos`, indexado pela posicao do ciclo
   (`app.jornada.modelagem.escalas.posicao_do_ciclo`, reaproveitada, nunca
   duplicada).
2. Senao, existe `vinculo_jornadas` vigente? A jornada manda: o dia vem de
   `jornada_dias`, indexado pelo dia da semana (`0` domingo .. `6` sabado).
3. Senao, `PONTO-APUR-002` (nenhuma regra resolvida) -- nunca um 500, nunca
   um resultado inventado.

Depois de resolvida a base (escala ou jornada), duas camadas se sobrepoem,
nesta ordem fixa:

1. Afastamento aprovado, integral, cobrindo a data, do colaborador do
   vinculo -> `tipoDia = 'afastamento'`, `origem = 'afastamento'`.
2. Senao, feriado aplicavel a unidade do vinculo nesta data (via
   `unidade_feriado_conjuntos`, resolvendo moveis pelo ano da data
   consultada com `app.jornada.calendario.feriados.resolver_data_feriado`,
   que por sua vez usa `resolver_ancora_movel` de A2) -> `tipoDia` vem de
   `feriados.tipo` quando este e `feriado` ou `ponto_facultativo`; os demais
   tipos do catalogo (`data_comemorativa`, `compensado`) so preenchem
   `feriadoId`/`feriadoNome`, sem sobrescrever `tipoDia`/`origem`/carga (PCF,
   secao 2: "os demais tipos ... nao sobrescrevem o tipo do dia").
3. Senao, o `tipoDia` e a `origem` ficam os da base resolvida no passo 1/2
   acima (`'jornada'` ou `'escala'`).

`jornadaId`/`escalaId`/`turnoId`/`horarioId`/`entradaPrevista`/`saidaPrevista`
sempre refletem o que a jornada/escala previa para o dia, mesmo quando
`origem` acaba sendo `'feriado'` ou `'afastamento'` (PCF, secao 2).

---

**`CacheResolucao` (otimizacao de ADR-010, 2026-08-07).** Todas as leituras
que esta funcao faz sao de dados que NAO variam de um dia para o seguinte do
MESMO vinculo (a atribuicao de escala/jornada vigente, a jornada e seus
`jornada_dias`, o horario, o fuso da unidade, os afastamentos do colaborador,
o conjunto de feriados da unidade). Rodando `recalcular_periodo` sobre um
intervalo, o resolvedor disparava ~8,7 consultas POR DIA por vinculo --
medido, nao estimado: 27.100 dos 78.918 statements SQL de uma amostra de
3.100 apuracoes (34,3%).

`CacheResolucao` e um cache OPCIONAL, de vida curta, criado por quem chama em
lote (`recalcular_periodo`) e passado adiante por `apurar_dia`. Ele guarda
**linhas inteiras**, filtradas por data em Python exatamente com o mesmo
predicado que o SQL usava -- inclusive levantando `MultipleResultsFound` nos
mesmos casos em que `scalar_one_or_none()` levantaria, para nao mascarar dado
incoerente que as constraints `EXCLUDE` deveriam impedir. O resultado de
`resolver_jornada_do_dia` com e sem cache e, por construcao, identico (mesmos
ids, mesmas previsoes, portanto mesmo `hash_entrada` em `apurar_dia`).

**Escopo de validade:** uma unica execucao em lote, dentro de uma unica
sessao/transacao. Nunca guarde um `CacheResolucao` entre requisicoes ou entre
jobs -- ele nao enxerga escrita concorrente. Sem cache (default `None`), o
comportamento e byte a byte o de antes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from ponto_contracts import (
    Afastamento,
    Empresa,
    Escala,
    EscalaAtribuicao,
    EscalaCiclo,
    Feriado,
    Horario,
    Jornada,
    JornadaDia,
    Turno,
    Unidade,
    UnidadeFeriadoConjunto,
    Vinculo,
    VinculoJornada,
)
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario.feriados import resolver_data_feriado
from app.jornada.modelagem.escalas import posicao_do_ciclo
from app.jornada.modelagem.vinculo_jornadas import obter_vinculo
from app.schemas.contrato import ResolucaoJornada

CODIGO_SEM_REGRA = "PONTO-APUR-002"

#: `jornada_dias.tipo_dia` -> `ResolucaoJornada.tipoDia` (PCF secao 2:
#: "Mapeamento de tipo_dia para o tipoDia da resposta").
_MAPA_TIPO_DIA_JORNADA: dict[str, str] = {
    "util": "util",
    "dsr": "dsr",
    "folga": "folga",
    "compensado": "compensado",
    "facultativo": "ponto_facultativo",
}

#: `escala_ciclos.tipo_dia` -> `ResolucaoJornada.tipoDia`.
_MAPA_TIPO_DIA_ESCALA: dict[str, str] = {
    "trabalho": "util",
    "folga": "folga",
    "dsr": "dsr",
    "compensado": "compensado",
}

#: Tipos de `feriados.tipo` que sobrescrevem `tipoDia`/`origem`/carga da
#: resposta (PCF secao 2). `data_comemorativa` e `compensado` so preenchem
#: `feriadoId`/`feriadoNome`.
_TIPOS_FERIADO_QUE_SOBRESCREVEM: dict[str, str] = {
    "feriado": "feriado",
    "ponto_facultativo": "ponto_facultativo",
}

#: Prioridade de desempate quando mais de um feriado aplicavel cai na mesma
#: data (por exemplo nacional e municipal coincidindo) -- caso raro, sem
#: orientacao explicita no PCF; escolha documentada aqui: `feriado` vence
#: `ponto_facultativo`, que vence os tipos informativos.
_PRIORIDADE_TIPO_FERIADO: dict[str, int] = {
    "feriado": 0,
    "ponto_facultativo": 1,
    "data_comemorativa": 2,
    "compensado": 3,
}


@dataclass(slots=True)
class CacheResolucao:
    """Cache de vida curta das leituras invariantes por dia do resolvedor.

    Ver o bloco `CacheResolucao` no docstring do modulo para o porque, o
    escopo de validade e a garantia de equivalencia. Criado por quem chama em
    lote; nunca compartilhado entre sessoes/transacoes.
    """

    #: `vinculos` por `vinculo_id` (leitura de `obter_vinculo`).
    vinculos: dict[UUID, Vinculo] = field(default_factory=dict)
    #: Fuso efetivo ja resolvido, por `vinculo_id`.
    fusos: dict[UUID, str] = field(default_factory=dict)
    #: TODAS as `escala_atribuicoes` do vinculo (sem filtro de data).
    escala_atribuicoes: dict[UUID, list[EscalaAtribuicao]] = field(default_factory=dict)
    #: TODAS as `vinculo_jornadas` do vinculo (sem filtro de data).
    vinculo_jornadas: dict[UUID, list[VinculoJornada]] = field(default_factory=dict)
    escalas: dict[UUID, Escala | None] = field(default_factory=dict)
    #: `escala_ciclos` por `(escala_id, posicao)`.
    ciclos: dict[tuple[UUID, int], EscalaCiclo | None] = field(default_factory=dict)
    turnos: dict[UUID, Turno | None] = field(default_factory=dict)
    jornadas: dict[UUID, Jornada | None] = field(default_factory=dict)
    #: `jornada_dias` por `(jornada_id, dia_semana)`.
    jornada_dias: dict[tuple[UUID, int], JornadaDia | None] = field(default_factory=dict)
    horarios: dict[UUID, Horario | None] = field(default_factory=dict)
    #: Afastamentos aprovados/integrais/nao excluidos por `colaborador_id`,
    #: como `(id, data_inicio, data_fim)` -- nunca a linha inteira, para nao
    #: trazer `afastamentos.cid` (dado de saude) para a memoria do lote.
    afastamentos: dict[UUID, list[tuple[UUID, dt.date, dt.date | None]]] = field(
        default_factory=dict
    )
    #: `feriado_conjunto_id` aplicaveis por `unidade_id`.
    feriado_conjuntos: dict[UUID, list[UUID]] = field(default_factory=dict)
    #: Feriados candidatos por tupla ordenada de `feriado_conjunto_id`.
    feriados: dict[tuple[UUID, ...], list[Feriado]] = field(default_factory=dict)


async def obter_jornada(
    sessao: AsyncSession, jornada_id: UUID, cache: CacheResolucao | None
) -> Jornada | None:
    """`sessao.get(Jornada, ...)` memoizado. Publico dentro do pacote porque
    `app.apuracao.dominio.servico.apurar_dia` lê a MESMA jornada logo depois
    da resolucao (era a 2a leitura da mesma linha por dia apurado)."""
    if cache is None:
        return await sessao.get(Jornada, jornada_id)
    if jornada_id not in cache.jornadas:
        cache.jornadas[jornada_id] = await sessao.get(Jornada, jornada_id)
    return cache.jornadas[jornada_id]


def _unico(linhas: list[Any]) -> Any | None:
    """Equivalente em memoria de `scalar_one_or_none()`: `None` para nenhuma
    linha, a linha para exatamente uma, e a MESMA excecao do SQLAlchemy para
    mais de uma (dado incoerente que a constraint `EXCLUDE` deveria impedir
    nunca pode virar "escolhe a primeira" silenciosamente)."""
    if not linhas:
        return None
    if len(linhas) > 1:
        raise MultipleResultsFound("Multiple rows were found when exactly one or none was required")
    return linhas[0]


def _vigente_na_data(linhas: list[Any], data: dt.date) -> list[Any]:
    """Mesmo predicado do SQL: `vigencia_inicio <= data AND (vigencia_fim IS
    NULL OR vigencia_fim >= data)`."""
    return [
        linha
        for linha in linhas
        if linha.vigencia_inicio <= data
        and (linha.vigencia_fim is None or linha.vigencia_fim >= data)
    ]


async def resolver_jornada_do_dia(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    data: dt.date,
    *,
    cache: CacheResolucao | None = None,
) -> ResolucaoJornada:
    """Dado um vinculo e uma data, devolve a jornada/escala vigente, o
    horario previsto e o tipo do dia. Assinatura fixada no PCF da fase
    (secao 4) -- os quatro parametros posicionais nao mudam; `cache` e um
    parametro OPCIONAL somente-nomeado acrescentado por ADR-010 (ver
    docstring do modulo), inerte quando ausente.

    Vinculo de outro tenant, ou inexistente, responde `PONTO-REC-001` (via
    `obter_vinculo`, RLS ja restringe a consulta ao tenant corrente da
    sessao).
    """
    if cache is not None and vinculo_id in cache.vinculos:
        vinculo = cache.vinculos[vinculo_id]
    else:
        vinculo = await obter_vinculo(sessao, vinculo_id)
        if cache is not None:
            cache.vinculos[vinculo_id] = vinculo
    fuso_horario = await _fuso_efetivo(sessao, vinculo, cache)

    base = await _resolver_base_escala(sessao, vinculo_id, data, cache)
    if base is None:
        base = await _resolver_base_jornada(sessao, vinculo_id, data, cache)
    if base is None:
        raise ErroDeAplicacao(
            CODIGO_SEM_REGRA,
            detalhe="Nenhuma escala nem jornada vigente para o vinculo nesta data.",
            contexto_log={"vinculo_id": str(vinculo_id), "data": data.isoformat()},
        )

    horario: Horario | None = None
    if base["horario_id"] is not None:
        horario = await _obter_horario(sessao, base["horario_id"], cache)

    entrada_prevista, saida_prevista, cruza_meia_noite, intervalos = _montar_horario(
        horario, data, fuso_horario
    )

    tipo_dia = base["tipo_dia"]
    origem = base["origem"]
    carga_minutos = base["carga_minutos"]
    feriado_id: UUID | None = None
    feriado_nome: str | None = None
    afastamento_id: UUID | None = None

    afastamento_id = await _afastamento_vigente(
        sessao, tenant_id, vinculo.colaborador_id, data, cache
    )
    if afastamento_id is not None:
        tipo_dia = "afastamento"
        origem = "afastamento"
    else:
        feriado = await _feriado_aplicavel(sessao, tenant_id, vinculo.unidade_id, data, cache)
        if feriado is not None:
            feriado_id = feriado.id
            feriado_nome = feriado.nome
            tipo_dia_feriado = _TIPOS_FERIADO_QUE_SOBRESCREVEM.get(feriado.tipo)
            if tipo_dia_feriado is not None:
                tipo_dia = tipo_dia_feriado
                origem = "feriado"
                if not feriado.integral and feriado.carga_reduzida_minutos is not None:
                    carga_minutos = feriado.carga_reduzida_minutos

    # `ResolucaoJornada.model_validate` (nao o construtor direto): os campos
    # gerados do contrato tem `alias` camelCase e este modulo, como o resto
    # da base, escreve chaves em snake_case -- `populate_by_name=True` no
    # modelo aceita as duas, mas so `model_validate` (nao `__init__`) e
    # visivel para o mypy sem o plugin do pydantic (nao configurado neste
    # projeto), que e o mesmo motivo de nenhum outro router construir um
    # schema gerado por kwargs diretos.
    return ResolucaoJornada.model_validate(
        {
            "vinculo_id": vinculo.id,
            "colaborador_id": vinculo.colaborador_id,
            "data": data,
            "tipo_dia": tipo_dia,
            "jornada_id": base["jornada_id"],
            "jornada_codigo": base["jornada_codigo"],
            "escala_id": base["escala_id"],
            "posicao_ciclo": base["posicao_ciclo"],
            "turno_id": base["turno_id"],
            "horario_id": base["horario_id"],
            "entrada_prevista": entrada_prevista,
            "saida_prevista": saida_prevista,
            "intervalos_previstos": intervalos,
            "carga_prevista_minutos": carga_minutos,
            "cruza_meia_noite": cruza_meia_noite,
            "feriado_id": feriado_id,
            "feriado_nome": feriado_nome,
            "afastamento_id": afastamento_id,
            "fuso_horario": fuso_horario,
            "origem": origem,
        }
    )


async def _obter_horario(
    sessao: AsyncSession, horario_id: UUID, cache: CacheResolucao | None
) -> Horario | None:
    if cache is None:
        return await sessao.get(Horario, horario_id)
    if horario_id not in cache.horarios:
        cache.horarios[horario_id] = await sessao.get(Horario, horario_id)
    return cache.horarios[horario_id]


async def _fuso_efetivo(
    sessao: AsyncSession, vinculo: Vinculo, cache: CacheResolucao | None = None
) -> str:
    """Fuso efetivo da resolucao (ADR-004: a data civil da apuracao deriva
    do fuso da unidade do vinculo). `vinculos.unidade_id` e opcional no
    schema: **sem unidade, use `empresas.fuso_horario` do vinculo como fuso
    efetivo e trate o vinculo como sem nenhum `feriado_conjunto` aplicavel**
    (decisao fixada no PCF da F3, secao 2, documentada aqui com a frase
    exata do PCF para que ninguem a redescubra por tentativa e erro).
    """
    if cache is not None and vinculo.id in cache.fusos:
        return cache.fusos[vinculo.id]
    fuso = await _fuso_efetivo_do_banco(sessao, vinculo)
    if cache is not None:
        cache.fusos[vinculo.id] = fuso
    return fuso


async def _fuso_efetivo_do_banco(sessao: AsyncSession, vinculo: Vinculo) -> str:
    if vinculo.unidade_id is not None:
        unidade = await sessao.get(Unidade, vinculo.unidade_id)
        if unidade is not None:
            return str(unidade.fuso_horario)
    empresa = await sessao.get(Empresa, vinculo.empresa_id)
    if empresa is None:
        # Nunca deveria acontecer: `vinculos.empresa_id` e FK RESTRICT NOT
        # NULL. Defensivo, nao 500 -- cai no fuso padrao do domínio
        # (`dom_fuso`), a mesma default de `empresas.fuso_horario`.
        return "America/Sao_Paulo"
    return str(empresa.fuso_horario)


async def _resolver_base_escala(
    sessao: AsyncSession, vinculo_id: UUID, data: dt.date, cache: CacheResolucao | None = None
) -> dict[str, Any] | None:
    """Passo 1 da precedencia: `escala_atribuicoes` vigente na `data`.

    A constraint `EXCLUDE` (`ex_escala_atribuicoes_sobreposicao`) garante que
    esta consulta devolve no maximo uma linha (PCF secao 2).
    """
    if cache is None:
        resultado = await sessao.execute(
            select(EscalaAtribuicao).where(
                EscalaAtribuicao.vinculo_id == vinculo_id,
                EscalaAtribuicao.vigencia_inicio <= data,
                sa.or_(
                    EscalaAtribuicao.vigencia_fim.is_(None),
                    EscalaAtribuicao.vigencia_fim >= data,
                ),
            )
        )
        atribuicao = resultado.scalar_one_or_none()
    else:
        if vinculo_id not in cache.escala_atribuicoes:
            cache.escala_atribuicoes[vinculo_id] = list(
                (
                    await sessao.execute(
                        select(EscalaAtribuicao).where(EscalaAtribuicao.vinculo_id == vinculo_id)
                    )
                )
                .scalars()
                .all()
            )
        atribuicao = _unico(_vigente_na_data(cache.escala_atribuicoes[vinculo_id], data))
    if atribuicao is None:
        return None

    escala = await _obter_escala(sessao, atribuicao.escala_id, cache)
    if escala is None:
        # Nunca deveria acontecer: `escala_atribuicoes.escala_id` e FK
        # RESTRICT NOT NULL. Defensivo, nao 500.
        return None

    posicao = posicao_do_ciclo(escala, atribuicao, data)
    ciclo = await _obter_ciclo(sessao, escala.id, posicao, cache)
    if ciclo is None:
        # T3 valida cobertura completa das posicoes na criacao; chegar aqui
        # sem ciclo e defensivo (dado incoerente escapou da validacao). Trata
        # como "sem regra para o dia" em vez de 500 -- nunca 500, nunca
        # resultado inventado (PCF, criterio de aceite 10).
        return None

    horario_id: UUID | None = None
    if ciclo.turno_id is not None:
        turno = await _obter_turno(sessao, ciclo.turno_id, cache)
        if turno is not None:
            horario_id = turno.horario_id

    jornada_codigo: str | None = None
    if escala.jornada_id is not None:
        jornada = await obter_jornada(sessao, escala.jornada_id, cache)
        if jornada is not None:
            jornada_codigo = jornada.codigo

    return {
        "jornada_id": escala.jornada_id,
        "jornada_codigo": jornada_codigo,
        "escala_id": escala.id,
        "posicao_ciclo": posicao,
        "turno_id": ciclo.turno_id,
        "horario_id": horario_id,
        "tipo_dia": _MAPA_TIPO_DIA_ESCALA[ciclo.tipo_dia],
        "carga_minutos": ciclo.carga_minutos,
        "origem": "escala",
    }


async def _obter_escala(
    sessao: AsyncSession, escala_id: UUID, cache: CacheResolucao | None
) -> Escala | None:
    if cache is None:
        return await sessao.get(Escala, escala_id)
    if escala_id not in cache.escalas:
        cache.escalas[escala_id] = await sessao.get(Escala, escala_id)
    return cache.escalas[escala_id]


async def _obter_turno(
    sessao: AsyncSession, turno_id: UUID, cache: CacheResolucao | None
) -> Turno | None:
    if cache is None:
        return await sessao.get(Turno, turno_id)
    if turno_id not in cache.turnos:
        cache.turnos[turno_id] = await sessao.get(Turno, turno_id)
    return cache.turnos[turno_id]


async def _obter_ciclo(
    sessao: AsyncSession, escala_id: UUID, posicao: int, cache: CacheResolucao | None
) -> EscalaCiclo | None:
    chave = (escala_id, posicao)
    if cache is not None and chave in cache.ciclos:
        return cache.ciclos[chave]
    ciclo = (
        await sessao.execute(
            select(EscalaCiclo).where(
                EscalaCiclo.escala_id == escala_id, EscalaCiclo.posicao == posicao
            )
        )
    ).scalar_one_or_none()
    if cache is not None:
        cache.ciclos[chave] = ciclo
    return ciclo


async def _obter_jornada_dia(
    sessao: AsyncSession, jornada_id: UUID, dia_semana: int, cache: CacheResolucao | None
) -> JornadaDia | None:
    chave = (jornada_id, dia_semana)
    if cache is not None and chave in cache.jornada_dias:
        return cache.jornada_dias[chave]
    jornada_dia = (
        await sessao.execute(
            select(JornadaDia).where(
                JornadaDia.jornada_id == jornada_id, JornadaDia.dia_semana == dia_semana
            )
        )
    ).scalar_one_or_none()
    if cache is not None:
        cache.jornada_dias[chave] = jornada_dia
    return jornada_dia


async def _resolver_base_jornada(
    sessao: AsyncSession, vinculo_id: UUID, data: dt.date, cache: CacheResolucao | None = None
) -> dict[str, Any] | None:
    """Passo 2 da precedencia: `vinculo_jornadas` vigente na `data`, dia
    resolvido por `jornada_dias` indexado pelo dia da semana (`0` domingo ..
    `6` sabado -- `date.isoweekday() % 7`: Python usa 1=segunda..7=domingo,
    entao `% 7` leva domingo a 0 e preserva segunda..sabado como 1..6).
    """
    if cache is None:
        resultado = await sessao.execute(
            select(VinculoJornada).where(
                VinculoJornada.vinculo_id == vinculo_id,
                VinculoJornada.vigencia_inicio <= data,
                sa.or_(VinculoJornada.vigencia_fim.is_(None), VinculoJornada.vigencia_fim >= data),
            )
        )
        atribuicao = resultado.scalar_one_or_none()
    else:
        if vinculo_id not in cache.vinculo_jornadas:
            cache.vinculo_jornadas[vinculo_id] = list(
                (
                    await sessao.execute(
                        select(VinculoJornada).where(VinculoJornada.vinculo_id == vinculo_id)
                    )
                )
                .scalars()
                .all()
            )
        atribuicao = _unico(_vigente_na_data(cache.vinculo_jornadas[vinculo_id], data))
    if atribuicao is None:
        return None

    jornada = await obter_jornada(sessao, atribuicao.jornada_id, cache)
    if jornada is None:
        # Nunca deveria acontecer: `vinculo_jornadas.jornada_id` e FK
        # RESTRICT NOT NULL. Defensivo, nao 500.
        return None

    dia_semana = data.isoweekday() % 7
    jornada_dia = await _obter_jornada_dia(sessao, jornada.id, dia_semana, cache)
    if jornada_dia is None:
        # Jornada vigente mas sem desdobramento para este dia da semana:
        # tratado como sem regra para o dia (nunca 500, nunca resultado
        # inventado -- PCF, criterio de aceite 10).
        return None

    return {
        "jornada_id": jornada.id,
        "jornada_codigo": jornada.codigo,
        "escala_id": None,
        "posicao_ciclo": None,
        "turno_id": None,
        "horario_id": jornada_dia.horario_id,
        "tipo_dia": _MAPA_TIPO_DIA_JORNADA[jornada_dia.tipo_dia],
        "carga_minutos": jornada_dia.carga_minutos,
        "origem": "jornada",
    }


async def _afastamento_vigente(
    sessao: AsyncSession,
    tenant_id: UUID,
    colaborador_id: UUID,
    data: dt.date,
    cache: CacheResolucao | None = None,
) -> UUID | None:
    """Afastamento aprovado, integral, cobrindo a `data`, do colaborador do
    vinculo (PCF secao 2, passo 1 da sobreposicao). A constraint `EXCLUDE`
    (`ex_afastamentos_sobreposicao`) garante no maximo um afastamento integral
    aprovado por dia.

    Seleciona **so** `Afastamento.id`: nunca le `afastamentos.cid` aqui --
    esse campo e dado de saude e so pode ser lido atras de
    `Depends(exigir_permissao("afastamentos.ler"))` (T6 de A2), que grava
    `acessos_dados_sensiveis` sozinho. O resolvedor exige apenas
    `jornadas.ler` e nao deve disparar esse registro.
    """
    if cache is None:
        resultado = await sessao.execute(
            select(Afastamento.id).where(
                Afastamento.tenant_id == tenant_id,
                Afastamento.colaborador_id == colaborador_id,
                Afastamento.status == "aprovado",
                Afastamento.periodo_parcial.is_(False),
                Afastamento.excluido_em.is_(None),
                Afastamento.data_inicio <= data,
                sa.or_(Afastamento.data_fim.is_(None), Afastamento.data_fim >= data),
            )
        )
        return resultado.scalar_one_or_none()

    if colaborador_id not in cache.afastamentos:
        linhas = (
            await sessao.execute(
                select(Afastamento.id, Afastamento.data_inicio, Afastamento.data_fim).where(
                    Afastamento.tenant_id == tenant_id,
                    Afastamento.colaborador_id == colaborador_id,
                    Afastamento.status == "aprovado",
                    Afastamento.periodo_parcial.is_(False),
                    Afastamento.excluido_em.is_(None),
                )
            )
        ).all()
        cache.afastamentos[colaborador_id] = [(linha[0], linha[1], linha[2]) for linha in linhas]
    aplicaveis = [
        item
        for item in cache.afastamentos[colaborador_id]
        if item[1] <= data and (item[2] is None or item[2] >= data)
    ]
    encontrado = _unico(aplicaveis)
    return encontrado[0] if encontrado is not None else None


async def _feriado_aplicavel(
    sessao: AsyncSession,
    tenant_id: UUID,
    unidade_id: UUID | None,
    data: dt.date,
    cache: CacheResolucao | None = None,
) -> Feriado | None:
    """Feriado aplicavel a unidade do vinculo nesta `data`, ou `None`.

    Sem `unidade_id` (vinculo sem unidade), **nao ha nenhum feriado_conjunto
    aplicavel** -- mesma decisao documentada em `_fuso_efetivo`. Resolve
    moveis pelo ano da `data` consultada via `resolver_data_feriado`
    (reaproveitada de `app.jornada.calendario.feriados`, que ja encapsula
    `resolver_ancora_movel` e o tratamento de `feriados.ano`).
    """
    if unidade_id is None:
        return None

    if cache is not None and unidade_id in cache.feriado_conjuntos:
        conjunto_ids = cache.feriado_conjuntos[unidade_id]
    else:
        conjunto_ids_resultado = await sessao.execute(
            select(UnidadeFeriadoConjunto.feriado_conjunto_id).where(
                UnidadeFeriadoConjunto.tenant_id == tenant_id,
                UnidadeFeriadoConjunto.unidade_id == unidade_id,
            )
        )
        conjunto_ids = list(conjunto_ids_resultado.scalars().all())
        if cache is not None:
            cache.feriado_conjuntos[unidade_id] = conjunto_ids
    if not conjunto_ids:
        return None

    chave_feriados = tuple(conjunto_ids)
    if cache is not None and chave_feriados in cache.feriados:
        candidatos = cache.feriados[chave_feriados]
    else:
        candidatos_resultado = await sessao.execute(
            select(Feriado).where(
                Feriado.tenant_id == tenant_id,
                Feriado.feriado_conjunto_id.in_(conjunto_ids),
            )
        )
        candidatos = list(candidatos_resultado.scalars().all())
        if cache is not None:
            cache.feriados[chave_feriados] = candidatos

    aplicaveis = [f for f in candidatos if resolver_data_feriado(f, data.year) == data]
    if not aplicaveis:
        return None

    aplicaveis.sort(key=lambda f: (_PRIORIDADE_TIPO_FERIADO.get(f.tipo, 9), str(f.id)))
    return aplicaveis[0]


def _montar_horario(
    horario: Horario | None, data: dt.date, fuso: str
) -> tuple[dt.datetime | None, dt.datetime | None, bool, dict[str, Any] | None]:
    """Entrada/saida previstas no fuso efetivo (ADR-004), intervalos
    previstos e a flag `cruzaMeiaNoite`. Sem horario (dia de folga/DSR sem
    turno, por exemplo), tudo fica `None`/`False`.
    """
    if horario is None:
        return None, None, False, None

    cruza_meia_noite = bool(horario.cruza_meia_noite)
    if horario.entrada is None or horario.saida is None:
        return None, None, cruza_meia_noite, None

    zona = ZoneInfo(fuso)
    entrada_prevista = dt.datetime.combine(data, horario.entrada, tzinfo=zona)
    data_saida = data + dt.timedelta(days=1) if cruza_meia_noite else data
    saida_prevista = dt.datetime.combine(data_saida, horario.saida, tzinfo=zona)

    intervalos: list[dict[str, Any]] = []
    if horario.intervalo_inicio is not None and horario.intervalo_fim is not None:
        minutos = horario.duracao_intervalo_minutos
        if minutos is None:
            inicio_dt = dt.datetime.combine(data, horario.intervalo_inicio)
            fim_dt = dt.datetime.combine(data, horario.intervalo_fim)
            if fim_dt < inicio_dt:
                fim_dt += dt.timedelta(days=1)
            minutos = int((fim_dt - inicio_dt).total_seconds() // 60)
        intervalos.append(
            {
                "inicio": horario.intervalo_inicio.isoformat(timespec="minutes"),
                "fim": horario.intervalo_fim.isoformat(timespec="minutes"),
                "minutos": minutos,
            }
        )
    if isinstance(horario.intervalos_extras, dict):
        extras = horario.intervalos_extras.get("intervalos")
        if isinstance(extras, list):
            intervalos.extend(extras)

    intervalos_previstos = {"intervalos": intervalos} if intervalos else None
    return entrada_prevista, saida_prevista, cruza_meia_noite, intervalos_previstos
