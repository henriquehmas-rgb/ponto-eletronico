"""Rotas da tag `colaboradores` do contrato. GERADO -- nao editar.

Pessoas.
Guarda dados cadastrais e pessoais; as condicoes de trabalho vivem em contratos e vinculos.
Leitura de campo sensivel gera registro proprio de acesso, exigido pela LGPD.

Regra de negocio destas operacoes entra na fase F2. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["colaboradores"])


@roteador.get(
    "/v1/colaboradores",
    status_code=200,
    operation_id="listarColaboradores",
    summary="Listar colaboradores",
    responses=RESPOSTAS_PADRAO,
)
async def listar_colaboradores(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
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
    """Listar colaboradores

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarColaboradores", fase="F2")


@roteador.post(
    "/v1/colaboradores",
    status_code=201,
    operation_id="criarColaborador",
    summary="Criar colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def criar_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ColaboradorCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Colaborador:
    """Criar colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarColaborador", fase="F2")


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
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Colaborador:
    """Obter colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterColaborador", fase="F2")


@roteador.patch(
    "/v1/colaboradores/{colaboradorId}",
    status_code=200,
    operation_id="atualizarColaborador",
    summary="Atualizar colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    corpo: contrato.ColaboradorAtualizar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Colaborador:
    """Atualizar colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarColaborador", fase="F2")


@roteador.delete(
    "/v1/colaboradores/{colaboradorId}",
    status_code=204,
    operation_id="excluirColaborador",
    summary="Excluir colaborador",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Excluir colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirColaborador", fase="F2")


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
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
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
    """Listar gestores do colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarGestoresColaborador", fase="F2")


@roteador.put(
    "/v1/colaboradores/{colaboradorId}/gestores",
    status_code=200,
    operation_id="definirGestoresColaborador",
    summary="Definir gestores do colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def definir_gestores_colaborador(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    corpo: contrato.ColaboradorGestorCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.ColaboradorGestor:
    """Definir gestores do colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("definirGestoresColaborador", fase="F2")


@roteador.post(
    "/v1/colaboradores/importar",
    status_code=202,
    operation_id="importarColaboradores",
    summary="Importar colaboradores em lote",
    responses=RESPOSTAS_PADRAO,
)
async def importar_colaboradores(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ImportacaoCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Importacao:
    """Importar colaboradores em lote

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("importarColaboradores", fase="F2")
