"""Consentimento LGPD versionado (F14/A3, PCF secao 5 "A3 -- LGPD").

`criarConsentimento` / `revogarConsentimento` / `listarConsentimentos`.

**Vinculo com "tipos de tratamento".** O PCF desta fase menciona vinculo com
"tipos_tratamento". Ha uma tabela chamada exatamente `tipos_tratamento` no
schema (secao 9, "TRATAMENTO E APURACAO"), mas ela cataloga as categorias de
CORRECAO DE JORNADA (`inclusao_marcacao`, `ajuste_intervalo`, `abono`, ...) --
nada a ver com finalidade de tratamento de dado pessoal. `consentimentos` nao
tem nenhuma FK para ela (confirmado em `packages/contracts/schema.sql`
secao 15: a coluna e `finalidade`, um `CHECK` com os seis valores do enum
`Finalidade` do contrato). Registrado aqui, e em `docs/backlog.md`, como
achado de fraseado do PCF -- nenhuma mudanca de contrato foi feita: o
vinculo real e por `finalidade`, exatamente como o contrato ja modela.

**Versao vigente do termo (ADR implicito, decisao desta fase).** O contrato
recusa aceitar uma versao de termo que "nao e a vigente"
(`PONTO-LGPD-004`), mas nao existe tabela de catalogo de termos em
`schema.sql` -- so a coluna livre `consentimentos.versao_termo`. Sem inventar
DDL nova (fora do escopo de A3, secao 6 do PCF), a versao vigente de um par
(tenant, finalidade) e definida operacionalmente como a `versao_termo` do
ultimo consentimento ja registrado para aquele par, por `criado_em`. O
primeiro registro de uma finalidade em um tenant sempre e aceito (nao ha o
que comparar); a partir do segundo, submeter uma versao diferente da ultima
usada e recusado -- e exatamente o cenario que `causa_provavel` do catalogo
de erros descreve ("Aplicativo desatualizado exibindo termo antigo").

**`hashTermo` e obrigatorio na pratica.** O contrato marca `hashTermo` como
opcional em `ConsentimentoCriar`, mas sem ele nao ha como cumprir ADR-006
regra 7 ("guarde o texto EXATO aceito"): o hash e a UNICA prova de qual texto
foi lido. Ausente, a operacao recusa com `PONTO-VAL-001`. `textoTermoRef`
(chave do texto no armazenamento de objetos) e opcional de verdade: sem ele,
grava-se uma chave convencional derivada de finalidade+versao, porque
`consentimentos.texto_termo_ref` e `NOT NULL` no schema e o contrato nao tem
nenhuma operacao de upload de termo (mesma classe de lacuna que
`docs/backlog.md` ja registra para `criarBiometria`/`versaoModelo`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    AcessoDadoSensivel,
    Biometria,
    BiometriaTemplate,
    Colaborador,
    Consentimento,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.lgpd.comum import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    normalizar_limite,
    traduzir_integridade,
)

__all__ = [
    "CAMPOS_ORDENACAO_CONSENTIMENTO",
    "DadosConsentimentoCriar",
    "criar_consentimento",
    "expurgar_templates_biometricos",
    "listar_consentimentos",
    "revogar_consentimento",
]

CAMPOS_ORDENACAO_CONSENTIMENTO = frozenset({"concedidoEm", "finalidade"})

#: Finalidade de consentimento -> modalidade de `biometrias`. So facial e
#: digital tem vetor biometrico de verdade (mesmo mapa de
#: `app.biometria.servico._FINALIDADE_POR_MODALIDADE`, invertido -- duplicado
#: aqui de proposito: e o mesmo motivo documentado em varios modulos desta
#: base ("apps/worker nao importa apps/api/app/biometria", "device-gw nao
#: importa app/core") -- manter os dois modulos de negocio (biometria, lgpd)
#: desacoplados um do outro dentro do MESMO processo `apps/api`, ja que
#: ownership de arquivo desta fase e mutuamente exclusivo (secao 3 do PCF).
_MODALIDADE_POR_FINALIDADE: dict[str, str] = {
    "biometria_facial": "facial",
    "biometria_digital": "digital",
}


@dataclass(frozen=True, slots=True)
class DadosConsentimentoCriar:
    colaborador_id: UUID
    finalidade: str
    versao_termo: str
    texto_termo_ref: str | None
    hash_termo: str | None
    canal: str | None
    ip: str | None
    evidencia_ref: str | None
    user_agent: str | None


async def _versao_vigente(sessao: AsyncSession, *, tenant_id: UUID, finalidade: str) -> str | None:
    consulta = (
        sa.select(Consentimento.versao_termo)
        .where(Consentimento.tenant_id == tenant_id, Consentimento.finalidade == finalidade)
        .order_by(Consentimento.criado_em.desc())
        .limit(1)
    )
    return (await sessao.execute(consulta)).scalars().first()


async def criar_consentimento(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dados: DadosConsentimentoCriar,
    usuario_id: UUID | None,
) -> Consentimento:
    colaborador = (
        await sessao.execute(
            sa.select(Colaborador).where(
                Colaborador.id == dados.colaborador_id,
                Colaborador.tenant_id == tenant_id,
                Colaborador.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if colaborador is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Colaborador nao encontrado.")

    if not dados.hash_termo:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="Campo 'hashTermo' e obrigatorio: e a prova do texto exato aceito (ADR-006).",
        )

    vigente = await _versao_vigente(sessao, tenant_id=tenant_id, finalidade=dados.finalidade)
    if vigente is not None and vigente != dados.versao_termo:
        raise ErroDeAplicacao(
            "PONTO-LGPD-004",
            detalhe=(
                f"Versao '{dados.versao_termo}' nao e a vigente para '{dados.finalidade}' "
                f"('{vigente}' e a versao corrente)."
            ),
        )

    agora = dt.datetime.now(tz=dt.UTC)
    consentimento = Consentimento(
        tenant_id=tenant_id,
        colaborador_id=dados.colaborador_id,
        finalidade=dados.finalidade,
        versao_termo=dados.versao_termo,
        texto_termo_ref=dados.texto_termo_ref
        or f"lgpd/termos/{dados.finalidade}/{dados.versao_termo}",
        hash_termo=dados.hash_termo,
        # O ato de chamar esta operacao E o aceite: status enviado pelo
        # cliente e ignorado por design, mesmo padrao que
        # `app.biometria.servico.criar_biometria` ja usa para `status`.
        status="concedido",
        concedido_em=agora,
        canal=dados.canal or "app",
        ip=dados.ip,
        user_agent=dados.user_agent,
        evidencia_ref=dados.evidencia_ref,
        criado_por=usuario_id,
    )
    sessao.add(consentimento)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return consentimento


async def _carregar_consentimento(
    sessao: AsyncSession, *, tenant_id: UUID, consentimento_id: UUID
) -> Consentimento:
    consulta = sa.select(Consentimento).where(
        Consentimento.id == consentimento_id, Consentimento.tenant_id == tenant_id
    )
    consentimento = (await sessao.execute(consulta)).scalar_one_or_none()
    if consentimento is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Consentimento nao encontrado.")
    return consentimento


async def expurgar_templates_biometricos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    finalidade: str,
    usuario_id: UUID | None,
) -> int:
    """Revogacao de consentimento biometrico dispara expurgo REAL do
    template (PCF secao 5, aceite de A3). Nao reescreve `app.biometria.cifra`
    (ADR-006 ja implementado, F2): so DELETA a linha cifrada de
    `biometria_templates` -- exatamente o dado que a cifra protege, sem
    precisar decifra-lo para apagar. Idempotente: chamar duas vezes so
    apaga o que ainda existir na segunda vez (zero linhas, sem erro).

    Devolve a quantidade de templates removidos.
    """
    modalidade = _MODALIDADE_POR_FINALIDADE.get(finalidade)
    if modalidade is None:
        return 0

    biometrias = (
        (
            await sessao.execute(
                sa.select(Biometria).where(
                    Biometria.tenant_id == tenant_id,
                    Biometria.colaborador_id == colaborador_id,
                    Biometria.modalidade == modalidade,
                    Biometria.status.in_(("pendente", "ativa")),
                )
            )
        )
        .scalars()
        .all()
    )
    if not biometrias:
        return 0

    agora = dt.datetime.now(tz=dt.UTC)
    total_templates = 0
    for biometria in biometrias:
        resultado = await sessao.execute(
            sa.delete(BiometriaTemplate)
            .where(
                BiometriaTemplate.tenant_id == tenant_id,
                BiometriaTemplate.biometria_id == biometria.id,
            )
            .returning(BiometriaTemplate.id)
        )
        total_templates += len(resultado.all())
        biometria.status = "revogada"
        biometria.revogada_em = agora
        biometria.motivo_revogacao = "Consentimento LGPD revogado pelo titular."
        biometria.atualizado_por = usuario_id

    sessao.add(
        AcessoDadoSensivel(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            colaborador_id=colaborador_id,
            categoria="biometria",
            entidade="biometria_templates",
            entidade_id=None,
            finalidade="expurgo_por_revogacao_consentimento",
            base_legal="consentimento",
            acao="eliminacao",
            quantidade_registros=total_templates,
            origem="api",
        )
    )
    await sessao.flush()
    return total_templates


async def revogar_consentimento(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    consentimento_id: UUID,
    usuario_id: UUID | None,
) -> Consentimento:
    consentimento = await _carregar_consentimento(
        sessao, tenant_id=tenant_id, consentimento_id=consentimento_id
    )
    if consentimento.status != "revogado":
        consentimento.status = "revogado"
        consentimento.revogado_em = dt.datetime.now(tz=dt.UTC)
        consentimento.atualizado_por = usuario_id
        await sessao.flush()

    # Sempre tenta o expurgo, mesmo em chamada repetida (idempotente por
    # construcao -- ver docstring de `expurgar_templates_biometricos`):
    # cobre tanto a primeira revogacao quanto uma reentrega da mesma
    # `Idempotency-Key` antes do retrofit generico de A2 (F13, backlog
    # 2026-08-03) cobrir esta rota.
    await expurgar_templates_biometricos(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=consentimento.colaborador_id,
        finalidade=consentimento.finalidade,
        usuario_id=usuario_id,
    )
    return consentimento


async def listar_consentimentos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID | None,
    finalidade: str | None,
    status: str | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> tuple[list[Consentimento], bool, str | None]:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_CONSENTIMENTO, padrao="concedidoEm"
    )
    mapa = {
        "concedidoEm": CampoOrdenacao(Consentimento.concedido_em, lambda v: v),
        "finalidade": CampoOrdenacao(Consentimento.finalidade, lambda v: v),
    }
    consulta = sa.select(Consentimento).where(Consentimento.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(Consentimento.colaborador_id == colaborador_id)
    if finalidade is not None:
        consulta = consulta.where(Consentimento.finalidade == finalidade)
    if status is not None:
        consulta = consulta.where(Consentimento.status == status)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=mapa[ordenacao.campo],
        coluna_id=Consentimento.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    proximo: str | None = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor = getattr(
            ultimo, "concedido_em" if ordenacao.campo == "concedidoEm" else "finalidade"
        )
        proximo = codificar_cursor(ordenacao, valor, ultimo.id)
    return list(linhas), tem_mais, proximo


def calcular_hash_termo(texto: str) -> str:
    """Utilitario opcional para quem ja tem o texto em maos (ex.: teste,
    ferramenta interna) e quer computar o hash no mesmo algoritmo do
    contrato (`^[0-9a-f]{64}$`, SHA-256)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
