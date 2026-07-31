"""Prova de integração (não um teste de aceite formal, evidência extra para
o relatório de fechamento): o motor genérico (A1) executa datasets REAIS já
registrados por A2/A3/A4 contra a fixture compartilhada, sem nenhum ajuste
especial -- confirma que a âncora de coordenação (`dataset` string) e o
contrato de `ConstrutorDataset` (`catalogo.py`) realmente funcionam entre
módulos escritos por agentes diferentes, em paralelo.
"""

from __future__ import annotations

from ponto_contracts import RelatorioDefinicao
from sqlalchemy.ext.asyncio import AsyncSession

# Import por efeito colateral: fora do processo da aplicação real (que
# importa isto via `app/routers/relatorios.py`, ver comentário lá), um teste
# que chama `motor.executar_dataset` direto (sem subir `app.main`) precisa
# disparar o mesmo registro -- senão `obter_dataset` nunca encontra as
# funções reais de A2/A3/A4, mesmo com as 24 linhas do catálogo semeadas.
import app.relatorios.datasets  # noqa: F401
from app.relatorios import motor
from tests.f11.conftest import ContextoF11


async def test_motor_executa_espelho_jornada_real_de_a2(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    definicao = await sessao_f11.get(
        RelatorioDefinicao, contexto_f11.relatorio_ids["espelho-jornada"]
    )
    assert definicao is not None

    contexto = motor.montar_contexto_consulta(
        contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await motor.executar_dataset(
        sessao_f11, contexto_f11.tenant_id, definicao, filtros=contexto, limite=100
    )
    assert len(resultado.linhas) == 9  # 3 colaboradores x 3 dias uteis semeados pela fixture
    assert resultado.colunas  # A2 declarou colunas reais, o motor projeta todas


async def test_motor_executa_custo_horas_extras_real_de_a3(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    definicao = await sessao_f11.get(
        RelatorioDefinicao, contexto_f11.relatorio_ids["custo-horas-extras"]
    )
    assert definicao is not None

    contexto = motor.montar_contexto_consulta(
        contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await motor.executar_dataset(
        sessao_f11, contexto_f11.tenant_id, definicao, filtros=contexto, limite=100
    )
    # Nao afirma quantidade exata (dataset de A3, fora do meu ownership) --
    # so que o motor consegue executa-lo sem erro e devolve algo coerente.
    assert isinstance(resultado.linhas, list)


async def test_motor_executa_espelho_oficial_real_de_a4(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    definicao = await sessao_f11.get(
        RelatorioDefinicao, contexto_f11.relatorio_ids["espelho-oficial"]
    )
    assert definicao is not None

    contexto = motor.montar_contexto_consulta(contexto_f11.tenant_id)
    resultado = await motor.executar_dataset(
        sessao_f11, contexto_f11.tenant_id, definicao, filtros=contexto, limite=100
    )
    # Nenhum espelho foi gerado pela fixture (F10 nao roda aqui) -- zero
    # linhas e o resultado correto, nao um erro (PCF T12: "se o filtro nao
    # encontrar nenhum espelho... o relatorio devolve zero linhas").
    assert resultado.linhas == []
