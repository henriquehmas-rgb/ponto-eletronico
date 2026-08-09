"""Retrofit de deduplicação genuína de `idempotencia_generica.py` (F13) para
uma amostra representativa de rotas de escrita de F1-F12 (F14/A2).

**Por que middleware, e não `Depends()` nos routers, para ESTA parte.** O
PCF de F14 (§5, A2) pede o retrofit "via `Depends()`, sem tocar lógica de
negócio" -- e é exatamente isso que `app/comum/limitador_taxa.py::
exigir_limite_taxa_sessao` faz (só acrescenta um parâmetro à assinatura da
rota). Idempotência é diferente por construção: `abrir_operacao`/
`concluir_operacao` (`idempotencia_generica.py`, docstring do módulo)
precisam rodar ANTES e DEPOIS da lógica de negócio, na MESMA transação dela
-- é assim que F13 já implementou nas próprias rotas (`webhooks.py` etc.),
chamando as duas funções de dentro do CORPO do handler. Reproduzir isso nas
~130 rotas de F1-F12 exigiria editar o corpo de cada handler (não só
acrescentar `Depends()`), o que a ownership desta fase proíbe explicitamente
("routers/*.py: EDITAR SÓ PARA ACRESCENTAR Depends()... nunca tocar a
lógica de negócio dentro de cada rota").

A saída: um middleware ASGI que envolve a rota por fora, sem tocar nenhum
arquivo de router. Ele não reaproveita a MESMA sessão/transação do handler
(motivo pelo qual `idempotencia_generica.py` foi desenhado do jeito que foi
-- ver a docstring daquele módulo) porque não tem como: a sessão do handler
é aberta por uma dependência (`app/db/sessao.py::obter_sessao`) interna à
árvore de dependências do FastAPI, inacessível a um middleware que roda por
fora dela. Em vez disso, este middleware abre a PRÓPRIA sessão/transação,
curta, só para `idempotencia_chaves`, e decide se deixa o handler rodar:

1. Antes de chamar a rota: tenta abrir a operação (mesmo
   `pg_try_advisory_xact_lock` de `idempotencia_generica.abrir_operacao`).
   Se já concluída, a resposta ARMAZENADA é devolvida direto -- a rota
   NUNCA roda (dedup real, não só validação de cabeçalho). Se em conflito
   (chave em voo ou corpo diferente), `409` sem chamar a rota.
2. Só então chama a rota de verdade, na sessão PRÓPRIA dela (como sempre).
3. Depois que a rota responde: sucesso (`2xx`) grava a resposta para
   replay futuro e COMMITA; qualquer outro status faz ROLLBACK -- a
   tentativa falhada nunca "envenena" a chave (mesma semântica que
   `idempotencia_generica.py` já documenta para o caso do handler chamar as
   funções diretamente).

**Por que uma ALLOWLIST explícita, não todo `POST/PUT/PATCH/DELETE`.** Um
middleware genérico tocando toda escrita da API é um raio de explosão que
esta sessão não tem como revisar/testar com segurança (streaming, corpos
grandes, rotas que já têm idempotência própria -- `marcacoes.py`/F5,
`webhooks.py`/F13). A allowlist abaixo é a amostra representativa que o
critério de aceite de A2 pede (PCF F14 §5: "numa amostra representativa de
rotas de F1-F12"), escolhida a dedo por span de fase (F2/F3/F6) e por serem
rotas de criação simples (path sem parâmetro, corpo JSON pequeno, sem
upload). O resto de F1-F12 recebe só `Depends(exigir_idempotencia())`
(retrofit de verdade, mas limitado à validação do cabeçalho -- ver
`docs/backlog.md`, 2026-08-05, para o motivo da não-cobertura total).

**Casamento de rota: exato + template (2026-08-08, terceira passada).** Até
esta versão o middleware só casava `(método, caminho)` EXATO, o que excluía
por construção toda rota com parâmetro de path -- ou seja, praticamente todo
`PATCH`/`DELETE .../{id}` e toda ação `.../{id}/decidir|cancelar|...`, a
maioria das escritas restantes do sistema (lacuna registrada em
`docs/backlog.md`, 2026-08-08). Agora existem duas listas:

* `ROTAS_COM_DEDUP_REAL` -- caminho exato, casado por `frozenset`, O(1);
* `ROTAS_COM_DEDUP_REAL_TEMPLATE` -- caminho como template
  (`/v1/tratamentos/{id}/decidir`), casado por uma árvore de prefixos de
  SEGMENTOS montada uma única vez, no import.

O casamento por template segmenta o caminho por `/` e desce a árvore um
segmento por vez, tratando `{...}` como curinga de exatamente um segmento:
O(profundidade do caminho) por requisição, sem regex (nada de ReDoS, nada de
varredura O(rotas x caracteres)) e sem backtracking (o construtor do índice
recusa, no import, um conjunto de templates ambíguo). `tem_dedup_real` é a
única porta de entrada da decisão.

O que vai gravado como escopo continua sendo o caminho CONCRETO
(`"POST:/v1/tratamentos/<uuid-real>/decidir"`), nunca o template: dois
recursos diferentes com a mesma `Idempotency-Key` nunca colidem, e o replay
devolve a resposta daquele recurso específico.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, Final
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
)
from app.core import contexto, erros
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger
from app.db.sessao import aplicar_tenant, fabrica_de_sessoes

logger = obter_logger("idempotencia_middleware")

ProximoMiddleware = Callable[[Request], Awaitable[Response]]

#: Amostra representativa (F14/A2), expandida em 2026-08-07 (task de backlog
#: "idempotência genérica ainda falta em ~120 rotas") -- ver docstring do
#: módulo. `(método, caminho)` EXATO (nenhuma rota AQUI tem parâmetro de
#: path, de propósito: mantém o casamento O(1), sem regex, sem risco de
#: casar caminho errado; rotas COM parâmetro de path vivem em
#: `ROTAS_COM_DEDUP_REAL_TEMPLATE`, ver abaixo). Toda rota abaixo já EXIGE
#: `Idempotency-Key` via
#: `Depends(exigir_idempotencia())` no próprio router (contrato inalterado
#: por esta expansão, só a garantia de dedup real passa a valer) -- expansão
#: mantém o mesmo critério de seleção original (criação simples, corpo JSON
#: pequeno, sem upload/streaming, path sem parâmetro), e exclui
#: deliberadamente: rotas de autenticação/sessão/SSO (login, logout, MFA,
#: refresh, recuperação de senha, emissão de token OAuth -- semântica de
#: "sempre gera algo novo", não de criação deduplicável), geração de arquivo
#: fiscal (`fiscal/aej`, `fiscal/afd`, `fiscal/rep-ps`, `.../assinar` --
#: crítico de conformidade legal, fora do escopo de um retrofit mecânico),
#: rotas de importação/sincronização em lote (`colaboradores/importar`,
#: `marcacoes/sincronizar-offline`, `importacoes` -- corpo potencialmente
#: grande), ações que não são "criar um recurso" (`apuracoes/recalcular`,
#: `banco-horas/simular`, `auditoria/verificar-cadeia` -- disparo de
#: processamento/verificação sobre dado imutável, não criação -- rodar duas
#: vezes já produz o mesmo resultado por natureza, dedup aqui não agrega
#: nada), e rotas que já têm idempotência própria (`marcacoes.py`/F5,
#: `webhooks.py`/F13, `admin/api-clients`/F13 -- `criarApiClient` já chama
#: `abrir_operacao`/`concluir_operacao` direto no corpo do handler, mesmo
#: padrão de `webhooks.py`) ou ainda são `501` (`tenants.py`). PUT/PATCH/
#: DELETE ficaram de fora DESTA lista porque ela só casa caminho exato e
#: praticamente toda escrita desses métodos tem parâmetro de path -- a
#: terceira passada (2026-08-08) fechou essa lacuna em
#: `ROTAS_COM_DEDUP_REAL_TEMPLATE`.
ROTAS_COM_DEDUP_REAL: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("POST", "/v1/colaboradores"),  # F2
        ("POST", "/v1/empresas"),  # F2
        ("POST", "/v1/unidades"),  # F2
        ("POST", "/v1/departamentos"),  # F2
        ("POST", "/v1/contratos"),  # F2
        ("POST", "/v1/escalas"),  # F3
        ("POST", "/v1/feriados"),  # F3
        ("POST", "/v1/horarios"),  # F3
        ("POST", "/v1/afastamentos"),  # F9b
        ("POST", "/v1/dispositivos"),  # F6
        ("POST", "/v1/admin/perfis"),  # F1
        ("POST", "/v1/admin/usuarios"),  # F1
        ("POST", "/v1/banco-horas/contas"),  # F4
        ("POST", "/v1/banco-horas/politicas"),  # F4
        ("POST", "/v1/banco-horas/quitacoes"),  # F4
        ("POST", "/v1/cargos"),  # F2
        ("POST", "/v1/centros-custo"),  # F2
        ("POST", "/v1/delegacoes"),  # F10
        ("POST", "/v1/equipes"),  # F9b
        ("POST", "/v1/fechamentos"),  # F10
        ("POST", "/v1/feriado-conjuntos"),  # F3
        ("POST", "/v1/jornadas"),  # F3
        ("POST", "/v1/lgpd/consentimentos"),  # F14
        ("POST", "/v1/lgpd/solicitacoes-titular"),  # F14
        ("POST", "/v1/periodos"),  # F10
        ("POST", "/v1/relatorios/agendamentos"),  # F11
        ("POST", "/v1/solicitacoes"),  # F10
        ("POST", "/v1/terminais"),  # F6
        ("POST", "/v1/tipos-afastamento"),  # F9b
        ("POST", "/v1/tipos-solicitacao"),  # F10
        ("POST", "/v1/tratamentos"),  # F4
        ("POST", "/v1/turnos"),  # F3
        ("POST", "/v1/vinculos"),  # F2
        ("POST", "/v1/biometrias"),  # F14
        ("POST", "/v1/espelhos"),  # F10 (segunda passada, 2026-08-08)
    }
)

#: Terceira passada (2026-08-08): rotas de escrita COM parâmetro de path,
#: habilitadas pelo casamento por template (`_casa_template`, abaixo). Toda
#: entrada aqui já EXIGE `Idempotency-Key` no próprio router (verificado
#: rota a rota via `app.openapi()`, não `app.routes` -- `_IncludedRouter`),
#: então o contrato não muda: o que muda é a chave passar a deduplicar de
#: verdade em vez de só ser validada e descartada.
#:
#: **Por que dedup aqui não é redundante com a semântica HTTP.** `PATCH`/
#: `DELETE` já são idempotentes quanto ao ESTADO final do recurso, mas não
#: quanto aos EFEITOS COLATERAIS de reexecutar o handler: nova linha de
#: auditoria, nova notificação, novo evento de webhook, novo recálculo
#: disparado. As ações de decisão/transição de estado (`.../decidir`,
#: `.../cancelar`, `.../conferir`, `.../reabrir`, `.../encerrar`,
#: `.../validar`) não são idempotentes nem quanto ao estado (a segunda
#: chamada tipicamente falha com conflito de estado, ou pior, aprova duas
#: vezes). O escopo gravado é `MÉTODO:caminho CONCRETO` (com o id real,
#: não o template), então a dedup é por recurso, nunca entre recursos
#: distintos que compartilham o mesmo template.
#:
#: Exclusões deliberadas desta passada (as 34 rotas de escrita que
#: permanecem só com validação de cabeçalho), com o motivo de cada família:
#:
#: * **Autenticação/sessão/SSO** (`auth/login`, `auth/logout`,
#:   `auth/mfa/verificar`, `auth/reautenticar`, `auth/refresh`,
#:   `auth/senha/recuperar`, `auth/senha/redefinir`, `auth/token`,
#:   `DELETE auth/sessoes/{id}`, `PUT admin/sso/provedores`,
#:   `POST sso/saml/acs`) -- exclusão mantida da passada anterior:
#:   semântica de "sempre emite credencial nova", e um replay devolvendo
#:   token/sessão armazenados seria um risco de segurança, não um ganho.
#:   `admin/sso/provedores` entra na mesma família por precaução: replay de
#:   configuração de SSO pode deixar um tenant sem conseguir autenticar.
#:   `sso/saml/acs` sequer declara `Idempotency-Key` no contrato.
#: * **Geração/assinatura de arquivo fiscal e documento legal**
#:   (`fiscal/aej`, `fiscal/afd`, `fiscal/rep-ps`,
#:   `fiscal/arquivos/{id}/assinar`, `espelhos/{id}/assinar`) -- crítico de
#:   conformidade legal, fora do escopo de um retrofit mecânico (exclusão
#:   mantida das passadas anteriores, agora explicitamente estendida a
#:   `espelhos/{id}/assinar`, que é assinatura de documento com o mesmo
#:   peso jurídico).
#: * **Processamento assíncrono pesado / verificação sobre dado imutável**
#:   (`apuracoes/recalcular`, `banco-horas/simular`,
#:   `auditoria/verificar-cadeia`, `terminais/{id}/sincronizar`,
#:   `integracoes/folha/{id}/exportar`) -- disparo de processamento ou
#:   leitura verificadora, não criação de recurso; rodar duas vezes já
#:   converge para o mesmo resultado por natureza.
#: * **Importação/sincronização em lote** (`colaboradores/importar`,
#:   `marcacoes/sincronizar-offline`, `importacoes`) -- corpo
#:   potencialmente grande, que este middleware precisaria ler inteiro em
#:   memória para calcular o hash.
#: * **Rotas que JÁ têm dedup própria no corpo do handler**
#:   (`POST marcacoes` / F5; `POST|PATCH|DELETE webhooks`,
#:   `webhooks/{id}/entregas/{id}/reenviar` / F13; `POST admin/api-clients`,
#:   `POST admin/api-clients/{id}/chaves`,
#:   `DELETE admin/api-clients/{id}/chaves/{id}` / F13; `POST integracoes/folha`
#:   (`integracoesFolha.criar`), `integracoes/folha/{id}/exportar`,
#:   `importacoes` / F13) -- chamam `abrir_operacao`/`concluir_operacao`
#:   diretamente, na MESMA transação da lógica de negócio (dedup
#:   estritamente melhor que a deste middleware). `POST integracoes/folha`
#:   estava, até 08/08/2026, duplicado nas DUAS listas (esta e
#:   `ROTAS_COM_DEDUP_REAL`) -- como os escopos de dedup eram diferentes
#:   (`POST:/v1/integracoes/folha` vs `integracoesFolha.criar`) não havia
#:   deadlock, só uma chave redundante em `idempotencia_chaves` e a dedup do
#:   handler nunca chegando a rodar no replay (o middleware curto-circuitava
#:   antes). Removida da lista exata: a dedup própria do handler, na mesma
#:   transação, é a fonte de verdade correta aqui.
#: * **Sem `Idempotency-Key` no contrato**
#:   (`PUT relatorios/preferencias-colunas`) -- adicionar dedup aqui faria o
#:   middleware recusar (`PONTO-IDEM-001`) uma chamada hoje válida: seria
#:   quebra de contrato, não hardening.
#: * **`POST tenants` / `criarTenant`** -- deixou de ser `501` (rota
#:   cross-tenant do suporte da SEEG, `0005_role_suporte_bypassrls`), mas
#:   continua fora desta lista: o handler roda numa sessao de banco PROPRIA
#:   (`SessaoDbSuporte`, role com `BYPASSRLS`), enquanto este middleware
#:   registra a operacao pela sessao comum, escopada ao tenant da requisicao.
#:   Misturar as duas transacoes num replay e exatamente o tipo de sutileza
#:   que nao cabe num retrofit mecanico; a rota ja falha fechada em duplicata
#:   pelo `uq_tenants_slug` (`409 PONTO-CONF-001`).
ROTAS_COM_DEDUP_REAL_TEMPLATE: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # F1 -- administração de usuários
        ("PATCH", "/v1/admin/usuarios/{usuarioId}"),
        # F9b -- afastamentos
        ("PATCH", "/v1/afastamentos/{afastamentoId}"),
        ("DELETE", "/v1/afastamentos/{afastamentoId}"),
        ("PATCH", "/v1/tipos-afastamento/{tipoId}"),
        # F10 -- fluxo de aprovação/fechamento (decisões com notificação e
        # trilha de auditoria: o caso mais forte desta passada)
        ("POST", "/v1/aprovacoes/{aprovacaoId}/decidir"),
        ("POST", "/v1/solicitacoes/{solicitacaoId}/cancelar"),
        ("POST", "/v1/fechamentos/{fechamentoId}/conferir"),
        ("POST", "/v1/fechamentos/{fechamentoId}/reabrir"),
        # F14 -- biometria
        ("DELETE", "/v1/biometrias/{biometriaId}"),
        ("POST", "/v1/biometrias/{biometriaId}/validar"),
        # F2 -- cadastro/estrutura organizacional
        ("PATCH", "/v1/cargos/{cargoId}"),
        ("PATCH", "/v1/centros-custo/{centroCustoId}"),
        ("PATCH", "/v1/departamentos/{departamentoId}"),
        ("DELETE", "/v1/departamentos/{departamentoId}"),
        ("PATCH", "/v1/equipes/{equipeId}"),
        ("POST", "/v1/equipes/{equipeId}/membros"),
        ("PATCH", "/v1/colaboradores/{colaboradorId}"),
        ("DELETE", "/v1/colaboradores/{colaboradorId}"),
        ("PUT", "/v1/colaboradores/{colaboradorId}/gestores"),
        ("PATCH", "/v1/contratos/{contratoId}"),
        ("PATCH", "/v1/empresas/{empresaId}"),
        ("DELETE", "/v1/empresas/{empresaId}"),
        ("PATCH", "/v1/unidades/{unidadeId}"),
        ("DELETE", "/v1/unidades/{unidadeId}"),
        ("POST", "/v1/unidades/{unidadeId}/redes-permitidas"),
        ("DELETE", "/v1/unidades/{unidadeId}/redes-permitidas/{redeId}"),
        ("POST", "/v1/vinculos/{vinculoId}/encerrar"),
        # F6 -- dispositivos e terminais (o `sincronizar` de terminal fica
        # de fora, ver exclusões acima)
        ("PATCH", "/v1/dispositivos/{dispositivoId}"),
        ("DELETE", "/v1/dispositivos/{dispositivoId}"),
        ("POST", "/v1/dispositivos/{dispositivoId}/vincular"),
        ("PATCH", "/v1/terminais/{terminalId}"),
        ("DELETE", "/v1/terminais/{terminalId}"),
        # F3 -- jornadas, escalas, feriados
        ("PATCH", "/v1/escalas/{escalaId}"),
        ("DELETE", "/v1/escalas/{escalaId}"),
        ("POST", "/v1/escalas/{escalaId}/atribuicoes"),
        ("PATCH", "/v1/turnos/{turnoId}"),
        ("PATCH", "/v1/horarios/{horarioId}"),
        ("PATCH", "/v1/jornadas/{jornadaId}"),
        ("DELETE", "/v1/jornadas/{jornadaId}"),
        ("POST", "/v1/vinculos/{vinculoId}/jornadas"),
        ("PATCH", "/v1/feriado-conjuntos/{conjuntoId}"),
        ("DELETE", "/v1/feriado-conjuntos/{conjuntoId}"),
        ("DELETE", "/v1/feriados/{feriadoId}"),
        # F4 -- tratamentos e ocorrências de apuração
        ("PATCH", "/v1/tratamentos/{tratamentoId}"),
        ("DELETE", "/v1/tratamentos/{tratamentoId}"),
        ("POST", "/v1/tratamentos/{tratamentoId}/decidir"),
        ("PATCH", "/v1/ocorrencias/{ocorrenciaId}"),
        # F14 -- LGPD
        ("DELETE", "/v1/lgpd/consentimentos/{consentimentoId}"),
        # F14 -- decisão de revisão antifraude (`marcacoes.py`, mas NÃO a
        # rota de criação de marcação: esta não tem dedup própria e é uma
        # decisão humana com efeito colateral de auditoria)
        ("POST", "/v1/marcacoes/{marcacaoId}/meta/decisao"),
        # Tenant (só as duas rotas realmente implementadas -- `criarTenant`
        # continua `501`)
        ("PATCH", "/v1/tenants/{tenantId}"),
        ("PUT", "/v1/tenants/{tenantId}/configuracoes/{chave}"),
    }
)

#: Chave sentinela que marca "um template termina neste nó" no índice de
#: templates. É uma tupla vazia de propósito: todo segmento de caminho é
#: `str`, então nunca colide com um segmento real (um segmento literal
#: chamado `""` é impossível -- segmentos vazios são descartados).
_MARCA_FIM: Final[tuple[()]] = ()

#: Segmento curinga do índice -- casa exatamente UM segmento de caminho.
_CURINGA: Final[str] = "*"

#: Nó do índice: `segmento -> nó filho`, mais `_MARCA_FIM -> True` na folha.
#: Valor tipado como `Any` de propósito (o dicionário é heterogêneo por
#: construção) -- a leitura em `_casa_template` sempre confere `isinstance`
#: antes de descer, então o tipo largo aqui não vaza para fora do módulo.
_NoIndice = dict[object, Any]


def _segmentos(caminho: str) -> tuple[str, ...]:
    """Segmenta o caminho por `/`, descartando segmentos vazios.

    `str.split` é linear no tamanho do caminho e não faz backtracking --
    diferente de casar um regex por rota, que seria O(rotas x caminho) e
    abriria espaço para ReDoS num caminho controlado pelo cliente.
    """
    return tuple(parte for parte in caminho.split("/") if parte)


def _construir_indice(templates: frozenset[tuple[str, str]]) -> _NoIndice:
    """Monta a árvore de prefixos `método -> segmento -> ... -> _MARCA_FIM`.

    Roda UMA vez, no import. Recusa (`ValueError`) um conjunto de templates
    em que um mesmo nó tenha ao mesmo tempo filho literal e filho curinga:
    nesse caso o casamento sem backtracking (abaixo) poderia entrar pelo
    ramo literal, morrer mais fundo e devolver "não casa" para um caminho
    que o ramo curinga casaria. Falhar alto no import é preferível a um
    falso negativo silencioso -- e nenhum template real do sistema hoje
    precisa dessa ambiguidade.
    """
    raiz: _NoIndice = {}
    for metodo, template in templates:
        no: _NoIndice = raiz.setdefault(metodo, {})
        for segmento in _segmentos(template):
            chave = _CURINGA if segmento.startswith("{") and segmento.endswith("}") else segmento
            no = no.setdefault(chave, {})
        no[_MARCA_FIM] = True

    pendentes: list[_NoIndice] = [raiz]
    while pendentes:
        no = pendentes.pop()
        filhos = [chave for chave in no if chave != _MARCA_FIM]
        if _CURINGA in filhos and len(filhos) > 1:
            raise ValueError(
                "ROTAS_COM_DEDUP_REAL_TEMPLATE tem literal e curinga no mesmo nível: "
                f"{sorted(str(c) for c in filhos)}"
            )
        for chave in filhos:
            filho = no[chave]
            if isinstance(filho, dict):
                pendentes.append(filho)
    return raiz


_INDICE_TEMPLATES: Final[_NoIndice] = _construir_indice(ROTAS_COM_DEDUP_REAL_TEMPLATE)


def _casa_template(metodo: str, caminho: str) -> bool:
    """Casa `(método, caminho concreto)` contra `ROTAS_COM_DEDUP_REAL_TEMPLATE`.

    O(profundidade do caminho): uma busca em dicionário por segmento, sem
    regex, sem varrer a lista de rotas e sem backtracking (garantido pela
    validação de `_construir_indice`). O curinga só é tentado quando não há
    filho literal, então caminho literal sempre ganha do curinga.

        >>> _casa_template("POST", "/v1/tratamentos/9f3.../decidir")
        True
        >>> _casa_template("POST", "/v1/tratamentos/9f3.../outra-coisa")
        False
    """
    no = _INDICE_TEMPLATES.get(metodo)
    if not isinstance(no, dict):
        return False
    for segmento in _segmentos(caminho):
        proximo = no.get(segmento)
        if proximo is None:
            proximo = no.get(_CURINGA)
        if not isinstance(proximo, dict):
            return False
        no = proximo
    return _MARCA_FIM in no


def tem_dedup_real(metodo: str, caminho: str) -> bool:
    """Única porta de entrada da decisão "esta rota deduplica de verdade?".

    Caminho exato primeiro (`frozenset`, O(1)); só então o índice de
    templates. Exposta (sem `_`) porque os testes de regressão da allowlist
    a usam para provar cobertura sem subir HTTP.
    """
    return (metodo, caminho) in ROTAS_COM_DEDUP_REAL or _casa_template(metodo, caminho)


_CABECALHOS_NAO_REPASSADOS: Final[frozenset[str]] = frozenset(
    {"content-length", "content-encoding", "transfer-encoding"}
)


def _resposta_direta(
    status: int, corpo: dict[str, object], cabecalhos: dict[str, str] | None = None
) -> Response:
    return erros.RespostaProblema(status_code=status, content=corpo, headers=cabecalhos or None)


class IdempotenciaRetrofitMiddleware(BaseHTTPMiddleware):
    """Ver docstring do módulo. Só age nas rotas de `ROTAS_COM_DEDUP_REAL`
    (caminho exato) e `ROTAS_COM_DEDUP_REAL_TEMPLATE` (caminho com
    parâmetro), unificadas por `tem_dedup_real`."""

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        if not tem_dedup_real(request.method, request.url.path):
            return await call_next(request)

        chave_bruta = (request.headers.get("Idempotency-Key") or "").strip()
        if not chave_bruta:
            status, corpo = erros.montar_problema(codigo="PONTO-IDEM-001", caminho=request.url.path)
            return _resposta_direta(status, corpo)

        tenant_bruto = contexto.tenant_atual()
        if not tenant_bruto:
            # Sem tenant resolvido, deixa a rota seguir e falhar do jeito
            # normal (`obter_sessao` recusa com `PONTO-VAL-011`) -- não é
            # papel deste middleware inventar esse erro.
            return await call_next(request)

        try:
            tenant_id = UUID(tenant_bruto)
        except ValueError:
            return await call_next(request)

        corpo_bruto = await request.body()
        chave = ChaveIdempotencia(
            valor=chave_bruta[:255],
            corpo_hash=hashlib.sha256(corpo_bruto).hexdigest(),
        )
        escopo = f"{request.method}:{request.url.path}"

        fabrica = fabrica_de_sessoes()
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant_id))
            try:
                resultado = await abrir_operacao(
                    sessao, tenant_id=tenant_id, escopo=escopo, chave=chave
                )
            except ErroDeAplicacao as exc:
                await sessao.rollback()
                status, corpo = erros.montar_problema(
                    codigo=exc.codigo,
                    caminho=request.url.path,
                    detalhe=exc.detalhe,
                    tentar_novamente_em=exc.tentar_novamente_em,
                )
                cabecalhos = dict(exc.cabecalhos)
                logger.info(
                    "idempotencia (middleware): conflito",
                    extra={"codigo": exc.codigo, "escopo": escopo},
                )
                return _resposta_direta(status, corpo, cabecalhos)

            if resultado.ja_concluido:
                await sessao.rollback()  # nada a persistir, só leitura
                logger.info("idempotencia (middleware): replay", extra={"escopo": escopo})
                corpo_replay = resultado.resposta_corpo
                resposta = Response(
                    content=json.dumps(corpo_replay) if corpo_replay is not None else b"",
                    status_code=resultado.resposta_status or 200,
                    media_type="application/json" if corpo_replay is not None else None,
                )
                resposta.headers["Idempotency-Replayed"] = "true"
                return resposta

            # Operação nova: a rota roda de verdade, na PRÓPRIA sessão dela
            # (aberta por `Depends(obter_sessao)`, como sempre) -- este
            # middleware só observa o resultado por fora.
            resposta_real = await call_next(request)

            if not (200 <= resposta_real.status_code < 300):
                # Tentativa falhou: nunca persiste como concluída -- o
                # rollback libera a chave para a próxima tentativa (mesma
                # semântica de `idempotencia_generica.py`, docstring do
                # módulo, "uma tentativa que falhou nunca envenena a
                # chave").
                await sessao.rollback()
                return resposta_real

            pedacos = [secao async for secao in resposta_real.body_iterator]  # type: ignore[attr-defined]
            corpo_bytes = b"".join(
                secao if isinstance(secao, bytes) else secao.encode("utf-8") for secao in pedacos
            )
            try:
                corpo_para_guardar = json.loads(corpo_bytes) if corpo_bytes else None
            except ValueError:
                corpo_para_guardar = None

            await concluir_operacao(
                sessao,
                registro_id=resultado.registro_id,
                status_http=resposta_real.status_code,
                corpo_resposta=corpo_para_guardar,
            )
            await sessao.commit()

            cabecalhos_repassados = {
                nome: valor
                for nome, valor in resposta_real.headers.items()
                if nome.lower() not in _CABECALHOS_NAO_REPASSADOS
            }
            cabecalhos_repassados["Idempotency-Replayed"] = "false"
            return Response(
                content=corpo_bytes,
                status_code=resposta_real.status_code,
                headers=cabecalhos_repassados,
                media_type=resposta_real.media_type,
            )
