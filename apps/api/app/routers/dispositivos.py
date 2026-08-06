"""Rotas da tag `dispositivos` do contrato.

Aparelhos capazes de originar marcacao e seu estado antifraude conhecido.
A regra e de um unico dispositivo ativo por colaborador, e a troca exige aprovacao do RH.

Regra de negocio implementada na fase F2 (agente A3, T9): estas rotas so
orquestram HTTP <-> `app.biometria.dispositivos` (cadastro e vinculo). Os
sinais antifraude (`attestation_status`, `root_detectado`, ...) sao apenas
cadastrados e expostos aqui -- a avaliacao/score e da F14 (secao 9 do PCF).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.biometria import dispositivos as servico
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["dispositivos"])


def _dispositivo_para_schema(
    dispositivo: Any, colaborador_vinculado_id: UUID | None
) -> contrato.Dispositivo:
    # mypy sintetiza o `__init__` do Pydantic a partir do ALIAS de cada campo
    # (dataclass_transform nao enxerga `populate_by_name=True` em tempo de
    # tipagem) -- por isso os kwargs abaixo sao camelCase, mesmo o runtime
    # aceitando os dois nomes.
    return contrato.Dispositivo(
        id=dispositivo.id,
        tenantId=dispositivo.tenant_id,
        empresaId=dispositivo.empresa_id,
        unidadeId=dispositivo.unidade_id,
        tipo=dispositivo.tipo,
        plataforma=dispositivo.plataforma,
        identificador=dispositivo.identificador,
        nome=dispositivo.nome,
        fabricante=dispositivo.fabricante,
        modelo=dispositivo.modelo,
        versaoSo=dispositivo.versao_so,
        versaoApp=dispositivo.versao_app,
        status=dispositivo.status,
        attestationStatus=dispositivo.attestation_status,
        attestationVerificadoEm=dispositivo.attestation_verificado_em,
        rootDetectado=dispositivo.root_detectado,
        emuladorDetectado=dispositivo.emulador_detectado,
        modoDesenvolvedor=dispositivo.modo_desenvolvedor,
        depuracaoUsb=dispositivo.depuracao_usb,
        ultimoAcessoEm=dispositivo.ultimo_acesso_em,
        ultimoIp=str(dispositivo.ultimo_ip) if dispositivo.ultimo_ip is not None else None,
        colaboradorVinculadoId=colaborador_vinculado_id,
        observacoes=dispositivo.observacoes,
        criadoEm=dispositivo.criado_em,
        criadoPor=dispositivo.criado_por,
        atualizadoEm=dispositivo.atualizado_em,
        atualizadoPor=dispositivo.atualizado_por,
        excluidoEm=dispositivo.excluido_em,
        excluidoPor=dispositivo.excluido_por,
    )


@roteador.get(
    "/v1/dispositivos",
    status_code=200,
    operation_id="listarDispositivos",
    summary="Listar dispositivos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_dispositivos(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.ler"))],
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
        Query(alias="empresaId", description="Filtra pelos dispositivos de uma empresa."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Filtra pelos dispositivos de uma unidade."),
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador vinculado.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo tipo.")] = None,
    plataforma: Annotated[
        str | None, Query(alias="plataforma", description="Filtra pela plataforma.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    attestation_status: Annotated[
        str | None,
        Query(alias="attestationStatus", description="Filtra pelo ultimo veredito de attestation."),
    ] = None,
    com_risco: Annotated[
        bool | None,
        Query(
            alias="comRisco",
            description="Quando verdadeiro, lista apenas dispositivos com root, emulador, modo desenvolvedor ou depuracao USB detectados.",
        ),
    ] = None,
) -> contrato.ListaDispositivo:
    """Listar dispositivos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, tem_mais, proximo = await servico.listar_dispositivos(
        sessao,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        tipo=tipo,
        plataforma=plataforma,
        status=status,
        attestation_status=attestation_status,
        com_risco=com_risco,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    # Quando o filtro `colaboradorId` foi usado, o vinculo ativo E o proprio
    # filtro -- sem consulta extra. Sem filtro, o campo fica None na pagina
    # (resolve-lo por linha seria N+1); `obterDispositivo` devolve o detalhe.
    dados = [_dispositivo_para_schema(linha, colaborador_id) for linha in linhas]
    return contrato.ListaDispositivo(
        dados=dados,
        paginacao=contrato.Paginacao(
            proximoCursor=proximo,
            cursorAnterior=None,
            temMais=tem_mais,
            limite=limite or 50,
            totalEstimado=None,
        ),
    )


@roteador.post(
    "/v1/dispositivos",
    status_code=201,
    operation_id="criarDispositivo",
    summary="Criar dispositivo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.DispositivoCriar,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.criar"))],
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
) -> contrato.Dispositivo:
    """Criar dispositivo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = servico.DadosDispositivoCriar(
        empresa_id=corpo.empresa_id,
        unidade_id=corpo.unidade_id,
        tipo=corpo.tipo,
        plataforma=corpo.plataforma,
        identificador=corpo.identificador,
        nome=corpo.nome,
        fabricante=corpo.fabricante,
        modelo=corpo.modelo,
        versao_so=corpo.versao_so,
        versao_app=corpo.versao_app,
        status=corpo.status,
        root_detectado=corpo.root_detectado,
        emulador_detectado=corpo.emulador_detectado,
        modo_desenvolvedor=corpo.modo_desenvolvedor,
        depuracao_usb=corpo.depuracao_usb,
        observacoes=corpo.observacoes,
    )
    dispositivo = await servico.criar_dispositivo(
        sessao, tenant_id=tenant_id, dados=dados, usuario_id=sujeito.usuario_id
    )
    response.headers["Location"] = f"/v1/dispositivos/{dispositivo.id}"
    return _dispositivo_para_schema(dispositivo, None)


@roteador.get(
    "/v1/dispositivos/{dispositivoId}",
    status_code=200,
    operation_id="obterDispositivo",
    summary="Obter dispositivo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_dispositivo(
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.ler"))],
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
) -> contrato.Dispositivo:
    """Obter dispositivo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dispositivo = await servico.obter_dispositivo(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id
    )
    colaborador_vinculado = await servico.colaborador_vinculado_atual(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id
    )
    return _dispositivo_para_schema(dispositivo, colaborador_vinculado)


