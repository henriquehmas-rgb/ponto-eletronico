"""Canal de entrega `webhook` de `relatorio_agendamentos` (F11, T11/A3).

Um `POST` HTTP simples com a URL de download e metadados do arquivo gerado
-- **não** a assinatura HMAC/retentativa/DLQ completa da tag `webhooks`
(F13, fora de escopo desta fase, PCF §1/proibição 9). `agendamento.
destinatarios` guarda a(s) URL(s) de destino quando `canal='webhook'` (mesma
coluna que guarda endereços de e-mail quando `canal='email'` --
`relatorio_agendamentos.destinatarios`, `schema.sql` §16).

Usa `httpx` (já dependência da API desde o andaime da Fase 0; o worker
ganhou a mesma biblioteca nesta fase, `apps/worker/pyproject.toml`, bloco
`# --- F11 ---`, porque é o worker que executa `executar_relatorio` e chama
este módulo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from app.core.log import obter_logger

if TYPE_CHECKING:
    from ponto_contracts import RelatorioAgendamento, RelatorioExecucao

logger = obter_logger("relatorios.entrega.webhook")

#: Prazo de espera pela resposta do endpoint do cliente -- entrega best-effort,
#: nunca deve travar o worker esperando um endpoint lento/fora do ar
#: (sem retentativa nesta fase, ver docstring do módulo).
TIMEOUT_S = 10.0


def _payload(execucao: RelatorioExecucao, agendamento: RelatorioAgendamento) -> dict[str, Any]:
    return {
        "execucaoId": str(execucao.id),
        "agendamentoId": str(agendamento.id),
        "relatorioDefinicaoId": str(execucao.relatorio_definicao_id),
        "formato": execucao.formato,
        "status": execucao.status,
        "totalLinhas": execucao.total_linhas,
        "tamanhoBytes": execucao.tamanho_bytes,
        "hashSha256": execucao.hash_sha256,
        "conteudoRef": execucao.conteudo_ref,
        "concluidoEm": execucao.concluido_em.isoformat() if execucao.concluido_em else None,
    }


async def entregar(execucao: RelatorioExecucao, agendamento: RelatorioAgendamento) -> bool:
    """`POST` do payload de conclusão a cada URL em `agendamento.
    destinatarios`. Devolve `True` só se TODAS as URLs responderam `2xx`
    (uma entrega parcial ainda é reportada como falha -- quem consome o
    relatório espera o webhook completo, não uma fração dele)."""
    if not agendamento.destinatarios:
        logger.warning(
            "agendamento de relatorio sem destinatarios para o canal webhook",
            extra={"agendamentoId": str(agendamento.id), "execucaoId": str(execucao.id)},
        )
        return False

    payload = _payload(execucao, agendamento)
    sucesso = True
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
        for url in agendamento.destinatarios:
            try:
                resposta = await cliente.post(url, json=payload)
                resposta.raise_for_status()
            except httpx.HTTPError as exc:
                sucesso = False
                logger.warning(
                    "falha ao entregar webhook de relatorio",
                    extra={
                        "execucaoId": str(execucao.id),
                        "agendamentoId": str(agendamento.id),
                        "url": url,
                        "erro": str(exc),
                    },
                )
                continue
            logger.info(
                "webhook de relatorio entregue",
                extra={
                    "execucaoId": str(execucao.id),
                    "agendamentoId": str(agendamento.id),
                    "url": url,
                    "status": resposta.status_code,
                },
            )
    return sucesso


__all__ = ["TIMEOUT_S", "entregar"]
