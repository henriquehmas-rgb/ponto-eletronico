"""F14/A4 -- vetor 3: cross-tenant. Autenticado (ou apenas com o tenant
resolvido) no tenant A, tentar ler/gravar marcacao, template biometrico,
relatorio (dado de auditoria/LGPD) de outro tenant por manipulacao de
parametro, header ou reuso de sessao.

Cobre cinco caminhos distintos, todos contra Postgres real (RLS forcada, role
`ponto_app`, sem BYPASSRLS -- ADR-001):

1. **Reuso de sessao entre tenants (o caso mais grave, se existisse).**
   `app.identidade.tokens.middleware.AutenticacaoMiddleware` publica
   `usuario_id` a partir do JWT SEM checar se o claim `tenant` do token bate
   com o `X-Tenant` que `TenantMiddleware` resolveu (confirmado por leitura
   de codigo -- `middleware.py` linha 64, `contexto.definir_usuario(claims
   ["sub"])`, nenhuma comparacao com o tenant do contexto). Isto significa
   que a UNICA coisa que impede um usuario do tenant A de "logar como
   ninguem" no tenant B mandando `X-Tenant: B` com o proprio JWT de A e a
   camada de baixo: `app.identidade.rbac.resolucao.resolver_sujeito`
   consultando `usuarios` sob RLS escopada a B (a linha do usuario de A fica
   invisivel) MAIS uma checagem explicita de `usuario.tenant_id != tenant_id`
   (defesa em profundidade, linha 121 daquele modulo). Este teste prova que a
   segunda camada realmente segura o caso -- chamando exatamente a funcao que
   o middleware chamaria, com o "ataque" description (usuario_id de A, tenant
   de B) montado a mao.
2. Criar marcacao informando `colaboradorId` de OUTRO tenant.
3. Ler marcacao/meta de outro tenant pelo id (parametro de path).
4. Ler credencial biometrica de outro tenant pelo id.
5. `acessos_dados_sensiveis` (LGPD) de outro tenant nunca aparece na listagem.

Mais uma bateria de RLS DIRETA (SQL cru) sobre as tabelas que F14 passou a
escrever de verdade nesta fase (antes so tinham DDL, sem logica de negocio) --
`marcacoes_meta`, `biometria_templates`, `acessos_dados_sensiveis`,
`consentimentos`, `solicitacoes_titular` -- o mesmo padrao de
`tests/f1/tenancy/test_isolamento.py` (T3 da F1), reaplicado especificamente
as tabelas cujo CONTEUDO real so passou a existir com F14/A1/A3.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria import servico as biometria_servico
from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.identidade.rbac.resolucao import resolver_sujeito
from app.lgpd import acessos as lgpd_acessos
from app.marcacao.consulta import marcacoes as consulta_marcacoes
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f14.adversarial.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoDoisTenants,
    ContextoTenant,
    aplicar_tenant_teste,
    gerar_idempotency_key,
)


def _sujeito(contexto: ContextoTenant) -> Sujeito:
    return Sujeito(
        usuario_id=contexto.usuario_id,
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar", "marcacoes.ler", "marcacoes.ler_sensivel"}),
    )


async def _registrar_marcacao_valida(
    sessao: AsyncSession, contexto: ContextoTenant
) -> contrato.MarcacaoCriada:
    corpo = contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": "mobile",
            "dispositivoId": str(contexto.dispositivo_id),
            "latitude": GEOCERCA_LATITUDE,
            "longitude": GEOCERCA_LONGITUDE,
            "precisaoMetros": 5.0,
        }
    )
    resultado = await ingestao.registrar_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=_sujeito(contexto),
        ip_origem="203.0.113.40",
    )
    return resultado.resposta


# -----------------------------------------------------------------------------
# 1. Reuso de sessao/JWT entre tenants (usuario_id de A, tenant_id de B)
# -----------------------------------------------------------------------------
async def test_resolver_sujeito_com_usuario_de_a_e_tenant_de_b_devolve_anonimo(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Simula o que `core.seguranca.obter_sujeito()` faria se um atacante do
    tenant A enviasse `X-Tenant: B` mantendo o proprio JWT (usuario_id de A):
    chama `resolver_sujeito` exatamente como aquela funcao chama, com
    `usuario_id=tenant_a.usuario_id` e `tenant_id=tenant_b.tenant_id`.
    DEFENDIDO esperado: `Sujeito()` anonimo (sem permissoes), nunca as
    permissoes reais do usuario em A vazando para o contexto de B."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    sujeito_resolvido = await resolver_sujeito(
        sessao_f14a4, tenant_id=tenant_b.tenant_id, usuario_id=tenant_a.usuario_id
    )
    assert sujeito_resolvido.usuario_id is None
    assert sujeito_resolvido.tenant_id is None
    assert sujeito_resolvido.autenticado is False
    assert sujeito_resolvido.permissoes == frozenset(), (
        "VULNERAVEL se nao vazio: usuario do tenant A resolveu permissoes "
        "sob o contexto do tenant B."
    )


# -----------------------------------------------------------------------------
# 2. Criar marcacao com colaboradorId de outro tenant
# -----------------------------------------------------------------------------
async def test_criar_marcacao_com_colaborador_de_outro_tenant_e_recusada(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    corpo = contrato.MarcacaoCriar.model_validate(
        {
            # colaboradorId pertence ao tenant B; a sessao/tenant_id da
            # chamada e do tenant A.
            "colaboradorId": str(tenant_b.colaborador_id),
            "empresaId": str(tenant_b.empresa_id),
            "canal": "mobile",
            "dispositivoId": str(tenant_b.dispositivo_id),
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await ingestao.registrar_marcacao(
            sessao_f14a4,
            tenant_id=tenant_a.tenant_id,
            corpo=corpo,
            idempotency_key=gerar_idempotency_key(),
            sujeito=_sujeito(tenant_a),
            ip_origem="203.0.113.41",
        )
    assert excinfo.value.codigo == "PONTO-REC-001", (
        "VULNERAVEL se nao for PONTO-REC-001: colaborador de outro tenant "
        "foi aceito na criacao de marcacao."
    )

    total = await sessao_f14a4.execute(
        text("SELECT count(*) FROM marcacoes WHERE colaborador_id = :id"),
        {"id": str(tenant_b.colaborador_id)},
    )
    assert total.scalar_one() == 0


# -----------------------------------------------------------------------------
# 3. Ler marcacao/meta de outro tenant pelo id
# -----------------------------------------------------------------------------
async def test_ler_marcacao_e_meta_de_outro_tenant_por_id_e_404(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    resposta_b = await _registrar_marcacao_valida(sessao_f14a4, tenant_b)
    marcacao_id_b = resposta_b.marcacao.id
    assert marcacao_id_b is not None

    # Volta para o contexto do tenant A (a sessao continua "autenticada"
    # como A) e tenta ler o recurso de B pelo ID exato.
    await aplicar_tenant_teste(sessao_f14a4, tenant_a.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo_marcacao:
        await consulta_marcacoes.obter_marcacao(
            sessao_f14a4, tenant_id=tenant_a.tenant_id, marcacao_id=marcacao_id_b
        )
    assert excinfo_marcacao.value.codigo == "PONTO-REC-001"

    with pytest.raises(ErroDeAplicacao) as excinfo_meta:
        await consulta_marcacoes.obter_meta_marcacao(
            sessao_f14a4, tenant_id=tenant_a.tenant_id, marcacao_id=marcacao_id_b
        )
    assert excinfo_meta.value.codigo == "PONTO-REC-001"


# -----------------------------------------------------------------------------
# 4. Ler credencial/template biometrico de outro tenant
# -----------------------------------------------------------------------------
async def test_ler_biometria_de_outro_tenant_por_id_e_404(
    sessao_f14a4: AsyncSession,
    sessao_role_f14a4: AsyncSession,
    contexto_dois_tenants: ContextoDoisTenants,
) -> None:
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    biometria_id_b = uuid.uuid4()
    template_id_b = uuid.uuid4()
    await sessao_f14a4.execute(
        text(
            "INSERT INTO biometrias "
            "(id, tenant_id, colaborador_id, modalidade, status, origem_cadastro) "
            "VALUES (:id, :tenant_id, :colaborador_id, 'facial', 'ativa', 'web')"
        ),
        {
            "id": biometria_id_b,
            "tenant_id": tenant_b.tenant_id,
            "colaborador_id": tenant_b.colaborador_id,
        },
    )
    await sessao_f14a4.execute(
        text(
            "INSERT INTO biometria_templates "
            "(id, tenant_id, biometria_id, versao_modelo, dimensao, template_cifrado, "
            " iv, chave_id) "
            "VALUES (:id, :tenant_id, :biometria_id, 'arcface-r100-v1-teste', 128, "
            "        :cifrado, :iv, 'chave-teste-v1')"
        ),
        {
            "id": template_id_b,
            "tenant_id": tenant_b.tenant_id,
            "biometria_id": biometria_id_b,
            "cifrado": b"bytes-cifrados-fake-nao-real",
            "iv": b"iv-fake-12-bytes",
        },
    )
    # Commita: a checagem de RLS abaixo le por uma conexao/role DIFERENTE
    # (`sessao_role_f14a4`), que so enxerga dado ja commitado.
    await sessao_f14a4.commit()

    # Volta para o contexto do tenant A e tenta ler a credencial de B (mesma
    # sessao/role administrativa usada para a semeadura -- so confirma que a
    # CAMADA DE APLICACAO tem filtro explicito de tenant_id, independente de
    # RLS; a role `ponto` e superusuario/BYPASSRLS nesta instancia de teste,
    # entao este trecho por si so NAO prova isolamento por RLS -- ver
    # `test_bypass_rls.py` para o porque isso importa de verdade).
    await aplicar_tenant_teste(sessao_f14a4, tenant_a.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await biometria_servico.obter_biometria(
            sessao_f14a4,
            tenant_id=tenant_a.tenant_id,
            biometria_id=biometria_id_b,
            usuario_id=tenant_a.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"

    # RLS direta de VERDADE: `SELECT` cru SEM filtro de tenant_id, pela role
    # SEM BYPASSRLS (`sessao_role_f14a4`, ver conftest -- ADR-001 regra 4).
    # Isto e o que efetivamente prova isolamento por RLS; a mesma checagem
    # pela role `ponto` (superusuario) sempre "vazaria", nao por bug de
    # policy, e sim porque RLS nunca se aplica a superusuario.
    await aplicar_tenant_teste(sessao_role_f14a4, tenant_a.tenant_id)
    linha = (
        await sessao_role_f14a4.execute(
            text("SELECT id FROM biometria_templates WHERE id = :id"),
            {"id": str(template_id_b)},
        )
    ).first()
    assert linha is None, (
        "VULNERAVEL: template biometrico de outro tenant visivel via RLS "
        "mesmo pela role SEM BYPASSRLS -- isto indicaria uma policy "
        "genuinamente quebrada, nao so o achado de deployment de "
        "test_bypass_rls.py."
    )


# -----------------------------------------------------------------------------
# 5. acessos_dados_sensiveis (LGPD) nao vaza entre tenants
# -----------------------------------------------------------------------------
async def test_acessos_dados_sensiveis_de_outro_tenant_nao_aparece_na_listagem(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Gera uma marcacao suspeita/sensivel no tenant B (grava explicabilidade
    em `marcacoes_meta`, sinal antifraude), simula um acesso sensivel gravado
    para B, e confirma que `listar_acessos_sensiveis` chamado com
    `tenant_id=A` NUNCA devolve a linha de B -- mesmo que o `usuario_id`/
    `colaborador_id` do filtro nao seja informado (listagem "aberta")."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    acesso_id_b = uuid.uuid4()
    await sessao_f14a4.execute(
        text(
            "INSERT INTO acessos_dados_sensiveis "
            "(id, tenant_id, usuario_id, colaborador_id, categoria, acao, finalidade, "
            " base_legal, ocorrido_em) "
            "VALUES (:id, :tenant_id, :usuario_id, :colaborador_id, 'biometria', 'leitura', "
            "        'teste_adversarial_a4', 'execucao_contrato', now())"
        ),
        {
            "id": acesso_id_b,
            "tenant_id": tenant_b.tenant_id,
            "usuario_id": tenant_b.usuario_id,
            "colaborador_id": tenant_b.colaborador_id,
        },
    )
    await sessao_f14a4.flush()

    await aplicar_tenant_teste(sessao_f14a4, tenant_a.tenant_id)
    linhas, _tem_mais, _cursor = await lgpd_acessos.listar_acessos_sensiveis(
        sessao_f14a4,
        tenant_id=tenant_a.tenant_id,
        usuario_id=None,
        colaborador_id=None,
        categoria=None,
        acao=None,
        de=None,
        ate=None,
        cursor=None,
        limite=200,
        ordenar=None,
    )
    ids_vistos = {linha.id for linha in linhas}
    assert acesso_id_b not in ids_vistos, (
        "VULNERAVEL: registro de acesso sensivel do tenant B apareceu na " "listagem do tenant A."
    )


# -----------------------------------------------------------------------------
# RLS direta (SQL cru) nas tabelas cujo conteudo real e novo desta fase.
# -----------------------------------------------------------------------------
_TABELAS_F14_COM_CONTEUDO_REAL_NOVO = (
    "marcacoes_meta",
    "consentimentos",
    "solicitacoes_titular",
    "acessos_dados_sensiveis",
)


async def test_sql_direto_nao_ve_linha_do_outro_tenant_nas_tabelas_novas_de_f14(
    sessao_f14a4: AsyncSession,
    sessao_role_f14a4: AsyncSession,
    contexto_dois_tenants: ContextoDoisTenants,
) -> None:
    """Mesmo padrao de `tests/f1/tenancy/test_isolamento.py`
    (`test_sql_direto_nao_ve_linha_do_outro_tenant_em_10_tabelas`), reaplicado
    especificamente as tabelas que so passaram a ter LOGICA DE NEGOCIO real
    com F14/A1 (`marcacoes_meta`) e F14/A3 (`consentimentos`,
    `solicitacoes_titular`, `acessos_dados_sensiveis`) -- antes desta fase
    essas tabelas so tinham DDL, RLS generica ja auditada por A2
    (`test_auditoria_rls.py`) mas nunca exercitada com dado de verdade.

    A leitura de RLS de verdade usa `sessao_role_f14a4` (role SEM
    `BYPASSRLS`, ADR-001 regra 4) -- ver docstring do conftest e
    `test_bypass_rls.py` para o motivo de isto ser indispensavel: a role
    `ponto` usada para semear os dados e superusuario nesta instancia de
    teste, e RLS nunca se aplica a ela."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    resposta_b = await _registrar_marcacao_valida(sessao_f14a4, tenant_b)
    marcacao_id_b = resposta_b.marcacao.id
    assert marcacao_id_b is not None

    consentimento_id_b = uuid.uuid4()
    await sessao_f14a4.execute(
        text(
            "INSERT INTO consentimentos "
            "(id, tenant_id, colaborador_id, finalidade, versao_termo, texto_termo_ref, "
            " hash_termo, status, concedido_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, 'biometria_facial', 'v1-teste', "
            "        'ref-termo-teste', repeat('a', 64), 'concedido', now())"
        ),
        {
            "id": consentimento_id_b,
            "tenant_id": tenant_b.tenant_id,
            "colaborador_id": tenant_b.colaborador_id,
        },
    )
    solicitacao_id_b = uuid.uuid4()
    await sessao_f14a4.execute(
        text(
            "INSERT INTO solicitacoes_titular "
            "(id, tenant_id, colaborador_id, protocolo, requerente_nome, tipo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :protocolo, 'Titular de Teste B', "
            "        'acesso', 'recebida')"
        ),
        {
            "id": solicitacao_id_b,
            "tenant_id": tenant_b.tenant_id,
            "colaborador_id": tenant_b.colaborador_id,
            "protocolo": f"PROT-{uuid.uuid4().hex[:12]}",
        },
    )
    acesso_id_b = uuid.uuid4()
    await sessao_f14a4.execute(
        text(
            "INSERT INTO acessos_dados_sensiveis "
            "(id, tenant_id, usuario_id, colaborador_id, categoria, acao, finalidade, "
            " base_legal, ocorrido_em) "
            "VALUES (:id, :tenant_id, :usuario_id, :colaborador_id, 'biometria', 'leitura', "
            "        'teste_rls_direta', 'execucao_contrato', now())"
        ),
        {
            "id": acesso_id_b,
            "tenant_id": tenant_b.tenant_id,
            "usuario_id": tenant_b.usuario_id,
            "colaborador_id": tenant_b.colaborador_id,
        },
    )
    # Commita: a leitura abaixo usa uma conexao/role DIFERENTE
    # (`sessao_role_f14a4`), que so enxerga dado ja commitado.
    await sessao_f14a4.commit()

    ids_por_tabela_b = {
        "marcacoes_meta": marcacao_id_b,
        "consentimentos": consentimento_id_b,
        "solicitacoes_titular": solicitacao_id_b,
        "acessos_dados_sensiveis": acesso_id_b,
    }
    coluna_chave = {
        "marcacoes_meta": "marcacao_id",
        "consentimentos": "id",
        "solicitacoes_titular": "id",
        "acessos_dados_sensiveis": "id",
    }

    await aplicar_tenant_teste(sessao_role_f14a4, tenant_a.tenant_id)
    vazamentos: list[str] = []
    for tabela in _TABELAS_F14_COM_CONTEUDO_REAL_NOVO:
        coluna = coluna_chave[tabela]
        linha = (
            await sessao_role_f14a4.execute(
                text(f"SELECT {coluna} FROM {tabela} WHERE {coluna} = :id"),  # noqa: S608
                {"id": str(ids_por_tabela_b[tabela])},
            )
        ).first()
        if linha is not None:
            vazamentos.append(tabela)
    assert vazamentos == [], f"tenant A enxergou linha do tenant B em: {vazamentos}"
