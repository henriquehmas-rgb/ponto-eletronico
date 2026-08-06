"""Rotas da tag `biometria` do contrato.

Credenciais biometricas e equivalentes de fallback.
O vetor biometrico e dado pessoal sensivel: fica cifrado com chave externa ao banco, e versionado por modelo e NUNCA e exposto pela API, nem para o super administrador.

Regra de negocio implementada na fase F2 (agente A3, T9): estas rotas so
orquestram HTTP <-> `app.biometria.servico` (ciclo de vida da credencial) e
`app.biometria.cifra` (indiretamente, via `criar_biometria`). Nenhuma cifra
nem decifragem acontece aqui -- e nenhuma rota devolve o vetor decifrado
(ADR-006 regra 5, `PONTO-LGPD-002`).

`criarBiometria` recebe `vetor` (base64), `versaoModelo`, `provedor` e
`dimensao` fora do schema tipado `BiometriaCriar` -- o proprio
`ExemploBiometriaCriar` do `openapi.yaml` usa `versaoModelo`, que tampouco
esta no schema (nenhum `additionalProperties: false` os proibe; ver
`docs/backlog.md` e a docstring de `app.biometria.servico.DadosBiometriaCriar`).
Por isso esta rota le o corpo bruto via `Request.json()` para completar os
campos que o Pydantic gerado nao tipa.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.biometria import servico
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["biometria"])


def _biometria_para_schema(biometria: Any, versao_modelo: str | None) -> contrato.Biometria:
    """Converte a linha ORM de `biometrias` na resposta do contrato.

    NUNCA recebe o template em si -- so os metadados do ciclo de vida.
    `versaoModelo` e denormalizado do template ATIVO mais recente (a tabela
    `biometrias` nao guarda essa coluna, ver `schema.sql` secao 6).
    """
    # mypy sintetiza o `__init__` do Pydantic a partir do ALIAS de cada campo
    # (dataclass_transform nao enxerga `populate_by_name=True` em tempo de
    # tipagem) -- por isso os kwargs abaixo sao camelCase, mesmo o runtime
    # aceitando os dois nomes.
    return contrato.Biometria(
        id=biometria.id,
        tenantId=biometria.tenant_id,
        colaboradorId=biometria.colaborador_id,
        modalidade=biometria.modalidade,
        status=biometria.status,
        origemCadastro=biometria.origem_cadastro,
        qualidade=float(biometria.qualidade) if biometria.qualidade is not None else None,
        consentimentoId=biometria.consentimento_id,
        identificadorCartao=biometria.identificador_cartao,
        versaoModelo=versao_modelo,
        cadastradaEm=biometria.cadastrada_em,
        validadaEm=biometria.validada_em,
        revogadaEm=biometria.revogada_em,
        motivoRevogacao=biometria.motivo_revogacao,
        expiraEm=biometria.expira_em,
        criadoEm=biometria.criado_em,
        criadoPor=biometria.criado_por,
        atualizadoEm=biometria.atualizado_em,
        atualizadoPor=biometria.atualizado_por,
    )


def _decodificar_vetor(bruto: dict[str, Any]) -> bytes | None:
    """Decodifica `vetor` (base64) do corpo bruto. Nunca loga o conteudo."""
    valor = bruto.get("vetor")
    if not valor:
        return None
    if not isinstance(valor, str):
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="Campo 'vetor' precisa ser uma string base64."
        )
    try:
        return base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="Campo 'vetor' precisa ser base64 valido."
        ) from exc


@roteador.get(
    "/v1/biometrias",
    status_code=200,
    operation_id="listarBiometrias",
    summary="Listar credenciais biometricas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_biometrias(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("biometrias.ler"))],
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
        Query(alias="colaboradorId", description="Filtra pelas credenciais de um colaborador."),
    ] = None,
    modalidade: Annotated[
        str | None, Query(alias="modalidade", description="Filtra pela modalidade.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    versao_modelo: Annotated[
        str | None,
        Query(
            alias="versaoModelo", description="Filtra pela versao do modelo que gerou o template."
        ),
    ] = None,
) -> contrato.ListaBiometria:
    """Listar credenciais biometricas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, tem_mais, proximo = await servico.listar_biometrias(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        modalidade=modalidade,
        status=status,
        versao_modelo=versao_modelo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    # `versaoModelo` de cada item da PAGINA fica None: resolve-la exigiria uma
    # consulta por linha (N+1). O detalhe completo esta em `obterBiometria`.
    # Registrado como decisao de desempenho, nao lacuna -- ver docs/backlog.md.
    dados = [_biometria_para_schema(linha, None) for linha in linhas]
    return contrato.ListaBiometria(
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
    "/v1/biometrias",
    status_code=201,
    operation_id="criarBiometria",
    summary="Cadastrar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.BiometriaCriar,
    request: Request,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("biometrias.criar"))],
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
) -> contrato.Biometria:
    """Cadastrar credencial biometrica"""
    tenant_id = tenant_id_ou_erro(sujeito)
    bruto: dict[str, Any] = await request.json()
    vetor = _decodificar_vetor(bruto)
    versao_modelo = bruto.get("versaoModelo") or None
    provedor = bruto.get("provedor") or "facial-svc"
    dimensao = bruto.get("dimensao")

    dados = servico.DadosBiometriaCriar(
        colaborador_id=corpo.colaborador_id,
        modalidade=corpo.modalidade,
        origem_cadastro=corpo.origem_cadastro,
        consentimento_id=corpo.consentimento_id,
        qualidade=corpo.qualidade,
        identificador_cartao=corpo.identificador_cartao,
        vetor=vetor,
        versao_modelo=versao_modelo,
        provedor=provedor,
        dimensao=dimensao,
    )
    biometria = await servico.criar_biometria(
        sessao, tenant_id=tenant_id, dados=dados, usuario_id=sujeito.usuario_id
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=tenant_id, biometria_id=biometria.id
    )
    response.headers["Location"] = f"/v1/biometrias/{biometria.id}"
    return _biometria_para_schema(biometria, versao_ativa)


