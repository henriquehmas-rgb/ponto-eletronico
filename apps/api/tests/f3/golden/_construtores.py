"""Construtores de massa de dados para o golden dataset (T1/T8, agente A4).

Cada funcao insere diretamente nas tabelas do grupo 6 (jornada e calendario)
via SQL, **sem passar pela camada HTTP nem pelos routers** (que ainda nao
existem quando este modulo foi escrito -- o PCF da fase exige que o golden
dataset seja escrito antes do resolvedor, e o resolvedor so pode ser
exercitado depois que A1/A2 terminarem o CRUD das tabelas que ele le). Isto
mantem os cenarios de A4 totalmente independentes do cronograma dos outros
agentes da fase: a unica dependencia externa e
`app.jornada.resolvedor.servico.resolver_jornada_do_dia` (A3, T7), chamada
apenas em `test_cenarios.py`, nunca aqui.

`pascoa()` e `ancora_movel()` sao uma implementacao de referencia PROPRIA
(algoritmo de Meeus/Jones/Butcher, inteiro, sem ponto flutuante) usada
SOMENTE para calcular o resultado esperado dos cenarios de feriado movel --
nunca importar de `app.jornada` (isso descaracterizaria o teste: o golden
dataset tem que saber a resposta certa por conta propria, nao repetir o
calculo do codigo em teste). As datas produzidas foram conferidas a mao
contra o calendario oficial (ver comentario em cada cenario que as usa).
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def novo_id() -> uuid.UUID:
    return uuid.uuid4()


# =============================================================================
# Feriados moveis -- algoritmo de Meeus/Jones/Butcher (gregoriano), inteiro.
# =============================================================================
def pascoa(ano: int) -> _dt.date:
    """Data do Domingo de Pascoa no calendario gregoriano, para `ano`."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    # `l_epacta` (nome classico da variavel no algoritmo e so uma letra --
    # ver Meeus, "Astronomical Algorithms", cap. 8 -- renomeada aqui so para
    # nao colidir com o aviso E741 do ruff de nome ambiguo de variavel)
    # faltava na primeira versao deste arquivo, que usava `i` no lugar dela
    # por engano nas duas formulas abaixo. Sem ela o calculo da Pascoa de
    # 2024 dava 01/04 em vez de 31/03 -- pego pela conferencia manual contra
    # o calendario oficial (ver docstring do modulo).
    l_epacta = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_epacta) // 451
    mes = (h + l_epacta - 7 * m + 114) // 31
    dia = ((h + l_epacta - 7 * m + 114) % 31) + 1
    return _dt.date(ano, mes, dia)


_OFFSETS_ANCORA: dict[str, int] = {
    "pascoa": 0,
    "carnaval": -47,
    "quarta_cinzas": -46,
    "sexta_santa": -2,
    "corpus_christi": 60,
}


def ancora_movel(regra_movel: str, ano: int, offset_dias: int = 0) -> _dt.date:
    """Data efetiva de um feriado movel -- mesma formula da secao 2 do PCF:
    `ancora(regra_movel, ano) + offset_dias`, relativa a Pascoa do `ano`."""
    if regra_movel == "custom":
        base = pascoa(ano)
    else:
        base = pascoa(ano) + _dt.timedelta(days=_OFFSETS_ANCORA[regra_movel])
    return base + _dt.timedelta(days=offset_dias)


def posicao_do_ciclo(
    *, vigencia_inicio: _dt.date, posicao_inicial: int, dias_ciclo: int, data: _dt.date
) -> int:
    """Mesma formula da secao 2 do PCF -- usada aqui SOMENTE para calcular o
    esperado a mao nos cenarios de escala (referencia independente da
    implementacao de A1/A3, que expoe a mesma formula em
    `app.jornada.modelagem`)."""
    dias_desde_inicio = (data - vigencia_inicio).days
    return ((dias_desde_inicio + posicao_inicial - 1) % dias_ciclo) + 1


