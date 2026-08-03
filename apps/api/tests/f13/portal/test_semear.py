"""Testes de `app.integracoes.sandbox.semear` contra banco real (F13/A2, T8).

Cobre os dois criterios de aceite explicitos de T8:
* "rodar duas vezes nao duplica nada" (idempotencia);
* "sem nenhum dado real do tenant de producao aparecer" (isolamento por
  tenant, sob RLS de verdade -- ver `conftest.py`, role de LOGIN sem
  BYPASSRLS).

Nao cobre (documentado no relatorio final da fase, nao escondido): o ciclo
HTTP completo login -> criarApiClient -> emitirTokenOAuth exige o roteador de
`auth`/`admin` da aplicacao inteira montado (`app.main.app`), que nesta
sessao paralela depende de arquivos de outros agentes (`routers/sso.py`,
A9/A10) as vezes mid-edit no working tree compartilhado. Esse ciclo foi
validado manualmente contra a app real (ver relatorio da fase); o teste
automatizado aqui fica no nivel de banco, que e o nivel que este pacote
(`app.integracoes.sandbox`) realmente possui.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from ponto_contracts import Credencial, Marcacao, PerfilPermissao, Permissao, Usuario
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.sessao import aplicar_tenant
from app.identidade.autenticacao.senha import verificar_hash
from app.integracoes.sandbox import constantes as c
from app.integracoes.sandbox.semear import semear_tenant_sandbox


async def test_semear_e_idempotente(sessao_f13_a2: AsyncSession) -> None:
    primeiro = await semear_tenant_sandbox(sessao_f13_a2)
    segundo = await semear_tenant_sandbox(sessao_f13_a2)

    assert primeiro.tenant_id == segundo.tenant_id
    assert primeiro.tenant_ja_existia is False
    assert segundo.tenant_ja_existia is True
    assert primeiro.colaborador_ids == segundo.colaborador_ids
    assert (
        primeiro.marcacoes_criadas == len(primeiro.colaborador_ids) * c.DIAS_UTEIS_DE_HISTORICO * 4
    )
    assert segundo.marcacoes_criadas == 0


async def test_semear_cria_tres_colaboradores_com_marcacoes(
    sessao_f13_a2: AsyncSession,
) -> None:
    resultado = await semear_tenant_sandbox(sessao_f13_a2)

    assert len(resultado.colaborador_ids) == 3
    assert resultado.marcacoes_criadas == 3 * c.DIAS_UTEIS_DE_HISTORICO * 4

    for colaborador_id in resultado.colaborador_ids:
        contagem = (
            await sessao_f13_a2.execute(
                select(sa.func.count())
                .select_from(Marcacao)
                .where(
                    Marcacao.tenant_id == resultado.tenant_id,
                    Marcacao.colaborador_id == colaborador_id,
                )
            )
        ).scalar_one()
        assert contagem == c.DIAS_UTEIS_DE_HISTORICO * 4


async def test_admin_de_demonstracao_tem_so_as_duas_permissoes_de_api_clients(
    sessao_f13_a2: AsyncSession,
) -> None:
    resultado = await semear_tenant_sandbox(sessao_f13_a2)

    usuario = (
        await sessao_f13_a2.execute(select(Usuario).where(Usuario.id == resultado.admin_usuario_id))
    ).scalar_one()
    assert usuario.email == c.ADMIN_EMAIL
    assert usuario.status == "ativo"

    credencial = (
        await sessao_f13_a2.execute(
            select(Credencial).where(
                Credencial.usuario_id == usuario.id,
                Credencial.tipo == "senha",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one()
    assert verificar_hash(credencial.hash, c.senha_admin())
    assert not verificar_hash(credencial.hash, "senha-errada-de-proposito")

    codigos = set(
        (
            await sessao_f13_a2.execute(
                select(Permissao.codigo)
                .join(PerfilPermissao, PerfilPermissao.permissao_id == Permissao.id)
                .where(PerfilPermissao.tenant_id == resultado.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert codigos == {"api_clients.criar", "api_clients.ler"}


async def test_marcacoes_do_sandbox_sao_invisiveis_de_outro_tenant(
    sessao_f13_a2: AsyncSession,
) -> None:
    """Prova de isolamento por RLS (T8, "sem nenhum dado real do tenant de
    producao aparecer"): sob o contexto de um tenant QUALQUER diferente, as
    marcacoes sinteticas do sandbox nao aparecem em nenhuma consulta -- nao
    porque o codigo filtra por `ambiente`, mas porque RLS nega a linha
    inteira quando `app.tenant_id` nao bate."""
    resultado = await semear_tenant_sandbox(sessao_f13_a2)
    await sessao_f13_a2.flush()

    outro_tenant_id = uuid.uuid4()
    await aplicar_tenant(sessao_f13_a2, str(outro_tenant_id))

    contagem_marcacoes = (
        await sessao_f13_a2.execute(
            select(sa.func.count())
            .select_from(Marcacao)
            .where(Marcacao.colaborador_id.in_(resultado.colaborador_ids))
        )
    ).scalar_one()
    assert contagem_marcacoes == 0

    usuario_visivel = (
        await sessao_f13_a2.execute(select(Usuario).where(Usuario.id == resultado.admin_usuario_id))
    ).scalar_one_or_none()
    assert usuario_visivel is None

    # Nao commitamos neste teste: o fixture `sessao_f13_a2` da rollback no
    # fim (ver `conftest.py`). Isso mantem `ponto_f13_a2` limpo entre testes
    # -- o `admin_engine_sync_f13_a2` (conexao ADMINISTRATIVA separada, que so
    # enxergaria dado *commitado*) fica reservado para um teste adversarial
    # futuro que precise mesmo de commit; nenhum teste deste modulo commita
    # de proposito, para nao vazar o tenant sandbox entre execucoes da suite.
