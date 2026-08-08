"""Substituto de `app.apuracao.dominio.servico.apurar_dia` para os testes de
T9 (decisão) e T10 (recálculo) desta fase.

`app.apuracao.dominio.servico` é ownership exclusivo de A1 (T2..T4 do PCF) e
pode ainda não existir -- ou ainda não estar completo -- no momento em que
os testes de A3 rodam (os quatro agentes trabalham em paralelo; ver PCF §5
e a nota do orquestrador: "import fica quebrado até A1 terminar -- isso é
esperado"). `recalcular_periodo`/`decidir_tratamento` importam `apurar_dia`
de forma TARDIA (dentro da própria função, não no topo do módulo) exatamente
para permitir que este substituto seja instalado em `sys.modules` ANTES da
chamada, nos testes -- sem exigir que o motor real de A1 já exista, e sem
testar (nem duplicar) a lógica de cálculo dele, que é propriedade exclusiva
de A1 e verificada pelo golden dataset de A4 (T11).

O substituto simula fielmente o CONTRATO documentado de `apurar_dia` (PCF
§4, T4 "pronto quando"): dado `(sessao, tenant_id, vinculo_id, data)`,
calcula um hash determinístico a partir de um "marcador" que o teste
controla (`definir_marcador`), faz `INSERT ... ON CONFLICT DO UPDATE` em
`apuracoes_dia` comparando o hash anterior -- *no-op* (não reescreve) se
igual, senão grava e incrementa `versao` -- e devolve o schema Pydantic
`contrato.ApuracaoDia`, com uma linha de `apuracao_componentes` quando o
resultado muda. Não implementa nenhuma regra de cálculo de jornada.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
import types
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import ApuracaoComponente, ApuracaoDia, Vinculo
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import contrato

NOME_MODULO = "app.apuracao.dominio.servico"

#: `(vinculo_id, data)` -> marcador de texto livre. O teste muda o marcador
#: para simular "insumo mudou" (novo hash); o padrao ("default") produz
#: sempre o mesmo hash, simulando "nada mudou".
_MARCADORES: dict[tuple[UUID, dt.date], str] = {}


def definir_marcador(vinculo_id: UUID, data: dt.date, marcador: str) -> None:
    _MARCADORES[(vinculo_id, data)] = marcador


def limpar_marcadores() -> None:
    _MARCADORES.clear()


def _hash_do_marcador(marcador: str) -> str:
    return hashlib.sha256(marcador.encode("utf-8")).hexdigest()


async def apurar_dia_fake(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    data: dt.date,
    *,
    cache_resolucao: object | None = None,
) -> contrato.ApuracaoDia:
    # `cache_resolucao` (ADR-010) e aceito e IGNORADO de proposito: o
    # substituto nao chama o resolvedor de F3, entao nao tem o que cachear --
    # so precisa espelhar a assinatura real para `recalcular_periodo` poder
    # passar o cache como faz em producao.
    del cache_resolucao
    marcador = _MARCADORES.get((vinculo_id, data), "default")
    hash_entrada = _hash_do_marcador(marcador)

    linha = (
        await sessao.execute(
            sa.select(ApuracaoDia).where(
                ApuracaoDia.tenant_id == tenant_id,
                ApuracaoDia.vinculo_id == vinculo_id,
                ApuracaoDia.data == data,
            )
        )
    ).scalar_one_or_none()

    if linha is not None and linha.hash_entrada == hash_entrada:
        componentes = list(
            (
                await sessao.execute(
                    sa.select(ApuracaoComponente).where(
                        ApuracaoComponente.apuracao_dia_id == linha.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return _para_schema(linha, componentes)

    vinculo = await sessao.get(Vinculo, vinculo_id)
    if vinculo is None:
        raise RuntimeError("vinculo nao encontrado (dado deveria ter sido semeado pela fixture)")

    if linha is None:
        linha = ApuracaoDia(
            tenant_id=tenant_id,
            vinculo_id=vinculo_id,
            colaborador_id=vinculo.colaborador_id,
            data=data,
            empresa_id=vinculo.empresa_id,
            unidade_id=vinculo.unidade_id,
            tipo_dia="util",
            status="apurado",
            hash_entrada=hash_entrada,
            versao=1,
            saldo_minutos=len(marcador),
            trabalhado_minutos=480,
            normais_minutos=480,
        )
        sessao.add(linha)
    else:
        linha.hash_entrada = hash_entrada
        linha.versao = (linha.versao or 1) + 1
        linha.saldo_minutos = len(marcador)
        await sessao.execute(
            sa.delete(ApuracaoComponente).where(ApuracaoComponente.apuracao_dia_id == linha.id)
        )
    await sessao.flush()

    componente = ApuracaoComponente(
        tenant_id=tenant_id,
        apuracao_dia_id=linha.id,
        codigo="normal",
        categoria="normal",
        minutos=480,
        fator=Decimal("1.0"),
        minutos_equivalentes=480,
        origem="marcacao",
    )
    sessao.add(componente)
    await sessao.flush()

    return _para_schema(linha, [componente])


def _para_schema(linha: ApuracaoDia, componentes: list[ApuracaoComponente]) -> contrato.ApuracaoDia:
    dados: dict[str, Any] = {
        "id": linha.id,
        "tenant_id": linha.tenant_id,
        "vinculo_id": linha.vinculo_id,
        "colaborador_id": linha.colaborador_id,
        "data": linha.data,
        "empresa_id": linha.empresa_id,
        "tipo_dia": linha.tipo_dia,
        "status": linha.status,
        "versao": linha.versao,
        "hash_entrada": linha.hash_entrada,
        "saldo_minutos": linha.saldo_minutos,
        "trabalhado_minutos": linha.trabalhado_minutos,
        "normais_minutos": linha.normais_minutos,
        "componentes": [
            {
                "id": c.id if c.id is not None else uuid4(),
                "codigo": c.codigo,
                "categoria": c.categoria,
                "minutos": c.minutos,
                "fator": float(c.fator),
                "minutos_equivalentes": c.minutos_equivalentes,
                "origem": c.origem,
            }
            for c in componentes
        ],
    }
    return contrato.ApuracaoDia.model_validate(dados)


def instalar_modulo_falso() -> Iterator[None]:
    """Gerador usado por `apurar_dia_falso` (fixture pytest): injeta
    `app.apuracao.dominio` e `app.apuracao.dominio.servico` falsos em
    `sys.modules` durante o teste, restaurando o estado anterior ao final --
    nunca escreve em disco, nunca toca `apps/api/app/apuracao/dominio/**`
    (ownership de A1).

    Injeta a cadeia inteira (`app.apuracao.dominio` além de
    `app.apuracao.dominio.servico`) porque `from app.apuracao.dominio.servico
    import apurar_dia` resolve cada segmento do caminho hierarquicamente --
    só sobrescrever a folha em `sys.modules` não basta enquanto o pacote
    `app.apuracao.dominio` (T1..T4 de A1) ainda não existir em disco.
    """
    nome_pacote_dominio = "app.apuracao.dominio"
    modulo_dominio_original = sys.modules.get(nome_pacote_dominio)
    modulo_servico_original = sys.modules.get(NOME_MODULO)

    pacote_falso = types.ModuleType(nome_pacote_dominio)
    pacote_falso.__path__ = []  # type: ignore[attr-defined] # marca como pacote
    servico_falso = types.ModuleType(NOME_MODULO)
    servico_falso.apurar_dia = apurar_dia_fake  # type: ignore[attr-defined]
    pacote_falso.servico = servico_falso  # type: ignore[attr-defined]

    sys.modules[nome_pacote_dominio] = pacote_falso
    sys.modules[NOME_MODULO] = servico_falso
    try:
        yield
    finally:
        for nome, original in (
            (nome_pacote_dominio, modulo_dominio_original),
            (NOME_MODULO, modulo_servico_original),
        ):
            if original is not None:
                sys.modules[nome] = original
            else:
                sys.modules.pop(nome, None)
        limpar_marcadores()
