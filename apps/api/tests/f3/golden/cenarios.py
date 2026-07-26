"""Golden dataset da F3 (T8, agente A4): 40+ cenarios trabalhistas.

Escrito **antes** do resolvedor existir (`app.jornada.resolvedor.servico`,
A3/T7) -- e a razao de existir deste modulo separado de `test_cenarios.py`:
aqui so ha dado (massa de dados + resultado esperado calculado a mao contra
a formula fixada na secao 2 do PCF), nenhuma chamada ao resolvedor. Quem
executa e compara e `test_cenarios.py`.

Cada cenario cobre uma linha do PCF (T8): jornada fixa/flexivel/livre/
parcial/intermitente/teletrabalho/motorista, escalas 5x2/6x1/4x2/12x36/
espanhola/rotativa, troca de jornada respeitando vigencia, feriado nacional/
estadual/municipal/movel, ponto facultativo, afastamento integral/parcial e
vinculo sem regra (`PONTO-APUR-002`).

Convencoes usadas em todo o arquivo:

* Datas de referencia em 2025 (ano sem particularidade de calendario), exceto
  os feriados moveis, que cobrem 2024 E 2025 (criterio de aceite 6 do PCF
  exige pelo menos dois anos para as cinco ancoras).
* `dia_semana` no banco segue `schema.sql`: 0 domingo .. 6 sabado (comentario
  da coluna `jornada_dias.dia_semana`, conferido em
  `packages/contracts/schema.sql:1496`).
* A posicao do ciclo das escalas e sempre calculada por
  `_construtores.posicao_do_ciclo` (mesma formula do PCF, implementacao
  PROPRIA e independente da de A1/A3) -- nunca hardcoded a mao, para nao
  arriscar erro de transcricao na conta.
* Fuso: `America/Sao_Paulo` (unidade SP e a empresa) e `America/Bahia`
  (unidade BA) -- ambos UTC-3 o ano inteiro (Brasil nao usa horario de verao
  desde 2019), o que simplifica a conta de `entradaPrevista`/`saidaPrevista`
  sem que isso mascare bug de fuso: os cenarios de jornada nao ciclica
  (`_montar_jornada_tipo_dia_util`, compartilhada por fixa/flexivel/livre/
  parcial/intermitente/teletrabalho/motorista) afirmam `entradaPrevista`/
  `saidaPrevista` com `tzinfo` explicito via `zoneinfo`, nunca via offset
  numerico solto.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from tests.f3.conftest import ContextoF3
from tests.f3.golden import _construtores as c
from tests.f3.golden.formato import Cenario, Montagem, MontarMassa

FUSO_SP = ZoneInfo("America/Sao_Paulo")
FUSO_BA = ZoneInfo("America/Bahia")

_ENTRADA_PADRAO = _dt.time(8, 0)
_SAIDA_PADRAO = _dt.time(17, 0)
_INTERVALO_INICIO_PADRAO = _dt.time(12, 0)
_INTERVALO_FIM_PADRAO = _dt.time(13, 0)
_CARGA_PADRAO_MINUTOS = 480  # 8h

_VIGENCIA_ANTIGA = _dt.date(2023, 1, 1)

# Mapa de tipo_dia de escala_ciclos -> tipoDia da resposta (secao 2 do PCF).
# `jornada_dias.tipo_dia` nao precisa do mapa equivalente aqui: cada cenario
# de jornada ja escreve o `tipoDia` esperado explicitamente (a correspondencia
# e 1:1 exceto por 'facultativo' -> 'ponto_facultativo', ja documentada em
# `_montar_ponto_facultativo`).
_MAPA_TIPO_DIA_ESCALA = {
    "trabalho": "util",
    "folga": "folga",
    "dsr": "dsr",
    "compensado": "compensado",
}


# =============================================================================
# 1. Jornadas nao ciclicas: fixa, flexivel, livre, parcial, intermitente,
#    teletrabalho, motorista (T2) -- cada tipo so precisa gravar o `tipo`
#    correto (nenhuma logica especial), por isso um unico monta-cenario
#    parametrizado por `tipo`.
# =============================================================================
async def _montar_jornada_tipo_dia_util(
    sessao: AsyncSession, contexto: ContextoF3, *, tipo: str, codigo: str
) -> Montagem:
    jornada_id, horario_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo=codigo,
        nome=f"Jornada {tipo}",
        tipo=tipo,
        vigencia_inicio=_VIGENCIA_ANTIGA,
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=_CARGA_PADRAO_MINUTOS,
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_VIGENCIA_ANTIGA,
    )
    data_consulta = _dt.date(2025, 1, 6)  # segunda-feira
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=data_consulta,
        esperado={
            "tipo_dia": "util",
            "origem": "jornada",
            "jornada_id": jornada_id,
            "jornada_codigo": codigo,
            "horario_id": horario_id,
            "carga_prevista_minutos": _CARGA_PADRAO_MINUTOS,
            "cruza_meia_noite": False,
            "fuso_horario": "America/Sao_Paulo",
            "entrada_prevista": _dt.datetime(2025, 1, 6, 8, 0, tzinfo=FUSO_SP),
            "saida_prevista": _dt.datetime(2025, 1, 6, 17, 0, tzinfo=FUSO_SP),
        },
    )


async def _montar_jornada_fixa_dia_util(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(sessao, contexto, tipo="fixa", codigo="JOR-FIXA")


async def _montar_jornada_fixa_dia_dsr(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    jornada_id, horario_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-FIXA-DSR",
        nome="Jornada fixa (DSR)",
        tipo="fixa",
        vigencia_inicio=_VIGENCIA_ANTIGA,
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=_CARGA_PADRAO_MINUTOS,
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_VIGENCIA_ANTIGA,
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 5),  # domingo (dow 0)
        esperado={"tipo_dia": "dsr", "origem": "jornada", "jornada_id": jornada_id},
    )


async def _montar_jornada_fixa_dia_folga(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    jornada_id, _horario_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-FIXA-FOLGA",
        nome="Jornada fixa (folga)",
        tipo="fixa",
        vigencia_inicio=_VIGENCIA_ANTIGA,
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=_CARGA_PADRAO_MINUTOS,
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_VIGENCIA_ANTIGA,
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 11),  # sabado (dow 6)
        esperado={"tipo_dia": "folga", "origem": "jornada", "jornada_id": jornada_id},
    )


async def _montar_jornada_flexivel(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(sessao, contexto, tipo="flexivel", codigo="JOR-FLEX")


async def _montar_jornada_livre(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(sessao, contexto, tipo="livre", codigo="JOR-LIVRE")


async def _montar_jornada_parcial(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(
        sessao, contexto, tipo="parcial", codigo="JOR-PARCIAL"
    )


async def _montar_jornada_intermitente(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(
        sessao, contexto, tipo="intermitente", codigo="JOR-INTER"
    )


async def _montar_jornada_teletrabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(
        sessao, contexto, tipo="teletrabalho", codigo="JOR-TELE"
    )


async def _montar_jornada_motorista(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_jornada_tipo_dia_util(
        sessao, contexto, tipo="motorista", codigo="JOR-MOTO"
    )


# =============================================================================
# 2. Escalas ciclicas (T3): 5x2, 6x1, 4x2, 12x36 (incluindo virada de mes),
#    espanhola e rotativa de N dias com posicaoInicial != 1.
# =============================================================================
async def _criar_turno_padrao(
    sessao: AsyncSession,
    contexto: ContextoF3,
    *,
    codigo: str,
    entrada: _dt.time,
    saida: _dt.time,
    carga_minutos: int,
) -> tuple[uuid.UUID, uuid.UUID]:
    horario_id = await c.criar_horario(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo=f"HOR-{codigo}",
        nome=f"Horario {codigo}",
        entrada=entrada,
        saida=saida,
        carga_minutos=carga_minutos,
    )
    turno_id = await c.criar_turno(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo=f"TUR-{codigo}",
        nome=f"Turno {codigo}",
        horario_id=horario_id,
    )
    return horario_id, turno_id


async def _montar_escala_generica(
    sessao: AsyncSession,
    contexto: ContextoF3,
    *,
    codigo: str,
    tipo_escala: str,
    dias_ciclo: int,
    padrao_posicoes: dict[int, str],  # posicao -> tipo_dia ('trabalho'|'folga'|'dsr')
    vigencia_inicio: _dt.date,
    posicao_inicial: int,
    data_consulta: _dt.date,
    carga_trabalho_minutos: int = _CARGA_PADRAO_MINUTOS,
    entrada: _dt.time = _ENTRADA_PADRAO,
    saida: _dt.time = _SAIDA_PADRAO,
) -> Montagem:
    horario_id, turno_id = await _criar_turno_padrao(
        sessao,
        contexto,
        codigo=codigo,
        entrada=entrada,
        saida=saida,
        carga_minutos=carga_trabalho_minutos,
    )
    escala_id = await c.criar_escala(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo=f"ESC-{codigo}",
        nome=f"Escala {codigo}",
        tipo=tipo_escala,
        dias_ciclo=dias_ciclo,
        data_referencia=vigencia_inicio,
    )
    for posicao, tipo_dia in padrao_posicoes.items():
        await c.criar_escala_ciclo(
            sessao,
            contexto.tenant_id,
            escala_id,
            posicao=posicao,
            turno_id=turno_id if tipo_dia == "trabalho" else None,
            tipo_dia=tipo_dia,
            carga_minutos=carga_trabalho_minutos if tipo_dia == "trabalho" else 0,
        )
    await c.atribuir_escala_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        escala_id,
        posicao_inicial=posicao_inicial,
        vigencia_inicio=vigencia_inicio,
    )
    posicao_esperada = c.posicao_do_ciclo(
        vigencia_inicio=vigencia_inicio,
        posicao_inicial=posicao_inicial,
        dias_ciclo=dias_ciclo,
        data=data_consulta,
    )
    tipo_dia_escala = padrao_posicoes[posicao_esperada]
    tipo_dia_resposta = _MAPA_TIPO_DIA_ESCALA[tipo_dia_escala]
    esperado: dict[str, object] = {
        "tipo_dia": tipo_dia_resposta,
        "origem": "escala",
        "escala_id": escala_id,
        "posicao_ciclo": posicao_esperada,
    }
    if tipo_dia_escala == "trabalho":
        esperado["turno_id"] = turno_id
        esperado["horario_id"] = horario_id
        esperado["carga_prevista_minutos"] = carga_trabalho_minutos
    else:
        esperado["carga_prevista_minutos"] = 0
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id, data_consulta=data_consulta, esperado=esperado
    )


_PADRAO_5X2 = {
    1: "trabalho",
    2: "trabalho",
    3: "trabalho",
    4: "trabalho",
    5: "trabalho",
    6: "folga",
    7: "folga",
}
_PADRAO_6X1 = {
    1: "trabalho",
    2: "trabalho",
    3: "trabalho",
    4: "trabalho",
    5: "trabalho",
    6: "trabalho",
    7: "dsr",
}
_PADRAO_4X2 = {1: "trabalho", 2: "trabalho", 3: "trabalho", 4: "trabalho", 5: "folga", 6: "folga"}
_PADRAO_12X36 = {1: "trabalho", 2: "folga"}
# Espanhola: 2 semanas, sabado alternado (folga na 1a semana, trabalhado na 2a).
_PADRAO_ESPANHOLA = {
    1: "trabalho",
    2: "trabalho",
    3: "trabalho",
    4: "trabalho",
    5: "trabalho",
    6: "folga",
    7: "folga",
    8: "trabalho",
    9: "trabalho",
    10: "trabalho",
    11: "trabalho",
    12: "trabalho",
    13: "trabalho",
    14: "folga",
}
_PADRAO_ROTATIVA_3X2 = {1: "trabalho", 2: "trabalho", 3: "trabalho", 4: "folga", 5: "folga"}

_SEGUNDA_2025_01_06 = _dt.date(2025, 1, 6)


async def _montar_escala_5x2_trabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="5X2",
        tipo_escala="5x2",
        dias_ciclo=7,
        padrao_posicoes=_PADRAO_5X2,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
    )


async def _montar_escala_5x2_folga(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="5X2-F",
        tipo_escala="5x2",
        dias_ciclo=7,
        padrao_posicoes=_PADRAO_5X2,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 11),  # sabado
    )


async def _montar_escala_6x1_trabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="6X1",
        tipo_escala="6x1",
        dias_ciclo=7,
        padrao_posicoes=_PADRAO_6X1,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
    )


async def _montar_escala_6x1_dsr(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="6X1-D",
        tipo_escala="6x1",
        dias_ciclo=7,
        padrao_posicoes=_PADRAO_6X1,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 12),  # domingo
    )


async def _montar_escala_4x2_trabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="4X2",
        tipo_escala="4x2",
        dias_ciclo=6,
        padrao_posicoes=_PADRAO_4X2,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
    )


async def _montar_escala_4x2_folga(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="4X2-F",
        tipo_escala="4x2",
        dias_ciclo=6,
        padrao_posicoes=_PADRAO_4X2,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 10),  # sexta -- posicao 5 (folga)
    )


async def _montar_escala_12x36_trabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="12X36",
        tipo_escala="12x36",
        dias_ciclo=2,
        padrao_posicoes=_PADRAO_12X36,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
        carga_trabalho_minutos=720,
        entrada=_dt.time(7, 0),
        saida=_dt.time(19, 0),
    )


async def _montar_escala_12x36_folga(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="12X36-F",
        tipo_escala="12x36",
        dias_ciclo=2,
        padrao_posicoes=_PADRAO_12X36,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 7),
        carga_trabalho_minutos=720,
        entrada=_dt.time(7, 0),
        saida=_dt.time(19, 0),
    )


async def _montar_escala_12x36_virada_mes_vigencia_janeiro(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """Atribuicao com `vigenciaInicio` em janeiro, consultada em fevereiro
    (criterio de aceite 3: virada de mes no 12x36)."""
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="12X36-VM1",
        tipo_escala="12x36",
        dias_ciclo=2,
        padrao_posicoes=_PADRAO_12X36,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 2, 1),
        carga_trabalho_minutos=720,
        entrada=_dt.time(7, 0),
        saida=_dt.time(19, 0),
    )


async def _montar_escala_12x36_virada_mes_dia_anterior(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """31/01, um dia antes da virada -- par com o cenario seguinte prova que
    a posicao do ciclo atravessa o dia 1 do mes corretamente."""
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="12X36-VM2A",
        tipo_escala="12x36",
        dias_ciclo=2,
        padrao_posicoes=_PADRAO_12X36,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 31),
        carga_trabalho_minutos=720,
        entrada=_dt.time(7, 0),
        saida=_dt.time(19, 0),
    )


async def _montar_escala_12x36_virada_mes_dia_seguinte(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """01/02, o dia seguinte -- ver docstring do cenario anterior."""
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="12X36-VM2B",
        tipo_escala="12x36",
        dias_ciclo=2,
        padrao_posicoes=_PADRAO_12X36,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 2, 1),
        carga_trabalho_minutos=720,
        entrada=_dt.time(7, 0),
        saida=_dt.time(19, 0),
    )


async def _montar_escala_espanhola_trabalho(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="ESP",
        tipo_escala="espanhola",
        dias_ciclo=14,
        padrao_posicoes=_PADRAO_ESPANHOLA,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
    )


async def _montar_escala_espanhola_folga(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="ESP-F",
        tipo_escala="espanhola",
        dias_ciclo=14,
        padrao_posicoes=_PADRAO_ESPANHOLA,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 11),  # 1o sabado do ciclo -- folga
    )


async def _montar_escala_espanhola_sabado_trabalhado(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """2o sabado do ciclo (posicao 13) -- o que distingue a espanhola de um
    5x2 comum: o sabado alternado e trabalhado."""
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="ESP-S2",
        tipo_escala="espanhola",
        dias_ciclo=14,
        padrao_posicoes=_PADRAO_ESPANHOLA,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_dt.date(2025, 1, 18),  # 2o sabado do ciclo
    )


async def _montar_escala_rotativa_equipe_a(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    return await _montar_escala_generica(
        sessao,
        contexto,
        codigo="ROT-A",
        tipo_escala="rotativa",
        dias_ciclo=5,
        padrao_posicoes=_PADRAO_ROTATIVA_3X2,
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=1,
        data_consulta=_SEGUNDA_2025_01_06,
    )


async def _montar_escala_rotativa_equipe_b_desencontrada(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """Mesma escala (mesmo padrao de posicoes), mesma data da equipe A, mas
    `posicaoInicial = 4` -- as duas equipes ficam desencontradas no ciclo:
    enquanto a equipe A trabalha, a equipe B folga na mesma data."""
    horario_id, turno_id = await _criar_turno_padrao(
        sessao,
        contexto,
        codigo="ROT-B",
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        carga_minutos=_CARGA_PADRAO_MINUTOS,
    )
    escala_id = await c.criar_escala(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="ESC-ROT-B",
        nome="Escala rotativa 3x2 (equipe B)",
        tipo="rotativa",
        dias_ciclo=5,
        data_referencia=_SEGUNDA_2025_01_06,
    )
    for posicao, tipo_dia in _PADRAO_ROTATIVA_3X2.items():
        await c.criar_escala_ciclo(
            sessao,
            contexto.tenant_id,
            escala_id,
            posicao=posicao,
            turno_id=turno_id if tipo_dia == "trabalho" else None,
            tipo_dia=tipo_dia,
            carga_minutos=_CARGA_PADRAO_MINUTOS if tipo_dia == "trabalho" else 0,
        )
    posicao_inicial = 4
    await c.atribuir_escala_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_ba_id,
        escala_id,
        posicao_inicial=posicao_inicial,
        vigencia_inicio=_SEGUNDA_2025_01_06,
    )
    posicao_esperada = c.posicao_do_ciclo(
        vigencia_inicio=_SEGUNDA_2025_01_06,
        posicao_inicial=posicao_inicial,
        dias_ciclo=5,
        data=_SEGUNDA_2025_01_06,
    )
    tipo_dia_escala = _PADRAO_ROTATIVA_3X2[posicao_esperada]
    return Montagem(
        vinculo_id=contexto.vinculo_ba_id,
        data_consulta=_SEGUNDA_2025_01_06,
        esperado={
            "tipo_dia": _MAPA_TIPO_DIA_ESCALA[tipo_dia_escala],
            "origem": "escala",
            "escala_id": escala_id,
            "posicao_ciclo": posicao_esperada,
        },
    )


# =============================================================================
# 3. Troca de jornada no meio do mes, respeitando vigencia (T4/T7).
# =============================================================================
async def _montar_troca_jornada_dia_anterior(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    jornada_antiga_id, horario_antigo_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-TROCA-ANTIGA",
        nome="Jornada antiga (antes da troca)",
        tipo="fixa",
        vigencia_inicio=_dt.date(2025, 1, 1),
        vigencia_fim=_dt.date(2025, 1, 14),
        entrada=_dt.time(8, 0),
        saida=_dt.time(17, 0),
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=480,
    )
    jornada_nova_id, _horario_novo_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-TROCA-NOVA",
        nome="Jornada nova (depois da troca)",
        tipo="fixa",
        vigencia_inicio=_dt.date(2025, 1, 15),
        entrada=_dt.time(9, 0),
        saida=_dt.time(18, 0),
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=480,
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_antiga_id,
        vigencia_inicio=_dt.date(2025, 1, 1),
        vigencia_fim=_dt.date(2025, 1, 14),
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_nova_id,
        vigencia_inicio=_dt.date(2025, 1, 15),
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 14),  # terca -- ultimo dia da jornada antiga
        esperado={
            "tipo_dia": "util",
            "origem": "jornada",
            "jornada_id": jornada_antiga_id,
            "horario_id": horario_antigo_id,
        },
    )


async def _montar_troca_jornada_dia_da_troca(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    jornada_antiga_id, _horario_antigo_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-TROCA2-ANTIGA",
        nome="Jornada antiga (antes da troca)",
        tipo="fixa",
        vigencia_inicio=_dt.date(2025, 1, 1),
        vigencia_fim=_dt.date(2025, 1, 14),
        entrada=_dt.time(8, 0),
        saida=_dt.time(17, 0),
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=480,
    )
    jornada_nova_id, horario_novo_id = await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-TROCA2-NOVA",
        nome="Jornada nova (depois da troca)",
        tipo="fixa",
        vigencia_inicio=_dt.date(2025, 1, 15),
        entrada=_dt.time(9, 0),
        saida=_dt.time(18, 0),
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=480,
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_antiga_id,
        vigencia_inicio=_dt.date(2025, 1, 1),
        vigencia_fim=_dt.date(2025, 1, 14),
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_nova_id,
        vigencia_inicio=_dt.date(2025, 1, 15),
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 15),  # quarta -- primeiro dia da jornada nova
        esperado={
            "tipo_dia": "util",
            "origem": "jornada",
            "jornada_id": jornada_nova_id,
            "horario_id": horario_novo_id,
        },
    )


# =============================================================================
# 4. Feriados: nacional, estadual, municipal (so na unidade certa), moveis
#    (5 ancoras x 2 anos) e carga reduzida (T5/T7).
# =============================================================================
async def _jornada_base_sp(
    sessao: AsyncSession, contexto: ContextoF3, *, codigo: str, carga_minutos: int = 480
) -> tuple[uuid.UUID, uuid.UUID]:
    """Jornada de cobertura ampla (2023 em diante) para os cenarios de
    feriado/afastamento -- eles testam a SOBREPOSICAO, nao a jornada base."""
    return await c.criar_jornada_semana_padrao(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo=codigo,
        nome=f"Jornada base {codigo}",
        tipo="fixa",
        vigencia_inicio=_dt.date(2023, 1, 1),
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        intervalo_inicio=_INTERVALO_INICIO_PADRAO,
        intervalo_fim=_INTERVALO_FIM_PADRAO,
        duracao_intervalo_minutos=60,
        carga_minutos_dia_util=carga_minutos,
    )


async def _montar_feriado_nacional(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-NAC")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-NACIONAL",
        nome="Feriados nacionais",
        abrangencia="nacional",
    )
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    feriado_id = await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Confraternizacao Universal",
        data=_dt.date(2025, 1, 1),
        tipo="feriado",
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 1),
        esperado={
            "tipo_dia": "feriado",
            "origem": "feriado",
            "feriado_id": feriado_id,
            "feriado_nome": "Confraternizacao Universal",
            "jornada_id": jornada_id,
        },
    )


async def _montar_feriado_estadual_sp(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-EST")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-SP",
        nome="Feriados estaduais SP",
        abrangencia="estadual",
        uf="SP",
    )
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    feriado_id = await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Revolucao Constitucionalista",
        data=_dt.date(2025, 7, 9),
        tipo="feriado",
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 7, 9),
        esperado={
            "tipo_dia": "feriado",
            "origem": "feriado",
            "feriado_id": feriado_id,
            "feriado_nome": "Revolucao Constitucionalista",
        },
    )


async def _montar_feriado_municipal_aplica_unidade_certa(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-MUN-SP")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-MUN-SP",
        nome="Feriados municipais SP",
        abrangencia="municipal",
        codigo_ibge_municipio=contexto.unidade_sp_codigo_ibge,
    )
    # Associado SO a unidade_sp -- e o que garante que nao vaza para BA.
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    feriado_id = await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Aniversario de Sao Paulo",
        data=_dt.date(2025, 1, 25),
        tipo="feriado",
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 25),
        esperado={
            "tipo_dia": "feriado",
            "origem": "feriado",
            "feriado_id": feriado_id,
            "feriado_nome": "Aniversario de Sao Paulo",
        },
    )


async def _montar_feriado_municipal_nao_vaza_para_outra_unidade(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """Mesmo feriado do cenario anterior, mesma data, mas consultado pelo
    vinculo da OUTRA unidade (BA) -- criterio de aceite 5: as duas unidades
    resolvem `tipoDia` de forma diferente na mesma data."""
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-MUN-BA")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_ba_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-MUN-SP2",
        nome="Feriados municipais SP",
        abrangencia="municipal",
        codigo_ibge_municipio=contexto.unidade_sp_codigo_ibge,
    )
    # Associado SO a unidade_sp -- vinculo_ba nao ve este conjunto.
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Aniversario de Sao Paulo",
        data=_dt.date(2025, 1, 25),
        tipo="feriado",
    )
    data_consulta = _dt.date(2025, 1, 25)  # sabado -- cai em folga na jornada padrao
    return Montagem(
        vinculo_id=contexto.vinculo_ba_id,
        data_consulta=data_consulta,
        esperado={
            "tipo_dia": "folga",
            "origem": "jornada",
            "jornada_id": jornada_id,
            "feriado_id": None,
        },
    )


async def _montar_feriado_carga_reduzida(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(
        sessao, contexto, codigo="JOR-CARGA-RED", carga_minutos=480
    )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-CARGA-RED",
        nome="Feriados com expediente reduzido",
        abrangencia="empresa",
    )
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    feriado_id = await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Vespera de Natal (expediente reduzido)",
        data=_dt.date(2025, 12, 24),
        tipo="feriado",
        integral=False,
        carga_reduzida_minutos=240,
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 12, 24),
        esperado={
            "tipo_dia": "feriado",
            "origem": "feriado",
            "feriado_id": feriado_id,
            "carga_prevista_minutos": 240,
        },
    )


_ANCORAS_MOVEIS = ("pascoa", "carnaval", "sexta_santa", "corpus_christi", "quarta_cinzas")
_ANOS_MOVEIS = (2024, 2025)


def _fabrica_montador_feriado_movel(regra_movel: str, ano: int) -> MontarMassa:
    async def _montar(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
        jornada_id, _horario_id = await _jornada_base_sp(
            sessao, contexto, codigo=f"JOR-MOV-{regra_movel[:4].upper()}-{ano}"
        )
        await c.atribuir_jornada_vinculo(
            sessao,
            contexto.tenant_id,
            contexto.vinculo_sp_id,
            jornada_id,
            vigencia_inicio=_dt.date(2023, 1, 1),
        )
        conjunto_id = await c.criar_feriado_conjunto(
            sessao,
            contexto.tenant_id,
            codigo=f"CONJ-MOV-{regra_movel[:4].upper()}-{ano}",
            nome="Feriados moveis",
            abrangencia="nacional",
        )
        await c.associar_unidade_feriado_conjunto(
            sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
        )
        feriado_id = await c.criar_feriado(
            sessao,
            contexto.tenant_id,
            conjunto_id,
            nome=f"{regra_movel} {ano}",
            movel=True,
            regra_movel=regra_movel,
            offset_dias=0,
            tipo="feriado",
        )
        data_esperada = c.ancora_movel(regra_movel, ano)
        return Montagem(
            vinculo_id=contexto.vinculo_sp_id,
            data_consulta=data_esperada,
            esperado={"tipo_dia": "feriado", "origem": "feriado", "feriado_id": feriado_id},
        )

    return _montar


# =============================================================================
# 5. Ponto facultativo via `jornada_dias.tipo_dia = 'facultativo'` (mapeamento
#    da secao 2 do PCF: NAO depende de feriados/feriado_conjuntos).
# =============================================================================
async def _montar_ponto_facultativo(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    horario_id = await c.criar_horario(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="HOR-FACULT",
        nome="Horario ponto facultativo",
        entrada=_ENTRADA_PADRAO,
        saida=_SAIDA_PADRAO,
        carga_minutos=_CARGA_PADRAO_MINUTOS,
    )
    jornada_id = await c.criar_jornada(
        sessao,
        contexto.tenant_id,
        contexto.empresa_id,
        codigo="JOR-FACULT",
        nome="Jornada com sexta facultativa",
        tipo="fixa",
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    for dow in range(0, 7):
        if dow == 5:  # sexta-feira -- ponto facultativo fixado pelo cenario
            await c.criar_jornada_dia(
                sessao,
                contexto.tenant_id,
                jornada_id,
                dia_semana=dow,
                tipo_dia="facultativo",
            )
        elif dow == 0:
            await c.criar_jornada_dia(
                sessao, contexto.tenant_id, jornada_id, dia_semana=dow, tipo_dia="dsr"
            )
        elif dow == 6:
            await c.criar_jornada_dia(
                sessao, contexto.tenant_id, jornada_id, dia_semana=dow, tipo_dia="folga"
            )
        else:
            await c.criar_jornada_dia(
                sessao,
                contexto.tenant_id,
                jornada_id,
                dia_semana=dow,
                tipo_dia="util",
                horario_id=horario_id,
                carga_minutos=_CARGA_PADRAO_MINUTOS,
            )
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 1, 10),  # sexta-feira
        esperado={"tipo_dia": "ponto_facultativo", "origem": "jornada", "jornada_id": jornada_id},
    )


# =============================================================================
# 6. Afastamentos: integral aprovado sobrepondo dia de trabalho, e parcial
#    coexistindo com a jornada normal (T6/T7).
# =============================================================================
async def _montar_afastamento_integral_sobrepoe_trabalho(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-AFAST-INT")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    tipo_afastamento_id = await c.criar_tipo_afastamento(
        sessao,
        contexto.tenant_id,
        codigo="FERIAS",
        nome="Ferias",
        categoria="ferias",
    )
    afastamento_id = await c.criar_afastamento(
        sessao,
        contexto.tenant_id,
        contexto.colaborador_sp_id,
        tipo_afastamento_id,
        data_inicio=_dt.date(2025, 3, 3),
        data_fim=_dt.date(2025, 3, 17),
        vinculo_id=contexto.vinculo_sp_id,
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 3, 5),  # quarta -- dentro do periodo de ferias
        esperado={
            "tipo_dia": "afastamento",
            "origem": "afastamento",
            "afastamento_id": afastamento_id,
            "jornada_id": jornada_id,
        },
    )


async def _montar_afastamento_parcial_coexiste(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-AFAST-PARC")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sp_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    tipo_afastamento_id = await c.criar_tipo_afastamento(
        sessao,
        contexto.tenant_id,
        codigo="ATESTADO",
        nome="Atestado medico",
        categoria="atestado",
    )
    await c.criar_afastamento(
        sessao,
        contexto.tenant_id,
        contexto.colaborador_sp_id,
        tipo_afastamento_id,
        data_inicio=_dt.date(2025, 4, 7),
        data_fim=_dt.date(2025, 4, 7),
        periodo_parcial=True,
        hora_inicio=_dt.time(8, 0),
        hora_fim=_dt.time(12, 0),
        vinculo_id=contexto.vinculo_sp_id,
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sp_id,
        data_consulta=_dt.date(2025, 4, 7),  # segunda -- afastamento parcial nao sobrepoe
        esperado={
            "tipo_dia": "util",
            "origem": "jornada",
            "jornada_id": jornada_id,
            "afastamento_id": None,
        },
    )


# =============================================================================
# 7. Casos de borda: sem nenhuma regra vigente (`PONTO-APUR-002`) e vinculo
#    sem unidade (fuso da empresa, sem nenhum feriado_conjunto aplicavel).
# =============================================================================
async def _montar_sem_regra_vigente(sessao: AsyncSession, contexto: ContextoF3) -> Montagem:
    # `vinculo_sem_unidade` nao recebe nenhuma `vinculo_jornadas` nem
    # `escala_atribuicoes` -- de proposito, este e o caso "sem regra".
    return Montagem(
        vinculo_id=contexto.vinculo_sem_unidade_id,
        data_consulta=_dt.date(2025, 6, 2),
        erro_esperado="PONTO-APUR-002",
    )


async def _montar_vinculo_sem_unidade_usa_fuso_empresa(
    sessao: AsyncSession, contexto: ContextoF3
) -> Montagem:
    """`vinculo_sem_unidade` com jornada atribuida, mas sem `unidade_id`: o
    fuso efetivo cai para `empresas.fuso_horario` e nenhum feriado_conjunto
    se aplica, mesmo havendo um conjunto nacional associado as OUTRAS
    unidades (secao 2 do PCF, ultimo paragrafo antes de "Feriado municipal
    so vale na unidade certa")."""
    jornada_id, _horario_id = await _jornada_base_sp(sessao, contexto, codigo="JOR-SEM-UNID")
    await c.atribuir_jornada_vinculo(
        sessao,
        contexto.tenant_id,
        contexto.vinculo_sem_unidade_id,
        jornada_id,
        vigencia_inicio=_dt.date(2023, 1, 1),
    )
    conjunto_id = await c.criar_feriado_conjunto(
        sessao,
        contexto.tenant_id,
        codigo="CONJ-NAC-SEMUNID",
        nome="Feriados nacionais",
        abrangencia="nacional",
    )
    # Associado as duas unidades reais -- mas NUNCA a "nenhuma unidade", que e
    # exatamente o caso do vinculo_sem_unidade.
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_sp_id, conjunto_id
    )
    await c.associar_unidade_feriado_conjunto(
        sessao, contexto.tenant_id, contexto.unidade_ba_id, conjunto_id
    )
    await c.criar_feriado(
        sessao,
        contexto.tenant_id,
        conjunto_id,
        nome="Confraternizacao Universal",
        data=_dt.date(2025, 1, 1),
        tipo="feriado",
    )
    return Montagem(
        vinculo_id=contexto.vinculo_sem_unidade_id,
        data_consulta=_dt.date(2025, 1, 1),  # quarta -- seria feriado em qualquer unidade
        esperado={
            "tipo_dia": "util",  # NAO 'feriado': vinculo sem unidade nao ve o conjunto
            "origem": "jornada",
            "jornada_id": jornada_id,
            "feriado_id": None,
            "fuso_horario": contexto.empresa_fuso_horario,
        },
    )


