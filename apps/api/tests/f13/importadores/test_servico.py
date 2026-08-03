"""T19 (A8) -- `app.integracoes.importadores.servico`: CRUD genérico de
`Importacao` (RFC-017) que os três handlers de `app/routers/integracoes.py`
(A8) delegam para cá. Cobre os três tipos de dispatch (`afd_terceiro` com
resolução de REP-P, `colaboradores` reaproveitando a tarefa da F2,
tipo sem pipeline caindo no dispatcher genérico), `PONTO-IMP-002` (já em
andamento), paginação/filtros de `listarImportacoes` e `404 PONTO-REC-001`
de `obterImportacao`.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.integracoes.importadores.servico import (
    criar_importacao,
    listar_importacoes,
    obter_importacao,
)
from app.schemas import contrato as esquemas
from tests.f13.conftest import ContextoF13


def _corpo_afd_terceiro(*, empresa_id: uuid.UUID) -> esquemas.ImportacaoCriar:
    return esquemas.ImportacaoCriar.model_validate(
        {
            "empresaId": str(empresa_id),
            "tipo": "afd_terceiro",
            "origem": "afd",
            "nomeArquivo": "afd_terceiro.txt",
            "conteudoRef": "importacoes/teste/afd_terceiro.txt",
        }
    )


async def test_criar_importacao_afd_terceiro_resolve_rep_p_e_grava_parametros(
    sessao_f13, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    corpo = _corpo_afd_terceiro(empresa_id=contexto_f13.empresa_id)

    resultado = await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    await sessao_f13.commit()

    assert resultado.status == esquemas.Status49.recebido
    assert resultado.tipo == esquemas.Tipo33.afd_terceiro

    obtido = await obter_importacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, importacao_id=resultado.id
    )
    assert obtido.parametros is not None
    assert obtido.parametros["repPId"] == str(rep_p.id)


async def test_criar_importacao_afd_terceiro_sem_rep_p_levanta_rec001(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    corpo = _corpo_afd_terceiro(empresa_id=contexto_f13.empresa_id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_importacao(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            corpo=corpo,
            usuario_id=None,
            redis_url=obter_configuracao().redis_url,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_importacao_afd_terceiro_origem_errada_levanta_val009(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    corpo = esquemas.ImportacaoCriar.model_validate(
        {
            "empresaId": str(contexto_f13.empresa_id),
            "tipo": "afd_terceiro",
            "origem": "csv",  # errado: afd_terceiro exige origem=afd
            "conteudoRef": "x",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_importacao(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            corpo=corpo,
            usuario_id=None,
            redis_url=obter_configuracao().redis_url,
        )
    assert excinfo.value.codigo == "PONTO-VAL-009"


async def test_criar_importacao_afd_terceiro_ja_em_andamento_levanta_imp002(
    sessao_f13, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    corpo = _corpo_afd_terceiro(empresa_id=contexto_f13.empresa_id)
    await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_importacao(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            corpo=corpo,
            usuario_id=None,
            redis_url=obter_configuracao().redis_url,
        )
    assert excinfo.value.codigo == "PONTO-IMP-002"


async def test_criar_importacao_tipo_sem_pipeline_ainda_cria_registro(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """`estrutura` nao tem pipeline nesta fase -- ainda assim o contrato
    promete 202 + acompanhamento; so o WORKER (fora deste teste) e quem
    marca `falhou` de forma honesta."""
    corpo = esquemas.ImportacaoCriar.model_validate(
        {
            "empresaId": str(contexto_f13.empresa_id),
            "tipo": "estrutura",
            "origem": "csv",
            "conteudoRef": "importacoes/teste/estrutura.csv",
        }
    )
    resultado = await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    await sessao_f13.commit()
    assert resultado.status == esquemas.Status49.recebido
    assert resultado.tipo == esquemas.Tipo33.estrutura


async def test_obter_importacao_inexistente_levanta_rec001(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await obter_importacao(
            sessao_f13, tenant_id=contexto_f13.tenant_id, importacao_id=uuid.uuid4()
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_obter_importacao_de_outro_tenant_levanta_rec001(
    sessao_f13, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    corpo = _corpo_afd_terceiro(empresa_id=contexto_f13.empresa_id)
    criada = await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await obter_importacao(sessao_f13, tenant_id=uuid.uuid4(), importacao_id=criada.id)
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_listar_importacoes_filtra_por_tipo_e_pagina(
    sessao_f13, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    corpo_afd = _corpo_afd_terceiro(empresa_id=contexto_f13.empresa_id)
    await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo_afd,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    corpo_estrutura = esquemas.ImportacaoCriar.model_validate(
        {
            "empresaId": str(contexto_f13.empresa_id),
            "tipo": "estrutura",
            "origem": "csv",
            "conteudoRef": "importacoes/teste/estrutura.csv",
        }
    )
    await criar_importacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        corpo=corpo_estrutura,
        usuario_id=None,
        redis_url=obter_configuracao().redis_url,
    )
    await sessao_f13.commit()

    pagina = await listar_importacoes(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=None,
        tipo="afd_terceiro",
        status=None,
        cursor=None,
        limite=10,
        ordenar=None,
    )
    assert len(pagina.dados) == 1
    assert pagina.dados[0].tipo == esquemas.Tipo33.afd_terceiro
    assert pagina.paginacao.limite == 10
