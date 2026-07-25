"""Rotas da tag `relatorios` do contrato. GERADO -- nao editar.

Catalogo, execucao sincrona e assincrona, agendamento e exportacao dos relatorios gerenciais em CSV, XLSX e PDF, com colunas configuraveis por usuario.

Regra de negocio destas operacoes entra na fase F11. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["relatorios"])


@roteador.get(
    "/v1/relatorios",
    status_code=200,
    operation_id="listarRelatorios",
    summary="Listar catalogo de relatorios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_relatorios(
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
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria.")
    ] = None,
    sistema: Annotated[
        bool | None,
        Query(alias="sistema", description="Filtra relatorios de fabrica ou criados pelo cliente."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por relatorios ativos.")
    ] = None,
) -> contrato.ListaRelatorioDefinicao:
    """Listar catalogo de relatorios

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("listarRelatorios", fase="F11")


@roteador.get(
    "/v1/relatorios/{codigo}",
    status_code=200,
    operation_id="obterRelatorio",
    summary="Obter definicao de relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def obter_relatorio(
    codigo: Annotated[
        str,
        Path(
            alias="codigo", description="Codigo estavel do relatorio, por exemplo espelho-jornada."
        ),
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
) -> contrato.RelatorioDefinicao:
    """Obter definicao de relatorio

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("obterRelatorio", fase="F11")


@roteador.get(
    "/v1/relatorios/{codigo}/executar",
    status_code=200,
    operation_id="executarRelatorio",
    summary="Executar relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def executar_relatorio(
    codigo: Annotated[
        str,
        Path(
            alias="codigo", description="Codigo estavel do relatorio, por exemplo espelho-jornada."
        ),
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
    formato: Annotated[
        str | None, Query(alias="formato", description="Formato do resultado. O padrao e json.")
    ] = None,
    periodo_id: Annotated[
        UUID | None,
        Query(alias="periodoId", description="Periodo de apuracao, quando o relatorio o aceita."),
    ] = None,
    de: Annotated[date | None, Query(alias="de", description="Primeiro dia do intervalo.")] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Ultimo dia do intervalo.")] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Restringe a uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Restringe a uma unidade.")
    ] = None,
    departamento_id: Annotated[
        UUID | None, Query(alias="departamentoId", description="Restringe a um departamento.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Restringe a um colaborador.")
    ] = None,
    agrupamento: Annotated[
        str | None,
        Query(
            alias="agrupamento",
            description="Agrupamento, entre os declarados na definicao do relatorio.",
        ),
    ] = None,
    colunas: Annotated[
        str | None,
        Query(
            alias="colunas",
            description="Colunas a retornar, separadas por virgula, na ordem desejada.",
        ),
    ] = None,
    filtros: Annotated[
        str | None,
        Query(
            alias="filtros",
            description="Filtros adicionais em JSON codificado, conforme a definicao do relatorio.",
        ),
    ] = None,
    converter_decimal: Annotated[
        bool | None,
        Query(
            alias="converterDecimal",
            description="Converte duracoes de minutos para horas decimais na saida. Internamente tudo e minuto inteiro.",
        ),
    ] = None,
    incluir_inativos: Annotated[
        bool | None,
        Query(alias="incluirInativos", description="Inclui colaboradores desligados no resultado."),
    ] = None,
    assincrono: Annotated[
        bool | None,
        Query(
            alias="assincrono", description="Forca a execucao assincrona mesmo em relatorios leves."
        ),
    ] = None,
) -> contrato.RelatorioExecucao:
    """Executar relatorio

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("executarRelatorio", fase="F11")


@roteador.get(
    "/v1/relatorios/execucoes/{execucaoId}",
    status_code=200,
    operation_id="obterExecucaoRelatorio",
    summary="Obter execucao de relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def obter_execucao_relatorio(
    execucao_id: Annotated[
        UUID, Path(alias="execucaoId", description="Identificador da execucao.")
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
) -> contrato.RelatorioExecucao:
    """Obter execucao de relatorio

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("obterExecucaoRelatorio", fase="F11")


@roteador.get(
    "/v1/relatorios/agendamentos",
    status_code=200,
    operation_id="listarAgendamentosRelatorio",
    summary="Listar agendamentos de relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def listar_agendamentos_relatorio(
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
    relatorio_definicao_id: Annotated[
        UUID | None,
        Query(
            alias="relatorioDefinicaoId", description="Filtra pelos agendamentos de um relatorio."
        ),
    ] = None,
    usuario_id: Annotated[
        UUID | None,
        Query(alias="usuarioId", description="Filtra pelos agendamentos de um usuario."),
    ] = None,
    canal: Annotated[
        str | None, Query(alias="canal", description="Filtra pelo canal de entrega.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por agendamentos ativos.")
    ] = None,
) -> contrato.ListaRelatorioAgendamento:
    """Listar agendamentos de relatorio

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("listarAgendamentosRelatorio", fase="F11")


@roteador.post(
    "/v1/relatorios/agendamentos",
    status_code=201,
    operation_id="criarAgendamentoRelatorio",
    summary="Criar agendamento de relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def criar_agendamento_relatorio(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RelatorioAgendamentoCriar,
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
) -> contrato.RelatorioAgendamento:
    """Criar agendamento de relatorio

    Fase 0 entrega andaime: a implementacao entra na fase F11.
    """
    raise NaoImplementado("criarAgendamentoRelatorio", fase="F11")
