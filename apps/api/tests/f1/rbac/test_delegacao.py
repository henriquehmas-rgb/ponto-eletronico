"""T9 -- efeito da delegacao temporaria na autorizacao e na trilha de
auditoria. Os ENDPOINTS de delegacao sao da F10 (ver PCF secao 4); aqui a
delegacao e criada direto na tabela, como o proprio PCF instrui.
"""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.erros import ErroDeAplicacao
from app.identidade.auditoria.hash_chain import registrar_auditoria_de_sujeito
from app.identidade.rbac.delegacao import verificar_delegacao_vigente
from app.identidade.rbac.resolucao import resolver_sujeito
from tests.f1.rbac._apoio import atribuir_perfil, criar_usuario
from tests.f1.rbac.conftest import aplicar_tenant


async def _criar_par_delegante_delegado(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, sufixo: str
) -> tuple[uuid.UUID, uuid.UUID]:
    delegante_id = await criar_usuario(
        sessao, tenant_id=tenant_id, email=f"delegante.{sufixo}@f1a3.local", nome="Delegante RH"
    )
    delegado_id = await criar_usuario(
        sessao,
        tenant_id=tenant_id,
        email=f"delegado.{sufixo}@f1a3.local",
        nome="Delegado colaborador",
    )
    # Delegante: perfil `rh` (tem `auditoria.ler`, ver test_matriz_perfis.py).
    await atribuir_perfil(
        sessao,
        tenant_id=tenant_id,
        usuario_id=delegante_id,
        perfil_codigo="rh",
        escopo_tipo="tenant",
    )
    # Delegado: perfil `colaborador` (nao tem `auditoria.ler` por conta propria).
    await atribuir_perfil(
        sessao,
        tenant_id=tenant_id,
        usuario_id=delegado_id,
        perfil_codigo="colaborador",
        escopo_tipo="proprio",
    )
    return delegante_id, delegado_id


async def _criar_delegacao(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    delegante_id: uuid.UUID,
    delegado_id: uuid.UUID,
    inicio_em: _dt.datetime,
    fim_em: _dt.datetime,
    status: str = "ativa",
) -> uuid.UUID:
    delegacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO delegacoes "
            "(id, tenant_id, delegante_usuario_id, delegado_usuario_id, motivo, "
            " inicio_em, fim_em, status) "
            "VALUES (:id, :tenant, :delegante, :delegado, :motivo, :inicio, :fim, :status)"
        ),
        {
            "id": str(delegacao_id),
            "tenant": str(tenant_id),
            "delegante": str(delegante_id),
            "delegado": str(delegado_id),
            "motivo": "Ferias do gestor (teste F1/A3)",
            "inicio": inicio_em,
            "fim": fim_em,
            "status": status,
        },
    )
    return delegacao_id


