"""Fixtures locais dos testes de `app/biometria` (T9, agente A3).

Reusa `contexto_organizacional` e `sessao_f2` de `apps/api/tests/f2/conftest.py`
(A1, T1) para tenant/empresa/unidade. O que este arquivo acrescenta e proprio
de A3:

* `chave_mestra_biometria` (autouse): gera uma KEK de teste descartavel
  (`openssl rand -hex 32` equivalente, via `secrets.token_hex`) e a publica em
  `PONTO_BIOMETRIA_CHAVE_MESTRA` para cada teste, isolada por `monkeypatch`
  (nunca versionada, nunca compartilhada entre testes).
* `criar_colaborador`: fabrica um colaborador de teste na empresa do tenant
  corrente, com CPF valido gerado deterministicamente por indice (mesmo
  algoritmo de digito verificador de
  `apps/worker/tests` / `tests/f2/importadores/test_worker_tarefa.py`).
* `criar_consentimento_biometrico`: fabrica uma linha `concedido` em
  `consentimentos` para a finalidade `biometria_facial` ou `biometria_digital`
  -- sem ela `criar_biometria` recusa com `PONTO-LGPD-001` (ADR-006 regra
  "consentimento").
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
import pytest_asyncio
from ponto_contracts import Colaborador, Consentimento
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f2.conftest import ContextoOrganizacional


@pytest.fixture(autouse=True)
def chave_mestra_biometria(monkeypatch: pytest.MonkeyPatch) -> str:
    """KEK de teste descartavel: 32 bytes hexadecimais, nunca versionada."""
    chave = secrets.token_hex(32)
    monkeypatch.setenv("PONTO_BIOMETRIA_CHAVE_MESTRA", chave)
    return chave


def _cpf_valido_para_indice(indice: int) -> str:
    """Mesmo algoritmo (modulo 11) usado em `worker/tarefas/importacoes.py`,
    reimplementado aqui para nao acoplar `apps/api` a `apps/worker` (pacotes
    Docker separados -- ver docstring daquele modulo)."""
    base = str(300_000_000 + indice)[-9:]
    pesos1 = list(range(10, 1, -1))
    pesos2 = list(range(11, 1, -1))

    def _dv(digitos: str, pesos: list[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    dv1 = _dv(base, pesos1)
    dv2 = _dv(base + str(dv1), pesos2)
    return f"{base}{dv1}{dv2}"


@pytest_asyncio.fixture
async def criar_colaborador(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    """Fabrica: cria um colaborador na empresa matriz do tenant corrente e
    devolve o `id`. Cada chamada usa matricula e CPF novos."""

    contador = {"n": 0}

    async def _fabrica(*, empresa_id: UUID | None = None) -> UUID:
        contador["n"] += 1
        indice = contador["n"]
        colaborador = Colaborador(
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=empresa_id or contexto_organizacional.empresa_matriz_id,
            matricula=f"BIO{indice:05d}",
            cpf=_cpf_valido_para_indice(indice),
            nome_completo=f"Colaborador Biometria Teste {indice}",
            status="ativo",
        )
        sessao_f2.add(colaborador)
        await sessao_f2.flush()
        return colaborador.id

    return _fabrica


@pytest_asyncio.fixture
async def criar_consentimento_biometrico(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    """Fabrica: cria um consentimento `concedido` para a finalidade pedida."""

    async def _fabrica(*, colaborador_id: UUID, finalidade: str = "biometria_facial") -> UUID:
        consentimento = Consentimento(
            tenant_id=contexto_organizacional.tenant_id,
            colaborador_id=colaborador_id,
            finalidade=finalidade,
            versao_termo="v1",
            texto_termo_ref=f"termos/{uuid.uuid4()}.pdf",
            hash_termo="a" * 64,
            status="concedido",
            canal="app",
        )
        sessao_f2.add(consentimento)
        await sessao_f2.flush()
        return consentimento.id

    return _fabrica
