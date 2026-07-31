"""Datasets operacionais do catálogo de relatórios: itens 2-12 de `PROJETO.md`
§9 (F11/A2, T7/T8 — PCF §5, §6).

Onze funções de consulta, cada uma registrada em `app.relatorios.catalogo`
(`registrar_dataset`) na importação deste módulo (a importação acontece em
`app/routers/relatorios.py`, ver comentário no topo daquele arquivo -- A1).
Cada função segue o contrato fixado por `catalogo.py` (docstring do módulo,
"Contrato de uma função de dataset"): recebe `(sessao, tenant_id, contexto)`,
devolve um `sqlalchemy.Select` **linha a linha** (nunca `GROUP BY` dentro da
própria função -- o motor genérico, `motor.py`, é quem agrupa quando o
cliente pede `agrupamento`), com toda coluna de `colunas_disponiveis`
`.label(chave)` no `Select`.

**Somente leitura.** Nenhuma função aqui grava em `apuracoes_dia`,
`apuracao_componentes`, `ocorrencias`, `tratamentos`, `afastamentos`,
`bh_lancamentos` ou `marcacoes` -- nem chama `apurar_dia`/`recalcular_periodo`
(proibição 1, PCF §9). O dataset `tempo-real` (item 9) é a única exceção que
lê `marcacoes` diretamente em vez de `apuracoes_dia` -- ver docstring de
`tempo_real` e PCF §2.3/ADR-002.

## Nomes de `dataset` -- âncora de coordenação com `tests/f11/conftest.py`

`apps/api/tests/f11/conftest.py` (T1, ownership exclusivo de A1) já semeia as
24 linhas de `relatorio_definicoes`, e sua própria docstring fixa a regra:
*"Nomes de `dataset` são a âncora de coordenação entre os quatro agentes
desta fase: A2/A3/A4 devem chamar `registrar_dataset(<dataset>, <funcao>)`
com exatamente a string desta tabela para o motor encontrar a função."* Este
módulo registra cada uma das 11 funções sob a string EXATA que
`tests/f11/conftest.py::_CATALOGO_RELATORIOS` já usa (não a abreviação da
tabela do PCF §2.2, que era só ilustrativa -- ver `DATASET_*` abaixo, cada
uma comentada com o `codigo` de relatório correspondente).

## Colunas: superconjunto do que a fixture de teste já declara

A mesma fixture também já fixa `colunas_disponiveis`/`filtros_disponiveis`/
`agrupamentos` de cada um dos 24 relatórios (com nomes de coluna PRÓPRIOS,
escolhidos por A1 ao escrever `tests/f11/conftest.py`, antes deste módulo
existir -- corrida esperada de desenvolvimento em paralelo, PCF §2.9/ADR-009
"quem primeiro fixa a forma, os demais seguem"). Cada função de consulta
abaixo projeta, com `.label()`, **todas** as colunas que a fixture já
declarou (mesma chave, mesmo significado) mais colunas adicionais úteis para
quando um catálogo de produção real (fora do escopo desta fase, PCF §4) for
semeado a partir das constantes `COLUNAS_<NOME>`/`FILTROS_<NOME>`/
`AGRUPAMENTOS_<NOME>` exportadas por este módulo -- um superconjunto nunca
quebra a fixture de teste (colunas além de `colunas_disponiveis` simplesmente
não são pedidas por `_resolver_colunas_pedidas`, `motor.py`), só a enriquece
para uso fora dela.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    Afastamento,
    ApuracaoComponente,
    ApuracaoDia,
    BhConta,
    BhLancamento,
    Cargo,
    Colaborador,
    Departamento,
    Marcacao,
    Ocorrencia,
    Periodo,
    TipoAfastamento,
    TipoTratamento,
    Tratamento,
    Vinculo,
)
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios.catalogo import (
    AgrupamentoCatalogo,
    ColunaCatalogo,
    FiltroCatalogo,
    registrar_dataset,
)
from app.relatorios.motor import ContextoConsulta

CODIGO_FILTRO_INVALIDO = "PONTO-VAL-005"

#: `tratamentos.status` que já produziram (ou vão produzir) efeito na
#: apuração -- mesma FORMA de `app.workflow.fechamento.espelho.
#: _STATUS_TRATAMENTO_VISIVEL` (F10), replicada aqui (não importada: F10 é
#: outra fase, congelada -- reaproveitar a FORMA, não o módulo, é o mesmo
#: padrão que `catalogo.py`/`motor.py` já seguem para `paginacao.py`).
_STATUS_TRATAMENTO_VISIVEL = ("aprovado", "aplicado")

#: Categorias de `tipos_tratamento` que valem como "abono/justificativa" da
#: falta (item 11, e usadas pelo item 8 para a coluna `temTratamento`).
_CATEGORIAS_ABONO = ("abono", "justificativa")

#: Dataset keys -- EXATAMENTE as strings de `tests/f11/conftest.py::
#: _CATALOGO_RELATORIOS` (ver docstring do módulo).
DATASET_ESPELHO_JORNADA = "apuracao_dia"
DATASET_BANCO_DE_HORAS = "bh_lancamentos"
DATASET_HORAS_EXTRAS = "apuracao_componentes_extra"
DATASET_ADICIONAL_NOTURNO = "apuracao_componentes_noturno"
DATASET_ABSENTEISMO = "absenteismo"
DATASET_ATRASOS_SAIDAS_ANTECIPADAS = "apuracao_dia_atrasos"
DATASET_FALTAS = "apuracao_dia_faltas"
DATASET_TEMPO_REAL = "marcacoes_tempo_real"
DATASET_OCORRENCIAS = "ocorrencias"
DATASET_ABONOS_JUSTIFICATIVAS = "tratamentos_abono"
DATASET_FERIAS_AFASTAMENTOS = "afastamentos"


# ---------------------------------------------------------------------------
# Helpers de filtro compartilhados entre os 11 datasets deste módulo.
# ---------------------------------------------------------------------------


def _uuid_do_filtro(bruto: Any, *, chave: str) -> UUID | None:
    """Decodifica um valor de `contexto.filtros` (JSON, portanto string) para
    `UUID`. `PONTO-VAL-005` se não for um UUID válido."""
    if bruto in (None, ""):
        return None
    if isinstance(bruto, UUID):
        return bruto
    try:
        return UUID(str(bruto))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ErroDeAplicacao(
            CODIGO_FILTRO_INVALIDO, detalhe=f"Filtro '{chave}' precisa ser um UUID valido."
        ) from exc


def _aplicar_periodo(
    consulta: Select[Any], contexto: ContextoConsulta, coluna_data: Any, tenant_id: UUID
) -> Select[Any]:
    """Aplica o intervalo pedido (`periodoId` OU `de`/`ate`) contra
    `coluna_data`. `periodoId` é resolvido por subconsulta escalar (a função
    de dataset é síncrona -- não pode `await sessao.get(Periodo, ...)`, ver
    `catalogo.ConstrutorDataset`), nunca lido em Python."""
    if contexto.periodo_id is not None:
        condicoes_periodo = (Periodo.id == contexto.periodo_id, Periodo.tenant_id == tenant_id)
        inicio = sa.select(Periodo.data_inicio).where(*condicoes_periodo).scalar_subquery()
        fim = sa.select(Periodo.data_fim).where(*condicoes_periodo).scalar_subquery()
        return consulta.where(coluna_data >= inicio, coluna_data <= fim)
    if contexto.de is not None:
        consulta = consulta.where(coluna_data >= contexto.de)
    if contexto.ate is not None:
        consulta = consulta.where(coluna_data <= contexto.ate)
    return consulta


def _aplicar_escopo_apuracao(consulta: Select[Any], contexto: ContextoConsulta) -> Select[Any]:
    """Escopo empresa/unidade/departamento/colaborador/vínculo/centro de
    custo para datasets baseados em `apuracoes_dia`, que já denormaliza essas
    colunas (não precisa de `JOIN` em `vinculos` para filtrar por elas)."""
    if contexto.empresa_id is not None:
        consulta = consulta.where(ApuracaoDia.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        consulta = consulta.where(ApuracaoDia.unidade_id == contexto.unidade_id)
    if contexto.departamento_id is not None:
        consulta = consulta.where(ApuracaoDia.departamento_id == contexto.departamento_id)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(ApuracaoDia.colaborador_id == contexto.colaborador_id)
    vinculo_id = _uuid_do_filtro(contexto.filtros.get("vinculoId"), chave="vinculoId")
    if vinculo_id is not None:
        consulta = consulta.where(ApuracaoDia.vinculo_id == vinculo_id)
    centro_custo_id = _uuid_do_filtro(contexto.filtros.get("centroCustoId"), chave="centroCustoId")
    if centro_custo_id is not None:
        consulta = consulta.where(ApuracaoDia.centro_custo_id == centro_custo_id)
    return consulta


def _aplicar_escopo_vinculo(consulta: Select[Any], contexto: ContextoConsulta) -> Select[Any]:
    """Mesmo escopo, para datasets que precisam `JOIN vinculos` porque a
    tabela base (`tratamentos`, `afastamentos`, `ocorrencias`) não
    denormaliza empresa/unidade/departamento."""
    if contexto.empresa_id is not None:
        consulta = consulta.where(Vinculo.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        consulta = consulta.where(Vinculo.unidade_id == contexto.unidade_id)
    if contexto.departamento_id is not None:
        consulta = consulta.where(Vinculo.departamento_id == contexto.departamento_id)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(Vinculo.colaborador_id == contexto.colaborador_id)
    vinculo_id = _uuid_do_filtro(contexto.filtros.get("vinculoId"), chave="vinculoId")
    if vinculo_id is not None:
        consulta = consulta.where(Vinculo.id == vinculo_id)
    return consulta


def _aplicar_incluir_inativos(consulta: Select[Any], contexto: ContextoConsulta) -> Select[Any]:
    """`incluirInativos=false` (padrão) restringe a `colaboradores.status =
    'ativo'` -- exige `Colaborador` já no `FROM`/`JOIN` da consulta."""
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


def _mes(coluna_data: Any) -> Any:
    """`date_trunc('month', ...)` rotulado `mes` -- agrupamento mensal comum
    a quase todo dataset (dataviz de A4 consome via `agrupamento=mes`)."""
    return func.date_trunc("month", coluna_data).label("mes")


def _coluna_mes_agrupamento() -> AgrupamentoCatalogo:
    return AgrupamentoCatalogo(chave="mes", rotulo="Mes")


def _filtros_escopo_padrao() -> list[FiltroCatalogo]:
    return [
        FiltroCatalogo("periodoId", "Periodo", "uuid"),
        FiltroCatalogo("empresaId", "Empresa", "uuid"),
        FiltroCatalogo("unidadeId", "Unidade", "uuid"),
        FiltroCatalogo("departamentoId", "Departamento", "uuid"),
        FiltroCatalogo("colaboradorId", "Colaborador", "uuid"),
    ]


# ---------------------------------------------------------------------------
# Item 2 -- Jornada / espelho prévio (`espelho-jornada`, dataset
# `apuracao_dia`, 30+ colunas).
# ---------------------------------------------------------------------------

COLUNAS_ESPELHO_JORNADA: list[ColunaCatalogo] = [
    ColunaCatalogo("nomeCompleto", "Nome completo", "texto"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("cargo", "Cargo", "texto"),
    ColunaCatalogo("departamento", "Departamento", "texto"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("tipoDia", "Tipo do dia", "texto"),
    ColunaCatalogo("previstoMinutos", "Previsto", "numero", duracao=True),
    ColunaCatalogo("trabalhadoMinutos", "Trabalhado", "numero", duracao=True),
    ColunaCatalogo("normaisMinutos", "Normais", "numero", duracao=True),
    ColunaCatalogo("extrasMinutos", "Extras diurnas", "numero", duracao=True),
    ColunaCatalogo("extrasNoturnasMinutos", "Extras noturnas", "numero", duracao=True),
    ColunaCatalogo("noturnoMinutos", "Adicional noturno", "numero", duracao=True),
    ColunaCatalogo(
        "intrajornadaSuprimidaMinutos", "Intrajornada suprimida", "numero", duracao=True
    ),
    ColunaCatalogo("atrasoMinutos", "Atraso", "numero", duracao=True),
    ColunaCatalogo("saidaAntecipadaMinutos", "Saida antecipada", "numero", duracao=True),
    ColunaCatalogo("faltaMinutos", "Falta", "numero", duracao=True),
    ColunaCatalogo("dsrCreditoMinutos", "Credito DSR", "numero", duracao=True),
    ColunaCatalogo("dsrDebitoMinutos", "Debito DSR", "numero", duracao=True),
    ColunaCatalogo("bancoCreditoMinutos", "Credito banco de horas", "numero", duracao=True),
    ColunaCatalogo("bancoDebitoMinutos", "Debito banco de horas", "numero", duracao=True),
    ColunaCatalogo("pausasNr17Minutos", "Pausas NR-17", "numero", duracao=True),
    ColunaCatalogo("saldoMinutos", "Saldo do dia", "numero", duracao=True),
    ColunaCatalogo("status", "Status da apuracao", "texto"),
    # -- colunas adicionais além do mínimo já fixado pela fixture de teste --
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("centroCusto", "Centro de custo", "uuid"),
    ColunaCatalogo("intervaloMinutos", "Intervalo", "numero", duracao=True),
    ColunaCatalogo("intervaloPrevistoMinutos", "Intervalo previsto", "numero", duracao=True),
    ColunaCatalogo("sobreavisoMinutos", "Sobreaviso", "numero", duracao=True),
    ColunaCatalogo("prontidaoMinutos", "Prontidao", "numero", duracao=True),
    ColunaCatalogo("abonoMinutos", "Abono", "numero", duracao=True),
    ColunaCatalogo("horasFaltantesMinutos", "Horas faltantes", "numero", duracao=True),
    ColunaCatalogo("quantidadeMarcacoes", "Quantidade de marcacoes", "numero"),
    ColunaCatalogo("marcacoesImpares", "Marcacoes impares", "booleano"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_ESPELHO_JORNADA: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("vinculoId", "Vinculo", "uuid"),
    FiltroCatalogo("centroCustoId", "Centro de custo", "uuid"),
]

AGRUPAMENTOS_ESPELHO_JORNADA: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    _coluna_mes_agrupamento(),
]


def espelho_jornada(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 2 -- jornada / espelho prévio, 30+ colunas configuráveis
    (`PROJETO.md` §9 item 2; dataset `apuracao_dia`). Lê `apuracoes_dia`
    (materializado por F4), `colaboradores`/`vinculos`/`cargos`/
    `departamentos` só para os nomes de apresentação -- **nunca**
    `apurar_dia`/`recalcular_periodo` (proibição 1). Um dia sem linha em
    `apuracoes_dia` simplesmente não aparece (mesmo padrão de
    `espelho.py::_montar_conteudo`, F10, que mostra `"nao_apurado"` só
    porque monta um calendário completo; este relatório, por ser tabular
    linha-a-linha de um `SELECT`, naturalmente omite dias sem apuração --
    comportamento equivalente, forma diferente)."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("nomeCompleto"),
            Colaborador.matricula.label("matricula"),
            Cargo.nome.label("cargo"),
            Departamento.nome.label("departamento"),
            ApuracaoDia.data.label("data"),
            ApuracaoDia.tipo_dia.label("tipoDia"),
            ApuracaoDia.previsto_minutos.label("previstoMinutos"),
            ApuracaoDia.trabalhado_minutos.label("trabalhadoMinutos"),
            ApuracaoDia.normais_minutos.label("normaisMinutos"),
            ApuracaoDia.extras_minutos.label("extrasMinutos"),
            ApuracaoDia.extras_noturnas_minutos.label("extrasNoturnasMinutos"),
            ApuracaoDia.noturno_minutos.label("noturnoMinutos"),
            ApuracaoDia.intrajornada_suprimida_minutos.label("intrajornadaSuprimidaMinutos"),
            ApuracaoDia.atraso_minutos.label("atrasoMinutos"),
            ApuracaoDia.saida_antecipada_minutos.label("saidaAntecipadaMinutos"),
            ApuracaoDia.falta_minutos.label("faltaMinutos"),
            ApuracaoDia.dsr_credito_minutos.label("dsrCreditoMinutos"),
            ApuracaoDia.dsr_debito_minutos.label("dsrDebitoMinutos"),
            ApuracaoDia.banco_credito_minutos.label("bancoCreditoMinutos"),
            ApuracaoDia.banco_debito_minutos.label("bancoDebitoMinutos"),
            ApuracaoDia.pausas_nr17_minutos.label("pausasNr17Minutos"),
            ApuracaoDia.saldo_minutos.label("saldoMinutos"),
            ApuracaoDia.status.label("status"),
            ApuracaoDia.colaborador_id.label("colaborador"),
            ApuracaoDia.vinculo_id.label("vinculo"),
            ApuracaoDia.empresa_id.label("empresa"),
            ApuracaoDia.unidade_id.label("unidade"),
            ApuracaoDia.centro_custo_id.label("centroCusto"),
            ApuracaoDia.intervalo_minutos.label("intervaloMinutos"),
            ApuracaoDia.intervalo_previsto_minutos.label("intervaloPrevistoMinutos"),
            ApuracaoDia.sobreaviso_minutos.label("sobreavisoMinutos"),
            ApuracaoDia.prontidao_minutos.label("prontidaoMinutos"),
            ApuracaoDia.abono_minutos.label("abonoMinutos"),
            func.greatest(ApuracaoDia.previsto_minutos - ApuracaoDia.trabalhado_minutos, 0).label(
                "horasFaltantesMinutos"
            ),
            ApuracaoDia.quantidade_marcacoes.label("quantidadeMarcacoes"),
            ApuracaoDia.marcacoes_impares.label("marcacoesImpares"),
            _mes(ApuracaoDia.data),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(Vinculo, Vinculo.id == ApuracaoDia.vinculo_id)
        .outerjoin(Cargo, Cargo.id == Vinculo.cargo_id)
        .outerjoin(Departamento, Departamento.id == ApuracaoDia.departamento_id)
        .where(ApuracaoDia.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, ApuracaoDia.data, tenant_id)
    consulta = _aplicar_escopo_apuracao(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    return consulta


registrar_dataset(DATASET_ESPELHO_JORNADA, espelho_jornada)


# ---------------------------------------------------------------------------
# Item 3 -- Banco de horas: extrato + saldo por lançamento.
# ---------------------------------------------------------------------------

#: **Achado de contrato registrado (não escondido):** o PCF (§6, T7) descreve
#: este dataset como "reaproveita `obter_extrato_banco_horas` de F4" -- mas
#: `obter_extrato_banco_horas` é `async` e devolve um `esquemas.
#: ExtratoBancoHoras` já agregado (saldo inicial/final, um objeto por
#: consulta), incompatível com o contrato síncrono `ConstrutorDataset`
#: fixado por A1 em `catalogo.py` (`Callable[[AsyncSession, UUID,
#: ContextoConsulta], Select[Any]]`, sem `await`) -- que só existiu depois
#: que este PCF foi escrito (T2, decisão de A1 durante a fase). Em vez de
#: forçar uma chamada incompatível, este dataset lê `bh_lancamentos`
#: diretamente (a mesma tabela que `obter_extrato_banco_horas` lê, e a
#: origem de verdade do saldo, conforme o comentário de `bh_contas.
#: saldo_atual_minutos`) -- uma linha por lançamento do extrato, com
#: `saldoAposMinutos` já sendo o "saldo" do item 3 a cada movimento, e
#: `venceEm` cobrindo "projeção de vencimento" por lançamento (a agregação
#: 30/15/7 dias já existe na rota dedicada `GET .../banco-horas/saldo`,
#: fora do escopo desta fase repetir aqui).
COLUNAS_BANCO_DE_HORAS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("tipo", "Tipo do lancamento", "texto"),
    ColunaCatalogo("minutos", "Minutos", "numero", duracao=True),
    ColunaCatalogo("saldoAposMinutos", "Saldo apos", "numero", duracao=True),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("contaCodigo", "Conta", "texto"),
    ColunaCatalogo("origem", "Origem", "texto"),
    ColunaCatalogo("fator", "Fator", "numero"),
    ColunaCatalogo("minutosEquivalentes", "Minutos equivalentes", "numero", duracao=True),
    ColunaCatalogo("venceEm", "Vence em", "data"),
    ColunaCatalogo("consumidoMinutos", "Consumido", "numero", duracao=True),
    ColunaCatalogo("descricao", "Descricao", "texto"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_BANCO_DE_HORAS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("vinculoId", "Vinculo", "uuid"),
    FiltroCatalogo("contaCodigo", "Codigo da conta", "texto"),
    FiltroCatalogo("tipo", "Tipo do lancamento", "texto"),
]

AGRUPAMENTOS_BANCO_DE_HORAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    _coluna_mes_agrupamento(),
]


def banco_de_horas(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 3 -- extrato de banco de horas, uma linha por `bh_lancamentos`
    (extrato IMUTÁVEL, F4) -- ver achado de contrato acima sobre por que não
    chama `obter_extrato_banco_horas` diretamente."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            BhLancamento.data_competencia.label("data"),
            BhLancamento.tipo.label("tipo"),
            BhLancamento.minutos.label("minutos"),
            BhLancamento.saldo_apos_minutos.label("saldoAposMinutos"),
            Colaborador.matricula.label("matricula"),
            BhConta.colaborador_id.label("colaborador"),
            BhConta.vinculo_id.label("vinculo"),
            Vinculo.empresa_id.label("empresa"),
            Vinculo.unidade_id.label("unidade"),
            Vinculo.departamento_id.label("departamento"),
            BhConta.codigo.label("contaCodigo"),
            BhLancamento.origem.label("origem"),
            BhLancamento.fator.label("fator"),
            BhLancamento.minutos_equivalentes.label("minutosEquivalentes"),
            BhLancamento.vence_em.label("venceEm"),
            BhLancamento.consumido_minutos.label("consumidoMinutos"),
            BhLancamento.descricao.label("descricao"),
            _mes(BhLancamento.data_competencia),
        )
        .select_from(BhLancamento)
        .join(BhConta, BhConta.id == BhLancamento.bh_conta_id)
        .join(Colaborador, Colaborador.id == BhConta.colaborador_id)
        .outerjoin(Vinculo, Vinculo.id == BhConta.vinculo_id)
        .where(BhLancamento.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, BhLancamento.data_competencia, tenant_id)
    consulta = _aplicar_escopo_vinculo(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    conta_codigo = contexto.filtros.get("contaCodigo")
    if conta_codigo:
        consulta = consulta.where(BhConta.codigo == str(conta_codigo))
    tipo = contexto.filtros.get("tipo")
    if tipo:
        consulta = consulta.where(BhLancamento.tipo == str(tipo))
    return consulta


registrar_dataset(DATASET_BANCO_DE_HORAS, banco_de_horas)


# ---------------------------------------------------------------------------
# Itens 4/5 -- Horas extras e adicional noturno: `apuracao_componentes` por
# categoria, mesma forma de consulta parametrizada pela categoria.
# ---------------------------------------------------------------------------


def _colunas_componentes_por_categoria() -> list[ColunaCatalogo]:
    return [
        ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
        ColunaCatalogo("departamento", "Departamento", "texto"),
        ColunaCatalogo("data", "Data", "data"),
        ColunaCatalogo("fator", "Fator", "numero"),
        ColunaCatalogo("minutos", "Minutos", "numero", duracao=True),
        ColunaCatalogo("minutosEquivalentes", "Minutos equivalentes", "numero", duracao=True),
        ColunaCatalogo("matricula", "Matricula", "texto"),
        ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
        ColunaCatalogo("vinculo", "Vinculo", "uuid"),
        ColunaCatalogo("empresa", "Empresa", "uuid"),
        ColunaCatalogo("unidade", "Unidade", "uuid"),
        ColunaCatalogo("centroCusto", "Centro de custo", "uuid"),
        ColunaCatalogo("codigo", "Codigo da rubrica", "texto"),
        ColunaCatalogo("descricao", "Descricao", "texto"),
        ColunaCatalogo("origem", "Origem", "texto"),
        ColunaCatalogo("mes", "Mes", "data"),
    ]


def _filtros_componentes_por_categoria() -> list[FiltroCatalogo]:
    return [
        *_filtros_escopo_padrao(),
        FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
        FiltroCatalogo("vinculoId", "Vinculo", "uuid"),
        FiltroCatalogo("centroCustoId", "Centro de custo", "uuid"),
        FiltroCatalogo("codigo", "Codigo da rubrica", "texto"),
    ]


def _componentes_por_categoria(
    tenant_id: UUID, contexto: ContextoConsulta, *, categoria: str
) -> Select[Any]:
    """FORMA compartilhada pelos itens 4 (`categoria='extra'`) e 5
    (`categoria='noturno'`) -- uma linha por `apuracao_componentes` da
    categoria pedida, juntada a `apuracoes_dia` só para resolver
    data/escopo/identidade (nunca para reagregar: a agregação por período é
    responsabilidade do motor, via `agrupamento`)."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            Departamento.nome.label("departamento"),
            ApuracaoDia.data.label("data"),
            ApuracaoComponente.fator.label("fator"),
            ApuracaoComponente.minutos.label("minutos"),
            ApuracaoComponente.minutos_equivalentes.label("minutosEquivalentes"),
            Colaborador.matricula.label("matricula"),
            ApuracaoDia.colaborador_id.label("colaborador"),
            ApuracaoDia.vinculo_id.label("vinculo"),
            ApuracaoDia.empresa_id.label("empresa"),
            ApuracaoDia.unidade_id.label("unidade"),
            ApuracaoDia.centro_custo_id.label("centroCusto"),
            ApuracaoComponente.codigo.label("codigo"),
            ApuracaoComponente.descricao.label("descricao"),
            ApuracaoComponente.origem.label("origem"),
            _mes(ApuracaoDia.data),
        )
        .select_from(ApuracaoComponente)
        .join(ApuracaoDia, ApuracaoDia.id == ApuracaoComponente.apuracao_dia_id)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(Departamento, Departamento.id == ApuracaoDia.departamento_id)
        .where(
            ApuracaoComponente.tenant_id == tenant_id,
            ApuracaoDia.tenant_id == tenant_id,
            ApuracaoComponente.categoria == categoria,
        )
    )
    consulta = _aplicar_periodo(consulta, contexto, ApuracaoDia.data, tenant_id)
    consulta = _aplicar_escopo_apuracao(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    codigo = contexto.filtros.get("codigo")
    if codigo:
        consulta = consulta.where(ApuracaoComponente.codigo == str(codigo))
    return consulta


COLUNAS_HORAS_EXTRAS: list[ColunaCatalogo] = _colunas_componentes_por_categoria()
FILTROS_HORAS_EXTRAS: list[FiltroCatalogo] = _filtros_componentes_por_categoria()
AGRUPAMENTOS_HORAS_EXTRAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    _coluna_mes_agrupamento(),
]

