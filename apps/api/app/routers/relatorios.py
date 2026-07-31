"""Rotas da tag `relatorios` do contrato (F11).

Catálogo, execução síncrona/assíncrona e preferências de colunas
(`RFC-015`) -- **ownership de A1** (T1/T3, PCF F11 §5): `listarRelatorios`,
`obterRelatorio`, `executarRelatorio`, `obterExecucaoRelatorio`,
`listarPreferenciasColunas`, `salvarPreferenciaColunas`.

Agendamento (`listarAgendamentosRelatorio`/`criarAgendamentoRelatorio`) --
**ownership de A3** (T11): regra de negócio em `app.relatorios.
agendamentos`. Arquivo COMPARTILHADO dentro da fase (PCF §5, tabela
"compartilhado dentro da fase"): cada agente só edita a própria seção,
claramente separada por comentário.

Regra de negócio das operações de A1 está em `app.relatorios.execucao`/
`app.relatorios.preferencias`; este módulo só traduz HTTP <-> serviço (mesmo
padrão que `app/routers/espelhos.py`, F10, já estabelece para a tag
`espelhos`).

**ORDEM DE REGISTRO -- achado real, não mude sem ler isto primeiro.** As
rotas literais (`/v1/relatorios/preferencias-colunas`,
`/v1/relatorios/agendamentos`) precisam ser registradas ANTES de
`/v1/relatorios/{codigo}` (`obterRelatorio`) e de qualquer outra rota
parametrizada de um único segmento. O FastAPI/Starlette casa por ORDEM DE
REGISTRO, não por especificidade: com `{codigo}` primeiro, uma chamada real a
`GET /v1/relatorios/preferencias-colunas` cai em `obter_relatorio(codigo=
"preferencias-colunas")` (que devolve `PONTO-REC-001`, nunca chega ao
handler certo) -- confirmado batendo a rota real via `TestClient` durante o
desenvolvimento desta fase (T1/T3), não é hipotético. O contrato (`openapi.
yaml`) não impõe ordem nenhuma entre paths (é um mapa, não uma lista
ordenada relevante para roteamento); a ordem AQUI, no roteador real, é que
importa, e ela diverge de propósito da ordem em que as operações aparecem no
`openapi.yaml`. Isto já valia para `/v1/relatorios/agendamentos` mesmo antes
desta fase (stub da Fase 0): o defeito ficava invisível porque as duas rotas
colidentes respondiam o mesmo 501/`PONTO-INT-005` de qualquer forma -- só
virou visível quando `obterRelatorio` passou a ser implementação real (T3).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query

from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.relatorios import agendamentos as agendamentos_servico

# Importa por efeito colateral: e o que faz os 24 `registrar_dataset(...)`
# de A2/A3/A4 (`app/relatorios/datasets/{operacionais,gerenciais,
# espelho_oficial}.py`) rodarem antes da primeira requisicao. Sem isto,
# `app.relatorios.catalogo.obter_dataset` nunca encontraria as funcoes reais
# -- achado real de integracao entre os quatro agentes desta fase, corrigido
# durante o desenvolvimento de T1-T3 (ver docstring de `app/relatorios/
# datasets/__init__.py`). Este roteador e importado uma unica vez, no boot
# da aplicacao, por `app/routers/__init__.py::registrar_routers` (nao
# editado por esta fase) -- o ponto certo e mais cedo possivel para isto.
from app.relatorios import datasets as _datasets_registrados  # noqa: F401
from app.relatorios import execucao as execucao_servico
from app.relatorios import preferencias as preferencias_servico
from app.schemas import contrato

roteador = APIRouter(tags=["relatorios"])


def _usuario_id_ou_erro(sujeito: Sujeito) -> UUID:
    """Estreita `sujeito.usuario_id` (`UUID | None`) para `UUID`, mesmo
    espírito de `tenant_id_ou_erro` (`app/core/seguranca.py`). Preferência de
    colunas é sempre pessoal: uma conta de máquina (OAuth `client_
    credentials`, sem `usuario_id`) não tem "usuário" para guardar
    preferência nenhuma -- `PONTO-AUTH-002` porque o sujeito, apesar de
    autenticado, não é o tipo de credencial que esta operação aceita (mesmo
    código que `exigir_permissao` já usa para "não há sujeito autenticado";
    não inventa código novo, proibição 5 do PCF §9)."""
    if sujeito.usuario_id is None:
        raise ErroDeAplicacao(
            "PONTO-AUTH-002",
            detalhe="Preferencia de colunas exige um usuario autenticado, nao uma conta de maquina.",
        )
    return sujeito.usuario_id


# =============================================================================
# Catalogo (listagem) -- ownership de A1 (T3)
# =============================================================================
@roteador.get(
    "/v1/relatorios",
    status_code=200,
    operation_id="listarRelatorios",
    summary="Listar catalogo de relatorios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_relatorios(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
    """Listar catalogo de relatorios"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await execucao_servico.listar_definicoes(
        sessao,
        tenant_id,
        categoria=categoria,
        sistema=sistema,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.RelatorioDefinicao.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaRelatorioDefinicao(dados=dados, paginacao=paginacao)


