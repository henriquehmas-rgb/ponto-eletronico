"""Testes do módulo interno `app.relatorios.preferencias` (T1) e da
constraint `uq_preferencias_colunas` (critério de aceite 4, PCF §7).
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import PreferenciaColunas
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios import preferencias
from tests.f11.conftest import ContextoF11


async def test_salvar_preferencia_cria_e_reexecutar_atualiza_mesma_linha(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    relatorio_id = contexto_f11.relatorio_ids["espelho-jornada"]
    usuario_id = contexto_f11.usuario_rh_id

    primeira = await preferencias.salvar_preferencia(
        sessao_f11,
        contexto_f11.tenant_id,
        usuario_id,
        relatorio_definicao_id=relatorio_id,
        tela=None,
        nome="padrao",
        colunas=["nomeCompleto", "matricula"],
        ordenacao=None,
        filtros=None,
        larguras=None,
        padrao=True,
    )

    segunda = await preferencias.salvar_preferencia(
        sessao_f11,
        contexto_f11.tenant_id,
        usuario_id,
        relatorio_definicao_id=relatorio_id,
        tela=None,
        nome="padrao",
        colunas=["nomeCompleto", "matricula", "extrasMinutos"],
        ordenacao={"campo": "nomeCompleto", "direcao": "asc"},
        filtros=None,
        larguras={"nomeCompleto": 220},
        padrao=True,
    )

    assert primeira.id == segunda.id
    assert segunda.colunas == ["nomeCompleto", "matricula", "extrasMinutos"]

    contagem = (
        await sessao_f11.execute(
            sa.select(sa.func.count())
            .select_from(PreferenciaColunas)
            .where(
                PreferenciaColunas.tenant_id == contexto_f11.tenant_id,
                PreferenciaColunas.usuario_id == usuario_id,
            )
        )
    ).scalar_one()
    assert contagem == 1  # upsert nunca duplica


async def test_salvar_preferencia_exige_relatorio_ou_tela_nao_os_dois(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    relatorio_id = contexto_f11.relatorio_ids["espelho-jornada"]

    for kwargs in (
        {"relatorio_definicao_id": relatorio_id, "tela": "grade_apuracao"},
        {"relatorio_definicao_id": None, "tela": None},
    ):
        try:
            await preferencias.salvar_preferencia(
                sessao_f11,
                contexto_f11.tenant_id,
                contexto_f11.usuario_rh_id,
                nome="padrao",
                colunas=["a"],
                ordenacao=None,
                filtros=None,
                larguras=None,
                padrao=False,
                **kwargs,
            )
        except ErroDeAplicacao as exc:
            assert exc.codigo == "PONTO-VAL-001"
        else:
            raise AssertionError("deveria ter recusado")


async def test_obter_e_listar_preferencias(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    relatorio_id = contexto_f11.relatorio_ids["espelho-jornada"]
    usuario_id = contexto_f11.usuario_rh_id
    await preferencias.salvar_preferencia(
        sessao_f11,
        contexto_f11.tenant_id,
        usuario_id,
        relatorio_definicao_id=relatorio_id,
        tela=None,
        nome="padrao",
        colunas=["a", "b"],
        ordenacao=None,
        filtros=None,
        larguras=None,
        padrao=True,
    )
    await preferencias.salvar_preferencia(
        sessao_f11,
        contexto_f11.tenant_id,
        usuario_id,
        relatorio_definicao_id=None,
        tela="grade_apuracao",
        nome="compacta",
        colunas=["c"],
        ordenacao=None,
        filtros=None,
        larguras=None,
        padrao=False,
    )

    achada = await preferencias.obter_preferencia(
        sessao_f11,
        contexto_f11.tenant_id,
        usuario_id,
        relatorio_definicao_id=relatorio_id,
        tela=None,
    )
    assert achada is not None
    assert achada.colunas == ["a", "b"]

    todas, paginacao = await preferencias.listar_preferencias(
        sessao_f11, contexto_f11.tenant_id, usuario_id
    )
    assert len(todas) == 2
    assert paginacao.tem_mais is False

    so_do_relatorio, _ = await preferencias.listar_preferencias(
        sessao_f11, contexto_f11.tenant_id, usuario_id, relatorio_definicao_id=relatorio_id
    )
    assert len(so_do_relatorio) == 1
    assert so_do_relatorio[0].nome == "padrao"


async def test_uq_preferencias_colunas_recusa_duplicata_por_insert_direto(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    """Prova a constraint em si (não o upsert): dois `INSERT` diretos com o
    mesmo `(tenant_id, usuario_id, relatorioDefinicaoId, nome)` violam
    `uq_preferencias_colunas` -- é essa constraint que dá ao `PUT` sua
    idempotência sem `Idempotency-Key` (RFC-015, decisão 2)."""
    relatorio_id = contexto_f11.relatorio_ids["espelho-jornada"]
    usuario_id = contexto_f11.usuario_rh_id

    sessao_f11.add(
        PreferenciaColunas(
            tenant_id=contexto_f11.tenant_id,
            usuario_id=usuario_id,
            relatorio_definicao_id=relatorio_id,
            nome="padrao",
            colunas=["a"],
        )
    )
    await sessao_f11.flush()

    sessao_f11.add(
        PreferenciaColunas(
            tenant_id=contexto_f11.tenant_id,
            usuario_id=usuario_id,
            relatorio_definicao_id=relatorio_id,
            nome="padrao",
            colunas=["b"],
        )
    )
    try:
        await sessao_f11.flush()
    except IntegrityError:
        pass
    else:
        raise AssertionError("uq_preferencias_colunas deveria ter recusado a duplicata")
