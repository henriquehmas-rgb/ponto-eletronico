"""Esqueleto comum de listagem, obtencao e exclusao logica dos recursos desta
fase, para nao repetir tenant + soft delete + paginacao em cada um dos sete
recursos de cadastro (empresas, unidades, departamentos, centros de custo,
cargos, equipes, redes permitidas).

Cada service de recurso monta seus proprios filtros (`list[ColumnElement]`) e
o dicionario de campos ordenaveis; este modulo so aplica o que e identico em
todos: tenant, soft delete, ordenacao + desempate por id, e o "limite+1" que
`app.organizacao.paginacao.montar_paginacao` usa para descobrir `temMais` sem
`SELECT COUNT(*)`.
"""

from __future__ import annotations

import datetime
from typing import Any, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.organizacao.paginacao import PedidoDePagina, campo_e_direcao


@runtime_checkable
class _RegistroDeTenant(Protocol):
    id: Any
    tenant_id: Any


@runtime_checkable
class _RegistroComSoftDelete(_RegistroDeTenant, Protocol):
    # `Any`, e nao `datetime.datetime | None` / `UUID | None`: sem o plugin
    # mypy do SQLAlchemy (nao registrado neste projeto), `Mapped[X]` nao e
    # visto como estruturalmente igual a `X` puro, e todo model concreto
    # (Empresa, Departamento, Unidade, ...) falharia esta Protocol por
    # variancia mesmo estando correto em tempo de execucao.
    excluido_em: Any
    excluido_por: Any


ModeloT = TypeVar("ModeloT", bound=_RegistroDeTenant)
ModeloSoftDeleteT = TypeVar("ModeloSoftDeleteT", bound=_RegistroComSoftDelete)


async def listar(
    sessao: AsyncSession,
    modelo: type[ModeloT],
    *,
    tenant_id: UUID,
    filtros: list[ColumnElement[bool]],
    pedido: PedidoDePagina,
    campos_ordenaveis: dict[str, Any],
    tem_soft_delete: bool = True,
    incluir_excluidos: bool = False,
) -> list[ModeloT]:
    """Devolve ate `pedido.limite + 1` linhas (a extra so serve para
    `montar_paginacao` decidir `temMais`; o chamador corta em `[:limite]`)."""
    campo, direcao = campo_e_direcao(pedido.ordenar)
    coluna_ordenar = campos_ordenaveis.get(campo)
    if coluna_ordenar is None:
        raise ErroDeAplicacao(
            "PONTO-VAL-005", detalhe=f"Campo de ordenacao desconhecido: {campo!r}"
        )

    consulta: Select[Any] = select(modelo).where(modelo.tenant_id == tenant_id)
    if tem_soft_delete and not incluir_excluidos:
        consulta = consulta.where(modelo.excluido_em.is_(None))  # type: ignore[attr-defined]
    for filtro in filtros:
        consulta = consulta.where(filtro)

    ordenacao = coluna_ordenar.desc() if direcao == "desc" else coluna_ordenar.asc()
    consulta = consulta.order_by(ordenacao, modelo.id)
    consulta = consulta.offset(pedido.deslocamento).limit(pedido.limite + 1)

    linhas = (await sessao.execute(consulta)).scalars().all()
    return list(linhas)


async def obter_ou_404(
    sessao: AsyncSession,
    modelo: type[ModeloT],
    *,
    tenant_id: UUID,
    id_: UUID,
    tem_soft_delete: bool = True,
    incluir_excluidos: bool = False,
) -> ModeloT:
    consulta = select(modelo).where(modelo.tenant_id == tenant_id, modelo.id == id_)
    if tem_soft_delete and not incluir_excluidos:
        consulta = consulta.where(modelo.excluido_em.is_(None))  # type: ignore[attr-defined]
    instancia = (await sessao.execute(consulta)).scalar_one_or_none()
    if instancia is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Registro nao encontrado.")
    return instancia


def marcar_excluido(instancia: ModeloSoftDeleteT, *, usuario_id: UUID | None) -> None:
    instancia.excluido_em = datetime.datetime.now(datetime.UTC)
    instancia.excluido_por = usuario_id


async def existe(sessao: AsyncSession, consulta: Select[Any]) -> bool:
    """`True` quando `consulta.limit(1)` devolve alguma linha."""
    resultado = (await sessao.execute(consulta.limit(1))).first()
    return resultado is not None
