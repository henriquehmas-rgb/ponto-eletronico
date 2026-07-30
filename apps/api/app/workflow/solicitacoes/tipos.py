"""CRUD do catálogo `tipos_solicitacao` (F10, T2, agente A1).

**Achado de contrato, registrado em `docs/backlog.md` (não corrigido em
silêncio -- PCF §2.7 é a lista fechada dos achados já conhecidos antes do
build; este é um sexto, encontrado durante a implementação).** O schema
gerado tipa `TipoSolicitacao.etapas`/`TipoSolicitacaoCriar.etapas` como
`dict[str, Any]` (`type: object` em `openapi.yaml`), e o próprio EXEMPLO do
contrato (`components.examples.ExemploTipoSolicitacaoCriar`/
`ExemploTipoSolicitacao`) mostra a forma `{"etapas": [{"ordem": N, "papel":
"..."}]}` -- um objeto com uma única chave `etapas` envelopando o array.
Só que `apps/api/migrations/seed_dev.py::TIPOS_SOLICITACAO` (dado de
fábrica, você não edita) grava a coluna `tipos_solicitacao.etapas` (JSONB)
como um ARRAY simples `[{"etapa": N, "papel": "..."}]`, sem o envelope e com
a chave `etapa` em vez de `ordem` -- confirmado lendo a linha real no banco
(`ponto_f10_a1`, tenant `seeg`). As duas formas nunca poderiam ter a mesma
representação Pydantic ao mesmo tempo: se a coluna guardasse o envelope
`{"etapas": [...]}"`, todo o dado de fábrica seria inválido; se guardasse o
array cru, todo `model_validate` contra `dict[str, Any]` quebraria (Pydantic
recusa `list` onde espera `dict`).

**Decisão fixada por este módulo, para não reescrever nem o contrato nem o
dado de fábrica:** a COLUNA sempre guarda o array cru (mesma forma de
`seed_dev.py`, para o dado de fábrica e o criado por `criarTipoSolicitacao`
serem indistinguíveis um do outro). A camada HTTP é quem faz a ponte:
`criarTipoSolicitacao` aceita o `etapas` do cliente em QUALQUER uma das duas
formas (array cru OU `{"etapas": [...]}"`, a última documentada no exemplo
do contrato) e grava o array cru; toda resposta (`listarTiposSolicitacao`/
`criarTipoSolicitacao`) devolve `{"etapas": [...]}"`, a forma que o schema
Pydantic (`dict[str, Any]`) aceita e que bate com o exemplo do contrato. A
posição de cada entrada no array é a ordem de execução da etapa -- este
módulo NUNCA lê a chave `etapa`/`ordem` de dentro da entrada para decidir a
ordem (evita depender de qual convenção de nome o cliente usou); só valida
que `papel` está presente e é um dos quatro valores aceitos.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import TipoSolicitacao
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.solicitacoes.erros_bd import traduzir_integridade
from app.workflow.solicitacoes.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"

#: Mesmo conjunto de `aprovacoes.papel` (`Papel2` no contrato gerado,
#: `packages/contracts/schema.sql` seção 11, `ck_aprovacoes_papel`).
PAPEIS_VALIDOS = frozenset({"gestor", "rh", "diretoria", "sistema"})

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(TipoSolicitacao.codigo, str),
    "criadoEm": CampoOrdenacao(TipoSolicitacao.criado_em, dt.datetime.fromisoformat),
}


def _normalizar_etapas_entrada(bruto: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Aceita `{"etapas": [...]}"` (forma do exemplo do contrato) ou um array
    cru diretamente (forma de `seed_dev.py`) e devolve a lista pronta para
    gravar na coluna, na ORDEM recebida -- ver docstring do módulo."""
    if bruto is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="etapas e obrigatorio.")
    lista_bruta: Any = bruto
    if isinstance(bruto, dict):
        lista_bruta = bruto.get("etapas", bruto.get("dados"))
    if not isinstance(lista_bruta, list) or not lista_bruta:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="etapas deve conter ao menos uma etapa."
        )
    etapas: list[dict[str, Any]] = []
    for indice, entrada in enumerate(lista_bruta, start=1):
        if not isinstance(entrada, dict) or "papel" not in entrada:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe=f"etapas[{indice}] precisa do campo 'papel'."
            )
        papel = entrada["papel"]
        if papel not in PAPEIS_VALIDOS:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO,
                detalhe=f"etapas[{indice}].papel invalido: {papel!r}.",
            )
        etapas.append({"etapa": indice, "papel": papel})
    return etapas


