"""Critério de aceite 11 do PCF (`docs/fases/F10-workflows-aprovacoes-fechamento.md`,
§7): prova campo a campo, contra `packages/contracts/events.yaml`, que
`ajuste.solicitado`, `ajuste.aprovado` e `ajuste.reprovado` carregam todos os
campos `required` do contrato -- mesmo padrão de checagem manual que
`tests/f10/fechamento/test_eventos.py` (A2) já usa para os eventos de
fechamento.

Achado ao escrever este teste, já documentado por A1 no docstring de
`app.workflow.solicitacoes.eventos` e em `docs/backlog.md`: `ajuste.aprovado`
é publicado em DOIS lugares diferentes dependendo da categoria da
solicitação -- (a) pelo barramento de F4
(`app.apuracao.tratamento.eventos.BARRAMENTO_INTERNO`), quando a categoria
tem `tipo_tratamento_id` (a maioria: `ajuste_ponto`, `abono`, etc); (b) por
`app.workflow.solicitacoes.eventos.publicar_ajuste_aprovado` (este pacote),
só para `ferias`/`folga`, onde `tratamentoId` é OMITIDO porque essas duas
categorias nunca produzem `Tratamento` -- violação real e já aceita do campo
`required` `tratamentoId` para essas duas categorias especificamente, não
uma categoria geral. Este teste prova os dois caminhos separadamente, sem
esconder a diferença.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos as eventos_tratamento
from app.schemas import contrato as esquemas
from app.workflow.solicitacoes import eventos, servico
from app.workflow.solicitacoes.materializacao import (
    materializar_solicitacao_aprovada,
    reprovar_solicitacao,
)
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste

#: `events.yaml`, campo a campo (packages/contracts/events.yaml, linhas ~283-382).
_REQUERIDOS_AJUSTE_SOLICITADO = (
    "solicitacaoId",
    "protocolo",
    "colaboradorId",
    "dataReferencia",
    "tipoSolicitacaoCodigo",
)
_REQUERIDOS_AJUSTE_APROVADO = (
    "solicitacaoId",
    "protocolo",
    "colaboradorId",
    "dataReferencia",
    "tratamentoId",
    "decididoEm",
)
_REQUERIDOS_AJUSTE_REPROVADO = (
    "solicitacaoId",
    "protocolo",
    "colaboradorId",
    "dataReferencia",
    "decididoEm",
    "motivo",
)


@pytest.fixture(autouse=True)
def _barramentos_limpos() -> Iterator[None]:
    eventos.limpar_barramento()
    eventos_tratamento.limpar_barramento()
    yield
    eventos.limpar_barramento()
    eventos_tratamento.limpar_barramento()


async def _criar_tipo_solicitacao(
    sessao: AsyncSession, contexto: ContextoF10, *, codigo: str, categoria: str
) -> uuid.UUID:
    """`tipo_tratamento_id` sempre NULL -- reproduz, para este arquivo, as
    duas categorias sem `Tratamento` que `ContextoF10` (A1) não expõe
    prontas: `ferias` (usada por `materializar_ferias_ou_folga`, A4) e uma
    categoria genuinamente sem efeito (`troca_escala`, único caminho real que
    chama `publicar_ajuste_reprovado` -- ver
    `materializacao.py::reprovar_solicitacao`)."""
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, exige_justificativa, "
            " tipo_tratamento_id, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, "
            '        \'[{"etapa": 1, "papel": "gestor"}]\', TRUE, NULL, TRUE)'
        ),
        {
            "id": tipo_id,
            "tenant_id": contexto.tenant_id,
            "codigo": codigo,
            "nome": f"{codigo} (teste completude)",
            "categoria": categoria,
        },
    )
    return tipo_id


async def test_ajuste_solicitado_tem_todos_os_campos_required(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "descricao": "Prova de completude do evento ajuste.solicitado.",
        }
    )
    await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.solicitado"]
    assert len(publicados) == 1
    dados = publicados[0]["dados"]
    for campo in _REQUERIDOS_AJUSTE_SOLICITADO:
        assert campo in dados, f"campo required '{campo}' ausente em ajuste.solicitado"


async def test_ajuste_aprovado_vindo_de_ajuste_ponto_tem_todos_os_campos_required(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Caminho (a): categoria com `tipo_tratamento_id` -- publicado pelo
    barramento de F4, encaminhado por `_materializar_via_tratamento`."""
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "descricao": "Prova de completude do evento ajuste.aprovado (via tratamento).",
        }
    )
    solicitacao = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    await materializar_solicitacao_aprovada(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        aprovador_usuario_id=contexto_f10.rh_usuario_id,
    )

    publicados = [
        e for e in eventos_tratamento.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"
    ]
    assert len(publicados) == 1
    dados = publicados[0]["dados"]
    for campo in _REQUERIDOS_AJUSTE_APROVADO:
        assert (
            campo in dados
        ), f"campo required '{campo}' ausente em ajuste.aprovado (via tratamento)"


