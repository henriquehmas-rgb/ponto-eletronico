"""Regra de negocio de `biometria` (T9 do PCF da F2).

Ciclo de vida: `pendente -> ativa -> revogada|expirada` (ou `reprovada`),
homologado por `validarBiometria` (aprovacao do RH). O vetor em si nunca sai
por aqui: as funcoes que o tocam (`cifra.py`) so entram e saem de
`biometria_templates`, cifradas.

Consentimento (ADR-006 regra 7 e `docs/fases/F02-*.md`): biometria facial e
digital exigem `consentimentos` vigente para a finalidade correspondente; sem
isso, `PONTO-LGPD-001`. A tabela e a API de `consentimentos` sao da F14 -- este
modulo so LE a linha referenciada, nunca escreve nela.
"""

from __future__ import annotations

import datetime as dt
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

from app.biometria import cifra
from app.biometria.comum import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    normalizar_limite,
    traduzir_integridade,
)
from app.core.erros import ErroDeAplicacao

__all__ = [
    "CAMPOS_ORDENACAO_BIOMETRIA",
    "DadosBiometriaCriar",
    "criar_biometria",
    "ler_template_decifrado",
    "listar_biometrias",
    "obter_biometria",
    "revogar_biometria",
    "validar_biometria",
    "versao_modelo_ativa",
]

#: Finalidade de `consentimentos` exigida por modalidade. So facial e digital
#: sao vetor biometrico de verdade (ADR-006); cartao, pin e qrcode sao
#: fallback e nao exigem este consentimento especifico.
_FINALIDADE_POR_MODALIDADE: dict[str, str] = {
    "facial": "biometria_facial",
    "digital": "biometria_digital",
}

CAMPOS_ORDENACAO_BIOMETRIA = frozenset({"cadastradaEm", "status"})


@dataclass(frozen=True, slots=True)
class DadosBiometriaCriar:
    """Entrada normalizada de `criarBiometria`.

    `vetor` e `versao_modelo` nao estao no schema tipado `BiometriaCriar` do
    contrato (a propria `ExemploBiometriaCriar` do openapi.yaml usa
    `versaoModelo`, que tampouco esta la -- ver `docs/backlog.md`); o roteador
    os le do corpo bruto da requisicao, porque nenhum `additionalProperties:
    false` os proibe.
    """

    colaborador_id: UUID
    modalidade: str
    origem_cadastro: str
    consentimento_id: UUID | None
    qualidade: float | None
    identificador_cartao: str | None
    vetor: bytes | None
    versao_modelo: str | None
    provedor: str
    dimensao: int | None


async def _registrar_acesso(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    colaborador_id: UUID | None,
    entidade_id: UUID | None,
    acao: str,
    finalidade: str,
    base_legal: str = "obrigacao_legal",
    origem: str = "api",
) -> None:
    """Uma linha por acesso a dado sensivel (ADR-006 regra 6).

    `flush()` explicito: a sessao da aplicacao roda com `autoflush=False`
    (`app/db/sessao.py`), entao sem isto a linha fica pendente na
    `Session.new` e invisivel a qualquer `SELECT` -- inclusive o commit no
    fim da requisicao a tornaria durável, mas um teste (ou uma leitura
    subsequente na MESMA transacao) que consulte `acessos_dados_sensiveis`
    antes do commit veria zero linhas.
    """
    sessao.add(
        AcessoDadoSensivel(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            colaborador_id=colaborador_id,
            categoria="biometria",
            entidade="biometrias",
            entidade_id=entidade_id,
            finalidade=finalidade,
            base_legal=base_legal,
            acao=acao,
            origem=origem,
        )
    )
    await sessao.flush()


async def _consentimento_vigente(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    consentimento_id: UUID,
    finalidade: str,
) -> bool:
    consulta = sa.select(Consentimento).where(
        Consentimento.id == consentimento_id,
        Consentimento.tenant_id == tenant_id,
        Consentimento.colaborador_id == colaborador_id,
        Consentimento.finalidade == finalidade,
        Consentimento.status == "concedido",
    )
    consentimento = (await sessao.execute(consulta)).scalar_one_or_none()
    if consentimento is None:
        return False
    if consentimento.expira_em is not None:
        agora = dt.datetime.now(tz=dt.UTC)
        expira = consentimento.expira_em
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=dt.UTC)
        if expira <= agora:
            return False
    return True


