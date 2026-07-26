"""Rotas da tag `contratos` do contrato.

Contratos e vinculos.
O VINCULO, e nao o colaborador, e a chave da apuracao: jornada vigente, escala, apuracao do dia e conta de banco de horas penduram nele.
Um colaborador pode ter mais de um vinculo simultaneo.

Regra de negocio implementada na fase F2 (agente A2, ownership deste arquivo --
ver `docs/fases/F02-cadastros-organizacionais-pessoas.md`, secao 5). A regra em
si vive em `app.pessoas.contratos` (que tambem publica `colaborador.admitido` e
`colaborador.demitido`, ver T8); este modulo so traduz HTTP <-> servico.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.pessoas import contratos as servico
from app.schemas import contrato

roteador = APIRouter(tags=["contratos"])


@roteador.get(
    "/v1/contratos",
    status_code=200,
    operation_id="listarContratos",
    summary="Listar contratos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_contratos(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("contratos.ler"))],
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
        Query(alias="colaboradorId", description="Filtra pelos contratos de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos contratos de uma empresa.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pela modalidade de contratacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas contratos vigentes na data informada."
        ),
    ] = None,
) -> contrato.ListaContrato:
    """Listar contratos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_contratos(
        sessao,
        tenant_id,
        colaborador_id=colaborador_id,
        empresa_id=empresa_id,
        tipo=tipo,
        status=status,
        vigente_em=vigente_em,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Contrato.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaContrato(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/contratos",
    status_code=201,
    operation_id="criarContrato",
    summary="Criar contrato",
    responses=RESPOSTAS_PADRAO,
)
async def criar_contrato(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ContratoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("contratos.criar"))],
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
) -> contrato.Contrato:
    """Criar contrato"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await servico.criar_contrato(sessao, tenant_id, corpo)
    return contrato.Contrato.model_validate(novo, from_attributes=True)


@roteador.get(
    "/v1/contratos/{contratoId}",
    status_code=200,
    operation_id="obterContrato",
    summary="Obter contrato",
    responses=RESPOSTAS_PADRAO,
)
async def obter_contrato(
    contrato_id: Annotated[
        UUID, Path(alias="contratoId", description="Identificador do contrato.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("contratos.ler"))],
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
) -> contrato.Contrato:
    """Obter contrato"""
    tenant_id_ou_erro(sujeito)
    encontrado = await servico.obter_contrato(sessao, contrato_id)
    return contrato.Contrato.model_validate(encontrado, from_attributes=True)


@roteador.patch(
    "/v1/contratos/{contratoId}",
    status_code=200,
    operation_id="atualizarContrato",
    summary="Atualizar contrato",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_contrato(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    contrato_id: Annotated[
        UUID, Path(alias="contratoId", description="Identificador do contrato.")
    ],
    corpo: contrato.ContratoAtualizar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("contratos.editar"))],
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
) -> contrato.Contrato:
    """Atualizar contrato"""
    tenant_id_ou_erro(sujeito)
    atualizado = await servico.atualizar_contrato(sessao, contrato_id, corpo)
    return contrato.Contrato.model_validate(atualizado, from_attributes=True)


@roteador.get(
    "/v1/vinculos",
    status_code=200,
    operation_id="listarVinculos",
    summary="Listar vinculos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_vinculos(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("vinculos.ler"))],
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
        Query(alias="colaboradorId", description="Filtra pelos vinculos de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos vinculos de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade de lotacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    apura_ponto: Annotated[
        bool | None,
        Query(alias="apuraPonto", description="Filtra vinculos sujeitos ou nao a apuracao."),
    ] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas vinculos vigentes na data informada."
        ),
    ] = None,
) -> contrato.ListaVinculo:
    """Listar vinculos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_vinculos(
        sessao,
        tenant_id,
        colaborador_id=colaborador_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        status=status,
        apura_ponto=apura_ponto,
        vigente_em=vigente_em,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Vinculo.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaVinculo(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/vinculos",
    status_code=201,
    operation_id="criarVinculo",
    summary="Criar vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def criar_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.VinculoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("vinculos.criar"))],
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
) -> contrato.Vinculo:
    """Criar vinculo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await servico.criar_vinculo(sessao, tenant_id, corpo)
    return contrato.Vinculo.model_validate(novo, from_attributes=True)


@roteador.get(
    "/v1/vinculos/{vinculoId}",
    status_code=200,
    operation_id="obterVinculo",
    summary="Obter vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_vinculo(
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("vinculos.ler"))],
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
) -> contrato.Vinculo:
    """Obter vinculo"""
    tenant_id_ou_erro(sujeito)
    encontrado = await servico.obter_vinculo(sessao, vinculo_id)
    return contrato.Vinculo.model_validate(encontrado, from_attributes=True)


@roteador.post(
    "/v1/vinculos/{vinculoId}/encerrar",
    status_code=200,
    operation_id="encerrarVinculo",
    summary="Encerrar vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def encerrar_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    corpo: contrato.EncerramentoVinculoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("vinculos.editar"))],
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
) -> contrato.Vinculo:
    """Encerrar vinculo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    encerrado = await servico.encerrar_vinculo(sessao, tenant_id, vinculo_id, corpo)
    return contrato.Vinculo.model_validate(encerrado, from_attributes=True)
