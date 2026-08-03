"""Constantes do tenant de demonstracao (F13/A2, T8).

Todo identificador aqui e FIXO e deterministico de proposito: a semeadura
(`semear.py`) e get-or-create por chave natural (slug, CNPJ, matricula,
e-mail), entao rodar o script varias vezes nunca duplica nada -- a segunda
execucao so confere que o que existe bate com o que este modulo declara.

A UNICA coisa que NAO tem valor padrao neste modulo e a senha do usuario
administrador de demonstracao (mesma postura de seguranca de
`apps/api/migrations/seed_dev.py::VARIAVEL_SENHA`): ela so vem de variavel de
ambiente, nunca de codigo, porque e usada pelo proxy do portal
(`apps/web/src/app/desenvolvedores/api/sandbox/route.ts`) para autenticar
servidor-a-servidor em nome do visitante.
"""

from __future__ import annotations

import os

#: Slug do tenant de demonstracao. Overridavel só para ambientes onde
#: `sandbox-demo` colida com algo (nao deveria, mas nao custa permitir).
TENANT_SLUG = os.environ.get("PONTO_SANDBOX_TENANT_SLUG", "sandbox-demo")

TENANT_RAZAO_SOCIAL = "SEEG Ponto Sandbox de Demonstracao Ltda"
TENANT_NOME_EXIBICAO = "Sandbox SEEG Ponto"

#: CNPJ sintetico (14 digitos, so formato -- `dom_cnpj` nao valida digito
#: verificador, mesma convencao usada por `tests/f5/conftest.py`).
EMPRESA_CNPJ = "19000000000100"
EMPRESA_RAZAO_SOCIAL = "Sandbox Demonstracao Ltda"
EMPRESA_NOME_FANTASIA = "Sandbox SEEG Ponto"

UNIDADE_CODIGO = "SANDBOX-SEDE"
UNIDADE_NOME = "Sede de demonstracao"

REP_P_IDENTIFICADOR = "REP-SANDBOX-DEMO"
#: CNPJ do "desenvolvedor" do REP-P sintetico -- mesmo valor fixo usado por
#: `tests/f5/conftest.py` para o CNPJ da SEEG (nao e o CNPJ real da empresa,
#: e um dado de fixture).
REP_P_CNPJ_DESENVOLVEDOR = "60258502000149"
REP_P_RAZAO_SOCIAL_DESENVOLVEDOR = "SEEG Sistemas Ltda"
REP_P_VERSAO_PROGRAMA = "1.0.0-sandbox"

#: E-mail do usuario administrador de demonstracao. So existe para o proxy
#: server-side do portal (`route.ts`) autenticar em nome do visitante -- nunca
#: exposto ao navegador. NUNCA um TLD reservado (`.local`/`.test`/`.invalid`):
#: `EmailStr` (pydantic, usado por `LoginRequisicao`) rejeita nomes de
#: dominio de uso especial mesmo sem checagem de entregabilidade -- descoberto
#: validando esta fase contra o `POST /v1/auth/login` real.
ADMIN_EMAIL = os.environ.get(
    "PONTO_SANDBOX_ADMIN_EMAIL", f"portal-sandbox@{TENANT_SLUG}.ponto.seeg.com.br"
)
ADMIN_NOME = "Administrador do Sandbox (portal de desenvolvedor)"

#: Variavel de ambiente que carrega a senha em claro. SEM valor padrao --
#: o script recusa semear sem ela (mesma postura de seed_dev.py).
VARIAVEL_SENHA_ADMIN = "PONTO_SANDBOX_ADMIN_SENHA"


def senha_admin() -> str:
    """Le a senha do admin de demonstracao. Levanta se ausente."""
    senha = os.environ.get(VARIAVEL_SENHA_ADMIN)
    if not senha:
        raise RuntimeError(
            f"Variavel de ambiente {VARIAVEL_SENHA_ADMIN} ausente: a semeadura do "
            "sandbox recusa criar/rotacionar o usuario administrador de demonstracao "
            "sem uma senha explicita (mesma politica de "
            "apps/api/migrations/seed_dev.py::VARIAVEL_SENHA)."
        )
    return senha


#: Codigo da permissao RBAC que o admin de demonstracao precisa para chamar
#: `POST /v1/admin/api-clients` (RFC-016/T2, `x-permissao: api_clients.criar`)
#: e `GET /v1/admin/api-clients` (`api_clients.ler`). Nenhuma outra permissao
#: e concedida -- o usuario de demonstracao NUNCA enxerga tela de gestao,
#: so serve de identidade tecnica para o proxy do portal.
PERMISSOES_ADMIN_DEMO: tuple[tuple[str, str, str], ...] = (
    # (modulo, recurso, acao) -- mesma forma de CATALOGO_PERMISSOES em seed_dev.py.
    ("integracao", "api_clients", "criar"),
    ("integracao", "api_clients", "ler"),
)

PERFIL_CODIGO = "portal_sandbox"
PERFIL_NOME = "Portal de desenvolvedor (sandbox)"

#: Escopos OAuth concedidos ao `ApiClient` efemero que o proxy do portal cria
#: a cada visitante que clica em "criar cliente de sandbox". Deliberadamente
#: SEM `admin:*`: o visitante do portal nunca deve conseguir, a partir do
#: token de sandbox recebido, gerenciar outros clientes de API ou
#: configuracao do tenant -- so explorar o catalogo de leitura/escrita comum
#: da API publica (marcacoes, jornadas, tratamentos, fechamentos, relatorios,
#: fiscal de leitura, webhooks e integracoes, que sao literalmente as rotas
#: que esta fase protege com `exigir_escopo`, T1 de A1).
ESCOPOS_CLIENTE_PORTAL: tuple[str, ...] = (
    "colaboradores:ler",
    "jornadas:ler",
    "marcacoes:ler",
    "marcacoes:escrever",
    "tratamentos:ler",
    "fechamentos:ler",
    "relatorios:ler",
    "fiscal:ler",
    "webhooks:ler",
    "webhooks:escrever",
    "integracoes:ler",
    "integracoes:escrever",
)

#: Quantos dias uteis de historico sintetico semear por colaborador.
DIAS_UTEIS_DE_HISTORICO = 10

#: Ambiente do envelope de evento (`events.yaml`, campo `ambiente`) que
#: qualquer atividade deste tenant deve produzir, uma vez que o motor de
#: entrega de webhooks (A3, T11/T12) estampe o campo. Documentado aqui so
#: como referencia para os testes deste modulo -- A2 nao popula este campo
#: (ver nota de ownership no relatorio final da fase).
AMBIENTE_ENVELOPE_ESPERADO = "sandbox"
