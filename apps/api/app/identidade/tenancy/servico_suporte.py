"""Regras de `listarTenants` e `criarTenant` -- as duas operacoes CROSS-tenant
do suporte da SEEG.

Modulo separado de `app.identidade.tenancy.servico` de proposito: aquele
arquivo so recebe sessoes normais (`SessaoDb`, role `ponto_app_runtime`, sem
`BYPASSRLS`), e nenhuma funcao dele deve passar a aceitar a sessao de bypass
por descuido. Aqui, TODA funcao publica recebe a sessao de suporte
(`app/db/sessao_suporte.py`) e TODA funcao publica grava auditoria.

------------------------------------------------------------------------------
AUDITORIA REFORCADA -- o que foi decidido e por que
------------------------------------------------------------------------------
O requisito e que uma chamada bem-sucedida destas duas rotas fique rastreavel
COMO acesso cross-tenant, nao so como "mais uma leitura". A trilha
(`auditoria`) e encadeada por hash, e a formula do hash
(`app.identidade.auditoria.hash_chain.calcular_hash`) cobre, entre outros,
`evento`, `acao`, `entidade`, `usuario_id`, `valor_anterior` e `valor_novo` --
mas NAO cobre `metadados`. Logo:

* a **marca** de "isto foi bypass de RLS" vai no `evento`
  (`identidade.tenant.*_suporte_cross_tenant`) e em `valor_novo`
  (`{"bypass_rls": true, ...}`), os dois DENTRO da formula do hash: adulterar
  a marca depois quebra a cadeia e e detectado por `verificar_cadeia`;
* `metadados` repete a informacao em forma consultavel (role de banco usada,
  quantidade de tenants alcancados, ids), como conveniencia de investigacao --
  nunca como a unica evidencia.

Nao foi preciso estender o schema de `auditoria`: `evento` e TEXT livre,
`valor_novo`/`metadados` sao JSONB e `acao` ja aceita `ler` e `criar` no
CHECK. A unica escolha que o schema forcou e a do `tenant_id` da linha: a
coluna e NOT NULL e a cadeia de hash e POR tenant, entao a linha e gravada na
cadeia do tenant do PROPRIO usuario de suporte (o tenant da SEEG, de onde o
sujeito autenticou) -- que e onde uma auditoria do ATOR faz sentido e onde uma
verificacao de cadeia vai encontra-la. Para `criarTenant`, o tenant criado
aparece em `entidade_id`/`valor_novo`, ligando as duas pontas.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.db.sessao_suporte import ROLE_SUPORTE
from app.identidade.auditoria.hash_chain import registrar_auditoria_de_sujeito
from app.identidade.rbac import paginacao
from app.identidade.tenancy._contrato import contrato

#: Prefixo comum dos dois eventos. Entra na formula do hash da linha de
#: auditoria -- mudar o texto muda o hash de linhas FUTURAS (a cadeia
#: historica continua verificavel; ela recalcula com o valor gravado).
EVENTO_LISTAGEM = "identidade.tenant.listado_suporte_cross_tenant"
EVENTO_CRIACAO = "identidade.tenant.criado_suporte_cross_tenant"

_CAMPOS_TENANT = (
    "slug",
    "razao_social",
    "nome_exibicao",
    "documento",
    "plano",
    "status",
    "fuso_horario",
    "locale",
    "dominio_proprio",
    "limite_colaboradores",
    "data_contratacao",
    "data_cancelamento",
)


def _instantaneo(linha: Any) -> dict[str, Any]:
    return {campo: getattr(linha, campo, None) for campo in _CAMPOS_TENANT}


async def _auditar_acesso_cross_tenant(
    sessao: AsyncSession,
    sujeito: Sujeito,
    *,
    evento: str,
    acao: str,
    entidade_id: UUID | None,
    valor_novo: dict[str, Any],
    metadados: dict[str, Any],
) -> Any:
    """Grava a linha de auditoria obrigatoria da operacao de suporte.

    `registrar_auditoria_de_sujeito` exige `sujeito.tenant_id` -- garantido
    aqui porque as duas rotas passam por `exigir_permissao`, que so devolve
    sujeito autenticado (e `resolver_sujeito` so autentica com tenant
    resolvido).
    """
    return await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento=evento,
        entidade="tenants",
        entidade_id=entidade_id,
        acao=acao,
        valor_novo=valor_novo,
        metadados={
            "acesso": "suporte_seeg",
            "cross_tenant": True,
            "bypass_rls": True,
            "role_banco": ROLE_SUPORTE,
            **metadados,
        },
        mensagem=(
            "Acesso CROSS-tenant do suporte da SEEG, com bypass de Row Level "
            f"Security (role de banco {ROLE_SUPORTE})."
        ),
    )


async def listar_tenants(
    sessao: AsyncSession,
    *,
    sujeito: Sujeito,
    cursor: str | None,
    limite: int | None,
    status: str | None,
    plano: str | None,
    busca: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Lista tenants de TODA a instalacao (uma linha por cliente do SaaS).

    Sem nenhum filtro por tenant: e a sessao de suporte (BYPASSRLS) que torna
    isto possivel -- a mesma consulta com a sessao normal devolveria, no
    maximo, a linha do tenant corrente. `excluido_em IS NULL` fica de fora do
    filtro padrao de proposito: o suporte precisa enxergar tambem o tenant
    cancelado/soft-deleted, que e justamente o caso em que alguem liga
    pedindo ajuda. `status`/`plano`/`busca` seguem os enums do contrato.
    """
    consulta = sa.select(contrato.Tenant)
    if status:
        consulta = consulta.where(contrato.Tenant.status == status)
    if plano:
        consulta = consulta.where(contrato.Tenant.plano == plano)
    if busca:
        # Busca textual livre sobre os campos indexados/identificadores do
        # recurso, como o contrato descreve. `ilike` com escape do curinga do
        # usuario: `%` ou `_` digitados na busca sao literais, nao operadores.
        alvo = f"%{busca.replace('!', '!!').replace('%', '!%').replace('_', '!_')}%"
        consulta = consulta.where(
            sa.or_(
                contrato.Tenant.slug.ilike(alvo, escape="!"),
                contrato.Tenant.razao_social.ilike(alvo, escape="!"),
                contrato.Tenant.nome_exibicao.ilike(alvo, escape="!"),
            )
        )

    linhas, paginacao_bruta = await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.Tenant.criado_em,
        coluna_id=contrato.Tenant.id,
        cursor=cursor,
        limite=limite,
    )

    await _auditar_acesso_cross_tenant(
        sessao,
        sujeito,
        evento=EVENTO_LISTAGEM,
        acao="ler",
        entidade_id=None,
        valor_novo={
            "bypass_rls": True,
            "operacao": "listarTenants",
            "quantidade": len(linhas),
        },
        metadados={
            "filtros": {"status": status, "plano": plano, "busca": busca, "cursor": cursor},
            "tenants_retornados": [str(linha.id) for linha in linhas],
        },
    )
    return linhas, paginacao_bruta


