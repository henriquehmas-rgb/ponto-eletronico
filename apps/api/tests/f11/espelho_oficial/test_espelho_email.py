"""Testes de `app.relatorios.entrega.espelho_email` (T13, F11/A4).

Mesmo padrão de fixture/seed de `test_espelho_oficial.py` (mesmo diretório
-- ver ownership PCF §5: A4 só tem `tests/f11/espelho_oficial/**` e
`tests/f11/pdf_espelho/**` nomeados explicitamente; o teste deste módulo
mora aqui por afinidade de domínio, não em um terceiro diretório
`tests/f11/entrega/**` que o PCF não concedeu a A4).
"""

from __future__ import annotations

import datetime as dt
import hashlib

from ponto_contracts import AssinaturaEspelho, Espelho
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.entrega.espelho_email import entregar_espelho_por_email
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
    conteudo_ref: str | None = None,
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
        conteudo_ref=conteudo_ref,
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


async def test_sem_destinatarios_devolve_false_sem_erro(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    resultado = await entregar_espelho_por_email(
        sessao_f11,
        contexto_f11.tenant_id,
        vinculo_id=colaborador.vinculo_id,
        periodo_id=contexto_f11.periodo_id,
        destinatarios=[],
    )
    assert resultado is False


async def test_sem_espelho_assinado_devolve_false_sem_erro(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    # Espelho existe mas NAO esta assinado.
    await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=1)

    resultado = await entregar_espelho_por_email(
        sessao_f11,
        contexto_f11.tenant_id,
        vinculo_id=colaborador.vinculo_id,
        periodo_id=contexto_f11.periodo_id,
        destinatarios=["rh@f11.teste"],
    )
    assert resultado is False


async def test_sem_nenhum_espelho_gerado_devolve_false_sem_erro(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    resultado = await entregar_espelho_por_email(
        sessao_f11,
        contexto_f11.tenant_id,
        vinculo_id=colaborador.vinculo_id,
        periodo_id=contexto_f11.periodo_id,
        destinatarios=["rh@f11.teste"],
    )
    assert resultado is False


async def test_espelho_assinado_devolve_true(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    espelho = await _criar_espelho(
        sessao_f11, contexto_f11, tipo="oficial", versao=1, conteudo_ref="espelhos/x/y.pdf"
    )
    await _assinar_espelho(sessao_f11, contexto_f11, espelho)

    resultado = await entregar_espelho_por_email(
        sessao_f11,
        contexto_f11.tenant_id,
        vinculo_id=colaborador.vinculo_id,
        periodo_id=contexto_f11.periodo_id,
        destinatarios=["rh@f11.teste"],
    )
    assert resultado is True


async def test_escolhe_a_versao_mais_recente_assinada_entre_varias(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador = contexto_f11.colaboradores[0]
    v1 = await _criar_espelho(sessao_f11, contexto_f11, tipo="oficial", versao=1)
    await _assinar_espelho(sessao_f11, contexto_f11, v1)
    v2 = await _criar_espelho(sessao_f11, contexto_f11, tipo="retificado", versao=2)
    await _assinar_espelho(sessao_f11, contexto_f11, v2)

    # A funcao nao expoe qual versao escolheu diretamente -- prova indireta
    # via `_espelho_assinado_mais_recente` (mesmo modulo, uso interno de
    # teste, mesma tecnica que outros testes desta fase usam para conferir
    # helper privado sem inflar a API publica do modulo).
    from app.relatorios.entrega.espelho_email import _espelho_assinado_mais_recente

    escolhido = await _espelho_assinado_mais_recente(
        sessao_f11, contexto_f11.tenant_id, colaborador.vinculo_id, contexto_f11.periodo_id
    )
    assert escolhido is not None
    assert escolhido.versao == 2
    assert escolhido.id == v2.id


async def test_espelho_previo_assinado_nao_conta_como_oficial(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Mesma restricao de base do dataset de T12: `previo` nunca e "o
    espelho oficial assinado", mesmo com uma linha de assinatura real."""
    colaborador = contexto_f11.colaboradores[0]
    previo = await _criar_espelho(sessao_f11, contexto_f11, tipo="previo", versao=1)
    await _assinar_espelho(sessao_f11, contexto_f11, previo)

    resultado = await entregar_espelho_por_email(
        sessao_f11,
        contexto_f11.tenant_id,
        vinculo_id=colaborador.vinculo_id,
        periodo_id=contexto_f11.periodo_id,
        destinatarios=["rh@f11.teste"],
    )
    assert resultado is False
