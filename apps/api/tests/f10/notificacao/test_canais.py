"""Testes dos adaptadores provisórios de canal (T11) -- não precisam de
banco: `Notificacao` é instanciada em memória, o adaptador só formata log e
marca atributos no próprio objeto Python."""

from __future__ import annotations

import uuid

import pytest
from ponto_contracts import Notificacao

from app.notificacao import canais
from app.notificacao.canais import email, in_app, push


def _notificacao(canal: str) -> Notificacao:
    return Notificacao(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        usuario_id=uuid.uuid4(),
        canal=canal,
        evento="ajuste.aprovado",
        titulo="Título de teste",
        corpo="Corpo de teste",
    )


@pytest.mark.asyncio
async def test_push_marca_provedor_e_confirma_envio() -> None:
    notificacao = _notificacao("push")
    resultado = await push.enviar(notificacao)
    assert resultado is True
    assert notificacao.provedor == push.PROVEDOR


@pytest.mark.asyncio
async def test_email_marca_provedor_e_confirma_envio() -> None:
    notificacao = _notificacao("email")
    resultado = await email.enviar(notificacao)
    assert resultado is True
    assert notificacao.provedor == email.PROVEDOR


@pytest.mark.asyncio
async def test_in_app_marca_provedor_e_confirma_envio() -> None:
    notificacao = _notificacao("in_app")
    resultado = await in_app.enviar(notificacao)
    assert resultado is True
    assert notificacao.provedor == in_app.PROVEDOR


@pytest.mark.asyncio
async def test_adaptadores_registrados_para_os_tres_canais_desta_fase() -> None:
    assert set(canais.ADAPTADORES) == {"push", "email", "in_app"}
    for canal, adaptador in canais.ADAPTADORES.items():
        notificacao = _notificacao(canal)
        assert await adaptador(notificacao) is True


def test_whatsapp_e_sms_nao_tem_adaptador_nesta_fase() -> None:
    # PCF §2.8: arquitetura pronta, sem provedor real -- nenhum adaptador
    # registrado para os dois ainda.
    assert "whatsapp" not in canais.ADAPTADORES
    assert "sms" not in canais.ADAPTADORES