COLUNAS_ADICIONAL_NOTURNO: list[ColunaCatalogo] = _colunas_componentes_por_categoria()
FILTROS_ADICIONAL_NOTURNO: list[FiltroCatalogo] = _filtros_componentes_por_categoria()
AGRUPAMENTOS_ADICIONAL_NOTURNO: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    _coluna_mes_agrupamento(),
]


def horas_extras(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Item 4 -- horas extras por fator/período/centro de custo:
    `apuracao_componentes` onde `categoria = 'extra'`."""
    return _componentes_por_categoria(tenant_id, contexto, categoria="extra")


registrar_dataset(DATASET_HORAS_EXTRAS, horas_extras)


def adicional_noturno(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 5 -- adicional noturno: `apuracao_componentes` onde `categoria =
    'noturno'`."""
    return _componentes_por_categoria(tenant_id, contexto, categoria="noturno")


registrar_dataset(DATASET_ADICIONAL_NOTURNO, adicional_noturno)


# ---------------------------------------------------------------------------
# Item 6 -- Absenteísmo: índice, ranking, evolução.
# ---------------------------------------------------------------------------

#: **Decisão de julgamento registrada (não escondida):** `tests/f11/
#: conftest.py` já semeia a coluna `diasComFalta` com `duracao=true` (uma
#: CONTAGEM de dias, não minutos) -- divergindo do que este módulo teria
#: escolhido sozinho (documentado abaixo: contagem marcada `duracao=true`
#: faz o exportador `converterDecimal=true`, A3, dividir por 60 como se
#: fosse minuto). Como `tests/f11/conftest.py` é ownership exclusivo de A1 e
#: já está commitado com essa forma, este dataset segue o contrato já
#: fixado (devolve `diasComFalta` como 0/1 por linha, somável no modo
#: agrupado) em vez de divergir da fixture -- a divergência de julgamento
#: fica registrada aqui e no relatório de fechamento da fase, não escondida.
COLUNAS_ABSENTEISMO: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("departamento", "Departamento", "texto"),
    ColunaCatalogo("faltaMinutos", "Falta", "numero", duracao=True),
    ColunaCatalogo("diasComFalta", "Dias com falta", "numero", duracao=True),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("previstoMinutos", "Previsto", "numero", duracao=True),
    ColunaCatalogo("trabalhadoMinutos", "Trabalhado", "numero", duracao=True),
    ColunaCatalogo("abonoMinutos", "Abono", "numero", duracao=True),
    ColunaCatalogo("tipoDia", "Tipo do dia", "texto"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_ABSENTEISMO: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("centroCustoId", "Centro de custo", "uuid"),
    FiltroCatalogo("tipoDia", "Tipo do dia", "texto"),
]

AGRUPAMENTOS_ABSENTEISMO: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    _coluna_mes_agrupamento(),
]


