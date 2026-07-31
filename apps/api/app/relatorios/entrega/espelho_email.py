"""Entrega do espelho de ponto oficial por e-mail (F11, T13, A4).

**Diferente de `app.relatorios.entrega.email` (A3):** aquele módulo entrega
um RELATÓRIO EXPORTADO qualquer (arquivo genérico CSV/XLSX/PDF de um
`RelatorioExecucao`); este entrega **o espelho oficial já assinado de um
vínculo/período específico** (`Espelho`/`AssinaturaEspelho`, F10) -- domínio
diferente, tipos diferentes (`RelatorioExecucao`/`RelatorioAgendamento` não
descrevem "o espelho mais recente assinado de um vínculo", que é uma
pergunta sobre `espelhos`, não sobre execução de relatório). A fronteira do
PCF F11 §5 ("A4 importa uma função utilitária exposta por A3 se a lógica de
baixo nível de envio SMTP for idêntica") não se aplica na prática: o `email.
py` de A3 não expõe nenhuma função de baixo nível separada do `entregar(
execucao, agendamento)` monolítico (tipado especificamente para os dois
tipos do catálogo de relatórios) -- não há nada reaproveitável sem acoplar
este módulo a tipos que não fazem sentido para "enviar um espelho". Módulo
próprio, MESMA disciplina de adaptador provisório que A3 já usa (ver abaixo)
-- decisão de julgamento registrada aqui e no relatório de fechamento da
fase, não uma divergência escondida.

**Mesmo tratamento que `app.relatorios.entrega.email` (A3) e `app.
notificacao.canais.email` (F10) já deram ao mesmo problema estrutural: sem
credencial de SMTP configurada em lugar nenhum do repositório** (confirmado
em `infra/.env.example`: nenhuma variável `SMTP_*`/`EMAIL_*`). O adaptador
REAL desta função é "log estruturado + devolve `True`", nunca uma chamada
SMTP/HTTP inventada para um provedor sem credencial (PCF, proibição 10).
`# TODO F11+N: trocar por SMTP real quando houver credencial -- só o corpo
muda, a assinatura continua a mesma`.

**Onde isto é chamado:** a tarefa assíncrona do worker (T6,
`apps/worker/worker/tarefas/relatorios.py`, ownership conjunto de A1+A3,
ainda não concluída no momento em que este módulo foi escrito) é quem
decide, ao processar um `relatorio_agendamentos` com `relatorio_definicao_
id` apontando para o dataset `espelho_oficial` (`codigo="espelho-oficial"`)
e `canal='email'`, chamar esta função em vez do `entrega/email.py` genérico
de A3. Este módulo não se auto-invoca a partir de nenhum agendamento --
expõe só a função pura, pronta para T6 ligar quando A1/A3 concluírem aquela
tarefa compartilhada.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import AssinaturaEspelho, Espelho

from app.core.log import obter_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = obter_logger("relatorios.entrega.espelho_email")

#: Mesmo papel que `app.relatorios.entrega.email.PROVEDOR` cumpre para o
#: canal genérico (A3) -- constante própria, módulo não compartilhado (ver
#: docstring do módulo).
PROVEDOR: Final[str] = "smtp"

#: Só espelhos realmente oficiais são elegíveis para este envio -- mesmo
#: conjunto-base que `app.relatorios.datasets.espelho_oficial` usa (T12), a
#: mesma razão: um `previo` nunca é "o espelho oficial assinado".
_TIPOS_OFICIAIS = ("oficial", "retificado")


async def _espelho_assinado_mais_recente(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, periodo_id: UUID
) -> Espelho | None:
    """A versão mais alta, entre `oficial`/`retificado`, que tenha pelo
    menos uma `AssinaturaEspelho.status='assinado'` -- "o espelho oficial já
    assinado" do vínculo/período. `None` quando ainda não existe nenhum
    (nada para enviar, não é erro)."""
    consulta = (
        sa.select(Espelho)
        .where(
            Espelho.tenant_id == tenant_id,
            Espelho.vinculo_id == vinculo_id,
            Espelho.periodo_id == periodo_id,
            Espelho.tipo.in_(_TIPOS_OFICIAIS),
            sa.exists(
                sa.select(1).where(
                    AssinaturaEspelho.tenant_id == tenant_id,
                    AssinaturaEspelho.espelho_id == Espelho.id,
                    AssinaturaEspelho.status == "assinado",
                )
            ),
        )
        .order_by(Espelho.versao.desc())
        .limit(1)
    )
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def entregar_espelho_por_email(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    vinculo_id: UUID,
    periodo_id: UUID,
    destinatarios: Sequence[str],
) -> bool:
    """ "Envia" por e-mail o espelho oficial/retificado mais recente e já
    ASSINADO do vínculo/período aos `destinatarios`. Só lê `espelhos`/
    `assinaturas_espelho` (F10) -- nunca gera nem assina nada (mesma
    proibição 3 do PCF que o dataset de T12 já respeita).

    Devolve `False` sem levantar (nunca erro) quando: não há destinatário
    configurado; ou não existe (ainda) nenhum espelho oficial assinado para
    o escopo pedido -- "nada para enviar" é estado normal, não falha (mesmo
    padrão de honestidade que o resto do PCF já estabelece para escopo sem
    dado, §2.3).
    """
    if not destinatarios:
        logger.warning(
            "entrega de espelho por e-mail sem destinatarios",
            extra={"vinculoId": str(vinculo_id), "periodoId": str(periodo_id)},
        )
        return False

    espelho = await _espelho_assinado_mais_recente(sessao, tenant_id, vinculo_id, periodo_id)
    if espelho is None:
        logger.info(
            "nenhum espelho oficial assinado encontrado para o escopo pedido",
            extra={"vinculoId": str(vinculo_id), "periodoId": str(periodo_id)},
        )
        return False

    logger.info(
        "e-mail do espelho oficial (adaptador provisorio) enviado",
        extra={
            "espelhoId": str(espelho.id),
            "vinculoId": str(vinculo_id),
            "periodoId": str(periodo_id),
            "versao": espelho.versao,
            "tipo": espelho.tipo,
            "destinatarios": list(destinatarios),
            "conteudoRef": espelho.conteudo_ref,
            "provedor": PROVEDOR,
        },
    )
    return True


__all__ = ["PROVEDOR", "entregar_espelho_por_email"]
