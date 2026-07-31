"""T6 -- parte SÍNCRONA de `gerarAfd` (`solicitar_geracao_afd`): validação
antes de enfileirar. Não testa o processamento pesado (isso é
`gerar_afd_arquivo`, `test_gerador.py`) -- só o que o router precisa
decidir antes do `202`.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.fiscal.afd.gerador import solicitar_geracao_afd
from app.schemas import contrato as esquemas
from tests.f12.conftest import ContextoF12

_REDIS_URL = os.environ.get("PONTO_TEST_REDIS_URL", "redis://localhost:6379/0")


def _afd_criar(**sobrescreve: object) -> esquemas.AfdCriar:
    base: dict[str, object] = {
        "periodo_inicio": dt.date(2026, 7, 1),
        "periodo_fim": dt.date(2026, 7, 31),
        "assinar": True,
    }
    base.update(sobrescreve)
    return esquemas.AfdCriar.model_validate(base)


@pytest.mark.asyncio
async def test_sem_rep_p_id_responde_val_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_periodo_e_nsr_juntos_responde_val_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(rep_p_id=contexto_f12.rep_p_id, nsr_inicial=1, nsr_final=10),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_somente_nsr_responde_val_001_scaffold_nao_alcanca_worker(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Achado de contrato/scaffold documentado em `app.fiscal.afd.gerador`:
    `nsrInicial`/`nsrFinal` não alcançam o worker pela assinatura fixada de
    `gerar_afd(ctx, tenant_id, rep_p_id, inicio, fim, assinar,
    solicitante_id)`."""
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(
                rep_p_id=contexto_f12.rep_p_id,
                periodo_inicio=None,
                periodo_fim=None,
                nsr_inicial=1,
                nsr_final=10,
            ),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"
    assert "scaffold" in (excinfo.value.detalhe or "") or "worker" in (excinfo.value.detalhe or "")


@pytest.mark.asyncio
async def test_sem_periodo_nem_nsr_responde_val_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(rep_p_id=contexto_f12.rep_p_id, periodo_inicio=None, periodo_fim=None),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_periodo_fim_antes_do_inicio_responde_val_007(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(
                rep_p_id=contexto_f12.rep_p_id,
                periodo_inicio=dt.date(2026, 7, 31),
                periodo_fim=dt.date(2026, 7, 1),
            ),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-007"


@pytest.mark.asyncio
async def test_fracionar_true_responde_val_001_scaffold_nao_alcanca_worker(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(
                rep_p_id=contexto_f12.rep_p_id, fracionar=True, tamanho_fracao_registros=100
            ),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_rep_p_inexistente_responde_rec_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(rep_p_id=uuid.uuid4()),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_rep_p_sem_numero_inpi_responde_fisc_003(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    from ponto_contracts import RepP

    rep_p = await sessao_f12.get(RepP, contexto_f12.rep_p_id)
    assert rep_p is not None
    rep_p.numero_inpi = ""

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(rep_p_id=contexto_f12.rep_p_id),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-FISC-003"


@pytest.mark.asyncio
async def test_geracao_em_andamento_responde_fisc_002(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    from ponto_contracts import AfdArquivo

    linha_presa = AfdArquivo(
        tenant_id=contexto_f12.tenant_id,
        empresa_id=contexto_f12.empresa_id,
        rep_p_id=contexto_f12.rep_p_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nsr_inicial=1,
        nsr_final=1,
        nome_arquivo="AFD_PENDENTE.txt",
        status="gerando",
    )
    sessao_f12.add(linha_presa)
    await sessao_f12.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await solicitar_geracao_afd(
            sessao_f12,
            contexto_f12.tenant_id,
            _afd_criar(rep_p_id=contexto_f12.rep_p_id),
            usuario_id=None,
            redis_url=_REDIS_URL,
        )
    assert excinfo.value.codigo == "PONTO-FISC-002"


@pytest.mark.asyncio
async def test_pedido_valido_enfileira_e_devolve_processamento_assincrono(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Caminho feliz: enfileira de verdade no Redis de teste
    (`PONTO_TEST_REDIS_URL`) e devolve `ProcessamentoAssincrono` com `id`
    efêmero (ver docstring do módulo `app.fiscal.afd.gerador` sobre por que
    esse `id` não é uma linha de `afd_arquivos`)."""
    resultado = await solicitar_geracao_afd(
        sessao_f12,
        contexto_f12.tenant_id,
        _afd_criar(rep_p_id=contexto_f12.rep_p_id),
        usuario_id=None,
        redis_url=_REDIS_URL,
    )
    assert resultado.status == esquemas.Status62.enfileirado
    assert resultado.tipo == esquemas.Tipo42.afd
    assert resultado.id is not None