@roteador.get(
    "/v1/biometrias/{biometriaId}",
    status_code=200,
    operation_id="obterBiometria",
    summary="Obter credencial biometrica",
    responses=RESPOSTAS_PADRAO,
)
async def obter_biometria(
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
    ],
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("biometrias.ler"))],
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
) -> contrato.Biometria:
    """Obter credencial biometrica"""
    tenant_id = tenant_id_ou_erro(sujeito)
    biometria = await servico.obter_biometria(
        sessao, tenant_id=tenant_id, biometria_id=biometria_id, usuario_id=sujeito.usuario_id
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=tenant_id, biometria_id=biometria_id
    )
    return _biometria_para_schema(biometria, versao_ativa)


@roteador.delete(
    "/v1/biometrias/{biometriaId}",
    status_code=204,
    operation_id="revogarBiometria",
    summary="Revogar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def revogar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
    ],
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("biometrias.excluir"))],
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
    """Revogar credencial biometrica"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.revogar_biometria(
        sessao, tenant_id=tenant_id, biometria_id=biometria_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)


@roteador.post(
    "/v1/biometrias/{biometriaId}/validar",
    status_code=200,
    operation_id="validarBiometria",
    summary="Validar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def validar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
    ],
    corpo: contrato.DecisaoRequisicao,
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("biometrias.aprovar"))],
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
) -> contrato.Biometria:
    """Validar credencial biometrica"""
    tenant_id = tenant_id_ou_erro(sujeito)
    if corpo.decisao is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Campo 'decisao' e obrigatorio.")
    biometria = await servico.validar_biometria(
        sessao,
        tenant_id=tenant_id,
        biometria_id=biometria_id,
        decisao=corpo.decisao,
        comentario=corpo.comentario,
        usuario_id=sujeito.usuario_id,
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=tenant_id, biometria_id=biometria_id
    )
    return _biometria_para_schema(biometria, versao_ativa)
