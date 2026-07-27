"""CRUD de tratamentos e do catálogo de tipos de tratamento (T8).

`tratamentos` é a ÚNICA forma de corrigir a jornada (seção 9 do
`schema.sql`) -- este módulo nunca toca `marcacoes`. Um tratamento referencia
uma marcação existente apenas por `marcacao_id`; a coluna `marcacao_datahora`
(parte da FK composta `fk_tratamentos_marcacao` e do `CHECK
ck_tratamentos_marcacao`) é derivada aqui, lendo a marcação (somente leitura),
nunca aceita do cliente -- o schema `TratamentoCriar`/`TratamentoAtualizar`
gerado do contrato não expõe `marcacaoDatahora` (achado de contrato, ver
relatório da fase).

`tipos_tratamento` só tem leitura nesta fase (`listarTiposTratamento`); o
catálogo é seed/config (`migrations/seed_dev.py`, F1), nunca escrito por
rota.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Marcacao, TipoTratamento, Tratamento, Vinculo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.erros_bd import traduzir_integridade
from app.apuracao.tratamento.fechamento import verificar_periodo_aberto
from app.apuracao.tratamento.paginacao import (
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
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"

#: Situações a partir das quais `atualizarTratamento` é aceito (T8, "pronto
#: quando"): tratamento já decidido/cancelado/aplicado é imutável por PATCH,
#: a única correção possível é um recálculo (via cancelamento + novo
#: tratamento) ou a decisão em si (`decidirTratamento`, T9).
_STATUS_EDITAVEIS = frozenset({"rascunho", "pendente"})
#: Destinos aceitos de `status` dentro de um PATCH: só a submissão
#: rascunho -> pendente (ou permanecer no mesmo estágio). Aprovar, reprovar,
#: aplicar e cancelar têm rota própria (`decidirTratamento`,
#: `cancelarTratamento`) e nunca são alcançados por este PATCH.
_STATUS_DESTINO_PATCH_VALIDOS = frozenset({"rascunho", "pendente"})
#: Situações a partir das quais `cancelarTratamento` é aceito: qualquer uma
#: exceto já cancelado (idempotência negativa: cancelar de novo é erro, não
#: no-op silencioso, para não esconder um duplo clique de uma reprovação).
_STATUS_NAO_CANCELAVEIS = frozenset({"cancelado"})

_CAMPOS_ORDENACAO_TRATAMENTO: dict[str, CampoOrdenacao] = {
    "dataReferencia": CampoOrdenacao(Tratamento.data_referencia, dt.date.fromisoformat),
    "criadoEm": CampoOrdenacao(Tratamento.criado_em, dt.datetime.fromisoformat),
}
_CAMPOS_ORDENACAO_TIPO_TRATAMENTO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(TipoTratamento.codigo, str),
    "nome": CampoOrdenacao(TipoTratamento.nome, str),
}


#: Valores de enum StrEnum gerados pelo contrato chegam prontos como `str`
#: (StrEnum e' subtipo de `str`); ainda assim extraimos `.value` quando
#: presente por clareza e para casar com o padrao ja usado por
#: `app.pessoas.contratos` (F2).
def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def obter_vinculo(sessao: AsyncSession, vinculo_id: UUID) -> Vinculo:
    vinculo = await sessao.get(Vinculo, vinculo_id)
    if vinculo is None or vinculo.excluido_em is not None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


async def _resolver_marcacao_datahora(
    sessao: AsyncSession, marcacao_id: UUID | None
) -> dt.datetime | None:
    """Deriva `marcacao_datahora` a partir de `marcacao_id`, somente leitura
    (nunca escreve/altera `marcacoes`). `ck_tratamentos_marcacao` exige que
    os dois campos venham juntos ou nenhum -- como o contrato HTTP só expõe
    `marcacaoId`, a construção aqui garante o par sempre coerente."""
    if marcacao_id is None:
        return None
    marcacao = (
        await sessao.execute(sa.select(Marcacao).where(Marcacao.id == marcacao_id))
    ).scalar_one_or_none()
    if marcacao is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Marcacao nao encontrada.")
    return marcacao.datahora_marcacao


async def verificar_periodo_do_vinculo(
    sessao: AsyncSession, tenant_id: UUID, vinculo: Vinculo, data_referencia: dt.date
) -> None:
    await verificar_periodo_aberto(
        sessao,
        tenant_id,
        empresa_id=vinculo.empresa_id,
        data=data_referencia,
        unidade_id=vinculo.unidade_id,
        departamento_id=vinculo.departamento_id,
    )


async def obter_tratamento(sessao: AsyncSession, tratamento_id: UUID) -> Tratamento:
    tratamento = await sessao.get(Tratamento, tratamento_id)
    if tratamento is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Tratamento nao encontrado.")
    return tratamento


async def criar_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.TratamentoCriar,
    *,
    usuario_id: UUID | None,
) -> Tratamento:
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="motivo e obrigatorio.")

    # Achado de contrato (ver docstring do modulo e relatorio da fase):
    # `tratamentos.vinculo_id` e NOT NULL no schema, mas `TratamentoCriar
    # .vinculoId` e opcional. Sem um mecanismo saneado de "vinculo principal
    # do colaborador" no escopo desta fase, exigimos o campo explicitamente
    # em vez de inventar a resolucao.
    if dados.vinculo_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="vinculoId e obrigatorio na criacao de tratamento nesta fase.",
        )
    vinculo = await obter_vinculo(sessao, dados.vinculo_id)
    if vinculo.colaborador_id != dados.colaborador_id:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="vinculoId nao pertence ao colaboradorId informado."
        )

    tipo_tratamento = await sessao.get(TipoTratamento, dados.tipo_tratamento_id)
    if tipo_tratamento is None or tipo_tratamento.excluido_em is not None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Tipo de tratamento nao encontrado."
        )

    await verificar_periodo_do_vinculo(sessao, tenant_id, vinculo, dados.data_referencia)

    marcacao_datahora = await _resolver_marcacao_datahora(sessao, dados.marcacao_id)

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    campos["motivo"] = motivo
    campos["marcacao_datahora"] = marcacao_datahora
    for chave in ("sentido", "origem", "status"):
        if chave in campos and campos[chave] is not None:
            campos[chave] = _valor(campos[chave])

    tratamento = Tratamento(tenant_id=tenant_id, criado_por=usuario_id, **campos)
    sessao.add(tratamento)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return tratamento


async def atualizar_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    tratamento_id: UUID,
    dados: esquemas.TratamentoAtualizar,
    *,
    usuario_id: UUID | None,
) -> Tratamento:
    tratamento = await obter_tratamento(sessao, tratamento_id)
    if tratamento.status not in _STATUS_EDITAVEIS:
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=(
                f"Tratamento em situacao '{tratamento.status}' nao pode ser editado; "
                "apenas rascunho ou pendente."
            ),
        )

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)

    if "status" in campos and campos["status"] is not None:
        destino = _valor(campos["status"])
        if destino not in _STATUS_DESTINO_PATCH_VALIDOS:
            raise ErroDeAplicacao(
                CODIGO_TRANSICAO_INVALIDA,
                detalhe=(
                    f"Transicao para '{destino}' nao e aceita por este PATCH; use "
                    "decidirTratamento para aprovar/reprovar."
                ),
            )
        campos["status"] = destino

    vinculo_efetivo_id = campos.get("vinculo_id", tratamento.vinculo_id)
    data_efetiva = campos.get("data_referencia", tratamento.data_referencia)
    vinculo = await obter_vinculo(sessao, vinculo_efetivo_id)
    await verificar_periodo_do_vinculo(sessao, tenant_id, vinculo, data_efetiva)

    if "marcacao_id" in campos:
        campos["marcacao_datahora"] = await _resolver_marcacao_datahora(
            sessao, campos["marcacao_id"]
        )

    for chave in ("sentido", "origem"):
        if chave in campos and campos[chave] is not None:
            campos[chave] = _valor(campos[chave])

    if "motivo" in campos:
        motivo = (campos["motivo"] or "").strip()
        if not motivo:
            raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="motivo nao pode ficar vazio.")
        campos["motivo"] = motivo

    for campo, valor in campos.items():
        setattr(tratamento, campo, valor)
    tratamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return tratamento


async def cancelar_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    tratamento_id: UUID,
    *,
    usuario_id: UUID | None,
    motivo: str | None = None,
) -> Tratamento:
    """`DELETE` que cancela -- nunca apaga a linha (§9 proibicoes, item 12).
    `status` vira `cancelado` preservando a linha original (nenhum campo
    historico e sobrescrito); a auditoria grava o *antes*/*depois* do
    `status` como o "registro de cancelamento auditavel" exigido pelo T8.

    Quando o tratamento ja tinha sido `aplicado` (isto e', alguma apuracao ja
    o consumiu -- `aplicado_em is not None`), agenda o recalculo do dia
    afetado (T10) para que a apuracao deixe de refletir um tratamento que
    nao vale mais. Tratamento nunca `aplicado` nao precisa de recalculo: a
    apuracao nunca chegou a le-lo.
    """
    tratamento = await obter_tratamento(sessao, tratamento_id)
    if tratamento.status in _STATUS_NAO_CANCELAVEIS:
        raise ErroDeAplicacao(CODIGO_TRANSICAO_INVALIDA, detalhe="Tratamento ja esta cancelado.")

    status_anterior = tratamento.status
    precisa_recalculo = tratamento.aplicado_em is not None
    vinculo_id = tratamento.vinculo_id
    data_referencia = tratamento.data_referencia

    tratamento.status = "cancelado"
    tratamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    from app.identidade.auditoria.hash_chain import gravar_auditoria

    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="tratamento.cancelado",
        entidade="tratamentos",
        acao="revogar",
        entidade_id=tratamento.id,
        usuario_id=usuario_id,
        valor_anterior={"status": status_anterior},
        valor_novo={"status": "cancelado"},
        metadados={"motivo": motivo} if motivo else None,
    )

    if precisa_recalculo:
        # Import tardio: `recalcular_periodo` depende de `apurar_dia` (A1),
        # que pode ainda nao existir enquanto este modulo e' testado
        # isoladamente (T8) -- ver docstring de `recalculo.py`.
        from app.apuracao.tratamento.recalculo import recalcular_periodo

        await recalcular_periodo(
            sessao,
            tenant_id,
            vinculo_id=vinculo_id,
            inicio=data_referencia - dt.timedelta(days=1),
            fim=data_referencia + dt.timedelta(days=1),
            motivo="tratamento",
        )
    return tratamento


async def listar_tratamentos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    tipo_tratamento_id: UUID | None = None,
    status: str | None = None,
    origem: str | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    marcacao_id: UUID | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Tratamento], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_TRATAMENTO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Tratamento).where(Tratamento.tenant_id == tenant_id)
    if empresa_id is not None:
        consulta = consulta.join(Vinculo, Vinculo.id == Tratamento.vinculo_id).where(
            Vinculo.empresa_id == empresa_id
        )
    if colaborador_id is not None:
        consulta = consulta.where(Tratamento.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(Tratamento.vinculo_id == vinculo_id)
    if tipo_tratamento_id is not None:
        consulta = consulta.where(Tratamento.tipo_tratamento_id == tipo_tratamento_id)
    if status is not None:
        consulta = consulta.where(Tratamento.status == status)
    if origem is not None:
        consulta = consulta.where(Tratamento.origem == origem)
    if de is not None:
        consulta = consulta.where(Tratamento.data_referencia >= de)
    if ate is not None:
        consulta = consulta.where(Tratamento.data_referencia <= ate)
    if marcacao_id is not None:
        consulta = consulta.where(Tratamento.marcacao_id == marcacao_id)

    campo = _CAMPOS_ORDENACAO_TRATAMENTO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Tratamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "criado_em" if ordenacao.campo == "criadoEm" else "data_referencia"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def listar_tipos_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    categoria: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[TipoTratamento], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_TIPO_TRATAMENTO), padrao="codigo"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(TipoTratamento).where(
        TipoTratamento.tenant_id == tenant_id, TipoTratamento.excluido_em.is_(None)
    )
    if categoria is not None:
        consulta = consulta.where(TipoTratamento.categoria == categoria)
    if ativo is not None:
        consulta = consulta.where(TipoTratamento.ativo == ativo)

    campo = _CAMPOS_ORDENACAO_TIPO_TRATAMENTO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoTratamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "codigo" if ordenacao.campo == "codigo" else "nome"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