def _etapas_para_resposta(bruto: Any) -> dict[str, Any]:
    """Converte o array cru gravado na coluna de volta para a forma
    `dict[str, Any]` que o schema Pydantic exige (ver docstring do módulo)."""
    if isinstance(bruto, dict):
        return bruto
    if isinstance(bruto, list):
        return {"etapas": bruto}
    return {"etapas": []}


def papeis_da_cadeia(etapas_bruto: Any) -> list[str]:
    """Lê os papéis da cadeia, na ordem, tolerante às duas formas aceitas em
    `_normalizar_etapas_entrada`/gravadas na coluna. Usado por
    `app.workflow.aprovacoes.servico` para saber quantas etapas tem a
    cadeia e qual o papel de cada uma."""
    lista = etapas_bruto.get("etapas", []) if isinstance(etapas_bruto, dict) else etapas_bruto
    if not isinstance(lista, list):
        return []
    papeis: list[str] = []
    for entrada in lista:
        if isinstance(entrada, dict) and "papel" in entrada:
            papeis.append(str(entrada["papel"]))
    return papeis


_CAMPOS_TIPO_SOLICITACAO = (
    "id",
    "tenant_id",
    "codigo",
    "nome",
    "descricao",
    "categoria",
    "prazo_resposta_horas",
    "escalonar_apos_horas",
    "exige_anexo",
    "exige_justificativa",
    "permite_retroativo_dias",
    "tipo_tratamento_id",
    "ativo",
    "criado_em",
    "criado_por",
    "atualizado_em",
    "atualizado_por",
    "excluido_em",
    "excluido_por",
)


def tipo_para_schema(linha: TipoSolicitacao) -> esquemas.TipoSolicitacao:
    """`model_validate(linha, from_attributes=True)` quebraria em `etapas`
    (ver docstring do módulo) -- construção manual do dicionário, com
    `etapas` já convertido para a forma aceita pelo schema."""
    dados: dict[str, Any] = {campo: getattr(linha, campo) for campo in _CAMPOS_TIPO_SOLICITACAO}
    dados["etapas"] = _etapas_para_resposta(linha.etapas)
    return esquemas.TipoSolicitacao.model_validate(dados)


async def obter_tipo_solicitacao(sessao: AsyncSession, tipo_id: UUID) -> TipoSolicitacao:
    tipo = await sessao.get(TipoSolicitacao, tipo_id)
    if tipo is None or tipo.excluido_em is not None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Tipo de solicitacao nao encontrado."
        )
    return tipo


async def criar_tipo_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.TipoSolicitacaoCriar,
    *,
    usuario_id: UUID | None,
) -> TipoSolicitacao:
    etapas = _normalizar_etapas_entrada(dados.etapas)

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True, exclude={"etapas"})
    if "categoria" in campos and campos["categoria"] is not None:
        bruto = campos["categoria"]
        campos["categoria"] = bruto.value if hasattr(bruto, "value") else bruto
    campos["etapas"] = etapas

    tipo = TipoSolicitacao(tenant_id=tenant_id, criado_por=usuario_id, **campos)
    sessao.add(tipo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return tipo


async def listar_tipos_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    categoria: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[TipoSolicitacao], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="codigo"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(TipoSolicitacao).where(
        TipoSolicitacao.tenant_id == tenant_id, TipoSolicitacao.excluido_em.is_(None)
    )
    if categoria is not None:
        consulta = consulta.where(TipoSolicitacao.categoria == categoria)
    if ativo is not None:
        consulta = consulta.where(TipoSolicitacao.ativo == ativo)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoSolicitacao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "codigo" if ordenacao.campo == "codigo" else "criado_em"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
