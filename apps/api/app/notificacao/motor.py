"""Motor de notificações: mapeia um envelope de evento para linhas de
`notificacoes`, uma por (destinatário, canal aplicável) -- T10, A3.

Chamado em processo pelo próprio código de A1/A2/A4, logo após publicar um
envelope no barramento interno do domínio deles (mesmo padrão que
`app.apuracao.tratamento.eventos.publicar` já usa), e pela rotina de
varredura cross-tenant desta fase (`worker.notificacoes_verificacao`, T11)
para sinais que nascem em domínios já concluídos. Nunca "escuta" um
barramento genérico -- ele só existe a partir da F13 (PCF §2.7); os dois
caminhos de disparo estão documentados em `app/notificacao/__init__.py`.

`processar_evento` nunca levanta por "evento sem template" ou "sem
destinatário resolvível" -- essas são situações normais (por exemplo, um
envelope de domínio que este motor ainda não conhece), não erro de
aplicação. Só propaga exceção real (falha de banco, tipo inválido no
payload de um evento que ele SABE processar).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from ponto_contracts import Aprovacao, Notificacao, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log import obter_logger
from app.notificacao import mensagens, preferencias

logger = obter_logger("notificacao.motor")

#: Fuso civil de referência para a janela de silêncio -- mesmo padrão que
#: `worker.scheduler.verificar_banco_horas_vencendo` usa para "hoje": o
#: sistema tem America/Sao_Paulo como fuso de referência (ADR-004), nunca
#: UTC, para não desalinhar a comparação com o relógio de parede do usuário.
#: Simplificação documentada: não resolve o fuso PRÓPRIO do tenant/empresa
#: (`tenants.fuso_horario`) -- o mesmo grau de simplificação que a rotina
#: irmã de F4 já aceitou para a mesma finalidade (referência civil única).
FUSO_REFERENCIA = ZoneInfo("America/Sao_Paulo")

#: Canais que este motor sabe endereçar nesta fase. `whatsapp`/`sms` ficam
#: de fora de propósito (PCF §2.8: arquitetura pronta, sem provedor real
#: ainda -- a coluna `notificacoes.canal` aceita os dois, mas nenhuma regra
#: aqui os cria).
CANAIS_PADRAO: tuple[str, ...] = ("push", "email", "in_app")

#: `ocorrencia.aberta` é granular demais para push/email (uma marcação
#: ímpar isolada não deveria virar alarme fora do produto) -- fica só
#: `in_app`, decisão documentada aqui porque não há CRITÉRIO escrito em
#: `events.yaml` sobre canal por evento (isso é regra de notificação, não de
#: domínio).
_CANAIS_POR_EVENTO: dict[str, tuple[str, ...]] = {
    mensagens.NOME_OCORRENCIA_ABERTA: ("in_app",),
}

#: Entidade de origem e o campo do payload que carrega o id, usada para
#: preencher `notificacoes.entidade`/`entidade_id` -- é essa coluna que
#: `worker.notificacoes_verificacao` usa depois para não notificar duas
#: vezes o mesmo fato (`NOT EXISTS` por entidade+id, PCF §2.7).
_ENTIDADE_POR_EVENTO: dict[str, tuple[str, str]] = {
    mensagens.NOME_AJUSTE_SOLICITADO: ("solicitacoes", "solicitacaoId"),
    mensagens.NOME_AJUSTE_APROVADO: ("solicitacoes", "solicitacaoId"),
    mensagens.NOME_AJUSTE_REPROVADO: ("solicitacoes", "solicitacaoId"),
    mensagens.NOME_PERIODO_FECHADO: ("fechamentos", "fechamentoId"),
    mensagens.NOME_PERIODO_REABERTO: ("fechamentos", "fechamentoId"),
    mensagens.NOME_ESPELHO_ASSINADO: ("espelhos", "espelhoId"),
    mensagens.NOME_OCORRENCIA_ABERTA: ("ocorrencias", "ocorrenciaId"),
    mensagens.NOME_SOLICITACAO_PENDENTE: ("solicitacoes", "solicitacaoId"),
}


def _entidade_e_id(tipo: str, dados: dict[str, Any]) -> tuple[str | None, UUID | None]:
    par = _ENTIDADE_POR_EVENTO.get(tipo)
    if par is None:
        return None, None
    entidade, campo = par
    valor = dados.get(campo)
    if not valor:
        return None, None
    return entidade, UUID(str(valor))


async def _usuario_do_colaborador(
    sessao: AsyncSession, tenant_id: UUID, colaborador_id: UUID
) -> UUID | None:
    """`usuarios.colaborador_id` é o único elo entre pessoa e identidade de
    acesso (comentário da coluna em `schema.sql`) -- nem todo colaborador
    tem usuário (quem só bate marcação no terminal não precisa)."""
    linha = await sessao.execute(
        sa.select(Usuario.id).where(
            Usuario.tenant_id == tenant_id,
            Usuario.colaborador_id == colaborador_id,
            Usuario.excluido_em.is_(None),
        )
    )
    return linha.scalar_one_or_none()


async def _aprovadores_pendentes(
    sessao: AsyncSession, tenant_id: UUID, solicitacao_id: UUID
) -> list[UUID]:
    """Usuários com etapa `pendente` na cadeia da solicitação neste
    instante -- mesma leitura que `listarAprovacoesPendentes` (A1, T3) faz
    para montar a fila do aprovador. Delegação vigente é resolvida pelo
    próprio fluxo de aprovação (a linha de `aprovacoes` já nasce com o
    `aprovador_usuario_id` correto); aqui só lemos quem está com a
    pendência agora."""
    linhas = await sessao.execute(
        sa.select(Aprovacao.aprovador_usuario_id).where(
            Aprovacao.tenant_id == tenant_id,
            Aprovacao.solicitacao_id == solicitacao_id,
            Aprovacao.decisao == "pendente",
        )
    )
    return [uid for uid in linhas.scalars().all() if uid is not None]


async def _resolver_destinatarios(
    sessao: AsyncSession, tenant_id: UUID, tipo: str, dados: dict[str, Any]
) -> list[UUID]:
    """Um evento pode ter mais de um destinatário (mais de uma etapa
    `pendente` simultânea não acontece no desenho desta fase, mas a lista
    continua genérica). Devolve lista vazia quando o payload não permite
    resolver ninguém -- o motor nunca inventa destinatário; a linha
    simplesmente não é criada.
    """
    if tipo in (mensagens.NOME_AJUSTE_SOLICITADO, mensagens.NOME_SOLICITACAO_PENDENTE):
        # `ajuste.solicitado` nasce quando a etapa abre; `solicitacao.
        # pendente_prazo` (sintético, T11) é o lembrete de que ela segue
        # pendente com o prazo vencido -- os dois miram quem está com a
        # decisão em mãos agora, nunca o solicitante.
        solicitacao_id = dados.get("solicitacaoId")
        if not solicitacao_id:
            return []
        return await _aprovadores_pendentes(sessao, tenant_id, UUID(str(solicitacao_id)))

    if tipo == mensagens.NOME_PERIODO_FECHADO:
        usuario_id = dados.get("fechadoPor")
        return [UUID(str(usuario_id))] if usuario_id else []

    if tipo == mensagens.NOME_PERIODO_REABERTO:
        usuario_id = dados.get("reabertoPor")
        return [UUID(str(usuario_id))] if usuario_id else []

    # ajuste.aprovado / ajuste.reprovado / espelho.assinado /
    # ocorrencia.aberta: todos carregam colaboradorId no payload -- o
    # colaborador dono do fato é quem deve saber.
    colaborador_id = dados.get("colaboradorId")
    if not colaborador_id:
        return []
    usuario_id = await _usuario_do_colaborador(sessao, tenant_id, UUID(str(colaborador_id)))
    return [usuario_id] if usuario_id else []


def _canais_do_evento(tipo: str) -> tuple[str, ...]:
    return _CANAIS_POR_EVENTO.get(tipo, CANAIS_PADRAO)


async def processar_evento(sessao: AsyncSession, tenant_id: UUID, envelope: dict[str, Any]) -> int:
    """Cria uma linha de `Notificacao` por (destinatário, canal aplicável),
    respeitando preferência e janela de silêncio do usuário. Devolve a
    quantidade de linhas criadas -- `0` quando o evento não tem template,
    não tem destinatário resolvível, ou nenhum canal está habilitado; isso
    nunca é erro, só "nada a notificar aqui".

    Não comita: quem chama decide o limite da transação (mesmo padrão de
    `criar_tratamento`/`decidir_tratamento` de F4 -- o motor participa da
    MESMA transação da operação que disparou o evento).
    """
    tipo = envelope.get("tipo", "")
    dados = envelope.get("dados") or {}

    mensagem = mensagens.montar_mensagem(tipo, dados)
    if mensagem is None:
        logger.info("evento sem template de notificacao, ignorado", extra={"tipo": tipo})
        return 0

    destinatarios = await _resolver_destinatarios(sessao, tenant_id, tipo, dados)
    if not destinatarios:
        logger.info(
            "evento sem destinatario resolvivel, nenhuma notificacao criada",
            extra={"tipo": tipo},
        )
        return 0

    entidade, entidade_id = _entidade_e_id(tipo, dados)
    canais = _canais_do_evento(tipo)
    agora = dt.datetime.now(tz=FUSO_REFERENCIA)
    criadas = 0

    for usuario_id in destinatarios:
        for canal in canais:
            if not await preferencias.esta_habilitado(sessao, tenant_id, usuario_id, tipo, canal):
                continue

            inicio, fim = await preferencias.obter_janela_silencio(
                sessao, tenant_id, usuario_id, tipo, canal
            )
            agendada_para: dt.datetime | None = None
            # `inicio`/`fim` só podem ser `None` juntos (`obter_janela_
            # silencio` devolve os dois ou nenhum) -- o `is not None`
            # explícito nos dois, em vez de um `assert`, é o que deixa o
            # mypy estreitar `inicio` para `dt.time` dentro do bloco sem
            # levantar em produção (`python -O` descartaria um `assert`).
            if (
                inicio is not None
                and fim is not None
                and not preferencias.dentro_da_janela(agora.time(), inicio, fim)
            ):
                agendada_para = preferencias.proxima_janela(agora, inicio)

            sessao.add(
                Notificacao(
                    tenant_id=tenant_id,
                    usuario_id=usuario_id,
                    canal=canal,
                    evento=tipo,
                    titulo=mensagem.titulo,
                    corpo=mensagem.corpo,
                    payload=dados,
                    agendada_para=agendada_para,
                    entidade=entidade,
                    entidade_id=entidade_id,
                )
            )
            criadas += 1

    await sessao.flush()
    logger.info(
        "notificacoes criadas para evento",
        extra={"tipo": tipo, "quantidade": criadas, "tenantId": str(tenant_id)},
    )
    return criadas


__all__ = ["CANAIS_PADRAO", "FUSO_REFERENCIA", "processar_evento"]
