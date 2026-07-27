"""Fecha o gap de cobertura de `app.apuracao.tratamento.servico` (F4, §7 do
PCF exige >=90% de `app.apuracao`) NAO coberto por `test_servico.py`
(existente, ownership de A3, nao editado por este arquivo): os caminhos de
erro individuais de `criarTratamento`/`atualizarTratamento`/
`cancelarTratamento`, o 404 de `obterTratamento`, e os filtros opcionais de
`listarTratamentos`/`listarTiposTratamento`.

Reusa a mesma fixture minima de `tests/f4/tratamento/conftest.py`
(`sessao_tratamento`/`contexto_tratamento`) que `test_servico.py` ja usa.
Para os filtros que precisam de uma segunda empresa/colaborador/vinculo
genuinamente diferente, este modulo semeia um segundo contexto completo
(`outro_vinculo`) no MESMO tenant, via `INSERT` direto -- mesmo padrao que o
proprio `conftest.py` e `test_servico.py` (`periodos`/`fechamentos`) ja usam.
Para o caminho de marcacao valida (`marcacaoId` apontando para uma marcacao
real), semeia um REP-P e insere uma marcacao minima, no mesmo formato que
`tests/f4/propriedade/conftest.py::inserir_marcacao` ja usa (copia propria,
nunca importada -- ownership de A4 e' o outro conftest).
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.tratamento.conftest import ContextoTratamento

_DATA_REFERENCIA = dt.date(2026, 7, 10)


def _corpo_criar(
    ctx: ContextoTratamento,
    *,
    data_referencia: dt.date = _DATA_REFERENCIA,
    motivo: str = "Atestado medico",
    colaborador_id: uuid.UUID | None = None,
    vinculo_id: uuid.UUID | None = None,
    tipo_tratamento_id: uuid.UUID | None = None,
    **extras: object,
) -> esquemas.TratamentoCriar:
    return esquemas.TratamentoCriar(
        colaborador_id=colaborador_id if colaborador_id is not None else ctx.colaborador_id,
        vinculo_id=vinculo_id if vinculo_id is not None else ctx.vinculo_id,
        tipo_tratamento_id=(
            tipo_tratamento_id if tipo_tratamento_id is not None else ctx.tipo_tratamento_id
        ),
        data_referencia=data_referencia,
        motivo=motivo,
        **extras,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# Segundo vinculo (empresa/colaborador diferentes) no MESMO tenant, para os
# filtros de `listarTratamentos` que precisam de uma dimensao genuinamente
# diferente (empresa_id/colaborador_id/vinculo_id).
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutroVinculo:
    empresa_id: uuid.UUID
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


async def _criar_colaborador_e_vinculo(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
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
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "esocial": f"ESOC-{sufixo}",
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    return colaborador_id, vinculo_id


@pytest_asyncio.fixture
async def outro_vinculo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> OutroVinculo:
    tenant_id = contexto_tratamento.tenant_id
    empresa_id = await _criar_empresa(sessao_tratamento, tenant_id)
    colaborador_id, vinculo_id = await _criar_colaborador_e_vinculo(
        sessao_tratamento, tenant_id, empresa_id
    )
    return OutroVinculo(empresa_id=empresa_id, colaborador_id=colaborador_id, vinculo_id=vinculo_id)


async def _criar_tipo_tratamento(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    categoria: str = "justificativa",
    ativo: bool = True,
) -> uuid.UUID:
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Tipo filtro', :categoria, TRUE, :ativo)"
        ),
        {
            "id": tipo_id,
            "tenant_id": tenant_id,
            "codigo": f"TIPO-{uuid.uuid4().hex[:8]}",
            "categoria": categoria,
            "ativo": ativo,
        },
    )
    return tipo_id


async def _criar_rep_p(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> uuid.UUID:
    rep_p_id = uuid.uuid4()
    sufixo = uuid.uuid4().hex[:10]
    cnpj_dev = f"{secrets.randbelow(10**14):014d}"
    cnpj_emp = f"{secrets.randbelow(10**14):014d}"
    await sessao.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        :cnpj_dev, 'SEEG Servicos de TI', :cnpj_emp, 'Empresa de Teste', "
            "        '1.0.0', :data_inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_dev": cnpj_dev,
            "cnpj_emp": cnpj_emp,
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    return rep_p_id


async def _inserir_marcacao(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rep_p_id: uuid.UUID,
    empresa_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    cpf: str,
    datahora: dt.datetime,
    nsr: int,
) -> uuid.UUID:
    """Insere uma marcacao MINIMA e valida (satisfaz todo `CHECK`/`NOT NULL`
    da tabela) diretamente via SQL -- mesmo padrao de
    `tests/f4/propriedade/conftest.py::inserir_marcacao` (copia propria,
    nunca importada dali)."""
    marcacao_id = uuid.uuid4()
    hash_sintetico = secrets.token_hex(32)
    await sessao.execute(
        text(
            "INSERT INTO marcacoes "
            "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, vinculo_id, nsr, "
            " cpf, datahora_marcacao, fuso_horario, canal, crc16, hash_registro) "
            "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :vinculo_id, "
            "        :nsr, :cpf, :datahora, 'America/Sao_Paulo', 'terminal', :crc16, :hash)"
        ),
        {
            "id": marcacao_id,
            "tenant_id": tenant_id,
            "rep_p_id": rep_p_id,
            "empresa_id": empresa_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "nsr": nsr,
            "cpf": cpf,
            "datahora": datahora,
            "crc16": nsr % 65536,
            "hash": hash_sintetico,
        },
    )
    return marcacao_id


# --------------------------------------------------------------------------
# criarTratamento -- caminhos de erro individuais
# --------------------------------------------------------------------------


async def test_criar_tratamento_vinculo_inexistente_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, vinculo_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_tratamento_marcacao_inexistente_e_recusada(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, marcacao_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_tratamento_com_marcacao_real_deriva_datahora(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    rep_p_id = await _criar_rep_p(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.empresa_id
    )
    datahora = dt.datetime(2026, 7, 10, 8, 0, tzinfo=dt.UTC)
    marcacao_id = await _inserir_marcacao(
        sessao_tratamento,
        tenant_id=contexto_tratamento.tenant_id,
        rep_p_id=rep_p_id,
        empresa_id=contexto_tratamento.empresa_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        cpf="12345678901",
        datahora=datahora,
        nsr=1,
    )

    corpo = _corpo_criar(contexto_tratamento, marcacao_id=marcacao_id)
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    assert tratamento.marcacao_id == marcacao_id
    assert tratamento.marcacao_datahora == datahora


async def test_criar_tratamento_vinculo_de_outro_colaborador_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, colaborador_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_tratamento_tipo_tratamento_inexistente_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, tipo_tratamento_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_tratamento_grava_sentido_origem_status_informados(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(
        contexto_tratamento,
        sentido=esquemas.Sentido.entrada,
        origem=esquemas.Origem3.rh,
        status=esquemas.Status24.rascunho,
    )
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    assert tratamento.sentido == "entrada"
    assert tratamento.origem == "rh"
    assert tratamento.status == "rascunho"


async def test_criar_tratamento_com_erro_de_integridade_traduz_codigo_padrao(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    """`tipoAfastamentoId` nao e validado pela aplicacao antes do `INSERT`
    (so `tipoTratamentoId` e); um UUID que nao existe em `tipos_afastamento`
    viola a FK correspondente no flush, sem nome mapeado em
    `CODIGOS_POR_CONSTRAINT` -- exercita o fallback `padrao` de
    `traduzir_integridade` (as linhas 171-172 de `servico.py`)."""
    corpo = _corpo_criar(contexto_tratamento, tipo_afastamento_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# --------------------------------------------------------------------------
# obterTratamento -- 404
# --------------------------------------------------------------------------


async def test_obter_tratamento_nao_encontrado_leva_erro_recurso(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_tratamento(sessao_tratamento, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


# --------------------------------------------------------------------------
# atualizarTratamento -- caminho de sucesso completo + erro de motivo vazio
# --------------------------------------------------------------------------


async def test_atualizar_tratamento_sucesso_atualiza_status_marcacao_sentido_origem_motivo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    assert tratamento.status == "pendente"

    rep_p_id = await _criar_rep_p(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.empresa_id
    )
    datahora = dt.datetime(2026, 7, 10, 9, 0, tzinfo=dt.UTC)
    marcacao_id = await _inserir_marcacao(
        sessao_tratamento,
        tenant_id=contexto_tratamento.tenant_id,
        rep_p_id=rep_p_id,
        empresa_id=contexto_tratamento.empresa_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        cpf="98765432100",
        datahora=datahora,
        nsr=1,
    )

    atualizacao = esquemas.TratamentoAtualizar(
        status=esquemas.Status24.pendente,
        marcacao_id=marcacao_id,
        sentido=esquemas.Sentido.saida,
        origem=esquemas.Origem3.gestor,
        motivo="Motivo atualizado",
    )
    atualizado = await servico.atualizar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        tratamento.id,
        atualizacao,
        usuario_id=None,
    )
    assert atualizado.status == "pendente"
    assert atualizado.marcacao_id == marcacao_id
    assert atualizado.marcacao_datahora == datahora
    assert atualizado.sentido == "saida"
    assert atualizado.origem == "gestor"
    assert atualizado.motivo == "Motivo atualizado"


async def test_atualizar_tratamento_motivo_vazio_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    atualizacao = esquemas.TratamentoAtualizar(motivo="   ")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            atualizacao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_atualizar_tratamento_com_erro_de_integridade_traduz_codigo_padrao(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    """Mesmo achado de `criarTratamento` (`tipoAfastamentoId` nao e validado
    pela aplicacao antes do `UPDATE`): um UUID inexistente viola a FK no
    flush de `atualizar_tratamento`, sem nome mapeado em
    `CODIGOS_POR_CONSTRAINT` -- exercita o fallback `padrao` nas linhas
    233-234 de `servico.py`."""
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    atualizacao = esquemas.TratamentoAtualizar(tipo_afastamento_id=uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            atualizacao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# --------------------------------------------------------------------------
# cancelarTratamento -- erro de integridade traduzido pelo catalogo
# --------------------------------------------------------------------------


async def test_cancelar_tratamento_com_erro_de_integridade_traduz_codigo_da_constraint(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    """Corrompe `sentido` no objeto ja carregado (mutacao ORM direta, sem
    flush) para que o UPDATE que `cancelar_tratamento` dispara ao gravar
    `status='cancelado'` tambem inclua essa coluna suja e estoure
    `tratamentos_sentido_check` -- prova as linhas 270-271 de `servico.py` E
    que `traduzir_integridade` mapeia o nome da constraint para o codigo
    especifico (`PONTO-VAL-001`), nao so o `padrao`."""
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    tratamento.sentido = "valor-invalido-forca-check"

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.cancelar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, tratamento.id, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# --------------------------------------------------------------------------
# listarTratamentos -- filtros individuais
# --------------------------------------------------------------------------


async def test_listar_tratamentos_filtra_por_empresa_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_vinculo: OutroVinculo,
) -> None:
    padrao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    tipo_outro = await _criar_tipo_tratamento(sessao_tratamento, contexto_tratamento.tenant_id)
    outro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento,
            colaborador_id=outro_vinculo.colaborador_id,
            vinculo_id=outro_vinculo.vinculo_id,
            tipo_tratamento_id=tipo_outro,
        ),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, empresa_id=contexto_tratamento.empresa_id
    )
    ids = {linha.id for linha in linhas}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_tratamentos_filtra_por_colaborador_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_vinculo: OutroVinculo,
) -> None:
    padrao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    tipo_outro = await _criar_tipo_tratamento(sessao_tratamento, contexto_tratamento.tenant_id)
    outro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento,
            colaborador_id=outro_vinculo.colaborador_id,
            vinculo_id=outro_vinculo.vinculo_id,
            tipo_tratamento_id=tipo_outro,
        ),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        colaborador_id=contexto_tratamento.colaborador_id,
    )
    ids = {linha.id for linha in linhas}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_tratamentos_filtra_por_vinculo_id(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    outro_vinculo: OutroVinculo,
) -> None:
    padrao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento),
        usuario_id=None,
    )
    tipo_outro = await _criar_tipo_tratamento(sessao_tratamento, contexto_tratamento.tenant_id)
    outro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento,
            colaborador_id=outro_vinculo.colaborador_id,
            vinculo_id=outro_vinculo.vinculo_id,
            tipo_tratamento_id=tipo_outro,
        ),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, vinculo_id=contexto_tratamento.vinculo_id
    )
    ids = {linha.id for linha in linhas}
    assert padrao.id in ids
    assert outro.id not in ids


async def test_listar_tratamentos_filtra_por_tipo_tratamento_id(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    padrao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 1)),
        usuario_id=None,
    )
    outro_tipo_id = await _criar_tipo_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, categoria="abono"
    )
    outro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento,
            data_referencia=dt.date(2026, 7, 2),
            tipo_tratamento_id=outro_tipo_id,
        ),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, tipo_tratamento_id=outro_tipo_id
    )
    ids = {linha.id for linha in linhas}
    assert outro.id in ids
    assert padrao.id not in ids


async def test_listar_tratamentos_filtra_por_origem(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    padrao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 1)),
        usuario_id=None,
    )
    assert padrao.origem == "gestor"
    outro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento,
            data_referencia=dt.date(2026, 7, 2),
            origem=esquemas.Origem3.rh,
        ),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, origem="rh"
    )
    ids = {linha.id for linha in linhas}
    assert outro.id in ids
    assert padrao.id not in ids


async def test_listar_tratamentos_filtra_por_de_e_ate(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    antigo = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 1)),
        usuario_id=None,
    )
    recente = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 20)),
        usuario_id=None,
    )

    linhas_de, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, de=dt.date(2026, 7, 10)
    )
    ids_de = {linha.id for linha in linhas_de}
    assert recente.id in ids_de
    assert antigo.id not in ids_de

    linhas_ate, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, ate=dt.date(2026, 7, 10)
    )
    ids_ate = {linha.id for linha in linhas_ate}
    assert antigo.id in ids_ate
    assert recente.id not in ids_ate


async def test_listar_tratamentos_filtra_por_marcacao_id(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    rep_p_id = await _criar_rep_p(
        sessao_tratamento, contexto_tratamento.tenant_id, contexto_tratamento.empresa_id
    )
    marcacao_id = await _inserir_marcacao(
        sessao_tratamento,
        tenant_id=contexto_tratamento.tenant_id,
        rep_p_id=rep_p_id,
        empresa_id=contexto_tratamento.empresa_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        cpf="11122233344",
        datahora=dt.datetime(2026, 7, 10, 8, 0, tzinfo=dt.UTC),
        nsr=1,
    )
    com_marcacao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(
            contexto_tratamento, data_referencia=dt.date(2026, 7, 1), marcacao_id=marcacao_id
        ),
        usuario_id=None,
    )
    sem_marcacao = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 2)),
        usuario_id=None,
    )

    linhas, _ = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, marcacao_id=marcacao_id
    )
    ids = {linha.id for linha in linhas}
    assert com_marcacao.id in ids
    assert sem_marcacao.id not in ids


async def test_listar_tratamentos_pagina_com_mais_resultados_gera_cursor(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    primeiro = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 1)),
        usuario_id=None,
    )
    segundo = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 2)),
        usuario_id=None,
    )

    pagina1, paginacao1 = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, limite=1
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, paginacao2 = await servico.listar_tratamentos(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        limite=1,
        cursor=paginacao1.proximo_cursor,
    )
    assert len(pagina2) == 1
    assert paginacao2.tem_mais is False

    ids_paginados = {pagina1[0].id, pagina2[0].id}
    assert ids_paginados == {primeiro.id, segundo.id}


# --------------------------------------------------------------------------
# listarTiposTratamento -- filtros individuais + paginacao
# --------------------------------------------------------------------------


async def test_listar_tipos_tratamento_filtra_por_categoria(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    outro_tipo_id = await _criar_tipo_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, categoria="abono"
    )

    linhas, _ = await servico.listar_tipos_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, categoria="abono"
    )
    ids = {linha.id for linha in linhas}
    assert outro_tipo_id in ids
    assert contexto_tratamento.tipo_tratamento_id not in ids


async def test_listar_tipos_tratamento_filtra_por_ativo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    inativo_id = await _criar_tipo_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, ativo=False
    )

    linhas_ativos, _ = await servico.listar_tipos_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, ativo=True
    )
    ids_ativos = {linha.id for linha in linhas_ativos}
    assert contexto_tratamento.tipo_tratamento_id in ids_ativos
    assert inativo_id not in ids_ativos

    linhas_inativos, _ = await servico.listar_tipos_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, ativo=False
    )
    ids_inativos = {linha.id for linha in linhas_inativos}
    assert inativo_id in ids_inativos
    assert contexto_tratamento.tipo_tratamento_id not in ids_inativos


async def test_listar_tipos_tratamento_pagina_com_mais_resultados_gera_cursor(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    outro_tipo_id = await _criar_tipo_tratamento(sessao_tratamento, contexto_tratamento.tenant_id)

    pagina1, paginacao1 = await servico.listar_tipos_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, limite=1
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, paginacao2 = await servico.listar_tipos_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        limite=1,
        cursor=paginacao1.proximo_cursor,
    )
    assert len(pagina2) == 1
    assert paginacao2.tem_mais is False

    ids_paginados = {pagina1[0].id, pagina2[0].id}
    assert ids_paginados == {contexto_tratamento.tipo_tratamento_id, outro_tipo_id}
