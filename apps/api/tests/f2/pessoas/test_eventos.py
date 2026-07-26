"""Testes dos eventos de dominio `colaborador.admitido` e
`colaborador.demitido` (T8).

Cobre o criterio de aceite 10: o envelope e o *payload* publicados por
`criarVinculo` e `encerrarVinculo` batem, campo a campo, com o que
`packages/contracts/events.yaml` declara -- envelope (`required`: id, tipo,
versao, ocorridoEm, tenantId, dados) e o `payload` de cada evento, incluindo
todos os `required`.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import random
import uuid
from typing import Any

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.documentos import cpf_valido
from app.pessoas import colaboradores as colaboradores_servico
from app.pessoas import contratos as servico
from app.pessoas import eventos
from app.schemas.contrato import (
    ColaboradorCriar,
    EncerramentoVinculoRequisicao,
    VinculoCriar,
)
from tests.f2.conftest import ContextoOrganizacional

_CONTRATOS = pathlib.Path(__file__).resolve().parents[5] / "packages" / "contracts"
_EVENTS_YAML = yaml.safe_load((_CONTRATOS / "events.yaml").read_text(encoding="utf-8"))

_ENVELOPE_REQUERIDO: list[str] = _EVENTS_YAML["envelope"]["schema"]["required"]


def _payload_declarado(nome_evento: str) -> dict[str, Any]:
    (evento,) = (e for e in _EVENTS_YAML["eventos"] if e["nome"] == nome_evento)
    return evento["payload"]


def _gerar_cpf_valido() -> str:
    while True:
        base = "".join(str(random.randint(0, 9)) for _ in range(9))  # noqa: S311
        if len(set(base)) == 1:
            continue
        pesos1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
        dv1 = 11 - (sum(int(d) * p for d, p in zip(base, pesos1, strict=True)) % 11)
        dv1 = 0 if dv1 >= 10 else dv1
        base10 = base + str(dv1)
        pesos2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
        dv2 = 11 - (sum(int(d) * p for d, p in zip(base10, pesos2, strict=True)) % 11)
        dv2 = 0 if dv2 >= 10 else dv2
        candidato = base10 + str(dv2)
        if cpf_valido(candidato):
            return candidato


async def _criar_colaborador(sessao: AsyncSession, contexto: ContextoOrganizacional):
    dados = ColaboradorCriar(
        empresaId=contexto.empresa_matriz_id,
        matricula=f"MAT-{uuid.uuid4().hex[:8]}",
        cpf=_gerar_cpf_valido(),
        nomeCompleto="Colaborador Evento",
    )
    return await colaboradores_servico.criar_colaborador(sessao, contexto.tenant_id, dados)


def _validar_envelope(
    envelope: dict[str, Any], *, tipo_esperado: str, versao_esperada: int
) -> None:
    for campo in _ENVELOPE_REQUERIDO:
        assert campo in envelope, f"campo obrigatorio do envelope ausente: {campo}"
    assert envelope["tipo"] == tipo_esperado
    assert envelope["versao"] == versao_esperada
    uuid.UUID(envelope["id"])  # nao levanta
    uuid.UUID(envelope["tenantId"])
    dt.datetime.fromisoformat(envelope["ocorridoEm"])
    assert isinstance(envelope["dados"], dict)


def _validar_payload(dados: dict[str, Any], nome_evento: str) -> None:
    declarado = _payload_declarado(nome_evento)
    for campo in declarado["required"]:
        assert campo in dados, f"campo obrigatorio do payload de {nome_evento} ausente: {campo}"
    propriedades = declarado["properties"]
    for campo, valor in dados.items():
        assert campo in propriedades, f"campo {campo} nao declarado no payload de {nome_evento}"
        especificacao = propriedades[campo]
        if especificacao.get("format") == "uuid":
            uuid.UUID(valor)
        if especificacao.get("format") == "date":
            dt.date.fromisoformat(valor)
        if especificacao.get("type") == "boolean":
            assert isinstance(valor, bool)
        pattern = especificacao.get("pattern")
        if pattern == "^[0-9]{11}$":
            assert valor.isdigit() and len(valor) == 11


@pytest.mark.asyncio
async def test_criar_vinculo_publica_colaborador_admitido_com_payload_exato(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    eventos.limpar_barramento()
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)

    vinculo = await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
            dataInicio=dt.date(2026, 8, 1),
        ),
    )

    assert len(eventos.BARRAMENTO_INTERNO) == 1
    envelope = eventos.BARRAMENTO_INTERNO[0]
    _validar_envelope(envelope, tipo_esperado="colaborador.admitido", versao_esperada=1)
    _validar_payload(envelope["dados"], "colaborador.admitido")

    dados = envelope["dados"]
    assert dados["colaboradorId"] == str(colaborador.id)
    assert dados["vinculoId"] == str(vinculo.id)
    assert dados["empresaId"] == str(contexto_organizacional.empresa_matriz_id)
    assert dados["matricula"] == colaborador.matricula
    assert dados["cpf"] == colaborador.cpf
    assert dados["dataInicio"] == "2026-08-01"


@pytest.mark.asyncio
async def test_criar_vinculo_inativo_nao_publica_admitido(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    """So vinculo que nasce ativo dispara `colaborador.admitido` -- e o que
    `events.yaml` declara em `quando_dispara`."""
    eventos.limpar_barramento()
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)

    await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
            dataInicio=dt.date(2026, 8, 1),
            status="suspenso",
        ),
    )
    assert eventos.BARRAMENTO_INTERNO == []


@pytest.mark.asyncio
async def test_encerrar_vinculo_publica_colaborador_demitido_com_payload_exato(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    vinculo = await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
            dataInicio=dt.date(2026, 1, 1),
        ),
    )
    eventos.limpar_barramento()

    await servico.encerrar_vinculo(
        sessao_f2,
        tenant_id,
        vinculo.id,
        EncerramentoVinculoRequisicao(
            dataFim=dt.date(2026, 9, 30), motivoDesligamento="Pedido de demissao"
        ),
    )

    assert len(eventos.BARRAMENTO_INTERNO) == 1
    envelope = eventos.BARRAMENTO_INTERNO[0]
    _validar_envelope(envelope, tipo_esperado="colaborador.demitido", versao_esperada=1)
    _validar_payload(envelope["dados"], "colaborador.demitido")

    dados = envelope["dados"]
    assert dados["colaboradorId"] == str(colaborador.id)
    assert dados["vinculoId"] == str(vinculo.id)
    assert dados["empresaId"] == str(contexto_organizacional.empresa_matriz_id)
    assert dados["dataFim"] == "2026-09-30"
    assert dados["motivoDesligamento"] == "Pedido de demissao"


def test_envelope_e_payload_declarados_existem_no_contrato() -> None:
    """Prova que este teste le o `events.yaml` de verdade, e nao uma copia
    local que poderia divergir silenciosamente do contrato congelado."""
    assert set(_ENVELOPE_REQUERIDO) == {
        "id",
        "tipo",
        "versao",
        "ocorridoEm",
        "tenantId",
        "dados",
    }
    admitido = _payload_declarado("colaborador.admitido")
    assert set(admitido["required"]) == {
        "colaboradorId",
        "vinculoId",
        "empresaId",
        "matricula",
        "cpf",
        "dataInicio",
    }
    demitido = _payload_declarado("colaborador.demitido")
    assert set(demitido["required"]) == {"colaboradorId", "vinculoId", "empresaId", "dataFim"}