async def criar_biometria(
    sessao: AsyncSession, *, tenant_id: UUID, dados: DadosBiometriaCriar, usuario_id: UUID | None
) -> Biometria:
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

    finalidade_exigida = _FINALIDADE_POR_MODALIDADE.get(dados.modalidade)
    consentimento_ok = finalidade_exigida is None or (
        dados.consentimento_id is not None
        and await _consentimento_vigente(
            sessao,
            tenant_id=tenant_id,
            colaborador_id=dados.colaborador_id,
            consentimento_id=dados.consentimento_id,
            finalidade=finalidade_exigida,
        )
    )
    if not consentimento_ok:
        raise ErroDeAplicacao(
            "PONTO-LGPD-001",
            detalhe="Consentimento biometrico ausente, revogado ou expirado.",
        )

    # O cadastro nasce sempre pendente: so `validarBiometria` (aprovacao do
    # RH) o move para `ativa`. Ignorar `status` enviado pelo cliente e
    # deliberado -- ver descricao da operacao no contrato.
    biometria = Biometria(
        tenant_id=tenant_id,
        colaborador_id=dados.colaborador_id,
        modalidade=dados.modalidade,
        status="pendente",
        origem_cadastro=dados.origem_cadastro,
        qualidade=dados.qualidade,
        consentimento_id=dados.consentimento_id,
        identificador_cartao=dados.identificador_cartao,
        cadastrada_em=dt.datetime.now(tz=dt.UTC),
        cadastrada_por=usuario_id,
        criado_por=usuario_id,
    )
    sessao.add(biometria)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc

    if dados.vetor is not None:
        resultado = cifra.cifrar_vetor(
            tenant_id=tenant_id, colaborador_id=dados.colaborador_id, vetor=dados.vetor
        )
        template = BiometriaTemplate(
            tenant_id=tenant_id,
            biometria_id=biometria.id,
            versao_modelo=dados.versao_modelo or "desconhecida",
            provedor=dados.provedor,
            dimensao=dados.dimensao,
            template_cifrado=resultado.template_cifrado,
            iv=resultado.iv,
            tag_autenticacao=resultado.tag_autenticacao,
            algoritmo_cifra=resultado.algoritmo_cifra,
            chave_id=resultado.chave_id,
            criado_por=usuario_id,
        )
        sessao.add(template)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc) from exc

    return biometria


async def _carregar_biometria(
    sessao: AsyncSession, *, tenant_id: UUID, biometria_id: UUID
) -> Biometria:
    consulta = sa.select(Biometria).where(
        Biometria.id == biometria_id, Biometria.tenant_id == tenant_id
    )
    biometria = (await sessao.execute(consulta)).scalar_one_or_none()
    if biometria is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Credencial biometrica nao encontrada.")
    return biometria


async def versao_modelo_ativa(
    sessao: AsyncSession, *, tenant_id: UUID, biometria_id: UUID
) -> str | None:
    """`Biometria.versaoModelo` (contrato) e denormalizado do template ATIVO
    mais recente -- a tabela `biometrias` nao guarda essa coluna, so
    `biometria_templates` (ver `packages/contracts/schema.sql` secao 6)."""
    consulta = (
        sa.select(BiometriaTemplate.versao_modelo)
        .where(
            BiometriaTemplate.tenant_id == tenant_id,
            BiometriaTemplate.biometria_id == biometria_id,
            BiometriaTemplate.ativo.is_(True),
        )
        .order_by(BiometriaTemplate.gerado_em.desc())
    )
    return (await sessao.execute(consulta)).scalars().first()


async def obter_biometria(
    sessao: AsyncSession, *, tenant_id: UUID, biometria_id: UUID, usuario_id: UUID | None
) -> Biometria:
    biometria = await _carregar_biometria(sessao, tenant_id=tenant_id, biometria_id=biometria_id)
    await _registrar_acesso(
        sessao,
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        colaborador_id=biometria.colaborador_id,
        entidade_id=biometria.id,
        acao="leitura",
        finalidade="gestao_credencial_biometrica",
        base_legal="execucao_contrato",
    )
    return biometria


