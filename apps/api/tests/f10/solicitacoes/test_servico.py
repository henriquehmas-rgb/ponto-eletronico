"""Testes de `app.workflow.solicitacoes.servico` (T2, A1)."""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.solicitacoes import eventos, paginacao, servico
from tests.f10.conftest import ContextoF10


@pytest.fixture(autouse=True)
def _barramento_limpo() -> Iterator[None]:
    eventos.limpar_barramento()
    yield
    eventos.limpar_barramento()


def _corpo_ajuste_ponto(contexto: ContextoF10, *, dias_atras: int = 1) -> esquemas.SolicitacaoCriar:
    return esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto.tipo_solicitacao_id),
            "colaboradorId": str(contexto.colaborador_id),
            "dataReferencia": (dt.date.today() - dt.timedelta(days=dias_atras)).isoformat(),
            "descricao": "Esqueci de bater o ponto da saida.",
        }
    )


async def test_criar_solicitacao_resolve_vinculo_e_publica_ajuste_solicitado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = _corpo_ajuste_ponto(contexto_f10)
    criada = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    assert criada.vinculo_id == contexto_f10.vinculo_id
    assert criada.status == "em_aprovacao"
    assert criada.etapa_atual == 1
    assert criada.protocolo.startswith(f"{dt.date.today().year}-")

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.solicitado"]
    assert len(publicados) == 1
    assert publicados[0]["dados"]["solicitacaoId"] == str(criada.id)
    assert publicados[0]["dados"]["tipoSolicitacaoCodigo"] == contexto_f10.tipo_solicitacao_codigo


async def test_criar_solicitacao_categoria_fora_de_ajuste_ponto_nao_publica_evento(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_troca = esquemas.TipoSolicitacaoCriar.model_validate(
        {
            "codigo": f"troca-{contexto_f10.tenant_id.hex[:6]}",
            "nome": "Troca de escala de teste",
            "categoria": "troca_escala",
            "etapas": {"etapas": [{"papel": "gestor"}]},
        }
    )
    from app.workflow.solicitacoes import tipos as tipos_servico

    tipo_criado = await tipos_servico.criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, tipo_troca, usuario_id=None
    )

    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_criado.id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Troca de escala com um colega.",
        }
    )
    await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    assert eventos.BARRAMENTO_INTERNO == []


async def test_protocolo_e_sequencial_por_tenant(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    primeira = await servico.criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        _corpo_ajuste_ponto(contexto_f10, dias_atras=1),
        usuario_id=None,
    )
    segunda = await servico.criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        _corpo_ajuste_ponto(contexto_f10, dias_atras=2),
        usuario_id=None,
    )
    assert primeira.protocolo != segunda.protocolo
    numero_primeira = int(primeira.protocolo.split("-")[1])
    numero_segunda = int(segunda.protocolo.split("-")[1])
    assert numero_segunda == numero_primeira + 1


async def test_criar_solicitacao_retroativo_alem_do_limite_e_recusado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    # tipo de exemplo da fixture tem permite_retroativo_dias=30.
    corpo = _corpo_ajuste_ponto(contexto_f10, dias_atras=45)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-007"


