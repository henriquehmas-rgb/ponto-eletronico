"""Testes de `app.workflow.solicitacoes.afastamentos.materializar_ferias_ou_folga`
(F10, T12, agente A4).

Exercita a função DIRETAMENTE (não via `criarSolicitacao`/`decidirAprovacao`
HTTP, que é T3/T4 de A1 e é o alvo do e2e de T15) -- a fixture compartilhada
da fase (`tests/f10/conftest.py::contexto_f10`, ownership de A1) já entrega
tenant/empresa/unidade/colaborador/vínculo, uma jornada simples fixa (útil
seg-sex, 480 min/dia) e um `TipoAfastamento` categoria `ferias`; este módulo
só acrescenta, localmente (nunca editando o arquivo compartilhado), o que
falta para os casos `ferias`/`folga`: um `TipoSolicitacao`/`Solicitacao` de
cada categoria e, para `folga`, uma `bh_politica`/`bh_conta` com saldo
creditado (mesmo padrão de `tests/f4/banco_horas/conftest.py`/
`test_quitacoes.py`, que credita via `app.apuracao.banco_horas.lancamentos.
lancar` antes de testar o débito).

Prova, ponto a ponto, o "pronto quando" de T12 (PCF §6):

* `ferias` aprovada cria `Afastamento` com `status='aprovado'` e o resolvedor
  de F3 (`resolver_jornada_do_dia`, chamado só para leitura, nunca editado)
  lê esse afastamento como insumo normal a partir da data de início.
* Sobreposição de férias aprovadas do mesmo colaborador é recusada
  (`ex_afastamentos_sobreposicao`, traduzida para `PONTO-VAL-010`).
* `folga` aprovada debita o saldo de banco de horas correto, comparando
  `bh_contas.saldo_atual_minutos` antes/depois.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid

import pytest
from ponto_contracts import Afastamento, BhQuitacao, Solicitacao, TipoSolicitacao
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import lancamentos as lancamentos_servico
from app.core.erros import ErroDeAplicacao
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from app.workflow.solicitacoes import afastamentos as modulo
from app.workflow.solicitacoes import eventos as eventos_servico
from tests.f10.conftest import ContextoF10

# 2026-08-03/04 sao segunda/terca-feira -- dentro da jornada util seg-sex
# (480 min/dia) que `contexto_f10` ja atribui ao vinculo desde 2020-01-01,
# sem fim de vigencia (ver docstring de `tests/f10/conftest.py`).
_SEGUNDA = dt.date(2026, 8, 3)
_TERCA = dt.date(2026, 8, 4)
# Periodo de ferias fora do periodo de folga acima, para nao colidir com o
# teste de sobreposicao (que usa um segundo intervalo deliberadamente
# sobreposto a este).
_FERIAS_INICIO = dt.date(2026, 9, 1)
_FERIAS_FIM = dt.date(2026, 9, 10)


@pytest.fixture(autouse=True)
def _barramento_limpo():
    """`app.workflow.solicitacoes.eventos.BARRAMENTO_INTERNO` (A1) e uma
    lista em memoria no nivel do modulo -- limpa antes/depois de cada teste
    para os testes desta suite nunca verem envelope de outro (mesmo padrao
    de `tests/f4/banco_horas/test_quitacoes.py::_barramento_limpo`)."""
    eventos_servico.limpar_barramento()
    yield
    eventos_servico.limpar_barramento()


async def _criar_tipo_solicitacao(
    sessao: AsyncSession, tenant_id: uuid.UUID, *, categoria: str
) -> TipoSolicitacao:
    tipo = TipoSolicitacao(
        tenant_id=tenant_id,
        codigo=f"{categoria.upper()}-{secrets.token_hex(5)}",
        nome=f"{categoria} de teste",
        categoria=categoria,
        etapas=[{"etapa": 1, "papel": "gestor"}],
    )
    sessao.add(tipo)
    await sessao.flush()
    return tipo


async def _criar_solicitacao(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    tipo_solicitacao_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID | None,
    data_inicio: dt.date | None,
    data_fim: dt.date | None,
    descricao: str = "Solicitacao de teste (T12/A4).",
) -> Solicitacao:
    solicitacao = Solicitacao(
        tenant_id=tenant_id,
        tipo_solicitacao_id=tipo_solicitacao_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        protocolo=f"2026-{secrets.randbelow(999999):06d}",
        data_inicio=data_inicio,
        data_fim=data_fim,
        descricao=descricao,
    )
    sessao.add(solicitacao)
    await sessao.flush()
    return solicitacao


async def _criar_conta_banco_horas_com_saldo(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    empresa_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    minutos_creditados: int,
) -> uuid.UUID:
    """Mesma forma de `tests/f4/banco_horas/conftest.py::semear_tenant_minimo`
    (`bh_politicas`/`bh_contas` via `INSERT` direto) mais um lancamento de
    credito via `app.apuracao.banco_horas.lancamentos.lancar` (F4, real --
    mesmo padrao de `tests/f4/banco_horas/test_quitacoes.py`), para o saldo
    existir antes de qualquer debito."""
    from sqlalchemy import text

    sufixo = secrets.token_hex(5)
    bh_politica_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, "
            " metodo_consumo, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste T12', "
            "        'individual', 6, 'fifo', :vigencia_inicio, TRUE)"
        ),
        {
            "id": bh_politica_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"POL-{sufixo}",
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )

    bh_conta_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :bh_politica_id, "
            "        'normal', 'Banco de horas normal', :periodo_inicio, :periodo_fim, 'aberta')"
        ),
        {
            "id": bh_conta_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "bh_politica_id": bh_politica_id,
            "periodo_inicio": dt.date(2026, 1, 1),
            "periodo_fim": dt.date(2026, 12, 31),
        },
    )
    await sessao.flush()

    await lancamentos_servico.lancar(
        sessao,
        tenant_id=tenant_id,
        bh_conta_id=bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=minutos_creditados,
        data_competencia=dt.date(2026, 7, 1),
        descricao="Credito de teste para materializacao de folga (T12).",
    )
    await sessao.flush()
    return bh_conta_id


# ---------------------------------------------------------------------------
# ferias
# ---------------------------------------------------------------------------


async def test_ferias_aprovada_cria_afastamento_lido_pelo_resolvedor_de_f3(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="ferias"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_FERIAS_INICIO,
        data_fim=_FERIAS_FIM,
    )

    await modulo.materializar_ferias_ou_folga(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        aprovador_usuario_id=contexto_f10.rh_usuario_id,
    )

    afastamento = (
        await sessao_f10.execute(
            select(Afastamento).where(Afastamento.solicitacao_id == solicitacao.id)
        )
    ).scalar_one()
    assert afastamento.status == "aprovado"
    assert afastamento.origem == "solicitacao"
    assert afastamento.tipo_afastamento_id == contexto_f10.tipo_afastamento_ferias_id
    assert afastamento.data_inicio == _FERIAS_INICIO
    assert afastamento.data_fim == _FERIAS_FIM
    assert afastamento.colaborador_id == contexto_f10.colaborador_id
    assert afastamento.vinculo_id == contexto_f10.vinculo_id
    assert afastamento.aprovado_por == contexto_f10.rh_usuario_id
    assert afastamento.aprovado_em is not None

    # `ajuste.aprovado` publicado por A1 (`app.workflow.solicitacoes.eventos`),
    # com `tratamentoId` AUSENTE do payload (PCF §2.7 item 4) -- ferias nunca
    # produz um Tratamento.
    assert len(eventos_servico.BARRAMENTO_INTERNO) == 1
    envelope = eventos_servico.BARRAMENTO_INTERNO[0]
    assert envelope["tipo"] == "ajuste.aprovado"
    assert envelope["dados"]["solicitacaoId"] == str(solicitacao.id)
    assert envelope["dados"]["protocolo"] == solicitacao.protocolo
    assert "tratamentoId" not in envelope["dados"]

    # Prova de leitura pelo resolvedor de F3 (so leitura, nunca editado) --
    # o dia de inicio das ferias passa a resolver tipoDia='afastamento'.
    resolucao = await resolver_jornada_do_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _FERIAS_INICIO
    )
    assert resolucao.tipo_dia == "afastamento"
    assert resolucao.afastamento_id == afastamento.id


async def test_ferias_sobreposta_e_recusada_com_val_010(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="ferias"
    )
    primeira = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_FERIAS_INICIO,
        data_fim=_FERIAS_FIM,
    )
    await modulo.materializar_ferias_ou_folga(
        sessao_f10,
        contexto_f10.tenant_id,
        primeira,
        aprovador_usuario_id=contexto_f10.rh_usuario_id,
    )

    # Segundo pedido, mesmo colaborador, intervalo que se sobrepoe ao
    # primeiro (5 dias de overlap: 06/09 a 15/09 vs. 01/09 a 10/09).
    segunda = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_FERIAS_FIM - dt.timedelta(days=4),
        data_fim=_FERIAS_FIM + dt.timedelta(days=5),
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            segunda,
            aprovador_usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-010"
    # A violacao veio de um `IntegrityError` real do Postgres (`ex_afastamentos_
    # sobreposicao`) -- a transacao da sessao fica abortada ate um rollback
    # explicito (mesmo padrao que `tests/f4/banco_horas/test_quitacoes.py::
    # test_saldo_insuficiente_e_recusado` ja segue: nao ha consulta adicional
    # na mesma sessao depois do `pytest.raises`). Em producao isto nunca e um
    # problema: a sessao e por requisicao HTTP e e descartada quando o erro
    # propaga (`app/db/sessao.py`), nunca reaproveitada.


async def test_ferias_sem_tipo_afastamento_ativo_e_recusada_com_rec_001(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Tenant SEM nenhum `tipo_afastamento` ativo de categoria `ferias` --
    usa um tenant proprio (nao o de `contexto_f10`, que ja semeia um) para
    provar o ramo `PONTO-REC-001` do PCF §2.3 sem reaproveitar a fixture
    compartilhada fora do que ela promete."""
    from sqlalchemy import text

    sufixo = secrets.token_hex(5)
    tenant_id = uuid.uuid4()
    # RLS da raiz exige `app.tenant_id` publicado ANTES do INSERT em
    # `tenants` (`pol_isolamento_tenant`, `WITH CHECK (id = app.tenant_id)`)
    # -- mesma ordem que `tests/f10/conftest.py::contexto_f10` ja usa.
    await sessao_f10.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )
    await sessao_f10.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, 'Tenant sem tipo ferias', 'Tenant sem tipo ferias', 'ativo')"
        ),
        {"id": tenant_id, "slug": f"f10-a4-semtipo-{sufixo}"},
    )
    empresa_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO empresas (id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Empresa sem tipo ferias', "
            "        'Empresa sem tipo ferias', 'SP', '3550308', 'America/Sao_Paulo')"
        ),
        {"id": empresa_id, "tenant_id": tenant_id, "cnpj": f"{secrets.randbelow(10**14):014d}"},
    )
    colaborador_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO colaboradores (id, tenant_id, empresa_id, matricula, cpf, "
            " nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, 'Colaborador sem tipo', "
            "        'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": f"MAT-{sufixo}",
            "cpf": f"{secrets.randbelow(10**11):011d}",
        },
    )
    vinculo_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO vinculos (id, tenant_id, colaborador_id, empresa_id, "
            " matricula_esocial, tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :esocial, 'empregado', "
            "        :data_inicio, TRUE, 'ativo')"
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
    await sessao_f10.flush()

    tipo_solicitacao = await _criar_tipo_solicitacao(sessao_f10, tenant_id, categoria="ferias")
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        data_inicio=_FERIAS_INICIO,
        data_fim=_FERIAS_FIM,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10, tenant_id, solicitacao, aprovador_usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# folga
# ---------------------------------------------------------------------------


async def test_folga_aprovada_debita_saldo_correto_de_banco_de_horas(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    bh_conta_id = await _criar_conta_banco_horas_com_saldo(
        sessao_f10,
        contexto_f10.tenant_id,
        empresa_id=contexto_f10.empresa_id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        minutos_creditados=2000,
    )
    conta_antes = await contas_servico.obter_conta_banco_horas(
        sessao_f10, contexto_f10.tenant_id, bh_conta_id
    )
    assert conta_antes.saldo_atual_minutos == 2000

    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="folga"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_SEGUNDA,
        data_fim=_TERCA,
    )

    await modulo.materializar_ferias_ou_folga(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        aprovador_usuario_id=contexto_f10.gestor_usuario_id,
    )

    # Segunda + terca, 480 min uteis cada (jornada de `contexto_f10`) = 960.
    conta_depois = await contas_servico.obter_conta_banco_horas(
        sessao_f10, contexto_f10.tenant_id, bh_conta_id
    )
    assert conta_depois.saldo_atual_minutos == 2000 - 960

    quitacao = (
        await sessao_f10.execute(select(BhQuitacao).where(BhQuitacao.bh_conta_id == bh_conta_id))
    ).scalar_one()
    assert quitacao.tipo == "folga"
    assert quitacao.minutos == 960
    assert quitacao.status == "efetivada"

    assert len(eventos_servico.BARRAMENTO_INTERNO) == 1
    envelope = eventos_servico.BARRAMENTO_INTERNO[0]
    assert envelope["tipo"] == "ajuste.aprovado"
    assert "tratamentoId" not in envelope["dados"]

    # `folga` NUNCA cria `Afastamento` (PCF §2.2) -- diferente de `ferias`.
    afastamentos_da_solicitacao = (
        (
            await sessao_f10.execute(
                select(Afastamento).where(Afastamento.solicitacao_id == solicitacao.id)
            )
        )
        .scalars()
        .all()
    )
    assert afastamentos_da_solicitacao == []


async def test_folga_sem_dia_util_no_periodo_e_recusada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Sabado (`_SEGUNDA` + 5 dias = 2026-08-08) e folga na jornada de
    `contexto_f10` -- nenhuma carga prevista para debitar."""
    sabado = _SEGUNDA + dt.timedelta(days=5)
    assert sabado.isoweekday() == 6

    await _criar_conta_banco_horas_com_saldo(
        sessao_f10,
        contexto_f10.tenant_id,
        empresa_id=contexto_f10.empresa_id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        minutos_creditados=2000,
    )
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="folga"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=sabado,
        data_fim=sabado,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            solicitacao,
            aprovador_usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# validacoes de campo obrigatorio / configuracao do tenant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("categoria", "usar_vinculo", "data_inicio", "data_fim", "codigo_esperado"),
    [
        # ferias: vinculoId ausente.
        ("ferias", False, _FERIAS_INICIO, _FERIAS_FIM, "PONTO-VAL-001"),
        # ferias: dataInicio ausente.
        ("ferias", True, None, _FERIAS_FIM, "PONTO-VAL-001"),
        # folga: vinculoId ausente.
        ("folga", False, _SEGUNDA, _TERCA, "PONTO-VAL-001"),
        # folga: dataFim ausente.
        ("folga", True, _SEGUNDA, None, "PONTO-VAL-001"),
    ],
)
async def test_campo_obrigatorio_ausente_ou_invalido_e_recusado(
    sessao_f10: AsyncSession,
    contexto_f10: ContextoF10,
    categoria: str,
    usar_vinculo: bool,
    data_inicio: dt.date | None,
    data_fim: dt.date | None,
    codigo_esperado: str,
) -> None:
    """Não há caso "dataFim anterior a dataInicio" nesta lista: `ck_
    solicitacoes_periodo` já impede fisicamente gravar uma `Solicitacao`
    nesse estado (`data_fim IS NULL OR data_inicio IS NULL OR data_fim >=
    data_inicio`) -- o guard equivalente em `_materializar_ferias` (marcado
    `pragma: no cover` no módulo) é defesa em profundidade para um
    `Solicitacao` construído em memória fora do INSERT normal, nunca
    alcançável por um teste que insere de verdade."""
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria=categoria
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id if usar_vinculo else None,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            solicitacao,
            aprovador_usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == codigo_esperado


async def test_ferias_com_mais_de_um_tipo_ativo_e_recusada_com_conf_001(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """`contexto_f10` ja semeia um `TipoAfastamento` categoria `ferias`
    ativo -- acrescenta um SEGUNDO, tornando a resolucao ambigua (PCF §2.3:
    "mais de um tipo ativo ... erro de configuracao do tenant")."""
    from ponto_contracts import TipoAfastamento

    segundo_tipo = TipoAfastamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"FERIAS2-{secrets.token_hex(5)}",
        nome="Ferias de teste (segundo tipo)",
        categoria="ferias",
        ativo=True,
    )
    sessao_f10.add(segundo_tipo)
    await sessao_f10.flush()

    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="ferias"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_FERIAS_INICIO,
        data_fim=_FERIAS_FIM,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            solicitacao,
            aprovador_usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_folga_sem_conta_banco_de_horas_e_recusada_com_rec_001(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Nenhuma `bh_conta` foi criada para o vinculo -- `_resolver_conta_
    banco_horas` recusa antes de tentar `criar_quitacao_banco_horas`."""
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="folga"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_SEGUNDA,
        data_fim=_TERCA,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            solicitacao,
            aprovador_usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_folga_resolve_conta_sem_codigo_normal_pelo_fallback(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """`_resolver_conta_banco_horas` cai no fallback (qualquer conta do
    vinculo) quando nenhuma tem `codigo='normal'` -- aqui a unica conta do
    vinculo tem `codigo='especial'`."""
    from sqlalchemy import text

    sufixo = secrets.token_hex(5)
    bh_politica_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, "
            " metodo_consumo, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste T12b', "
            "        'individual', 6, 'fifo', :vigencia_inicio, TRUE)"
        ),
        {
            "id": bh_politica_id,
            "tenant_id": contexto_f10.tenant_id,
            "empresa_id": contexto_f10.empresa_id,
            "codigo": f"POL-{sufixo}",
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )
    bh_conta_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :bh_politica_id, "
            "        'especial', 'Banco de horas especial', :periodo_inicio, :periodo_fim, "
            "        'aberta')"
        ),
        {
            "id": bh_conta_id,
            "tenant_id": contexto_f10.tenant_id,
            "colaborador_id": contexto_f10.colaborador_id,
            "vinculo_id": contexto_f10.vinculo_id,
            "bh_politica_id": bh_politica_id,
            "periodo_inicio": dt.date(2026, 1, 1),
            "periodo_fim": dt.date(2026, 12, 31),
        },
    )
    await sessao_f10.flush()
    await lancamentos_servico.lancar(
        sessao_f10,
        tenant_id=contexto_f10.tenant_id,
        bh_conta_id=bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=2000,
        data_competencia=dt.date(2026, 7, 1),
        descricao="Credito de teste (conta sem codigo normal).",
    )
    await sessao_f10.flush()

    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="folga"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_SEGUNDA,
        data_fim=_TERCA,
    )

    await modulo.materializar_ferias_ou_folga(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        aprovador_usuario_id=contexto_f10.gestor_usuario_id,
    )

    conta_depois = await contas_servico.obter_conta_banco_horas(
        sessao_f10, contexto_f10.tenant_id, bh_conta_id
    )
    assert conta_depois.saldo_atual_minutos == 2000 - 960


# ---------------------------------------------------------------------------
# guarda defensiva (categoria fora de ferias/folga)
# ---------------------------------------------------------------------------


async def test_categoria_fora_de_ferias_folga_e_recusada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="abono"
    )
    solicitacao = await _criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        tipo_solicitacao_id=tipo_solicitacao.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        data_inicio=_FERIAS_INICIO,
        data_fim=None,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await modulo.materializar_ferias_ou_folga(
            sessao_f10,
            contexto_f10.tenant_id,
            solicitacao,
            aprovador_usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"