async def listar_biometrias(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID | None,
    modalidade: str | None,
    status: str | None,
    versao_modelo: str | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> tuple[list[Biometria], bool, str | None]:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_BIOMETRIA, padrao="cadastradaEm"
    )
    mapa = {
        "cadastradaEm": CampoOrdenacao(Biometria.cadastrada_em, lambda v: v),
        "status": CampoOrdenacao(Biometria.status, lambda v: v),
    }
    consulta = sa.select(Biometria).where(Biometria.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(Biometria.colaborador_id == colaborador_id)
    if modalidade is not None:
        consulta = consulta.where(Biometria.modalidade == modalidade)
    if status is not None:
        consulta = consulta.where(Biometria.status == status)
    if versao_modelo is not None:
        consulta = consulta.join(
            BiometriaTemplate, BiometriaTemplate.biometria_id == Biometria.id
        ).where(BiometriaTemplate.versao_modelo == versao_modelo)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=mapa[ordenacao.campo],
        coluna_id=Biometria.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    proximo: str | None = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor = getattr(ultimo, "cadastrada_em" if ordenacao.campo == "cadastradaEm" else "status")
        proximo = codificar_cursor(ordenacao, valor, ultimo.id)
    return list(linhas), tem_mais, proximo


async def revogar_biometria(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    biometria_id: UUID,
    usuario_id: UUID | None,
    motivo: str | None = None,
) -> None:
    biometria = await _carregar_biometria(sessao, tenant_id=tenant_id, biometria_id=biometria_id)
    biometria.status = "revogada"
    biometria.revogada_em = dt.datetime.now(tz=dt.UTC)
    biometria.motivo_revogacao = motivo
    biometria.atualizado_por = usuario_id
    # `flush()` explicito: sessao roda com `autoflush=False` -- sem isto uma
    # consulta de COLUNA (nao de entidade) na mesma transacao ainda veria
    # `status='ativa'` no banco.
    await sessao.flush()


async def validar_biometria(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    biometria_id: UUID,
    decisao: str,
    comentario: str | None,
    usuario_id: UUID | None,
) -> Biometria:
    """Homologacao do RH. `decisao` e `aprovar` ou `reprovar`."""
    biometria = await _carregar_biometria(sessao, tenant_id=tenant_id, biometria_id=biometria_id)
    if biometria.status != "pendente":
        raise ErroDeAplicacao(
            "PONTO-CONF-003",
            detalhe=f"Credencial em status '{biometria.status}' nao pode ser homologada.",
        )
    if decisao == "reprovar":
        if not comentario:
            raise ErroDeAplicacao(
                "PONTO-VAL-001", detalhe="Comentario e obrigatorio na reprovacao."
            )
        biometria.status = "reprovada"
        biometria.atualizado_por = usuario_id
        await sessao.flush()
        return biometria

    biometria.status = "ativa"
    biometria.validada_em = dt.datetime.now(tz=dt.UTC)
    biometria.validada_por = usuario_id
    biometria.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        # Segunda credencial ativa para o mesmo colaborador+modalidade
        # (uq_biometrias_ativa) -- ver criterio 6 da secao 7 do PCF.
        raise traduzir_integridade(exc) from exc
    return biometria


async def ler_template_decifrado(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    biometria_id: UUID,
    usuario_id: UUID | None,
    finalidade: str,
) -> bytes:
    """Decifra o template ativo mais recente. NUNCA exposta por rota da API
    (ADR-006 regra 5) -- existe para consumidores internos futuros (ex.:
    verificacao facial no `facial-svc`) e registra o acesso (regra 6)."""
    biometria = await _carregar_biometria(sessao, tenant_id=tenant_id, biometria_id=biometria_id)
    consulta_template = (
        sa.select(BiometriaTemplate)
        .where(
            BiometriaTemplate.tenant_id == tenant_id,
            BiometriaTemplate.biometria_id == biometria_id,
            BiometriaTemplate.ativo.is_(True),
        )
        .order_by(BiometriaTemplate.gerado_em.desc())
    )
    template = (await sessao.execute(consulta_template)).scalars().first()
    if template is None:
        raise ErroDeAplicacao(
            "PONTO-REC-001", detalhe="Nenhum template ativo para esta credencial."
        )
    await _registrar_acesso(
        sessao,
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        colaborador_id=biometria.colaborador_id,
        entidade_id=biometria.id,
        acao="leitura",
        finalidade=finalidade,
        base_legal="consentimento",
    )
    return cifra.decifrar_vetor(
        tenant_id=tenant_id,
        colaborador_id=biometria.colaborador_id,
        template_cifrado=template.template_cifrado,
        iv=template.iv,
        tag_autenticacao=template.tag_autenticacao or b"",
    )