async def test_criar_solicitacao_sem_nenhuma_data_e_recusado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "descricao": "Sem data nenhuma.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_cancelar_solicitacao_e_idempotente_negativo(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    criada = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, _corpo_ajuste_ponto(contexto_f10), usuario_id=None
    )
    cancelamento = esquemas.CancelamentoRequisicao.model_validate({"motivo": "Nao preciso mais."})

    cancelada = await servico.cancelar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, criada.id, cancelamento, usuario_id=None
    )
    assert cancelada.status == "cancelada"

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.cancelar_solicitacao(
            sessao_f10, contexto_f10.tenant_id, criada.id, cancelamento, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


# =============================================================================
# T15/T16 -- fecha o gap de cobertura de `app.workflow.solicitacoes.servico`
# (>=90% exigido pelo criterio de aceite 12 do PCF F10). Cada teste abaixo
# mira uma linha "Missing" real, descoberta rodando
# `pytest --cov=app.workflow.solicitacoes --cov-report=term-missing` --
# nunca teste generico solto.
# =============================================================================


async def _criar_tipo_solicitacao_bruto(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    categoria: str,
    sufixo: str,
    etapas: str = '[{"etapa": 1, "papel": "gestor"}]',
    tipo_tratamento_id: uuid.UUID | None = None,
    ativo: bool = True,
) -> uuid.UUID:
    """Mesmo padrao de `tests/f10/solicitacoes/test_materializacao.py::
    _criar_tipo_solicitacao` -- copia local (nunca importa helper privado
    de outro modulo de teste) para inserir uma linha de catalogo com
    combinacoes que `criarTipoSolicitacao` (T2) nao aceita compor sozinho
    (etapas vazio, `ativo=FALSE`)."""
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, exige_justificativa, "
            " tipo_tratamento_id, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, :etapas, TRUE, "
            "        :tipo_tratamento_id, :ativo)"
        ),
        {
            "id": tipo_id,
            "tenant_id": tenant_id,
            "codigo": f"TS-{sufixo}",
            "nome": f"Tipo de solicitacao {sufixo}",
            "categoria": categoria,
            "etapas": etapas,
            "tipo_tratamento_id": tipo_tratamento_id,
            "ativo": ativo,
        },
    )
    return tipo_id


async def _criar_colaborador_com_vinculo(
    sessao: AsyncSession, contexto: ContextoF10
) -> tuple[uuid.UUID, uuid.UUID]:
    """Um SEGUNDO colaborador (com vinculo `ativo` proprio), fora do
    semeado por `contexto_f10` -- usado para provar que `criarSolicitacao`
    recusa um `vinculoId` explicito que nao pertence ao `colaboradorId`
    informado."""
    colaborador_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO colaboradores (id, tenant_id, empresa_id, matricula, cpf, "
            "nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, 'Outro Colaborador', 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "matricula": f"OUTRO-{uuid.uuid4().hex[:8]}",
            "cpf": f"{uuid.uuid4().int % 10**11:011d}",
        },
    )
    vinculo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, principal, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": contexto.empresa_id,
            "unidade_id": contexto.unidade_id,
            "esocial": f"ESOC-OUTRO-{uuid.uuid4().hex[:8]}",
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    return colaborador_id, vinculo_id


def test_valor_extrai_value_de_enum_e_devolve_bruto_caso_contrario() -> None:
    """`_valor` (linha 175) nunca e chamado hoje dentro deste modulo -- so
    existe por simetria com `app.workflow.aprovacoes.servico._valor`/
    `app.workflow.aprovacoes.delegacoes._valor`. Testado diretamente."""

    class _EnumFalso:
        value = "bruto-convertido"

    assert servico._valor(_EnumFalso()) == "bruto-convertido"
    assert servico._valor("texto-puro") == "texto-puro"


