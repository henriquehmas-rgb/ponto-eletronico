#!/usr/bin/env python
"""Semeia o tenant de demonstracao do sandbox (F13/A2, T8).

Uso, a partir de `apps/api`::

    set PONTO_SANDBOX_ADMIN_SENHA=...          # Windows (PowerShell: $env:...)
    export PONTO_SANDBOX_ADMIN_SENHA=...       # Linux/macOS
    python -m app.integracoes.sandbox.semear

O que entra (reaproveitando a estrutura de composicao de
`apps/api/migrations/seed_dev.py`, PCF F13 T8 -- sem editar aquele arquivo):

* 1 tenant de demonstracao (`constantes.TENANT_SLUG`), 1 empresa, 1 unidade;
* 1 REP-P `ativo` + `nsr_sequencias` (mesmo padrao de `tests/f5/conftest.py`);
* 3 colaboradores sinteticos com vinculo `apura_ponto=true` ativo;
* `constantes.DIAS_UTEIS_DE_HISTORICO` dias uteis de marcacoes (4 batimentos/
  dia/colaborador), gravadas por `app.marcacao.dominio.registro.
  persistir_marcacao` -- a MESMA rotina que a F5 usa em producao, entao NSR,
  CRC-16 e cadeia de hash desta massa sintetica sao tao legitimos quanto os de
  qualquer marcacao real (nunca uma reimplementacao paralela da regra);
* o catalogo de permissao + 1 perfil + 1 usuario administrador de
  demonstracao, com a UNICA permissao que o proxy do portal de desenvolvedor
  precisa (`api_clients.criar`/`api_clients.ler`) para provisionar, em nome do
  visitante, um `ApiClient` de sandbox de verdade via `POST /v1/admin/
  api-clients` (A1, T2).

O que NAO entra, de proposito (T8 pede "marcacoes sinteticas" e "assinar um
webhook", nao apuracao fechada): jornada/escala formal, banco de horas,
fechamento. Ver a nota de escopo no relatorio final da fase -- a apuracao
completa nao e necessaria para nenhum criterio de aceite de T7/T8, e
replica-la aqui seria reimplementar dominio de F4, vedado por esta fase (PCF
proibicao 8).

Idempotente: toda entidade e get-or-create por chave natural (slug, CNPJ,
codigo, matricula, e-mail, codigo de permissao). Rodar duas vezes nao duplica
nada -- a segunda execucao so confirma que o que existe bate com o que este
modulo declara. As marcacoes sinteticas sao a unica excecao parcial: a
checagem e "este colaborador ja tem marcacao no intervalo planejado?", nao
batimento a batimento (ver `_colaborador_tem_marcacoes_no_periodo`).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
import uuid
import zoneinfo
from dataclasses import dataclass

from ponto_contracts import (
    Colaborador,
    Credencial,
    Empresa,
    Marcacao,
    NsrSequencia,
    Perfil,
    PerfilPermissao,
    Permissao,
    RepP,
    Unidade,
    Usuario,
    UsuarioPerfil,
    Vinculo,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obter_configuracao
from app.core.log import obter_logger
from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
from app.identidade.autenticacao.senha import gerar_hash
from app.integracoes.sandbox import constantes as c
from app.integracoes.sandbox.dados_sinteticos import (
    COLABORADORES_SINTETICOS,
    ColaboradorSintetico,
    cpf_sintetico,
    gerar_dias_uteis,
    gerar_plano_de_marcacoes,
    matricula_sintetica,
)
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao

logger = obter_logger("integracoes.sandbox.semear")

_FUSO_SANDBOX = zoneinfo.ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True, slots=True)
class ResultadoSemeadura:
    """IDs e contadores da semeadura, para o CLI imprimir e para os testes
    conferirem sem precisar reconsultar tudo do zero."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    rep_p_id: uuid.UUID
    colaborador_ids: tuple[uuid.UUID, ...]
    vinculo_ids: tuple[uuid.UUID, ...]
    admin_usuario_id: uuid.UUID
    admin_email: str
    marcacoes_criadas: int
    tenant_ja_existia: bool


async def _resolver_ou_gerar_tenant_id(sessao: AsyncSession, slug: str) -> tuple[uuid.UUID, bool]:
    """Usa `fn_resolve_tenant` (SECURITY DEFINER, RFC-004/§2 do schema) para
    descobrir se o tenant ja existe ANTES de haver `app.tenant_id` -- a
    policy de RLS de `tenants` nao permitiria um SELECT direto aqui (compara
    `id` contra o tenant corrente, que ainda nao esta definido). Devolve
    `(tenant_id, ja_existia)`."""
    resultado = await sessao.execute(
        text("SELECT id FROM fn_resolve_tenant(:slug)"), {"slug": slug}
    )
    linha = resultado.first()
    if linha is not None:
        return linha[0], True
    return uuid.uuid4(), False