def absenteismo(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Item 6 -- absenteísmo (índice, ranking, evolução): agregação de
    `falta_minutos`/dias por colaborador/período. `diasComFalta` é 1 quando
    `falta_minutos > 0` no dia, 0 caso contrário -- somável em modo agrupado
    para produzir "quantidade de dias com falta" por colaborador/
    departamento/mês; o "índice" propriamente (faltas / dias úteis
    previstos) é razão entre dois somatórios, calculada pelo consumidor
    (tela genérica de A1, T4; dataviz de A4, T13) sobre o resultado
    agrupado -- o motor genérico só soma/conta em SQL, nunca divide (PCF
    §6/T2)."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            Departamento.nome.label("departamento"),
            ApuracaoDia.falta_minutos.label("faltaMinutos"),
            sa.case((ApuracaoDia.falta_minutos > 0, 1), else_=0).label("diasComFalta"),
            ApuracaoDia.data.label("data"),
            Colaborador.matricula.label("matricula"),
            ApuracaoDia.colaborador_id.label("colaborador"),
            ApuracaoDia.previsto_minutos.label("previstoMinutos"),
            ApuracaoDia.trabalhado_minutos.label("trabalhadoMinutos"),
            ApuracaoDia.abono_minutos.label("abonoMinutos"),
            ApuracaoDia.tipo_dia.label("tipoDia"),
            _mes(ApuracaoDia.data),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(Departamento, Departamento.id == ApuracaoDia.departamento_id)
        .where(ApuracaoDia.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, ApuracaoDia.data, tenant_id)
    consulta = _aplicar_escopo_apuracao(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    tipo_dia = contexto.filtros.get("tipoDia")
    if tipo_dia:
        consulta = consulta.where(ApuracaoDia.tipo_dia == str(tipo_dia))
    return consulta


registrar_dataset(DATASET_ABSENTEISMO, absenteismo)


# ---------------------------------------------------------------------------
# Item 7 -- Atrasos e saídas antecipadas.
# ---------------------------------------------------------------------------

COLUNAS_ATRASOS_SAIDAS_ANTECIPADAS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("atrasoMinutos", "Atraso", "numero", duracao=True),
    ColunaCatalogo("saidaAntecipadaMinutos", "Saida antecipada", "numero", duracao=True),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("toleranciaAplicadaMinutos", "Tolerancia aplicada", "numero", duracao=True),
    ColunaCatalogo("status", "Status da apuracao", "texto"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_ATRASOS_SAIDAS_ANTECIPADAS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("somenteComOcorrencia", "Somente com atraso ou saida antecipada", "booleano"),
]

AGRUPAMENTOS_ATRASOS_SAIDAS_ANTECIPADAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    _coluna_mes_agrupamento(),
]


def atrasos_saidas_antecipadas(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 7 -- `apuracoes_dia.atraso_minutos`/`saida_antecipada_minutos`."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            ApuracaoDia.data.label("data"),
            ApuracaoDia.atraso_minutos.label("atrasoMinutos"),
            ApuracaoDia.saida_antecipada_minutos.label("saidaAntecipadaMinutos"),
            Colaborador.matricula.label("matricula"),
            ApuracaoDia.colaborador_id.label("colaborador"),
            ApuracaoDia.departamento_id.label("departamento"),
            ApuracaoDia.tolerancia_aplicada_minutos.label("toleranciaAplicadaMinutos"),
            ApuracaoDia.status.label("status"),
            _mes(ApuracaoDia.data),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .where(ApuracaoDia.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, ApuracaoDia.data, tenant_id)
    consulta = _aplicar_escopo_apuracao(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    if bool(contexto.filtros.get("somenteComOcorrencia")):
        consulta = consulta.where(
            sa.or_(ApuracaoDia.atraso_minutos > 0, ApuracaoDia.saida_antecipada_minutos > 0)
        )
    return consulta


registrar_dataset(DATASET_ATRASOS_SAIDAS_ANTECIPADAS, atrasos_saidas_antecipadas)


# ---------------------------------------------------------------------------
# Item 8 -- Faltas (justificadas e injustificadas).
# ---------------------------------------------------------------------------

COLUNAS_FALTAS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("faltaMinutos", "Falta", "numero", duracao=True),
    ColunaCatalogo("temTratamento", "Tem tratamento de abono/justificativa", "booleano"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("abonoMinutos", "Abono", "numero", duracao=True),
    ColunaCatalogo(
        "possuiAfastamentoRetroativo", "Possui afastamento retroativo aprovado", "booleano"
    ),
    ColunaCatalogo("tipoDia", "Tipo do dia", "texto"),
    ColunaCatalogo("status", "Status da apuracao", "texto"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_FALTAS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("somenteSemTratamento", "Somente sem tratamento", "booleano"),
]

AGRUPAMENTOS_FALTAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    _coluna_mes_agrupamento(),
]


def faltas(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Item 8 -- faltas (justificadas e injustificadas): `apuracoes_dia.
    falta_minutos > 0`, com subconsulta de existência contra `tratamentos`
    (categoria `abono`/`justificativa`, status visível) para indicar se a
    falta já tem tratamento associado.

    **`possuiAfastamentoRetroativo` reflete a lacuna do ADR-011 fielmente,
    não a esconde nem a compensa** (proibição 4, PCF §9): um `Tratamento` de
    categoria `afastamento` aprovado para o dia PODE estar presente
    (`possuiAfastamentoRetroativo = true`) e `faltaMinutos` continuar
    exatamente como `apuracoes_dia` gravou -- porque `_carregar_marcacoes_e_
    tratamentos` (F4) não dá efeito numérico a essa categoria (ADR-011).
    Este dataset não zera nem filtra a falta quando esse booleano é
    verdadeiro; mostra os dois fatos lado a lado. `tests/f11/conftest.py`
    semeia exatamente este caso (colaborador C, último dia útil, falta de
    480 minutos com um `Tratamento` categoria `abono` aprovado -- não
    `afastamento` -- então `temTratamento=true`/`possuiAfastamentoRetroativo
    =false` para essa linha)."""
    tem_tratamento = sa.exists(
        sa.select(1)
        .select_from(Tratamento)
        .join(TipoTratamento, TipoTratamento.id == Tratamento.tipo_tratamento_id)
        .where(
            Tratamento.vinculo_id == ApuracaoDia.vinculo_id,
            Tratamento.data_referencia == ApuracaoDia.data,
            TipoTratamento.categoria.in_(_CATEGORIAS_ABONO),
            Tratamento.status.in_(_STATUS_TRATAMENTO_VISIVEL),
        )
    )
    possui_afastamento_retroativo = sa.exists(
        sa.select(1)
        .select_from(Tratamento)
        .join(TipoTratamento, TipoTratamento.id == Tratamento.tipo_tratamento_id)
        .where(
            Tratamento.vinculo_id == ApuracaoDia.vinculo_id,
            Tratamento.data_referencia == ApuracaoDia.data,
            TipoTratamento.categoria == "afastamento",
            Tratamento.status.in_(_STATUS_TRATAMENTO_VISIVEL),
        )
    )
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            ApuracaoDia.data.label("data"),
            ApuracaoDia.falta_minutos.label("faltaMinutos"),
            tem_tratamento.label("temTratamento"),
            Colaborador.matricula.label("matricula"),
            ApuracaoDia.colaborador_id.label("colaborador"),
            ApuracaoDia.departamento_id.label("departamento"),
            ApuracaoDia.abono_minutos.label("abonoMinutos"),
            possui_afastamento_retroativo.label("possuiAfastamentoRetroativo"),
            ApuracaoDia.tipo_dia.label("tipoDia"),
            ApuracaoDia.status.label("status"),
            _mes(ApuracaoDia.data),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .where(ApuracaoDia.tenant_id == tenant_id, ApuracaoDia.falta_minutos > 0)
    )
    consulta = _aplicar_periodo(consulta, contexto, ApuracaoDia.data, tenant_id)
    consulta = _aplicar_escopo_apuracao(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    if bool(contexto.filtros.get("somenteSemTratamento")):
        consulta = consulta.where(~tem_tratamento)
    return consulta


registrar_dataset(DATASET_FALTAS, faltas)


# ---------------------------------------------------------------------------
# Item 9 -- Tempo real: quem está trabalhando agora.
# ---------------------------------------------------------------------------

COLUNAS_TEMPO_REAL: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("ultimaMarcacaoEm", "Ultima marcacao", "data"),
    ColunaCatalogo("situacao", "Situacao", "texto"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("quantidadeMarcacoesHoje", "Quantidade de marcacoes no dia", "numero"),
    ColunaCatalogo("ultimoCanal", "Ultimo canal", "texto"),
]

FILTROS_TEMPO_REAL: list[FiltroCatalogo] = [
    FiltroCatalogo("empresaId", "Empresa", "uuid"),
    FiltroCatalogo("unidadeId", "Unidade", "uuid"),
    FiltroCatalogo("departamentoId", "Departamento", "uuid"),
    FiltroCatalogo("colaboradorId", "Colaborador", "uuid"),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
]

AGRUPAMENTOS_TEMPO_REAL: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("unidade", "Unidade"),
    AgrupamentoCatalogo("empresa", "Empresa"),
]


def tempo_real(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Item 9 -- "quem está trabalhando agora, por unidade". **Único dataset
    deste módulo que lê `marcacoes` diretamente, nunca `apuracoes_dia`**
    (PCF §2.3/§8, ADR-002): no momento em que este relatório é consultado o
    dia normalmente ainda não foi apurado (a apuração roda depois, em lote
    ou no fechamento do dia) -- olhar `apuracoes_dia` mostraria sempre
    "nao_apurado" ou nada, nunca "quem está batendo ponto agora".

    **Heurística de "ainda trabalhando" = número ÍMPAR de marcações no dia
    para o vínculo.** O REP-P não registra sentido (entrada/saída) de forma
    confiável -- `marcacoes.sentido_informado` só é preenchido "QUANDO o
    coletor informa" e nunca por inferência no momento da gravação
    (`ADR-002`/comentário da coluna, `schema.sql`) -- então o pareamento
    real só existe depois da apuração (F3/F4, fora do escopo desta leitura).
    Um vínculo com número ímpar de marcações no dia tem uma "entrada" sem
    "saída" correspondente ainda registrada -- mesmo sinal que a ocorrência
    `marcacao_impar`/coluna `apuracoes_dia.marcacoes_impares` usa depois da
    apuração, aplicado aqui em tempo real, antes dela. `situacao` é sempre
    `"trabalhando"` (o único estado que este `WHERE` produz -- um relatório
    de presença futuro poderia expor `"fora"` numa segunda consulta, fora
    do escopo desta fase). Documentado como heurística, não como fato
    garantido (pode haver falha na sequência de marcações que o motor de
    apuração trataria como ocorrência).

    Implementado com funções de janela (`COUNT(*) OVER`, `ROW_NUMBER() OVER
    PARTITION BY`), nunca `GROUP BY` -- respeita a letra do contrato de
    `catalogo.py` ("a função só filtra e junta tabelas, nunca faz `GROUP
    BY`"), porque a entidade relatada aqui É "o vínculo, com seu status
    atual" (colapsar eventos de marcação para chegar nessa entidade é
    inerente ao relatório, não uma pré-agregação que concorreria com um
    `agrupamento` pedido pelo cliente sobre outro eixo, como `unidade`)."""
    # Fronteira do dia em UTC (simplificação documentada: o ideal seria o
    # fuso da empresa/unidade, mas `ContextoConsulta` não carrega fuso e
    # `marcacoes.datahora_marcacao` é `TIMESTAMPTZ` -- comparar contra um
    # datetime "naive" quebraria o driver assíncrono, então normalizamos em
    # UTC em vez de deixar o valor sem fuso).
    referencia = contexto.de or dt.date.today()
    ate = contexto.ate or referencia
    inicio_dia = dt.datetime.combine(referencia, dt.time.min, tzinfo=dt.UTC)
    fim_dia = dt.datetime.combine(ate, dt.time.max, tzinfo=dt.UTC)

    base = sa.select(
        Marcacao.colaborador_id.label("colaborador"),
        Marcacao.vinculo_id.label("vinculo"),
        Marcacao.empresa_id.label("empresa"),
        Marcacao.unidade_id.label("unidade"),
        Marcacao.canal.label("ultimoCanal"),
        Marcacao.datahora_marcacao.label("ultimaMarcacaoEm"),
        func.count().over(partition_by=Marcacao.vinculo_id).label("_quantidade"),
        func.row_number()
        .over(partition_by=Marcacao.vinculo_id, order_by=Marcacao.datahora_marcacao.desc())
        .label("_linha"),
    ).where(
        Marcacao.tenant_id == tenant_id,
        Marcacao.vinculo_id.is_not(None),
        Marcacao.datahora_marcacao >= inicio_dia,
        Marcacao.datahora_marcacao <= fim_dia,
    )
    if contexto.empresa_id is not None:
        base = base.where(Marcacao.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        base = base.where(Marcacao.unidade_id == contexto.unidade_id)
    if contexto.colaborador_id is not None:
        base = base.where(Marcacao.colaborador_id == contexto.colaborador_id)

    sub = base.subquery()
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            sub.c["ultimaMarcacaoEm"].label("ultimaMarcacaoEm"),
            sa.literal("trabalhando").label("situacao"),
            Colaborador.matricula.label("matricula"),
            sub.c["colaborador"].label("colaborador"),
            sub.c["vinculo"].label("vinculo"),
            sub.c["empresa"].label("empresa"),
            sub.c["unidade"].label("unidade"),
            sub.c["_quantidade"].label("quantidadeMarcacoesHoje"),
            sub.c["ultimoCanal"].label("ultimoCanal"),
        )
        .select_from(sub)
        .join(Colaborador, Colaborador.id == sub.c["colaborador"])
        .where(sub.c["_linha"] == 1, sub.c["_quantidade"] % 2 == 1)
    )
    if contexto.departamento_id is not None:
        consulta = consulta.join(Vinculo, Vinculo.id == sub.c["vinculo"]).where(
            Vinculo.departamento_id == contexto.departamento_id
        )
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    return consulta


registrar_dataset(DATASET_TEMPO_REAL, tempo_real)


# ---------------------------------------------------------------------------
# Item 10 -- Ocorrências e inconsistências.
# ---------------------------------------------------------------------------

COLUNAS_OCORRENCIAS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("codigo", "Codigo da ocorrencia", "texto"),
    ColunaCatalogo("severidade", "Severidade", "texto"),
    ColunaCatalogo("status", "Status", "texto"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("descricao", "Descricao", "texto"),
    ColunaCatalogo("resolucao", "Resolucao", "texto"),
    ColunaCatalogo("resolvidaEm", "Resolvida em", "data"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_OCORRENCIAS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("codigo", "Codigo da ocorrencia", "texto"),
    FiltroCatalogo("severidade", "Severidade", "texto"),
    FiltroCatalogo("status", "Status", "texto"),
]

AGRUPAMENTOS_OCORRENCIAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("codigo", "Codigo da ocorrencia"),
    _coluna_mes_agrupamento(),
]


def ocorrencias(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Item 10 -- ocorrências e inconsistências: leitura direta de
    `ocorrencias` (os 18 códigos de `ocorrencias.codigo`, `schema.sql` linha
    ~2561), com filtro por `codigo`/`severidade`/`status`."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            Ocorrencia.data.label("data"),
            Ocorrencia.codigo.label("codigo"),
            Ocorrencia.severidade.label("severidade"),
            Ocorrencia.status.label("status"),
            Colaborador.matricula.label("matricula"),
            Ocorrencia.colaborador_id.label("colaborador"),
            Ocorrencia.vinculo_id.label("vinculo"),
            Vinculo.empresa_id.label("empresa"),
            Vinculo.unidade_id.label("unidade"),
            Vinculo.departamento_id.label("departamento"),
            Ocorrencia.descricao.label("descricao"),
            Ocorrencia.resolucao.label("resolucao"),
            Ocorrencia.resolvida_em.label("resolvidaEm"),
            _mes(Ocorrencia.data),
        )
        .select_from(Ocorrencia)
        .join(Colaborador, Colaborador.id == Ocorrencia.colaborador_id)
        .outerjoin(Vinculo, Vinculo.id == Ocorrencia.vinculo_id)
        .where(Ocorrencia.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, Ocorrencia.data, tenant_id)
    consulta = _aplicar_escopo_vinculo(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(Ocorrencia.colaborador_id == contexto.colaborador_id)
    codigo = contexto.filtros.get("codigo")
    if codigo:
        consulta = consulta.where(Ocorrencia.codigo == str(codigo))
    severidade = contexto.filtros.get("severidade")
    if severidade:
        consulta = consulta.where(Ocorrencia.severidade == str(severidade))
    status = contexto.filtros.get("status")
    if status:
        consulta = consulta.where(Ocorrencia.status == str(status))
    return consulta


registrar_dataset(DATASET_OCORRENCIAS, ocorrencias)


# ---------------------------------------------------------------------------
# Item 11 -- Abonos e justificativas.
# ---------------------------------------------------------------------------

COLUNAS_ABONOS_JUSTIFICATIVAS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("dataReferencia", "Data", "data"),
    ColunaCatalogo("motivo", "Motivo", "texto"),
    ColunaCatalogo("status", "Status", "texto"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("tipoTratamentoCodigo", "Tipo de tratamento", "texto"),
    ColunaCatalogo("tipoTratamentoNome", "Nome do tipo de tratamento", "texto"),
    ColunaCatalogo("categoria", "Categoria", "texto"),
    ColunaCatalogo("minutosAjuste", "Minutos de ajuste", "numero", duracao=True),
    ColunaCatalogo("origem", "Origem", "texto"),
    ColunaCatalogo("aprovadoEm", "Aprovado em", "data"),
    ColunaCatalogo("mes", "Mes", "data"),
]

FILTROS_ABONOS_JUSTIFICATIVAS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("tipoTratamentoId", "Tipo de tratamento", "uuid"),
    FiltroCatalogo("status", "Status", "texto"),
    FiltroCatalogo("categoria", "Categoria", "texto"),
]

AGRUPAMENTOS_ABONOS_JUSTIFICATIVAS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("categoria", "Categoria"),
    _coluna_mes_agrupamento(),
]


def abonos_justificativas(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 11 -- abonos e justificativas: `tratamentos` cujo
    `tipos_tratamento.categoria` é `abono` ou `justificativa`."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            Tratamento.data_referencia.label("dataReferencia"),
            Tratamento.motivo.label("motivo"),
            Tratamento.status.label("status"),
            Colaborador.matricula.label("matricula"),
            Tratamento.colaborador_id.label("colaborador"),
            Tratamento.vinculo_id.label("vinculo"),
            Vinculo.empresa_id.label("empresa"),
            Vinculo.unidade_id.label("unidade"),
            Vinculo.departamento_id.label("departamento"),
            TipoTratamento.codigo.label("tipoTratamentoCodigo"),
            TipoTratamento.nome.label("tipoTratamentoNome"),
            TipoTratamento.categoria.label("categoria"),
            Tratamento.minutos_ajuste.label("minutosAjuste"),
            Tratamento.origem.label("origem"),
            Tratamento.aprovado_em.label("aprovadoEm"),
            _mes(Tratamento.data_referencia),
        )
        .select_from(Tratamento)
        .join(TipoTratamento, TipoTratamento.id == Tratamento.tipo_tratamento_id)
        .join(Colaborador, Colaborador.id == Tratamento.colaborador_id)
        .outerjoin(Vinculo, Vinculo.id == Tratamento.vinculo_id)
        .where(
            Tratamento.tenant_id == tenant_id,
            TipoTratamento.categoria.in_(_CATEGORIAS_ABONO),
        )
    )
    consulta = _aplicar_periodo(consulta, contexto, Tratamento.data_referencia, tenant_id)
    consulta = _aplicar_escopo_vinculo(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    tipo_tratamento_id = _uuid_do_filtro(
        contexto.filtros.get("tipoTratamentoId"), chave="tipoTratamentoId"
    )
    if tipo_tratamento_id is not None:
        consulta = consulta.where(Tratamento.tipo_tratamento_id == tipo_tratamento_id)
    status = contexto.filtros.get("status")
    if status:
        consulta = consulta.where(Tratamento.status == str(status))
    categoria = contexto.filtros.get("categoria")
    if categoria:
        consulta = consulta.where(TipoTratamento.categoria == str(categoria))
    return consulta


registrar_dataset(DATASET_ABONOS_JUSTIFICATIVAS, abonos_justificativas)


# ---------------------------------------------------------------------------
# Item 12 -- Férias e afastamentos.
# ---------------------------------------------------------------------------

COLUNAS_FERIAS_AFASTAMENTOS: list[ColunaCatalogo] = [
    ColunaCatalogo("colaboradorNome", "Colaborador", "texto"),
    ColunaCatalogo("categoria", "Categoria", "texto"),
    ColunaCatalogo("dataInicio", "Data de inicio", "data"),
    ColunaCatalogo("dataFim", "Data de fim", "data"),
    ColunaCatalogo("matricula", "Matricula", "texto"),
    ColunaCatalogo("colaborador", "Colaborador (id)", "uuid"),
    ColunaCatalogo("vinculo", "Vinculo", "uuid"),
    ColunaCatalogo("empresa", "Empresa", "uuid"),
    ColunaCatalogo("unidade", "Unidade", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("tipoAfastamentoCodigo", "Tipo de afastamento", "texto"),
    ColunaCatalogo("tipoAfastamentoNome", "Nome do tipo de afastamento", "texto"),
    ColunaCatalogo("diasPrevistos", "Dias previstos", "numero"),
    ColunaCatalogo("status", "Status", "texto"),
    ColunaCatalogo("remunerado", "Remunerado", "booleano"),
    ColunaCatalogo("abonaDia", "Abona o dia", "booleano"),
    ColunaCatalogo("origem", "Origem", "texto"),
]

FILTROS_FERIAS_AFASTAMENTOS: list[FiltroCatalogo] = [
    *_filtros_escopo_padrao(),
    FiltroCatalogo("incluirInativos", "Incluir inativos", "booleano"),
    FiltroCatalogo("categoria", "Categoria", "texto"),
    FiltroCatalogo("status", "Status", "texto"),
]

AGRUPAMENTOS_FERIAS_AFASTAMENTOS: list[AgrupamentoCatalogo] = [
    AgrupamentoCatalogo("colaborador", "Colaborador"),
    AgrupamentoCatalogo("departamento", "Departamento"),
    AgrupamentoCatalogo("categoria", "Categoria"),
]


def ferias_afastamentos(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Item 12 -- férias e afastamentos: `afastamentos` (todas as categorias
    de `tipos_afastamento`, não só férias -- o nome do relatório em
    `PROJETO.md` §9 agrupa os dois porque `ferias` é só mais uma categoria
    de `tipos_afastamento.categoria`, não uma tabela separada)."""
    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            TipoAfastamento.categoria.label("categoria"),
            Afastamento.data_inicio.label("dataInicio"),
            Afastamento.data_fim.label("dataFim"),
            Colaborador.matricula.label("matricula"),
            Afastamento.colaborador_id.label("colaborador"),
            Afastamento.vinculo_id.label("vinculo"),
            Vinculo.empresa_id.label("empresa"),
            Vinculo.unidade_id.label("unidade"),
            Vinculo.departamento_id.label("departamento"),
            TipoAfastamento.codigo.label("tipoAfastamentoCodigo"),
            TipoAfastamento.nome.label("tipoAfastamentoNome"),
            Afastamento.dias_previstos.label("diasPrevistos"),
            Afastamento.status.label("status"),
            TipoAfastamento.remunerado.label("remunerado"),
            TipoAfastamento.abona_dia.label("abonaDia"),
            Afastamento.origem.label("origem"),
        )
        .select_from(Afastamento)
        .join(TipoAfastamento, TipoAfastamento.id == Afastamento.tipo_afastamento_id)
        .join(Colaborador, Colaborador.id == Afastamento.colaborador_id)
        .outerjoin(Vinculo, Vinculo.id == Afastamento.vinculo_id)
        .where(Afastamento.tenant_id == tenant_id)
    )
    consulta = _aplicar_periodo(consulta, contexto, Afastamento.data_inicio, tenant_id)
    consulta = _aplicar_escopo_vinculo(consulta, contexto)
    consulta = _aplicar_incluir_inativos(consulta, contexto)
    categoria = contexto.filtros.get("categoria")
    if categoria:
        consulta = consulta.where(TipoAfastamento.categoria == str(categoria))
    status = contexto.filtros.get("status")
    if status:
        consulta = consulta.where(Afastamento.status == str(status))
    return consulta


registrar_dataset(DATASET_FERIAS_AFASTAMENTOS, ferias_afastamentos)