async def test_resolver_vinculo_cai_no_fallback_quando_data_e_anterior_ao_inicio(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Linha 120 -- o vinculo da fixture comeca em 2020-01-01 sem fim de
    vigencia, entao toda data usada pelos demais testes cai DENTRO da
    vigencia e a primeira consulta (vinculo vigente NA data) sempre acha
    algo. Pedir uma data ANTERIOR ao inicio forca a primeira consulta a nao
    achar nada, caindo no fallback (vinculo `ativo` mais recente, sem
    filtro de data)."""
    resolvido = await servico._resolver_vinculo(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.colaborador_id, dt.date(2019, 1, 1)
    )
    assert resolvido is not None
    assert resolvido.id == contexto_f10.vinculo_id


async def test_obter_colaborador_nao_encontrado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_colaborador(sessao_f10, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_obter_solicitacao_nao_encontrada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_solicitacao(sessao_f10, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_listar_aprovacoes_da_solicitacao_devolve_etapas_em_ordem(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    criada = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, _corpo_ajuste_ponto(contexto_f10), usuario_id=None
    )
    etapas = await servico.listar_aprovacoes_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, criada.id
    )
    assert [e.etapa for e in etapas] == [1]
    assert etapas[0].solicitacao_id == criada.id


async def test_criar_solicitacao_recusa_data_fim_anterior_a_data_inicio(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataInicio": dt.date.today().isoformat(),
            "dataFim": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "descricao": "Intervalo invertido de proposito.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-007"


async def test_criar_solicitacao_recusa_descricao_vazia(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "   ",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_recusa_tipo_inativo(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_id = await _criar_tipo_solicitacao_bruto(
        sessao_f10, contexto_f10.tenant_id, categoria="troca_escala", sufixo="inativo", ativo=False
    )
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Tipo inativo.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_recusa_tipo_sem_cadeia_de_aprovacao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_id = await _criar_tipo_solicitacao_bruto(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="troca_escala",
        sufixo="semcadeia",
        etapas="[]",
    )
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Sem cadeia de aprovacao.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_afastamento_exige_tipo_afastamento_id_no_payload(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_tratamento_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Afastamento retroativo de teste', 'afastamento', "
            "        TRUE, TRUE)"
        ),
        {
            "id": tipo_tratamento_id,
            "tenant_id": contexto_f10.tenant_id,
            "codigo": f"TT-AF-{uuid.uuid4().hex[:8]}",
        },
    )
    tipo_id = await _criar_tipo_solicitacao_bruto(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="afastamento",
        sufixo="afastsempayload",
        tipo_tratamento_id=tipo_tratamento_id,
    )
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Afastamento sem o payload obrigatorio.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_aceita_vinculo_explicito_do_proprio_colaborador(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "vinculoId": str(contexto_f10.vinculo_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Vinculo explicito valido.",
        }
    )
    criada = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None
    )
    assert criada.vinculo_id == contexto_f10.vinculo_id


async def test_criar_solicitacao_recusa_vinculo_explicito_inexistente(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "vinculoId": str(uuid.uuid4()),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Vinculo explicito que nao existe.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_solicitacao_recusa_vinculo_explicito_de_outro_colaborador(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    _, vinculo_de_outro_id = await _criar_colaborador_com_vinculo(sessao_f10, contexto_f10)
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "vinculoId": str(vinculo_de_outro_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Vinculo de outro colaborador.",
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_traduz_integrity_error_no_flush_da_solicitacao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linhas 279-280 sao rede de seguranca: a numeracao do protocolo ja e
    serializada por `pg_advisory_xact_lock` (`_proximo_protocolo`), entao
    uma colisao real de `uq_solicitacoes_protocolo` nesse INSERT especifico
    e praticamente irreproduzivel num processo de teste sequencial --
    forcamos o `IntegrityError` via monkeypatch no `flush()` para provar
    que o except realmente traduz o erro (mesmo padrao de injecao de falha
    usado por `tests/f4/tratamento/test_erros_bd.py` para os ramos de
    `_nome_constraint` que tambem nao tem contrapartida real acessivel)."""

    async def _flush_falha() -> None:
        raise IntegrityError("INSERT INTO solicitacoes", {}, Exception("erro sintetico de teste"))

    monkeypatch.setattr(sessao_f10, "flush", _flush_falha)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(
            sessao_f10, contexto_f10.tenant_id, _corpo_ajuste_ponto(contexto_f10), usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_solicitacao_traduz_integrity_error_no_flush_da_primeira_etapa(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesma rede de seguranca do teste acima, agora no SEGUNDO `flush()` de
    `criarSolicitacao` (insercao da primeira `Aprovacao` da cadeia) --
    linhas 302-303. O primeiro `flush()` real precisa ter sucesso (a
    `Solicitacao` precisa existir de verdade para o teste fazer sentido);
    o monkeypatch so falha a partir da segunda chamada."""
    original_flush = sessao_f10.flush
    chamadas = {"n": 0}

    async def _flush_falha_na_segunda_chamada() -> None:
        chamadas["n"] += 1
        if chamadas["n"] >= 2:
            raise IntegrityError("INSERT INTO aprovacoes", {}, Exception("erro sintetico de teste"))
        await original_flush()

    monkeypatch.setattr(sessao_f10, "flush", _flush_falha_na_segunda_chamada)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_solicitacao(
            sessao_f10, contexto_f10.tenant_id, _corpo_ajuste_ponto(contexto_f10), usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_listar_solicitacoes_aplica_todos_os_filtros_e_pagina(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Nenhum teste anterior chamava `listar_solicitacoes` -- cobre TODAS as
    clausulas de filtro (linhas 356-406) e o round-trip completo de
    paginacao por cursor (pagina 1 com `temMais=True`, pagina 2 usando o
    `proximoCursor` devolvido), exercitando de quebra
    `app.workflow.solicitacoes.paginacao.codificar_cursor`/
    `decodificar_cursor`/o ramo `if cursor:` de `executar_pagina`."""
    usuario_solicitante = contexto_f10.colaborador_usuario_id

    primeira = await servico.criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.SolicitacaoCriar.model_validate(
            {
                "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
                "colaboradorId": str(contexto_f10.colaborador_id),
                "dataReferencia": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
                "descricao": "Primeira solicitacao de teste da listagem.",
            }
        ),
        usuario_id=usuario_solicitante,
    )

    tipo_abono_id = await _criar_tipo_solicitacao_bruto(
        sessao_f10, contexto_f10.tenant_id, categoria="abono", sufixo="listagem"
    )
    segunda = await servico.criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.SolicitacaoCriar.model_validate(
            {
                "tipoSolicitacaoId": str(tipo_abono_id),
                "colaboradorId": str(contexto_f10.colaborador_id),
                "dataReferencia": (dt.date.today() - dt.timedelta(days=2)).isoformat(),
                "descricao": "Segunda solicitacao de teste da listagem.",
            }
        ),
        usuario_id=None,
    )

    outro_colaborador_id, _ = await _criar_colaborador_com_vinculo(sessao_f10, contexto_f10)
    terceira = await servico.criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.SolicitacaoCriar.model_validate(
            {
                "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
                "colaboradorId": str(outro_colaborador_id),
                "dataReferencia": (dt.date.today() - dt.timedelta(days=3)).isoformat(),
                "descricao": "Terceira solicitacao, outro colaborador.",
            }
        ),
        usuario_id=None,
    )

    todas_ids = {primeira.id, segunda.id, terceira.id}

    por_colaborador, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, colaborador_id=contexto_f10.colaborador_id
    )
    assert {s.id for s in por_colaborador} == {primeira.id, segunda.id}

    por_empresa, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, empresa_id=contexto_f10.empresa_id
    )
    assert {s.id for s in por_empresa} >= todas_ids

    por_tipo, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, tipo_solicitacao_id=tipo_abono_id
    )
    assert {s.id for s in por_tipo} == {segunda.id}

    por_categoria, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, categoria="abono"
    )
    assert {s.id for s in por_categoria} == {segunda.id}

    por_status, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, status="em_aprovacao"
    )
    assert {s.id for s in por_status} >= todas_ids

    minhas, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, minhas=True, usuario_atual_id=usuario_solicitante
    )
    assert {s.id for s in minhas} == {primeira.id}

    por_intervalo, _ = await servico.listar_solicitacoes(
        sessao_f10,
        contexto_f10.tenant_id,
        de=dt.date.today() - dt.timedelta(days=2),
        ate=dt.date.today() - dt.timedelta(days=1),
    )
    assert {s.id for s in por_intervalo} == {primeira.id, segunda.id}

    pagina1, paginacao1 = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, limite=1
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, _ = await servico.listar_solicitacoes(
        sessao_f10, contexto_f10.tenant_id, limite=1, cursor=paginacao1.proximo_cursor
    )
    assert len(pagina2) == 1
    assert pagina2[0].id != pagina1[0].id


