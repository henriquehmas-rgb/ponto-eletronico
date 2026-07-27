"""Fecha o gap de cobertura de `app.apuracao.dominio.consulta` (F4, §7 do
PCF exige >=90% de `app.apuracao`) NAO coberto por `test_consulta.py`
(existente, ownership de A1, nao editado por este arquivo): os filtros
opcionais individuais de `listar_apuracoes`/`listar_ocorrencias` e os dois
caminhos de erro (`ate < de` e `obterApuracao` 404).

Reusa a mesma fixture minima de `tests/f4/tratamento/conftest.py` (via
`tests/f4/dominio/conftest.py`) que `test_consulta.py` ja usa: um vinculo SEM
jornada/escala vigente faz `apurar_dia` cair sempre no ramo `PONTO-APUR-002`
(grava `apuracoes_dia`/`ocorrencias` reais sem precisar da massa de jornada
da F3). Para os filtros que precisam de duas entidades genuinamente
diferentes (empresa/unidade/departamento/colaborador/vinculo), este modulo
semeia um SEGUNDO contexto completo (`outro_contexto`) no MESMO tenant, via
`INSERT` direto (mesmo padrao ja usado por `tests/f4/tratamento/conftest.py`
e por `test_servico.py` para `periodos`/`fechamentos`). Para os filtros que
`apurar_dia` sempre grava com o mesmo valor (status, marcacoes_impares,
codigo/severidade/status de ocorrencia), muta-se a linha ja gravada
diretamente via ORM antes de flush -- mesmo padrao que
`test_servico.py:test_atualizar_tratamento_fora_de_rascunho_pendente_e_recusado`
ja usa (`tratamento.status = "aprovado"; await sessao.flush()`).
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
import sqlalchemy as sa
from ponto_contracts import ApuracaoDia as ApuracaoDiaOrm
from ponto_contracts import Ocorrencia as OcorrenciaOrm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.consulta import (
    CODIGO_INTERVALO_INVALIDO,
    CODIGO_RECURSO_NAO_ENCONTRADO,
    listar_apuracoes,
    listar_ocorrencias,
    obter_apuracao,
)
from app.apuracao.dominio.servico import apurar_dia
from app.core.erros import ErroDeAplicacao
from tests.f4.tratamento.conftest import ContextoTratamento

_DATA = dt.date(2026, 1, 5)
_DATA_2 = dt.date(2026, 1, 6)


# --------------------------------------------------------------------------
# Segundo contexto (empresa/unidade/departamento/colaborador/vinculo
# diferentes) no MESMO tenant de `contexto_tratamento`, para provar que cada
# filtro individual realmente restringe: uma apuracao/ocorrencia que bate,
# uma que nao bate.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContextoAlternativo:
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    departamento_id: uuid.UUID
    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID


async def _criar_empresa(sessao: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Empresa filtro Ltda', "
            "        'Empresa filtro', 'SP', '3550308', 'America/Sao_Paulo')"
        ),
        {"id": empresa_id, "tenant_id": tenant_id, "cnpj": cnpj},
    )
    return empresa_id


async def _criar_unidade(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> uuid.UUID:
    unidade_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Unidade filtro', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {
            "id": unidade_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"U-{uuid.uuid4().hex[:8]}",
        },
    )
    return unidade_id


async def _criar_departamento(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> uuid.UUID:
    departamento_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO departamentos (id, tenant_id, empresa_id, codigo, nome) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Departamento filtro')"
        ),
        {
            "id": departamento_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"D-{uuid.uuid4().hex[:8]}",
        },
    )
    return departamento_id


async def _criar_colaborador_e_vinculo(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    *,
    unidade_id: uuid.UUID,
    departamento_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    sufixo = uuid.uuid4().hex[:10]
    colaborador_id = uuid.uuid4()
    cpf = f"{secrets.randbelow(10**11):011d}"
    await sessao.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": f"MAT-{sufixo}",
            "cpf": cpf,
            "nome": "Colaborador filtro",
        },
    )
    vinculo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, departamento_id, "
            " matricula_esocial, tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :departamento_id, "
            "        :esocial, 'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "departamento_id": departamento_id,
            "esocial": f"ESOC-{sufixo}",
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    return colaborador_id, vinculo_id


@pytest_asyncio.fixture
async def outro_contexto(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> ContextoAlternativo:
    tenant_id = contexto_tratamento.tenant_id
    empresa_id = await _criar_empresa(sessao_tratamento, tenant_id)
    unidade_id = await _criar_unidade(sessao_tratamento, tenant_id, empresa_id)
    departamento_id = await _criar_departamento(sessao_tratamento, tenant_id, empresa_id)
    colaborador_id, vinculo_id = await _criar_colaborador_e_vinculo(
        sessao_tratamento,
        tenant_id,
        empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
    )
    return ContextoAlternativo(
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
    )


async def _criar_equipe(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> uuid.UUID:
    equipe_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO equipes (id, tenant_id, empresa_id, codigo, nome) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Equipe filtro')"
        ),
        {
            "id": equipe_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"EQ-{uuid.uuid4().hex[:8]}",
        },
    )
    return equipe_id


async def _adicionar_membro_equipe(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    equipe_id: uuid.UUID,
    colaborador_id: uuid.UUID,
) -> None:
    await sessao.execute(
        text(
            "INSERT INTO equipe_membros "
            "(id, tenant_id, equipe_id, colaborador_id, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :equipe_id, :colaborador_id, :vigencia_inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "equipe_id": equipe_id,
            "colaborador_id": colaborador_id,
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )


# --------------------------------------------------------------------------
# listar_apuracoes -- erro de intervalo
# --------------------------------------------------------------------------


async def test_listar_apuracoes_ate_anterior_a_de_leva_erro_intervalo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await listar_apuracoes(
            sessao_tratamento, contexto_tratamento.tenant_id, de=_DATA_2, ate=_DATA
        )
    assert excinfo.value.codigo == CODIGO_INTERVALO_INVALIDO


# --------------------------------------------------------------------------
# listar_apuracoes -- filtros de dimensao (contexto vs outro_contexto)
# --------------------------------------------------------------------------


async def test_listar_apuracoes_filtra_por_empresa_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        empresa_id=contexto_tratamento.empresa_id,
    )
    ids = {linha.id for linha in dados}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_apuracoes_filtra_por_unidade_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        unidade_id=contexto_tratamento.unidade_id,
    )
    ids = {linha.id for linha in dados}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_apuracoes_filtra_por_departamento_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    # `contexto_tratamento.vinculo_id` nao tem departamento (NULL) -- so
    # `outro_contexto` tem. Filtrar pelo departamento de `outro_contexto`
    # deve devolver so a apuracao dele.
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        departamento_id=outro_contexto.departamento_id,
    )
    ids = {linha.id for linha in dados}
    assert outro.id in ids
    assert padrao.id not in ids


async def test_listar_apuracoes_filtra_por_colaborador_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        colaborador_id=contexto_tratamento.colaborador_id,
    )
    ids = {linha.id for linha in dados}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_apuracoes_filtra_por_vinculo_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        vinculo_id=contexto_tratamento.vinculo_id,
    )
    ids = {linha.id for linha in dados}
    assert padrao.id in ids
    assert outro.id not in ids


# --------------------------------------------------------------------------
# listar_apuracoes -- status e somente_inconsistentes (mutacao direta da
# linha ja gravada, ja que `apurar_dia` no ramo PONTO-APUR-002 sempre grava
# status='com_ocorrencia'/marcacoes_impares=False)
# --------------------------------------------------------------------------


async def test_listar_apuracoes_filtra_por_status(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    original = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    mutada = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA_2
    )
    assert original.status == "com_ocorrencia"
    linha_mutada = await sessao_tratamento.get(ApuracaoDiaOrm, mutada.id)
    assert linha_mutada is not None
    linha_mutada.status = "apurado"
    await sessao_tratamento.flush()

    dados_apurado, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        status="apurado",
    )
    assert [linha.id for linha in dados_apurado] == [mutada.id]

    dados_com_ocorrencia, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        status="com_ocorrencia",
    )
    assert [linha.id for linha in dados_com_ocorrencia] == [original.id]


async def test_listar_apuracoes_filtra_por_somente_inconsistentes(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    inconsistente = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    consistente = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA_2
    )
    linha_consistente = await sessao_tratamento.get(ApuracaoDiaOrm, consistente.id)
    assert linha_consistente is not None
    linha_consistente.status = "apurado"
    linha_consistente.marcacoes_impares = False
    await sessao_tratamento.flush()

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        somente_inconsistentes=True,
    )
    assert [linha.id for linha in dados] == [inconsistente.id]

    dados_todos, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        somente_inconsistentes=False,
    )
    ids_todos = {linha.id for linha in dados_todos}
    assert {inconsistente.id, consistente.id} <= ids_todos


# --------------------------------------------------------------------------
# listar_apuracoes -- equipe_id (participacao via `equipe_membros`)
# --------------------------------------------------------------------------


async def test_listar_apuracoes_filtra_por_equipe_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    equipe_id = await _criar_equipe(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.empresa_id
    )
    await _adicionar_membro_equipe(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        equipe_id,
        contexto_tratamento.colaborador_id,
    )
    # `outro_contexto.colaborador_id` NAO e membro da equipe.

    membro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    nao_membro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    dados, _ = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA,
        equipe_id=equipe_id,
    )
    ids = {linha.id for linha in dados}
    assert membro.id in ids
    assert nao_membro.id not in ids


# --------------------------------------------------------------------------
# listar_apuracoes -- paginacao (tem_mais + proximo_cursor)
# --------------------------------------------------------------------------


async def test_listar_apuracoes_pagina_com_mais_resultados_gera_cursor(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    primeira = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    segunda = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA_2
    )

    pagina1, paginacao1 = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        limite=1,
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, paginacao2 = await listar_apuracoes(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        de=_DATA,
        ate=_DATA_2,
        limite=1,
        cursor=paginacao1.proximo_cursor,
    )
    assert len(pagina2) == 1
    assert paginacao2.tem_mais is False

    ids_paginados = {pagina1[0].id, pagina2[0].id}
    assert ids_paginados == {primeira.id, segunda.id}


# --------------------------------------------------------------------------
# obter_apuracao -- 404
# --------------------------------------------------------------------------


async def test_obter_apuracao_nao_encontrada_leva_erro_recurso(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await obter_apuracao(sessao_tratamento, uuid.uuid4())
    assert excinfo.value.codigo == CODIGO_RECURSO_NAO_ENCONTRADO


# --------------------------------------------------------------------------
# listar_ocorrencias -- empresa_id / unidade_id (join com `vinculos`)
# --------------------------------------------------------------------------


async def test_listar_ocorrencias_filtra_por_empresa_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        empresa_id=contexto_tratamento.empresa_id,
    )
    ids_apuracao = {ocorrencia.apuracao_dia_id for ocorrencia in ocorrencias}
    assert padrao.id in ids_apuracao
    assert outro.id not in ids_apuracao


async def test_listar_ocorrencias_filtra_por_unidade_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_contexto: ContextoAlternativo,
) -> None:
    padrao = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id, _DATA
    )
    outro = await apurar_dia(
        sessao_tratamento, contexto_tratamento.tenant_id, outro_contexto.vinculo_id, _DATA
    )

    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        unidade_id=contexto_tratamento.unidade_id,
    )
    ids_apuracao = {ocorrencia.apuracao_dia_id for ocorrencia in ocorrencias}
    assert padrao.id in ids_apuracao
    assert outro.id not in ids_apuracao


# --------------------------------------------------------------------------
# listar_ocorrencias -- codigo / severidade / status / de / ate
# --------------------------------------------------------------------------


async def _duas_ocorrencias(
    sessao: AsyncSession, tenant_id: uuid.UUID, vinculo_id: uuid.UUID
) -> tuple[OcorrenciaOrm, OcorrenciaOrm]:
    """Gera 2 ocorrencias reais (via `apurar_dia` em duas datas distintas do
    MESMO vinculo) e devolve as linhas ORM ja carregadas, na ordem (data,
    data_2)."""
    resposta_a = await apurar_dia(sessao, tenant_id, vinculo_id, _DATA)
    resposta_b = await apurar_dia(sessao, tenant_id, vinculo_id, _DATA_2)
    ocorrencia_a = (
        await sessao.execute(
            sa.select(OcorrenciaOrm).where(OcorrenciaOrm.apuracao_dia_id == resposta_a.id)
        )
    ).scalar_one()
    ocorrencia_b = (
        await sessao.execute(
            sa.select(OcorrenciaOrm).where(OcorrenciaOrm.apuracao_dia_id == resposta_b.id)
        )
    ).scalar_one()
    return ocorrencia_a, ocorrencia_b


async def test_listar_ocorrencias_filtra_por_codigo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )
    assert ocorrencia_a.codigo == "sem_marcacao"
    ocorrencia_b.codigo = "falta"
    await sessao_tratamento.flush()

    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, codigo="falta"
    )
    assert [o.id for o in ocorrencias] == [ocorrencia_b.id]


async def test_listar_ocorrencias_filtra_por_severidade(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )
    assert ocorrencia_a.severidade == "critica"
    ocorrencia_b.severidade = "info"
    await sessao_tratamento.flush()

    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, severidade="info"
    )
    assert [o.id for o in ocorrencias] == [ocorrencia_b.id]


async def test_listar_ocorrencias_filtra_por_status(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )
    assert ocorrencia_a.status == "aberta"
    ocorrencia_b.status = "resolvida"
    await sessao_tratamento.flush()

    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, status="resolvida"
    )
    assert [o.id for o in ocorrencias] == [ocorrencia_b.id]


async def test_listar_ocorrencias_filtra_por_de(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )
    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, de=_DATA_2
    )
    ids = {o.id for o in ocorrencias}
    assert ocorrencia_b.id in ids
    assert ocorrencia_a.id not in ids


async def test_listar_ocorrencias_filtra_por_ate(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )
    ocorrencias, _ = await listar_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, ate=_DATA
    )
    ids = {o.id for o in ocorrencias}
    assert ocorrencia_a.id in ids
    assert ocorrencia_b.id not in ids


# --------------------------------------------------------------------------
# listar_ocorrencias -- paginacao (tem_mais + proximo_cursor)
# --------------------------------------------------------------------------


async def test_listar_ocorrencias_pagina_com_mais_resultados_gera_cursor(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ocorrencia_a, ocorrencia_b = await _duas_ocorrencias(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.vinculo_id
    )

    pagina1, paginacao1 = await listar_ocorrencias(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        limite=1,
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, paginacao2 = await listar_ocorrencias(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        limite=1,
        cursor=paginacao1.proximo_cursor,
    )
    assert len(pagina2) == 1
    assert paginacao2.tem_mais is False

    ids_paginados = {pagina1[0].id, pagina2[0].id}
    assert ids_paginados == {ocorrencia_a.id, ocorrencia_b.id}
