"""Servicos de dominio do recurso `colaboradores`: CRUD, busca por nome e a
hierarquia de gestores (`colaborador_gestores`).

`colaboradores` e a PESSOA -- dados cadastrais e pessoais. Criar um
colaborador NAO cria vinculo (ver `app.pessoas.contratos`): a relacao de
trabalho e um passo separado, deliberado no contrato (`POST /v1/vinculos`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Colaborador, ColaboradorGestor, EquipeMembro, Vinculo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.documentos import cpf_valido, pis_valido, somente_digitos
from app.core.erros import ErroDeAplicacao
from app.pessoas.erros_bd import traduzir_integridade
from app.pessoas.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_CPF_INVALIDO = "PONTO-VAL-002"
CODIGO_PIS_INVALIDO = "PONTO-VAL-004"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CICLO_HIERARQUIA = "PONTO-CONF-003"

#: Campos aceitos em `ordenar` para `listarColaboradores`, conforme o
#: `openapi.yaml`: nomeCompleto, matricula, dataAdmissao, criadoEm.
_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "nomeCompleto": CampoOrdenacao(Colaborador.nome_completo, str),
    "matricula": CampoOrdenacao(Colaborador.matricula, str),
    "dataAdmissao": CampoOrdenacao(Colaborador.data_admissao, dt.date.fromisoformat),
    "criadoEm": CampoOrdenacao(Colaborador.criado_em, dt.datetime.fromisoformat),
}
_ATRIBUTO_POR_CAMPO: dict[str, str] = {
    "nomeCompleto": "nome_completo",
    "matricula": "matricula",
    "dataAdmissao": "data_admissao",
    "criadoEm": "criado_em",
}


def _validar_documentos(cpf: str, pis_nit: str | None) -> tuple[str, str | None]:
    """Normaliza para so-digitos e valida o digito verificador.

    O schema Pydantic gerado ja restringe `cpf`/`pisNit` a `^[0-9]{11}$`
    (sem mascara), mas a normalizacao roda de novo aqui -- e o contrato
    interno de `app/comum/documentos.py` ("guarde sempre so digitos") vale
    tambem se o schema um dia relaxar o `pattern`.
    """
    cpf_normalizado = somente_digitos(cpf)
    if not cpf_valido(cpf_normalizado):
        raise ErroDeAplicacao(CODIGO_CPF_INVALIDO, detalhe="CPF invalido.")
    pis_normalizado = somente_digitos(pis_nit) if pis_nit else None
    if pis_normalizado and not pis_valido(pis_normalizado):
        raise ErroDeAplicacao(CODIGO_PIS_INVALIDO, detalhe="PIS, PASEP ou NIT invalido.")
    return cpf_normalizado, pis_normalizado


async def obter_colaborador(
    sessao: AsyncSession, colaborador_id: UUID, *, incluir_excluidos: bool = False
) -> Colaborador:
    """Devolve o colaborador ou levanta `PONTO-REC-001`."""
    consulta = select(Colaborador).where(Colaborador.id == colaborador_id)
    if not incluir_excluidos:
        consulta = consulta.where(Colaborador.excluido_em.is_(None))
    resultado = await sessao.execute(consulta)
    colaborador = resultado.scalar_one_or_none()
    if colaborador is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Colaborador nao encontrado.")
    return colaborador


async def criar_colaborador(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.ColaboradorCriar
) -> Colaborador:
    """Cadastra a pessoa. Nao cria vinculo -- so o cadastro."""
    cpf, pis_nit = _validar_documentos(dados.cpf, dados.pis_nit)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    campos["cpf"] = cpf
    campos["pis_nit"] = pis_nit
    colaborador = Colaborador(tenant_id=tenant_id, **campos)
    sessao.add(colaborador)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return colaborador


async def atualizar_colaborador(
    sessao: AsyncSession,
    colaborador_id: UUID,
    dados: esquemas.ColaboradorAtualizar,
) -> Colaborador:
    """Atualizacao parcial: so os campos enviados sao alterados."""
    colaborador = await obter_colaborador(sessao, colaborador_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "cpf" in campos or "pis_nit" in campos:
        cpf_bruto = campos.get("cpf", colaborador.cpf)
        pis_bruto = campos.get("pis_nit", colaborador.pis_nit)
        cpf, pis_nit = _validar_documentos(cpf_bruto, pis_bruto)
        if "cpf" in campos:
            campos["cpf"] = cpf
        if "pis_nit" in campos:
            campos["pis_nit"] = pis_nit
    for campo, valor in campos.items():
        setattr(colaborador, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return colaborador


async def excluir_colaborador(sessao: AsyncSession, colaborador_id: UUID) -> None:
    """Exclusao logica (`excluido_em`/`excluido_por`). Nunca fisica."""
    colaborador = await obter_colaborador(sessao, colaborador_id)
    colaborador.excluido_em = dt.datetime.now(tz=dt.UTC)
    await sessao.flush()


def _filtro_subordinados(consulta: sa.Select[Any], gestor_ids: set[UUID]) -> sa.Select[Any]:
    if not gestor_ids:
        # Nenhum subordinado: devolve consulta que nao encontra nenhuma linha,
        # em vez de devolver a lista inteira de colaboradores por engano.
        return consulta.where(sa.false())
    return consulta.where(Colaborador.id.in_(gestor_ids))


async def listar_colaboradores(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
    gestor_colaborador_id: UUID | None = None,
    status: str | None = None,
    cpf: str | None = None,
    matricula: str | None = None,
    admitido_de: dt.date | None = None,
    admitido_ate: dt.date | None = None,
    incluir_inativos: bool = False,
    busca: str | None = None,
    incluir_excluidos: bool = False,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Colaborador], esquemas.Paginacao]:
    """Lista colaboradores com os filtros de `listarColaboradores`."""
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Colaborador).where(Colaborador.tenant_id == tenant_id)
    if not incluir_excluidos:
        consulta = consulta.where(Colaborador.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(Colaborador.empresa_id == empresa_id)
    if status is not None:
        consulta = consulta.where(Colaborador.status == status)
    elif not incluir_inativos:
        consulta = consulta.where(Colaborador.status != "desligado")
    if cpf is not None:
        consulta = consulta.where(Colaborador.cpf == somente_digitos(cpf))
    if matricula is not None:
        consulta = consulta.where(Colaborador.matricula == matricula)
    if admitido_de is not None:
        consulta = consulta.where(Colaborador.data_admissao >= admitido_de)
    if admitido_ate is not None:
        consulta = consulta.where(Colaborador.data_admissao <= admitido_ate)
    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            sa.or_(
                Colaborador.nome_completo.ilike(padrao),
                Colaborador.nome_social.ilike(padrao),
            )
        )
    if unidade_id is not None:
        consulta = consulta.where(
            sa.exists().where(
                Vinculo.colaborador_id == Colaborador.id,
                Vinculo.tenant_id == tenant_id,
                Vinculo.unidade_id == unidade_id,
                Vinculo.excluido_em.is_(None),
            )
        )
    if departamento_id is not None:
        consulta = consulta.where(
            sa.exists().where(
                Vinculo.colaborador_id == Colaborador.id,
                Vinculo.tenant_id == tenant_id,
                Vinculo.departamento_id == departamento_id,
                Vinculo.excluido_em.is_(None),
            )
        )
    if equipe_id is not None:
        consulta = consulta.where(
            sa.exists().where(
                EquipeMembro.colaborador_id == Colaborador.id,
                EquipeMembro.tenant_id == tenant_id,
                EquipeMembro.equipe_id == equipe_id,
            )
        )
    if gestor_colaborador_id is not None:
        subordinados = await subordinados_de(
            sessao, tenant_id, gestor_colaborador_id, dt.date.today()
        )
        consulta = _filtro_subordinados(consulta, subordinados)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Colaborador.id,
        cursor=cursor,
        limite=limite_efetivo,
    )

    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor_ultimo = getattr(ultimo, _ATRIBUTO_POR_CAMPO[ordenacao.campo])
        proximo_cursor = codificar_cursor(ordenacao, valor_ultimo, ultimo.id)

    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


# ---------------------------------------------------------------------------
# Hierarquia de gestores
# ---------------------------------------------------------------------------
async def subordinados_de(
    sessao: AsyncSession, tenant_id: UUID, gestor_id: UUID, data: dt.date
) -> set[UUID]:
    """Arvore completa de subordinados (diretos e transitivos) de `gestor_id`
    na data informada, seguindo apenas vinculos de gestao `imediato`
    vigentes -- e essa cadeia que define "a propria arvore" que o perfil
    gestor enxerga (F1) e a cadeia de aprovacao (F10).
    """
    consulta = sa.text(
        """
        WITH RECURSIVE arvore AS (
            SELECT colaborador_id
            FROM colaborador_gestores
            WHERE tenant_id = :tenant_id
              AND gestor_colaborador_id = :gestor_id
              AND tipo = 'imediato'
              AND vigencia_inicio <= :data
              AND (vigencia_fim IS NULL OR vigencia_fim >= :data)
            UNION
            SELECT cg.colaborador_id
            FROM colaborador_gestores cg
            JOIN arvore a ON cg.gestor_colaborador_id = a.colaborador_id
            WHERE cg.tenant_id = :tenant_id
              AND cg.tipo = 'imediato'
              AND cg.vigencia_inicio <= :data
              AND (cg.vigencia_fim IS NULL OR cg.vigencia_fim >= :data)
        )
        SELECT colaborador_id FROM arvore
        """
    )
    resultado = await sessao.execute(
        consulta, {"tenant_id": str(tenant_id), "gestor_id": str(gestor_id), "data": data}
    )
    return {linha[0] for linha in resultado.all()}


async def listar_gestores_colaborador(
    sessao: AsyncSession,
    colaborador_id: UUID,
    *,
    vigente_em: dt.date | None = None,
    tipo: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[ColaboradorGestor], esquemas.Paginacao]:
    """Lista os vinculos de gestao (imediato, substituto, matricial, rh) do
    colaborador."""
    campos_ordenacao = {
        "vigenciaInicio": CampoOrdenacao(ColaboradorGestor.vigencia_inicio, dt.date.fromisoformat),
        "criadoEm": CampoOrdenacao(ColaboradorGestor.criado_em, dt.datetime.fromisoformat),
    }
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(campos_ordenacao), padrao="vigenciaInicio"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(ColaboradorGestor).where(ColaboradorGestor.colaborador_id == colaborador_id)
    if tipo is not None:
        consulta = consulta.where(ColaboradorGestor.tipo == tipo)
    if vigente_em is not None:
        consulta = consulta.where(
            ColaboradorGestor.vigencia_inicio <= vigente_em,
            sa.or_(
                ColaboradorGestor.vigencia_fim.is_(None),
                ColaboradorGestor.vigencia_fim >= vigente_em,
            ),
        )

    campo = campos_ordenacao[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=ColaboradorGestor.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        atributo = "vigencia_inicio" if ordenacao.campo == "vigenciaInicio" else "criado_em"
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def definir_gestor_colaborador(
    sessao: AsyncSession,
    tenant_id: UUID,
    colaborador_id: UUID,
    dados: esquemas.ColaboradorGestorCriar,
) -> ColaboradorGestor:
    """Cria um vinculo de gestao. `EXCLUDE` do banco recusa dois gestores
    imediatos vigentes na mesma data (`PONTO-VAL-010`); aqui, alem disso,
    detectamos e recusamos ciclo (`PONTO-CONF-003`): A gerencia B que
    gerencia A.
    """
    gestor_id = dados.gestor_colaborador_id
    if colaborador_id == gestor_id:
        raise ErroDeAplicacao(
            CODIGO_CICLO_HIERARQUIA, detalhe="Um colaborador nao pode ser gestor de si mesmo."
        )
    if dados.tipo == esquemas.Tipo6.imediato:
        subordinados = await subordinados_de(
            sessao, tenant_id, colaborador_id, dados.vigencia_inicio
        )
        if gestor_id in subordinados:
            raise ErroDeAplicacao(
                CODIGO_CICLO_HIERARQUIA,
                detalhe="Ciclo detectado na hierarquia: o gestor indicado ja e subordinado "
                "deste colaborador.",
            )

    registro = ColaboradorGestor(
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        gestor_colaborador_id=gestor_id,
        tipo=dados.tipo.value,
        vigencia_inicio=dados.vigencia_inicio,
        vigencia_fim=dados.vigencia_fim,
    )
    sessao.add(registro)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return registro
