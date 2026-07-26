"""Regra de negocio da tag `organizacao`: departamentos e centros de custo
(hierarquicos, com deteccao de ciclo), cargos (com CBO) e equipes (com
participacao datada e sobreposicao recusada pela constraint `EXCLUDE`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from ponto_contracts.organizacao import Cargo, CentroCusto, Departamento, Empresa, Unidade
from ponto_contracts.pessoas import Colaborador, Equipe, EquipeMembro, Vinculo
from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.erros import ErroDeAplicacao
from app.organizacao import crud_base
from app.organizacao.erros_integridade import mapear_integridade
from app.organizacao.paginacao import PedidoDePagina

_PADRAO_CBO = re.compile(r"^[0-9]{6}$")


async def _existe_ou_404(
    sessao: AsyncSession, modelo: type, *, tenant_id: UUID, id_: UUID, tem_soft_delete: bool = True
) -> None:
    await crud_base.obter_ou_404(
        sessao,
        modelo,
        tenant_id=tenant_id,
        id_=id_,
        tem_soft_delete=tem_soft_delete,
    )


async def _cria_ciclo(
    sessao: AsyncSession,
    modelo: type,
    coluna_pai: InstrumentedAttribute[UUID | None],
    *,
    tenant_id: UUID,
    id_: UUID,
    novo_pai_id: UUID | None,
) -> bool:
    """`True` quando adotar `novo_pai_id` como pai de `id_` fecharia um ciclo
    -- isto e, `novo_pai_id` e o proprio `id_` ou um dos seus descendentes."""
    if novo_pai_id is None:
        return False
    if novo_pai_id == id_:
        return True
    atual: UUID | None = novo_pai_id
    visitados: set[UUID] = set()
    while atual is not None:
        if atual in visitados:
            break
        visitados.add(atual)
        linha = (
            await sessao.execute(
                select(coluna_pai).where(modelo.id == atual, modelo.tenant_id == tenant_id)  # type: ignore[attr-defined]
            )
        ).first()
        if linha is None:
            break
        atual = linha[0]
        if atual == id_:
            return True
    return False


# --------------------------------------------------------------------------
# Departamentos
# --------------------------------------------------------------------------

CAMPOS_ORDENAVEIS_DEPARTAMENTO: dict[str, object] = {
    "criado_em": Departamento.criado_em,
    "nome": Departamento.nome,
    "codigo": Departamento.codigo,
}


async def listar_departamentos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    departamento_pai_id: UUID | None = None,
    raiz: bool | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
) -> list[Departamento]:
    filtros = []
    if empresa_id is not None:
        filtros.append(Departamento.empresa_id == empresa_id)
    if departamento_pai_id is not None:
        filtros.append(Departamento.departamento_pai_id == departamento_pai_id)
    if raiz:
        filtros.append(Departamento.departamento_pai_id.is_(None))
    if ativo is not None:
        filtros.append(Departamento.ativo == ativo)
    if busca:
        filtros.append(Departamento.nome.ilike(f"%{busca}%"))
    return await crud_base.listar(
        sessao,
        Departamento,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_DEPARTAMENTO,
    )


async def obter_departamento(
    sessao: AsyncSession, *, tenant_id: UUID, departamento_id: UUID
) -> Departamento:
    return await crud_base.obter_ou_404(
        sessao, Departamento, tenant_id=tenant_id, id_=departamento_id
    )


async def criar_departamento(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    empresa_id: UUID,
    codigo: str,
    nome: str,
    departamento_pai_id: UUID | None = None,
    responsavel_colaborador_id: UUID | None = None,
    descricao: str | None = None,
    ativo: bool | None = None,
) -> Departamento:
    await _existe_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=empresa_id)
    if departamento_pai_id is not None:
        await _existe_ou_404(sessao, Departamento, tenant_id=tenant_id, id_=departamento_pai_id)
    if responsavel_colaborador_id is not None:
        await _existe_ou_404(
            sessao, Colaborador, tenant_id=tenant_id, id_=responsavel_colaborador_id
        )

    departamento = Departamento(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        departamento_pai_id=departamento_pai_id,
        responsavel_colaborador_id=responsavel_colaborador_id,
        codigo=codigo,
        nome=nome,
        descricao=descricao,
        criado_por=usuario_id,
    )
    if ativo is not None:
        departamento.ativo = ativo
    sessao.add(departamento)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarDepartamento") from exc
    return departamento


_CAMPOS_ATUALIZAVEIS_DEPARTAMENTO = ("codigo", "nome", "descricao", "ativo")


async def atualizar_departamento(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    departamento_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> Departamento:
    departamento = await obter_departamento(
        sessao, tenant_id=tenant_id, departamento_id=departamento_id
    )

    if "departamento_pai_id" in dados:
        novo_pai_id = dados["departamento_pai_id"]
        if novo_pai_id is not None:
            await _existe_ou_404(sessao, Departamento, tenant_id=tenant_id, id_=novo_pai_id)  # type: ignore[arg-type]
        if await _cria_ciclo(
            sessao,
            Departamento,
            Departamento.departamento_pai_id,
            tenant_id=tenant_id,
            id_=departamento_id,
            novo_pai_id=novo_pai_id,  # type: ignore[arg-type]
        ):
            raise ErroDeAplicacao(
                "PONTO-CONF-003",
                detalhe="A mudanca de hierarquia criaria um ciclo (departamento pai de si mesmo).",
            )
        departamento.departamento_pai_id = novo_pai_id  # type: ignore[assignment]

    if "responsavel_colaborador_id" in dados and dados["responsavel_colaborador_id"] is not None:
        await _existe_ou_404(
            sessao,
            Colaborador,
            tenant_id=tenant_id,
            id_=dados["responsavel_colaborador_id"],  # type: ignore[arg-type]
        )
        departamento.responsavel_colaborador_id = dados["responsavel_colaborador_id"]  # type: ignore[assignment]

    for campo in _CAMPOS_ATUALIZAVEIS_DEPARTAMENTO:
        if campo in dados:
            setattr(departamento, campo, dados[campo])

    departamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarDepartamento") from exc
    return departamento


async def _departamento_tem_dependente(
    sessao: AsyncSession, *, tenant_id: UUID, departamento_id: UUID
) -> bool:
    checagens: Sequence[tuple[type, ColumnElement[bool]]] = (
        (Departamento, Departamento.departamento_pai_id == departamento_id),
        (Vinculo, Vinculo.departamento_id == departamento_id),
        (Equipe, Equipe.departamento_id == departamento_id),
    )
    for tabela, condicao in checagens:
        consulta = select(tabela.id).where(tabela.tenant_id == tenant_id, condicao)  # type: ignore[attr-defined]
        if await crud_base.existe(sessao, consulta):
            return True
    return False


async def excluir_departamento(
    sessao: AsyncSession, *, tenant_id: UUID, departamento_id: UUID, usuario_id: UUID | None
) -> None:
    departamento = await obter_departamento(
        sessao, tenant_id=tenant_id, departamento_id=departamento_id
    )
    tem_dependente = await _departamento_tem_dependente(
        sessao, tenant_id=tenant_id, departamento_id=departamento_id
    )
    if tem_dependente:
        raise ErroDeAplicacao(
            "PONTO-CONF-004",
            detalhe="Departamento tem subdepartamento, vinculo ou equipe ativos.",
        )
    crud_base.marcar_excluido(departamento, usuario_id=usuario_id)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="excluirDepartamento", ao_excluir=True) from exc


# --------------------------------------------------------------------------
# Centros de custo
# --------------------------------------------------------------------------

CAMPOS_ORDENAVEIS_CENTRO_CUSTO: dict[str, object] = {
    "criado_em": CentroCusto.criado_em,
    "nome": CentroCusto.nome,
    "codigo": CentroCusto.codigo,
}


async def listar_centros_custo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    centro_custo_pai_id: UUID | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
) -> list[CentroCusto]:
    filtros = []
    if empresa_id is not None:
        filtros.append(CentroCusto.empresa_id == empresa_id)
    if centro_custo_pai_id is not None:
        filtros.append(CentroCusto.centro_custo_pai_id == centro_custo_pai_id)
    if ativo is not None:
        filtros.append(CentroCusto.ativo == ativo)
    if busca:
        filtros.append(CentroCusto.nome.ilike(f"%{busca}%"))
    return await crud_base.listar(
        sessao,
        CentroCusto,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_CENTRO_CUSTO,
    )


async def obter_centro_custo(
    sessao: AsyncSession, *, tenant_id: UUID, centro_custo_id: UUID
) -> CentroCusto:
    return await crud_base.obter_ou_404(
        sessao, CentroCusto, tenant_id=tenant_id, id_=centro_custo_id
    )


async def criar_centro_custo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    empresa_id: UUID,
    codigo: str,
    nome: str,
    centro_custo_pai_id: UUID | None = None,
    descricao: str | None = None,
    codigo_externo: str | None = None,
    ativo: bool | None = None,
) -> CentroCusto:
    await _existe_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=empresa_id)
    if centro_custo_pai_id is not None:
        await _existe_ou_404(sessao, CentroCusto, tenant_id=tenant_id, id_=centro_custo_pai_id)

    centro = CentroCusto(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        centro_custo_pai_id=centro_custo_pai_id,
        codigo=codigo,
        nome=nome,
        descricao=descricao,
        codigo_externo=codigo_externo,
        criado_por=usuario_id,
    )
    if ativo is not None:
        centro.ativo = ativo
    sessao.add(centro)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarCentroCusto") from exc
    return centro


_CAMPOS_ATUALIZAVEIS_CENTRO_CUSTO = ("codigo", "nome", "descricao", "codigo_externo", "ativo")


async def atualizar_centro_custo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    centro_custo_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> CentroCusto:
    centro = await obter_centro_custo(sessao, tenant_id=tenant_id, centro_custo_id=centro_custo_id)

    if "centro_custo_pai_id" in dados:
        novo_pai_id = dados["centro_custo_pai_id"]
        if novo_pai_id is not None:
            await _existe_ou_404(sessao, CentroCusto, tenant_id=tenant_id, id_=novo_pai_id)  # type: ignore[arg-type]
        if await _cria_ciclo(
            sessao,
            CentroCusto,
            CentroCusto.centro_custo_pai_id,
            tenant_id=tenant_id,
            id_=centro_custo_id,
            novo_pai_id=novo_pai_id,  # type: ignore[arg-type]
        ):
            raise ErroDeAplicacao(
                "PONTO-CONF-003",
                detalhe=(
                    "A mudanca de hierarquia criaria um ciclo " "(centro de custo pai de si mesmo)."
                ),
            )
        centro.centro_custo_pai_id = novo_pai_id  # type: ignore[assignment]

    for campo in _CAMPOS_ATUALIZAVEIS_CENTRO_CUSTO:
        if campo in dados:
            setattr(centro, campo, dados[campo])

    centro.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarCentroCusto") from exc
    return centro


# --------------------------------------------------------------------------
# Cargos
# --------------------------------------------------------------------------

CAMPOS_ORDENAVEIS_CARGO: dict[str, object] = {
    "criado_em": Cargo.criado_em,
    "nome": Cargo.nome,
    "codigo": Cargo.codigo,
}


def _validar_cbo(cbo: str | None) -> None:
    if cbo is not None and not _PADRAO_CBO.match(cbo):
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="CBO deve ter exatamente 6 digitos.")


async def listar_cargos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    cbo: str | None = None,
    nivel: str | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
) -> list[Cargo]:
    filtros = []
    if empresa_id is not None:
        filtros.append(Cargo.empresa_id == empresa_id)
    if cbo is not None:
        filtros.append(Cargo.cbo == cbo)
    if nivel is not None:
        filtros.append(Cargo.nivel == nivel)
    if ativo is not None:
        filtros.append(Cargo.ativo == ativo)
    if busca:
        filtros.append(Cargo.nome.ilike(f"%{busca}%"))
    return await crud_base.listar(
        sessao,
        Cargo,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_CARGO,
    )


async def obter_cargo(sessao: AsyncSession, *, tenant_id: UUID, cargo_id: UUID) -> Cargo:
    return await crud_base.obter_ou_404(sessao, Cargo, tenant_id=tenant_id, id_=cargo_id)


async def criar_cargo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    empresa_id: UUID,
    codigo: str,
    nome: str,
    cbo: str | None = None,
    descricao: str | None = None,
    nivel: str | None = None,
    salario_base: float | None = None,
    cargo_confianca: bool | None = None,
    ativo: bool | None = None,
) -> Cargo:
    await _existe_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=empresa_id)
    _validar_cbo(cbo)

    cargo = Cargo(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        codigo=codigo,
        nome=nome,
        cbo=cbo,
        descricao=descricao,
        nivel=nivel,
        salario_base=salario_base,
        criado_por=usuario_id,
    )
    if cargo_confianca is not None:
        cargo.cargo_confianca = cargo_confianca
    if ativo is not None:
        cargo.ativo = ativo
    sessao.add(cargo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarCargo") from exc
    return cargo


_CAMPOS_ATUALIZAVEIS_CARGO = (
    "codigo",
    "nome",
    "descricao",
    "nivel",
    "salario_base",
    "cargo_confianca",
    "ativo",
)


async def atualizar_cargo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cargo_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> Cargo:
    cargo = await obter_cargo(sessao, tenant_id=tenant_id, cargo_id=cargo_id)

    if "cbo" in dados:
        _validar_cbo(dados["cbo"])  # type: ignore[arg-type]
        cargo.cbo = dados["cbo"]  # type: ignore[assignment]

    for campo in _CAMPOS_ATUALIZAVEIS_CARGO:
        if campo in dados:
            setattr(cargo, campo, dados[campo])

    cargo.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarCargo") from exc
    return cargo


# --------------------------------------------------------------------------
# Equipes e membros
# --------------------------------------------------------------------------

CAMPOS_ORDENAVEIS_EQUIPE: dict[str, object] = {
    "criado_em": Equipe.criado_em,
    "nome": Equipe.nome,
    "codigo": Equipe.codigo,
}


async def listar_equipes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    gestor_colaborador_id: UUID | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
) -> list[Equipe]:
    filtros = []
    if empresa_id is not None:
        filtros.append(Equipe.empresa_id == empresa_id)
    if unidade_id is not None:
        filtros.append(Equipe.unidade_id == unidade_id)
    if gestor_colaborador_id is not None:
        filtros.append(Equipe.gestor_colaborador_id == gestor_colaborador_id)
    if ativo is not None:
        filtros.append(Equipe.ativo == ativo)
    if busca:
        filtros.append(Equipe.nome.ilike(f"%{busca}%"))
    return await crud_base.listar(
        sessao,
        Equipe,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_EQUIPE,
    )


async def obter_equipe(sessao: AsyncSession, *, tenant_id: UUID, equipe_id: UUID) -> Equipe:
    return await crud_base.obter_ou_404(sessao, Equipe, tenant_id=tenant_id, id_=equipe_id)


async def criar_equipe(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    empresa_id: UUID,
    codigo: str,
    nome: str,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    gestor_colaborador_id: UUID | None = None,
    descricao: str | None = None,
    cor: str | None = None,
    ativo: bool | None = None,
) -> Equipe:
    await _existe_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=empresa_id)
    if unidade_id is not None:
        await _existe_ou_404(sessao, Unidade, tenant_id=tenant_id, id_=unidade_id)
    if departamento_id is not None:
        await _existe_ou_404(sessao, Departamento, tenant_id=tenant_id, id_=departamento_id)
    if gestor_colaborador_id is not None:
        await _existe_ou_404(sessao, Colaborador, tenant_id=tenant_id, id_=gestor_colaborador_id)

    equipe = Equipe(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        gestor_colaborador_id=gestor_colaborador_id,
        codigo=codigo,
        nome=nome,
        descricao=descricao,
        cor=cor,
        criado_por=usuario_id,
    )
    if ativo is not None:
        equipe.ativo = ativo
    sessao.add(equipe)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarEquipe") from exc
    return equipe


_CAMPOS_ATUALIZAVEIS_EQUIPE = ("codigo", "nome", "descricao", "cor", "ativo")


async def atualizar_equipe(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    equipe_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> Equipe:
    equipe = await obter_equipe(sessao, tenant_id=tenant_id, equipe_id=equipe_id)

    if "unidade_id" in dados and dados["unidade_id"] is not None:
        await _existe_ou_404(sessao, Unidade, tenant_id=tenant_id, id_=dados["unidade_id"])  # type: ignore[arg-type]
        equipe.unidade_id = dados["unidade_id"]  # type: ignore[assignment]
    if "departamento_id" in dados and dados["departamento_id"] is not None:
        await _existe_ou_404(
            sessao,
            Departamento,
            tenant_id=tenant_id,
            id_=dados["departamento_id"],  # type: ignore[arg-type]
        )
        equipe.departamento_id = dados["departamento_id"]  # type: ignore[assignment]
    if "gestor_colaborador_id" in dados and dados["gestor_colaborador_id"] is not None:
        await _existe_ou_404(
            sessao,
            Colaborador,
            tenant_id=tenant_id,
            id_=dados["gestor_colaborador_id"],  # type: ignore[arg-type]
        )
        equipe.gestor_colaborador_id = dados["gestor_colaborador_id"]  # type: ignore[assignment]

    for campo in _CAMPOS_ATUALIZAVEIS_EQUIPE:
        if campo in dados:
            setattr(equipe, campo, dados[campo])

    equipe.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarEquipe") from exc
    return equipe


async def adicionar_membro_equipe(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    equipe_id: UUID,
    usuario_id: UUID | None,
    colaborador_id: UUID,
    papel: str | None = None,
    vigencia_inicio: date | None = None,
    vigencia_fim: date | None = None,
) -> EquipeMembro:
    await obter_equipe(sessao, tenant_id=tenant_id, equipe_id=equipe_id)
    await _existe_ou_404(sessao, Colaborador, tenant_id=tenant_id, id_=colaborador_id)

    membro = EquipeMembro(
        tenant_id=tenant_id,
        equipe_id=equipe_id,
        colaborador_id=colaborador_id,
        vigencia_fim=vigencia_fim,
        criado_por=usuario_id,
    )
    if papel is not None:
        membro.papel = papel
    if vigencia_inicio is not None:
        membro.vigencia_inicio = vigencia_inicio
    sessao.add(membro)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="adicionarMembroEquipe") from exc
    return membro
