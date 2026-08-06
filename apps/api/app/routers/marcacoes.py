"""Rotas da tag `marcacoes` do contrato. GERADO -- nao editar.

Registro de ponto: o nucleo legal do sistema.
MARCACAO E IMUTAVEL.
Esta tag expoe deliberadamente apenas criacao e leitura.

Regra de negocio destas operacoes entra na fase F5. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.antifraude import fila as fila_revisao
from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.marcacao.consulta import marcacoes as consulta_marcacoes
from app.marcacao.dominio import verificacao_nsr
from app.marcacao.pipeline import ingestao, offline
from app.schemas import contrato

roteador = APIRouter(tags=["marcacoes"])


@roteador.post(
    "/v1/marcacoes",
    status_code=201,
    operation_id="criarMarcacao",
    summary="Registrar marcacao de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def criar_marcacao(
    corpo: contrato.MarcacaoCriar,
    request: Request,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.criar"))],
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ] = None,
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
) -> contrato.MarcacaoCriada:
    """Registrar marcacao de ponto.

    `Idempotency-Key` fica opcional na assinatura (o contrato a declara
    obrigatoria) so para que a ausencia responda `PONTO-IDEM-001`
    especificamente -- o `errors.yaml` e explicito (`PONTO-VAL-011`: "Para
    Idempotency-Key veja PONTO-IDEM-001") de que o cabecalho generico
    ausente NAO e o codigo certo aqui.
    """
    tenant_id = tenant_id_ou_erro(sujeito)
    resultado = await ingestao.registrar_marcacao(
        sessao,
        tenant_id=tenant_id,
        corpo=corpo,
        idempotency_key=idempotency_key,
        sujeito=sujeito,
        ip_origem=ip_confiavel_do_cliente(request),
    )
    if resultado.replay:
        response.headers["Idempotency-Replayed"] = "true"
    if resultado.resposta.marcacao is not None:
        response.headers["Location"] = f"/v1/marcacoes/{resultado.resposta.marcacao.id}"
    return resultado.resposta


@roteador.get(
    "/v1/marcacoes",
    status_code=200,
    operation_id="listarMarcacoes",
    summary="Listar marcacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_marcacoes(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.ler"))],
    sessao: SessaoDb,
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelas marcacoes de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelas marcacoes de um vinculo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas marcacoes de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pelas marcacoes de uma unidade.")
    ] = None,
    rep_p_id: Annotated[
        UUID | None, Query(alias="repPId", description="Filtra pelas marcacoes de um REP-P.")
    ] = None,
    cpf: Annotated[
        str | None, Query(alias="cpf", description="Filtra por CPF, somente digitos.")
    ] = None,
    canal: Annotated[
        str | None, Query(alias="canal", description="Filtra pelo canal de origem.")
    ] = None,
    de: Annotated[
        datetime | None,
        Query(alias="de", description="Marcacoes a partir deste instante, no fuso da unidade."),
    ] = None,
    ate: Annotated[
        datetime | None,
        Query(alias="ate", description="Marcacoes ate este instante, no fuso da unidade."),
    ] = None,
    nsr_de: Annotated[
        int | None, Query(alias="nsrDe", description="Faixa de NSR: valor inicial.")
    ] = None,
    nsr_ate: Annotated[
        int | None, Query(alias="nsrAte", description="Faixa de NSR: valor final.")
    ] = None,
    coletada_offline: Annotated[
        bool | None,
        Query(
            alias="coletadaOffline", description="Filtra marcacoes que chegaram por fila offline."
        ),
    ] = None,
    incluir_meta: Annotated[
        bool | None,
        Query(
            alias="incluirMeta",
            description="Inclui o contexto antifraude de cada marcacao. Exige permissao sensivel e gera registro de acesso a dado sensivel.",
        ),
    ] = None,
) -> contrato.ListaMarcacao:
    """Listar marcacoes. Somente leitura -- ver `x-vedacao-legal` da tag no
    contrato: nunca havera `PUT`/`PATCH`/`DELETE` aqui."""
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_marcacoes.listar_marcacoes(
        sessao,
        tenant_id=tenant_id,
        sujeito=sujeito,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        rep_p_id=rep_p_id,
        cpf=cpf,
        canal=canal,
        de=de,
        ate=ate,
        nsr_de=nsr_de,
        nsr_ate=nsr_ate,
        coletada_offline=coletada_offline,
        incluir_meta=incluir_meta,
    )


@roteador.get(
    "/v1/marcacoes/{marcacaoId}",
    status_code=200,
    operation_id="obterMarcacao",
    summary="Obter marcacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_marcacao(
    marcacao_id: Annotated[
        UUID, Path(alias="marcacaoId", description="Identificador da marcacao.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.ler"))],
    sessao: SessaoDb,
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
) -> contrato.Marcacao:
    """Obter marcacao. `PONTO-REC-001` quando o id nao existe no tenant
    corrente (inclusive marcacao de outro tenant -- 404 por isolamento)."""
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_marcacoes.obter_marcacao(
        sessao, tenant_id=tenant_id, marcacao_id=marcacao_id
    )


@roteador.get(
    "/v1/marcacoes/{marcacaoId}/meta",
    status_code=200,
    operation_id="obterMetaMarcacao",
    summary="Obter contexto antifraude da marcacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_meta_marcacao(
    marcacao_id: Annotated[
        UUID, Path(alias="marcacaoId", description="Identificador da marcacao.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.ler_sensivel"))],
    sessao: SessaoDb,
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
) -> contrato.MarcacaoMeta:
    """Obter contexto antifraude da marcacao. Dado sensivel: a permissao
    `marcacoes.ler_sensivel` (`Depends(exigir_permissao(...))` acima) ja
    registra o acesso em `acessos_dados_sensiveis` antes do corpo rodar."""
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_marcacoes.obter_meta_marcacao(
        sessao, tenant_id=tenant_id, marcacao_id=marcacao_id
    )


@roteador.post(
    "/v1/marcacoes/{marcacaoId}/meta/decisao",
    status_code=200,
    operation_id="decidirRevisaoMarcacao",
    summary="Decidir revisao antifraude da marcacao",
    responses=RESPOSTAS_PADRAO,
)
async def decidir_revisao_marcacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    marcacao_id: Annotated[
        UUID, Path(alias="marcacaoId", description="Identificador da marcacao.")
    ],
    corpo: contrato.DecisaoRevisaoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.aprovar"))],
    sessao: SessaoDb,
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
) -> contrato.MarcacaoMeta:
    """Decidir revisao antifraude da marcacao (RFC-020). NUNCA altera a
    marcacao em si (ADR-002) -- so os campos de revisao de `MarcacaoMeta`,
    via `app.antifraude.fila.decidir_revisao`."""
    tenant_id = tenant_id_ou_erro(sujeito)
    meta = await fila_revisao.decidir_revisao(
        sessao,
        tenant_id=tenant_id,
        marcacao_id=marcacao_id,
        decisao=corpo.decisao.value,
        observacao=corpo.observacao,
        usuario_id=sujeito.usuario_id,
    )
    return consulta_marcacoes.serializar_meta_marcacao(meta)


@roteador.get(
    "/v1/marcacoes/revisao-pendente",
    status_code=200,
    operation_id="listarRevisaoPendente",
    summary="Listar fila de revisao antifraude",
    responses=RESPOSTAS_PADRAO,
)
async def listar_revisao_pendente(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.ler_sensivel"))],
    sessao: SessaoDb,
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
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina.",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas marcacoes de uma empresa.")
    ] = None,
) -> contrato.ListaRevisaoPendente:
    """Listar fila de revisao antifraude (RFC-020): marcacoes com
    `revisaoStatus=pendente`, mais recentes primeiro. Cursor proprio (o
    instante da marcacao anterior), independente do cursor generico de
    `listarMarcacoes` -- ver `app.antifraude.fila.listar_pendentes`."""
    tenant_id = tenant_id_ou_erro(sujeito)
    limite_efetivo = limite if limite is not None else 50
    cursor_datahora = datetime.fromisoformat(cursor) if cursor else None

    itens = await fila_revisao.listar_pendentes(
        sessao,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        limite=limite_efetivo + 1,
        cursor_datahora=cursor_datahora,
    )
    tem_mais = len(itens) > limite_efetivo
    pagina = itens[:limite_efetivo]
    proximo_cursor = pagina[-1].datahora_marcacao.isoformat() if tem_mais and pagina else None

    return contrato.ListaRevisaoPendente(
        dados=[
            contrato.ItemRevisaoPendente(
                marcacaoId=item.marcacao_id,
                colaboradorId=item.colaborador_id,
                empresaId=item.empresa_id,
                canal=contrato.Canal2(item.canal),
                datahoraMarcacao=item.datahora_marcacao,
                nsr=item.nsr,
                scoreConfianca=item.score_confianca,
                classificacaoConfianca=(
                    contrato.ClassificacaoConfianca(item.classificacao_confianca)
                    if item.classificacao_confianca is not None
                    else None
                ),
                flagsIntegridade=item.flags_integridade,
            )
            for item in pagina
        ],
        paginacao=contrato.Paginacao(
            proximoCursor=proximo_cursor,
            cursorAnterior=None,
            temMais=tem_mais,
            limite=limite_efetivo,
            totalEstimado=None,
        ),
    )


@roteador.post(
    "/v1/marcacoes/sincronizar-offline",
    status_code=207,
    operation_id="sincronizarMarcacoesOffline",
    summary="Sincronizar fila offline",
    responses=RESPOSTAS_PADRAO,
)
async def sincronizar_marcacoes_offline(
    corpo: contrato.SincronizacaoOfflineRequisicao,
    request: Request,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.criar"))],
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ] = None,
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
) -> contrato.SincronizacaoOfflineResposta:
    """Sincronizar fila offline. Ver `criarMarcacao` sobre `Idempotency-Key`
    opcional na assinatura (so para responder `PONTO-IDEM-001` certo)."""
    tenant_id = tenant_id_ou_erro(sujeito)
    resposta = await offline.sincronizar_lote(
        sessao,
        tenant_id=tenant_id,
        corpo=corpo,
        idempotency_key=idempotency_key,
        sujeito=sujeito,
        ip_origem=ip_confiavel_do_cliente(request),
    )
    return resposta


@roteador.get(
    "/v1/marcacoes/nsr/verificar",
    status_code=200,
    operation_id="verificarSequenciaNsr",
    summary="Verificar continuidade do NSR",
    responses=RESPOSTAS_PADRAO,
)
async def verificar_sequencia_nsr(
    rep_p_id: Annotated[UUID, Query(alias="repPId", description="REP-P a verificar.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("marcacoes.ler"))],
    sessao: SessaoDb,
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
    nsr_de: Annotated[
        int | None, Query(alias="nsrDe", description="Inicio da faixa. Ausente comeca em 1.")
    ] = None,
    nsr_ate: Annotated[
        int | None,
        Query(alias="nsrAte", description="Fim da faixa. Ausente vai ate o ultimo emitido."),
    ] = None,
    verificar_cadeia_hash: Annotated[
        bool | None,
        Query(
            alias="verificarCadeiaHash",
            description="Alem da continuidade numerica, recalcula a cadeia de hash encadeado. Mais lento.",
        ),
    ] = None,
) -> contrato.VerificacaoNsr:
    """Verificar continuidade do NSR"""
    tenant_id = tenant_id_ou_erro(sujeito)
    resultado = await verificacao_nsr.verificar_sequencia_nsr(
        sessao,
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        nsr_de=nsr_de,
        nsr_ate=nsr_ate,
        verificar_cadeia_hash=bool(verificar_cadeia_hash),
    )
    return contrato.VerificacaoNsr.model_validate(resultado, from_attributes=True)