async def test_delegado_herda_permissao_dentro_da_janela(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    agora = _dt.datetime.now(_dt.UTC)
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        delegante_id, delegado_id = await _criar_par_delegante_delegado(
            sessao, tenant_id=tenant_a_id, sufixo="janela"
        )
        delegacao_id = await _criar_delegacao(
            sessao,
            tenant_id=tenant_a_id,
            delegante_id=delegante_id,
            delegado_id=delegado_id,
            inicio_em=agora - _dt.timedelta(hours=1),
            fim_em=agora + _dt.timedelta(hours=1),
        )
        await sessao.commit()
        # `commit()` fecha a transacao onde `SET LOCAL app.tenant_id` valia;
        # sem reaplicar, a consulta seguinte nesta mesma sessao roda sem
        # tenant publicado e o RLS devolve zero linhas.
        await aplicar_tenant(sessao, tenant_a_id)

        sem_delegacao = await resolver_sujeito(
            sessao,
            tenant_id=tenant_a_id,
            usuario_id=delegado_id,
            agora=agora,
            seguir_delegacao=False,
        )
        com_delegacao = await resolver_sujeito(
            sessao, tenant_id=tenant_a_id, usuario_id=delegado_id, agora=agora
        )

    assert "auditoria.ler" not in sem_delegacao.permissoes
    assert "auditoria.ler" in com_delegacao.permissoes
    assert com_delegacao.delegacao_id == delegacao_id


async def test_delegado_nao_herda_fora_da_janela(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    agora = _dt.datetime.now(_dt.UTC)
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        delegante_id, delegado_id = await _criar_par_delegante_delegado(
            sessao, tenant_id=tenant_a_id, sufixo="expirada"
        )
        await _criar_delegacao(
            sessao,
            tenant_id=tenant_a_id,
            delegante_id=delegante_id,
            delegado_id=delegado_id,
            inicio_em=agora - _dt.timedelta(days=2),
            fim_em=agora - _dt.timedelta(days=1),
            status="encerrada",
        )
        await sessao.commit()
        await aplicar_tenant(sessao, tenant_a_id)

        sujeito = await resolver_sujeito(
            sessao, tenant_id=tenant_a_id, usuario_id=delegado_id, agora=agora
        )

    assert sujeito.delegacao_id is None
    assert "auditoria.ler" not in sujeito.permissoes


async def test_delegacao_expirada_verificacao_explicita_e_perm_005(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    """Uso de `verificar_delegacao_vigente` (fase que afirma agir por uma
    delegacao especifica, por exemplo a F10) com delegacao fora da janela."""
    agora = _dt.datetime.now(_dt.UTC)
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        delegante_id, delegado_id = await _criar_par_delegante_delegado(
            sessao, tenant_id=tenant_a_id, sufixo="perm005"
        )
        delegacao_id = await _criar_delegacao(
            sessao,
            tenant_id=tenant_a_id,
            delegante_id=delegante_id,
            delegado_id=delegado_id,
            inicio_em=agora - _dt.timedelta(days=2),
            fim_em=agora - _dt.timedelta(days=1),
            status="cancelada",
        )
        await sessao.commit()
        await aplicar_tenant(sessao, tenant_a_id)

        delegacao = (
            (
                await sessao.execute(
                    text("SELECT * FROM delegacoes WHERE id = :id"), {"id": str(delegacao_id)}
                )
            )
            .mappings()
            .first()
        )
        assert delegacao is not None
        status_gravado = delegacao["status"]
        inicio_gravado = delegacao["inicio_em"]
        fim_gravado = delegacao["fim_em"]

    class _Fake:
        status = status_gravado
        inicio_em = inicio_gravado
        fim_em = fim_gravado

    with pytest.raises(ErroDeAplicacao) as excinfo:
        verificar_delegacao_vigente(_Fake(), agora=agora)
    assert excinfo.value.codigo == "PONTO-PERM-005"

    with pytest.raises(ErroDeAplicacao) as excinfo_none:
        verificar_delegacao_vigente(None, agora=agora)
    assert excinfo_none.value.codigo == "PONTO-PERM-005"


async def test_auditoria_registra_delegacao_id(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    """Toda acao exercida por delegacao grava `auditoria.delegacao_id` (T9 + T10)."""
    agora = _dt.datetime.now(_dt.UTC)
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        delegante_id, delegado_id = await _criar_par_delegante_delegado(
            sessao, tenant_id=tenant_a_id, sufixo="auditoria"
        )
        delegacao_id = await _criar_delegacao(
            sessao,
            tenant_id=tenant_a_id,
            delegante_id=delegante_id,
            delegado_id=delegado_id,
            inicio_em=agora - _dt.timedelta(hours=1),
            fim_em=agora + _dt.timedelta(hours=1),
        )
        await sessao.commit()
        await aplicar_tenant(sessao, tenant_a_id)

        sujeito = await resolver_sujeito(
            sessao, tenant_id=tenant_a_id, usuario_id=delegado_id, agora=agora
        )
        assert sujeito.delegacao_id == delegacao_id

        registro = await registrar_auditoria_de_sujeito(
            sessao,
            sujeito,
            evento="identidade.teste.acao_delegada",
            entidade="testes",
            acao="atualizar",
        )
        await sessao.commit()
        await aplicar_tenant(sessao, tenant_a_id)

        linha = (
            (
                await sessao.execute(
                    text("SELECT delegacao_id FROM auditoria WHERE id = :id"),
                    {"id": str(registro.id)},
                )
            )
            .mappings()
            .first()
        )

    assert linha is not None
    assert str(linha["delegacao_id"]) == str(delegacao_id)
