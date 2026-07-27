"""Reparo do agente A1: prova que `listarApuracoes`, `obterApuracao` e
`listarOcorrencias` (`app.apuracao.dominio.consulta`) devolvem dado REAL
contra banco de teste depois de uma apuracao existir -- as 3 operacoes desta
tag que `routers/apuracoes.py` ainda respondia com 501 (`NaoImplementado`)
antes deste reparo. Ownership de A1 (as outras 2 operacoes da tag,
`recalcularApuracoes`/`atualizarOcorrencia`, sao de A3 e ja tem teste
proprio em `tests/f4/tratamento/`).

Reusa o contexto minimo de `tests/f4/tratamento/conftest.py` (ver
`conftest.py` deste diretorio) -- vinculo SEM jornada/escala vigente, o que
faz `app.apuracao.dominio.servico.apurar_dia` cair no ramo `PONTO-APUR-002`
(`_gravar_nao_apurado`): grava uma linha real em `apuracoes_dia`
(`tipo_dia='nao_apurado'`, `status='com_ocorrencia'`) e abre uma
`ocorrencia` (`codigo='sem_marcacao'`) -- o suficiente para exercitar as 3
funcoes de leitura sem precisar da massa de jornada da F3 (a combinacao
jornada real + `apurar_dia` real, com zero marcacoes, ja e coberta pelo
golden dataset em `tests/f4/golden/`).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.consulta import (
    listar_apuracoes,
    listar_ocorrencias,
    obter_apuracao,
)
from app.apuracao.dominio.servico import CODIGO_OCORRENCIA_SEM_JORNADA_VIGENTE, apurar_dia
from tests.f4.tratamento.conftest import ContextoTratamento

_DATA_APURADA = dt.date(2026, 1, 5)


async def test_listar_e_obter_apuracao_devolvem_dado_real_apos_apurar_dia(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    criada = await apurar_dia(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        contexto_tratamento.vinculo_id,
        _DATA_APURADA,
    )
    assert criada.tipo_dia == "nao_apurado"
    assert criada.id is not None

    dados, paginacao = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA_APURADA,
        ate=_DATA_APURADA,
    )
    assert [linha.id for linha in dados] == [criada.id]
    assert dados[0].vinculo_id == contexto_tratamento.vinculo_id
    assert dados[0].data == _DATA_APURADA
    assert paginacao.tem_mais is False

    obtida = await obter_apuracao(sessao_tratamento, criada.id)
    assert obtida.id == criada.id
    assert obtida.vinculo_id == contexto_tratamento.vinculo_id
    assert obtida.componentes == []


async def test_listar_ocorrencias_devolve_dado_real_apos_apurar_dia(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    criada = await apurar_dia(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        contexto_tratamento.vinculo_id,
        _DATA_APURADA,
    )

    ocorrencias, paginacao = await listar_ocorrencias(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        colaborador_id=contexto_tratamento.colaborador_id,
    )
    assert len(ocorrencias) == 1
    assert ocorrencias[0].apuracao_dia_id == criada.id
    assert ocorrencias[0].codigo == CODIGO_OCORRENCIA_SEM_JORNADA_VIGENTE
    assert paginacao.tem_mais is False