# =============================================================================
# Horarios, jornadas e jornada_dias
# =============================================================================
async def criar_horario(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    entrada: _dt.time | None = None,
    saida: _dt.time | None = None,
    intervalo_inicio: _dt.time | None = None,
    intervalo_fim: _dt.time | None = None,
    duracao_intervalo_minutos: int | None = None,
    cruza_meia_noite: bool = False,
    carga_minutos: int,
) -> uuid.UUID:
    horario_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, "
            " intervalo_inicio, intervalo_fim, duracao_intervalo_minutos, "
            " cruza_meia_noite, carga_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, :nome, :entrada, :saida, "
            "        :intervalo_inicio, :intervalo_fim, :duracao_intervalo_minutos, "
            "        :cruza_meia_noite, :carga_minutos)"
        ),
        {
            "id": horario_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": codigo,
            "nome": nome,
            "entrada": entrada,
            "saida": saida,
            "intervalo_inicio": intervalo_inicio,
            "intervalo_fim": intervalo_fim,
            "duracao_intervalo_minutos": duracao_intervalo_minutos,
            "cruza_meia_noite": cruza_meia_noite,
            "carga_minutos": carga_minutos,
        },
    )
    return horario_id


async def criar_jornada(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    tipo: str,
    vigencia_inicio: _dt.date,
    vigencia_fim: _dt.date | None = None,
    carga_diaria_minutos: int | None = None,
) -> uuid.UUID:
    jornada_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, vigencia_inicio, "
            " vigencia_fim, carga_diaria_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, :nome, :tipo, "
            "        :vigencia_inicio, :vigencia_fim, :carga_diaria_minutos)"
        ),
        {
            "id": jornada_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": codigo,
            "nome": nome,
            "tipo": tipo,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
            "carga_diaria_minutos": carga_diaria_minutos,
        },
    )
    return jornada_id


async def criar_jornada_dia(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    jornada_id: uuid.UUID,
    *,
    dia_semana: int,
    tipo_dia: str = "util",
    horario_id: uuid.UUID | None = None,
    carga_minutos: int = 0,
) -> uuid.UUID:
    jornada_dia_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO jornada_dias "
            "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
            "VALUES (:id, :tenant_id, :jornada_id, :dia_semana, :tipo_dia, :horario_id, "
            "        :carga_minutos)"
        ),
        {
            "id": jornada_dia_id,
            "tenant_id": tenant_id,
            "jornada_id": jornada_id,
            "dia_semana": dia_semana,
            "tipo_dia": tipo_dia,
            "horario_id": horario_id,
            "carga_minutos": carga_minutos,
        },
    )
    return jornada_dia_id


