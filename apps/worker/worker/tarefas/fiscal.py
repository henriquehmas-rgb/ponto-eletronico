"""Geracao dos arquivos fiscais REP-P. Implementacao na F12.

Dois arquivos com escopos deliberadamente diferentes -- confundir os dois e o
erro que invalida o sistema numa fiscalizacao:

**AFD** (Arquivo Fonte de Dados)
    Deriva **exclusivamente** das marcacoes. Texto ASCII ISO 8859-1, campos
    separados por `|`, linhas terminadas em CR+LF, um NSR por registro comecando
    em 1 e sem lacuna, CRC-16 por registro e SHA-256 do arquivo. Registro tipo 7
    e a marcacao do REP-P. Nao enxerga tratamento, nao enxerga abono.

**AEJ** (Arquivo Eletronico de Jornada)
    Gerado pelo Programa de Tratamento. Enxerga horario contratual, tratamento,
    ausencia e banco de horas, alem das marcacoes. Substitui AFDT e ACJEF.

Assinatura CAdES (`.p7s` destacado, certificado ICP-Brasil) e tarefa da F12/A3 e
depende do e-CNPJ A1 da SEEG. Ate o certificado chegar, os arquivos sao gerados
validos porem nao assinados -- e o parametro `assinar` existe para isso.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from worker.log import obter_logger

logger = obter_logger("tarefas.fiscal")


async def gerar_afd(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    rep_p_id: str,
    inicio: dt.date | str,
    fim: dt.date | str,
    assinar: bool = True,
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Gera o AFD de um REP-P para um periodo e guarda o arquivo no MinIO.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        rep_p_id: REP-P cujo AFD sera extraido. O NSR e sequencial POR REP-P.
        inicio: primeiro dia do periodo, inclusive.
        fim: ultimo dia do periodo, inclusive.
        assinar: quando `False`, gera sem `.p7s` (certificado ICP ainda ausente).
        solicitante_id: usuario que pediu a geracao, para a trilha de auditoria.

    **Achado de contrato/scaffold documentado (ver
    `app.fiscal.afd.gerador`, docstring do modulo).** A assinatura desta
    tarefa e FIXADA pelo andaime da Fase 0 (PCF F12 secao 5: nao muda
    parametro/nome/tipo de retorno sem RFC) e nao carrega `nsrInicial`/
    `nsrFinal` nem `fracionar`/`tamanhoFracaoRegistros` (campos de
    `AfdCriar`) -- por isso `solicitar_geracao_afd` (router) recusa esses
    dois modos com `PONTO-VAL-001` antes de enfileirar, e esta tarefa so
    precisa lidar com o caminho `periodoInicio`/`periodoFim` sem
    fracionamento. Diferente de `gerar_aej` (abaixo): `gerar_afd_arquivo`
    e AUTOCONTIDA (nunca precisa re-localizar uma linha de controle
    pre-criada) porque o fracionamento pode produzir 1..N linhas de
    `afd_arquivos` por chamada, e uma unica linha pre-criada pelo router
    nao teria como representar essa relacao 1-para-N.
    """
    logger.info(
        "gerar_afd recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "repPId": rep_p_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "assinar": assinar,
        },
    )

    # Import tardio: `apps/worker` so instala `apps/api` como biblioteca na
    # imagem `runtime` (ADR-009) -- mesmo padrao/mesma nota de mypy que
    # `gerar_aej` (abaixo) ja documenta: so a PRIMEIRA ocorrencia textual de
    # cada modulo neste ARQUIVO carrega `# type: ignore[import-not-found]`.
    # `app.db.sessao`/`app.fiscal.aej.gerador` ja carregaram o supressor em
    # `gerar_aej`, que vem depois deste texto no arquivo mas e' definido
    # antes na ordem de leitura -- para manter a regra "primeira ocorrencia
    # TEXTUAL", os dois imports abaixo (`app.db.sessao`, um modulo ja citado
    # acima em `gerar_aej`) precisam do supressor aqui tambem, pois esta
    # funcao aparece ANTES de `gerar_aej` no arquivo.
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]
    from app.fiscal.afd.gerador import gerar_afd_arquivo  # type: ignore[import-not-found]

    tenant_uuid = UUID(tenant_id)
    rep_p_uuid = UUID(rep_p_id)
    solicitante_uuid = UUID(solicitante_id) if solicitante_id else None
    data_inicio = inicio if isinstance(inicio, dt.date) else dt.date.fromisoformat(str(inicio))
    data_fim = fim if isinstance(fim, dt.date) else dt.date.fromisoformat(str(fim))

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)
        arquivos = await gerar_afd_arquivo(
            sessao,
            tenant_uuid,
            rep_p_id=rep_p_uuid,
            inicio=data_inicio,
            fim=data_fim,
            assinar=assinar,
            solicitante_id=solicitante_uuid,
        )
        # `gerar_afd_arquivo` nao commita (mesmo padrao de `criar_rep_p`,
        # F12/A1) -- quem abriu a sessao commita, mesmo padrao ja usado por
        # `app.workflow.fechamento.tarefas.processar_fechamento` (F10).
        await sessao.commit()

    resultado = {
        "implementado": True,
        "tenantId": tenant_id,
        "repPId": rep_p_id,
        "inicio": str(inicio),
        "fim": str(fim),
        "assinar": assinar,
        "arquivoIds": [str(arquivo.id) for arquivo in arquivos],
        "totalArquivos": len(arquivos),
        "status": arquivos[0].status if arquivos else None,
    }
    logger.info("gerar_afd concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado


async def gerar_aej(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    empresa_id: str,
    inicio: dt.date | str,
    fim: dt.date | str,
    assinar: bool = True,
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Gera o AEJ de uma empresa para um periodo.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        empresa_id: empresa (CNPJ) do arquivo. O AEJ e por empregador.
        inicio: primeiro dia do periodo, inclusive.
        fim: ultimo dia do periodo, inclusive.
        assinar: quando `False`, gera sem `.p7s`.
        solicitante_id: usuario que pediu a geracao, para a trilha de auditoria.

    **Nota sobre `incluir_banco_horas` (achado documentado, ver
    `app.fiscal.aej.gerador`, docstring do modulo).** A assinatura desta
    tarefa e FIXADA pelo andaime da Fase 0 (PCF F12 secao 5: nao muda
    parametro/nome/tipo de retorno sem RFC) e nao carrega
    `incluirBancoHoras` (campo de `AejCriar`) nem `arquivo_id` (o id da
    linha de controle que `solicitar_geracao_aej` ja criou). Por isso esta
    tarefa sempre chama `gerar_aej_arquivo` com `incluir_banco_horas=True` e
    deixa a funcao RE-LOCALIZAR a linha `status='gerando'` pela chave
    `(tenant_id, empresa_id, periodo_inicio, periodo_fim)` -- seguro porque
    `PONTO-FISC-002` garante no maximo uma geracao em andamento por essa
    chave.
    """
    logger.info(
        "gerar_aej recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "empresaId": empresa_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "assinar": assinar,
        },
    )

    # Import tardio: `apps/worker` so instala `apps/api` como biblioteca na
    # imagem `runtime` (ADR-009), nunca como dependencia formal de
    # `apps/worker/pyproject.toml` -- mesmo padrao ja usado por
    # `worker/tarefas/apuracao.py::recalcular_periodo`/`apurar_dia`. So a
    # PRIMEIRA ocorrencia textual de um modulo neste ARQUIVO carrega
    # `# type: ignore[import-not-found]` (mypy do worker, rodado sem
    # `apps/api` instalado, so emite `import-not-found` uma vez por modulo
    # nao encontrado -- a segunda ocorrencia do MESMO modulo geraria
    # "unused-ignore" com `warn_unused_ignores`). `app.db.sessao` ja foi
    # importado com o supressor em `gerar_afd` (acima, primeira ocorrencia
    # textual do arquivo) -- aqui NAO leva `# type: ignore`, senao o proprio
    # mypy reclamaria de supressor nao usado.
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
    from app.fiscal.aej.gerador import gerar_aej_arquivo  # type: ignore[import-not-found]

    tenant_uuid = UUID(tenant_id)
    empresa_uuid = UUID(empresa_id)
    solicitante_uuid = UUID(solicitante_id) if solicitante_id else None
    data_inicio = inicio if isinstance(inicio, dt.date) else dt.date.fromisoformat(str(inicio))
    data_fim = fim if isinstance(fim, dt.date) else dt.date.fromisoformat(str(fim))

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)
        arquivo = await gerar_aej_arquivo(
            sessao,
            tenant_uuid,
            empresa_id=empresa_uuid,
            inicio=data_inicio,
            fim=data_fim,
            incluir_banco_horas=True,
            assinar=assinar,
            solicitante_id=solicitante_uuid,
        )

    resultado = {
        "implementado": True,
        "tenantId": tenant_id,
        "empresaId": empresa_id,
        "inicio": str(inicio),
        "fim": str(fim),
        "assinar": assinar,
        "arquivoId": str(arquivo.id),
        "status": arquivo.status,
        "totalVinculos": arquivo.total_vinculos,
        "totalMarcacoes": arquivo.total_marcacoes,
        "totalAusencias": arquivo.total_ausencias,
        "totalLancamentosBanco": arquivo.total_lancamentos_banco,
        "hashSha256": arquivo.hash_sha256,
    }
    logger.info("gerar_aej concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado
