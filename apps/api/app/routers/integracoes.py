"""Rotas da tag `integracoes` do contrato. GERADO -- nao editar.

Exportadores para sistemas de folha e importadores de planilha, de cadastros e de AFD de terceiros.
Marcacoes importadas de outro fabricante usam namespace de NSR separado e nunca interferem na sequencia do nosso REP-P.

Regra de negocio destas operacoes entra na fase F13. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
    exigir_idempotencia,
)
from app.comum.limitador_taxa import exigir_limite_taxa
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.integracoes.webhooks.seguranca import ContextoAcesso, exigir_permissao_ou_escopo
from app.schemas import contrato

roteador = APIRouter(tags=["integracoes"])


# =============================================================================
# A5 (T15, RFC-017) -- autenticacao para `listarIntegracoesFolha`/
# `criarIntegracaoFolha`/`exportarFolha`/`obterExportacaoFolha`, as unicas
# quatro funcoes deste arquivo que A5 possui (PCF F13 §5.2).
#
# CORRIGIDO (achado real desta sessao, nao do PCF): a primeira versao deste
# bloco mantinha uma copia PROPRIA do combinador de autenticacao
# (`_IdentidadeFolha`/`_exigir_permissao_ou_escopo_folha`) que chamava
# `exigir_escopo(escopo)(request)` diretamente, SEM passar
# `authorization`/`x_api_key`/`x_tenant` explicitos -- fora do mecanismo de
# injecao do FastAPI (`Depends()`), esses tres parametros usam o `= None`
# declarado na assinatura de `exigir_escopo`, nunca o cabecalho real da
# requisicao. Resultado: qualquer cliente OAuth/API key seria SEMPRE
# rejeitado com `PONTO-AUTH-002`, mesmo com credencial valida -- exatamente
# o bug que A8 documentou (ver comentario dele, abaixo) ao decidir NAO
# repetir o mesmo erro na propria copia. Corrigido reaproveitando o mesmo
# combinador generico e correto que A3 construiu para `webhooks`
# (`app.integracoes.webhooks.seguranca.exigir_permissao_ou_escopo`/
# `ContextoAcesso`, que extrai os tres cabecalhos explicitamente antes de
# chamar `exigir_escopo`) -- mesma decisao que A8 ja tomou para
# `importacoes`, agora tambem aqui. `exigir_permissao_ou_escopo` importado
# aqui (precisa estar ligado ANTES de `_ACESSO_*` abaixo, que o chama
# imediatamente). `ContextoAcesso` NAO reimportado aqui de proposito: e o
# tipo de um PARAMETRO de rota real (`Depends(...)`), que FastAPI/pydantic
# precisam resolver em runtime (`app.openapi()` falharia sem isso em
# algum lugar do modulo) -- mas basta UMA ligacao real por modulo, e o
# bloco de A8 (abaixo) ja faz essa ligacao real, antes de qualquer rota
# deste arquivo ser definida. Reimportar aqui de novo so produziria
# F811 (redefinicao) sem nenhum ganho -- confirmado com `app.openapi()`
# rodando de ponta a ponta ao final desta fase. `ChaveIdempotencia`/
# `abrir_operacao`/`concluir_operacao`/`exigir_idempotencia`/
# `exigir_limite_taxa`/`exigir_permissao_ou_escopo`/`ContextoAcesso` importados
# no topo do arquivo (E402 -- ruff exige import antes de qualquer statement,
# `roteador = APIRouter(...)` acima incluido), nao mais aqui.
# =============================================================================

_ACESSO_LISTAR_FOLHA = exigir_permissao_ou_escopo(
    permissao="integracoes.ler", escopo="integracoes:ler"
)
_ACESSO_CRIAR_FOLHA = exigir_permissao_ou_escopo(
    permissao="integracoes.criar", escopo="integracoes:escrever"
)
_ACESSO_EXPORTAR_FOLHA = exigir_permissao_ou_escopo(
    permissao="integracoes.executar", escopo="integracoes:escrever"
)
_ACESSO_OBTER_EXPORTACAO_FOLHA = exigir_permissao_ou_escopo(
    permissao="integracoes.ler", escopo="integracoes:ler"
)


async def _cliente_folha_ja_resolvido() -> ClienteAutenticado:  # pragma: no cover
    """Nunca chamada de verdade -- so da a `exigir_limite_taxa` um
    *callable* do tipo certo (mesmo truque que A3/A8 ja usam em
    `app/routers/webhooks.py`/`_cliente_importacoes_ja_resolvido`)."""
    raise AssertionError("_cliente_folha_ja_resolvido nao deveria ser invocada")


_LIMITE_TAXA_FOLHA = exigir_limite_taxa(_cliente_folha_ja_resolvido)


async def _aplicar_limite_taxa_se_cliente_folha(response: Response, acesso: ContextoAcesso) -> None:
    """`exigir_limite_taxa` (T4) so se aplica a cliente de integracao
    (`ClienteAutenticado.rate_limit_por_minuto`); sessao humana nao tem
    equivalente neste contrato. Chamada MANUAL (nao `Depends()` direto na
    rota) porque so se sabe qual dos dois caminhos foi usado DEPOIS de
    `exigir_permissao_ou_escopo` resolver `acesso`. Mesmo padrao de A8
    (`_aplicar_limite_taxa_se_cliente_importacoes`)."""
    if acesso.cliente is None:
        return
    await _LIMITE_TAXA_FOLHA(response=response, cliente=acesso.cliente)


# =============================================================================
# A8 (T19, RFC-017) -- `listarImportacoes`/`criarImportacao`/
# `obterImportacao`, as unicas tres funcoes deste arquivo que A8 possui
# (PCF F13 §5.2).
#
# Autenticacao: reaproveita `app.integracoes.webhooks.seguranca.
# exigir_permissao_ou_escopo`/`ContextoAcesso` (A3, T10) em vez de manter
# uma terceira copia quase identica da de A5 (`_exigir_permissao_ou_escopo_
# folha`, acima) -- decisao de A8, nao pedida literalmente pelo PCF (que
# previa cada agente com sua propria copia), mas o combinador de A3 e
# genuinamente generico (permissao/escopo -> tenant_id, nada especifico de
# webhook) e ja corrige um detalhe sutil que a copia de A5 acima NAO trata
# (`exigir_escopo(escopo)(request)` sem os tres cabecalhos explicitos --
# ver `app.comum.autenticacao_cliente.exigir_escopo`: os parametros
# `authorization`/`x_api_key`/`x_tenant` tem `Header()` como valor PADRAO,
# que so e resolvido pelo FastAPI via `Depends()` de verdade; chamado
# manualmente como a copia de A5 faz, os tres ficam `None` e a
# autenticacao de cliente falha sempre com PONTO-AUTH-002 mesmo com
# credencial valida -- achado registrado no relatorio da fase, nao
# corrigido aqui por nao ser arquivo/funcao de ownership de A8).
# Rate limit (T4): mesmo truque de `app.comum.limitador_taxa.
# exigir_limite_taxa` + callable "ja resolvido" que `app/routers/webhooks.py`
# (A3) ja usa -- reaproveitado aqui por identidade de padrao, nao por
# import cruzado (copia pequena, autocontida). `exigir_limite_taxa`/
# `ContextoAcesso`/`exigir_permissao_ou_escopo` ja foram importados no bloco
# de A5, acima, no topo deste mesmo modulo -- nao reimportados aqui de novo
# (reimportar o mesmo nome duas vezes no mesmo modulo e apenas redundante,
# `ruff` acusa F811). `TYPE_CHECKING` importado junto de `Annotated` no topo
# do arquivo.
#
# IMPORTANTE (achado real desta sessao, corrigido aqui): `ContextoAcesso` NAO
# pode ficar só sob `TYPE_CHECKING` -- diferente de `ClienteAutenticado`
# abaixo (que so aparece na anotacao de retorno de uma funcao auxiliar
# interna, nunca inspecionada pelo FastAPI), `ContextoAcesso` e o tipo de um
# PARAMETRO de rota real (`Depends(...)`), que o FastAPI/pydantic PRECISA
# resolver em tempo de execucao para montar o schema OpenAPI (`app.openapi()`
# falha com `PydanticUserError: ... is not fully defined` sem isto, mesmo
# com `from __future__ import annotations` no topo do arquivo). Import REAL
# (nao condicional) aqui garante que o nome exista em tempo de execucao para
# TODAS as rotas deste arquivo que o usam (as de A5, acima, e as de A8,
# abaixo) -- independente de qual bloco "e dono" da linha de import.
# `ContextoAcesso` importado no topo do arquivo (E402), nao mais aqui.
# =============================================================================

if TYPE_CHECKING:
    from app.comum.autenticacao_cliente import ClienteAutenticado

_ACESSO_LISTAR_IMPORTACOES = exigir_permissao_ou_escopo(
    permissao="importacoes.ler", escopo="integracoes:ler"
)
_ACESSO_CRIAR_IMPORTACAO = exigir_permissao_ou_escopo(
    permissao="importacoes.criar", escopo="integracoes:escrever"
)
_ACESSO_OBTER_IMPORTACAO = exigir_permissao_ou_escopo(
    permissao="importacoes.ler", escopo="integracoes:ler"
)


async def _cliente_importacoes_ja_resolvido() -> ClienteAutenticado:  # pragma: no cover
    """Nunca chamada de verdade -- ver docstring de `_LIMITE_TAXA_IMPORTACOES`
    abaixo. Existe so para dar a `exigir_limite_taxa` um *callable* do tipo
    certo (mesmo truque que `app/routers/webhooks.py`, A3, ja usa)."""
    raise AssertionError("_cliente_importacoes_ja_resolvido nao deveria ser invocada")


_LIMITE_TAXA_IMPORTACOES = exigir_limite_taxa(_cliente_importacoes_ja_resolvido)


async def _aplicar_limite_taxa_se_cliente_importacoes(
    response: Response, acesso: ContextoAcesso
) -> None:
    """`exigir_limite_taxa` (T4) so se aplica a cliente de integracao
    (`ClienteAutenticado.rate_limit_por_minuto`); sessao humana nao tem
    equivalente neste contrato. Chamada MANUAL (nao `Depends()` direto na
    rota) porque so se sabe qual dos dois caminhos foi usado DEPOIS de
    `exigir_permissao_ou_escopo` resolver `acesso`."""
    if acesso.cliente is None:
        return
    await _LIMITE_TAXA_IMPORTACOES(response=response, cliente=acesso.cliente)


def _usuario_id_importacoes(acesso: ContextoAcesso) -> UUID | None:
    """`criado_por` de uma importacao: `usuario_id` humano quando a rota foi
    chamada por sessao (`Sujeito`), `None` para cliente OAuth/API key (conta
    de maquina, sem usuario humano) -- mesmo criterio de `_usuario_id` em
    `app/routers/webhooks.py` (A3)."""
    return acesso.sujeito.usuario_id if acesso.sujeito is not None else None


@roteador.get(
    "/v1/integracoes/folha",
    status_code=200,
    operation_id="listarIntegracoesFolha",
    summary="Listar integracoes de folha",
    responses=RESPOSTAS_PADRAO,
)
async def listar_integracoes_folha(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas integracoes de uma empresa."),
    ] = None,
    parceiro: Annotated[
        str | None, Query(alias="parceiro", description="Filtra pelo sistema de folha de destino.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por integracoes ativas.")
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LISTAR_FOLHA)],
    sessao: SessaoDb,
    response: Response,
) -> contrato.ListaIntegracaoFolha:
    """Listar integracoes de folha

    A5 (T15). Corpo real em `app.integracoes.folha.comum.servico.listar_integracoes`.
    """
    await _aplicar_limite_taxa_se_cliente_folha(response, acesso)
    from app.integracoes.folha.comum.servico import listar_integracoes as _servico_listar

    return await _servico_listar(
        sessao,
        tenant_id=acesso.tenant_id,
        cursor=cursor,
        limite_bruto=limite,
        ordenar=ordenar,
        empresa_id=empresa_id,
        parceiro=parceiro,
        ativo=ativo,
    )


@roteador.post(
    "/v1/integracoes/folha",
    status_code=201,
    operation_id="criarIntegracaoFolha",
    summary="Criar integracao de folha",
    responses=RESPOSTAS_PADRAO,
)
async def criar_integracao_folha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.IntegracaoFolhaCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR_FOLHA)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
) -> contrato.IntegracaoFolha:
    """Criar integracao de folha

    A5 (T15). Corpo real em `app.integracoes.folha.comum.servico.criar_integracao`.
    Idempotencia genarica de A1 (T3): reusar `Idempotency-Key` com o mesmo
    corpo devolve a mesma resposta (`Idempotency-Replayed: true`), sem criar
    uma segunda integracao; corpo diferente e `409 PONTO-IDEM-002`.
    """
    del idempotency_key  # lido pela dependencia `exigir_idempotencia`, nao aqui
    await _aplicar_limite_taxa_se_cliente_folha(response, acesso)
    from app.integracoes.folha.comum.servico import criar_integracao as _servico_criar

    resultado_abertura = await abrir_operacao(
        sessao, tenant_id=acesso.tenant_id, escopo="integracoesFolha.criar", chave=chave_idem
    )
    if resultado_abertura.ja_concluido:
        response.headers["Idempotency-Replayed"] = "true"
        return contrato.IntegracaoFolha.model_validate(resultado_abertura.resposta_corpo)

    resposta = await _servico_criar(sessao, tenant_id=acesso.tenant_id, dados=corpo)
    await concluir_operacao(
        sessao,
        registro_id=resultado_abertura.registro_id,
        status_http=201,
        corpo_resposta=resposta.model_dump(mode="json", by_alias=True),
    )
    return resposta


@roteador.post(
    "/v1/integracoes/folha/{integracaoId}/exportar",
    status_code=202,
    operation_id="exportarFolha",
    summary="Exportar apuracao para a folha",
    responses=RESPOSTAS_PADRAO,
)
async def exportar_folha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    integracao_id: Annotated[
        UUID, Path(alias="integracaoId", description="Identificador da integracao.")
    ],
    corpo: contrato.ExportacaoFolhaRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXPORTAR_FOLHA)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
) -> contrato.ProcessamentoAssincrono:
    """Exportar apuracao para a folha

    A5 (T15). Parte sincrona (valida integracao/periodo, enfileira o
    worker) em `app.integracoes.folha.comum.servico.solicitar_exportacao`;
    o arquivo em si e gerado pela tarefa `exportar_folha`
    (`apps/worker/worker/tarefas/integracoes.py`). Idempotencia generica de
    A1 (T3): reusar `Idempotency-Key` com o mesmo corpo devolve o mesmo
    `processamentoId` (nao enfileira duas vezes).
    """
    del idempotency_key  # lido pela dependencia `exigir_idempotencia`, nao aqui
    await _aplicar_limite_taxa_se_cliente_folha(response, acesso)
    from app.integracoes.folha.comum.servico import solicitar_exportacao as _servico_exportar

    resultado_abertura = await abrir_operacao(
        sessao,
        tenant_id=acesso.tenant_id,
        escopo="integracoesFolha.exportar",
        chave=chave_idem,
    )
    if resultado_abertura.ja_concluido:
        response.headers["Idempotency-Replayed"] = "true"
        return contrato.ProcessamentoAssincrono.model_validate(resultado_abertura.resposta_corpo)

    resposta = await _servico_exportar(
        sessao, tenant_id=acesso.tenant_id, integracao_id=integracao_id, pedido=corpo
    )
    await concluir_operacao(
        sessao,
        registro_id=resultado_abertura.registro_id,
        status_http=202,
        corpo_resposta=resposta.model_dump(mode="json", by_alias=True),
    )
    return resposta


@roteador.get(
    "/v1/integracoes/folha/{integracaoId}/exportacoes/{processamentoId}",
    status_code=200,
    operation_id="obterExportacaoFolha",
    summary="Obter exportacao de folha",
    responses=RESPOSTAS_PADRAO,
)
async def obter_exportacao_folha(
    integracao_id: Annotated[
        UUID, Path(alias="integracaoId", description="Identificador da integracao.")
    ],
    processamento_id: Annotated[
        UUID,
        Path(
            alias="processamentoId",
            description="Identificador do processamento, devolvido por exportarFolha.",
        ),
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_OBTER_EXPORTACAO_FOLHA)],
    response: Response,
) -> contrato.ProcessamentoAssincrono:
    """Obter exportacao de folha

    A5 (T15, RFC-017 -- `packages/contracts/openapi.yaml`, caminho novo
    `/v1/integracoes/folha/{integracaoId}/exportacoes/{processamentoId}`).
    Corpo real em `app.integracoes.folha.comum.servico.obter_exportacao`.
    `404 PONTO-REC-001` quando o processamento nao existe, ja expirou (24h,
    ver `app.integracoes.folha.comum.processamento`) ou pertence a outro
    tenant/integracao -- os tres casos sao indistinguiveis de proposito
    (isolamento de tenant).
    """
    await _aplicar_limite_taxa_se_cliente_folha(response, acesso)
    from app.integracoes.folha.comum.servico import obter_exportacao as _servico_obter

    return await _servico_obter(
        tenant_id=acesso.tenant_id,
        integracao_id=integracao_id,
        processamento_id=processamento_id,
    )


@roteador.get(
    "/v1/importacoes",
    status_code=200,
    operation_id="listarImportacoes",
    summary="Listar importacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_importacoes(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas importacoes de uma empresa."),
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de importacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LISTAR_IMPORTACOES)],
    sessao: SessaoDb,
    response: Response,
) -> contrato.ListaImportacao:
    """Listar importacoes

    A8 (T19). Corpo real em `app.integracoes.importadores.servico.listar_importacoes`.
    """
    await _aplicar_limite_taxa_se_cliente_importacoes(response, acesso)
    from app.integracoes.importadores.servico import listar_importacoes as _servico_listar

    return await _servico_listar(
        sessao,
        tenant_id=acesso.tenant_id,
        empresa_id=empresa_id,
        tipo=tipo,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )


@roteador.post(
    "/v1/importacoes",
    status_code=202,
    operation_id="criarImportacao",
    summary="Criar importacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_importacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ImportacaoCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR_IMPORTACAO)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
) -> contrato.Importacao:
    """Criar importacao

    A8 (T19). Corpo real em `app.integracoes.importadores.servico.criar_importacao`.
    Idempotencia generica de A1 (T3): reusar `Idempotency-Key` com o mesmo
    corpo devolve a MESMA `Importacao` sem enfileirar o worker de novo (mesmo
    padrao de `criarWebhook`, `app/routers/webhooks.py`, A3).
    """
    del idempotency_key  # lido pela dependencia `exigir_idempotencia`, nao aqui
    await _aplicar_limite_taxa_se_cliente_importacoes(response, acesso)

    abertura = await abrir_operacao(
        sessao, tenant_id=acesso.tenant_id, escopo="importacoes.criarImportacao", chave=chave_idem
    )
    response.headers["Idempotency-Replayed"] = "true" if abertura.ja_concluido else "false"
    if abertura.ja_concluido:
        return contrato.Importacao.model_validate(abertura.resposta_corpo)

    from app.integracoes.importadores.servico import criar_importacao as _servico_criar

    resultado = await _servico_criar(
        sessao,
        tenant_id=acesso.tenant_id,
        corpo=corpo,
        usuario_id=_usuario_id_importacoes(acesso),
        redis_url=obter_configuracao().redis_url,
    )
    await concluir_operacao(
        sessao,
        registro_id=abertura.registro_id,
        status_http=202,
        corpo_resposta=resultado.model_dump(mode="json", by_alias=True),
    )
    return resultado


@roteador.get(
    "/v1/importacoes/{importacaoId}",
    status_code=200,
    operation_id="obterImportacao",
    summary="Obter importacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_importacao(
    importacao_id: Annotated[
        UUID, Path(alias="importacaoId", description="Identificador da importacao.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    *,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_OBTER_IMPORTACAO)],
    sessao: SessaoDb,
    response: Response,
) -> contrato.Importacao:
    """Obter importacao

    A8 (T19, RFC-017 -- `packages/contracts/openapi.yaml`, caminho novo
    `/v1/importacoes/{importacaoId}`). Corpo real em `app.integracoes.
    importadores.servico.obter_importacao`. `404 PONTO-REC-001` quando a
    importacao nao existe no tenant, mesmo padrao de `obterWebhook`/
    `obterExecucaoRelatorio`.
    """
    await _aplicar_limite_taxa_se_cliente_importacoes(response, acesso)
    from app.integracoes.importadores.servico import obter_importacao as _servico_obter

    return await _servico_obter(sessao, tenant_id=acesso.tenant_id, importacao_id=importacao_id)