async def criar_jornada_semana_padrao(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    tipo: str,
    vigencia_inicio: _dt.date,
    vigencia_fim: _dt.date | None = None,
    entrada: _dt.time,
    saida: _dt.time,
    intervalo_inicio: _dt.time | None,
    intervalo_fim: _dt.time | None,
    duracao_intervalo_minutos: int | None,
    carga_minutos_dia_util: int,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Jornada fixa/flexivel/etc. de segunda a sexta util (dow 1..5), sabado
    folga (dow 6) e domingo DSR (dow 0) -- o padrao mais comum do golden
    dataset. Devolve `(jornada_id, horario_id)`."""
    horario_id = await criar_horario(
        sessao,
        tenant_id,
        empresa_id,
        codigo=f"HOR-{codigo}",
        nome=f"Horario {nome}",
        entrada=entrada,
        saida=saida,
        intervalo_inicio=intervalo_inicio,
        intervalo_fim=intervalo_fim,
        duracao_intervalo_minutos=duracao_intervalo_minutos,
        carga_minutos=carga_minutos_dia_util,
    )
    jornada_id = await criar_jornada(
        sessao,
        tenant_id,
        empresa_id,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
        carga_diaria_minutos=carga_minutos_dia_util,
    )
    for dow in range(0, 7):
        if dow == 0:
            await criar_jornada_dia(sessao, tenant_id, jornada_id, dia_semana=dow, tipo_dia="dsr")
        elif dow == 6:
            await criar_jornada_dia(sessao, tenant_id, jornada_id, dia_semana=dow, tipo_dia="folga")
        else:
            await criar_jornada_dia(
                sessao,
                tenant_id,
                jornada_id,
                dia_semana=dow,
                tipo_dia="util",
                horario_id=horario_id,
                carga_minutos=carga_minutos_dia_util,
            )
    return jornada_id, horario_id


# =============================================================================
# Turnos e escalas ciclicas
# =============================================================================
async def criar_turno(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    horario_id: uuid.UUID | None = None,
    tipo: str = "diurno",
    sequencia: int | None = None,
) -> uuid.UUID:
    turno_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO turnos "
            "(id, tenant_id, empresa_id, codigo, nome, horario_id, tipo, sequencia) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, :nome, :horario_id, :tipo, "
            "        :sequencia)"
        ),
        {
            "id": turno_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": codigo,
            "nome": nome,
            "horario_id": horario_id,
            "tipo": tipo,
            "sequencia": sequencia,
        },
    )
    return turno_id


async def criar_escala(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    tipo: str,
    dias_ciclo: int,
    data_referencia: _dt.date,
    jornada_id: uuid.UUID | None = None,
) -> uuid.UUID:
    escala_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO escalas "
            "(id, tenant_id, empresa_id, jornada_id, codigo, nome, tipo, dias_ciclo, "
            " data_referencia) "
            "VALUES (:id, :tenant_id, :empresa_id, :jornada_id, :codigo, :nome, :tipo, "
            "        :dias_ciclo, :data_referencia)"
        ),
        {
            "id": escala_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "jornada_id": jornada_id,
            "codigo": codigo,
            "nome": nome,
            "tipo": tipo,
            "dias_ciclo": dias_ciclo,
            "data_referencia": data_referencia,
        },
    )
    return escala_id


async def criar_escala_ciclo(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    escala_id: uuid.UUID,
    *,
    posicao: int,
    turno_id: uuid.UUID | None = None,
    tipo_dia: str = "trabalho",
    carga_minutos: int = 0,
) -> uuid.UUID:
    ciclo_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO escala_ciclos "
            "(id, tenant_id, escala_id, posicao, turno_id, tipo_dia, carga_minutos) "
            "VALUES (:id, :tenant_id, :escala_id, :posicao, :turno_id, :tipo_dia, "
            "        :carga_minutos)"
        ),
        {
            "id": ciclo_id,
            "tenant_id": tenant_id,
            "escala_id": escala_id,
            "posicao": posicao,
            "turno_id": turno_id,
            "tipo_dia": tipo_dia,
            "carga_minutos": carga_minutos,
        },
    )
    return ciclo_id


# =============================================================================
# Atribuicoes ao vinculo (vigencia)
# =============================================================================
async def atribuir_jornada_vinculo(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    jornada_id: uuid.UUID,
    *,
    vigencia_inicio: _dt.date,
    vigencia_fim: _dt.date | None = None,
) -> uuid.UUID:
    vinculo_jornada_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO vinculo_jornadas "
            "(id, tenant_id, vinculo_id, jornada_id, vigencia_inicio, vigencia_fim) "
            "VALUES (:id, :tenant_id, :vinculo_id, :jornada_id, :vigencia_inicio, "
            "        :vigencia_fim)"
        ),
        {
            "id": vinculo_jornada_id,
            "tenant_id": tenant_id,
            "vinculo_id": vinculo_id,
            "jornada_id": jornada_id,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
        },
    )
    return vinculo_jornada_id


async def atribuir_escala_vinculo(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    escala_id: uuid.UUID,
    *,
    posicao_inicial: int = 1,
    vigencia_inicio: _dt.date,
    vigencia_fim: _dt.date | None = None,
) -> uuid.UUID:
    atribuicao_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO escala_atribuicoes "
            "(id, tenant_id, vinculo_id, escala_id, posicao_inicial, vigencia_inicio, "
            " vigencia_fim) "
            "VALUES (:id, :tenant_id, :vinculo_id, :escala_id, :posicao_inicial, "
            "        :vigencia_inicio, :vigencia_fim)"
        ),
        {
            "id": atribuicao_id,
            "tenant_id": tenant_id,
            "vinculo_id": vinculo_id,
            "escala_id": escala_id,
            "posicao_inicial": posicao_inicial,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
        },
    )
    return atribuicao_id


# =============================================================================
# Feriados
# =============================================================================
async def criar_feriado_conjunto(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    abrangencia: str,
    uf: str | None = None,
    codigo_ibge_municipio: str | None = None,
) -> uuid.UUID:
    conjunto_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO feriado_conjuntos "
            "(id, tenant_id, codigo, nome, abrangencia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :abrangencia, :uf, :ibge)"
        ),
        {
            "id": conjunto_id,
            "tenant_id": tenant_id,
            "codigo": codigo,
            "nome": nome,
            "abrangencia": abrangencia,
            "uf": uf,
            "ibge": codigo_ibge_municipio,
        },
    )
    return conjunto_id


async def associar_unidade_feriado_conjunto(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    unidade_id: uuid.UUID,
    feriado_conjunto_id: uuid.UUID,
) -> None:
    await sessao.execute(
        text(
            "INSERT INTO unidade_feriado_conjuntos "
            "(id, tenant_id, unidade_id, feriado_conjunto_id) "
            "VALUES (:id, :tenant_id, :unidade_id, :feriado_conjunto_id)"
        ),
        {
            "id": novo_id(),
            "tenant_id": tenant_id,
            "unidade_id": unidade_id,
            "feriado_conjunto_id": feriado_conjunto_id,
        },
    )


async def criar_feriado(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    feriado_conjunto_id: uuid.UUID,
    *,
    nome: str,
    data: _dt.date | None = None,
    ano: int | None = None,
    tipo: str = "feriado",
    movel: bool = False,
    regra_movel: str | None = None,
    offset_dias: int | None = None,
    integral: bool = True,
    carga_reduzida_minutos: int | None = None,
) -> uuid.UUID:
    feriado_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO feriados "
            "(id, tenant_id, feriado_conjunto_id, nome, data, ano, tipo, movel, "
            " regra_movel, offset_dias, integral, carga_reduzida_minutos) "
            "VALUES (:id, :tenant_id, :feriado_conjunto_id, :nome, :data, :ano, :tipo, "
            "        :movel, :regra_movel, :offset_dias, :integral, :carga_reduzida_minutos)"
        ),
        {
            "id": feriado_id,
            "tenant_id": tenant_id,
            "feriado_conjunto_id": feriado_conjunto_id,
            "nome": nome,
            "data": data,
            "ano": ano,
            "tipo": tipo,
            "movel": movel,
            "regra_movel": regra_movel,
            "offset_dias": offset_dias,
            "integral": integral,
            "carga_reduzida_minutos": carga_reduzida_minutos,
        },
    )
    return feriado_id


# =============================================================================
# Afastamentos
# =============================================================================
async def criar_tipo_afastamento(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    codigo: str,
    nome: str,
    categoria: str,
) -> uuid.UUID:
    tipo_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO tipos_afastamento (id, tenant_id, codigo, nome, categoria) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria)"
        ),
        {
            "id": tipo_id,
            "tenant_id": tenant_id,
            "codigo": codigo,
            "nome": nome,
            "categoria": categoria,
        },
    )
    return tipo_id


async def criar_afastamento(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    tipo_afastamento_id: uuid.UUID,
    *,
    data_inicio: _dt.date,
    data_fim: _dt.date | None = None,
    periodo_parcial: bool = False,
    hora_inicio: _dt.time | None = None,
    hora_fim: _dt.time | None = None,
    status: str = "aprovado",
    vinculo_id: uuid.UUID | None = None,
) -> uuid.UUID:
    afastamento_id = novo_id()
    await sessao.execute(
        text(
            "INSERT INTO afastamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_afastamento_id, "
            " data_inicio, data_fim, periodo_parcial, hora_inicio, hora_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_afastamento_id, "
            "        :data_inicio, :data_fim, :periodo_parcial, :hora_inicio, :hora_fim, "
            "        :status)"
        ),
        {
            "id": afastamento_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "tipo_afastamento_id": tipo_afastamento_id,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "periodo_parcial": periodo_parcial,
            "hora_inicio": hora_inicio,
            "hora_fim": hora_fim,
            "status": status,
        },
    )
    return afastamento_id
