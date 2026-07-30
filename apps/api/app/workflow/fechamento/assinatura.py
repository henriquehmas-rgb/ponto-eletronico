"""Assinatura eletrônica do espelho de ponto e sua verificação (T8, F10/A2).

**Não confunda com a assinatura CAdES/ICP-Brasil do REP-P (F12).** Esta é a
assinatura de ACEITE do colaborador -- prova de que ele tomou ciência da
jornada apurada (PCF §2.4). O mecanismo já está fixado no schema
(`assinaturas_espelho.metodo DEFAULT 'aceite_eletronico'`); **esta fase
implementa apenas `aceite_eletronico`** -- os demais métodos do enum ficam
aceitos pelo `CHECK` mas sem implementação (mesmo padrão de "contrato mais
amplo que a implementação atual" que F4 já viu em `banco_horas`).

**Fórmula de verificabilidade e não repúdio (§2.4, fixada pelo PCF, não é
decisão em aberto):**

1. O servidor recusa o aceite se `AssinaturaEspelhoRequisicao.hashSha256`
   não bater byte a byte com `espelhos.hash_sha256` gravado --
   `PONTO-CONF-002` ("Versão desatualizada... alterado depois da leitura
   que originou esta escrita"), o código exato que `assinarEspelho` declara
   em `x-erros` (não `PONTO-CONF-003`, que é para transição de estado
   inválida -- este caso é mais precisamente "o que você viu não é mais o
   que existe").
2. `hash_assinado` grava exatamente esse hash -- redundante com
   `espelhos.hash_sha256` de propósito (a linha de assinatura fica
   autocontida e verificável mesmo se o espelho fosse hipoteticamente
   reemitido).
3. `carimbo_tempo` é o relógio do servidor; `ip`/`user_agent` vêm da
   requisição HTTP.
4. Imutabilidade real: `assinaturas_espelho` já tem os gatilhos
   `trg_assinaturas_espelho_bloqueia_update/_delete` -- este módulo nunca
   executa `UPDATE`/`DELETE` nessa tabela.
5. `espelhos` NÃO tem gatilho de imutabilidade -- a disciplina é de
   aplicação: uma vez que existe **qualquer**
   `assinaturas_espelho.status='assinado'` para um `espelho_id`, este
   módulo nunca executa `UPDATE` na linha de `espelhos` correspondente
   (retificação sempre cria `Espelho` novo, `espelho.py`).
6. **Verificação = recomputação, não um endpoint novo**
   (`verificar_assinatura`, abaixo): recalcula `SHA256(json_canônico(
   espelho.conteudo))` com a MESMA canonicalização de `_json_canonico` e
   confere contra `espelho.hash_sha256` **e** `assinatura.hash_assinado`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from ponto_contracts import AssinaturaEspelho, Espelho
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.auditoria.hash_chain import gravar_auditoria
from app.schemas import contrato as esquemas
from app.workflow.fechamento.erros_bd import traduzir_integridade
from app.workflow.fechamento.espelho import _hash_conteudo, obter_espelho
from app.workflow.fechamento.eventos import publicar_espelho_assinado

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_HASH_DESATUALIZADO = "PONTO-CONF-002"

#: Único método implementado nesta fase (§2.4 do PCF).
METODO_IMPLEMENTADO = "aceite_eletronico"
#: `signatarioTipo` padrão quando o cliente não informa -- o caso principal
#: do critério de aceite ("aceite do colaborador").
SIGNATARIO_PADRAO = "colaborador"


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def assinar_espelho(
    sessao: AsyncSession,
    tenant_id: UUID,
    espelho_id: UUID,
    dados: esquemas.AssinaturaEspelhoRequisicao,
    *,
    usuario_id: UUID | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AssinaturaEspelho:
    if not dados.hash_sha256:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="hashSha256 e obrigatorio.")

    espelho = await obter_espelho(sessao, tenant_id, espelho_id)
    if dados.hash_sha256 != espelho.hash_sha256:
        raise ErroDeAplicacao(
            CODIGO_HASH_DESATUALIZADO,
            detalhe=(
                "O hash informado nao corresponde ao hash atual do espelho: o conteudo "
                "mudou entre a exibicao e o clique. Recarregue o espelho e assine de novo."
            ),
        )

    metodo = _valor(dados.metodo) or METODO_IMPLEMENTADO
    if metodo != METODO_IMPLEMENTADO:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                f"Metodo de assinatura '{metodo}' ainda nao implementado nesta fase; "
                f"use '{METODO_IMPLEMENTADO}'."
            ),
        )

    signatario_tipo = _valor(dados.signatario_tipo) or SIGNATARIO_PADRAO
    aceite = True if dados.aceite is None else bool(dados.aceite)
    recusa_motivo = (dados.recusa_motivo or "").strip() or None
    if not aceite and not recusa_motivo:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="recusaMotivo e obrigatorio quando aceite e falso."
        )

    agora = dt.datetime.now(tz=dt.UTC)
    signatario_colaborador_id = espelho.colaborador_id if signatario_tipo == "colaborador" else None
    assinatura = AssinaturaEspelho(
        tenant_id=tenant_id,
        espelho_id=espelho.id,
        signatario_tipo=signatario_tipo,
        signatario_usuario_id=usuario_id,
        signatario_colaborador_id=signatario_colaborador_id,
        metodo=metodo,
        hash_assinado=dados.hash_sha256,
        carimbo_tempo=agora,
        ip=ip,
        user_agent=user_agent,
        status="assinado" if aceite else "recusado",
        recusa_motivo=recusa_motivo,
        criado_por=usuario_id,
    )
    sessao.add(assinatura)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="espelho.assinado" if aceite else "espelho.assinatura_recusada",
        entidade="espelhos",
        acao="assinar",
        entidade_id=espelho.id,
        usuario_id=usuario_id,
        valor_anterior=None,
        valor_novo={
            "assinaturaId": str(assinatura.id),
            "status": assinatura.status,
            "signatarioTipo": signatario_tipo,
            "metodo": metodo,
        },
        metadados={"recusaMotivo": recusa_motivo} if recusa_motivo else None,
    )

    if aceite:
        envelope = publicar_espelho_assinado(
            tenant_id=tenant_id,
            espelho_id=espelho.id,
            colaborador_id=espelho.colaborador_id,
            vinculo_id=espelho.vinculo_id,
            periodo_id=espelho.periodo_id,
            signatario_tipo=signatario_tipo,
            metodo=metodo,
            carimbo_tempo=agora,
            hash_assinado=assinatura.hash_assinado,
            assinatura_id=assinatura.id,
            versao_espelho=espelho.versao,
        )
        # Achado de integracao consertado ao fechar a fase (T15/T16) --
        # mesma nota de `app/workflow/solicitacoes/servico.py::
        # criar_solicitacao`. Import tardio: `app.notificacao` e ownership
        # de A3.
        from app.notificacao.motor import processar_evento

        await processar_evento(sessao, tenant_id, envelope)
    return assinatura


async def verificar_assinatura(sessao: AsyncSession, tenant_id: UUID, assinatura_id: UUID) -> bool:
    """ "Verificação = recomputação" (§2.4 item 6): recalcula
    `SHA256(json_canônico(espelho.conteudo))` e confere contra
    `espelho.hash_sha256` **e** `assinatura.hash_assinado`. Não é um
    endpoint HTTP novo -- função pronta para auditoria interna, o próprio
    colaborador ou um perito reproduzirem o cálculo."""
    assinatura = await sessao.get(AssinaturaEspelho, assinatura_id)
    if assinatura is None or assinatura.tenant_id != tenant_id:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Assinatura nao encontrada.")
    espelho = await sessao.get(Espelho, assinatura.espelho_id)
    if espelho is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Espelho nao encontrado.")

    recomputado = _hash_conteudo(espelho.conteudo)
    return recomputado == espelho.hash_sha256 == assinatura.hash_assinado
