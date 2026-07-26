"""Servicos de dominio de `feriado_conjuntos`, `feriados` e
`unidade_feriado_conjuntos`.

Um `feriado_conjunto` agrupa feriados por abrangencia (nacional, estadual,
municipal, empresa, unidade) mas so vale para uma unidade quando ha uma linha
explicita em `unidade_feriado_conjuntos` -- inclusive para conjuntos
nacionais (decisao fixada no PCF da F3, secao 2: "o motivo de
unidade_feriado_conjuntos existir"). Isto e o que impede o feriado municipal
de Uberlandia de vazar para a unidade de Belo Horizonte mesmo que as duas
pertencam ao mesmo tenant.

Feriados moveis nao guardam data: `resolver_ancora_movel`
(`feriados_moveis.py`) calcula a data efetiva a partir da Pascoa do ano
consultado. Um feriado fixo com `ano` ausente repete todo ano (o mes/dia de
`data` e reaplicado ao ano consultado); com `ano` presente, so se aplica
naquele ano especifico -- a mesma regra vale para moveis (o caso comum e
`ano` ausente).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from ponto_contracts import Feriado, FeriadoConjunto, UnidadeFeriadoConjunto
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario.erros_bd import traduzir_integridade
from app.jornada.calendario.feriados_moveis import REGRAS_MOVEIS, resolver_ancora_movel
from app.jornada.calendario.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    decodificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_DEPENDENTES = "PONTO-CONF-004"

_CAMPOS_ORDENACAO_CONJUNTO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(FeriadoConjunto.criado_em, dt.datetime.fromisoformat),
    "codigo": CampoOrdenacao(FeriadoConjunto.codigo, str),
    "nome": CampoOrdenacao(FeriadoConjunto.nome, str),
}


# ---------------------------------------------------------------------------
# Validacao de aplicacao (mensagem melhor que o CHECK cru do banco)
# ---------------------------------------------------------------------------
def _validar_abrangencia(
    abrangencia: str, uf: str | None, codigo_ibge_municipio: str | None
) -> None:
    """Espelha `ck_feriado_conjuntos_abrangencia`."""
    if abrangencia == "estadual" and not uf:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="uf e obrigatorio para conjunto de abrangencia estadual.",
        )
    if abrangencia == "municipal" and not codigo_ibge_municipio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="codigoIbgeMunicipio e obrigatorio para conjunto de abrangencia municipal.",
        )


def _validar_definicao_feriado(
    movel: bool, data: dt.date | None, regra_movel: str | None, offset_dias: int | None
) -> None:
    """Espelha `ck_feriados_definicao`. `custom` sem `offset_dias` cairia em
    cima da propria Pascoa -- quase nunca a intencao (PCF, secao 2) -- por
    isso e recusado aqui como corpo invalido, e nao silenciosamente aceito."""
    if movel:
        if not regra_movel:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="regraMovel e obrigatorio quando movel e verdadeiro."
            )
        if regra_movel not in REGRAS_MOVEIS:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe=f"regraMovel invalido: {regra_movel!r}."
            )
        if regra_movel == "custom" and not offset_dias:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO,
                detalhe="offsetDias e obrigatorio para regraMovel 'custom' (sem ele o feriado "
                "cairia em cima da propria Pascoa).",
            )
    else:
        if data is None:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="data e obrigatoria quando movel e falso."
            )


def _validar_parcial_feriado(integral: bool, carga_reduzida_minutos: int | None) -> None:
    """Espelha `ck_feriados_parcial`."""
    if not integral and carga_reduzida_minutos is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="cargaReduzidaMinutos e obrigatorio quando integral e falso.",
        )


# ---------------------------------------------------------------------------
# feriado_conjuntos
# ---------------------------------------------------------------------------
async def _obter_conjunto(
    sessao: AsyncSession, tenant_id: UUID, conjunto_id: UUID
) -> FeriadoConjunto:
    resultado = await sessao.execute(
        select(FeriadoConjunto).where(
            FeriadoConjunto.tenant_id == tenant_id,
            FeriadoConjunto.id == conjunto_id,
            FeriadoConjunto.excluido_em.is_(None),
        )
    )
    conjunto = resultado.scalar_one_or_none()
    if conjunto is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Conjunto de feriados nao encontrado."
        )
    return conjunto


async def _unidade_ids_do_conjunto(
    sessao: AsyncSession, tenant_id: UUID, conjunto_id: UUID
) -> list[UUID]:
    resultado = await sessao.execute(
        select(UnidadeFeriadoConjunto.unidade_id)
        .where(
            UnidadeFeriadoConjunto.tenant_id == tenant_id,
            UnidadeFeriadoConjunto.feriado_conjunto_id == conjunto_id,
        )
        .order_by(UnidadeFeriadoConjunto.criado_em)
    )
    return list(resultado.scalars().all())


async def _sincronizar_unidades(
    sessao: AsyncSession, tenant_id: UUID, conjunto_id: UUID, unidade_ids: list[UUID]
) -> None:
    """Trata `unidadeIds` como o estado desejado da associacao: insere o que
    falta, remove o que sobra. So chamada quando o campo foi explicitamente
    enviado no corpo -- omiti-lo preserva a associacao existente; enviar uma
    lista vazia e o unico jeito de remover todas as associacoes (nunca
    silencioso: e uma escolha explicita do consumidor da API)."""
    atuais_resultado = await sessao.execute(
        select(UnidadeFeriadoConjunto).where(
            UnidadeFeriadoConjunto.tenant_id == tenant_id,
            UnidadeFeriadoConjunto.feriado_conjunto_id == conjunto_id,
        )
    )
    atuais = {linha.unidade_id: linha for linha in atuais_resultado.scalars().all()}
    desejados = set(unidade_ids)
    for unidade_id in desejados - atuais.keys():
        sessao.add(
            UnidadeFeriadoConjunto(
                tenant_id=tenant_id, unidade_id=unidade_id, feriado_conjunto_id=conjunto_id
            )
        )
    for unidade_id in atuais.keys() - desejados:
        await sessao.delete(atuais[unidade_id])
    await sessao.flush()


async def criar_feriado_conjunto(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.FeriadoConjuntoCriar
) -> FeriadoConjunto:
    _validar_abrangencia(dados.abrangencia.value, dados.uf, dados.codigo_ibge_municipio)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True, exclude={"unidade_ids"})
    if "abrangencia" in campos:
        campos["abrangencia"] = dados.abrangencia.value
    conjunto = FeriadoConjunto(tenant_id=tenant_id, **campos)
    sessao.add(conjunto)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if dados.unidade_ids is not None:
        await _sincronizar_unidades(sessao, tenant_id, conjunto.id, dados.unidade_ids)
    conjunto.unidade_ids = await _unidade_ids_do_conjunto(sessao, tenant_id, conjunto.id)  # type: ignore[attr-defined]
    return conjunto


async def atualizar_feriado_conjunto(
    sessao: AsyncSession,
    tenant_id: UUID,
    conjunto_id: UUID,
    dados: esquemas.FeriadoConjuntoAtualizar,
) -> FeriadoConjunto:
    conjunto = await _obter_conjunto(sessao, tenant_id, conjunto_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True, exclude={"unidade_ids"})
    if "abrangencia" in campos:
        campos["abrangencia"] = dados.abrangencia.value if dados.abrangencia else None

    abrangencia_efetiva = campos.get("abrangencia", conjunto.abrangencia)
    uf_efetivo = campos.get("uf", conjunto.uf)
    ibge_efetivo = campos.get("codigo_ibge_municipio", conjunto.codigo_ibge_municipio)
    _validar_abrangencia(abrangencia_efetiva, uf_efetivo, ibge_efetivo)

    for campo, valor in campos.items():
        setattr(conjunto, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if dados.unidade_ids is not None:
        await _sincronizar_unidades(sessao, tenant_id, conjunto.id, dados.unidade_ids)
    conjunto.unidade_ids = await _unidade_ids_do_conjunto(sessao, tenant_id, conjunto.id)  # type: ignore[attr-defined]
    return conjunto


async def excluir_feriado_conjunto(
    sessao: AsyncSession, tenant_id: UUID, conjunto_id: UUID
) -> None:
    """Exclusao logica do conjunto e remocao (fisica) das associacoes com
    unidades -- `unidade_feriado_conjuntos` nao tem coluna de soft delete.
    Recusa (`PONTO-CONF-004`) quando ainda ha `feriados` deste conjunto:
    `feriados` tambem nao tem soft delete (so DELETE via `excluirFeriado`),
    entao exigir que o chamador limpe os feriados primeiro evita apagar
    silenciosamente o historico de datas que a apuracao ja usou."""
    conjunto = await _obter_conjunto(sessao, tenant_id, conjunto_id)
    tem_feriados = await sessao.execute(
        select(Feriado.id)
        .where(Feriado.tenant_id == tenant_id, Feriado.feriado_conjunto_id == conjunto_id)
        .limit(1)
    )
    if tem_feriados.scalar_one_or_none() is not None:
        raise ErroDeAplicacao(
            CODIGO_DEPENDENTES,
            detalhe=(
                "Exclua os feriados deste conjunto (excluirFeriado) antes de excluir o conjunto."
            ),
        )
    await _sincronizar_unidades(sessao, tenant_id, conjunto_id, [])
    conjunto.excluido_em = dt.datetime.now(tz=dt.UTC)
    await sessao.flush()


async def listar_feriado_conjuntos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    abrangencia: str | None = None,
    uf: str | None = None,
    unidade_id: UUID | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[FeriadoConjunto], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_CONJUNTO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(FeriadoConjunto).where(
        FeriadoConjunto.tenant_id == tenant_id, FeriadoConjunto.excluido_em.is_(None)
    )
    if abrangencia is not None:
        consulta = consulta.where(FeriadoConjunto.abrangencia == abrangencia)
    if uf is not None:
        consulta = consulta.where(FeriadoConjunto.uf == uf)
    if ativo is not None:
        consulta = consulta.where(FeriadoConjunto.ativo == ativo)
    if unidade_id is not None:
        consulta = consulta.where(
            FeriadoConjunto.id.in_(
                select(UnidadeFeriadoConjunto.feriado_conjunto_id).where(
                    UnidadeFeriadoConjunto.tenant_id == tenant_id,
                    UnidadeFeriadoConjunto.unidade_id == unidade_id,
                )
            )
        )

    campo = _CAMPOS_ORDENACAO_CONJUNTO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=FeriadoConjunto.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    for linha in linhas:
        linha.unidade_ids = await _unidade_ids_do_conjunto(sessao, tenant_id, linha.id)

    atributo = {"codigo": "codigo", "nome": "nome", "criadoEm": "criado_em"}[ordenacao.campo]
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


# ---------------------------------------------------------------------------
# feriados (resolucao de moveis, listagem efetiva por unidade/ano)
# ---------------------------------------------------------------------------
def resolver_data_feriado(feriado: Feriado, ano: int) -> dt.date | None:
    """Data efetiva do `feriado` no `ano` consultado, ou `None` se o feriado
    nao se aplica a este ano (`feriado.ano` presente e diferente do
    consultado).
    """
    if feriado.ano is not None and feriado.ano != ano:
        return None
    if feriado.movel:
        if feriado.regra_movel is None:
            # Nunca deveria acontecer: `ck_feriados_definicao` exige
            # `regra_movel` quando `movel = true`. Defensivo, nao 500.
            return None
        return resolver_ancora_movel(feriado.regra_movel, ano, feriado.offset_dias)
    if feriado.data is None:
        # Idem: `ck_feriados_definicao` exige `data` quando `movel = false`.
        return None
    if feriado.ano is not None:
        # Restrito a um ano especifico: a propria `data` ja e a data efetiva.
        return feriado.data
    try:
        return feriado.data.replace(year=ano)
    except ValueError:
        # 29/02 num ano nao bissexto: nao ha data efetiva neste ano.
        return None


async def _conjunto_ids_da_unidade(
    sessao: AsyncSession, tenant_id: UUID, unidade_id: UUID
) -> list[UUID]:
    resultado = await sessao.execute(
        select(UnidadeFeriadoConjunto.feriado_conjunto_id).where(
            UnidadeFeriadoConjunto.tenant_id == tenant_id,
            UnidadeFeriadoConjunto.unidade_id == unidade_id,
        )
    )
    return list(resultado.scalars().all())


async def listar_feriados(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    feriado_conjunto_id: UUID | None = None,
    unidade_id: UUID | None = None,
    ano: int | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    tipo: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[list[Feriado], esquemas.Paginacao]:
    """Lista feriados de um conjunto, ou os feriados EFETIVOS de uma unidade
    (somando todos os conjuntos associados a ela). Sem `ano`, resolve pelo
    ano corrente -- decisao deste modulo, documentada aqui porque o contrato
    nao fixa um padrao.

    Paginacao em memoria: o conjunto de feriados de um tenant/ano e sempre
    pequeno (dezenas, nao milhares), e resolver `dataResolvida` de um feriado
    movel nao e algo que o SQL deste projeto expressa (a formula da Pascoa e
    aritmetica de aplicacao, nao de banco) -- paginar em memoria evita
    duplicar o resolvedor em SQL so para um caso de uso de baixo volume.
    """
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset({"dataResolvida", "nome"}), padrao="dataResolvida"
    )
    limite_efetivo = normalizar_limite(limite)
    ano_efetivo = ano if ano is not None else dt.date.today().year

    consulta = select(Feriado).where(Feriado.tenant_id == tenant_id)
    if feriado_conjunto_id is not None:
        consulta = consulta.where(Feriado.feriado_conjunto_id == feriado_conjunto_id)
    elif unidade_id is not None:
        conjunto_ids = await _conjunto_ids_da_unidade(sessao, tenant_id, unidade_id)
        if not conjunto_ids:
            return [], montar_paginacao(proximo_cursor=None, tem_mais=False, limite=limite_efetivo)
        consulta = consulta.where(Feriado.feriado_conjunto_id.in_(conjunto_ids))
    if tipo is not None:
        consulta = consulta.where(Feriado.tipo == tipo)

    resultado = await sessao.execute(consulta)
    candidatos = list(resultado.scalars().all())

    resolvidos: list[tuple[Any, Feriado]] = []
    for feriado in candidatos:
        data_resolvida = resolver_data_feriado(feriado, ano_efetivo)
        if data_resolvida is None:
            continue
        if de is not None and data_resolvida < de:
            continue
        if ate is not None and data_resolvida > ate:
            continue
        feriado.data_resolvida = data_resolvida  # type: ignore[attr-defined]
        chave = data_resolvida if ordenacao.campo == "dataResolvida" else feriado.nome
        resolvidos.append((chave, feriado))

    reverso = ordenacao.direcao == "desc"
    resolvidos.sort(key=lambda par: (par[0], par[1].id), reverse=reverso)

    def _conversor(bruto: Any) -> Any:
        if ordenacao.campo == "dataResolvida":
            return dt.date.fromisoformat(bruto) if bruto is not None else None
        return bruto

    if cursor:
        valor_cursor_bruto, id_cursor = decodificar_cursor(cursor, ordenacao=ordenacao)
        valor_cursor = _conversor(valor_cursor_bruto)

        def _apos_cursor(par: tuple[Any, Feriado]) -> bool:
            chave, feriado = par
            tupla = (chave, feriado.id)
            tupla_cursor = (valor_cursor, id_cursor)
            return tupla < tupla_cursor if reverso else tupla > tupla_cursor

        resolvidos = [par for par in resolvidos if _apos_cursor(par)]

    pagina = resolvidos[: limite_efetivo + 1]
    tem_mais = len(pagina) > limite_efetivo
    pagina = pagina[:limite_efetivo]

    proximo_cursor = None
    if tem_mais and pagina:
        ultima_chave, ultimo_feriado = pagina[-1]
        proximo_cursor = codificar_cursor(ordenacao, ultima_chave, ultimo_feriado.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return [feriado for _, feriado in pagina], paginacao


async def criar_feriado(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.FeriadoCriar
) -> Feriado:
    await _obter_conjunto(sessao, tenant_id, dados.feriado_conjunto_id)

    movel = bool(dados.movel)
    _validar_definicao_feriado(
        movel, dados.data, dados.regra_movel.value if dados.regra_movel else None, dados.offset_dias
    )
    integral = dados.integral if dados.integral is not None else True
    _validar_parcial_feriado(integral, dados.carga_reduzida_minutos)

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "tipo" in campos:
        campos["tipo"] = dados.tipo.value if dados.tipo else campos["tipo"]
    if "regra_movel" in campos and campos["regra_movel"] is not None:
        campos["regra_movel"] = dados.regra_movel.value if dados.regra_movel else None

    feriado = Feriado(tenant_id=tenant_id, **campos)
    sessao.add(feriado)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    ano_referencia = feriado.ano or dt.date.today().year
    feriado.data_resolvida = resolver_data_feriado(feriado, ano_referencia)  # type: ignore[attr-defined]
    return feriado


async def excluir_feriado(sessao: AsyncSession, tenant_id: UUID, feriado_id: UUID) -> None:
    """`feriados` nao tem soft delete: a exclusao e fisica (ver schema.sql,
    tabela `feriados` -- sem `excluido_em`/`excluido_por`)."""
    resultado = await sessao.execute(
        select(Feriado).where(Feriado.tenant_id == tenant_id, Feriado.id == feriado_id)
    )
    feriado = resultado.scalar_one_or_none()
    if feriado is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Feriado nao encontrado.")
    await sessao.delete(feriado)
    await sessao.flush()
