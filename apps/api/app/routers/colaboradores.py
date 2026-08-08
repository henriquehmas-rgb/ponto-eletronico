"""Rotas da tag `colaboradores` do contrato.

Pessoas.
Guarda dados cadastrais e pessoais; as condicoes de trabalho vivem em contratos e vinculos.
Leitura de campo sensivel gera registro proprio de acesso, exigido pela LGPD.

Regra de negocio implementada na fase F2 (agente A2, ownership deste arquivo --
ver `docs/fases/F02-cadastros-organizacionais-pessoas.md`, secao 5). A regra em
si vive em `app.pessoas.colaboradores`; este modulo so traduz HTTP <-> servico.

`importarColaboradores`: RFC-007 decidida (opcao a) -- `ImportacaoCriar` ganhou
`conteudoRef` no contrato, e o handler abaixo repassa para
`app.importadores.servico.criar_importacao_colaboradores` (ownership F2/A3).

Autenticacao dupla (retrofit de 2026-08-08, mesma decisao do dono do produto
aplicada em `app/routers/empresas.py`): o contrato ja declarava os tres
esquemas alternativos por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas
so sessao humana era aceita. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E' tentada
primeiro (comportamento humano preservado byte a byte), cliente de integracao
(OAuth/API key) so entra quando nao ha sessao humana autenticada.
`importarColaboradores` ficou DE FORA do retrofit (importacao em lote, corpo
potencialmente grande, fora do escopo desta rodada).
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
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.importadores import servico as importadores_servico
from app.pessoas import colaboradores as servico
from app.schemas import contrato

roteador = APIRouter(tags=["colaboradores"])

# Uma instancia por par (permissao, escopo) unico -- nunca uma fabrica chamada
# de novo dentro do handler: mesmo motivo documentado em
# `app.comum.limitador_taxa` (identidade estavel do *callable* pro cache de
# dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="colaboradores.ler", escopo="colaboradores:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="colaboradores.criar", escopo="colaboradores:escrever"
)
_ACESSO_EDITAR = exigir_permissao_ou_escopo(
    permissao="colaboradores.editar", escopo="colaboradores:escrever"
)
_ACESSO_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="colaboradores.excluir", escopo="colaboradores:escrever"
)


@roteador.get(
    "/v1/colaboradores",
    status_code=200,
    operation_id="listarColaboradores",
    summary="Listar colaboradores",
    responses=RESPOSTAS_PADRAO,
)
async def listar_colaboradores(
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
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos colaboradores de uma empresa."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Filtra pelos colaboradores lotados em uma unidade."),
    ] = None,
    departamento_id: Annotated[
        UUID | None, Query(alias="departamentoId", description="Filtra por departamento.")
    ] = None,
    equipe_id: Annotated[
        UUID | None, Query(alias="equipeId", description="Filtra por equipe.")
    ] = None,
    gestor_colaborador_id: Annotated[
        UUID | None,
        Query(alias="gestorColaboradorId", description="Lista os subordinados de um gestor."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    cpf: Annotated[
        str | None, Query(alias="cpf", description="Filtra por CPF, somente digitos.")
    ] = None,
    matricula: Annotated[
        str | None, Query(alias="matricula", description="Filtra por matricula exata.")
    ] = None,
    admitido_de: Annotated[
        date | None, Query(alias="admitidoDe", description="Admissao a partir desta data.")
    ] = None,
    admitido_ate: Annotated[
        date | None, Query(alias="admitidoAte", description="Admissao ate esta data.")
    ] = None,
    incluir_inativos: Annotated[
        bool | None, Query(alias="incluirInativos", description="Inclui desligados no resultado.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
    incluir_excluidos: Annotated[
        bool | None,
        Query(
            alias="incluirExcluidos",
            description="Inclui registros com exclusao logica (excluidoEm preenchido) no resultado.",
        ),
    ] = None,
) -> contrato.ListaColaborador:
    """Listar colaboradores"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_colaboradores(
        sessao,
        acesso.tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        equipe_id=equipe_id,
        gestor_colaborador_id=gestor_colaborador_id,
        status=status,
        cpf=cpf,
        matricula=matricula,
        admitido_de=admitido_de,
        admitido_ate=admitido_ate,
        incluir_inativos=bool(incluir_inativos),
        busca=busca,
        incluir_excluidos=bool(incluir_excluidos),
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Colaborador.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaColaborador(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/colaboradores",
    status_code=201,
    operation_id="criarColaborador",
    summary="Criar colaborador",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ColaboradorCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
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
) -> contrato.Colaborador:
    """Criar colaborador"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    colaborador = await servico.criar_colaborador(sessao, acesso.tenant_id, corpo)
    return contrato.Colaborador.model_validate(colaborador, from_attributes=True)


@roteador.get(
    "/v1/colaboradores/{colaboradorId}",
    status_code=200,
    operation_id="obterColaborador",
    summary="Obter colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def obter_colaborador(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
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
) -> contrato.Colaborador:
    """Obter colaborador"""
    # `acesso` ja confirma o chamador autenticado; RLS ja restringe por tenant.
    await aplicar_limite_taxa_se_cliente(response, acesso)
    colaborador = await servico.obter_colaborador(sessao, colaborador_id)
    return contrato.Colaborador.model_validate(colaborador, from_attributes=True)


@roteador.patch(
    "/v1/colaboradores/{colaboradorId}",
    status_code=200,
    operation_id="atualizarColaborador",
    summary="Atualizar colaborador",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    corpo: contrato.ColaboradorAtualizar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EDITAR)],
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
) -> contrato.Colaborador:
    """Atualizar colaborador"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    colaborador = await servico.atualizar_colaborador(sessao, colaborador_id, corpo)
    return contrato.Colaborador.model_validate(colaborador, from_attributes=True)


