"""Autenticacao e autorizacao da API. CONTRATO ENTRE FASES.

As assinaturas publicas deste modulo estao fixadas nos PCFs da F1 e da F2 e
NAO mudam sem RFC. A implementacao real e da F1 (agente A3): a partir daqui,
somente A3 edita este arquivo.

**Como o sujeito chega ate aqui.** `obter_sujeito()` nao recebe parametro
nenhum -- e a assinatura fixada. A validacao do JWT (F1/A1) publica
`usuario_id` e o middleware de tenant (F1/A2, endurecido na T2) publica o
tenant resolvido em `app.core.contexto` (`contexto.definir_usuario` /
`contexto.definir_tenant`), que sao `ContextVar` e por isso atravessam toda a
`Task` assincrona da requisicao sem precisar de injecao explicita. Esta
funcao le esse contexto, abre uma sessao propria (nao a `SessaoDb` do
handler, que esta rota alguma injeta aqui) e resolve o RBAC completo via
`app.identidade.rbac.resolucao.resolver_sujeito`. Sem `usuario_id`/`tenant_id`
no contexto (rota publica, ou JWT ainda nao validado), devolve o sujeito
anonimo -- o mesmo comportamento do stub original.

**Extensoes aditivas ao `Sujeito`.** `permissoes_sensiveis` e `alcance` sao
campos NOVOS, sempre com valor padrao: qualquer chamador que already construa
`Sujeito(usuario_id=..., tenant_id=..., ...)` com os sete campos originais
continua funcionando sem alteracao. Nenhuma assinatura de funcao publica
(`obter_sujeito`, `exigir_permissao`, `exigir_alcance`) mudou de forma
incompativel.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends

from app.core import contexto
from app.core.erros import ErroDeAplicacao


@dataclass(frozen=True, slots=True)
class AlcanceEfetivo:
    """Alcance hierarquico do sujeito, pre-computado na resolucao do RBAC.

    `amplo_tenant=True` quando alguma atribuicao vigente do usuario tem
    `escopo_tipo='tenant'`: alcanca qualquer alvo dentro do proprio tenant,
    sem checar os conjuntos abaixo. Caso contrario, cada dimensao contem os
    identificadores efetivamente alcancaveis -- ja expandidos pela arvore de
    departamentos quando a atribuicao tem `incluir_subordinados=True` (ver
    `app.identidade.rbac.escopo`).
    """

    amplo_tenant: bool = False
    empresas: frozenset[UUID] = frozenset()
    unidades: frozenset[UUID] = frozenset()
    departamentos: frozenset[UUID] = frozenset()
    equipes: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class Sujeito:
    """Quem esta chamando. A F1 preenche a partir do JWT validado."""

    usuario_id: UUID | None = None
    tenant_id: UUID | None = None
    email: str = ""
    perfis: tuple[str, ...] = ()
    permissoes: frozenset[str] = frozenset()
    delegacao_id: UUID | None = None
    autenticado: bool = False
    # --- Campos aditivos (T8/T9/T10 -- ver docstring do modulo) -------------
    #: Subconjunto de `permissoes` cujo exercicio grava `acessos_dados_sensiveis`.
    permissoes_sensiveis: frozenset[str] = frozenset()
    #: Alcance hierarquico agregado de todas as atribuicoes vigentes (e das
    #: delegacoes ativas). `None` para sujeito anonimo ou conta de maquina
    #: sem RBAC hierarquico (OAuth client_credentials, F1/A1/T7).
    alcance: AlcanceEfetivo | None = None
    #: Verdadeiro quando TODAS as atribuicoes de perfil vigentes do sujeito
    #: sao de perfil `somente_leitura`. Veta qualquer permissao de escrita
    #: (acao diferente de `ler`/`ler_sensivel`) mesmo que `perfil_permissoes`
    #: a conceda -- rede de seguranca contra conceder escrita por engano a um
    #: perfil pensado como auditor/fiscal.
    perfis_somente_leitura: bool = False


async def obter_sujeito() -> Sujeito:
    """Dependencia FastAPI: o sujeito da requisicao corrente.

    Ver docstring do modulo para a origem de `usuario_id`/`tenant_id`.
    """
    tenant_bruto = contexto.tenant_atual()
    usuario_bruto = contexto.usuario_atual()
    if not tenant_bruto or not usuario_bruto:
        return Sujeito()
    try:
        tenant_id = UUID(tenant_bruto)
        usuario_id = UUID(usuario_bruto)
    except ValueError:
        # Contexto com valor que nao e UUID (por exemplo, slug de tenant que
        # ainda nao passou pela resolucao de T2): sujeito anonimo, nao erro.
        # Rotas que exigem autenticacao vao recusar via `exigir_permissao`.
        return Sujeito()

    # Import tardio: evita ciclo de import entre `app.core.seguranca` (que o
    # `app.identidade.rbac.resolucao` importa para construir `Sujeito`) e o
    # proprio pacote de RBAC.
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
    from app.identidade.rbac.resolucao import resolver_sujeito

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, str(tenant_id))
        return await resolver_sujeito(sessao, tenant_id=tenant_id, usuario_id=usuario_id)


def exigir_permissao(codigo: str) -> Callable[..., Awaitable[Sujeito]]:
    """Fabrica de dependencia. `codigo` e o `x-permissao` da operacao.

    `PONTO-AUTH-002` quando nao ha sujeito autenticado (credencial ausente);
    `PONTO-PERM-001` quando o sujeito esta autenticado mas nao tem `codigo`
    entre as permissoes efetivas (ja considerando negacao explicita e
    delegacao -- ver `app.identidade.rbac.resolucao`). Permissao **sensivel**
    exercida com sucesso grava `acessos_dados_sensiveis` (LGPD).
    """

    async def _verificar(sujeito: Sujeito = Depends(obter_sujeito)) -> Sujeito:
        if not sujeito.autenticado:
            raise ErroDeAplicacao("PONTO-AUTH-002", contexto_log={"permissao": codigo})
        if codigo not in sujeito.permissoes:
            raise ErroDeAplicacao("PONTO-PERM-001", contexto_log={"permissao": codigo})
        acao = codigo.rpartition(".")[2]
        if sujeito.perfis_somente_leitura and acao not in ("ler", "ler_sensivel"):
            raise ErroDeAplicacao("PONTO-PERM-004", contexto_log={"permissao": codigo})
        if codigo in sujeito.permissoes_sensiveis:
            # Import tardio pelo mesmo motivo do bloco acima.
            from app.identidade.auditoria.hash_chain import registrar_acesso_sensivel_generico

            await registrar_acesso_sensivel_generico(sujeito, codigo)
        return sujeito

    return _verificar


def exigir_alcance(
    sujeito: Sujeito,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
) -> None:
    """Alcance hierarquico. `PONTO-PERM-002` quando o alvo esta fora da arvore.

    Sem `sujeito.alcance` resolvido (conta de maquina, ou sujeito anonimo que
    ja teria sido barrado por `exigir_permissao`), o comportamento e
    permissivo -- mesma semantica do stub original. Com `amplo_tenant`,
    qualquer alvo dentro do tenant passa. Caso contrario, cada dimensao
    informada precisa estar no conjunto alcancavel daquela dimensao.
    """
    alcance = sujeito.alcance
    if alcance is None or alcance.amplo_tenant:
        return None
    for alvo, alcancaveis in (
        (empresa_id, alcance.empresas),
        (unidade_id, alcance.unidades),
        (departamento_id, alcance.departamentos),
        (equipe_id, alcance.equipes),
    ):
        if alvo is not None and alvo not in alcancaveis:
            raise ErroDeAplicacao("PONTO-PERM-002")
    return None


def tenant_id_ou_erro(sujeito: Sujeito) -> UUID:
    """Estreita `sujeito.tenant_id` (`UUID | None`) para `UUID`.

    Depois de `exigir_permissao` confirmar `sujeito.autenticado`, o tenant
    sempre esta presente (`resolver_sujeito` so devolve `autenticado=True`
    com `tenant_id` preenchido) -- mas o tipo estatico de `Sujeito.tenant_id`
    continua `UUID | None`, entao os routers chamam esta funcao para obter um
    `UUID` sem `# type: ignore` espalhado. `PONTO-AUTH-002` aqui e defensivo:
    nunca deveria disparar na pratica.
    """
    if sujeito.tenant_id is None:
        raise ErroDeAplicacao("PONTO-AUTH-002")
    return sujeito.tenant_id
