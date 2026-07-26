"""Testes de `app/marcacao/consulta/marcacoes.py` (T10, agente A3).

Cobre listagem paginada por cursor nas duas ordenacoes do contrato (`nsr`,
`datahoraMarcacao`), rejeicao de cursor trocado de ordenacao (`PONTO-VAL-006`),
bloqueio de `incluirMeta` sem `marcacoes.ler_sensivel` (`PONTO-PERM-001`), e
`obterMarcacao`/`obterMetaMarcacao` (incluindo 404 via `PONTO-REC-001`).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.consulta import marcacoes as consulta_marcacoes
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from tests.f5.conftest import ContextoF5


def _sujeito(contexto: ContextoF5, *, com_ler_sensivel: bool) -> Sujeito:
    """Sujeito de teste. `permissoes_sensiveis` fica vazio de proposito: com
    o codigo la dentro, `exigir_permissao` tambem grava
    `acessos_dados_sensiveis` (F1), que exigiria um `usuarios.id` real -- fora
    do escopo desta suite, que testa so o gate de permissao do T10."""
    permissoes = {"marcacoes.ler"}
    if com_ler_sensivel:
        permissoes.add("marcacoes.ler_sensivel")
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset(permissoes),
    )


async def _criar_marcacoes(
    sessao: AsyncSession, contexto: ContextoF5, quantidade: int
) -> list[uuid.UUID]:
    """Cria `quantidade` marcacoes sequenciais do mesmo REP-P, com
    `datahora_marcacao` crescente na mesma ordem do NSR (facilita comparar as
    duas ordenacoes do contrato sem duas fixtures separadas)."""
    base = dt.datetime.now(tz=dt.UTC).replace(microsecond=0)
    ids: list[uuid.UUID] = []
    for indice in range(quantidade):
        marcacao = await persistir_marcacao(
            sessao,
            tenant_id=contexto.tenant_id,
            dados=DadosMarcacao(
                rep_p_id=contexto.rep_p_id,
                empresa_id=contexto.empresa_id,
                unidade_id=contexto.unidade_id,
                colaborador_id=contexto.colaborador_id,
                vinculo_id=contexto.vinculo_id,
                cpf=contexto.colaborador_cpf,
                canal="mobile",
                datahora_marcacao=base + dt.timedelta(seconds=indice),
                dispositivo_id=contexto.dispositivo_id,
            ),
        )
        ids.append(marcacao.id)
    # Sem commit: a query seguinte roda na MESMA transacao (flush basta para
    # ela enxergar as linhas). Commitar aqui encerraria o SET LOCAL
    # app.tenant_id da fixture (`aplicar_tenant_teste`) e a consulta seguinte,
    # sob RLS, devolveria vazio -- nao erro -- ate reaplicar o tenant.
    return ids


async def test_listar_marcacoes_ordenar_nsr_desc_pagina_estavel(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 5)
    sujeito = _sujeito(contexto_f5, com_ler_sensivel=False)

    vistos: list[uuid.UUID] = []
    cursor = None
    for _ in range(10):
        pagina = await consulta_marcacoes.listar_marcacoes(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            sujeito=sujeito,
            ordenar="nsr:desc",
            limite=2,
            cursor=cursor,
        )
        vistos.extend(uuid.UUID(str(item.id)) for item in pagina.dados)
        if not pagina.paginacao.tem_mais:
            break
        cursor = pagina.paginacao.proximo_cursor

    assert vistos == list(reversed(ids))


async def test_listar_marcacoes_ordenar_datahora_asc_pagina_estavel(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 5)
    sujeito = _sujeito(contexto_f5, com_ler_sensivel=False)

    vistos: list[uuid.UUID] = []
    cursor = None
    for _ in range(10):
        pagina = await consulta_marcacoes.listar_marcacoes(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            sujeito=sujeito,
            ordenar="datahoraMarcacao:asc",
            limite=2,
            cursor=cursor,
        )
        vistos.extend(uuid.UUID(str(item.id)) for item in pagina.dados)
        if not pagina.paginacao.tem_mais:
            break
        cursor = pagina.paginacao.proximo_cursor

    assert vistos == ids


async def test_cursor_de_uma_ordenacao_nao_e_aceito_noutra(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _criar_marcacoes(sessao_f5, contexto_f5, 3)
    sujeito = _sujeito(contexto_f5, com_ler_sensivel=False)

    pagina = await consulta_marcacoes.listar_marcacoes(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        sujeito=sujeito,
        ordenar="nsr:desc",
        limite=1,
    )
    assert pagina.paginacao.tem_mais
    cursor_de_nsr = pagina.paginacao.proximo_cursor
    assert cursor_de_nsr is not None

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta_marcacoes.listar_marcacoes(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            sujeito=sujeito,
            ordenar="datahoraMarcacao:asc",
            cursor=cursor_de_nsr,
        )
    assert excinfo.value.codigo == "PONTO-VAL-006"


async def test_incluir_meta_sem_permissao_sensivel_bloqueia(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _criar_marcacoes(sessao_f5, contexto_f5, 1)
    sujeito_sem_permissao = _sujeito(contexto_f5, com_ler_sensivel=False)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta_marcacoes.listar_marcacoes(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            sujeito=sujeito_sem_permissao,
            incluir_meta=True,
        )
    assert excinfo.value.codigo == "PONTO-PERM-001"


async def test_incluir_meta_com_permissao_sensivel_nao_bloqueia(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 1)
    marcacao_id = ids[0]
    linha = (
        await sessao_f5.execute(
            text("SELECT datahora_marcacao FROM marcacoes WHERE id = :id"),
            {"id": marcacao_id},
        )
    ).first()
    assert linha is not None
    await sessao_f5.execute(
        text(
            "INSERT INTO marcacoes_meta "
            "(id, tenant_id, marcacao_id, marcacao_datahora, dentro_geocerca, "
            " score_confianca, classificacao_confianca, revisao_status) "
            "VALUES (:id, :tenant_id, :marcacao_id, :marcacao_datahora, TRUE, "
            "        100, 'alta', 'nao_requer')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f5.tenant_id,
            "marcacao_id": marcacao_id,
            "marcacao_datahora": linha.datahora_marcacao,
        },
    )
    sujeito_com_permissao = _sujeito(contexto_f5, com_ler_sensivel=True)

    # RFC-011 (decidida): a permissao e checada de verdade e o conteudo de
    # MarcacaoMeta vem embutido em `pagina.metas` (mapa marcacaoId -> MarcacaoMeta,
    # irmao de `dados`), sem alterar o schema de `Marcacao`.
    pagina = await consulta_marcacoes.listar_marcacoes(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        sujeito=sujeito_com_permissao,
        incluir_meta=True,
    )
    assert len(pagina.dados) == 1
    assert pagina.metas is not None
    meta = pagina.metas[str(marcacao_id)]
    assert meta.marcacao_id == marcacao_id
    assert meta.dentro_geocerca is True
    assert meta.score_confianca == 100


async def test_listar_marcacoes_sem_incluir_meta_nao_popula_metas(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _criar_marcacoes(sessao_f5, contexto_f5, 1)
    sujeito_sem_pedir_meta = _sujeito(contexto_f5, com_ler_sensivel=True)

    pagina = await consulta_marcacoes.listar_marcacoes(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        sujeito=sujeito_sem_pedir_meta,
    )
    assert pagina.metas is None


async def test_obter_marcacao_devolve_registro_gravado(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 1)

    marcacao = await consulta_marcacoes.obter_marcacao(
        sessao_f5, tenant_id=contexto_f5.tenant_id, marcacao_id=ids[0]
    )
    assert marcacao.id == ids[0]
    assert marcacao.cpf == contexto_f5.colaborador_cpf
    assert marcacao.nsr is not None and marcacao.nsr >= 1


async def test_obter_marcacao_inexistente_e_rec_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta_marcacoes.obter_marcacao(
            sessao_f5, tenant_id=contexto_f5.tenant_id, marcacao_id=uuid.uuid4()
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_obter_meta_marcacao_devolve_contexto_gravado(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 1)
    marcacao_id = ids[0]

    linha = (
        await sessao_f5.execute(
            text("SELECT datahora_marcacao FROM marcacoes WHERE id = :id"),
            {"id": marcacao_id},
        )
    ).first()
    assert linha is not None

    await sessao_f5.execute(
        text(
            "INSERT INTO marcacoes_meta "
            "(id, tenant_id, marcacao_id, marcacao_datahora, dentro_geocerca, "
            " score_confianca, classificacao_confianca, revisao_status) "
            "VALUES (:id, :tenant_id, :marcacao_id, :marcacao_datahora, TRUE, "
            "        100, 'alta', 'nao_requer')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f5.tenant_id,
            "marcacao_id": marcacao_id,
            "marcacao_datahora": linha.datahora_marcacao,
        },
    )

    meta = await consulta_marcacoes.obter_meta_marcacao(
        sessao_f5, tenant_id=contexto_f5.tenant_id, marcacao_id=marcacao_id
    )
    assert meta.marcacao_id == marcacao_id
    assert meta.dentro_geocerca is True
    assert meta.score_confianca == 100
    assert meta.classificacao_confianca is not None
    assert meta.classificacao_confianca.value == "alta"


async def test_obter_meta_marcacao_sem_meta_e_rec_001(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    ids = await _criar_marcacoes(sessao_f5, contexto_f5, 1)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta_marcacoes.obter_meta_marcacao(
            sessao_f5, tenant_id=contexto_f5.tenant_id, marcacao_id=ids[0]
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
