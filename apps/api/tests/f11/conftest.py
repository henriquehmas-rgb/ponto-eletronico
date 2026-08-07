"""Fixture compartilhada da fase F11 (T1, ownership exclusivo de A1 -- PCF
§5, linha "`apps/api/tests/f11/conftest.py`"). Todos os demais agentes da
fase (A2, A3, A4) **usam** esta fixture; não a editam -- se precisarem de um
dado a mais, pedem no relatório de fechamento em vez de editar aqui (mesma
regra de convivência que `tests/f10/conftest.py` já estabeleceu para F10).

Mesma FORMA de bootstrap já estabelecida por `tests/f3/conftest.py` e
`tests/f10/conftest.py` (migração + role de LOGIN derivada do nome do banco
de `PONTO_TEST_DATABASE_URL` + sessão por teste sob RLS, nunca
superusuário): cada agente desta fase roda contra seu próprio banco
exclusivo (`ponto_f11_a1`, `ponto_f11_a2`, `ponto_f11_a3`, `ponto_f11_a4`), e
o nome da role deriva do banco para não colidir entre agentes rodando em
paralelo contra o mesmo cluster.

## O que esta fixture entrega, por teste (`contexto_f11`, escopo `function`)

* 1 tenant, 1 empresa, 1 unidade, 2 departamentos (`Operações`/`Financeiro`
  -- necessários para os testes de agrupamento do motor, T2, e reaproveitados
  por A2/A3 para os próprios agrupamentos de dataset).
* 3 colaboradores com vínculo `apura_ponto=true`, `status='ativo'`: dois no
  departamento "Operações", um no "Financeiro".
* 1 jornada SIMPLES fixa (`tipo='fixa'`), 08:00-17:00 com 1h de intervalo
  (480 min de carga líquida) -- mesma forma de `tests/f10/conftest.py`,
  atribuída aos três vínculos.
* 1 `Periodo` (`status='fechado'`, `tipo='mensal'`) cobrindo o mês da semana
  de referência abaixo.
* Dados sintéticos de apuração para 3 dias úteis (segunda a quarta de uma
  semana de referência determinística, nunca fim de semana) **por `INSERT`
  em lote direto, nunca via `apurar_dia`** (PCF §2.3, proibição 1): uma linha
  de `ApuracaoDia` por colaborador/dia (9 linhas), com `apuracao_componentes`
  (`categoria='extra'`, e uma de `categoria='noturno'` para o colaborador B),
  1 `Ocorrencia` e 1 `Tratamento` (com `TipoTratamento` de exemplo) de
  exemplo. Os números são conhecidos de propósito (documentados em
  `ColaboradorF11`), para os testes de soma/agrupamento (T2, e os de A2 em
  T7/T8) poderem conferir contra um cálculo feito à mão.
* 24 linhas de `relatorio_definicoes`, semeadas com `sistema=true`, uma por
  `codigo` do catálogo fixado em `PCF F11 §2.2` -- ver `_CATALOGO_RELATORIOS`
  abaixo. **Nomes de `dataset` são a âncora de coordenação entre os quatro
  agentes desta fase**: A2/A3/A4 devem chamar
  `app.relatorios.catalogo.registrar_dataset(<dataset>, <funcao>)` com
  exatamente a string desta tabela para o motor encontrar a função (ver
  docstring de `_CATALOGO_RELATORIOS`).
* `cliente` -- `TestClient` da aplicação real (`app.main.criar_aplicacao`),
  apontada para este banco de teste, mesmo padrão de `tests/f1/conftest.py`.
* `construir_sujeito`/`sobrescrever_sujeito` -- autenticação de teste por
  `dependency_overrides` em vez de login real via `/v1/auth/login`: esta
  fase não depende de `tests/f1/conftest.py` (ownership de outra fase) nem
  recria a infraestrutura pesada de par RS256 descartável só para exercitar
  rota HTTP -- `app.core.seguranca.obter_sujeito` é o único ponto de entrada
  do sujeito autenticado (`app/core/seguranca.py`, "CONTRATO ENTRE FASES"),
  então sobrescrevê-lo continua exercitando o roteador, a validação Pydantic
  e o banco reais; só pula a validação de JWT em si, que não é desta fase.

Cada teste que precisar de dado adicional cria a própria linha extra
localmente, no seu módulo de teste -- esta fixture só entrega "uma semente
comum", como o PCF pediu, não o catálogo de casos de cada dataset.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.seguranca import AlcanceEfetivo, Sujeito
from app.relatorios.catalogo import (
    AgrupamentoCatalogo,
    ColunaCatalogo,
    FiltroCatalogo,
    montar_agrupamentos,
    montar_colunas_disponiveis,
    montar_filtros_disponiveis,
)

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    """Deriva o nome da role de LOGIN do nome do banco -- evita colisao entre
    os quatro agentes de F11 rodando contra bancos exclusivos distintos no
    mesmo cluster (mesmo padrao de `tests/f3/conftest.py`/`tests/f10/
    conftest.py`)."""
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f11_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_f11() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN."""
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_super.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(RAIZ_API),
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head falhou ao preparar o banco de teste da F11:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )

    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (role_login,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )

    url_login = url_super.set(drivername="postgresql+asyncpg", username=role_login, password=senha)
    dsn_login = url_login.set(drivername="postgresql").render_as_string(hide_password=False)

    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_login, connect_timeout=5):
                pass
            break
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            time.sleep(0.3 * (tentativa + 1))
    else:
        raise RuntimeError(
            f"Nao foi possivel validar a role de LOGIN apos 5 tentativas: {ultimo_erro}"
        )

    return url_login


