"""Rotas da tag `biometria` do contrato.

Credenciais biometricas e equivalentes de fallback.
O vetor biometrico e dado pessoal sensivel: fica cifrado com chave externa ao banco, e versionado por modelo e NUNCA e exposto pela API, nem para o super administrador.

Regra de negocio implementada na fase F2 (agente A3, T9): estas rotas so
orquestram HTTP <-> `app.biometria.servico` (ciclo de vida da credencial) e
`app.biometria.cifra` (indiretamente, via `criar_biometria`). Nenhuma cifra
nem decifragem acontece aqui -- e nenhuma rota devolve o vetor decifrado
(ADR-006 regra 5, `PONTO-LGPD-002`).

`criarBiometria` recebe `vetor` (base64), `versaoModelo`, `provedor`,
`dimensao`, `fotoBase64` e `mimeType`. Ate 09/08/2026 NENHUM desses seis
estava declarado em `BiometriaCriar` (o proprio `ExemploBiometriaCriar` do
`openapi.yaml` ja usava `versaoModelo`, que tampouco estava no schema; nenhum
`additionalProperties: false` os proibia). **RFC-021 declarou os seis no
contrato** -- `packages/contracts/openapi.yaml`, `components.schemas.
BiometriaCriar` -- e formalizou a exclusividade mutua entre `fotoBase64` e
`vetor`.

Esta rota continua lendo o corpo bruto via `Request.json()`, de proposito:
`app/schemas/contrato.py` e GERADO por `tools/gerar_do_contrato.py` e ainda
nao foi regerado (a regeneracao exige o extra `codegen` na versao fixada --
regerar com outra versao renomeia classes de enum nao relacionadas e quebra
importacoes de outros modulos). No dia em que o arquivo for regerado,
`corpo.foto_base64`/`corpo.vetor`/... passam a existir e a leitura pode ser
simplificada; ate la, o comportamento observavel e exatamente o mesmo, porque
Pydantic v2 sem `extra` declarado IGNORA chave desconhecida, nao a rejeita.

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

import base64
import binascii
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.biometria import cliente_facial, servico
from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["biometria"])

# Uma instancia por par (permissao, escopo) -- nao uma fabrica chamada de novo
# dentro do handler: mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_BIOMETRIAS_LER = exigir_permissao_ou_escopo(
    permissao="biometrias.ler", escopo="biometria:ler"
)
_ACESSO_BIOMETRIAS_CRIAR = exigir_permissao_ou_escopo(
    permissao="biometrias.criar", escopo="biometria:escrever"
)
_ACESSO_BIOMETRIAS_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="biometrias.excluir", escopo="biometria:escrever"
)
_ACESSO_BIOMETRIAS_APROVAR = exigir_permissao_ou_escopo(
    permissao="biometrias.aprovar", escopo="biometria:escrever"
)


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


async def _extrair_template(
    bruto: dict[str, Any], *, colaborador_id: UUID
) -> cliente_facial.ResultadoEnroll | None:
    """`fotoBase64` no corpo -> chama `facial-svc:/enroll` e devolve o template.

    **`fotoBase64` esta declarado no contrato desde a RFC-021** (09/08/2026),
    em `components.schemas.BiometriaCriar`, com o mesmo nome e o mesmo
    significado que `MarcacaoCriar.fotoBase64` ja usava ("Captura ao vivo em
    base64... NUNCA aceita upload de arquivo previamente salvo"). Continua
    sendo lido do corpo bruto pelo motivo explicado na docstring do modulo
    (`app/schemas/contrato.py` ainda nao regerado) -- e leitura, nao contorno
    de contrato.

    **`fotoBase64` e `vetor` sao mutuamente exclusivos** (regra agora escrita
    na descricao do schema, verificada aqui). Aceitar os dois
    obrigaria a escolher em silencio entre um template extraido aqui e um
    template que o cliente afirma ter -- e a escolha errada grava biometria da
    pessoa errada. Erro explicito e a unica resposta honesta.

    **Falha fechada.** `facial-svc` fora do ar durante um cadastro vira
    `503 PONTO-INT-003` (retentavel), nunca uma `biometrias` gravada sem
    template: uma credencial que parece cadastrada e nao verifica ninguem e pior
    que a ausencia dela, porque o RH a aprova achando que esta pronta.
    """
    foto = bruto.get("fotoBase64")
    if not foto:
        return None
    if not isinstance(foto, str):
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="Campo 'fotoBase64' precisa ser uma string base64."
        )
    if bruto.get("vetor"):
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="Envie 'fotoBase64' (o servidor extrai o template) ou 'vetor', nunca os dois.",
        )
    try:
        return await cliente_facial.enroll(
            imagem_base64=foto,
            mime_type=str(bruto.get("mimeType") or "image/jpeg"),
            # Identificador OPACO da operacao: o facial-svc nunca recebe CPF,
            # nome nem matricula (ver `facial/esquemas.py`). O UUID do
            # colaborador ja e opaco fora deste banco e amarra a chamada a
            # `acessos_dados_sensiveis`.
            referencia=f"enroll:{colaborador_id}",
        )
    except cliente_facial.FacialSvcIndisponivel as exc:
        raise ErroDeAplicacao(
            "PONTO-INT-003",
            detalhe="Servico de reconhecimento facial indisponivel. Tente novamente.",
            contexto_log={"motivo": exc.motivo},
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_BIOMETRIAS_LER)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, tem_mais, proximo = await servico.listar_biometrias(
        sessao,
        tenant_id=acesso.tenant_id,
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_BIOMETRIAS_CRIAR)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    bruto: dict[str, Any] = await request.json()
    extraido = await _extrair_template(bruto, colaborador_id=corpo.colaborador_id)
    if extraido is not None:
        # `versaoModelo`/`dimensao` do CORPO sao ignorados quando o servidor
        # extraiu o template: o carimbo tem que ser o do motor que gerou o
        # vetor, nunca o que o cliente afirma (ADR-006 regra 3 -- carimbo que
        # mente invalida a base biometrica inteira em silencio).
        vetor: bytes | None = extraido.vetor
        versao_modelo: str | None = extraido.versao_modelo
        dimensao: Any = extraido.dimensao
    else:
        vetor = _decodificar_vetor(bruto)
        versao_modelo = bruto.get("versaoModelo") or None
        dimensao = bruto.get("dimensao")
    provedor = bruto.get("provedor") or "facial-svc"

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
        sessao,
        tenant_id=acesso.tenant_id,
        dados=dados,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=acesso.tenant_id, biometria_id=biometria.id
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_BIOMETRIAS_LER)],
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
    """Obter credencial biometrica"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    biometria = await servico.obter_biometria(
        sessao,
        tenant_id=acesso.tenant_id,
        biometria_id=biometria_id,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=acesso.tenant_id, biometria_id=biometria_id
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_BIOMETRIAS_EXCLUIR)],
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
    """Revogar credencial biometrica"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.revogar_biometria(
        sessao,
        tenant_id=acesso.tenant_id,
        biometria_id=biometria_id,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_BIOMETRIAS_APROVAR)],
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
    """Validar credencial biometrica"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    if corpo.decisao is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Campo 'decisao' e obrigatorio.")
    biometria = await servico.validar_biometria(
        sessao,
        tenant_id=acesso.tenant_id,
        biometria_id=biometria_id,
        decisao=corpo.decisao,
        comentario=corpo.comentario,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    versao_ativa = await servico.versao_modelo_ativa(
        sessao, tenant_id=acesso.tenant_id, biometria_id=biometria_id
    )
    return _biometria_para_schema(biometria, versao_ativa)
