"""T19 (A8) -- `app.integracoes.importadores.afd_terceiro.servico`: resolução
de REP-P alvo e processamento de ponta a ponta (`processar_arquivo`) contra
banco real."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Importacao, Marcacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.importadores.afd_terceiro.parser import ArquivoAfdInvalido
from app.integracoes.importadores.afd_terceiro.servico import (
    processar_arquivo,
    resolver_rep_p_alvo,
)
from tests.f13.conftest import ContextoF13, aplicar_tenant_teste
from tests.f13.importadores.afd_terceiro.conftest import montar_arquivo_afd


async def _criar_importacao_teste(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> Importacao:
    importacao = Importacao(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        tipo="afd_terceiro",
        origem="afd",
        nome_arquivo="afd_terceiro.txt",
        status="recebido",
    )
    sessao.add(importacao)
    await sessao.flush()
    return importacao


async def test_resolver_rep_p_alvo_sem_rep_p_levanta_rec001(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_rep_p_alvo(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            empresa_id=contexto_f13.empresa_id,
            rep_p_id_informado=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_resolver_rep_p_alvo_um_rep_p_ativo_resolve_sozinho(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    resolvido = await resolver_rep_p_alvo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id_informado=None,
    )
    assert resolvido == rep_p.id


async def test_resolver_rep_p_alvo_dois_ativos_sem_override_levanta_val001(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_rep_p_alvo(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            empresa_id=contexto_f13.empresa_id,
            rep_p_id_informado=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_resolver_rep_p_alvo_dois_ativos_com_override_resolve(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    _primeiro = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    segundo = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    resolvido = await resolver_rep_p_alvo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id_informado=segundo.id,
    )
    assert resolvido == segundo.id


async def test_resolver_rep_p_alvo_rep_p_inativo_nao_conta_no_automatico(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    ativo = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
        status="inativo",
    )
    resolvido = await resolver_rep_p_alvo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id_informado=None,
    )
    assert resolvido == ativo.id


async def test_processar_arquivo_insere_marcacoes_e_resolve_colaborador(
    sessao_f13: AsyncSession,
    contexto_f13: ContextoF13,
    criar_rep_p,
    criar_colaborador_ativo,
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    colaborador = await criar_colaborador_ativo(
        tenant_id=contexto_f13.tenant_id, empresa_id=contexto_f13.empresa_id, cpf="12345678909"
    )
    importacao = await _criar_importacao_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, empresa_id=contexto_f13.empresa_id
    )

    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 100, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": colaborador.cpf},
            {"nsr": 101, "datahora_marc": "2026-01-01T17:00:00-0300", "cpf": "98765432100"},
        ]
    )

    resultado = await processar_arquivo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id=rep_p.id,
        importacao=importacao,
        conteudo=conteudo,
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    assert resultado.total_linhas_tipo7 == 2
    assert resultado.linhas_sucesso == 2
    assert resultado.linhas_erro == 0

    linhas = (
        (
            await sessao_f13.execute(
                sa.select(Marcacao)
                .where(Marcacao.origem_importacao_id == importacao.id)
                .order_by(Marcacao.nsr)
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas) == 2

    linha_com_colaborador = linhas[0]
    assert linha_com_colaborador.nsr == 100
    assert linha_com_colaborador.cpf == colaborador.cpf
    assert linha_com_colaborador.colaborador_id == colaborador.id
    assert linha_com_colaborador.vinculo_id == colaborador.vinculo_id
    assert linha_com_colaborador.canal == "importacao"
    assert linha_com_colaborador.rep_p_id == rep_p.id
    assert linha_com_colaborador.hash_anterior is None

    linha_sem_colaborador = linhas[1]
    assert linha_sem_colaborador.nsr == 101
    assert linha_sem_colaborador.colaborador_id is None
    assert linha_sem_colaborador.vinculo_id is None
    # Encadeada com o hash do registro importado anterior (cadeia PROPRIA
    # desta importacao -- ver app.integracoes.importadores.afd_terceiro.cadeia).
    assert linha_sem_colaborador.hash_anterior == linha_com_colaborador.hash_registro


async def test_processar_arquivo_cpf_invalido_vira_erro_de_linha_sem_abortar(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    importacao = await _criar_importacao_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, empresa_id=contexto_f13.empresa_id
    )
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            # CPF com todos os digitos iguais: estruturalmente numerico (12
            # digitos), mas reprovado pelo digito verificador -- erro de
            # LINHA, nao de arquivo.
            {"nsr": 1, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"},
            {"nsr": 2, "datahora_marc": "2026-01-01T09:00:00-0300", "cpf": "52998224725"},
        ]
    )

    resultado = await processar_arquivo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id=rep_p.id,
        importacao=importacao,
        conteudo=conteudo,
    )

    assert resultado.total_linhas_tipo7 == 2
    assert resultado.linhas_sucesso == 1
    assert resultado.linhas_erro == 1
    assert resultado.erros[0]["codigo"] == "PONTO-VAL-002"
    assert resultado.erros[0]["campo"] == "cpf"


async def test_processar_arquivo_estrutural_invalido_propaga_arquivoafdinvalido(
    sessao_f13: AsyncSession, contexto_f13: ContextoF13, criar_rep_p
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    importacao = await _criar_importacao_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, empresa_id=contexto_f13.empresa_id
    )
    with pytest.raises(ArquivoAfdInvalido):
        await processar_arquivo(
            sessao_f13,
            tenant_id=contexto_f13.tenant_id,
            empresa_id=contexto_f13.empresa_id,
            rep_p_id=rep_p.id,
            importacao=importacao,
            conteudo=b"arquivo totalmente invalido",
        )
