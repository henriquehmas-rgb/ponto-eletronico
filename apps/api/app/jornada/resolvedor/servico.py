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
"""

from __future__ import annotations

import datetime as dt
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


async def resolver_jornada_do_dia(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, data: dt.date
) -> ResolucaoJornada:
    """Dado um vinculo e uma data, devolve a jornada/escala vigente, o
    horario previsto e o tipo do dia. Assinatura fixada no PCF da fase
    (secao 4) -- mudar exige atualizar rota, golden dataset e testes no
    mesmo commit.

    Vinculo de outro tenant, ou inexistente, responde `PONTO-REC-001` (via
    `obter_vinculo`, RLS ja restringe a consulta ao tenant corrente da
    sessao).
    """
    vinculo = await obter_vinculo(sessao, vinculo_id)
    fuso_horario = await _fuso_efetivo(sessao, vinculo)

    base = await _resolver_base_escala(sessao, vinculo_id, data)
    if base is None:
        base = await _resolver_base_jornada(sessao, vinculo_id, data)
    if base is None:
        raise ErroDeAplicacao(
            CODIGO_SEM_REGRA,
            detalhe="Nenhuma escala nem jornada vigente para o vinculo nesta data.",
            contexto_log={"vinculo_id": str(vinculo_id), "data": data.isoformat()},
        )

    horario: Horario | None = None
    if base["horario_id"] is not None:
        horario = await sessao.get(Horario, base["horario_id"])

    entrada_prevista, saida_prevista, cruza_meia_noite, intervalos = _montar_horario(
        horario, data, fuso_horario
    )

    tipo_dia = base["tipo_dia"]
    origem = base["origem"]
    carga_minutos = base["carga_minutos"]
    feriado_id: UUID | None = None
    feriado_nome: str | None = None
    afastamento_id: UUID | None = None

    afastamento_id = await _afastamento_vigente(sessao, tenant_id, vinculo.colaborador_id, data)
    if afastamento_id is not None:
        tipo_dia = "afastamento"
        origem = "afastamento"
    else:
        feriado = await _feriado_aplicavel(sessao, tenant_id, vinculo.unidade_id, data)
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


async def _fuso_efetivo(sessao: AsyncSession, vinculo: Vinculo) -> str:
    """Fuso efetivo da resolucao (ADR-004: a data civil da apuracao deriva
    do fuso da unidade do vinculo). `vinculos.unidade_id` e opcional no
    schema: **sem unidade, use `empresas.fuso_horario` do vinculo como fuso
    efetivo e trate o vinculo como sem nenhum `feriado_conjunto` aplicavel**
    (decisao fixada no PCF da F3, secao 2, documentada aqui com a frase
    exata do PCF para que ninguem a redescubra por tentativa e erro).
    """
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
    sessao: AsyncSession, vinculo_id: UUID, data: dt.date
) -> dict[str, Any] | None:
    """Passo 1 da precedencia: `escala_atribuicoes` vigente na `data`.

    A constraint `EXCLUDE` (`ex_escala_atribuicoes_sobreposicao`) garante que
    esta consulta devolve no maximo uma linha (PCF secao 2).
    """
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
    if atribuicao is None:
        return None

    escala = await sessao.get(Escala, atribuicao.escala_id)
    if escala is None:
        # Nunca deveria acontecer: `escala_atribuicoes.escala_id` e FK
        # RESTRICT NOT NULL. Defensivo, nao 500.
        return None

    posicao = posicao_do_ciclo(escala, atribuicao, data)
    ciclo_resultado = await sessao.execute(
        select(EscalaCiclo).where(
            EscalaCiclo.escala_id == escala.id, EscalaCiclo.posicao == posicao
        )
    )
    ciclo = ciclo_resultado.scalar_one_or_none()
    if ciclo is None:
        # T3 valida cobertura completa das posicoes na criacao; chegar aqui
        # sem ciclo e defensivo (dado incoerente escapou da validacao). Trata
        # como "sem regra para o dia" em vez de 500 -- nunca 500, nunca
        # resultado inventado (PCF, criterio de aceite 10).
        return None

    horario_id: UUID | None = None
    if ciclo.turno_id is not None:
        turno = await sessao.get(Turno, ciclo.turno_id)
        if turno is not None:
            horario_id = turno.horario_id

    jornada_codigo: str | None = None
    if escala.jornada_id is not None:
        jornada = await sessao.get(Jornada, escala.jornada_id)
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


async def _resolver_base_jornada(
    sessao: AsyncSession, vinculo_id: UUID, data: dt.date
) -> dict[str, Any] | None:
    """Passo 2 da precedencia: `vinculo_jornadas` vigente na `data`, dia
    resolvido por `jornada_dias` indexado pelo dia da semana (`0` domingo ..
    `6` sabado -- `date.isoweekday() % 7`: Python usa 1=segunda..7=domingo,
    entao `% 7` leva domingo a 0 e preserva segunda..sabado como 1..6).
    """
    resultado = await sessao.execute(
        select(VinculoJornada).where(
            VinculoJornada.vinculo_id == vinculo_id,
            VinculoJornada.vigencia_inicio <= data,
            sa.or_(VinculoJornada.vigencia_fim.is_(None), VinculoJornada.vigencia_fim >= data),
        )
    )
    atribuicao = resultado.scalar_one_or_none()
    if atribuicao is None:
        return None

    jornada = await sessao.get(Jornada, atribuicao.jornada_id)
    if jornada is None:
        # Nunca deveria acontecer: `vinculo_jornadas.jornada_id` e FK
        # RESTRICT NOT NULL. Defensivo, nao 500.
        return None

    dia_semana = data.isoweekday() % 7
    dia_resultado = await sessao.execute(
        select(JornadaDia).where(
            JornadaDia.jornada_id == jornada.id, JornadaDia.dia_semana == dia_semana
        )
    )
    jornada_dia = dia_resultado.scalar_one_or_none()
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
    sessao: AsyncSession, tenant_id: UUID, colaborador_id: UUID, data: dt.date
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


async def _feriado_aplicavel(
    sessao: AsyncSession, tenant_id: UUID, unidade_id: UUID | None, data: dt.date
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

    conjunto_ids_resultado = await sessao.execute(
        select(UnidadeFeriadoConjunto.feriado_conjunto_id).where(
            UnidadeFeriadoConjunto.tenant_id == tenant_id,
            UnidadeFeriadoConjunto.unidade_id == unidade_id,
        )
    )
    conjunto_ids = list(conjunto_ids_resultado.scalars().all())
    if not conjunto_ids:
        return None

    candidatos_resultado = await sessao.execute(
        select(Feriado).where(
            Feriado.tenant_id == tenant_id,
            Feriado.feriado_conjunto_id.in_(conjunto_ids),
        )
    )
    candidatos = list(candidatos_resultado.scalars().all())

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
