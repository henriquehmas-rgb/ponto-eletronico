"""Prova da ferramenta de auditoria/correcao dos dados antigos do ADR-011
(`apps/api/tools/auditar_afastamento_adr011.py`).

O fix do ADR-011 (2026-08-07, commit `2b44875`) vale para apuracoes NOVAS ou
reprocessadas -- as linhas de `apuracoes_dia` gravadas ANTES dele continuam com
a falta nao abonada ate alguem reprocessa-las. Estes testes montam exatamente
esse dado "sujo" (linha inserida direto via ORM, com `falta_minutos > 0` num
dia que hoje seria de afastamento e um `hash_entrada` antigo qualquer -- mesmo
recurso que os demais testes desta fase ja usam para simular estado
pre-existente) e verificam os tres comportamentos que a ferramenta promete:

1. `--dry-run` (padrao) DETECTA e NAO altera nada.
2. `--aplicar` corrige de verdade (`falta_minutos = 0`,
   `abono_minutos = previsto_minutos`, `tipo_dia = 'afastamento'`).
3. Uma linha LIMPA (dia util de verdade, sem afastamento nem tratamento) nao e
   detectada nem tocada em nenhum dos dois modos.

Os dois caminhos que produzem o dado sujo sao cobertos separadamente: o "de
fabrica" (tabela `afastamentos`, criterio B/A da ferramenta) e o retroativo
(`Tratamento` de categoria `afastamento`, criterio C -- o gap original do
ADR-011, que ANTES do fix nem sequer rotulava `tipo_dia`, e por isso nao seria
achado por uma auditoria que olhasse so o sintoma `tipo_dia='afastamento'`).
"""

from __future__ import annotations

import datetime as dt
import secrets