@pytest_asyncio.fixture
async def engine_f11(url_login_sessao_f11: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f11, pool_pre_ping=True, connect_args={"timeout": 8}
        )
        try:
            async with asyncio.timeout(10):
                async with engine.connect():
                    pass
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            await engine.dispose()
            await asyncio.sleep(min(0.5 * (tentativa + 1), 3.0))
            continue
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F11: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f11(engine_f11: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    Cuidado com `SET LOCAL` + `commit()`: `aplicar_tenant_teste` usa
    `SET LOCAL`, valido so ate o fim da transacao corrente. Commitar no meio
    do teste e continuar operando exige chamar `aplicar_tenant_teste` de
    novo (mesmo aviso de `tests/f10/conftest.py`).
    """
    fabrica = async_sessionmaker(engine_f11, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


# =============================================================================
# Catalogo dos 24 relatorios (PCF F11 secao 2.2) -- ver docstring do modulo.
# =============================================================================
@dataclass(frozen=True, slots=True)
class _DefinicaoSeed:
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

#: Nomes de `dataset` -- string estavel que ancora `RelatorioDefinicao.
#: dataset` -> `app.relatorios.catalogo.registrar_dataset(...)`. Cada agente
#: (A2 itens 2-12, A3 itens 13-24, A4 item 1) registra a funcao de consulta
#: correspondente em seu proprio modulo (`datasets/operacionais.py`,
#: `datasets/gerenciais.py`, `datasets/espelho_oficial.py`) usando
#: EXATAMENTE a string abaixo -- e o unico ponto de coordenacao entre a
#: semente desta fixture (A1) e a funcao real (A2/A3/A4). Onde o mesmo tipo
#: de tabela serve mais de um relatorio (por exemplo `apuracao_componentes`
#: para os itens 4/5/17/21), o nome do dataset e sufixado pela
#: especializacao -- ver PCF F11 §2.2, coluna "Dataset (interno)": o texto
#: la e ilustrativo ("apuracao_componentes (categoria extra)"), e como
#: `dataset` e uma unica string que resolve para uma unica funcao Python,
#: A1 precisou decidir o sufixo exato (julgamento documentado no relatorio
#: de fechamento da fase).
_CATALOGO_RELATORIOS: list[_DefinicaoSeed] = [
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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
    _DefinicaoSeed(
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

assert len(_CATALOGO_RELATORIOS) == 24, "O catalogo desta fixture precisa ter os 24 relatorios."
assert len({item.codigo for item in _CATALOGO_RELATORIOS}) == 24, "codigo de relatorio duplicado."


# =============================================================================
# Dados sintéticos de apuração -- ver docstring do modulo.
# =============================================================================
@dataclass(frozen=True, slots=True)
class ColaboradorF11:
    """Um colaborador semeado, com os totais sintéticos conhecidos (soma dos
    3 dias úteis inseridos) para os testes conferirem à mão."""

    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID
    usuario_id: uuid.UUID
    departamento_id: uuid.UUID
    departamento_nome: str
    matricula: str
    nome: str
    #: Por dia (3 dias uteis identicos por colaborador, ver `_DIAS_UTEIS`).
    extras_minutos_por_dia: int
    noturno_minutos_por_dia: int
    falta_minutos_ultimo_dia: int


def _proxima_segunda(referencia: dt.date) -> dt.date:
    """Segunda-feira da semana de `referencia` -- determinístico, nunca cai
    em fim de semana, então o mesmo cálculo funciona em qualquer dia em que
    os testes rodem."""
    return referencia - dt.timedelta(days=referencia.weekday())


@pytest_asyncio.fixture
async def contexto_f11(sessao_f11: AsyncSession, url_login_sessao_f11: URL) -> ContextoF11:
    """Semeia a base comum da fase (ver docstring do módulo). Cada chamada
    gera tenant, CNPJ, CPFs, matrículas e códigos novos -- nenhum teste
    compartilha semente com outro (mesma isolação de `tests/f10/conftest.py`)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f11-{sufixo}"

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    await sessao_f11.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F11",
            "nome": "Tenant F11",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_f11.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', "
            "        '3550308', 'America/Sao_Paulo')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F11 Ltda",
            "fantasia": "Empresa Teste F11",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de Teste', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    departamento_operacoes_id = uuid.uuid4()
    departamento_financeiro_id = uuid.uuid4()
    for dep_id, codigo, nome in (
        (departamento_operacoes_id, f"OPS-{sufixo}", "Operacoes"),
        (departamento_financeiro_id, f"FIN-{sufixo}", "Financeiro"),
    ):
        await sessao_f11.execute(
            text(
                "INSERT INTO departamentos (id, tenant_id, empresa_id, codigo, nome, ativo) "
                "VALUES (:id, :tenant_id, :empresa_id, :codigo, :nome, TRUE)"
            ),
            {
                "id": dep_id,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "codigo": codigo,
                "nome": nome,
            },
        )

    # Jornada simples fixa: util seg-sex (08:00-17:00, 1h de intervalo, 480
    # min de carga liquida) -- mesma forma de `tests/f10/conftest.py`.
    horario_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, intervalo_inicio, "
            " intervalo_fim, duracao_intervalo_minutos, carga_minutos, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Horario padrao 08-17', "
            "        '08:00', '17:00', '12:00', '13:00', 60, 480, TRUE)"
        ),
        {
            "id": horario_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"HOR-{sufixo}",
        },
    )

    data_inicio_vinculo = dt.date(2020, 1, 1)
    jornada_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, carga_diaria_minutos, "
            " carga_semanal_minutos, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Jornada simples de teste', "
            "        'fixa', 480, 2400, :vigencia_inicio, TRUE)"
        ),
        {
            "id": jornada_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"JOR-{sufixo}",
            "vigencia_inicio": data_inicio_vinculo,
        },
    )
    for dia_semana, tipo_dia, horario_do_dia, carga in (
        (0, "dsr", None, 0),
        (1, "util", horario_id, 480),
        (2, "util", horario_id, 480),
        (3, "util", horario_id, 480),
        (4, "util", horario_id, 480),
        (5, "util", horario_id, 480),
        (6, "folga", None, 0),
    ):
        await sessao_f11.execute(
            text(
                "INSERT INTO jornada_dias "
                "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
                "VALUES (:id, :tenant_id, :jornada_id, :dia_semana, :tipo_dia, :horario_id, :carga)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "jornada_id": jornada_id,
                "dia_semana": dia_semana,
                "tipo_dia": tipo_dia,
                "horario_id": horario_do_dia,
                "carga": carga,
            },
        )

    # Tres colaboradores: dois em Operacoes (A extras=30min/dia, B
    # extras=60min/dia + noturno=15min/dia), um em Financeiro (C falta
    # completa no ultimo dia util, 480 minutos).
    colaboradores: list[ColaboradorF11] = []
    especificacoes = (
        ("A", departamento_operacoes_id, "Operacoes", 30, 0, 0),
        ("B", departamento_operacoes_id, "Operacoes", 60, 15, 0),
        ("C", departamento_financeiro_id, "Financeiro", 0, 0, 480),
    )
    for rotulo, dep_id, dep_nome, extras, noturno, falta_ultimo_dia in especificacoes:
        colaborador_id = uuid.uuid4()
        cpf = f"{secrets.randbelow(10**11):011d}"
        matricula = f"MAT-{rotulo}-{sufixo}"
        nome = f"Colaborador {rotulo} de Teste F11"
        await sessao_f11.execute(
            text(
                "INSERT INTO colaboradores "
                "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
            ),
            {
                "id": colaborador_id,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "matricula": matricula,
                "cpf": cpf,
                "nome": nome,
            },
        )

        vinculo_id = uuid.uuid4()
        await sessao_f11.execute(
            text(
                "INSERT INTO vinculos "
                "(id, tenant_id, colaborador_id, empresa_id, unidade_id, departamento_id, "
                " matricula_esocial, tipo_vinculo, data_inicio, apura_ponto, principal, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :dep_id, "
                "        :esocial, 'empregado', :data_inicio, TRUE, TRUE, 'ativo')"
            ),
            {
                "id": vinculo_id,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": empresa_id,
                "unidade_id": unidade_id,
                "dep_id": dep_id,
                "esocial": f"ESOC-{rotulo}-{sufixo}",
                "data_inicio": data_inicio_vinculo,
            },
        )
        await sessao_f11.execute(
            text(
                "INSERT INTO vinculo_jornadas "
                "(id, tenant_id, vinculo_id, jornada_id, vigencia_inicio) "
                "VALUES (:id, :tenant_id, :vinculo_id, :jornada_id, :vigencia_inicio)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "vinculo_id": vinculo_id,
                "jornada_id": jornada_id,
                "vigencia_inicio": data_inicio_vinculo,
            },
        )

        usuario_id = uuid.uuid4()
        await sessao_f11.execute(
            text(
                "INSERT INTO usuarios "
                "(id, tenant_id, colaborador_id, email, nome_completo, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :email, :nome, 'ativo')"
            ),
            {
                "id": usuario_id,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "email": f"colaborador-{rotulo.lower()}-{sufixo}@f11.teste",
                "nome": nome,
            },
        )

        colaboradores.append(
            ColaboradorF11(
                colaborador_id=colaborador_id,
                vinculo_id=vinculo_id,
                usuario_id=usuario_id,
                departamento_id=dep_id,
                departamento_nome=dep_nome,
                matricula=matricula,
                nome=nome,
                extras_minutos_por_dia=extras,
                noturno_minutos_por_dia=noturno,
                falta_minutos_ultimo_dia=falta_ultimo_dia,
            )
        )

    # Usuario de RH generico (sem colaborador correspondente) -- usado por
    # quem precisar de um `usuario_id` de sujeito sem vinculo de colaborador.
    usuario_rh_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :email, 'RH de Teste F11', 'ativo')"
        ),
        {"id": usuario_rh_id, "tenant_id": tenant_id, "email": f"rh-{sufixo}@f11.teste"},
    )

    # Periodo fechado cobrindo o mes da semana de referencia (segunda desta
    # semana -- sempre dia util, nunca fim de semana).
    segunda = _proxima_segunda(dt.date.today())
    dias_uteis = [segunda, segunda + dt.timedelta(days=1), segunda + dt.timedelta(days=2)]
    periodo_data_inicio = segunda.replace(day=1)
    if segunda.month == 12:
        periodo_data_fim = dt.date(segunda.year, 12, 31)
    else:
        periodo_data_fim = dt.date(segunda.year, segunda.month + 1, 1) - dt.timedelta(days=1)
    periodo_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO periodos "
            "(id, tenant_id, empresa_id, codigo, tipo, data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'mensal', :data_inicio, :data_fim, "
            "        'fechado')"
        ),
        {
            "id": periodo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"{segunda.year:04d}-{segunda.month:02d}-{sufixo}",
            "data_inicio": periodo_data_inicio,
            "data_fim": periodo_data_fim,
        },
    )

    # Tipo de tratamento + tratamento de exemplo (categoria abono), motivo
    # ADR-011: um tratamento aprovado NAO altera apuracoes_dia (F4, debito
    # conhecido) -- os dados sinteticos abaixo refletem isso fielmente (a
    # falta de C no ultimo dia continua com falta_minutos=480 mesmo com o
    # tratamento aprovado).
    tipo_tratamento_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, exige_anexo, "
            " exige_motivo, permite_retroativo_dias, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Abono de teste F11', 'abono', TRUE, FALSE, TRUE, "
            "        60, TRUE)"
        ),
        {"id": tipo_tratamento_id, "tenant_id": tenant_id, "codigo": f"ABONO-{sufixo}"},
    )

    colaborador_c = colaboradores[2]
    tratamento_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO tratamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, data_referencia, "
            " motivo, origem, status, aprovado_por, aprovado_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
            "        :data_referencia, 'Atestado medico de teste', 'rh', 'aprovado', "
            "        :usuario_rh_id, now())"
        ),
        {
            "id": tratamento_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_c.colaborador_id,
            "vinculo_id": colaborador_c.vinculo_id,
            "tipo_tratamento_id": tipo_tratamento_id,
            "data_referencia": dias_uteis[2],
            "usuario_rh_id": usuario_rh_id,
        },
    )

    # Ocorrencia de exemplo (atraso) para o colaborador A, no primeiro dia.
    await sessao_f11.execute(
        text(
            "INSERT INTO ocorrencias "
            "(id, tenant_id, colaborador_id, vinculo_id, data, codigo, severidade, descricao, "
            " status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :data, 'atraso', 'atencao', "
            "        'Atraso sintetico de teste F11', 'aberta')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "colaborador_id": colaboradores[0].colaborador_id,
            "vinculo_id": colaboradores[0].vinculo_id,
            "data": dias_uteis[0],
        },
    )

    # `ApuracaoDia`/`ApuracaoComponente` sinteticos, por INSERT em lote direto
    # -- nunca via `apurar_dia` (PCF §2.3, proibicao 1).
    for colaborador in colaboradores:
        for indice, data in enumerate(dias_uteis):
            falta = colaborador.falta_minutos_ultimo_dia if indice == len(dias_uteis) - 1 else 0
            trabalhado = 480 + colaborador.extras_minutos_por_dia - falta
            apuracao_id = uuid.uuid4()
            await sessao_f11.execute(
                text(
                    "INSERT INTO apuracoes_dia "
                    "(id, tenant_id, vinculo_id, colaborador_id, data, empresa_id, unidade_id, "
                    " departamento_id, jornada_id, horario_id, tipo_dia, previsto_minutos, "
                    " trabalhado_minutos, normais_minutos, extras_minutos, noturno_minutos, "
                    " falta_minutos, saldo_minutos, status) "
                    "VALUES (:id, :tenant_id, :vinculo_id, :colaborador_id, :data, :empresa_id, "
                    "        :unidade_id, :departamento_id, :jornada_id, :horario_id, 'util', 480, "
                    "        :trabalhado, 480, :extras, :noturno, :falta, :saldo, 'apurado')"
                ),
                {
                    "id": apuracao_id,
                    "tenant_id": tenant_id,
                    "vinculo_id": colaborador.vinculo_id,
                    "colaborador_id": colaborador.colaborador_id,
                    "data": data,
                    "empresa_id": empresa_id,
                    "unidade_id": unidade_id,
                    "departamento_id": colaborador.departamento_id,
                    "jornada_id": jornada_id,
                    "horario_id": horario_id,
                    "trabalhado": trabalhado,
                    "extras": colaborador.extras_minutos_por_dia,
                    "noturno": colaborador.noturno_minutos_por_dia,
                    "falta": falta,
                    "saldo": colaborador.extras_minutos_por_dia - falta,
                },
            )
            if colaborador.extras_minutos_por_dia:
                await sessao_f11.execute(
                    text(
                        "INSERT INTO apuracao_componentes "
                        "(id, tenant_id, apuracao_dia_id, codigo, categoria, minutos, fator, "
                        " minutos_equivalentes, origem) "
                        "VALUES (:id, :tenant_id, :apuracao_dia_id, 'he50', 'extra', :minutos, "
                        "        1.5, :equivalentes, 'marcacao')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "apuracao_dia_id": apuracao_id,
                        "minutos": colaborador.extras_minutos_por_dia,
                        "equivalentes": int(colaborador.extras_minutos_por_dia * 1.5),
                    },
                )
            if colaborador.noturno_minutos_por_dia:
                await sessao_f11.execute(
                    text(
                        "INSERT INTO apuracao_componentes "
                        "(id, tenant_id, apuracao_dia_id, codigo, categoria, minutos, fator, "
                        " minutos_equivalentes, origem) "
                        "VALUES (:id, :tenant_id, :apuracao_dia_id, 'adnoturno', 'noturno', "
                        "        :minutos, 1.2, :equivalentes, 'marcacao')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "apuracao_dia_id": apuracao_id,
                        "minutos": colaborador.noturno_minutos_por_dia,
                        "equivalentes": int(colaborador.noturno_minutos_por_dia * 1.2),
                    },
                )

    # 24 linhas de `relatorio_definicoes` -- ver `_CATALOGO_RELATORIOS`.
    relatorio_ids: dict[str, uuid.UUID] = {}
    for item in _CATALOGO_RELATORIOS:
        definicao_id = uuid.uuid4()
        relatorio_ids[item.codigo] = definicao_id
        await sessao_f11.execute(
            text(
                "INSERT INTO relatorio_definicoes "
                "(id, tenant_id, codigo, nome, categoria, sistema, dataset, "
                " colunas_disponiveis, filtros_disponiveis, agrupamentos, formatos, "
                " permissao_codigo, assincrono, ativo) "
                "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, TRUE, :dataset, "
                "        CAST(:colunas AS JSONB), CAST(:filtros AS JSONB), "
                "        CAST(:agrupamentos AS JSONB), "
                "        :formatos, 'relatorios.executar', :assincrono, TRUE)"
            ),
            {
                "id": definicao_id,
                "tenant_id": tenant_id,
                "codigo": item.codigo,
                "nome": item.nome,
                "categoria": item.categoria,
                "dataset": item.dataset,
                "colunas": _para_json(montar_colunas_disponiveis(item.colunas)),
                "filtros": _para_json(montar_filtros_disponiveis(item.filtros)),
                "agrupamentos": _para_json(montar_agrupamentos(item.agrupamentos)),
                "formatos": item.formatos,
                "assincrono": item.assincrono,
            },
        )

    await sessao_f11.commit()
    await aplicar_tenant_teste(sessao_f11, tenant_id)

    return ContextoF11(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_operacoes_id=departamento_operacoes_id,
        departamento_financeiro_id=departamento_financeiro_id,
        jornada_id=jornada_id,
        horario_id=horario_id,
        colaboradores=colaboradores,
        usuario_rh_id=usuario_rh_id,
        periodo_id=periodo_id,
        periodo_data_inicio=periodo_data_inicio,
        periodo_data_fim=periodo_data_fim,
        dias_uteis=dias_uteis,
        relatorio_ids=relatorio_ids,
        url_login_async=url_login_sessao_f11.render_as_string(hide_password=False),
    )


