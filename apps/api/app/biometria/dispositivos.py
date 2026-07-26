"""Regra de negocio de `dispositivos` (T9 do PCF da F2).

Dispositivo != terminal (`terminais` e F6). Aqui: cadastro do aparelho e o
vinculo com o colaborador, com a regra de um unico vinculo ATIVO por
colaborador (`uq_dispositivo_vinculos_ativo` -> `PONTO-DISP-006`). Avaliar os
sinais antifraude (`attestation_status`, `root_detectado`, ...) e da F14; aqui
so cadastramos e expomos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Colaborador, Dispositivo, DispositivoVinculo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria.comum import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    normalizar_limite,
    traduzir_integridade,
)
from app.core.erros import ErroDeAplicacao

__all__ = [
    "CAMPOS_ORDENACAO_DISPOSITIVO",
    "DadosDispositivoAtualizar",
    "DadosDispositivoCriar",
    "colaborador_vinculado_atual",
    "criar_dispositivo",
    "excluir_dispositivo",
    "listar_dispositivos",
    "obter_dispositivo",
    "atualizar_dispositivo",
    "vincular_dispositivo",
]

CAMPOS_ORDENACAO_DISPOSITIVO = frozenset({"ultimoAcessoEm", "criadoEm"})


@dataclass(frozen=True, slots=True)
class DadosDispositivoCriar:
    empresa_id: UUID | None
    unidade_id: UUID | None
    tipo: str
    plataforma: str | None
    identificador: str
    nome: str | None
    fabricante: str | None
    modelo: str | None
    versao_so: str | None
    versao_app: str | None
    status: str | None
    root_detectado: bool | None
    emulador_detectado: bool | None
    modo_desenvolvedor: bool | None
    depuracao_usb: bool | None
    observacoes: str | None


@dataclass(frozen=True, slots=True)
class DadosDispositivoAtualizar:
    empresa_id: UUID | None = None
    unidade_id: UUID | None = None
    tipo: str | None = None
    plataforma: str | None = None
    identificador: str | None = None
    nome: str | None = None
    fabricante: str | None = None
    modelo: str | None = None
    versao_so: str | None = None
    versao_app: str | None = None
    status: str | None = None
    root_detectado: bool | None = None
    emulador_detectado: bool | None = None
    modo_desenvolvedor: bool | None = None
    depuracao_usb: bool | None = None
    observacoes: str | None = None


async def criar_dispositivo(
    sessao: AsyncSession, *, tenant_id: UUID, dados: DadosDispositivoCriar, usuario_id: UUID | None
) -> Dispositivo:
    dispositivo = Dispositivo(
        tenant_id=tenant_id,
        empresa_id=dados.empresa_id,
        unidade_id=dados.unidade_id,
        tipo=dados.tipo,
        plataforma=dados.plataforma,
        identificador=dados.identificador,
        nome=dados.nome,
        fabricante=dados.fabricante,
        modelo=dados.modelo,
        versao_so=dados.versao_so,
        versao_app=dados.versao_app,
        status=dados.status or "pendente",
        root_detectado=bool(dados.root_detectado),
        emulador_detectado=bool(dados.emulador_detectado),
        modo_desenvolvedor=bool(dados.modo_desenvolvedor),
        depuracao_usb=bool(dados.depuracao_usb),
        observacoes=dados.observacoes,
        criado_por=usuario_id,
    )
    sessao.add(dispositivo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return dispositivo


async def _carregar(sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID) -> Dispositivo:
    dispositivo = (
        await sessao.execute(
            sa.select(Dispositivo).where(
                Dispositivo.id == dispositivo_id, Dispositivo.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if dispositivo is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Dispositivo nao encontrado.")
    return dispositivo


async def obter_dispositivo(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID
) -> Dispositivo:
    return await _carregar(sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id)


async def colaborador_vinculado_atual(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID
) -> UUID | None:
    """`colaboradorVinculadoId` da resposta: nao e coluna de `dispositivos`
    (schema.sql secao 6), e derivado do vinculo ATIVO mais recente."""
    return (
        (
            await sessao.execute(
                sa.select(DispositivoVinculo.colaborador_id).where(
                    DispositivoVinculo.tenant_id == tenant_id,
                    DispositivoVinculo.dispositivo_id == dispositivo_id,
                    DispositivoVinculo.status == "ativo",
                )
            )
        )
        .scalars()
        .first()
    )


async def listar_dispositivos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID | None,
    unidade_id: UUID | None,
    colaborador_id: UUID | None,
    tipo: str | None,
    plataforma: str | None,
    status: str | None,
    attestation_status: str | None,
    com_risco: bool | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> tuple[list[Dispositivo], bool, str | None]:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_DISPOSITIVO, padrao="criadoEm"
    )
    mapa = {
        "ultimoAcessoEm": CampoOrdenacao(Dispositivo.ultimo_acesso_em, lambda v: v),
        "criadoEm": CampoOrdenacao(Dispositivo.criado_em, lambda v: v),
    }
    consulta = sa.select(Dispositivo).where(
        Dispositivo.tenant_id == tenant_id, Dispositivo.excluido_em.is_(None)
    )
    if empresa_id is not None:
        consulta = consulta.where(Dispositivo.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(Dispositivo.unidade_id == unidade_id)
    if tipo is not None:
        consulta = consulta.where(Dispositivo.tipo == tipo)
    if plataforma is not None:
        consulta = consulta.where(Dispositivo.plataforma == plataforma)
    if status is not None:
        consulta = consulta.where(Dispositivo.status == status)
    if attestation_status is not None:
        consulta = consulta.where(Dispositivo.attestation_status == attestation_status)
    if com_risco:
        consulta = consulta.where(
            sa.or_(
                Dispositivo.root_detectado.is_(True),
                Dispositivo.emulador_detectado.is_(True),
                Dispositivo.modo_desenvolvedor.is_(True),
                Dispositivo.depuracao_usb.is_(True),
            )
        )
    if colaborador_id is not None:
        consulta = consulta.join(
            DispositivoVinculo,
            sa.and_(
                DispositivoVinculo.dispositivo_id == Dispositivo.id,
                DispositivoVinculo.status == "ativo",
            ),
        ).where(DispositivoVinculo.colaborador_id == colaborador_id)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=mapa[ordenacao.campo],
        coluna_id=Dispositivo.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    proximo: str | None = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        campo_valor = "ultimo_acesso_em" if ordenacao.campo == "ultimoAcessoEm" else "criado_em"
        proximo = codificar_cursor(ordenacao, getattr(ultimo, campo_valor), ultimo.id)
    return list(linhas), tem_mais, proximo


async def atualizar_dispositivo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dispositivo_id: UUID,
    dados: DadosDispositivoAtualizar,
    usuario_id: UUID | None,
) -> Dispositivo:
    dispositivo = await _carregar(sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id)
    for campo in (
        "empresa_id",
        "unidade_id",
        "tipo",
        "plataforma",
        "identificador",
        "nome",
        "fabricante",
        "modelo",
        "versao_so",
        "versao_app",
        "status",
        "root_detectado",
        "emulador_detectado",
        "modo_desenvolvedor",
        "depuracao_usb",
        "observacoes",
    ):
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(dispositivo, campo, valor)
    dispositivo.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return dispositivo


async def excluir_dispositivo(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID, usuario_id: UUID | None
) -> None:
    dispositivo = await _carregar(sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id)
    agora = dt.datetime.now(tz=dt.UTC)
    dispositivo.excluido_em = agora
    dispositivo.excluido_por = usuario_id
    # Revoga vinculos ativos, como a descricao da operacao exige.
    vinculos_ativos = (
        (
            await sessao.execute(
                sa.select(DispositivoVinculo).where(
                    DispositivoVinculo.tenant_id == tenant_id,
                    DispositivoVinculo.dispositivo_id == dispositivo_id,
                    DispositivoVinculo.status == "ativo",
                )
            )
        )
        .scalars()
        .all()
    )
    for vinculo in vinculos_ativos:
        vinculo.status = "revogado"
        vinculo.revogado_em = agora
        vinculo.motivo_revogacao = "Dispositivo excluido"
        vinculo.atualizado_por = usuario_id
    # `flush()` explicito: a sessao roda com `autoflush=False`
    # (`app/db/sessao.py`). Sem isto, um `SELECT` de COLUNA (nao de entidade
    # completa) feito logo em seguida na MESMA transacao -- como
    # `colaborador_vinculado_atual` -- ignora o identity map e ve a linha
    # ainda com `status = 'ativo'` no banco.
    await sessao.flush()


async def vincular_dispositivo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dispositivo_id: UUID,
    colaborador_id: UUID,
    aprovar_imediatamente: bool,
    revogar_anterior: bool,
    motivo: str | None,
    usuario_id: UUID | None,
) -> Dispositivo:
    dispositivo = await _carregar(sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id)
    colaborador = (
        await sessao.execute(
            sa.select(Colaborador).where(
                Colaborador.id == colaborador_id,
                Colaborador.tenant_id == tenant_id,
                Colaborador.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if colaborador is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Colaborador nao encontrado.")

    if revogar_anterior:
        anteriores = (
            (
                await sessao.execute(
                    sa.select(DispositivoVinculo).where(
                        DispositivoVinculo.tenant_id == tenant_id,
                        DispositivoVinculo.colaborador_id == colaborador_id,
                        DispositivoVinculo.status == "ativo",
                    )
                )
            )
            .scalars()
            .all()
        )
        agora = dt.datetime.now(tz=dt.UTC)
        for anterior in anteriores:
            anterior.status = "revogado"
            anterior.revogado_em = agora
            anterior.motivo_revogacao = motivo or "Troca de aparelho"
            anterior.atualizado_por = usuario_id
        await sessao.flush()

    vinculo = DispositivoVinculo(
        tenant_id=tenant_id,
        dispositivo_id=dispositivo_id,
        colaborador_id=colaborador_id,
        status="ativo" if aprovar_imediatamente else "pendente",
        aprovado_por=usuario_id if aprovar_imediatamente else None,
        aprovado_em=dt.datetime.now(tz=dt.UTC) if aprovar_imediatamente else None,
        criado_por=usuario_id,
    )
    sessao.add(vinculo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        # uq_dispositivo_vinculos_ativo: segundo vinculo ativo do colaborador.
        raise traduzir_integridade(exc) from exc

    return dispositivo
