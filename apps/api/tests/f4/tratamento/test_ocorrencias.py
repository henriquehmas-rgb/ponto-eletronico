"""Testes de `atualizarOcorrencia` (compartilhado por operationId em
`app/routers/apuracoes.py`; ownership de A3 -- ver `ocorrencias.py`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from ponto_contracts import Ocorrencia
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import ocorrencias
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.tratamento.conftest import ContextoTratamento


async def _criar_ocorrencia(sessao: AsyncSession, ctx: ContextoTratamento) -> Ocorrencia:
    ocorrencia = Ocorrencia(
        tenant_id=ctx.tenant_id,
        colaborador_id=ctx.colaborador_id,
        vinculo_id=ctx.vinculo_id,
        data=dt.date(2026, 7, 10),
        codigo="marcacao_impar",
        severidade="alta",
        descricao="Dia com numero impar de marcacoes.",
        status="aberta",
    )
    sessao.add(ocorrencia)
    await sessao.flush()
    return ocorrencia


async def test_atualizar_ocorrencia_para_resolvida_preenche_carimbo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia = await _criar_ocorrencia(sessao_tratamento, contexto_tratamento)
    usuario_id = uuid.uuid4()

    atualizacao = esquemas.OcorrenciaAtualizar(
        status=esquemas.Status28.resolvida, resolucao="Tratamento de inclusao aprovado"
    )
    resolvida = await ocorrencias.atualizar_ocorrencia(
        sessao_tratamento, ocorrencia.id, atualizacao, usuario_id=usuario_id
    )
    assert resolvida.status == "resolvida"
    assert resolvida.resolucao == "Tratamento de inclusao aprovado"
    assert resolvida.resolvida_em is not None
    assert resolvida.resolvida_por == usuario_id


async def test_atualizar_ocorrencia_recusa_mudar_codigo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia = await _criar_ocorrencia(sessao_tratamento, contexto_tratamento)
    atualizacao = esquemas.OcorrenciaAtualizar(codigo=esquemas.Codigo.falta)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ocorrencias.atualizar_ocorrencia(
            sessao_tratamento, ocorrencia.id, atualizacao, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_atualizar_ocorrencia_inexistente_e_404(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    atualizacao = esquemas.OcorrenciaAtualizar(status=esquemas.Status28.em_tratamento)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ocorrencias.atualizar_ocorrencia(
            sessao_tratamento, uuid.uuid4(), atualizacao, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