async def test_cancelar_solicitacao_traduz_integrity_error_no_flush(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10, monkeypatch: pytest.MonkeyPatch
) -> None:
    criada = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, _corpo_ajuste_ponto(contexto_f10), usuario_id=None
    )

    async def _flush_falha() -> None:
        raise IntegrityError("UPDATE solicitacoes", {}, Exception("erro sintetico de teste"))

    monkeypatch.setattr(sessao_f10, "flush", _flush_falha)

    cancelamento = esquemas.CancelamentoRequisicao.model_validate({"motivo": "Teste de falha."})
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.cancelar_solicitacao(
            sessao_f10, contexto_f10.tenant_id, criada.id, cancelamento, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# -----------------------------------------------------------------------
# `app.workflow.solicitacoes.paginacao` -- copia propria de paginacao por
# cursor (mesma forma de `app.workflow.aprovacoes.paginacao`); nenhum teste
# desta fase exercitava os ramos de erro/explicitos ate agora.
# -----------------------------------------------------------------------


def test_paginacao_normalizar_limite_aceita_valor_explicito_e_recusa_fora_da_faixa() -> None:
    assert paginacao.normalizar_limite(10) == 10
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.normalizar_limite(0)
    assert excinfo.value.codigo == "PONTO-VAL-005"
    with pytest.raises(ErroDeAplicacao):
        paginacao.normalizar_limite(paginacao.LIMITE_MAXIMO + 1)


def test_paginacao_interpretar_ordenar_aceita_campo_e_direcao_explicitos() -> None:
    ordenacao = paginacao.interpretar_ordenar(
        "criadoEm:asc", campos_aceitos=frozenset({"criadoEm", "prazoEm"}), padrao="criadoEm"
    )
    assert ordenacao.campo == "criadoEm"
    assert ordenacao.direcao == "asc"


def test_paginacao_interpretar_ordenar_recusa_direcao_invalida() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.interpretar_ordenar(
            "criadoEm:lateral", campos_aceitos=frozenset({"criadoEm"}), padrao="criadoEm"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_paginacao_interpretar_ordenar_recusa_campo_invalido() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.interpretar_ordenar(
            "campoQueNaoExiste:asc", campos_aceitos=frozenset({"criadoEm"}), padrao="criadoEm"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_paginacao_decodificar_cursor_recusa_base64_ilegivel() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor("###nao-e-base64-valido###", ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_paginacao_decodificar_cursor_recusa_ordenacao_diferente() -> None:
    emitida_para = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    cursor = paginacao.codificar_cursor(emitida_para, "2026-01-01T00:00:00", uuid.uuid4())

    decodificada_para = paginacao.Ordenacao(campo="prazoEm", direcao="desc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor(cursor, ordenacao=decodificada_para)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_paginacao_decodificar_cursor_recusa_payload_sem_id() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    payload = {"o": "criadoEm", "d": "desc", "v": "2026-01-01T00:00:00"}
    bruto = json.dumps(payload).encode("utf-8")
    cursor = base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor(cursor, ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_paginacao_serializar_datetime_date_uuid_e_valor_bruto() -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    assert paginacao._serializar(agora) == agora.isoformat()
    hoje = dt.date.today()
    assert paginacao._serializar(hoje) == hoje.isoformat()
    id_ = uuid.uuid4()
    assert paginacao._serializar(id_) == str(id_)
    assert paginacao._serializar("valor-puro") == "valor-puro"