@roteador.patch(
    "/v1/dispositivos/{dispositivoId}",
    status_code=200,
    operation_id="atualizarDispositivo",
    summary="Atualizar dispositivo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    corpo: contrato.DispositivoAtualizar,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.editar"))],
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
) -> contrato.Dispositivo:
    """Atualizar dispositivo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = servico.DadosDispositivoAtualizar(
        empresa_id=corpo.empresa_id,
        unidade_id=corpo.unidade_id,
        tipo=corpo.tipo,
        plataforma=corpo.plataforma,
        identificador=corpo.identificador,
        nome=corpo.nome,
        fabricante=corpo.fabricante,
        modelo=corpo.modelo,
        versao_so=corpo.versao_so,
        versao_app=corpo.versao_app,
        status=corpo.status,
        root_detectado=corpo.root_detectado,
        emulador_detectado=corpo.emulador_detectado,
        modo_desenvolvedor=corpo.modo_desenvolvedor,
        depuracao_usb=corpo.depuracao_usb,
        observacoes=corpo.observacoes,
    )
    dispositivo = await servico.atualizar_dispositivo(
        sessao,
        tenant_id=tenant_id,
        dispositivo_id=dispositivo_id,
        dados=dados,
        usuario_id=sujeito.usuario_id,
    )
    colaborador_vinculado = await servico.colaborador_vinculado_atual(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id
    )
    return _dispositivo_para_schema(dispositivo, colaborador_vinculado)


@roteador.delete(
    "/v1/dispositivos/{dispositivoId}",
    status_code=204,
    operation_id="excluirDispositivo",
    summary="Excluir dispositivo",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.excluir"))],
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
    """Excluir dispositivo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.excluir_dispositivo(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)


@roteador.post(
    "/v1/dispositivos/{dispositivoId}/vincular",
    status_code=201,
    operation_id="vincularDispositivo",
    summary="Vincular dispositivo a colaborador",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def vincular_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    corpo: contrato.VinculoDispositivoRequisicao,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("dispositivos.editar"))],
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
) -> contrato.Dispositivo:
    """Vincular dispositivo a colaborador"""
    tenant_id = tenant_id_ou_erro(sujeito)
    if corpo.colaborador_id is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Campo 'colaboradorId' e obrigatorio.")
    dispositivo = await servico.vincular_dispositivo(
        sessao,
        tenant_id=tenant_id,
        dispositivo_id=dispositivo_id,
        colaborador_id=corpo.colaborador_id,
        aprovar_imediatamente=bool(corpo.aprovar_imediatamente),
        revogar_anterior=bool(corpo.revogar_anterior),
        motivo=corpo.motivo,
        usuario_id=sujeito.usuario_id,
    )
    colaborador_vinculado = await servico.colaborador_vinculado_atual(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo.id
    )
    response.headers["Location"] = f"/v1/dispositivos/{dispositivo.id}"
    return _dispositivo_para_schema(dispositivo, colaborador_vinculado)