@roteador.delete(
    "/v1/colaboradores/{colaboradorId}",
    status_code=204,
    operation_id="excluirColaborador",
    summary="Excluir colaborador",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXCLUIR)],
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
    """Excluir colaborador"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_colaborador(sessao, colaborador_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


@roteador.get(
    "/v1/colaboradores/{colaboradorId}/gestores",
    status_code=200,
    operation_id="listarGestoresColaborador",
    summary="Listar gestores do colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def listar_gestores_colaborador(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
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
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm",
            description="Considera apenas os vinculos de gestao vigentes na data informada.",
        ),
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de vinculo de gestao.")
    ] = None,
) -> contrato.ListaColaboradorGestor:
    """Listar gestores do colaborador"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_gestores_colaborador(
        sessao,
        colaborador_id,
        vigente_em=vigente_em,
        tipo=tipo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.ColaboradorGestor.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaColaboradorGestor(dados=dados, paginacao=paginacao)


@roteador.put(
    "/v1/colaboradores/{colaboradorId}/gestores",
    status_code=200,
    operation_id="definirGestoresColaborador",
    summary="Definir gestores do colaborador",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def definir_gestores_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    corpo: contrato.ColaboradorGestorCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EDITAR)],
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
) -> contrato.ColaboradorGestor:
    """Definir gestores do colaborador"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    registro = await servico.definir_gestor_colaborador(
        sessao, acesso.tenant_id, colaborador_id, corpo
    )
    return contrato.ColaboradorGestor.model_validate(registro, from_attributes=True)


@roteador.post(
    "/v1/colaboradores/importar",
    status_code=202,
    operation_id="importarColaboradores",
    summary="Importar colaboradores em lote",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def importar_colaboradores(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ImportacaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("colaboradores.criar"))],
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
) -> contrato.Importacao:
    """Importar colaboradores em lote"""
    tenant_id = tenant_id_ou_erro(sujeito)
    config = obter_configuracao()
    importacao = await importadores_servico.criar_importacao_colaboradores(
        sessao,
        tenant_id=tenant_id,
        empresa_id=corpo.empresa_id,
        nome_arquivo=corpo.nome_arquivo,
        origem=corpo.origem,
        conteudo_ref=corpo.conteudo_ref,
        parametros=corpo.parametros,
        usuario_id=sujeito.usuario_id,
        redis_url=config.redis_url,
    )
    return contrato.Importacao.model_validate(importacao, from_attributes=True)
