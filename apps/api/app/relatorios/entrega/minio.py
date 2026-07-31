"""Canal de entrega `minio` de `relatorio_agendamentos` (F11, T11/A3).

No-op documentado: quando `formato != 'json'`, o arquivo do relatório JÁ está
gravado no bucket MinIO ao final de `executar_relatorio`
(`RelatorioExecucao.conteudo_ref`, gravado pela parte de A3 de T6) --
"entregar" pelo canal `minio` não move nem copia nada, só CONFIRMA que o
artefato existe onde o cliente já sabe procurá-lo (mesmo bucket, mesma
convenção de chave que os outros formatos). Existe como canal nomeado
porque `relatorio_agendamentos.canal` (`schema.sql` §16) fixa os três
valores `email`/`webhook`/`minio` e um agendamento com `canal='minio'`
precisa de alguma função `entregar` para chamar -- mesmo padrão de "canal
trivial documentado" que o resto do sistema usa quando a ação real já
aconteceu em outro lugar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.log import obter_logger

if TYPE_CHECKING:
    from ponto_contracts import RelatorioAgendamento, RelatorioExecucao

logger = obter_logger("relatorios.entrega.minio")


async def entregar(execucao: RelatorioExecucao, agendamento: RelatorioAgendamento) -> bool:
    """Confirma que o artefato de `execucao` está no armazenamento de
    objetos. Devolve `False` (sem levantar) quando `conteudo_ref` está
    vazio -- sinal de que a execução falhou antes de gravar o arquivo, e não
    há nada para "entregar" por este canal."""
    if not execucao.conteudo_ref:
        logger.warning(
            "execucao de relatorio sem conteudo_ref para o canal minio",
            extra={"execucaoId": str(execucao.id), "agendamentoId": str(agendamento.id)},
        )
        return False
    logger.info(
        "artefato de relatorio confirmado no armazenamento de objetos",
        extra={
            "execucaoId": str(execucao.id),
            "agendamentoId": str(agendamento.id),
            "conteudoRef": execucao.conteudo_ref,
        },
    )
    return True


__all__ = ["entregar"]
