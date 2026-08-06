"""Rotas da tag `apuracoes` do contrato. GERADO -- nao editar.

Resultado do motor de calculo por vinculo e dia, com decomposicao auditavel de cada bloco de minutos, e as ocorrencias detectadas.
A apuracao e deterministica e recalculavel: mesmos insumos produzem exatamente o mesmo resultado.

Regra de negocio destas operacoes entra na fase F4. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query

from app.apuracao.dominio import consulta
from app.apuracao.tratamento import ocorrencias as ocorrencias_servico
from app.apuracao.tratamento import recalculo
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["apuracoes"])


@roteador.get(
    "/v1/apuracoes",
    status_code=200,
    operation_id="listarApuracoes",
    summary="Listar apuracoes do dia",
    responses=RESPOSTAS_PADRAO,
)
async def listar_apuracoes(
    de: Annotated[date, Query(alias="de", description="Primeiro dia do intervalo.")],
    ate: Annotated[date, Query(alias="ate", description="Ultimo dia do intervalo.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("apuracoes.ler"))],
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
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pela empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade.")
    ] = None,
    departamento_id: Annotated[
        UUID | None, Query(alias="departamentoId", description="Filtra pelo departamento.")
    ] = None,
    equipe_id: Annotated[
        UUID | None, Query(alias="equipeId", description="Filtra pela equipe.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador.")
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelo vinculo.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    somente_inconsistentes: Annotated[
        bool | None,
        Query(
            alias="somenteInconsistentes",
            description="Lista apenas dias com marcacao impar, ocorrencia aberta ou apuracao pendente.",
        ),
    ] = None,
    incluir_componentes: Annotated[
        bool | None,
        Query(
            alias="incluirComponentes",
            description="Inclui a decomposicao do calculo em cada dia. Aumenta bastante o volume da resposta.",
        ),
    ] = None,
    incluir_marcacoes: Annotated[
        bool | None,
        Query(
            alias="incluirMarcacoes", description="Inclui as marcacoes consideradas em cada dia."
        ),
    ] = None,
) -> contrato.ListaApuracaoDia:
    """Listar apuracoes do dia"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados, paginacao = await consulta.listar_apuracoes(
        sessao,
        tenant_id,
        de=de,
        ate=ate,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        equipe_id=equipe_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        status=status,
        somente_inconsistentes=somente_inconsistentes,
        incluir_componentes=incluir_componentes,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaApuracaoDia(dados=list(dados), paginacao=paginacao)


@roteador.get(
    "/v1/apuracoes/{apuracaoId}",
    status_code=200,
    operation_id="obterApuracao",
    summary="Obter apuracao do dia",
    responses=RESPOSTAS_PADRAO,
)
async def obter_apuracao(
    apuracao_id: Annotated[
        UUID, Path(alias="apuracaoId", description="Identificador da apuracao.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("apuracoes.ler"))],
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
) -> contrato.ApuracaoDia:
    """Obter apuracao do dia"""
    tenant_id_ou_erro(sujeito)
    return await consulta.obter_apuracao(sessao, apuracao_id)


@roteador.post(
    "/v1/apuracoes/recalcular",
    status_code=202,
    operation_id="recalcularApuracoes",
    summary="Recalcular apuracoes",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def recalcular_apuracoes(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RecalculoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("apuracoes.executar"))],
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
) -> contrato.ProcessamentoAssincrono:
    """Recalcular apuracoes"""
    tenant_id = tenant_id_ou_erro(sujeito)
    config = obter_configuracao()
    job_id, total_vinculos = await recalculo.enfileirar_recalculo(
        sessao, tenant_id, corpo, redis_url=config.redis_url
    )
    return contrato.ProcessamentoAssincrono.model_validate(
        {
            "id": job_id,
            "tipo": "recalculo",
            "status": "enfileirado",
            "total_itens": total_vinculos,
            "itens_processados": 0,
        }
    )


@roteador.get(
    "/v1/ocorrencias",
    status_code=200,
    operation_id="listarOcorrencias",
    summary="Listar ocorrencias",
    responses=RESPOSTAS_PADRAO,
)
async def listar_ocorrencias(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("ocorrencias.ler"))],
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
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pela empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador.")
    ] = None,
    codigo: Annotated[
        str | None, Query(alias="codigo", description="Filtra pelo tipo de ocorrencia.")
    ] = None,
    severidade: Annotated[
        str | None, Query(alias="severidade", description="Filtra pela gravidade.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Ocorrencias a partir desta data.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Ocorrencias ate esta data.")
    ] = None,
) -> contrato.ListaOcorrencia:
    """Listar ocorrencias"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados, paginacao = await consulta.listar_ocorrencias(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        codigo=codigo,
        severidade=severidade,
        status=status,
        de=de,
        ate=ate,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaOcorrencia(dados=list(dados), paginacao=paginacao)


@roteador.patch(
    "/v1/ocorrencias/{ocorrenciaId}",
    status_code=200,
    operation_id="atualizarOcorrencia",
    summary="Atualizar ocorrencia",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_ocorrencia(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    ocorrencia_id: Annotated[
        UUID, Path(alias="ocorrenciaId", description="Identificador da ocorrencia.")
    ],
    corpo: contrato.OcorrenciaAtualizar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("ocorrencias.editar"))],
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
) -> contrato.Ocorrencia:
    """Atualizar ocorrencia"""
    tenant_id_ou_erro(sujeito)
    atualizada = await ocorrencias_servico.atualizar_ocorrencia(
        sessao, ocorrencia_id, corpo, usuario_id=sujeito.usuario_id
    )
    return contrato.Ocorrencia.model_validate(atualizada, from_attributes=True)
