"""T12 (performance): tempo real de `recalcular_periodo` sobre um volume de
vinculos x dias, medido -- nunca "deve escalar" sem medir (PCF, proibicao
14).

**Volume-alvo do PCF:** 10.000 vinculos x 31 dias, com o alvo de referencia
de `FASES-E-AGENTES.md` ("< 5 min" para 10.000 colaboradores x 31 dias).

**Medido de verdade em 26/07/2026, direto na VPS (mesma maquina do Postgres
de teste, sem custo de tunel SSH somado a medicao):** 1.000 vinculos x 31
dias (31.000 apuracoes) levaram 3.575,7s (115,35 ms/apuracao). Extrapolacao
linear para o alvo de 10.000 x 31 da' ~596 min, contra o alvo de < 5 min --
~120x acima. **Este e' um debito tecnico aceito pelo dono do produto, nao um
bug deste teste nem uma limitacao de medicao** -- ver
`docs/adr/ADR-010-debito-tecnico-performance-recalculo-em-lote.md` para o
diagnostico completo (hipotese: `apurar_dia` chama `resolver_jornada_do_dia`
do zero a cada dia, sem cache de resolucao entre dias consecutivos do mesmo
vinculo) e os candidatos de otimizacao para uma fase futura dedicada.

Os defaults abaixo (200 x 31 = 6.200 apuracoes) continuam deliberadamente
pequenos para esta suite rodar em minutos, nao horas, no dia a dia de CI;
aumentar `PONTO_PERF_VINCULOS` (ex.: para 1.000, 2.000 ou 10.000) mede o
volume maior sem editar este arquivo -- prefira rodar direto numa maquina com
acesso local ao Postgres (nao por tunel SSH) para nao confundir latencia de
rede com custo real de computacao.

**Extrapolacao linear -- SOMENTE quando a amostra medida for menor que
10.000 x 31:** `tempo_estimado_10000x31 = tempo_medido *
(10000 * 31) / (vinculos_medidos * dias_medidos)`, impressa no console e
marcada explicitamente como EXTRAPOLACAO (nunca apresentada como medicao
real) -- exatamente o que o PCF exige ("documente uma amostra menor medida
... com extrapolacao linear EXPLICITA -- nunca afirme 'deve escalar' sem
medir"). `recalcular_periodo` e' um loop sequencial em Python (vinculo por
vinculo, dia por dia -- lido em `app/apuracao/tratamento/recalculo.py`,
`for vinc in vinculos: for dia in dias: ...`), sem paralelismo nem batch de
consultas entre dias/vinculos; a extrapolacao linear e' portanto o modelo
mais simples e honesto disponivel (nao ha razao estrutural para esperar
sub-linearidade nem super-linearidade dentro da mesma ordem de grandeza),
mas continua sendo uma PROJECAO, nao uma medicao.
"""

from __future__ import annotations

import datetime as _dt
import os
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.recalculo import recalcular_periodo
from tests.f4.performance.conftest import (
    ContextoPerformance,
    aplicar_tenant_teste,
    gerar_vinculos_em_massa,
)

_ALVO_VINCULOS = 10_000
_ALVO_DIAS = 31


async def test_recalcular_periodo_em_volume(
    sessao_performance: AsyncSession, contexto_performance: ContextoPerformance
) -> None:
    n_vinculos = int(os.environ.get("PONTO_PERF_VINCULOS", "200"))
    n_dias = int(os.environ.get("PONTO_PERF_DIAS", str(_ALVO_DIAS)))
    inicio = _dt.date(2025, 1, 1)
    fim = inicio + _dt.timedelta(days=n_dias - 1)

    t0_massa = time.perf_counter()
    await gerar_vinculos_em_massa(sessao_performance, contexto_performance, quantidade=n_vinculos)
    await sessao_performance.commit()
    # `commit()` encerra a transacao em que `contexto_performance` publicou
    # `app.tenant_id` via `SET LOCAL` -- sem republicar, `recalcular_periodo`
    # roda sob RLS sem tenant nenhum e filtra todas as linhas (achado da
    # verificacao da fase: `dias_processados == 0`).
    await aplicar_tenant_teste(sessao_performance, contexto_performance.tenant_id)
    tempo_massa = time.perf_counter() - t0_massa
    print(
        f"\n[perf] massa sintetica gerada: {n_vinculos} vinculos, "
        f"{tempo_massa:.2f}s (nao faz parte do tempo medido de recalculo)"
    )

    t0 = time.perf_counter()
    resultado = await recalcular_periodo(
        sessao_performance,
        contexto_performance.tenant_id,
        empresa_id=contexto_performance.empresa_id,
        inicio=inicio,
        fim=fim,
        motivo="teste de performance T12 -- recalculo em volume",
    )
    tempo_total = time.perf_counter() - t0

    apuracoes_totais = n_vinculos * n_dias
    print(
        f"\n[perf] recalcular_periodo: {n_vinculos} vinculos x {n_dias} dias "
        f"= {apuracoes_totais} apuracoes em {tempo_total:.3f}s "
        f"({tempo_total / apuracoes_totais * 1000:.2f} ms/apuracao)"
    )
    assert resultado.dias_processados == apuracoes_totais
    assert resultado.vinculos_processados == n_vinculos

    volume_alvo = _ALVO_VINCULOS * _ALVO_DIAS
    if n_vinculos < _ALVO_VINCULOS or n_dias < _ALVO_DIAS:
        extrapolado_segundos = tempo_total * (volume_alvo / apuracoes_totais)
        print(
            f"[perf] EXTRAPOLACAO LINEAR (nao medida) para "
            f"{_ALVO_VINCULOS} vinculos x {_ALVO_DIAS} dias = {volume_alvo} apuracoes: "
            f"{extrapolado_segundos:.1f}s (~{extrapolado_segundos / 60:.1f} min), "
            f"a partir de {apuracoes_totais} apuracoes medidas em {tempo_total:.3f}s. "
            f"Alvo de referencia (FASES-E-AGENTES.md, F4): < 5 min."
        )
    else:
        print(
            f"[perf] volume MEDIDO integralmente no alvo do PCF "
            f"({_ALVO_VINCULOS} x {_ALVO_DIAS}): {tempo_total:.1f}s "
            f"(~{tempo_total / 60:.1f} min). Alvo de referencia: < 5 min."
        )