from ponto_contracts import (
    Afastamento,
    ApuracaoDia,
    TipoAfastamento,
    TipoTratamento,
    Tratamento,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f10.conftest import ContextoF10
from tools.auditar_afastamento_adr011 import blocos_contiguos, executar

#: Segunda e terca uteis na jornada de `contexto_f10` (480 min/dia), dentro do
#: periodo ABERTO que a fixture cria para o mes corrente.
_DIA_SUJO = dt.date(2026, 8, 10)
_DIA_LIMPO = dt.date(2026, 8, 11)

#: `apuracoes_dia.hash_entrada` e do dominio `dom_sha256` -- qualquer valor de
#: 64 hex serve como "hash da apuracao antiga", so precisa ser diferente do que
#: `apurar_dia` calcula hoje (e e, porque o `abonoMinutos` entra no hash).
_HASH_ANTIGO = "0" * 64


async def _inserir_apuracao_crua(
    sessao: AsyncSession,
    contexto: ContextoF10,
    *,
    data: dt.date,
    tipo_dia: str,
    falta_minutos: int,
) -> ApuracaoDia:
    """Grava uma linha de `apuracoes_dia` direto via ORM, como se tivesse sido
    materializada pela versao ANTERIOR ao fix do ADR-011."""
    linha = ApuracaoDia(
        tenant_id=contexto.tenant_id,
        vinculo_id=contexto.vinculo_id,
        colaborador_id=contexto.colaborador_id,
        data=data,
        empresa_id=contexto.empresa_id,
        unidade_id=contexto.unidade_id,
        jornada_id=contexto.jornada_id,
        horario_id=contexto.horario_id,
        tipo_dia=tipo_dia,
        previsto_minutos=480,
        falta_minutos=falta_minutos,
        abono_minutos=0,
        saldo_minutos=-falta_minutos,
        banco_debito_minutos=falta_minutos,
        status="apurado",
        hash_entrada=_HASH_ANTIGO,
        versao=1,
    )
    sessao.add(linha)
    await sessao.flush()
    return linha


async def _criar_afastamento_aprovado(
    sessao: AsyncSession, contexto: ContextoF10, *, data: dt.date
) -> Afastamento:
    tipo = TipoAfastamento(
        tenant_id=contexto.tenant_id,
        codigo=f"LICMED-{secrets.token_hex(5)}",
        nome="Licenca medica (teste auditoria ADR-011)",
        categoria="atestado",
        ativo=True,
    )
    sessao.add(tipo)
    await sessao.flush()

    afastamento = Afastamento(
        tenant_id=contexto.tenant_id,
        colaborador_id=contexto.colaborador_id,
        vinculo_id=contexto.vinculo_id,
        tipo_afastamento_id=tipo.id,
        data_inicio=data,
        data_fim=data,
        periodo_parcial=False,
        status="aprovado",
        origem="manual",
    )
    sessao.add(afastamento)
    await sessao.flush()
    return afastamento


async def _ler(sessao: AsyncSession, contexto: ContextoF10, data: dt.date) -> ApuracaoDia:
    linha = (
        await sessao.execute(
            select(ApuracaoDia).where(
                ApuracaoDia.tenant_id == contexto.tenant_id,
                ApuracaoDia.vinculo_id == contexto.vinculo_id,
                ApuracaoDia.data == data,
            )
        )
    ).scalar_one()
    await sessao.refresh(linha)
    return linha


def test_blocos_contiguos_agrupa_apenas_dias_consecutivos() -> None:
    """A ferramenta chama `recalcular_periodo` por BLOCO de dias consecutivos
    justamente para nao reprocessar nenhum dia fora do conjunto identificado --
    esta e a garantia que sustenta essa promessa."""
    assert blocos_contiguos([]) == []
    assert blocos_contiguos([dt.date(2026, 8, 10)]) == [
        (dt.date(2026, 8, 10), dt.date(2026, 8, 10))
    ]
    assert blocos_contiguos(
        [dt.date(2026, 8, 12), dt.date(2026, 8, 10), dt.date(2026, 8, 11), dt.date(2026, 8, 20)]
    ) == [
        (dt.date(2026, 8, 10), dt.date(2026, 8, 12)),
        (dt.date(2026, 8, 20), dt.date(2026, 8, 20)),
    ]


async def test_dry_run_detecta_apuracao_suja_de_afastamento_sem_alterar_nada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    await _criar_afastamento_aprovado(sessao_f10, contexto_f10, data=_DIA_SUJO)
    await _inserir_apuracao_crua(
        sessao_f10, contexto_f10, data=_DIA_SUJO, tipo_dia="afastamento", falta_minutos=480
    )
    await _inserir_apuracao_crua(
        sessao_f10, contexto_f10, data=_DIA_LIMPO, tipo_dia="util", falta_minutos=480
    )

    relatorio = await executar(sessao_f10, tenants=[contexto_f10.tenant_id])

    assert len(relatorio.linhas) == 1
    achada = relatorio.linhas[0]
    assert achada.data == _DIA_SUJO
    assert achada.vinculo_id == contexto_f10.vinculo_id
    assert achada.falta_minutos == 480
    assert relatorio.total_falta_minutos == 480
    assert relatorio.colaboradores == [contexto_f10.colaborador_id]
    # Criterio A (`tipo_dia='afastamento'`) e B (afastamento vigente cobrindo o
    # dia) casam; C (tratamento retroativo) nao -- este e o caminho "de fabrica".
    assert achada.criterios == "AB-"

    # Dry-run e o PADRAO: nada foi escrito, nem na linha suja nem na limpa.
    assert relatorio.aplicado is False
    assert relatorio.correcoes == []
    suja = await _ler(sessao_f10, contexto_f10, _DIA_SUJO)
    assert (suja.falta_minutos, suja.abono_minutos, suja.versao) == (480, 0, 1)
    limpa = await _ler(sessao_f10, contexto_f10, _DIA_LIMPO)
    assert (limpa.falta_minutos, limpa.abono_minutos, limpa.versao) == (480, 0, 1)


async def test_aplicar_corrige_a_linha_suja_e_nao_toca_a_linha_limpa(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    await _criar_afastamento_aprovado(sessao_f10, contexto_f10, data=_DIA_SUJO)
    await _inserir_apuracao_crua(
        sessao_f10, contexto_f10, data=_DIA_SUJO, tipo_dia="afastamento", falta_minutos=480
    )
    await _inserir_apuracao_crua(
        sessao_f10, contexto_f10, data=_DIA_LIMPO, tipo_dia="util", falta_minutos=480
    )
    await sessao_f10.commit()

    relatorio = await executar(sessao_f10, aplicar=True, tenants=[contexto_f10.tenant_id])

    assert relatorio.aplicado is True
    assert len(relatorio.correcoes) == 1
    correcao = relatorio.correcoes[0]
    assert correcao.data == _DIA_SUJO
    assert (correcao.falta_antes, correcao.abono_antes) == (480, 0)
    assert (correcao.falta_depois, correcao.abono_depois) == (0, 480)
    assert correcao.tipo_dia_depois == "afastamento"
    assert correcao.corrigida is True
    assert relatorio.dias_ignorados_fechados == 0

    suja = await _ler(sessao_f10, contexto_f10, _DIA_SUJO)
    assert suja.falta_minutos == 0
    assert suja.abono_minutos == 480
    assert suja.tipo_dia == "afastamento"
    assert suja.hash_entrada != _HASH_ANTIGO
    assert suja.versao == 2

    # A linha limpa (dia util de verdade, sem afastamento nem tratamento) nao
    # entrou no escopo do recalculo: continua byte a byte como estava, inclusive
    # `versao` -- prova de que a ferramenta so toca nos dias identificados.
    limpa = await _ler(sessao_f10, contexto_f10, _DIA_LIMPO)
    assert (limpa.falta_minutos, limpa.abono_minutos, limpa.versao) == (480, 0, 1)
    assert limpa.tipo_dia == "util"
    assert limpa.hash_entrada == _HASH_ANTIGO


async def test_detecta_e_corrige_o_caso_retroativo_ainda_rotulado_como_util(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Criterio C: antes do fix, um `Tratamento` de categoria `afastamento`
    aprovado nao produzia efeito NENHUM -- a linha ficava `tipo_dia = 'util'`
    com a falta cheia. Uma auditoria pelo sintoma `tipo_dia='afastamento'`
    sozinho perderia exatamente o caso que o ADR-011 documentou."""
    tipo_tratamento = TipoTratamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"AFRETRO-{secrets.token_hex(5)}",
        nome="Afastamento retroativo (teste auditoria ADR-011)",
        categoria="afastamento",
        exige_aprovacao=True,
        ativo=True,
    )
    sessao_f10.add(tipo_tratamento)
    await sessao_f10.flush()

    sessao_f10.add(
        Tratamento(
            tenant_id=contexto_f10.tenant_id,
            colaborador_id=contexto_f10.colaborador_id,
            vinculo_id=contexto_f10.vinculo_id,
            tipo_tratamento_id=tipo_tratamento.id,
            data_referencia=_DIA_SUJO,
            motivo="Atestado medico retroativo (teste auditoria ADR-011).",
            status="aprovado",
            origem="sistema",
        )
    )
    await _inserir_apuracao_crua(
        sessao_f10, contexto_f10, data=_DIA_SUJO, tipo_dia="util", falta_minutos=480
    )
    await sessao_f10.commit()

    relatorio_dry = await executar(sessao_f10, tenants=[contexto_f10.tenant_id])
    assert len(relatorio_dry.linhas) == 1
    assert relatorio_dry.linhas[0].criterios == "--C"
    assert relatorio_dry.linhas[0].tipo_dia == "util"

    relatorio = await executar(sessao_f10, aplicar=True, tenants=[contexto_f10.tenant_id])
    assert len(relatorio.correcoes) == 1
    assert relatorio.correcoes[0].corrigida is True

    linha = await _ler(sessao_f10, contexto_f10, _DIA_SUJO)
    assert linha.falta_minutos == 0
    assert linha.abono_minutos == 480
    assert linha.tipo_dia == "afastamento"

    # Rodar a auditoria de novo nao encontra mais nada -- a correcao e estavel.
    relatorio_final = await executar(sessao_f10, tenants=[contexto_f10.tenant_id])
    assert relatorio_final.linhas == []
