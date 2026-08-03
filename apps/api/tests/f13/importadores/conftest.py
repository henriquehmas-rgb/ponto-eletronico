"""Fixtures do subarvore `importadores` da fase F13 (A8, T19 -- ownership
exclusivo de tudo sob `apps/api/tests/f13/importadores/**`, ver PCF F13 §5.2
e a nota de ownership em `apps/api/app/integracoes/importadores/__init__
.py`).

Construido SOBRE `apps/api/tests/f13/conftest.py` (compartilhada da fase,
criacao exclusiva de A1): reaproveita `sessao_f13`/`contexto_f13`/
`aplicar_tenant_teste` de la (composicao automatica do pytest). Este arquivo
fica no nivel `importadores/` (nao dentro de `afd_terceiro/`) porque
`criar_rep_p`/`criar_colaborador_ativo` sao usados tanto pelos testes do
importador de AFD de terceiro (`afd_terceiro/test_*.py`) quanto pelo teste
do CRUD generico de `Importacao` (`test_servico.py`, neste mesmo nivel) --
o pytest compoe este conftest automaticamente para os dois.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RepPTeste:
    id: uuid.UUID
    numero_inpi: str


@pytest_asyncio.fixture
async def criar_rep_p(
    sessao_f13: AsyncSession,
) -> Callable[..., Awaitable[RepPTeste]]:
    """Fabrica: insere um REP-P `ativo` para `(tenant_id, empresa_id)`,
    devolve `RepPTeste`. Chame quantas vezes precisar dentro do mesmo teste
    -- cada chamada gera um REP-P novo (util para o caso adversarial de
    "mais de um REP-P ativo, sem repPId explicito")."""

    async def _fabrica(
        *, tenant_id: uuid.UUID, empresa_id: uuid.UUID, empresa_cnpj: str, status: str = "ativo"
    ) -> RepPTeste:
        rep_p_id = uuid.uuid4()
        numero_inpi = str(uuid.uuid4().int)[:15].zfill(15)
        hoje = dt.date.today()
        await sessao_f13.execute(
            text(
                "INSERT INTO rep_ps "
                "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
                " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
                " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', :numero_inpi, "
                "        :cnpj_dev, :razao_dev, :cnpj_emp, :razao_emp, '1.0.0-teste', "
                "        :inicio, :status)"
            ),
            {
                "id": rep_p_id,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "identificador": f"REP-{uuid.uuid4().hex[:10]}",
                "numero_inpi": numero_inpi,
                "cnpj_dev": "60258502000149",
                "razao_dev": "SEEG Servicos de Tecnologia da Informacao LTDA",
                "cnpj_emp": empresa_cnpj,
                "razao_emp": "Empresa de teste F13/A8 Ltda",
                "inicio": hoje,
                "status": status,
            },
        )
        return RepPTeste(id=rep_p_id, numero_inpi=numero_inpi)

    return _fabrica


@dataclass(frozen=True, slots=True)
class ColaboradorTeste:
    id: uuid.UUID
    cpf: str
    vinculo_id: uuid.UUID


@pytest_asyncio.fixture
async def criar_colaborador_ativo(
    sessao_f13: AsyncSession,
) -> Callable[..., Awaitable[ColaboradorTeste]]:
    """Fabrica: colaborador + vinculo `apura_ponto=true`/`ativo` para um CPF
    especifico (o CPF que o teste vai usar num registro tipo 7 sintetico) --
    prova que o importador RESOLVE `colaborador_id`/`vinculo_id` quando o
    CPF do arquivo bate com alguem cadastrado."""

    async def _fabrica(
        *, tenant_id: uuid.UUID, empresa_id: uuid.UUID, cpf: str
    ) -> ColaboradorTeste:
        colaborador_id = uuid.uuid4()
        matricula = uuid.uuid4().hex[:10]
        hoje = dt.date.today()
        await sessao_f13.execute(
            text(
                "INSERT INTO colaboradores "
                "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status, "
                " data_admissao) "
                "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo', "
                "        :admissao)"
            ),
            {
                "id": colaborador_id,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "matricula": matricula,
                "cpf": cpf,
                "nome": "Colaborador de Teste F13/A8",
                "admissao": hoje - dt.timedelta(days=365),
            },
        )
        vinculo_id = uuid.uuid4()
        await sessao_f13.execute(
            text(
                "INSERT INTO vinculos "
                "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
                " tipo_vinculo, data_inicio, principal, apura_ponto, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :matricula, "
                "        'empregado', :inicio, TRUE, TRUE, 'ativo')"
            ),
            {
                "id": vinculo_id,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": empresa_id,
                "matricula": matricula,
                "inicio": hoje - dt.timedelta(days=365),
            },
        )
        return ColaboradorTeste(id=colaborador_id, cpf=cpf, vinculo_id=vinculo_id)

    return _fabrica
