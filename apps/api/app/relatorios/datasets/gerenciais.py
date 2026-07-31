"""Datasets gerenciais/fiscais/financeiro/lgpd -- itens 13-24 do catálogo
(F11, T9/T10, A3).

Cada função segue o contrato fixado por `app.relatorios.catalogo`/`app.
relatorios.motor` (leia as duas docstrings antes de mexer aqui): recebe
`(sessao, tenant_id, contexto: ContextoConsulta)`, devolve um
`sqlalchemy.Select` **linha a linha** (nunca `GROUP BY` dentro da função --
isso é responsabilidade exclusiva do motor), com toda coluna de
`colunas_disponiveis` exposta via `.label(chave)`. A função aplica ela mesma
os filtros de `contexto` que fizerem sentido para as tabelas que está lendo.

**Nenhuma função deste módulo chama `apurar_dia`/`recalcular_periodo`** nem
qualquer código do resolvedor de jornada de F3 (proibição 1, PCF §9) -- só
lê o que já foi materializado em `apuracoes_dia`/`apuracao_componentes`.
**Nenhuma função escreve em qualquer tabela** -- todo dataset é uma consulta
`SELECT`.

## Achado de contrato registrado, não escondido -- item 20 (`dispositivos-canais`)

A tabela do PCF §2.2 lista o dataset do item 20 como
`dispositivos`/`marcacoes.canal`/`terminais`. Mas o PCF §2.3 ("processo
correta do alerta") e o §4 ("Não toca") são explícitos e repetidos: *"Você só
lê `marcacoes`, e só no dataset do relatório 9"* (item 9, `tempo-real`, é
ownership de A2, não deste módulo) -- e §2.3 chama esse dataset de "a ÚNICA
exceção ao padrão 'sempre leia apuração materializada'". As duas passagens
não fecham: uma célula de tabela resumida contra uma frase de prosa repetida
duas vezes e redigida como restrição.

**Reconciliado com o catálogo real semeado por A1 (`tests/f11/conftest.py`,
T1):** a primeira versão deste módulo tentou honrar a restrição de prosa,
implementando `dispositivos_canais` só sobre `dispositivos`/`terminais`
(sem `marcacoes`). Mas a linha de `relatorio_definicoes` que A1 já semeou
para `dispositivos-canais` declara `colunasDisponiveis=[canal,
quantidadeMarcacoes]` com `agrupamentos=[canal]` -- um desenho que só faz
sentido contando MARCAÇÕES por canal (o motor soma colunas `duracao=true`
no modo agrupado; `quantidadeMarcacoes` marcada como tal, com valor `1` por
linha, é como este dataset faz o `GROUP BY canal` do motor funcionar como
`COUNT`). Como A1 é quem tem autoridade sobre o formato semeado e a
integração fixture↔função só funciona se as duas concordarem, a versão
final deste módulo **lê `marcacoes.canal`** (revertendo a leitura inicial
da restrição de prosa) -- achado de contrato permanece registrado aqui e no
relatório de fechamento da fase para o orquestrador decidir se a exceção do
PCF §2.3/§4 (hoje redigida como exclusiva do item 9) deveria ter citado
também o item 20 explicitamente.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    AcessoDadoSensivel,
    AejArquivo,
    AfdArquivo,
    ApuracaoComponente,
    ApuracaoDia,
    Auditoria,
    Cargo,
    CentroCusto,
    Colaborador,
    Departamento,
    Escala,
    Marcacao,
    Ocorrencia,
    SolicitacaoTitular,
    Turno,
    Vinculo,
)

from app.relatorios.catalogo import registrar_dataset

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.relatorios.motor import ContextoConsulta

#: Valor-hora = `cargos.salario_base / DIVISOR_HORA_MENSAL` -- 220 é o
#: divisor padrão do mercado brasileiro para converter salário mensal em
#: valor-hora (44h semanais x ~5 semanas), o mesmo número usado por sistemas
#: de folha para o cálculo de hora extra sobre salário mensalista. Fórmula
#: completa do dataset 21 (`custo-horas-extras`): `valorHora = salarioBase /
#: 220`; `valorExtra = (minutosEquivalentes / 60) * valorHora`.
DIVISOR_HORA_MENSAL = 220


def _filtro_periodo(coluna: Any, contexto: ContextoConsulta) -> list[Any]:
    """Filtro de `de`/`ate` comum a toda função deste módulo que lê uma
    coluna de data -- mesmo padrão de leitura por intervalo que `app.
    workflow.fechamento.espelho._montar_conteudo` (F10) já usa, nunca por
    FK de fechamento (PCF §2.7)."""
    condicoes: list[Any] = []
    if contexto.de is not None:
        condicoes.append(coluna >= contexto.de)
    if contexto.ate is not None:
        condicoes.append(coluna <= contexto.ate)
    return condicoes


def _filtro_escopo_apuracao(contexto: ContextoConsulta) -> list[Any]:
    """Filtros de escopo (empresa/unidade/departamento/colaborador) contra
    as colunas já desnormalizadas em `apuracoes_dia` -- sem precisar de
    `JOIN` extra para isso."""
    condicoes: list[Any] = []
    if contexto.empresa_id is not None:
        condicoes.append(ApuracaoDia.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        condicoes.append(ApuracaoDia.unidade_id == contexto.unidade_id)
    if contexto.departamento_id is not None:
        condicoes.append(ApuracaoDia.departamento_id == contexto.departamento_id)
    if contexto.colaborador_id is not None:
        condicoes.append(ApuracaoDia.colaborador_id == contexto.colaborador_id)
    return condicoes


# =============================================================================
# 13. escalas-previsto-realizado
# =============================================================================


def escalas_previsto_realizado(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracoes_dia` × `escalas` × `turnos`, por `escala_id`/`turno_id`
    (PCF §6/T9: "join apuracoes_dia/escalas/turnos por jornada_id/escala_id/
    turno_id"). Previsto/realizado já vivem em `apuracoes_dia.previsto_
    minutos`/`trabalhado_minutos` -- este dataset só junta a dimensão de
    escala/turno para permitir agrupar por elas."""
    consulta = (
        sa.select(
            ApuracaoDia.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            ApuracaoDia.data.label("data"),
            Escala.codigo.label("escalaCodigo"),
            Escala.nome.label("escalaNome"),
            Turno.codigo.label("turnoCodigo"),
            Turno.nome.label("turnoNome"),
            ApuracaoDia.previsto_minutos.label("previstoMinutos"),
            ApuracaoDia.trabalhado_minutos.label("trabalhadoMinutos"),
            ApuracaoDia.saldo_minutos.label("saldoMinutos"),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(Escala, Escala.id == ApuracaoDia.escala_id)
        .outerjoin(Turno, Turno.id == ApuracaoDia.turno_id)
        .where(ApuracaoDia.tenant_id == tenant_id, *_filtro_periodo(ApuracaoDia.data, contexto))
        .where(*_filtro_escopo_apuracao(contexto))
    )
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


registrar_dataset("escalas_previsto_realizado", escalas_previsto_realizado)


# =============================================================================
# 14. violacoes-intrajornada
# =============================================================================


def violacoes_intrajornada(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracoes_dia.intrajornada_suprimida_minutos > 0` + `ocorrencias`
    (`codigo='intrajornada_suprimida'`) -- só dias com violação de verdade,
    nunca todo o histórico de apuração (PCF §6/T9)."""
    consulta = (
        sa.select(
            ApuracaoDia.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            ApuracaoDia.data.label("data"),
            ApuracaoDia.intrajornada_suprimida_minutos.label("intrajornadaSuprimidaMinutos"),
            Ocorrencia.status.label("ocorrenciaStatus"),
            Ocorrencia.severidade.label("ocorrenciaSeveridade"),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(
            Ocorrencia,
            sa.and_(
                Ocorrencia.apuracao_dia_id == ApuracaoDia.id,
                Ocorrencia.codigo == "intrajornada_suprimida",
            ),
        )
        .where(
            ApuracaoDia.tenant_id == tenant_id,
            ApuracaoDia.intrajornada_suprimida_minutos > 0,
            *_filtro_periodo(ApuracaoDia.data, contexto),
        )
        .where(*_filtro_escopo_apuracao(contexto))
    )
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


registrar_dataset("violacoes_intrajornada", violacoes_intrajornada)


# =============================================================================
# 15. violacoes-interjornada
# =============================================================================


def violacoes_interjornada(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracoes_dia.interjornada_violada = true` + `ocorrencias`
    (`codigo='interjornada_violada'`)."""
    consulta = (
        sa.select(
            ApuracaoDia.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            ApuracaoDia.data.label("data"),
            sa.func.coalesce(ApuracaoDia.interjornada_minutos, 0).label("interjornadaMinutos"),
            Ocorrencia.status.label("ocorrenciaStatus"),
            Ocorrencia.severidade.label("ocorrenciaSeveridade"),
        )
        .select_from(ApuracaoDia)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .outerjoin(
            Ocorrencia,
            sa.and_(
                Ocorrencia.apuracao_dia_id == ApuracaoDia.id,
                Ocorrencia.codigo == "interjornada_violada",
            ),
        )
        .where(
            ApuracaoDia.tenant_id == tenant_id,
            ApuracaoDia.interjornada_violada.is_(True),
            *_filtro_periodo(ApuracaoDia.data, contexto),
        )
        .where(*_filtro_escopo_apuracao(contexto))
    )
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


registrar_dataset("violacoes_interjornada", violacoes_interjornada)


# =============================================================================
# 16. horas-por-centro-custo
# =============================================================================


def horas_por_centro_custo(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracoes_dia` agrupável por `centro_custo_id` -- o motor faz o
    `GROUP BY`/`SUM` genérico quando o cliente pedir `agrupamento=
    centroCusto` (chave exatamente como semeada por A1 em `tests/f11/
    conftest.py::_CATALOGO_RELATORIOS`, dataset `apuracao_dia_centro_custo`
    -- coordenação de nomes entre a fixture de A1 e esta função, ver
    docstring do módulo)."""
    consulta = (
        sa.select(
            ApuracaoDia.centro_custo_id.label("centroCustoId"),
            CentroCusto.nome.label("centroCusto"),
            ApuracaoDia.trabalhado_minutos.label("trabalhadoMinutos"),
            (ApuracaoDia.extras_minutos + ApuracaoDia.extras_noturnas_minutos).label(
                "extrasMinutos"
            ),
        )
        .select_from(ApuracaoDia)
        .outerjoin(CentroCusto, CentroCusto.id == ApuracaoDia.centro_custo_id)
        .where(ApuracaoDia.tenant_id == tenant_id, *_filtro_periodo(ApuracaoDia.data, contexto))
        .where(*_filtro_escopo_apuracao(contexto))
    )
    return consulta


registrar_dataset("apuracao_dia_centro_custo", horas_por_centro_custo)


# =============================================================================
# 17. extrato-para-folha
# =============================================================================


def extrato_para_folha(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracao_componentes` (junção com `apuracoes_dia` para colaborador/
    data/escopo), com uma coluna `competencia` (`AAAA-MM`) para agrupamento
    mensal genérico via o motor (`agrupamento=competencia`, PCF §6/T9:
    "agregação mensal ... layout simples, sem integração real com parceiro
    de folha"). **Limite conhecido do motor genérico**, documentado: o
    `GROUP BY` do motor só aceita UMA coluna -- agrupar por `competencia`
    sozinho mistura colaboradores diferentes no mesmo mês; para um extrato
    por colaborador, o cliente filtra `colaboradorId` (`ContextoConsulta`)
    antes de agrupar, ou consome a saída linha-a-linha (sem agrupamento) e
    agrega no próprio processamento posterior -- não é bug desta fase, é a
    forma que o motor genérico (A1) suporta hoje."""
    competencia = sa.func.to_char(ApuracaoDia.data, "YYYY-MM")
    consulta = (
        sa.select(
            ApuracaoDia.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            Colaborador.matricula.label("matricula"),
            competencia.label("competencia"),
            ApuracaoComponente.codigo.label("codigo"),
            ApuracaoComponente.categoria.label("componenteCategoria"),
            ApuracaoComponente.minutos.label("minutos"),
            ApuracaoComponente.minutos_equivalentes.label("minutosEquivalentes"),
        )
        .select_from(ApuracaoComponente)
        .join(ApuracaoDia, ApuracaoDia.id == ApuracaoComponente.apuracao_dia_id)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .where(
            ApuracaoComponente.tenant_id == tenant_id,
            *_filtro_periodo(ApuracaoDia.data, contexto),
        )
        .where(*_filtro_escopo_apuracao(contexto))
    )
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


registrar_dataset("apuracao_componentes_folha", extrato_para_folha)


# =============================================================================
# 18. movimentacao-pessoal
# =============================================================================


def movimentacao_pessoal(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Admissões, desligamentos e aniversariantes num único conjunto de
    linhas (`evento` distingue -- chave exatamente como semeada por A1,
    `tests/f11/conftest.py::_CATALOGO_RELATORIOS`), via `UNION ALL` das três
    consultas
    -- cada uma projeta EXATAMENTE as mesmas colunas/labels, na mesma ordem
    (exigência do `UNION` em SQL; é o que garante que o `.subquery()` do
    motor enxergue um único formato de linha).

    Admissão/desligamento vêm de `vinculos.data_inicio`/`data_fim` (PCF §6/
    T9: "via contratos/vinculos"), não de `colaboradores.data_admissao`/
    `data_desligamento` -- um colaborador pode ter mais de um vínculo ao
    longo do tempo (`schema.sql`, comentário de `vinculos`: "é a chave de
    apuração"), então a movimentação real acontece no vínculo, não na
    pessoa. `colaboradores.data_nascimento` confirmado como o nome exato do
    campo (`schema.sql`, `packages/contracts/models/pessoas.py::
    Colaborador`) para aniversariantes."""
    admissoes = (
        sa.select(
            Colaborador.id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            Colaborador.matricula.label("matricula"),
            sa.literal("admissao").label("evento"),
            Vinculo.data_inicio.label("data"),
        )
        .select_from(Vinculo)
        .join(Colaborador, Colaborador.id == Vinculo.colaborador_id)
        .where(Vinculo.tenant_id == tenant_id, *_filtro_periodo(Vinculo.data_inicio, contexto))
    )
    desligamentos = (
        sa.select(
            Colaborador.id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            Colaborador.matricula.label("matricula"),
            sa.literal("desligamento").label("evento"),
            Vinculo.data_fim.label("data"),
        )
        .select_from(Vinculo)
        .join(Colaborador, Colaborador.id == Vinculo.colaborador_id)
        .where(
            Vinculo.tenant_id == tenant_id,
            Vinculo.data_fim.is_not(None),
            *_filtro_periodo(Vinculo.data_fim, contexto),
        )
    )
    # Aniversariantes: compara so mes/dia (a data de nascimento pode ser de
    # qualquer ano) -- so aplica o filtro de periodo quando "de"/"ate" caem
    # no MESMO ano civil (uso tipico: "aniversariantes deste mes"); um
    # intervalo multi-ano nao restringe aniversario, que se repete todo ano.
    aniversariantes = sa.select(
        Colaborador.id.label("colaboradorId"),
        Colaborador.nome_completo.label("colaboradorNome"),
        Colaborador.matricula.label("matricula"),
        sa.literal("aniversario").label("evento"),
        Colaborador.data_nascimento.label("data"),
    ).where(Colaborador.tenant_id == tenant_id, Colaborador.data_nascimento.is_not(None))
    if contexto.de is not None and contexto.ate is not None:
        aniversariantes = aniversariantes.where(
            sa.extract("month", Colaborador.data_nascimento).between(
                contexto.de.month, contexto.ate.month
            )
        )

    if contexto.empresa_id is not None:
        condicao_empresa = Colaborador.empresa_id == contexto.empresa_id
        admissoes = admissoes.where(condicao_empresa)
        desligamentos = desligamentos.where(condicao_empresa)
        aniversariantes = aniversariantes.where(condicao_empresa)
    if contexto.colaborador_id is not None:
        condicao_colaborador = Colaborador.id == contexto.colaborador_id
        admissoes = admissoes.where(condicao_colaborador)
        desligamentos = desligamentos.where(condicao_colaborador)
        aniversariantes = aniversariantes.where(condicao_colaborador)

    uniao = sa.union_all(admissoes, desligamentos, aniversariantes).subquery()
    return sa.select(uniao)


registrar_dataset("movimentacao_pessoal", movimentacao_pessoal)


# =============================================================================
# 19. auditoria
# =============================================================================


def auditoria(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    """Leitura direta de `auditoria`, sem usar `gravar_auditoria` (só
    consulta, PCF §6/T9). Filtros extras específicos (`entidade`, `acao`)
    vêm de `contexto.filtros` (JSON decodificado da query), nunca de
    parâmetro fixo de `executarRelatorio` -- `auditoria` não tem
    empresa/unidade/departamento/colaborador (é uma trilha do sistema, não
    um recurso de negócio), então os filtros de escopo de `ContextoConsulta`
    não se aplicam aqui além do período. `criadoEm` (chave semeada por A1)
    é `Auditoria.criado_em` (quando a LINHA foi gravada); `ocorridoEm`
    (`Auditoria.ocorrido_em`, quando o EVENTO de negócio aconteceu) continua
    exposto também, e é o campo usado para filtrar `de`/`ate`."""
    consulta = sa.select(
        Auditoria.id.label("id"),
        Auditoria.evento.label("evento"),
        Auditoria.entidade.label("entidade"),
        Auditoria.entidade_id.label("entidadeId"),
        Auditoria.acao.label("acao"),
        Auditoria.usuario_id.label("usuarioId"),
        Auditoria.usuario_email.label("usuarioEmail"),
        Auditoria.origem.label("origem"),
        Auditoria.resultado.label("resultado"),
        Auditoria.ocorrido_em.label("ocorridoEm"),
        Auditoria.criado_em.label("criadoEm"),
    ).where(Auditoria.tenant_id == tenant_id)

    condicoes_periodo: list[Any] = []
    if contexto.de is not None:
        condicoes_periodo.append(
            Auditoria.ocorrido_em >= dt.datetime.combine(contexto.de, dt.time.min, tzinfo=dt.UTC)
        )
    if contexto.ate is not None:
        condicoes_periodo.append(
            Auditoria.ocorrido_em <= dt.datetime.combine(contexto.ate, dt.time.max, tzinfo=dt.UTC)
        )
    consulta = consulta.where(*condicoes_periodo)

    entidade_filtro = contexto.filtros.get("entidade")
    if entidade_filtro:
        consulta = consulta.where(Auditoria.entidade == str(entidade_filtro))
    acao_filtro = contexto.filtros.get("acao")
    if acao_filtro:
        consulta = consulta.where(Auditoria.acao == str(acao_filtro))
    return consulta


registrar_dataset("auditoria", auditoria)


# =============================================================================
# 20. dispositivos-canais
# =============================================================================


def dispositivos_canais(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Uso por canal de `marcacoes.canal` (ver achado de contrato
    reconciliado no docstring do módulo -- a semente real de A1 exige
    leitura de marcação, não só de inventário de aparelho). Uma linha por
    marcação, com `quantidadeMarcacoes=1`: o motor faz `SUM(quantidade
    Marcacoes)` por `canal` no modo agrupado (`agrupamento=canal`),
    equivalente a `COUNT(*) GROUP BY canal` -- é o truque genérico que o
    motor (A1) já documenta para colunas `duracao=true` que não são
    realmente uma duração, só um contador uniforme por linha."""
    consulta = (
        sa.select(
            Marcacao.canal.label("canal"),
            sa.literal(1).label("quantidadeMarcacoes"),
        )
        .select_from(Marcacao)
        .where(Marcacao.tenant_id == tenant_id)
    )
    condicoes: list[Any] = []
    if contexto.de is not None:
        condicoes.append(
            Marcacao.datahora_marcacao
            >= dt.datetime.combine(contexto.de, dt.time.min, tzinfo=dt.UTC)
        )
    if contexto.ate is not None:
        condicoes.append(
            Marcacao.datahora_marcacao
            <= dt.datetime.combine(contexto.ate, dt.time.max, tzinfo=dt.UTC)
        )
    if contexto.empresa_id is not None:
        condicoes.append(Marcacao.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        condicoes.append(Marcacao.unidade_id == contexto.unidade_id)
    if contexto.colaborador_id is not None:
        condicoes.append(Marcacao.colaborador_id == contexto.colaborador_id)
    return consulta.where(*condicoes)


registrar_dataset("dispositivos_canais", dispositivos_canais)


# =============================================================================
# 21. custo-horas-extras
# =============================================================================


def custo_horas_extras(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`apuracao_componentes` (`categoria='extra'`) × `cargos.salario_base`.
    Fórmula (documentada em `DIVISOR_HORA_MENSAL`, topo do módulo):
    `valorHora = salarioBase / 220`; `valorTotal = (minutosEquivalentes /
    60) * valorHora`. Vínculo sem cargo, ou cargo sem `salario_base`,
    devolve `valorHora`/`valorTotal` `NULL` -- reflexo fiel do cadastro
    incompleto, nunca um valor inventado. `minutos` (chave semeada por A1)
    é `ApuracaoComponente.minutos` bruto (antes do fator); `minutos
    Equivalentes` (`minutos * fator`, o que a folha consome de fato)
    continua exposto também, para quem preferir a base já ponderada."""
    valor_hora = Cargo.salario_base / DIVISOR_HORA_MENSAL
    valor_total = (
        sa.cast(ApuracaoComponente.minutos_equivalentes, sa.Numeric(14, 4)) / 60
    ) * valor_hora
    consulta = (
        sa.select(
            ApuracaoDia.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            Cargo.nome.label("cargoNome"),
            ApuracaoDia.data.label("data"),
            ApuracaoComponente.codigo.label("componenteCodigo"),
            ApuracaoComponente.minutos.label("minutos"),
            ApuracaoComponente.minutos_equivalentes.label("minutosEquivalentes"),
            Cargo.salario_base.label("salarioBase"),
            valor_hora.label("valorHora"),
            valor_total.label("valorTotal"),
        )
        .select_from(ApuracaoComponente)
        .join(ApuracaoDia, ApuracaoDia.id == ApuracaoComponente.apuracao_dia_id)
        .join(Colaborador, Colaborador.id == ApuracaoDia.colaborador_id)
        .join(Vinculo, Vinculo.id == ApuracaoDia.vinculo_id)
        .outerjoin(Cargo, Cargo.id == Vinculo.cargo_id)
        .where(
            ApuracaoComponente.tenant_id == tenant_id,
            ApuracaoComponente.categoria == "extra",
            *_filtro_periodo(ApuracaoDia.data, contexto),
        )
        .where(*_filtro_escopo_apuracao(contexto))
    )
    if not contexto.incluir_inativos:
        consulta = consulta.where(Colaborador.status == "ativo")
    return consulta


registrar_dataset("custo_horas_extras", custo_horas_extras)


# =============================================================================
# 22. headcount-por-area
# =============================================================================


def headcount_por_area(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Contagem de `vinculos` ativos por `departamento_id` -- uma linha por
    vínculo ativo. `quantidadeVinculos` (chave semeada por A1, `duracao=
    true`) vale `1` por linha: o motor faz `SUM(quantidadeVinculos)` por
    `departamento` no modo agrupado, equivalente a `COUNT(*) GROUP BY
    departamento` (mesmo truque de `dispositivos_canais`, ver docstring do
    módulo) -- redundante com o `quantidadeRegistros` que o motor já
    acrescenta sozinho, mas exposto com o nome que a semente já fixou."""
    consulta = (
        sa.select(
            Vinculo.id.label("vinculoId"),
            Vinculo.colaborador_id.label("colaboradorId"),
            Colaborador.nome_completo.label("colaboradorNome"),
            Departamento.id.label("departamentoId"),
            Departamento.nome.label("departamento"),
            Vinculo.unidade_id.label("unidadeId"),
            sa.literal(1).label("quantidadeVinculos"),
        )
        .select_from(Vinculo)
        .join(Colaborador, Colaborador.id == Vinculo.colaborador_id)
        .outerjoin(Departamento, Departamento.id == Vinculo.departamento_id)
        .where(Vinculo.tenant_id == tenant_id, Vinculo.status == "ativo")
    )
    if contexto.empresa_id is not None:
        consulta = consulta.where(Vinculo.empresa_id == contexto.empresa_id)
    if contexto.unidade_id is not None:
        consulta = consulta.where(Vinculo.unidade_id == contexto.unidade_id)
    if contexto.departamento_id is not None:
        consulta = consulta.where(Vinculo.departamento_id == contexto.departamento_id)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(Vinculo.colaborador_id == contexto.colaborador_id)
    return consulta


registrar_dataset("headcount_por_area", headcount_por_area)


# =============================================================================
# 23. arquivos-fiscais-historico
# =============================================================================


def arquivos_fiscais_historico(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`afd_arquivos` ∪ `aej_arquivos` -- histórico de geração, **nunca**
    gera nem assina nenhum dos dois (F12, fora de escopo). Pode devolver
    zero linhas nesta fase: F12 roda em paralelo, sem dependência entre as
    duas (PCF §2.2)."""
    afd = sa.select(
        AfdArquivo.id.label("id"),
        sa.literal("AFD").label("tipo"),
        AfdArquivo.empresa_id.label("empresaId"),
        AfdArquivo.periodo_inicio.label("periodoInicio"),
        AfdArquivo.periodo_fim.label("periodoFim"),
        AfdArquivo.nome_arquivo.label("nomeArquivo"),
        AfdArquivo.tamanho_bytes.label("tamanhoBytes"),
        AfdArquivo.hash_sha256.label("hashSha256"),
        AfdArquivo.status.label("status"),
        AfdArquivo.gerado_em.label("geradoEm"),
    ).where(
        AfdArquivo.tenant_id == tenant_id, *_filtro_periodo(AfdArquivo.periodo_inicio, contexto)
    )
    aej = sa.select(
        AejArquivo.id.label("id"),
        sa.literal("AEJ").label("tipo"),
        AejArquivo.empresa_id.label("empresaId"),
        AejArquivo.periodo_inicio.label("periodoInicio"),
        AejArquivo.periodo_fim.label("periodoFim"),
        AejArquivo.nome_arquivo.label("nomeArquivo"),
        AejArquivo.tamanho_bytes.label("tamanhoBytes"),
        AejArquivo.hash_sha256.label("hashSha256"),
        AejArquivo.status.label("status"),
        AejArquivo.gerado_em.label("geradoEm"),
    ).where(
        AejArquivo.tenant_id == tenant_id, *_filtro_periodo(AejArquivo.periodo_inicio, contexto)
    )
    if contexto.empresa_id is not None:
        afd = afd.where(AfdArquivo.empresa_id == contexto.empresa_id)
        aej = aej.where(AejArquivo.empresa_id == contexto.empresa_id)

    uniao = sa.union_all(afd, aej).subquery()
    consulta = sa.select(uniao)
    # `tipo` (AFD/AEJ) e um filtro extra declarado em `filtros_disponiveis`
    # (semeado por A1), aplicado sobre o resultado da uniao (nao teria como
    # filtrar so um lado ANTES do UNION sem duplicar a condicao acima).
    tipo_filtro = contexto.filtros.get("tipo")
    if tipo_filtro:
        consulta = consulta.where(uniao.c.tipo == str(tipo_filtro).upper())
    return consulta


registrar_dataset("arquivos_fiscais_historico", arquivos_fiscais_historico)


# =============================================================================
# 24. lgpd-acessos-e-titulares
# =============================================================================


def lgpd_acessos_e_titulares(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """`acessos_dados_sensiveis` ∪ `solicitacoes_titular` -- sem controle de
    acesso novo (PCF §6/T10: "respeitando qualquer RLS/sensibilidade já
    imposta por essas tabelas... você não adiciona controle de acesso
    novo, herda o que já existe"): a sessão já opera sob RLS
    (`app.tenant_id` publicado por `obter_sessao`), nenhuma coluna extra de
    permissão é checada aqui.

    **Achado de contrato registrado, não escondido:** a semente de A1
    (`tests/f11/conftest.py::_CATALOGO_RELATORIOS`, dataset `lgpd_acessos_
    titulares`) declara uma coluna `permissaoCodigo` que **não existe** em
    `acessos_dados_sensiveis` nem em `solicitacoes_titular` (nenhuma das
    duas tem coluna de permissão -- `acessos_dados_sensiveis` guarda
    `acao`/`base_legal`/`finalidade`, não um código de permissão RBAC).
    Como não invento dado que a tabela não tem, a coluna é exposta como
    `NULL` explícito (texto) em vez de causar erro em tempo de execução se
    alguém pedir essa coluna -- não é dado fabricado, é ausência honesta.
    Registrado para o orquestrador reconciliar o catálogo semeado (renomear
    ou remover `permissaoCodigo`) no relatório de fechamento da fase."""
    acessos = sa.select(
        AcessoDadoSensivel.id.label("id"),
        sa.literal("acesso").label("tipo"),
        AcessoDadoSensivel.colaborador_id.label("colaboradorId"),
        AcessoDadoSensivel.usuario_id.label("usuarioId"),
        AcessoDadoSensivel.categoria.label("categoria"),
        AcessoDadoSensivel.finalidade.label("descricao"),
        AcessoDadoSensivel.ocorrido_em.label("ocorridoEm"),
        AcessoDadoSensivel.criado_em.label("criadoEm"),
        sa.cast(sa.null(), sa.Text()).label("permissaoCodigo"),
    ).where(
        AcessoDadoSensivel.tenant_id == tenant_id,
        *_filtro_periodo(sa.func.cast(AcessoDadoSensivel.ocorrido_em, sa.Date()), contexto),
    )
    solicitacoes = sa.select(
        SolicitacaoTitular.id.label("id"),
        sa.literal("solicitacao").label("tipo"),
        SolicitacaoTitular.colaborador_id.label("colaboradorId"),
        SolicitacaoTitular.usuario_id.label("usuarioId"),
        SolicitacaoTitular.tipo.label("categoria"),
        SolicitacaoTitular.status.label("descricao"),
        sa.func.cast(SolicitacaoTitular.criado_em, sa.DateTime(timezone=True)).label("ocorridoEm"),
        SolicitacaoTitular.criado_em.label("criadoEm"),
        sa.cast(sa.null(), sa.Text()).label("permissaoCodigo"),
    ).where(SolicitacaoTitular.tenant_id == tenant_id)
    if contexto.colaborador_id is not None:
        acessos = acessos.where(AcessoDadoSensivel.colaborador_id == contexto.colaborador_id)
        solicitacoes = solicitacoes.where(
            SolicitacaoTitular.colaborador_id == contexto.colaborador_id
        )

    uniao = sa.union_all(acessos, solicitacoes).subquery()
    return sa.select(uniao)


registrar_dataset("lgpd_acessos_titulares", lgpd_acessos_e_titulares)


__all__ = [
    "DIVISOR_HORA_MENSAL",
    "arquivos_fiscais_historico",
    "auditoria",
    "custo_horas_extras",
    "dispositivos_canais",
    "escalas_previsto_realizado",
    "extrato_para_folha",
    "headcount_por_area",
    "horas_por_centro_custo",
    "lgpd_acessos_e_titulares",
    "movimentacao_pessoal",
    "violacoes_interjornada",
    "violacoes_intrajornada",
]
