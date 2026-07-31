"""Testes do dataset `espelho_oficial` (T12, F11/A4).

Chama `app.relatorios.motor.executar_dataset` diretamente contra o dataset
real (não via HTTP): `app/routers/relatorios.py` ainda é o stub da Fase 0
no momento em que este módulo foi escrito (T3 é ownership de A1, em
andamento em paralelo) -- testar pela camada de motor é o nível certo para
a responsabilidade desta tarefa (a função de consulta), e é exatamente a
mesma chamada que o roteador fará quando A1 concluir T3.

Import de `app.relatorios.datasets.espelho_oficial` (mesmo módulo que
`registrar_dataset("espelho_oficial", ...)`, efeito colateral da
importação) é obrigatório antes de qualquer `executar_dataset` -- sem ele
`catalogo.obter_dataset("espelho_oficial")` responde `PONTO-INT-005`
("dataset ainda não registrado"), o mesmo comportamento que
`app/routers/relatorios.py` terá até que A1/A3 importem os três módulos de
dataset (A2/A3/A4) no topo daquele arquivo (ver `catalogo.py`, docstring).
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import inspect
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import AssinaturaEspelho, Espelho, Periodo, RelatorioDefinicao
from sqlalchemy.ext.asyncio import AsyncSession

import app.relatorios.datasets.espelho_oficial as modulo_espelho_oficial
from app.core.erros import ErroDeAplicacao
from app.relatorios.datasets.espelho_oficial import espelho_oficial
from app.relatorios.motor import ContextoConsulta, executar_dataset
from tests.f11.conftest import ContextoF11


def _hash_de_exemplo(sal: str) -> str:
    return hashlib.sha256(sal.encode("utf-8")).hexdigest()


async def _criar_espelho(
    sessao: AsyncSession,
    contexto: ContextoF11,
    *,
    colaborador_indice: int = 0,
    tipo: str = "oficial",
    versao: int = 1,
) -> Espelho:
    colaborador = contexto.colaboradores[colaborador_indice]
    espelho = Espelho(
        tenant_id=contexto.tenant_id,
        periodo_id=contexto.periodo_id,
        colaborador_id=colaborador.colaborador_id,
        vinculo_id=colaborador.vinculo_id,
        versao=versao,
        tipo=tipo,
        conteudo={"dias": []},
        hash_sha256=_hash_de_exemplo(f"{colaborador.colaborador_id}-{tipo}-{versao}"),
    )
    sessao.add(espelho)
    await sessao.flush()
    return espelho


async def _assinar_espelho(sessao: AsyncSession, contexto: ContextoF11, espelho: Espelho) -> None:
    sessao.add(
        AssinaturaEspelho(
            tenant_id=contexto.tenant_id,
            espelho_id=espelho.id,
            signatario_tipo="colaborador",
            hash_assinado=espelho.hash_sha256,
            status="assinado",
            carimbo_tempo=dt.datetime.now(tz=dt.UTC),
        )
    )
    await sessao.flush()


async def _definicao_espelho_oficial(
    sessao: AsyncSession, contexto: ContextoF11
) -> RelatorioDefinicao:
    definicao = await sessao.get(RelatorioDefinicao, contexto.relatorio_ids["espelho-oficial"])
    assert definicao is not None
    return definicao


def _nomes_importados(modulo: object) -> set[str]:
    """Nomes de módulo/símbolo de toda instrução `import`/`from ... import`
    do arquivo-fonte de `modulo`, via `ast` (nunca uma busca textual sobre
    `inspect.getsource` -- essa busca falsearia positivo contra a própria
    DOCSTRING deste módulo, que cita os nomes proibidos em prosa para
    explicar a restrição, ver docstring do módulo)."""
    arvore = ast.parse(inspect.getsource(modulo))
    nomes: set[str] = set()
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            for alias in node.names:
                nomes.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefixo = node.module or ""
            for alias in node.names:
                nomes.add(f"{prefixo}.{alias.name}" if prefixo else alias.name)
                nomes.add(alias.name)
    return nomes


class TestEspelhoOficialNuncaGeraNemAssina:
    """Critério de aceite (T12 "pronto quando"): prova por análise estática
    (AST de import, não busca textual -- ver `_nomes_importados`) que o
    módulo nunca importa `gerar_espelho_do_vinculo` (nem qualquer outra
    função de escrita de F10) -- mesmo padrão de prova que F10/A4 já usou
    para "nenhuma escrita direta em apuracoes_dia" (PCF §6/T8)."""

    def test_modulo_nao_importa_funcoes_de_escrita_de_f10(self) -> None:
        importados = _nomes_importados(modulo_espelho_oficial)
        proibidos = [
            "gerar_espelho_do_vinculo",
            "criar_espelhos_assincrono",
            "apurar_dia",
            "recalcular_periodo",
        ]
        for termo in proibidos:
            assert termo not in importados, f"'{termo}' esta entre os imports de espelho_oficial.py"

    def test_modulo_nao_importa_nenhum_submodulo_de_workflow_fechamento(self) -> None:
        # Nenhum `import app.workflow.fechamento.*` (nem `espelho`, nem
        # `servico`, nem `assinatura`) -- só leitura de `espelhos`/
        # `assinaturas_espelho` via SQLAlchemy Core direto neste módulo,
        # nunca reimportando o pacote de domínio de F10.
        importados = _nomes_importados(modulo_espelho_oficial)
        assert not any(nome.startswith("app.workflow.fechamento") for nome in importados)


async def test_lista_apenas_oficial_e_retificado_nunca_previo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _criar_espelho(sessao_f11, contexto_f11, tipo="previo", versao=1)
    await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=2)
    await _criar_espelho(sessao_f11, contexto_f11, tipo="retificado", versao=3)

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )

    tipos = {linha["tipo"] for linha in resultado.linhas}
    assert tipos == {"oficial", "retificado"}
    assert len(resultado.linhas) == 2


async def test_escopo_sem_espelho_gerado_devolve_zero_linhas_nao_erro(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )
    assert resultado.linhas == []


async def test_colunas_refletem_colaborador_periodo_versao_tipo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    espelho = await _criar_espelho(
        sessao_f11, contexto_f11, colaborador_indice=0, tipo="oficial", versao=1
    )

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )

    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["colaboradorNome"] == colaborador.nome
    assert str(linha["vinculoId"]) == str(colaborador.vinculo_id)
    assert linha["versao"] == 1
    assert linha["tipo"] == "oficial"
    assert linha["assinado"] is False
    assert linha["assinadoEm"] is None
    assert espelho.periodo_id == contexto_f11.periodo_id


async def test_assinado_e_assinado_em_refletem_assinaturas_espelho(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    espelho = await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=1)
    await _assinar_espelho(sessao_f11, contexto_f11, espelho)

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )

    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["assinado"] is True
    assert linha["assinadoEm"] is not None


async def test_filtro_periodo_id_restringe_ao_periodo_certo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """`contexto.periodo_id` -- filtro embutido do motor, resolvido pelo
    query param `periodoId` de `executarRelatorio` (não passa por
    `filtros`, ao contrário de `vinculoId`/`tipo`)."""
    outro_periodo_id = uuid.uuid4()
    sessao_f11.add(
        Periodo(
            id=outro_periodo_id,
            tenant_id=contexto_f11.tenant_id,
            empresa_id=contexto_f11.empresa_id,
            codigo="OUTRO-PERIODO-F11",
            tipo="mensal",
            data_inicio=contexto_f11.periodo_data_inicio,
            data_fim=contexto_f11.periodo_data_fim,
            status="fechado",
        )
    )
    await sessao_f11.flush()

    colaborador = contexto_f11.colaboradores[0]
    espelho_no_periodo_da_fixture = await _criar_espelho(
        sessao_f11, contexto_f11, colaborador_indice=0, tipo="oficial", versao=1
    )
    espelho_no_outro_periodo = Espelho(
        tenant_id=contexto_f11.tenant_id,
        periodo_id=outro_periodo_id,
        colaborador_id=colaborador.colaborador_id,
        vinculo_id=colaborador.vinculo_id,
        versao=1,
        tipo="oficial",
        conteudo={"dias": []},
        hash_sha256=_hash_de_exemplo("outro-periodo"),
    )
    sessao_f11.add(espelho_no_outro_periodo)
    await sessao_f11.flush()

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id, periodo_id=contexto_f11.periodo_id
        ),
    )

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0]["versao"] == espelho_no_periodo_da_fixture.versao
    assert resultado.linhas[0]["periodoCodigo"] != "OUTRO-PERIODO-F11"


async def test_filtro_colaborador_id_restringe_ao_vinculo_certo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _criar_espelho(sessao_f11, contexto_f11, colaborador_indice=0, tipo="oficial")
    await _criar_espelho(sessao_f11, contexto_f11, colaborador_indice=1, tipo="oficial")

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    alvo = contexto_f11.colaboradores[1]
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id, colaborador_id=alvo.colaborador_id
        ),
    )

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0]["colaboradorNome"] == alvo.nome


async def test_filtro_vinculo_id_via_filtros_json(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _criar_espelho(sessao_f11, contexto_f11, colaborador_indice=0, tipo="oficial")
    await _criar_espelho(sessao_f11, contexto_f11, colaborador_indice=1, tipo="oficial")

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    alvo = contexto_f11.colaboradores[0]
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id,
            filtros={"vinculoId": str(alvo.vinculo_id)},
        ),
    )

    assert len(resultado.linhas) == 1
    assert str(resultado.linhas[0]["vinculoId"]) == str(alvo.vinculo_id)


async def test_filtro_tipo_json_estreita_para_so_oficial(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=1)
    await _criar_espelho(sessao_f11, contexto_f11, tipo="retificado", versao=2)

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id, filtros={"tipo": "oficial"}),
    )

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0]["tipo"] == "oficial"


async def test_filtro_tipo_previo_via_filtros_json_devolve_zero_linhas_nao_erro(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """`previo` nunca pertence a este relatório (ver docstring do módulo) --
    mesmo pedindo explicitamente via `filtros.tipo`, a restrição de base
    (`oficial`/`retificado`) some com o resultado, não vira erro."""
    await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=1)

    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id, filtros={"tipo": "previo"}),
    )

    assert resultado.linhas == []


async def test_filtro_vinculo_id_malformado_responde_val_005(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await executar_dataset(
            sessao_f11,
            contexto_f11.tenant_id,
            definicao,
            filtros=ContextoConsulta(
                tenant_id=contexto_f11.tenant_id, filtros={"vinculoId": "nao-e-um-uuid"}
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


async def test_nao_escreve_em_espelhos_nem_assinaturas_espelho(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """`espelho_oficial` é só `SELECT` -- chamar o dataset várias vezes nunca
    muda a contagem de linhas em `espelhos`/`assinaturas_espelho` (proibição
    2, PCF §9)."""
    espelho = await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial")
    await _assinar_espelho(sessao_f11, contexto_f11, espelho)

    async def _contagens() -> tuple[int, int]:
        total_espelhos = (
            await sessao_f11.execute(
                sa.select(sa.func.count())
                .select_from(Espelho)
                .where(Espelho.tenant_id == contexto_f11.tenant_id)
            )
        ).scalar_one()
        total_assinaturas = (
            await sessao_f11.execute(
                sa.select(sa.func.count())
                .select_from(AssinaturaEspelho)
                .where(AssinaturaEspelho.tenant_id == contexto_f11.tenant_id)
            )
        ).scalar_one()
        return total_espelhos, total_assinaturas

    antes = await _contagens()
    definicao = await _definicao_espelho_oficial(sessao_f11, contexto_f11)
    for _ in range(3):
        await executar_dataset(
            sessao_f11,
            contexto_f11.tenant_id,
            definicao,
            filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
        )
    depois = await _contagens()
    assert antes == depois


def test_espelho_oficial_e_registrado_no_catalogo() -> None:
    from app.relatorios.catalogo import datasets_registrados

    assert "espelho_oficial" in datasets_registrados()
    assert espelho_oficial.__name__ == "espelho_oficial"
