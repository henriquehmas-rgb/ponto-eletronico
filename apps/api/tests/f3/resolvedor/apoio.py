"""Apoio de teste do resolvedor (F3 / A3, ownership exclusivo de
`tests/f3/resolvedor/**`).

Cria massa de dados chamando os servicos REAIS de A1 (`app.jornada.modelagem`)
e A2 (`app.jornada.calendario`) -- nunca `INSERT` cru -- para o resolvedor ser
exercitado contra o mesmo caminho que a API usa. Nao e um golden dataset (isso
e T8, ownership de A4): sao helpers de massa de dados para os testes desta
pasta, que provam o comportamento do resolvedor descrito no PCF (secao 6, T7).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from ponto_contracts import (
    Afastamento,
    Escala,
    EscalaAtribuicao,
    FeriadoConjunto,
    Horario,
    Jornada,
    TipoAfastamento,
    Turno,
    VinculoJornada,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.calendario import afastamentos as servico_afastamentos
from app.jornada.calendario import feriados as servico_feriados
from app.jornada.modelagem import escala_atribuicoes as servico_escala_atribuicoes
from app.jornada.modelagem import escalas as servico_escalas
from app.jornada.modelagem import horarios as servico_horarios
from app.jornada.modelagem import jornadas as servico_jornadas
from app.jornada.modelagem import turnos as servico_turnos
from app.jornada.modelagem import vinculo_jornadas as servico_vinculo_jornadas
from app.schemas import contrato as esquemas


async def criar_horario(
    sessao: AsyncSession,
    tenant_id: UUID,
    empresa_id: UUID,
    *,
    codigo: str,
    carga_minutos: int,
    entrada: str | None = None,
    saida: str | None = None,
    cruza_meia_noite: bool = False,
    intervalo_inicio: str | None = None,
    intervalo_fim: str | None = None,
) -> Horario:
    corpo = esquemas.HorarioCriar(
        empresa_id=empresa_id,
        codigo=codigo,
        nome=codigo,
        entrada=entrada,
        saida=saida,
        intervalo_inicio=intervalo_inicio,
        intervalo_fim=intervalo_fim,
        cruza_meia_noite=cruza_meia_noite,
        carga_minutos=carga_minutos,
    )
    return await servico_horarios.criar_horario(sessao, tenant_id, corpo)


async def criar_jornada_fixa_semanal(
    sessao: AsyncSession,
    tenant_id: UUID,
    empresa_id: UUID,
    *,
    codigo: str,
    horario_util_id: UUID,
    carga_minutos_util: int,
    vigencia_inicio: dt.date,
    vigencia_fim: dt.date | None = None,
    dia_dsr: int = 0,
) -> Jornada:
    """Jornada fixa com `horario_util_id` de segunda a sabado (exceto
    `dia_dsr`, padrao domingo=0, que e DSR sem horario previsto)."""
    dias = [
        esquemas.JornadaDia(
            dia_semana=d,
            tipo_dia=esquemas.TipoDia.dsr if d == dia_dsr else esquemas.TipoDia.util,
            horario_id=None if d == dia_dsr else horario_util_id,
            carga_minutos=0 if d == dia_dsr else carga_minutos_util,
        )
        for d in range(7)
    ]
    corpo = esquemas.JornadaCriar(
        empresa_id=empresa_id,
        codigo=codigo,
        nome=codigo,
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
        dias=dias,
    )
    return await servico_jornadas.criar_jornada(sessao, tenant_id, corpo)


async def atribuir_jornada(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    jornada_id: UUID,
    *,
    vigencia_inicio: dt.date,
    vigencia_fim: dt.date | None = None,
) -> VinculoJornada:
    corpo = esquemas.VinculoJornadaCriar(
        vinculo_id=vinculo_id,
        jornada_id=jornada_id,
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
    )
    return await servico_vinculo_jornadas.atribuir_jornada_vinculo(
        sessao, tenant_id, vinculo_id, corpo
    )


async def encerrar_vigencia_jornada(
    sessao: AsyncSession, atribuicao: VinculoJornada, vigencia_fim: dt.date
) -> None:
    """Fecha a vigencia de uma atribuicao ja gravada, direto no ORM (nao ha
    `atualizarJornadaVinculo` no contrato -- so `atribuirJornadaVinculo`).
    Simula a troca de jornada no meio do mes (PCF, criterio de aceite 4)."""
    atribuicao.vigencia_fim = vigencia_fim
    await sessao.flush()


async def criar_turno(
    sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID, *, codigo: str, horario_id: UUID | None
) -> Turno:
    corpo = esquemas.TurnoCriar(
        empresa_id=empresa_id, codigo=codigo, nome=codigo, horario_id=horario_id
    )
    return await servico_turnos.criar_turno(sessao, tenant_id, corpo)


async def criar_escala_12x36(
    sessao: AsyncSession,
    tenant_id: UUID,
    empresa_id: UUID,
    *,
    codigo: str,
    turno_trabalho_id: UUID,
    data_referencia: dt.date,
    carga_trabalho_minutos: int,
) -> Escala:
    corpo = esquemas.EscalaCriar(
        empresa_id=empresa_id,
        codigo=codigo,
        nome=codigo,
        tipo=esquemas.Tipo20.field_12x36,
        dias_ciclo=2,
        data_referencia=data_referencia,
        ciclos=[
            esquemas.EscalaCiclo(
                posicao=1,
                turno_id=turno_trabalho_id,
                tipo_dia=esquemas.TipoDia1.trabalho,
                carga_minutos=carga_trabalho_minutos,
            ),
            esquemas.EscalaCiclo(
                posicao=2, turno_id=None, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0
            ),
        ],
    )
    return await servico_escalas.criar_escala(sessao, tenant_id, corpo)


async def atribuir_escala(
    sessao: AsyncSession,
    tenant_id: UUID,
    escala_id: UUID,
    vinculo_id: UUID,
    *,
    vigencia_inicio: dt.date,
    posicao_inicial: int = 1,
    vigencia_fim: dt.date | None = None,
) -> EscalaAtribuicao:
    corpo = esquemas.EscalaAtribuicaoCriar(
        vinculo_id=vinculo_id,
        posicao_inicial=posicao_inicial,
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
    )
    return await servico_escala_atribuicoes.atribuir_escala_vinculo(
        sessao, tenant_id, escala_id, corpo
    )


async def criar_feriado_conjunto_municipal(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    codigo: str,
    codigo_ibge: str,
    unidade_ids: list[UUID],
) -> FeriadoConjunto:
    corpo = esquemas.FeriadoConjuntoCriar(
        codigo=codigo,
        nome=codigo,
        abrangencia=esquemas.Abrangencia.municipal,
        codigo_ibge_municipio=codigo_ibge,
        unidade_ids=unidade_ids,
    )
    return await servico_feriados.criar_feriado_conjunto(sessao, tenant_id, corpo)


async def criar_feriado_fixo(
    sessao: AsyncSession,
    tenant_id: UUID,
    conjunto_id: UUID,
    *,
    nome: str,
    data: dt.date,
    tipo: str = "feriado",
    integral: bool = True,
    carga_reduzida_minutos: int | None = None,
) -> None:
    corpo = esquemas.FeriadoCriar(
        feriado_conjunto_id=conjunto_id,
        nome=nome,
        data=data,
        movel=False,
        tipo=tipo,  # type: ignore[arg-type]
        integral=integral,
        carga_reduzida_minutos=carga_reduzida_minutos,
    )
    await servico_feriados.criar_feriado(sessao, tenant_id, corpo)


async def criar_tipo_afastamento(
    sessao: AsyncSession, tenant_id: UUID, *, codigo: str, categoria: str = "ferias"
) -> TipoAfastamento:
    corpo = esquemas.TipoAfastamentoCriar(codigo=codigo, nome=codigo, categoria=categoria)  # type: ignore[arg-type]
    return await servico_afastamentos.criar_tipo_afastamento(sessao, tenant_id, corpo)


async def criar_afastamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID,
    tipo_afastamento_id: UUID,
    data_inicio: dt.date,
    data_fim: dt.date | None = None,
    status: str = "aprovado",
) -> Afastamento:
    corpo = esquemas.AfastamentoCriar(
        colaborador_id=colaborador_id,
        tipo_afastamento_id=tipo_afastamento_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status,  # type: ignore[arg-type]
    )
    return await servico_afastamentos.criar_afastamento(sessao, tenant_id, corpo)