async def _criar_tenant_se_necessario(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, ja_existia: bool
) -> None:
    if ja_existia:
        return
    await sessao.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, plano, status, "
            " data_contratacao) "
            "VALUES (:id, :slug, :razao, :nome, 'enterprise', 'ativo', CURRENT_DATE)"
        ),
        {
            "id": tenant_id,
            "slug": c.TENANT_SLUG,
            "razao": c.TENANT_RAZAO_SOCIAL,
            "nome": c.TENANT_NOME_EXIBICAO,
        },
    )


async def _obter_ou_criar_empresa(sessao: AsyncSession, tenant_id: uuid.UUID) -> Empresa:
    existente = (
        await sessao.execute(
            select(Empresa).where(Empresa.tenant_id == tenant_id, Empresa.cnpj == c.EMPRESA_CNPJ)
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente
    empresa = Empresa(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tipo="matriz",
        cnpj=c.EMPRESA_CNPJ,
        razao_social=c.EMPRESA_RAZAO_SOCIAL,
        nome_fantasia=c.EMPRESA_NOME_FANTASIA,
        uf="GO",
        municipio="Goiania",
        codigo_ibge_municipio="5208707",
        fuso_horario="America/Sao_Paulo",
        ativo=True,
    )
    sessao.add(empresa)
    await sessao.flush()
    return empresa


async def _obter_ou_criar_unidade(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> Unidade:
    existente = (
        await sessao.execute(
            select(Unidade).where(
                Unidade.tenant_id == tenant_id,
                Unidade.empresa_id == empresa_id,
                Unidade.codigo == c.UNIDADE_CODIGO,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente
    unidade = Unidade(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        codigo=c.UNIDADE_CODIGO,
        nome=c.UNIDADE_NOME,
        tipo="sede",
        uf="GO",
        municipio="Goiania",
        codigo_ibge_municipio="5208707",
        fuso_horario="America/Sao_Paulo",
        geocerca_obrigatoria=False,
        geocerca_tolerancia_metros=50,
        ativo=True,
    )
    sessao.add(unidade)
    await sessao.flush()
    return unidade


async def _obter_ou_criar_rep_p(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> RepP:
    existente = (
        await sessao.execute(
            select(RepP).where(
                RepP.tenant_id == tenant_id,
                RepP.empresa_id == empresa_id,
                RepP.identificador == c.REP_P_IDENTIFICADOR,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente
    rep_p = RepP(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        identificador=c.REP_P_IDENTIFICADOR,
        tipo="rep_p",
        numero_inpi="00000000",
        cnpj_desenvolvedor=c.REP_P_CNPJ_DESENVOLVEDOR,
        razao_social_desenvolvedor=c.REP_P_RAZAO_SOCIAL_DESENVOLVEDOR,
        cnpj_empregador=c.EMPRESA_CNPJ,
        razao_social_empregador=c.EMPRESA_RAZAO_SOCIAL,
        versao_programa=c.REP_P_VERSAO_PROGRAMA,
        data_inicio_operacao=dt.date.today() - dt.timedelta(days=365),
        status="ativo",
    )
    sessao.add(rep_p)
    await sessao.flush()

    # `nsr_sequencias` nasce junto (mesmo par que o cadastro real de REP-P, F12,
    # cria -- ver `tests/f5/conftest.py`, mesma nota).
    sessao.add(
        NsrSequencia(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            rep_p_id=rep_p.id,
            proximo_nsr=1,
            ultimo_nsr_emitido=0,
        )
    )
    await sessao.flush()
    return rep_p


async def _obter_ou_criar_colaborador_e_vinculo(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    unidade_id: uuid.UUID,
    molde: ColaboradorSintetico,
) -> tuple[Colaborador, Vinculo]:
    matricula = matricula_sintetica(molde)
    colaborador = (
        await sessao.execute(
            select(Colaborador).where(
                Colaborador.tenant_id == tenant_id,
                Colaborador.empresa_id == empresa_id,
                Colaborador.matricula == matricula,
            )
        )
    ).scalar_one_or_none()
    if colaborador is None:
        colaborador = Colaborador(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            empresa_id=empresa_id,
            matricula=matricula,
            cpf=cpf_sintetico(molde),
            nome_completo=molde.nome_completo,
            status="ativo",
            data_admissao=dt.date.today() - dt.timedelta(days=180),
        )
        sessao.add(colaborador)
        await sessao.flush()

    vinculo = (
        await sessao.execute(
            select(Vinculo).where(
                Vinculo.tenant_id == tenant_id,
                Vinculo.colaborador_id == colaborador.id,
                Vinculo.matricula_esocial == matricula,
            )
        )
    ).scalar_one_or_none()
    if vinculo is None:
        vinculo = Vinculo(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            colaborador_id=colaborador.id,
            empresa_id=empresa_id,
            unidade_id=unidade_id,
            matricula_esocial=matricula,
            tipo_vinculo="empregado",
            data_inicio=dt.date.today() - dt.timedelta(days=180),
            principal=True,
            apura_ponto=True,
            status="ativo",
        )
        sessao.add(vinculo)
        await sessao.flush()
    return colaborador, vinculo


async def _colaborador_tem_marcacoes_no_periodo(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    inicio: dt.date,
    fim: dt.date,
) -> bool:
    inicio_dt = dt.datetime.combine(inicio, dt.time.min, tzinfo=_FUSO_SANDBOX)
    fim_dt = dt.datetime.combine(fim, dt.time.max, tzinfo=_FUSO_SANDBOX)
    contagem = (
        await sessao.execute(
            select(func.count())
            .select_from(Marcacao)
            .where(
                Marcacao.tenant_id == tenant_id,
                Marcacao.colaborador_id == colaborador_id,
                Marcacao.datahora_marcacao >= inicio_dt,
                Marcacao.datahora_marcacao <= fim_dt,
            )
        )
    ).scalar_one()
    return contagem > 0


async def _semear_marcacoes_do_colaborador(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    empresa_id: uuid.UUID,
    unidade_id: uuid.UUID,
    rep_p_id: uuid.UUID,
    colaborador: Colaborador,
    vinculo: Vinculo,
) -> int:
    dias = gerar_dias_uteis(terminando_em=dt.date.today(), quantidade=c.DIAS_UTEIS_DE_HISTORICO)
    if await _colaborador_tem_marcacoes_no_periodo(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador.id,
        inicio=dias[0],
        fim=dias[-1],
    ):
        return 0

    plano = gerar_plano_de_marcacoes(dias)
    criadas = 0
    for batimento in plano:
        datahora = dt.datetime.combine(batimento.data, batimento.hora, tzinfo=_FUSO_SANDBOX)
        dados = DadosMarcacao(
            rep_p_id=rep_p_id,
            empresa_id=empresa_id,
            cpf=colaborador.cpf,
            canal="api",
            datahora_marcacao=datahora,
            unidade_id=unidade_id,
            colaborador_id=colaborador.id,
            vinculo_id=vinculo.id,
            tipo_registro=batimento.tipo_registro,
            datahora_dispositivo=datahora,
            fuso_horario="America/Sao_Paulo",
        )
        await persistir_marcacao(sessao, tenant_id=tenant_id, dados=dados)
        criadas += 1
    return criadas


async def _obter_permissao(sessao: AsyncSession, *, recurso: str, acao: str) -> Permissao:
    """So LEITURA -- de proposito, nunca cria. `permissoes` e o catalogo
    GLOBAL do produto e a propria migration (`schema.sql`, bloco de GRANTs)
    revoga `INSERT/UPDATE/DELETE` de `ponto_app` nela: "somente leitura para
    a aplicacao" nao e so um comentario, e um privilegio de banco de verdade,
    e este script roda sob a MESMA role restrita que a API usa em producao
    (nunca uma role administrativa). Se a linha esperada nao existir, o
    catalogo do ambiente nao foi bootstrapado (passo de implantacao/ops, o
    mesmo que semeia `seed_dev.py::semeia_permissoes` em desenvolvimento) --
    isto e um erro de ambiente, nao algo que a semeadura do sandbox deva
    tentar corrigir escrevendo numa tabela que o proprio banco proibe."""
    codigo = f"{recurso}.{acao}"
    existente = (
        await sessao.execute(select(Permissao).where(Permissao.codigo == codigo))
    ).scalar_one_or_none()
    if existente is None:
        raise RuntimeError(
            f"Permissao '{codigo}' nao encontrada no catalogo global (tabela "
            "permissoes). O ambiente precisa ter o catalogo de permissoes "
            "bootstrapado (mesmo passo que semeia_permissoes() faz em "
            "apps/api/migrations/seed_dev.py) antes de rodar a semeadura do "
            "sandbox -- este script nunca escreve em `permissoes` (revogado "
            "de ponto_app pela propria migration)."
        )
    return existente


async def _obter_ou_criar_perfil_sandbox(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, permissoes: list[Permissao]
) -> Perfil:
    perfil = (
        await sessao.execute(
            select(Perfil).where(Perfil.tenant_id == tenant_id, Perfil.codigo == c.PERFIL_CODIGO)
        )
    ).scalar_one_or_none()
    if perfil is None:
        perfil = Perfil(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            codigo=c.PERFIL_CODIGO,
            nome=c.PERFIL_NOME,
            descricao=(
                "Perfil tecnico exclusivo do proxy do portal de desenvolvedor "
                "(apps/web/src/app/desenvolvedores/api/sandbox/route.ts). Concede "
                "so o minimo para provisionar ApiClient de sandbox em nome do "
                "visitante -- nunca acesso de gestao."
            ),
            sistema=False,
            escopo_padrao="tenant",
            somente_leitura=False,
            ativo=True,
        )
        sessao.add(perfil)
        await sessao.flush()

    for permissao in permissoes:
        vinculo_existente = (
            await sessao.execute(
                select(PerfilPermissao).where(
                    PerfilPermissao.tenant_id == tenant_id,
                    PerfilPermissao.perfil_id == perfil.id,
                    PerfilPermissao.permissao_id == permissao.id,
                )
            )
        ).scalar_one_or_none()
        if vinculo_existente is None:
            sessao.add(
                PerfilPermissao(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    perfil_id=perfil.id,
                    permissao_id=permissao.id,
                    concedida=True,
                )
            )
    await sessao.flush()
    return perfil


async def _obter_ou_criar_admin_demo(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, perfil_id: uuid.UUID
) -> Usuario:
    usuario = (
        await sessao.execute(
            select(Usuario).where(Usuario.tenant_id == tenant_id, Usuario.email == c.ADMIN_EMAIL)
        )
    ).scalar_one_or_none()
    if usuario is None:
        usuario = Usuario(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=c.ADMIN_EMAIL,
            nome_completo=c.ADMIN_NOME,
            tipo="humano",
            status="ativo",
            mfa_obrigatorio=False,
            email_verificado_em=dt.datetime.now(tz=dt.UTC),
        )
        sessao.add(usuario)
        await sessao.flush()

    # Credencial de senha: sempre REGRAVADA com o valor corrente de
    # `PONTO_SANDBOX_ADMIN_SENHA` (rotacionavel a cada execucao do script,
    # mesmo que o usuario ja existisse) -- diferente de seed_dev.py, que so
    # cria a credencial quando ainda nao existe: aqui o script E a unica
    # ferramenta de rotacao desta senha tecnica, entao "rodar de novo com
    # senha nova" precisa funcionar.
    hash_senha = gerar_hash(c.senha_admin())
    credencial = (
        await sessao.execute(
            select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.usuario_id == usuario.id,
                Credencial.tipo == "senha",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if credencial is None:
        sessao.add(
            Credencial(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                tipo="senha",
                hash=hash_senha,
                algoritmo="argon2id",
                trocar_no_proximo_acesso=False,
                ativo=True,
                ultima_troca_em=dt.datetime.now(tz=dt.UTC),
            )
        )
    else:
        credencial.hash = hash_senha
        credencial.ultima_troca_em = dt.datetime.now(tz=dt.UTC)
    await sessao.flush()

    vinculo_perfil = (
        await sessao.execute(
            select(UsuarioPerfil).where(
                UsuarioPerfil.tenant_id == tenant_id,
                UsuarioPerfil.usuario_id == usuario.id,
                UsuarioPerfil.perfil_id == perfil_id,
            )
        )
    ).scalar_one_or_none()
    if vinculo_perfil is None:
        sessao.add(
            UsuarioPerfil(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                perfil_id=perfil_id,
                escopo_tipo="tenant",
                incluir_subordinados=True,
            )
        )
        await sessao.flush()
    return usuario


async def semear_tenant_sandbox(sessao: AsyncSession) -> ResultadoSemeadura:
    """Ponto de entrada reaproveitavel (chamado pelo CLI abaixo e pelos
    testes de `apps/api/tests/f13/portal/`). A sessao recebida NAO e
    commitada aqui -- quem chama decide (o CLI commita; os testes
    tipicamente fazem rollback no fim, mesmo padrao de `tests/f5/
    conftest.py`)."""
    tenant_id, ja_existia = await _resolver_ou_gerar_tenant_id(sessao, c.TENANT_SLUG)
    # Ordem importa (mesma nota de `seed_dev.py::semeia`): a policy de RLS de
    # `tenants` compara `id` contra `app.tenant_id`, entao o contexto precisa
    # estar publicado ANTES do INSERT -- nunca depois.
    await aplicar_tenant(sessao, str(tenant_id))
    await _criar_tenant_se_necessario(sessao, tenant_id=tenant_id, ja_existia=ja_existia)

    empresa = await _obter_ou_criar_empresa(sessao, tenant_id)
    unidade = await _obter_ou_criar_unidade(sessao, tenant_id=tenant_id, empresa_id=empresa.id)
    rep_p = await _obter_ou_criar_rep_p(sessao, tenant_id=tenant_id, empresa_id=empresa.id)

    colaborador_ids: list[uuid.UUID] = []
    vinculo_ids: list[uuid.UUID] = []
    marcacoes_criadas = 0
    for molde in COLABORADORES_SINTETICOS:
        colaborador, vinculo = await _obter_ou_criar_colaborador_e_vinculo(
            sessao,
            tenant_id=tenant_id,
            empresa_id=empresa.id,
            unidade_id=unidade.id,
            molde=molde,
        )
        colaborador_ids.append(colaborador.id)
        vinculo_ids.append(vinculo.id)
        marcacoes_criadas += await _semear_marcacoes_do_colaborador(
            sessao,
            tenant_id=tenant_id,
            empresa_id=empresa.id,
            unidade_id=unidade.id,
            rep_p_id=rep_p.id,
            colaborador=colaborador,
            vinculo=vinculo,
        )

    permissoes = [
        await _obter_permissao(sessao, recurso=recurso, acao=acao)
        for _modulo, recurso, acao in c.PERMISSOES_ADMIN_DEMO
    ]
    perfil = await _obter_ou_criar_perfil_sandbox(
        sessao, tenant_id=tenant_id, permissoes=permissoes
    )
    admin = await _obter_ou_criar_admin_demo(sessao, tenant_id=tenant_id, perfil_id=perfil.id)

    logger.info(
        "tenant sandbox semeado",
        extra={
            "tenantId": str(tenant_id),
            "tenantJaExistia": ja_existia,
            "colaboradores": len(colaborador_ids),
            "marcacoesCriadasNestaExecucao": marcacoes_criadas,
        },
    )
    return ResultadoSemeadura(
        tenant_id=tenant_id,
        tenant_slug=c.TENANT_SLUG,
        empresa_id=empresa.id,
        unidade_id=unidade.id,
        rep_p_id=rep_p.id,
        colaborador_ids=tuple(colaborador_ids),
        vinculo_ids=tuple(vinculo_ids),
        admin_usuario_id=admin.id,
        admin_email=c.ADMIN_EMAIL,
        marcacoes_criadas=marcacoes_criadas,
        tenant_ja_existia=ja_existia,
    )


# ===========================================================================
# CLI
# ===========================================================================
def _monta_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Semeia o tenant de demonstracao do sandbox da API publica (F13/A2, T8)."
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Permite rodar mesmo quando AMBIENTE indica producao (nunca faca isso de verdade).",
    )
    return parser


async def _rodar_cli(argv: list[str] | None = None) -> int:
    args = _monta_parser().parse_args(argv)
    config = obter_configuracao()
    if config.producao and not args.forcar:
        print(
            "Recusado: AMBIENTE indica producao/homologacao. Use --forcar se voce "
            "tem certeza absoluta (nao deveria: sandbox e ferramenta de "
            "desenvolvimento e demonstracao, nunca de producao).",
            file=sys.stderr,
        )
        return 1

    try:
        c.senha_admin()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        resultado = await semear_tenant_sandbox(sessao)
        await sessao.commit()

    print(f"Tenant sandbox: {resultado.tenant_slug} ({resultado.tenant_id})")
    print(f"  {'ja existia' if resultado.tenant_ja_existia else 'criado agora'}")
    print(f"  colaboradores: {len(resultado.colaborador_ids)}")
    print(f"  marcacoes novas nesta execucao: {resultado.marcacoes_criadas}")
    print(f"  admin de demonstracao: {resultado.admin_email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_rodar_cli(argv))


if __name__ == "__main__":  # pragma: no cover - exercitado via subprocess nos testes
    raise SystemExit(main())