# =============================================================================
# Preferencias de colunas (RFC-015) -- ownership de A1 (T1). Rota LITERAL:
# tem que vir antes de `/v1/relatorios/{codigo}` (ver nota de ordem no topo
# do arquivo).
# =============================================================================
@roteador.get(
    "/v1/relatorios/preferencias-colunas",
    status_code=200,
    operation_id="listarPreferenciasColunas",
    summary="Listar preferencias de colunas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_preferencias_colunas(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior.",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None, Query(alias="ordenar", description="Campo de ordenacao: criadoEm ou nome.")
    ] = None,
    relatorio_definicao_id: Annotated[
        UUID | None,
        Query(
            alias="relatorioDefinicaoId",
            description="Filtra pelas preferencias de um relatorio do catalogo. Mutuamente exclusivo com tela.",
        ),
    ] = None,
    tela: Annotated[
        str | None,
        Query(
            alias="tela",
            description="Filtra pelas preferencias de uma tela (grade) da interface. Mutuamente exclusivo com relatorioDefinicaoId.",
        ),
    ] = None,
) -> contrato.ListaPreferenciaColunas:
    """Listar preferencias de colunas

    RFC-015: sempre filtrada pelo `usuario_id` do sujeito autenticado, nunca
    aceita um `usuarioId` de fora.
    """
    tenant_id = tenant_id_ou_erro(sujeito)
    usuario_id = _usuario_id_ou_erro(sujeito)
    linhas, paginacao = await preferencias_servico.listar_preferencias(
        sessao,
        tenant_id,
        usuario_id,
        relatorio_definicao_id=relatorio_definicao_id,
        tela=tela,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.PreferenciaColunas.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaPreferenciaColunas(dados=dados, paginacao=paginacao)


@roteador.put(
    "/v1/relatorios/preferencias-colunas",
    status_code=200,
    operation_id="salvarPreferenciaColunas",
    summary="Salvar preferencia de colunas",
    responses=RESPOSTAS_PADRAO,
)
async def salvar_preferencia_colunas(
    corpo: contrato.PreferenciaColunasCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
) -> contrato.PreferenciaColunas:
    """Salvar preferencia de colunas

    RFC-015: sem `Idempotency-Key` -- o corpo descreve o estado final
    completo, `INSERT ... ON CONFLICT ... DO UPDATE` sobre
    `uq_preferencias_colunas`. `usuarioId` e sempre o do sujeito autenticado,
    nunca aceito no corpo.
    """
    tenant_id = tenant_id_ou_erro(sujeito)
    usuario_id = _usuario_id_ou_erro(sujeito)
    preferencia = await preferencias_servico.salvar_preferencia(
        sessao,
        tenant_id,
        usuario_id,
        relatorio_definicao_id=corpo.relatorio_definicao_id,
        tela=corpo.tela,
        nome=corpo.nome,
        colunas=corpo.colunas,
        ordenacao=corpo.ordenacao,
        filtros=corpo.filtros,
        larguras=corpo.larguras,
        padrao=corpo.padrao,
    )
    return contrato.PreferenciaColunas.model_validate(preferencia, from_attributes=True)


# =============================================================================
# Agendamento -- ownership de A3 (T11). Regra de negocio em
# `app.relatorios.agendamentos`; nao editar esta secao alem de A3 (PCF §5).
# Rota LITERAL: tem que vir antes de `/v1/relatorios/{codigo}` (ver nota de
# ordem no topo do arquivo) -- por isso esta secao esta aqui, nao mais perto
# do final do arquivo como no stub original da Fase 0.
# =============================================================================
@roteador.get(
    "/v1/relatorios/agendamentos",
    status_code=200,
    operation_id="listarAgendamentosRelatorio",
    summary="Listar agendamentos de relatorio",
    responses=RESPOSTAS_PADRAO,
)
async def listar_agendamentos_relatorio(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
    """Listar agendamentos de relatorio"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await agendamentos_servico.listar_agendamentos(
        sessao,
        tenant_id,
        relatorio_definicao_id=relatorio_definicao_id,
        usuario_id=usuario_id,
        canal=canal,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.RelatorioAgendamento.model_validate(linha, from_attributes=True)
        for linha in linhas
    ]
    return contrato.ListaRelatorioAgendamento(dados=dados, paginacao=paginacao)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RelatorioAgendamentoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.criar"))],
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
) -> contrato.RelatorioAgendamento:
    """Criar agendamento de relatorio"""
    tenant_id = tenant_id_ou_erro(sujeito)
    agendamento = await agendamentos_servico.criar_agendamento(
        sessao,
        tenant_id,
        corpo,
        usuario_id_solicitante=sujeito.usuario_id,
    )
    return contrato.RelatorioAgendamento.model_validate(agendamento, from_attributes=True)


# =============================================================================
# Catalogo (item unico) e execucao -- ownership de A1 (T1/T3). Rotas
# PARAMETRIZADAS: precisam vir DEPOIS de todas as rotas literais acima (ver
# nota de ordem no topo do arquivo).
# =============================================================================
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
) -> contrato.RelatorioDefinicao:
    """Obter definicao de relatorio"""
    tenant_id = tenant_id_ou_erro(sujeito)
    definicao = await execucao_servico.obter_definicao(sessao, tenant_id, codigo)
    return contrato.RelatorioDefinicao.model_validate(definicao, from_attributes=True)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.executar"))],
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
    """Executar relatorio"""
    tenant_id = tenant_id_ou_erro(sujeito)
    config = obter_configuracao()
    parametros = execucao_servico.ParametrosExecucao(
        formato=formato,
        periodo_id=periodo_id,
        de=de,
        ate=ate,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        colaborador_id=colaborador_id,
        agrupamento=agrupamento,
        colunas=colunas,
        filtros=filtros,
        converter_decimal=converter_decimal,
        incluir_inativos=incluir_inativos,
        assincrono=assincrono,
    )
    execucao = await execucao_servico.executar_relatorio_pedido(
        sessao,
        tenant_id,
        codigo,
        parametros,
        usuario_id=sujeito.usuario_id,
        redis_url=config.redis_url,
    )
    return await execucao_servico.montar_execucao_resposta(execucao, codigo=codigo)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("relatorios.ler"))],
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
) -> contrato.RelatorioExecucao:
    """Obter execucao de relatorio"""
    tenant_id = tenant_id_ou_erro(sujeito)
    execucao = await execucao_servico.obter_execucao(sessao, tenant_id, execucao_id)
    return await execucao_servico.montar_execucao_resposta(execucao, sessao=sessao)
