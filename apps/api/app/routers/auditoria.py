"""Rotas da tag `auditoria` do contrato.

Trilha de auditoria append-only e encadeada por hash: cada linha carrega o
hash da anterior, o que torna remocao silenciosa detectavel e verificavel sob
demanda. Regra de negocio implementada na F1/A3 (T10) -- ver
`app.identidade.auditoria.servico` e `app.identidade.auditoria.hash_chain`.

Autenticacao dupla (retrofit de 2026-08-08): o contrato ja declarava os tres
esquemas alternativos por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas
so sessao humana era aceita ate agora. `Depends(exigir_permissao(...))`
trocado por `Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E'
tentada primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
Mesmo padrao ja provado em `app/routers/empresas.py`/`webhooks.py`.
"""

from __future__ import annotations

import datetime as _dt
from datetime import datetime
from typing import Annotated, Any, TypeVar
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pydantic import BaseModel

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.identidade.auditoria import hash_chain, servico
from app.identidade.rbac._contrato import contrato as _contrato_orm
from app.schemas import contrato

roteador = APIRouter(tags=["auditoria"])

# Uma instancia por par (permissao, escopo) usado no arquivo -- nunca uma
# chamada nova a `exigir_permissao_ou_escopo` dentro do handler (identidade
# estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="auditoria.ler", escopo="auditoria:ler")
_ACESSO_EXECUTAR = exigir_permissao_ou_escopo(
    permissao="auditoria.executar", escopo="auditoria:ler"
)

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _para_schema(schema_cls: type[_SchemaT], origem: Any, **extras: Any) -> _SchemaT:
    """Ver docstring da mesma funcao em `app/routers/admin.py`."""
    dados = {nome: getattr(origem, nome, None) for nome in schema_cls.model_fields}
    dados.update(extras)
    return schema_cls.model_validate(dados)


@roteador.get(
    "/v1/auditoria",
    status_code=200,
    operation_id="listarAuditoria",
    summary="Listar trilha de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def listar_auditoria(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    entidade: Annotated[str | None, Query(alias="entidade")] = None,
    entidade_id: Annotated[UUID | None, Query(alias="entidadeId")] = None,
    usuario_id: Annotated[UUID | None, Query(alias="usuarioId")] = None,
    acao: Annotated[str | None, Query(alias="acao")] = None,
    resultado: Annotated[str | None, Query(alias="resultado")] = None,
    origem: Annotated[str | None, Query(alias="origem")] = None,
    de: Annotated[datetime | None, Query(alias="de")] = None,
    ate: Annotated[datetime | None, Query(alias="ate")] = None,
) -> contrato.ListaRegistroAuditoria:
    """Listar trilha de auditoria."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await servico.listar_auditoria(
        sessao,
        tenant_id=tenant_id,
        cursor=cursor,
        limite=limite,
        entidade=entidade,
        entidade_id=entidade_id,
        usuario_id=usuario_id,
        acao=acao,
        resultado=resultado,
        origem=origem,
        de=de,
        ate=ate,
    )
    dados = [_para_schema(contrato.RegistroAuditoria, linha) for linha in linhas]
    return contrato.ListaRegistroAuditoria(
        dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao)
    )


@roteador.get(
    "/v1/auditoria/{registroId}",
    status_code=200,
    operation_id="obterRegistroAuditoria",
    summary="Obter registro de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def obter_registro_auditoria(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    registro_id: Annotated[UUID, Path(alias="registroId")],
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.RegistroAuditoria:
    """Obter registro de auditoria."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    registro = await servico.obter_registro_auditoria(
        sessao, tenant_id=tenant_id, registro_id=registro_id
    )
    return _para_schema(contrato.RegistroAuditoria, registro)


@roteador.post(
    "/v1/auditoria/verificar-cadeia",
    status_code=200,
    operation_id="verificarCadeiaAuditoria",
    summary="Verificar cadeia de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def verificar_cadeia_auditoria(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXECUTAR)],
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.VerificacaoCadeiaRequisicao,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.VerificacaoCadeiaResposta:
    """Verificar a integridade da cadeia de hash da trilha de auditoria.

    `de`/`ate` (instante) do corpo restringem por `ocorrido_em` antes de
    aplicar `sequenciaDe`/`sequenciaAte`, quando informados -- a formula do
    hash so precisa da faixa de sequencia; a janela de tempo e resolvida aqui
    para a faixa de sequencia correspondente.
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    sequencia_de = corpo.sequencia_de
    sequencia_ate = corpo.sequencia_ate
    if corpo.de is not None or corpo.ate is not None:
        sequencia_de, sequencia_ate = await _faixa_sequencia_por_instante(
            sessao, tenant_id=tenant_id, de=corpo.de, ate=corpo.ate
        )
    resultado = await hash_chain.verificar_cadeia(
        sessao,
        tenant_id=tenant_id,
        sequencia_de=sequencia_de,
        sequencia_ate=sequencia_ate,
    )
    return contrato.VerificacaoCadeiaResposta.model_validate(
        {
            "sequenciaInicial": resultado.sequencia_inicial,
            "sequenciaFinal": resultado.sequencia_final,
            "totalVerificado": resultado.total_verificado,
            "integra": resultado.integra,
            "primeiraDivergenciaSequencia": resultado.primeira_divergencia_sequencia,
            "lacunas": resultado.lacunas,
            "verificadoEm": _dt.datetime.now(_dt.UTC),
        }
    )


async def _faixa_sequencia_por_instante(
    sessao: SessaoDb, *, tenant_id: UUID, de: datetime | None, ate: datetime | None
) -> tuple[int | None, int | None]:
    """Resolve `de`/`ate` (instante) do corpo de `verificarCadeiaAuditoria` para
    a faixa `(sequencia_de, sequencia_ate)` correspondente em `auditoria`."""
    consulta = sa.select(
        sa.func.min(_contrato_orm.Auditoria.sequencia),
        sa.func.max(_contrato_orm.Auditoria.sequencia),
    ).where(_contrato_orm.Auditoria.tenant_id == tenant_id)
    if de is not None:
        consulta = consulta.where(_contrato_orm.Auditoria.ocorrido_em >= de)
    if ate is not None:
        consulta = consulta.where(_contrato_orm.Auditoria.ocorrido_em <= ate)
    minimo, maximo = (await sessao.execute(consulta)).one()
    return minimo, maximo
