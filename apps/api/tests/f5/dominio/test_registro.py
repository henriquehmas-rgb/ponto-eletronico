"""T3 -- persistencia atomica da marcacao (`persistir_marcacao`, `rep_p_ativo`).

Prova a cadeia de hash direto no banco (3 marcacoes sequenciais do mesmo
REP-P) e que `rep_p_ativo` devolve `None` para uma empresa sem REP-P ativo.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao, rep_p_ativo
from tests.f5.conftest import ContextoF5, aplicar_tenant_teste


def _dados_de_teste(contexto: ContextoF5, *, external_id: str, canal: str = "api") -> DadosMarcacao:
    return DadosMarcacao(
        rep_p_id=contexto.rep_p_id,
        empresa_id=contexto.empresa_id,
        cpf=contexto.colaborador_cpf,
        canal=canal,
        datahora_marcacao=dt.datetime.now(tz=dt.UTC),
        unidade_id=contexto.unidade_id,
        colaborador_id=contexto.colaborador_id,
        vinculo_id=contexto.vinculo_id,
        external_id=external_id,
    )


async def test_persistir_marcacao_grava_cadeia_de_hash_direto_no_banco(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacoes = []
    for indice in range(3):
        dados = _dados_de_teste(contexto_f5, external_id=f"ext-cadeia-{indice}")
        marcacao = await persistir_marcacao(sessao_f5, tenant_id=contexto_f5.tenant_id, dados=dados)
        marcacoes.append(marcacao)
    await sessao_f5.commit()
    # `commit()` fecha a transacao onde `SET LOCAL app.tenant_id` valia (ver
    # docstring de `sessao_f5` em `conftest.py`).
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    assert [m.nsr for m in marcacoes] == [1, 2, 3]
    assert marcacoes[0].hash_anterior is None
    assert marcacoes[1].hash_anterior == marcacoes[0].hash_registro
    assert marcacoes[2].hash_anterior == marcacoes[1].hash_registro
    # Cada hash e unico (nenhuma colisao trivial nas tres primeiras emissoes).
    assert len({m.hash_registro for m in marcacoes}) == 3

    # Confirma "direto no banco": relendo por `nsr_emissoes`, nao pela
    # identidade Python dos objetos ja retornados.
    linhas = (
        await sessao_f5.execute(
            text(
                "SELECT nsr, hash_anterior, hash_registro FROM nsr_emissoes "
                "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id ORDER BY nsr"
            ),
            {"tenant_id": contexto_f5.tenant_id, "rep_p_id": contexto_f5.rep_p_id},
        )
    ).all()
    assert [linha.nsr for linha in linhas] == [1, 2, 3]
    assert linhas[0].hash_anterior is None
    assert linhas[1].hash_anterior == linhas[0].hash_registro
    assert linhas[2].hash_anterior == linhas[1].hash_registro

    sequencia = (
        await sessao_f5.execute(
            text(
                "SELECT proximo_nsr, ultimo_nsr_emitido, ultimo_hash FROM nsr_sequencias "
                "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id"
            ),
            {"tenant_id": contexto_f5.tenant_id, "rep_p_id": contexto_f5.rep_p_id},
        )
    ).first()
    assert sequencia is not None
    assert sequencia.proximo_nsr == 4
    assert sequencia.ultimo_nsr_emitido == 3
    assert sequencia.ultimo_hash == marcacoes[2].hash_registro


async def test_persistir_marcacao_grava_crc16_e_linha_afd(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    dados = _dados_de_teste(contexto_f5, external_id="ext-crc")
    marcacao = await persistir_marcacao(sessao_f5, tenant_id=contexto_f5.tenant_id, dados=dados)
    await sessao_f5.commit()

    assert 0 <= marcacao.crc16 <= 0xFFFF
    assert marcacao.linha_afd is not None
    assert contexto_f5.colaborador_cpf in marcacao.linha_afd
    assert marcacao.coletada_offline is False
    assert marcacao.canal == "api"


async def test_rep_p_ativo_devolve_none_para_empresa_sem_rep_p(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    outra_empresa_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO empresas (id, tenant_id, tipo, cnpj, razao_social, uf, "
            "codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Empresa sem REP-P Ltda', 'GO', '5208707')"
        ),
        {
            "id": outra_empresa_id,
            "tenant_id": contexto_f5.tenant_id,
            "cnpj": str(uuid.uuid4().int)[:14],
        },
    )

    resultado = await rep_p_ativo(sessao_f5, contexto_f5.tenant_id, outra_empresa_id)

    assert resultado is None


async def test_rep_p_ativo_devolve_o_rep_p_da_empresa(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    resultado = await rep_p_ativo(sessao_f5, contexto_f5.tenant_id, contexto_f5.empresa_id)

    assert resultado is not None
    assert resultado.id == contexto_f5.rep_p_id
    assert resultado.status == "ativo"
