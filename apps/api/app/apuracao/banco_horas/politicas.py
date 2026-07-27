"""CRUD de `bh_politicas` (T5, tag `banco-horas`).

`criarPoliticaBancoHoras` valida em aplicacao, com mensagem melhor que o
`CHECK` cru do banco (que continua sendo a ultima linha de defesa, ver
`erros_bd.py`):

* `ck_bh_politicas_periodo_legal` -- regime `individual` <= 6 meses,
  `coletivo`/`convencao` <= 12 meses, `especial` sem limite proprio (o
  limite absoluto de 1..12 continua vindo da coluna `periodo_meses`,
  validado pelo schema Pydantic gerado). `PONTO-BH-003` quando excedido.
* Documento do acordo (`documentoAcordoId`) exigido quando o regime NAO e
  `especial` -- "sem ele o regime e juridicamente fragil", comentario da
  propria coluna em `schema.sql`. `PONTO-BH-006` quando ausente.

Nao ha `atualizarPoliticaBancoHoras`/`excluirPoliticaBancoHoras` no contrato
(openapi.yaml, tag `banco-horas`) -- so listar e criar.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import BhPolitica
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.erros_bd import traduzir_integridade
from app.apuracao.banco_horas.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_PERIODO_ACIMA_DO_LIMITE = "PONTO-BH-003"
CODIGO_ACORDO_AUSENTE = "PONTO-BH-006"

#: Limite legal por regime (`ck_bh_politicas_periodo_legal`). `especial` nao
#: entra no mapa: sem limite proprio, so o 1..12 absoluto da coluna.
_LIMITE_MESES_POR_REGIME: dict[str, int] = {"individual": 6, "coletivo": 12, "convencao": 12}

_CAMPOS_DECIMAL = ("fator_credito_padrao", "fator_debito_padrao")
_CAMPOS_ENUM = ("regime", "metodo_consumo", "acao_vencimento")

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(BhPolitica.codigo, str),
    "vigenciaInicio": CampoOrdenacao(BhPolitica.vigencia_inicio, dt.date.fromisoformat),
}


def _validar_periodo_legal(regime: str, periodo_meses: int) -> None:
    limite = _LIMITE_MESES_POR_REGIME.get(regime)
    if limite is not None and periodo_meses > limite:
        raise ErroDeAplicacao(
            CODIGO_PERIODO_ACIMA_DO_LIMITE,
            detalhe=(
                f"Regime '{regime}' admite compensacao em ate {limite} meses; "
                f"periodoMeses={periodo_meses} excede o limite legal."
            ),
        )


def _validar_documento_acordo(regime: str, documento_acordo_id: UUID | None) -> None:
    if regime != "especial" and documento_acordo_id is None:
        raise ErroDeAplicacao(
            CODIGO_ACORDO_AUSENTE,
            detalhe=(
                "documentoAcordoId e obrigatorio para os regimes individual, coletivo e "
                "convencao -- sem o acordo assinado o banco de horas e questionavel em "
                "juizo."
            ),
        )


def _normalizar_campos(campos: dict[str, object]) -> dict[str, object]:
    """Enums do Pydantic (`StrEnum`) e `float` de fator viram, respectivamente,
    `str` puro e `Decimal` -- mesmo tratamento de `app.pessoas.contratos`
    para os campos tipados de forma equivalente."""
    for chave in _CAMPOS_ENUM:
        valor = campos.get(chave)
        if valor is not None and hasattr(valor, "value"):
            campos[chave] = valor.value
    for chave in _CAMPOS_DECIMAL:
        valor = campos.get(chave)
        if valor is not None:
            campos[chave] = Decimal(str(valor))
    return campos


async def criar_politica_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.BhPoliticaCriar
) -> BhPolitica:
    _validar_periodo_legal(dados.regime.value, dados.periodo_meses)
    _validar_documento_acordo(dados.regime.value, dados.documento_acordo_id)

    campos = _normalizar_campos(dados.model_dump(exclude_unset=True))
    politica = BhPolitica(tenant_id=tenant_id, **campos)
    sessao.add(politica)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_RECURSO_NAO_ENCONTRADO) from exc
    return politica


async def obter_politica_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, politica_id: UUID
) -> BhPolitica:
    resultado = await sessao.execute(
        select(BhPolitica).where(
            BhPolitica.id == politica_id,
            BhPolitica.tenant_id == tenant_id,
            BhPolitica.excluido_em.is_(None),
        )
    )
    politica = resultado.scalar_one_or_none()
    if politica is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Politica de banco de horas nao encontrada."
        )
    return politica


async def listar_politicas_banco_horas(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    regime: str | None = None,
    vigente_em: dt.date | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[BhPolitica], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="vigenciaInicio"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(BhPolitica).where(
        BhPolitica.tenant_id == tenant_id, BhPolitica.excluido_em.is_(None)
    )
    if empresa_id is not None:
        consulta = consulta.where(BhPolitica.empresa_id == empresa_id)
    if regime is not None:
        consulta = consulta.where(BhPolitica.regime == regime)
    if ativo is not None:
        consulta = consulta.where(BhPolitica.ativo == ativo)
    if vigente_em is not None:
        consulta = consulta.where(
            BhPolitica.vigencia_inicio <= vigente_em,
            sa.or_(BhPolitica.vigencia_fim.is_(None), BhPolitica.vigencia_fim >= vigente_em),
        )

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=BhPolitica.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "codigo" if ordenacao.campo == "codigo" else "vigencia_inicio"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
