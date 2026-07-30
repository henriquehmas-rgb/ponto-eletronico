"""Testes de `app.workflow.solicitacoes.tipos` (T2, A1)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.solicitacoes import tipos
from tests.f10.conftest import ContextoF10


async def test_criar_tipo_solicitacao_aceita_etapas_envelopadas(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    dados = esquemas.TipoSolicitacaoCriar.model_validate(
        {
            "codigo": f"troca-{uuid4().hex[:8]}",
            "nome": "Troca de escala de teste",
            "categoria": "troca_escala",
            "etapas": {"etapas": [{"ordem": 1, "papel": "gestor"}]},
        }
    )
    criado = await tipos.criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, dados, usuario_id=None
    )
    assert criado.etapas == [{"etapa": 1, "papel": "gestor"}]

    schema = tipos.tipo_para_schema(criado)
    assert schema.etapas == {"etapas": [{"etapa": 1, "papel": "gestor"}]}


async def test_normalizar_etapas_aceita_array_cru_direto() -> None:
    """`TipoSolicitacaoCriar.etapas` é tipado `dict[str, Any]` pelo contrato
    -- o próprio Pydantic recusa um `list` no corpo da requisição antes de
    chegar a este módulo (`ValidationError` na fronteira HTTP, não algo que
    `criar_tipo_solicitacao` precise vedar). O fallback "array cru" de
    `_normalizar_etapas_entrada` existe só para tolerar um dicionário cuja
    chave `etapas`/`dados` está ausente mas cujo valor já é a lista (uso
    interno, nunca alcançado por uma requisição HTTP real) -- testado aqui
    diretamente na função, não via `TipoSolicitacaoCriar`."""
    etapas = tipos._normalizar_etapas_entrada([{"papel": "gestor"}])  # type: ignore[arg-type]
    assert etapas == [{"etapa": 1, "papel": "gestor"}]


async def test_criar_tipo_solicitacao_recusa_papel_invalido(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    dados = esquemas.TipoSolicitacaoCriar.model_validate(
        {
            "codigo": f"invalido-{uuid4().hex[:8]}",
            "nome": "Tipo invalido",
            "categoria": "outro",
            "etapas": {"etapas": [{"papel": "chefe"}]},
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await tipos.criar_tipo_solicitacao(
            sessao_f10, contexto_f10.tenant_id, dados, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_listar_tipos_solicitacao_devolve_etapas_no_formato_do_contrato(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Prova de fumaça do achado de contrato documentado no módulo: o tipo
    de exemplo semeado pela fixture (mesma forma de `seed_dev.py`, array
    cru) precisa aparecer, na listagem, no formato `dict[str, Any]` que o
    schema Pydantic exige -- sem isto, `listarTiposSolicitacao` quebraria
    com `ValidationError` para TODO tipo de fábrica."""
    linhas, _ = await tipos.listar_tipos_solicitacao(sessao_f10, contexto_f10.tenant_id)
    codigos = {linha.codigo: linha for linha in linhas}
    assert contexto_f10.tipo_solicitacao_codigo in codigos
    schema = tipos.tipo_para_schema(codigos[contexto_f10.tipo_solicitacao_codigo])
    assert schema.etapas is not None
    assert isinstance(schema.etapas, dict)
    assert schema.etapas["etapas"] == [
        {"etapa": 1, "papel": "gestor"},
        {"etapa": 2, "papel": "rh"},
    ]
