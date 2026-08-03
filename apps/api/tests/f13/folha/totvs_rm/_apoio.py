"""Fabricas de teste compartilhadas pelos tres exportadores TOTVS (T17,
agente A6). Fica em `totvs_rm/` (dentro do glob de ownership exclusivo de
A6 para testes, `apps/api/tests/f13/folha/totvs_rm/**`) e e importada pelos
testes de `totvs_protheus`/`totvs_datasul` -- mesmo raciocinio de
`app.integracoes.folha.totvs_rm._formatacao`, reaproveitado em vez de
triplicado.

Nao e um modulo de teste em si (nenhuma funcao `test_*`): so fabricas de
`LinhaApuracaoFolha`/`ContextoExportacaoFolha`
(`app.integracoes.folha.comum.protocolo`, real, publicado por A5/T15 -- nao
um tipo local inventado por A6)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha


def linha(**sobrescritas: Any) -> LinhaApuracaoFolha:
    base: dict[str, Any] = {
        "vinculo_id": uuid4(),
        "colaborador_id": uuid4(),
        "empresa_id": uuid4(),
        "unidade_id": None,
        "departamento_id": None,
        "departamento_codigo": None,
        "matricula": "00123",
        "cpf": "12345678909",
        "pis_nit": "12345678901",
        "nome_completo": "Jose da Silva",
        "empresa_cnpj": "12345678000190",
        "data": dt.date(2026, 7, 15),
        "componente_codigo": "he_50",
        "componente_descricao": "Hora extra 50%",
        "categoria": "extra",
        "minutos": 60,
        "fator": Decimal("1.5"),
        "minutos_equivalentes": 90,
        "origem": "marcacao",
        "rubrica": None,
    }
    base.update(sobrescritas)
    return LinhaApuracaoFolha(**base)


def contexto(
    *,
    parceiro: str,
    linhas: tuple[LinhaApuracaoFolha, ...] = (),
    mapeamento_rubricas: dict[str, Any] | None = None,
    configuracao: dict[str, Any] | None = None,
    tenant_id: UUID | None = None,
    integracao_id: UUID | None = None,
    processamento_id: UUID | None = None,
    empresa_id: UUID | None = None,
) -> ContextoExportacaoFolha:
    return ContextoExportacaoFolha(
        tenant_id=tenant_id or uuid4(),
        integracao_id=integracao_id or uuid4(),
        processamento_id=processamento_id or uuid4(),
        empresa_id=empresa_id or uuid4(),
        empresa_cnpj="12345678000190",
        parceiro=parceiro,
        competencia_folha="2026-07",
        periodo_id=None,
        unidade_id=None,
        somente_fechados=True,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        configuracao=configuracao or {},
        mapeamento_rubricas=mapeamento_rubricas or {},
        linhas=linhas,
        gerado_em=dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.UTC),
    )
