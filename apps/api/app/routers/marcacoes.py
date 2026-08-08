"""Rotas da tag `marcacoes` do contrato.

Registro de ponto: o nucleo legal do sistema.
MARCACAO E IMUTAVEL.
Esta tag expoe deliberadamente apenas criacao e leitura.

Regra de negocio implementada na fase F5 (`app.marcacao.*`); este modulo so
traduz HTTP <-> servico.

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto --
ver `docs/backlog.md` e a docstring de `app.comum.autenticacao_cliente`): o
contrato ja declarava os tres esquemas alternativos por operacao
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era aceita ate
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E' tentada
primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.

Nada da logica de negocio muda: em particular o colaborador de
`criarMarcacao`/`sincronizarMarcacoesOffline` continua sendo resolvido do
CORPO (`colaboradorId`/`cpf`/`matricula`) e do dispositivo, NUNCA do sujeito
autenticado -- quem bate o ponto e a pessoa identificada no pedido, nao o
portador da credencial (terminal, totem, app do proprio colaborador ou
integracao de RH). O sujeito so alimenta campos de auditoria e a
reautenticacao recente do canal `web`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.antifraude import fila as fila_revisao
from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito
from app.db.sessao import SessaoDb
from app.marcacao.consulta import marcacoes as consulta_marcacoes
from app.marcacao.dominio import verificacao_nsr
from app.marcacao.pipeline import ingestao, offline
from app.schemas import contrato

roteador = APIRouter(tags=["marcacoes"])

# Uma instancia por par (permissao, escopo) unico do arquivo, criada no nivel
# de modulo (nunca chamada de novo dentro do handler): identidade estavel do
# *callable* pro cache de dependencia do FastAPI, mesmo motivo documentado em
# `app.comum.limitador_taxa`.
_ACESSO_REGISTRAR = exigir_permissao_ou_escopo(
    permissao="marcacoes.criar", escopo="ponto:registrar"
)
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="marcacoes.ler", escopo="marcacoes:ler")
_ACESSO_LER_FISCAL = exigir_permissao_ou_escopo(permissao="marcacoes.ler", escopo="fiscal:ler")
_ACESSO_LER_SENSIVEL = exigir_permissao_ou_escopo(
    permissao="marcacoes.ler_sensivel", escopo="marcacoes:ler"
)
_ACESSO_APROVAR = exigir_permissao_ou_escopo(permissao="marcacoes.aprovar", escopo="marcacoes:ler")


def _sujeito_para_servico(acesso: ContextoAcesso) -> Sujeito:
    """`Sujeito` a repassar para a camada de servico.

    Tres handlers deste arquivo repassam o `Sujeito` INTEIRO (nao so
    `usuario_id`): `criarMarcacao`/`sincronizarMarcacoesOffline` (auditoria de
    `criado_por` e reautenticacao recente do canal `web`) e `listarMarcacoes`
    (que reexecuta `exigir_permissao('marcacoes.ler_sensivel')` quando
    `incluirMeta=true`).

    Acesso humano devolve o proprio `Sujeito` resolvido, sem nenhuma alteracao
    (comportamento preservado byte a byte). Acesso de cliente de integracao
    devolve um `Sujeito` sintetico so com o `tenant_id` do cliente: sem
    `usuario_id`, sem perfis, sem `alcance` -- exatamente a "conta de maquina
    sem RBAC hierarquico" que `app.core.seguranca.Sujeito` ja documenta como
    caso previsto (`alcance=None` -> `exigir_alcance` permissivo dentro do
    tenant; `usuario_id=None` -> campos de auditoria nulos, todos `UUID`
    nullable no schema). Mesmo padrao ja usado em `app/routers/admin.py`.

    Consequencias deliberadas para cliente de integracao:
    - `listarMarcacoes?incluirMeta=true` responde `PONTO-PERM-001` (o
      sintetico nao carrega `marcacoes.ler_sensivel`); a leitura sensivel
      permanece exclusiva de sessao humana com a permissao, que e o
      comportamento conservador -- o escopo concedido e so `marcacoes:ler`.
    - `criarMarcacao` em canal `web` com `exigeReautenticacao` responde
      `PONTO-AUTH-011` (nao ha sessao humana a reautenticar). Canais
      `terminal`/`mobile`/`totem`/`api` nao passam por essa checagem.
    """
    if acesso.sujeito is not None:
        return acesso.sujeito
    return Sujeito(tenant_id=acesso.tenant_id, autenticado=True)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_REGISTRAR)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    resultado = await ingestao.registrar_marcacao(
        sessao,
        tenant_id=acesso.tenant_id,
        corpo=corpo,
        idempotency_key=idempotency_key,
        sujeito=_sujeito_para_servico(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_marcacoes.listar_marcacoes(
        sessao,
        tenant_id=acesso.tenant_id,
        sujeito=_sujeito_para_servico(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_marcacoes.obter_marcacao(
        sessao, tenant_id=acesso.tenant_id, marcacao_id=marcacao_id
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER_SENSIVEL)],
    sessao: SessaoDb,
    response: Response,
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
    """Obter contexto antifraude da marcacao. Dado sensivel: em acesso HUMANO
    a permissao `marcacoes.ler_sensivel` (dentro de
    `exigir_permissao_ou_escopo` acima) ja registra o acesso em
    `acessos_dados_sensiveis` antes do corpo rodar -- inalterado pelo
    retrofit. Cliente de integracao chega aqui pelo escopo `marcacoes:ler` e
    nao tem usuario humano a registrar (`acessos_dados_sensiveis` guarda o
    exercicio de uma permissao humana), entao nao gera esse registro."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_marcacoes.obter_meta_marcacao(
        sessao, tenant_id=acesso.tenant_id, marcacao_id=marcacao_id
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_APROVAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    meta = await fila_revisao.decidir_revisao(
        sessao,
        tenant_id=acesso.tenant_id,
        marcacao_id=marcacao_id,
        decisao=corpo.decisao.value,
        observacao=corpo.observacao,
        usuario_id=usuario_id_do_acesso(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER_SENSIVEL)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    limite_efetivo = limite if limite is not None else 50
    cursor_datahora = datetime.fromisoformat(cursor) if cursor else None

    itens = await fila_revisao.listar_pendentes(
        sessao,
        tenant_id=acesso.tenant_id,
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_REGISTRAR)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    resposta = await offline.sincronizar_lote(
        sessao,
        tenant_id=acesso.tenant_id,
        corpo=corpo,
        idempotency_key=idempotency_key,
        sujeito=_sujeito_para_servico(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER_FISCAL)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    resultado = await verificacao_nsr.verificar_sequencia_nsr(
        sessao,
        tenant_id=acesso.tenant_id,
        rep_p_id=rep_p_id,
        nsr_de=nsr_de,
        nsr_ate=nsr_ate,
        verificar_cadeia_hash=bool(verificar_cadeia_hash),
    )
    return contrato.VerificacaoNsr.model_validate(resultado, from_attributes=True)
