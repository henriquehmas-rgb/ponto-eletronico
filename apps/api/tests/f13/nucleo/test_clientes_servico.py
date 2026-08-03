"""T2 -- `app.integracoes.clientes.servico` (F13/A1), casos de borda que o
teste HTTP (`test_admin_api_keys.py`) não cobre: cliente/chave inexistentes
e a interseção de escopo efetiva. Chama o serviço diretamente (sem TestClient
nem app.main) -- mais rápido e isola a lógica do serviço da camada HTTP."""

from __future__ import annotations

import uuid

import pytest

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.integracoes.clientes import servico as clientes_servico
from app.schemas import contrato
from tests.f13.conftest import ContextoF13, criar_api_client_teste


def _sujeito(tenant_id: uuid.UUID) -> Sujeito:
    return Sujeito(usuario_id=uuid.uuid4(), tenant_id=tenant_id, autenticado=True)


async def test_listar_api_keys_cliente_inexistente_e_rec_001(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await clientes_servico.listar_api_keys(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            api_client_id=uuid.uuid4(),
            cursor=None,
            limite=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_api_key_cliente_inexistente_e_rec_001(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    dados = contrato.ApiKeyCriar(escopos=["marcacoes:ler"])
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await clientes_servico.criar_api_key(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            api_client_id=uuid.uuid4(),
            dados=dados,
            sujeito=_sujeito(contexto_f13.tenant_id),
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_revogar_api_key_chave_inexistente_e_rec_001(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    await sessao_f13.flush()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await clientes_servico.revogar_api_key(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            api_client_id=cliente.id,
            chave_id=uuid.uuid4(),
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_api_key_escopo_efetivo_e_a_intersecao(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """Pedir menos escopos do que o cliente concede: a chave sai só com o
    subconjunto pedido (mesmo comportamento de `oauth.calcular_escopo_efetivo`
    já usado por `emitirTokenOAuth`)."""
    cliente = await criar_api_client_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        escopos=["marcacoes:ler", "colaboradores:ler", "fechamentos:ler"],
    )
    await sessao_f13.flush()

    dados = contrato.ApiKeyCriar(escopos=["marcacoes:ler"])
    chave, chave_em_claro = await clientes_servico.criar_api_key(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        api_client_id=cliente.id,
        dados=dados,
        sujeito=_sujeito(contexto_f13.tenant_id),
    )
    assert chave.escopos == ["marcacoes:ler"]
    assert chave_em_claro


async def test_criar_api_key_sem_ambiente_pedido_herda_do_cliente(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, ambiente="sandbox"
    )
    await sessao_f13.flush()

    dados = contrato.ApiKeyCriar(escopos=list(cliente.escopos or []))
    chave, _ = await clientes_servico.criar_api_key(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        api_client_id=cliente.id,
        dados=dados,
        sujeito=_sujeito(contexto_f13.tenant_id),
    )
    assert chave.ambiente == "sandbox"
    assert chave.prefixo.startswith("pk_sbx_")


async def test_revogar_api_key_duas_vezes_preserva_o_primeiro_motivo(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    await sessao_f13.flush()
    dados = contrato.ApiKeyCriar(escopos=list(cliente.escopos or []))
    chave, _ = await clientes_servico.criar_api_key(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        api_client_id=cliente.id,
        dados=dados,
        sujeito=_sujeito(contexto_f13.tenant_id),
    )
    await sessao_f13.flush()

    await clientes_servico.revogar_api_key(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        api_client_id=cliente.id,
        chave_id=chave.id,
        motivo="primeiro motivo",
    )
    primeira_revogacao = chave.revogada_em
    assert primeira_revogacao is not None

    await clientes_servico.revogar_api_key(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        api_client_id=cliente.id,
        chave_id=chave.id,
        motivo="segundo motivo, nunca deveria substituir o primeiro",
    )
    assert chave.revogada_em == primeira_revogacao
    assert chave.motivo_revogacao == "primeiro motivo"