async def criar_tenant(sessao: AsyncSession, *, sujeito: Sujeito, dados: Any) -> Any:
    """Provisiona a LINHA do tenant novo.

    A linha nasce fora de qualquer `app.tenant_id`: e a segunda razao de a
    rota precisar da sessao de suporte (o `WITH CHECK` de
    `pol_isolamento_tenant` compara `id` com `current_setting('app.tenant_id')`,
    impossivel de satisfazer para uma linha que ainda nao existe).

    ESCOPO: cria o tenant, nada mais. A descricao da operacao no contrato
    tambem menciona semear perfis de fabrica, tipos de tratamento, tipos de
    solicitacao, tipos de afastamento e catalogo de relatorios -- esses
    catalogos continuam sendo semeados por `migrations/seed_dev.py`, que abre
    a propria sessao administrativa e conhece a matriz de perfis inteira.
    Traze-los para dentro desta rota exigiria dar a `ponto_app_suporte`
    `INSERT` em perfis, permissoes, tipos_* e relatorios -- alargando uma
    credencial com `BYPASSRLS` de duas tabelas para uma dezena. A troca nao
    compensa: o provisionamento completo fica registrado como pendencia para
    quem desenhar o onboarding automatico (ver relatorio da tarefa).
    """
    valores = dados.model_dump(exclude_unset=True, by_alias=False)
    for campo, valor in list(valores.items()):
        if hasattr(valor, "value"):  # StrEnum (plano, status)
            valores[campo] = valor.value

    linha = contrato.Tenant(**valores, criado_por=sujeito.usuario_id)
    sessao.add(linha)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        # `uq_tenants_slug` (ou `ix_tenants_dominio_proprio`): o contrato ja
        # descreve PONTO-CONF-001 como "ja existe registro com a mesma chave
        # unica (... slug ...)".
        await sessao.rollback()
        raise ErroDeAplicacao(
            "PONTO-CONF-001",
            detalhe=f"Ja existe tenant com slug '{valores.get('slug')}'.",
            contexto_log={"slug": valores.get("slug")},
        ) from exc

    await _auditar_acesso_cross_tenant(
        sessao,
        sujeito,
        evento=EVENTO_CRIACAO,
        acao="criar",
        entidade_id=linha.id,
        valor_novo={"bypass_rls": True, "operacao": "criarTenant", **_instantaneo(linha)},
        metadados={"tenant_criado": str(linha.id)},
    )
    return linha