async def test_ajuste_aprovado_vindo_de_ferias_omite_tratamento_id_gap_conhecido(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Caminho (b): `ferias`/`folga` -- publicado por
    `app.workflow.solicitacoes.eventos.publicar_ajuste_aprovado` (A1/A4).
    Prova o comportamento REAL, incluindo o gap já documentado: `tratamentoId`
    é `required` no contrato mas fica ausente aqui, porque `ferias` nunca
    produz `Tratamento` (docs/backlog.md, achado de A1 -- não é bug desta
    fase, é limitação estrutural das duas categorias, sem invenção de uma
    quarta forma de materialização, PCF §9 proibição 11)."""
    tipo_ferias = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10, codigo="FERIAS-COMPLETUDE", categoria="ferias"
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_ferias),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataInicio": (dt.date.today() + dt.timedelta(days=10)).isoformat(),
            "dataFim": (dt.date.today() + dt.timedelta(days=15)).isoformat(),
            "payload": {"tipoAfastamentoId": str(contexto_f10.tipo_afastamento_ferias_id)},
            "descricao": "Prova de completude do evento ajuste.aprovado (via ferias).",
        }
    )
    solicitacao = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    await materializar_solicitacao_aprovada(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        aprovador_usuario_id=contexto_f10.rh_usuario_id,
    )

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"]
    assert len(publicados) == 1
    dados = publicados[0]["dados"]

    requeridos_sem_tratamento_id = tuple(
        c for c in _REQUERIDOS_AJUSTE_APROVADO if c != "tratamentoId"
    )
    for campo in requeridos_sem_tratamento_id:
        assert campo in dados, f"campo required '{campo}' ausente em ajuste.aprovado (via ferias)"
    assert "tratamentoId" not in dados, (
        "gap conhecido deixou de existir -- se ferias passou a produzir Tratamento, "
        "atualize este teste E o achado em docs/backlog.md (A1, ajuste.aprovado/tratamentoId)"
    )


async def test_ajuste_reprovado_categoria_sem_efeito_tem_todos_os_campos_required(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Único caminho real que chama `publicar_ajuste_reprovado` (deste
    pacote) em vez do barramento de F4: categoria sem `tipo_tratamento_id` e
    fora de `ferias`/`folga` (`materializacao.py::reprovar_solicitacao`)."""
    tipo_sem_efeito = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10, codigo="TROCA-COMPLETUDE", categoria="troca_escala"
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_sem_efeito),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dt.date.today().isoformat(),
            "descricao": "Prova de completude do evento ajuste.reprovado.",
        }
    )
    solicitacao = await servico.criar_solicitacao(
        sessao_f10, contexto_f10.tenant_id, corpo, usuario_id=contexto_f10.colaborador_usuario_id
    )

    await reprovar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        solicitacao,
        motivo="Sem evidencia suficiente (teste de completude).",
        etapa=1,
        aprovador_usuario_id=contexto_f10.gestor_usuario_id,
    )

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.reprovado"]
    assert len(publicados) == 1
    dados = publicados[0]["dados"]
    for campo in _REQUERIDOS_AJUSTE_REPROVADO:
        assert campo in dados, f"campo required '{campo}' ausente em ajuste.reprovado"
