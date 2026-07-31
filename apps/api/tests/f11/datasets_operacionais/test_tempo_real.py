"""Dataset `tempo-real` (item 9, `PROJETO.md` §9, dataset
`marcacoes_tempo_real`) -- T8 do PCF F11/A2.

A semente comum de `tests/f11/conftest.py` não insere `marcacoes` (não é
escopo da semente comum) -- este módulo semeia `rep_ps` + `marcacoes`
localmente, mesma regra que a docstring da fixture já autoriza.

**Pronto quando (T8):** teste prova que o dataset `tempo-real` nunca lê
`apuracoes_dia` (prova por análise estática do módulo -- mesmo padrão de
prova que F10 já usou para "nenhuma escrita direta em apuracoes_dia").
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.datasets import operacionais
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, executar_bruto


def _corpo_sem_docstring(funcao: object) -> str:
    """Código-fonte de `funcao` com a docstring removida -- a docstring de
    `tempo_real` PRECISA mencionar `apuracoes_dia` em prosa (para explicar a
    exceção), então a análise estática só pode varrer o CORPO executável."""
    codigo_fonte = inspect.getsource(funcao)  # type: ignore[arg-type]
    arvore = ast.parse(codigo_fonte)
    definicao_funcao = arvore.body[0]
    assert isinstance(definicao_funcao, ast.AsyncFunctionDef | ast.FunctionDef)
    corpo = definicao_funcao.body
    if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]  # descarta o nó da docstring
    linha_inicio = corpo[0].lineno if corpo else definicao_funcao.lineno
    linhas = codigo_fonte.splitlines()
    return "\n".join(linhas[linha_inicio - 1 :])


def test_tempo_real_nunca_le_apuracoes_dia() -> None:
    """Análise estática: o CORPO (excluída a docstring, que precisa citar
    `apuracoes_dia` em prosa para explicar a exceção) da função `tempo_real`
    não contém nenhuma referência real a `ApuracaoDia`/`apuracoes_dia` --
    único dataset deste módulo que lê `marcacoes` diretamente (PCF §2.3/§8,
    ADR-002)."""
    corpo = _corpo_sem_docstring(operacionais.tempo_real)
    assert "ApuracaoDia" not in corpo
    assert "apuracoes_dia" not in corpo
    assert "apurar_dia" not in corpo
    assert "recalcular_periodo" not in corpo


async def _semear_rep_p(sessao: AsyncSession, contexto_f11: ContextoF11) -> uuid.UUID:
    rep_p_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    sufixo = uuid.uuid4().hex[:8]
    await sessao.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, numero_inpi, cnpj_desenvolvedor, "
            " razao_social_desenvolvedor, cnpj_empregador, razao_social_empregador, "
            " versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, '12345678', :cnpj, "
            "        'SEEG Servicos de TI', :cnpj, 'Empresa de Teste F11 Ltda', '1.0.0', "
            "        '2020-01-01', 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": contexto_f11.tenant_id,
            "empresa_id": contexto_f11.empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj": cnpj,
        },
    )
    return rep_p_id


async def _inserir_marcacao(
    sessao: AsyncSession,
    contexto_f11: ContextoF11,
    rep_p_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    *,
    nsr: int,
    quando: dt.datetime,
) -> None:
    await sessao.execute(
        text(
            "INSERT INTO marcacoes "
            "(id, tenant_id, rep_p_id, empresa_id, unidade_id, colaborador_id, vinculo_id, "
            " nsr, cpf, datahora_marcacao, canal, crc16, hash_registro) "
            "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :unidade_id, :colaborador_id, "
            "        :vinculo_id, :nsr, :cpf, :quando, 'terminal', :crc16, :hash)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f11.tenant_id,
            "rep_p_id": rep_p_id,
            "empresa_id": contexto_f11.empresa_id,
            "unidade_id": contexto_f11.unidade_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "nsr": nsr,
            "cpf": f"{secrets.randbelow(10**11):011d}",
            "quando": quando,
            "crc16": secrets.randbelow(65536),
            "hash": secrets.token_hex(32),
        },
    )


async def test_numero_impar_de_marcacoes_aparece_como_trabalhando(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    rep_p_id = await _semear_rep_p(sessao_f11, contexto_f11)
    colaborador_a, colaborador_b, colaborador_c = contexto_f11.colaboradores
    hoje = dt.datetime.now(tz=dt.UTC).date()
    base = dt.datetime.combine(hoje, dt.time(8, 0), tzinfo=dt.UTC)

    # A: 1 marcacao (impar) -- "entrou", ainda sem saida -- trabalhando.
    await _inserir_marcacao(
        sessao_f11,
        contexto_f11,
        rep_p_id,
        colaborador_a.colaborador_id,
        colaborador_a.vinculo_id,
        nsr=1,
        quando=base,
    )
    # B: 2 marcacoes (par) -- entrada e saida completas -- nao trabalhando.
    await _inserir_marcacao(
        sessao_f11,
        contexto_f11,
        rep_p_id,
        colaborador_b.colaborador_id,
        colaborador_b.vinculo_id,
        nsr=2,
        quando=base,
    )
    await _inserir_marcacao(
        sessao_f11,
        contexto_f11,
        rep_p_id,
        colaborador_b.colaborador_id,
        colaborador_b.vinculo_id,
        nsr=3,
        quando=base + dt.timedelta(hours=8),
    )
    # C: 3 marcacoes (impar) -- trabalhando (ex.: esqueceu de bater o
    # intervalo, ou esta no meio da jornada).
    for indice, offset_horas in enumerate((0, 4, 8)):
        await _inserir_marcacao(
            sessao_f11,
            contexto_f11,
            rep_p_id,
            colaborador_c.colaborador_id,
            colaborador_c.vinculo_id,
            nsr=10 + indice,
            quando=base + dt.timedelta(hours=offset_horas),
        )
    await sessao_f11.flush()

    contexto = ContextoConsulta(tenant_id=contexto_f11.tenant_id, de=hoje, ate=hoje)
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "tempo-real",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    nomes_trabalhando = {linha["colaboradorNome"] for linha in resultado.linhas}
    assert nomes_trabalhando == {colaborador_a.nome, colaborador_c.nome}
    assert all(linha["situacao"] == "trabalhando" for linha in resultado.linhas)

    # `colaborador` (uuid) e `quantidadeMarcacoesHoje` não estão em
    # `colunas_disponiveis` da fixture (T1/A1) -- chama a função de consulta
    # diretamente para conferir a heurística ímpar/par com precisão.
    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, operacionais.tempo_real, filtros=contexto
    )
    por_colaborador = {linha["colaborador"]: linha for linha in linhas_brutas}
    assert set(por_colaborador) == {colaborador_a.colaborador_id, colaborador_c.colaborador_id}
    assert por_colaborador[colaborador_a.colaborador_id]["quantidadeMarcacoesHoje"] == 1
    assert por_colaborador[colaborador_c.colaborador_id]["quantidadeMarcacoesHoje"] == 3
