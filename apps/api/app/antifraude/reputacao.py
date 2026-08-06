"""Reputacao de dispositivo por historico (PCF F14 sec 5, A1).

`app.biometria.dispositivos` (F2) so cadastra e expoe `dispositivos`; a
propria docstring daquele modulo diz "avaliar os sinais antifraude
(attestation_status, root_detectado, ...) e da F14 -- aqui so cadastramos e
expomos". Este modulo e essa avaliacao: combina o ESTADO conhecido do
aparelho (colunas de `dispositivos`, atualizadas por quem gerencia o
dispositivo) com o HISTORICO de marcacoes recentes originadas por ele
(`marcacoes.dispositivo_id` + `marcacoes_meta.classificacao_confianca`) num
unico numero de 0 (nada confiavel) a 100 (totalmente confiavel).

`dispositivo_id` ausente (canal `terminal`/`totem`/`api`, ou `web` sem
cadastro de dispositivo pessoal) devolve `None` -- "nao aplicavel", nunca um
valor inventado (ADR-014): o motor de composicao (`app.antifraude.motor`)
remove a fatia de "reputacao" da categoria "dispositivo" quando o sinal e
`None`, em vez de fingir neutralidade.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Dispositivo, Marcacao, MarcacaoMeta
from sqlalchemy.ext.asyncio import AsyncSession

#: Quantas marcacoes recentes do MESMO dispositivo entram no calculo de
#: historico. Numero pequeno de proposito: dispositivo novo (sem historico)
#: nao pode ser punido por falta de dado -- ver `_pontuacao_historico`.
JANELA_HISTORICO_MARCACOES = 20

#: Pontuacao de base por `attestation_status` do dispositivo (0-100, maior =
#: mais confiavel). `indisponivel`/`nao_verificado` fica num meio-termo
#: deliberadamente alto (nao um bloqueio disfarcado): ADR-008 e explicito que
#: puxar demais este sinal pune o parque de celulares real do trabalhador
#: brasileiro por um motivo que nao e fraude. `reprovado` so chega aqui
#: quando a politica NAO exige attestation (do contrario o sinal decisivo em
#: `app.antifraude.motor` ja recusou antes de este modulo ser consultado).
_PONTUACAO_ATTESTATION: dict[str, float] = {
    "aprovado": 100.0,
    "nao_verificado": 70.0,
    "indisponivel": 70.0,
    "reprovado": 30.0,
}

#: Penalidade (subtraida da base) por sinal negativo persistido na propria
#: linha de `dispositivos`. Cada um so entra aqui quando a politica permite
#: (nao bloqueia) o sinal -- caso contrario `app.antifraude.motor` ja
#: recusou antes deste modulo ser chamado.
_PENALIDADE_ROOT = 30.0
_PENALIDADE_DEPURACAO_USB = 15.0
_PENALIDADE_STATUS_RISCO: dict[str, float] = {
    "bloqueado": 80.0,
    "revogado": 80.0,
    "substituido": 40.0,
}

#: Classificacoes de `marcacoes_meta.classificacao_confianca` que contam
#: como "marcacao suspeita" no historico do aparelho.
_CLASSIFICACOES_SUSPEITAS = ("baixa", "bloqueada")

#: Penalidade por marcacao suspeita recente do MESMO dispositivo, aplicada
#: por ocorrencia dentro da janela (`JANELA_HISTORICO_MARCACOES`).
_PENALIDADE_POR_OCORRENCIA_SUSPEITA = 8.0


async def avaliar_reputacao_dispositivo(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID | None
) -> float | None:
    """Pontuacao de reputacao (0-100) do dispositivo, ou `None` quando nao ha
    `dispositivo_id` (canal sem aparelho cadastrado -- nao aplicavel)."""
    if dispositivo_id is None:
        return None

    dispositivo = (
        await sessao.execute(
            sa.select(Dispositivo).where(
                Dispositivo.tenant_id == tenant_id, Dispositivo.id == dispositivo_id
            )
        )
    ).scalar_one_or_none()
    if dispositivo is None:
        # Dispositivo referenciado mas nao encontrado (nunca deveria
        # acontecer com FK valida) -- trata como sinal ausente, nunca inventa.
        return None

    pontuacao = _PONTUACAO_ATTESTATION.get(dispositivo.attestation_status, 70.0)
    if dispositivo.root_detectado:
        pontuacao -= _PENALIDADE_ROOT
    if dispositivo.depuracao_usb:
        pontuacao -= _PENALIDADE_DEPURACAO_USB
    if dispositivo.status in _PENALIDADE_STATUS_RISCO:
        pontuacao -= _PENALIDADE_STATUS_RISCO[dispositivo.status]

    pontuacao -= await _penalidade_historico(
        sessao, tenant_id=tenant_id, dispositivo_id=dispositivo_id
    )

    return max(0.0, min(100.0, pontuacao))


async def _penalidade_historico(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo_id: UUID
) -> float:
    """Conta marcacoes suspeitas do MESMO dispositivo nas ultimas
    `JANELA_HISTORICO_MARCACOES` marcacoes que ele originou."""
    subconsulta = (
        sa.select(Marcacao.id, Marcacao.datahora_marcacao)
        .where(Marcacao.tenant_id == tenant_id, Marcacao.dispositivo_id == dispositivo_id)
        .order_by(Marcacao.datahora_marcacao.desc())
        .limit(JANELA_HISTORICO_MARCACOES)
        .subquery()
    )
    consulta = (
        sa.select(sa.func.count())
        .select_from(
            sa.join(
                subconsulta,
                MarcacaoMeta,
                sa.and_(
                    MarcacaoMeta.marcacao_id == subconsulta.c.id,
                    MarcacaoMeta.tenant_id == tenant_id,
                ),
            )
        )
        .where(MarcacaoMeta.classificacao_confianca.in_(_CLASSIFICACOES_SUSPEITAS))
    )
    ocorrencias = (await sessao.execute(consulta)).scalar_one()
    return float(ocorrencias) * _PENALIDADE_POR_OCORRENCIA_SUSPEITA