# =============================================================================
# Lista final -- CRITERIO DE ACEITE 2 do PCF: `len(CENARIOS) >= 40`.
# =============================================================================
CENARIOS: list[Cenario] = [
    # 1. Jornadas nao ciclicas.
    Cenario(
        "jornada_fixa_dia_util", "Jornada fixa, dia util (segunda).", _montar_jornada_fixa_dia_util
    ),
    Cenario("jornada_fixa_dia_dsr", "Jornada fixa, DSR (domingo).", _montar_jornada_fixa_dia_dsr),
    Cenario(
        "jornada_fixa_dia_folga", "Jornada fixa, folga (sabado).", _montar_jornada_fixa_dia_folga
    ),
    Cenario("jornada_flexivel_dia_util", "Jornada flexivel, dia util.", _montar_jornada_flexivel),
    Cenario("jornada_livre_dia_util", "Jornada livre, dia util.", _montar_jornada_livre),
    Cenario("jornada_parcial_dia_util", "Jornada parcial, dia util.", _montar_jornada_parcial),
    Cenario(
        "jornada_intermitente_dia_util",
        "Jornada intermitente, dia util.",
        _montar_jornada_intermitente,
    ),
    Cenario(
        "jornada_teletrabalho_dia_util",
        "Jornada teletrabalho, dia util.",
        _montar_jornada_teletrabalho,
    ),
    Cenario(
        "jornada_motorista_dia_util", "Jornada motorista, dia util.", _montar_jornada_motorista
    ),
    # 2. Escalas ciclicas.
    Cenario("escala_5x2_trabalho", "Escala 5x2, dia de trabalho.", _montar_escala_5x2_trabalho),
    Cenario("escala_5x2_folga", "Escala 5x2, dia de folga.", _montar_escala_5x2_folga),
    Cenario("escala_6x1_trabalho", "Escala 6x1, dia de trabalho.", _montar_escala_6x1_trabalho),
    Cenario("escala_6x1_dsr", "Escala 6x1, dia de DSR.", _montar_escala_6x1_dsr),
    Cenario("escala_4x2_trabalho", "Escala 4x2, dia de trabalho.", _montar_escala_4x2_trabalho),
    Cenario("escala_4x2_folga", "Escala 4x2, dia de folga.", _montar_escala_4x2_folga),
    Cenario(
        "escala_12x36_trabalho", "Escala 12x36, dia de trabalho.", _montar_escala_12x36_trabalho
    ),
    Cenario("escala_12x36_folga", "Escala 12x36, dia de folga.", _montar_escala_12x36_folga),
    Cenario(
        "escala_12x36_virada_mes_vigencia_janeiro",
        "12x36: vigenciaInicio em janeiro, consulta em fevereiro.",
        _montar_escala_12x36_virada_mes_vigencia_janeiro,
    ),
    Cenario(
        "escala_12x36_virada_mes_dia_anterior",
        "12x36: 31/01, um dia antes da virada de mes.",
        _montar_escala_12x36_virada_mes_dia_anterior,
    ),
    Cenario(
        "escala_12x36_virada_mes_dia_seguinte",
        "12x36: 01/02, o dia seguinte a virada de mes.",
        _montar_escala_12x36_virada_mes_dia_seguinte,
    ),
    Cenario(
        "escala_espanhola_trabalho",
        "Escala espanhola, dia de trabalho.",
        _montar_escala_espanhola_trabalho,
    ),
    Cenario(
        "escala_espanhola_folga",
        "Escala espanhola, folga (1o sabado).",
        _montar_escala_espanhola_folga,
    ),
    Cenario(
        "escala_espanhola_sabado_trabalhado",
        "Escala espanhola, sabado alternado trabalhado (2o sabado do ciclo).",
        _montar_escala_espanhola_sabado_trabalhado,
    ),
    Cenario(
        "escala_rotativa_equipe_a_trabalho",
        "Escala rotativa 3x2, equipe A (posicaoInicial=1), trabalho.",
        _montar_escala_rotativa_equipe_a,
    ),
    Cenario(
        "escala_rotativa_equipe_b_desencontrada_folga",
        "Escala rotativa 3x2, equipe B (posicaoInicial=4), folga na mesma data da equipe A.",
        _montar_escala_rotativa_equipe_b_desencontrada,
    ),
    # 3. Troca de jornada respeitando vigencia.
    Cenario(
        "troca_jornada_dia_anterior_usa_antiga",
        "Troca de jornada no meio do mes: dia anterior usa a jornada antiga.",
        _montar_troca_jornada_dia_anterior,
    ),
    Cenario(
        "troca_jornada_dia_da_troca_usa_nova",
        "Troca de jornada no meio do mes: dia da troca usa a jornada nova.",
        _montar_troca_jornada_dia_da_troca,
    ),
    # 4. Feriados.
    Cenario(
        "feriado_nacional",
        "Feriado nacional fixo (Confraternizacao Universal).",
        _montar_feriado_nacional,
    ),
    Cenario(
        "feriado_estadual_sp",
        "Feriado estadual (Revolucao Constitucionalista, SP).",
        _montar_feriado_estadual_sp,
    ),
    Cenario(
        "feriado_municipal_aplica_unidade_certa",
        "Feriado municipal aplica na unidade de Sao Paulo.",
        _montar_feriado_municipal_aplica_unidade_certa,
    ),
    Cenario(
        "feriado_municipal_nao_vaza_outra_unidade",
        "Mesmo feriado municipal nao se aplica a unidade de Salvador.",
        _montar_feriado_municipal_nao_vaza_para_outra_unidade,
    ),
    Cenario(
        "feriado_carga_reduzida",
        "Feriado com expediente reduzido (integral=false) reduz cargaPrevistaMinutos.",
        _montar_feriado_carga_reduzida,
    ),
    Cenario(
        "ponto_facultativo",
        "Ponto facultativo via jornada_dias.tipo_dia.",
        _montar_ponto_facultativo,
    ),
    # 5. Afastamentos.
    Cenario(
        "afastamento_integral_sobrepoe_trabalho",
        "Afastamento integral aprovado (ferias) sobrepoe dia de trabalho.",
        _montar_afastamento_integral_sobrepoe_trabalho,
    ),
    Cenario(
        "afastamento_parcial_coexiste_com_jornada",
        "Afastamento parcial (atestado) coexiste com a jornada normal do dia.",
        _montar_afastamento_parcial_coexiste,
    ),
    # 6. Casos de borda.
    Cenario(
        "sem_regra_vigente_apur_002",
        "Vinculo sem nenhuma atribuicao vigente -> PONTO-APUR-002.",
        _montar_sem_regra_vigente,
    ),
    Cenario(
        "vinculo_sem_unidade_fuso_empresa",
        "Vinculo sem unidade_id usa o fuso da empresa e nao ve nenhum feriado_conjunto.",
        _montar_vinculo_sem_unidade_usa_fuso_empresa,
    ),
]

# 7. Feriados moveis -- 5 ancoras x 2 anos = 10 cenarios (criterio de aceite 6).
for _ano in _ANOS_MOVEIS:
    for _regra in _ANCORAS_MOVEIS:
        CENARIOS.append(
            Cenario(
                f"feriado_movel_{_regra}_{_ano}",
                f"Feriado movel '{_regra}' de {_ano}, ancorado na Pascoa "
                f"({c.pascoa(_ano).isoformat()}).",
                _fabrica_montador_feriado_movel(_regra, _ano),
            )
        )

assert len(CENARIOS) >= 40, f"golden dataset com {len(CENARIOS)} cenarios, esperado >= 40"
