"""Rotas da tag `feriados` do contrato.

Calendario de feriados por abrangencia nacional, estadual, municipal, de empresa e de unidade.
Feriados moveis nao guardam data: sao calculados por regra a partir da Pascoa do ano de referencia.

Regra de negocio implementada na fase F3 (agente A2, ownership deste arquivo --
ver `docs/fases/F03-motor-de-jornada.md`, secao 5). A regra em si vive em
`app.jornada.calendario.feriados`; este modulo so traduz HTTP <-> servico.

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto
apesar de F14/A2 ter deixado como "sem valor de produto validado ainda",
ver `docs/backlog.md`): contrato ja declarava os tres esquemas alternativos
por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era
aceita ate agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador ja provado em
`app/routers/webhooks.py`/F13) -- sessao humana E' tentada primeiro
(comportamento humano preservado byte a byte), cliente de integracao (OAuth/
API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.jornada.calendario import feriados as servico
from app.schemas import contrato

roteador = APIRouter(tags=["feriados"])

# Uma instancia por par (permissao, escopo) -- nao uma fabrica chamada de novo
# dentro do handler: mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_FERIADOS_LER = exigir_permissao_ou_escopo(permissao="feriados.ler", escopo="jornadas:ler")
_ACESSO_FERIADOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="feriados.criar", escopo="jornadas:escrever"
)
_ACESSO_FERIADOS_EDITAR = exigir_permissao_ou_escopo(
    permissao="feriados.editar", escopo="jornadas:escrever"
)
_ACESSO_FERIADOS_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="feriados.excluir", escopo="jornadas:escrever"
)


@roteador.get(
    "/v1/feriado-conjuntos",
    status_code=200,
    operation_id="listarFeriadoConjuntos",
    summary="Listar conjuntos de feriados",
    responses=RESPOSTAS_PADRAO,
)
async def listar_feriado_conjuntos(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_LER)],
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
    abrangencia: Annotated[
        str | None, Query(alias="abrangencia", description="Filtra pela abrangencia.")
    ] = None,
    uf: Annotated[
        str | None, Query(alias="uf", description="Filtra pelos conjuntos estaduais de uma UF.")
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Lista os conjuntos aplicados a uma unidade."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por conjuntos ativos.")
    ] = None,
) -> contrato.ListaFeriadoConjunto:
    """Listar conjuntos de feriados"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_feriado_conjuntos(
        sessao,
        acesso.tenant_id,
        abrangencia=abrangencia,
        uf=uf,
        unidade_id=unidade_id,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.FeriadoConjunto.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaFeriadoConjunto(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/feriado-conjuntos",
    status_code=201,
    operation_id="criarFeriadoConjunto",
    summary="Criar conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.FeriadoConjuntoCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_CRIAR)],
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
) -> contrato.FeriadoConjunto:
    """Criar conjunto de feriados"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico.criar_feriado_conjunto(sessao, acesso.tenant_id, corpo)
    return contrato.FeriadoConjunto.model_validate(novo, from_attributes=True)


@roteador.patch(
    "/v1/feriado-conjuntos/{conjuntoId}",
    status_code=200,
    operation_id="atualizarFeriadoConjunto",
    summary="Atualizar conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    conjunto_id: Annotated[
        UUID, Path(alias="conjuntoId", description="Identificador do conjunto.")
    ],
    corpo: contrato.FeriadoConjuntoAtualizar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_EDITAR)],
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
) -> contrato.FeriadoConjunto:
    """Atualizar conjunto de feriados"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizado = await servico.atualizar_feriado_conjunto(
        sessao, acesso.tenant_id, conjunto_id, corpo
    )
    return contrato.FeriadoConjunto.model_validate(atualizado, from_attributes=True)


@roteador.delete(
    "/v1/feriado-conjuntos/{conjuntoId}",
    status_code=204,
    operation_id="excluirFeriadoConjunto",
    summary="Excluir conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    conjunto_id: Annotated[
        UUID, Path(alias="conjuntoId", description="Identificador do conjunto.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_EXCLUIR)],
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
) -> Response:
    """Excluir conjunto de feriados"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_feriado_conjunto(sessao, acesso.tenant_id, conjunto_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


@roteador.get(
    "/v1/feriados",
    status_code=200,
    operation_id="listarFeriados",
    summary="Listar feriados",
    responses=RESPOSTAS_PADRAO,
)
async def listar_feriados(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_LER)],
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
    feriado_conjunto_id: Annotated[
        UUID | None,
        Query(alias="feriadoConjuntoId", description="Filtra pelos feriados de um conjunto."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(
            alias="unidadeId",
            description="Resolve os feriados efetivos de uma unidade, somando os conjuntos aplicados.",
        ),
    ] = None,
    ano: Annotated[
        int | None,
        Query(alias="ano", description="Ano de referencia para resolver os feriados moveis."),
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Considera feriados a partir desta data.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Considera feriados ate esta data.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo tipo.")] = None,
) -> contrato.ListaFeriado:
    """Listar feriados"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_feriados(
        sessao,
        acesso.tenant_id,
        feriado_conjunto_id=feriado_conjunto_id,
        unidade_id=unidade_id,
        ano=ano,
        de=de,
        ate=ate,
        tipo=tipo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Feriado.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaFeriado(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/feriados",
    status_code=201,
    operation_id="criarFeriado",
    summary="Criar feriado",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_feriado(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.FeriadoCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_CRIAR)],
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
) -> contrato.Feriado:
    """Criar feriado"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico.criar_feriado(sessao, acesso.tenant_id, corpo)
    return contrato.Feriado.model_validate(novo, from_attributes=True)


@roteador.delete(
    "/v1/feriados/{feriadoId}",
    status_code=204,
    operation_id="excluirFeriado",
    summary="Excluir feriado",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_feriado(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    feriado_id: Annotated[UUID, Path(alias="feriadoId", description="Identificador do feriado.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_FERIADOS_EXCLUIR)],
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
) -> Response:
    """Excluir feriado"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_feriado(sessao, acesso.tenant_id, feriado_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response
