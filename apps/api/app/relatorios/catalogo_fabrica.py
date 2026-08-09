"""Catálogo dos 24 relatórios "de fábrica" (F11 §2.2) -- dados puros, sem
sessão de banco, para semear `relatorio_definicoes` por tenant.

Extraído de `tests/f11/conftest.py::_CATALOGO_RELATORIOS`, que já fixava esta
mesma lista para os testes desde a F11. `RelatorioDefinicao` (`schema.sql`
§16, comentário da tabela) sempre disse "os 24 relatórios do produto são
semeados por tenant com `sistema = true`" -- mas nenhum código de produção
fazia esse `INSERT`: só a fixture de teste, e só para os quatro bancos
isolados de F11/A1-A4. Achado real, 09/08/2026 (dono do produto navegando o
painel de RH em `ponto-hml`: "Tendência de horas extras" e "Ocorrências por
mês" sempre `404 PONTO-REC-001`, porque a linha do catálogo nunca existia
para nenhum tenant, dev ou real).

Os 24 `codigo`/`dataset` abaixo são a MESMA string que
`app.relatorios.catalogo.registrar_dataset(...)` já usa nos três módulos de
`app/relatorios/datasets/` -- não são independentes; mudar um sem o outro
quebra a resolução em `motor.py::executar_dataset`.

Quem semeia, usando este catálogo:
* `migrations/seed_dev.py` (dev/hml, tenant de desenvolvimento) --
  `semeia_relatorios_de_fabrica`.
* Onboarding de tenant real: ainda não migrado para uma rota (ver
  `app.identidade.tenancy.servico_suporte.criar_tenant`, que documenta a
  lacuna e por que não é a credencial de suporte que deveria fazer esse
  `INSERT`) -- por ora, `scripts/semear_relatorios_tenant.py` cobre o caso
  manual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.relatorios.catalogo import AgrupamentoCatalogo, ColunaCatalogo, FiltroCatalogo


@dataclass(frozen=True, slots=True)
class DefinicaoRelatorioFabrica:
    codigo: str
    nome: str
    categoria: str
    dataset: str
    colunas: list[ColunaCatalogo]
    filtros: list[FiltroCatalogo] = field(default_factory=list)
    agrupamentos: list[AgrupamentoCatalogo] = field(default_factory=list)
    formatos: list[str] = field(default_factory=lambda: ["csv", "xlsx", "pdf"])
    assincrono: bool = False


def _c(chave: str, rotulo: str, tipo: str = "texto", duracao: bool = False) -> ColunaCatalogo:
    return ColunaCatalogo(chave=chave, rotulo=rotulo, tipo=tipo, duracao=duracao)


def _f(chave: str, rotulo: str, tipo: str = "texto") -> FiltroCatalogo:
    return FiltroCatalogo(chave=chave, rotulo=rotulo, tipo=tipo)


def _a(chave: str, rotulo: str) -> AgrupamentoCatalogo:
    return AgrupamentoCatalogo(chave=chave, rotulo=rotulo)


_FILTROS_PADRAO = [
    _f("periodoId", "Periodo", "uuid"),
    _f("empresaId", "Empresa", "uuid"),
    _f("unidadeId", "Unidade", "uuid"),
    _f("departamentoId", "Departamento", "uuid"),
    _f("colaboradorId", "Colaborador", "uuid"),
]

CATALOGO_RELATORIOS_DE_FABRICA: list[DefinicaoRelatorioFabrica] = [
    DefinicaoRelatorioFabrica(
        codigo="espelho-oficial",
        nome="Espelho de ponto oficial",
        categoria="operacional",
        dataset="espelho_oficial",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("vinculoId", "Vinculo", "uuid"),
            _c("periodoCodigo", "Periodo"),
            _c("versao", "Versao", "numero"),
            _c("tipo", "Tipo"),
            _c("assinado", "Assinado", "booleano"),
            _c("assinadoEm", "Assinado em", "data"),
        ],
        filtros=[
            _f("periodoId", "Periodo", "uuid"),
            _f("colaboradorId", "Colaborador", "uuid"),
            _f("vinculoId", "Vinculo", "uuid"),
            _f("tipo", "Tipo"),
        ],
        formatos=["pdf"],
    ),
    DefinicaoRelatorioFabrica(
        codigo="espelho-jornada",
        nome="Jornada / espelho previo",
        categoria="operacional",
        dataset="apuracao_dia",
        colunas=[
            _c("nomeCompleto", "Nome completo"),
            _c("matricula", "Matricula"),
            _c("cargo", "Cargo"),
            _c("departamento", "Departamento"),
            _c("data", "Data", "data"),
            _c("tipoDia", "Tipo do dia"),
            _c("previstoMinutos", "Previsto", "numero", True),
            _c("trabalhadoMinutos", "Trabalhado", "numero", True),
            _c("normaisMinutos", "Normais", "numero", True),
            _c("extrasMinutos", "Extras diurnas", "numero", True),
            _c("extrasNoturnasMinutos", "Extras noturnas", "numero", True),
            _c("noturnoMinutos", "Adicional noturno", "numero", True),
            _c("intrajornadaSuprimidaMinutos", "Intrajornada suprimida", "numero", True),
            _c("atrasoMinutos", "Atraso", "numero", True),
            _c("saidaAntecipadaMinutos", "Saida antecipada", "numero", True),
            _c("faltaMinutos", "Falta", "numero", True),
            _c("dsrCreditoMinutos", "Credito DSR", "numero", True),
            _c("dsrDebitoMinutos", "Debito DSR", "numero", True),
            _c("bancoCreditoMinutos", "Credito banco de horas", "numero", True),
            _c("bancoDebitoMinutos", "Debito banco de horas", "numero", True),
            _c("pausasNr17Minutos", "Pausas NR-17", "numero", True),
            _c("saldoMinutos", "Saldo do dia", "numero", True),
            _c("status", "Status"),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("departamento", "Departamento"), _a("colaborador", "Colaborador")],
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="banco-de-horas",
        nome="Banco de horas",
        categoria="operacional",
        dataset="bh_lancamentos",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("tipo", "Tipo"),
            _c("minutos", "Minutos", "numero", True),
            _c("saldoAposMinutos", "Saldo apos", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
    ),
    DefinicaoRelatorioFabrica(
        codigo="horas-extras",
        nome="Horas extras",
        categoria="operacional",
        dataset="apuracao_componentes_extra",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("departamento", "Departamento"),
            _c("data", "Data", "data"),
            _c("fator", "Fator", "numero"),
            _c("minutos", "Minutos", "numero", True),
            _c("minutosEquivalentes", "Minutos equivalentes", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("departamento", "Departamento"), _a("colaborador", "Colaborador")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="adicional-noturno",
        nome="Adicional noturno",
        categoria="operacional",
        dataset="apuracao_componentes_noturno",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("minutos", "Minutos", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("colaborador", "Colaborador")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="absenteismo",
        nome="Absenteismo",
        categoria="operacional",
        dataset="absenteismo",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("departamento", "Departamento"),
            _c("faltaMinutos", "Falta", "numero", True),
            _c("diasComFalta", "Dias com falta", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("departamento", "Departamento")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="atrasos-saidas-antecipadas",
        nome="Atrasos e saidas antecipadas",
        categoria="operacional",
        dataset="apuracao_dia_atrasos",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("atrasoMinutos", "Atraso", "numero", True),
            _c("saidaAntecipadaMinutos", "Saida antecipada", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="faltas",
        nome="Faltas",
        categoria="operacional",
        dataset="apuracao_dia_faltas",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("faltaMinutos", "Falta", "numero", True),
            _c("temTratamento", "Tem tratamento", "booleano"),
        ],
        filtros=_FILTROS_PADRAO,
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="tempo-real",
        nome="Tempo real",
        categoria="operacional",
        dataset="marcacoes_tempo_real",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("ultimaMarcacaoEm", "Ultima marcacao", "data"),
            _c("situacao", "Situacao"),
        ],
        filtros=[_f("unidadeId", "Unidade", "uuid"), _f("departamentoId", "Departamento", "uuid")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="ocorrencias",
        nome="Ocorrencias e inconsistencias",
        categoria="operacional",
        dataset="ocorrencias",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("codigo", "Codigo"),
            _c("severidade", "Severidade"),
            _c("status", "Status"),
        ],
        filtros=[
            *_FILTROS_PADRAO,
            _f("codigo", "Codigo"),
            _f("severidade", "Severidade"),
            _f("status", "Status"),
        ],
    ),
    DefinicaoRelatorioFabrica(
        codigo="abonos-justificativas",
        nome="Abonos e justificativas",
        categoria="operacional",
        dataset="tratamentos_abono",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("dataReferencia", "Data", "data"),
            _c("motivo", "Motivo"),
            _c("status", "Status"),
        ],
        filtros=_FILTROS_PADRAO,
    ),
    DefinicaoRelatorioFabrica(
        codigo="ferias-afastamentos",
        nome="Ferias e afastamentos",
        categoria="operacional",
        dataset="afastamentos",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("categoria", "Categoria"),
            _c("dataInicio", "Inicio", "data"),
            _c("dataFim", "Fim", "data"),
        ],
        filtros=_FILTROS_PADRAO,
    ),
    DefinicaoRelatorioFabrica(
        codigo="escalas-previsto-realizado",
        nome="Escalas: previsto x realizado",
        categoria="gerencial",
        dataset="escalas_previsto_realizado",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("previstoMinutos", "Previsto", "numero", True),
            _c("trabalhadoMinutos", "Trabalhado", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="violacoes-intrajornada",
        nome="Violacoes de intrajornada",
        categoria="fiscal",
        dataset="violacoes_intrajornada",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("intrajornadaSuprimidaMinutos", "Intrajornada suprimida", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="violacoes-interjornada",
        nome="Violacoes de interjornada",
        categoria="fiscal",
        dataset="violacoes_interjornada",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("data", "Data", "data"),
            _c("interjornadaMinutos", "Interjornada", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="horas-por-centro-custo",
        nome="Horas por centro de custo",
        categoria="gerencial",
        dataset="apuracao_dia_centro_custo",
        colunas=[
            _c("centroCusto", "Centro de custo"),
            _c("trabalhadoMinutos", "Trabalhado", "numero", True),
            _c("extrasMinutos", "Extras", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("centroCusto", "Centro de custo")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="extrato-para-folha",
        nome="Extrato para folha",
        categoria="financeiro",
        dataset="apuracao_componentes_folha",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("competencia", "Competencia"),
            _c("codigo", "Codigo da rubrica"),
            _c("minutos", "Minutos", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
    ),
    DefinicaoRelatorioFabrica(
        codigo="movimentacao-pessoal",
        nome="Movimentacao de pessoal",
        categoria="gerencial",
        dataset="movimentacao_pessoal",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("evento", "Evento"),
            _c("data", "Data", "data"),
        ],
        filtros=[
            _f("empresaId", "Empresa", "uuid"),
            _f("de", "De", "data"),
            _f("ate", "Ate", "data"),
        ],
    ),
    DefinicaoRelatorioFabrica(
        codigo="auditoria",
        nome="Auditoria",
        categoria="gerencial",
        dataset="auditoria",
        colunas=[
            _c("entidade", "Entidade"),
            _c("acao", "Acao"),
            _c("usuarioId", "Usuario", "uuid"),
            _c("criadoEm", "Quando", "data"),
        ],
        filtros=[
            _f("entidade", "Entidade"),
            _f("acao", "Acao"),
            _f("de", "De", "data"),
            _f("ate", "Ate", "data"),
        ],
        assincrono=True,
    ),
    DefinicaoRelatorioFabrica(
        codigo="dispositivos-canais",
        nome="Dispositivos e canais",
        categoria="gerencial",
        dataset="dispositivos_canais",
        colunas=[
            _c("canal", "Canal"),
            _c("quantidadeMarcacoes", "Marcacoes", "numero", True),
        ],
        filtros=_FILTROS_PADRAO,
        agrupamentos=[_a("canal", "Canal")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="custo-horas-extras",
        nome="Custo de horas extras",
        categoria="financeiro",
        dataset="custo_horas_extras",
        colunas=[
            _c("colaboradorNome", "Colaborador"),
            _c("minutos", "Minutos", "numero", True),
            _c("valorHora", "Valor hora", "numero"),
            _c("valorTotal", "Valor total", "numero"),
        ],
        filtros=_FILTROS_PADRAO,
    ),
    DefinicaoRelatorioFabrica(
        codigo="headcount-por-area",
        nome="Headcount por area",
        categoria="gerencial",
        dataset="headcount_por_area",
        colunas=[
            _c("departamento", "Departamento"),
            _c("quantidadeVinculos", "Vinculos ativos", "numero", True),
        ],
        filtros=[_f("empresaId", "Empresa", "uuid")],
        agrupamentos=[_a("departamento", "Departamento")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="arquivos-fiscais-historico",
        nome="Arquivos fiscais: historico",
        categoria="fiscal",
        dataset="arquivos_fiscais_historico",
        colunas=[
            _c("tipo", "Tipo"),
            _c("geradoEm", "Gerado em", "data"),
            _c("hashSha256", "Hash"),
        ],
        filtros=[_f("empresaId", "Empresa", "uuid"), _f("tipo", "Tipo")],
    ),
    DefinicaoRelatorioFabrica(
        codigo="lgpd-acessos-e-titulares",
        nome="LGPD: acessos e solicitacoes de titular",
        categoria="lgpd",
        dataset="lgpd_acessos_titulares",
        colunas=[
            _c("usuarioId", "Usuario", "uuid"),
            _c("permissaoCodigo", "Permissao"),
            _c("criadoEm", "Quando", "data"),
        ],
        filtros=[_f("de", "De", "data"), _f("ate", "Ate", "data")],
    ),
]

assert len(CATALOGO_RELATORIOS_DE_FABRICA) == 24, "O catalogo precisa ter os 24 relatorios."
assert len({item.codigo for item in CATALOGO_RELATORIOS_DE_FABRICA}) == 24, (
    "codigo de relatorio duplicado."
)
