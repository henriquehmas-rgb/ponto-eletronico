"""Rotas HTTP da fila de revisao antifraude (`app.routers.marcacoes`, RFC-020):
`listarRevisaoPendente`/`decidirRevisaoMarcacao`.

Chamada direta ao handler do router (nao `TestClient`) -- mesmo padrao ja
usado por toda a suite de F14 desta pasta (`test_fila_revisao.py`) e por F5
(`tests/f5/pipeline/test_ingestao.py`): a permissao em si
(`Depends(exigir_permissao(...))`) e mecanismo generico ja coberto em
`tests/f1/rbac/**`, o que este arquivo cobre e o que e NOVO aqui -- a
matematica de paginacao por cursor e a serializacao dos enums do contrato,
que `app.antifraude.fila` (testado em `test_fila_revisao.py`) nao tem.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.autenticacao_cliente import ContextoAcesso
from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.routers.marcacoes import decidir_revisao_marcacao, listar_revisao_pendente
from app.schemas import contrato
from tests.f14.antifraude.conftest import ContextoF14A1
from tests.f14.antifraude.test_fila_revisao import _registrar_marcacao_suspeita


async def _sujeito_gestor(contexto: ContextoF14A1) -> Sujeito:
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.ler_sensivel", "marcacoes.aprovar"}),
    )


def _acesso(sujeito: Sujeito) -> ContextoAcesso:
    # Retrofit de 2026-08-08: os handlers de `app/routers/marcacoes.py`
    # passaram a receber `ContextoAcesso`, nao mais `Sujeito` direto -- ver
    # `app/comum/autenticacao_cliente.py`.
    return ContextoAcesso(tenant_id=sujeito.tenant_id, sujeito=sujeito)


async def test_listar_revisao_pendente_serializa_item_com_enums_corretos(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    gestor = await _sujeito_gestor(contexto_f14a1)

    pagina = await listar_revisao_pendente(
        acesso=_acesso(gestor),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
        cursor=None,
        limite=None,
        empresa_id=None,
    )

    assert isinstance(pagina, contrato.ListaRevisaoPendente)
    item = next(i for i in pagina.dados if i.marcacao_id == resposta.marcacao.id)
    assert isinstance(item.canal, contrato.Canal2)
    assert item.classificacao_confianca is None or isinstance(
        item.classificacao_confianca, contrato.ClassificacaoConfianca
    )
    assert pagina.paginacao.limite == 50


async def test_listar_revisao_pendente_pagina_por_cursor(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    for _ in range(3):
        await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    gestor = await _sujeito_gestor(contexto_f14a1)

    pagina_1 = await listar_revisao_pendente(
        acesso=_acesso(gestor),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
        cursor=None,
        limite=2,
        empresa_id=None,
    )
    assert len(pagina_1.dados) == 2
    assert pagina_1.paginacao.tem_mais is True
    assert pagina_1.paginacao.proximo_cursor is not None

    pagina_2 = await listar_revisao_pendente(
        acesso=_acesso(gestor),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
        cursor=pagina_1.paginacao.proximo_cursor,
        limite=2,
        empresa_id=None,
    )
    assert len(pagina_2.dados) >= 1
    assert pagina_2.paginacao.tem_mais is False

    ids_pagina_1 = {item.marcacao_id for item in pagina_1.dados}
    ids_pagina_2 = {item.marcacao_id for item in pagina_2.dados}
    assert ids_pagina_1.isdisjoint(ids_pagina_2)


async def test_decidir_revisao_marcacao_devolve_meta_atualizada(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    gestor = await _sujeito_gestor(contexto_f14a1)

    meta = await decidir_revisao_marcacao(
        idempotency_key="teste-decisao-http-" + uuid.uuid4().hex,
        marcacao_id=resposta.marcacao.id,
        corpo=contrato.DecisaoRevisaoRequisicao(
            decisao=contrato.DecisaoRevisao.aprovada,
            observacao="Confirmado com o colaborador.",
        ),
        acesso=_acesso(gestor),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
    )

    assert isinstance(meta, contrato.MarcacaoMeta)
    assert meta.revisao_status == "aprovada"
    assert meta.revisado_por == gestor.usuario_id
    assert meta.revisao_observacao == "Confirmado com o colaborador."

    pendentes_apos = await listar_revisao_pendente(
        acesso=_acesso(gestor),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
        cursor=None,
        limite=None,
        empresa_id=None,
    )
    assert resposta.marcacao.id not in {i.marcacao_id for i in pendentes_apos.dados}


async def test_decidir_revisao_marcacao_ja_decidida_propaga_erro_de_aplicacao(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """O router nao precisa de tratamento proprio para o erro -- confirma
    que `ErroDeAplicacao` de `app.antifraude.fila` atravessa sem ser
    engolido, para o handler global de excecoes formatar o problem+json."""
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    gestor = await _sujeito_gestor(contexto_f14a1)

    async def _decidir() -> contrato.MarcacaoMeta:
        return await decidir_revisao_marcacao(
            idempotency_key="teste-decisao-http-" + uuid.uuid4().hex,
            marcacao_id=resposta.marcacao.id,
            corpo=contrato.DecisaoRevisaoRequisicao(decisao=contrato.DecisaoRevisao.rejeitada),
            acesso=_acesso(gestor),
            response=Response(),
            sessao=sessao_f14a1,
            x_tenant=None,
            x_request_id=None,
        )

    await _decidir()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _decidir()
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_listar_revisao_pendente_nao_mistura_tenant(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """Sanity check da RLS de ponta a ponta pelo router: um sujeito de OUTRO
    tenant nao ve a marcacao sinalizada deste teste."""
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    outro_tenant = uuid.uuid4()
    sujeito_outro_tenant = Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=outro_tenant,
        autenticado=True,
        permissoes=frozenset({"marcacoes.ler_sensivel"}),
    )

    # `sessao_f14a1` tem `SET LOCAL app.tenant_id` do tenant do teste (RLS),
    # e o handler tambem filtra explicitamente por `tenant_id_ou_erro(sujeito)`
    # (= outro_tenant aqui) em `fila.listar_pendentes` -- as duas camadas
    # concordam em excluir a marcacao, cada uma bastaria sozinha.
    pendentes = await listar_revisao_pendente(
        acesso=_acesso(sujeito_outro_tenant),
        response=Response(),
        sessao=sessao_f14a1,
        x_tenant=None,
        x_request_id=None,
        cursor=None,
        limite=None,
        empresa_id=None,
    )
    assert resposta.marcacao.id not in {i.marcacao_id for i in pendentes.dados}