def _para_json(valor: dict[str, Any]) -> str:
    import json

    return json.dumps(valor)


@dataclass(frozen=True, slots=True)
class ContextoF11:
    """IDs da semente comum da fase F11 (ver docstring do módulo)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    departamento_operacoes_id: uuid.UUID
    departamento_financeiro_id: uuid.UUID
    jornada_id: uuid.UUID
    horario_id: uuid.UUID
    colaboradores: list[ColaboradorF11]
    usuario_rh_id: uuid.UUID
    periodo_id: uuid.UUID
    periodo_data_inicio: dt.date
    periodo_data_fim: dt.date
    dias_uteis: list[dt.date]
    relatorio_ids: dict[str, uuid.UUID]
    url_login_async: str


# =============================================================================
# Cliente HTTP da aplicacao real, apontado para o banco de teste.
# =============================================================================
@pytest.fixture
def cliente(contexto_f11: ContextoF11) -> Iterator[TestClient]:
    """`TestClient` da aplicacao real (`app.main.criar_aplicacao`), com
    `DATABASE_URL` redirecionada para o banco de teste desta fixture -- mesmo
    padrao de `tests/f1/conftest.py::cliente`."""
    from app.core.config import obter_configuracao
    from app.main import criar_aplicacao

    antigo = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = contexto_f11.url_login_async
    obter_configuracao.cache_clear()
    try:
        aplicacao = criar_aplicacao()
        with TestClient(aplicacao, raise_server_exceptions=False) as cliente_http:
            yield cliente_http
    finally:
        if antigo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = antigo
        obter_configuracao.cache_clear()


def cabecalhos(tenant_slug: str) -> dict[str, str]:
    return {"X-Tenant": tenant_slug}


def construir_sujeito(
    *, usuario_id: uuid.UUID, tenant_id: uuid.UUID, permissoes: frozenset[str]
) -> Sujeito:
    """`Sujeito` autenticado pronto para `dependency_overrides[obter_sujeito]`
    -- ver docstring do módulo ("autenticação de teste por dependency_
    overrides")."""
    return Sujeito(
        usuario_id=usuario_id,
        tenant_id=tenant_id,
        email="sujeito-de-teste@f11.teste",
        perfis=("teste",),
        permissoes=permissoes,
        autenticado=True,
        alcance=AlcanceEfetivo(amplo_tenant=True),
    )


def sobrescrever_sujeito(cliente_http: TestClient, sujeito: Sujeito) -> None:
    """Instala o override de `obter_sujeito` no app por trás de `cliente_http`."""
    from app.core.seguranca import obter_sujeito

    cliente_http.app.dependency_overrides[obter_sujeito] = lambda: sujeito  # type: ignore[attr-defined]
