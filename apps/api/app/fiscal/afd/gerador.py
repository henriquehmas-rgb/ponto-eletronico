"""Orquestrador do gerador de AFD (T6, F12/A1).

`gerar_afd_arquivo` é a função de domínio que faz o trabalho de verdade
(verificação de NSR, montagem de todos os registros, fracionamento, cálculo
de hash, gravação em objeto e em `afd_arquivos`, assinatura quando
aplicável, publicação do evento) — chamada tanto por
`apps/worker/worker/tarefas/fiscal.py::gerar_afd` (o caminho real de
produção, via fila) quanto diretamente pelos testes desta fase (T6/T13).
`solicitar_geracao_afd` é a parte SÍNCRONA que o router chama: valida o que
precisa ser síncrono e enfileira.

**Dois achados de contrato/scaffold documentados aqui, não resolvidos por
conta própria** (ver `docs/backlog.md`): a assinatura de
`apps/worker/worker/tarefas/fiscal.py::gerar_afd` já veio FIXADA pelo
scaffold da Fase 0 — `(ctx, *, tenant_id, rep_p_id, inicio, fim, assinar,
solicitante_id)` — e o PCF F12 proíbe mudar parâmetro, nome ou tipo de
retorno desta tarefa sem RFC (§4/§5). Essa assinatura não tem como carregar
nem `AfdCriar.nsrInicial`/`nsrFinal` ("como alternativa ao período") nem
`AfdCriar.fracionar`/`tamanhoFracaoRegistros` até o worker — os dois
recursos SÃO implementados e testados em `gerar_afd_arquivo` (chamada
diretamente), mas `solicitarGeracaoAfd`/o endpoint HTTP `gerarAfd` só
consegue exercitar, de ponta a ponta, o caminho por
`periodoInicio`/`periodoFim` sem fracionamento — os outros dois modos
respondem `PONTO-VAL-001` com a explicação, em vez de fingir um suporte que
não alcança o worker. Uma RFC que estenda a assinatura da tarefa (ou outro
mecanismo, ex.: persistir o pedido original e o worker relê por id) resolve
isto; não é algo para A1 decidir sozinho trocando a assinatura fixada.

**`ProcessamentoAssincrono.id` devolvido por `solicitar_geracao_afd` é um
identificador de acompanhamento EFÊMERO (`uuid4()`), não o `id` de uma
linha de `afd_arquivos`.** Decisão documentada, não um acidente: como o
AFD pode ser fracionado em N linhas por um único pedido (§2.11 do PCF), e a
tarefa do worker (acima) não tem como devolver ao chamador síncrono qual(is)
`afd_arquivos.id` serão criados antes de o worker rodar, não há UM único
identificador de linha que representasse "o resultado" de forma estável —
diferente do padrão que `criarFechamento` (F10) usa (`ProcessamentoAssincrono
.id = fechamento.id`, uma correspondência 1-para-1 que aqui não existe). O
cliente descobre o(s) arquivo(s) gerado(s) consultando `GET /v1/fiscal/afd`
filtrado por `repPId`/período (`listarAfd`, A3) depois que o status deixa
de ser `gerando`/`processando` — não por reconsultar este `id` específico.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Final
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import AfdArquivo, ArquivoAssinatura, Marcacao, RepP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import salvar_objeto
from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.fiscal.afd import registros
from app.fiscal.afd.eventos import publicar_afd_gerado
from app.fiscal.afd.tipo7 import RegistroTipo7, montar_registros_tipo7
from app.fiscal.comum.formatos import montar_arquivo_texto
from app.schemas import contrato as esquemas

NOME_TAREFA_GERAR_AFD: Final[str] = "gerar_afd"

#: Fuso fixo -03:00 (Brasil, sem horário de verão desde 2019) usado só para
#: converter as datas `periodoInicio`/`periodoFim` (tipo `date`, sem fuso)
#: em fronteiras de `datahora_marcacao` (`TIMESTAMPTZ`) — mesma convenção já
#: usada por `packages/contracts/schema.sql::fn_cria_particao_marcacoes`
#: para as partições mensais de `marcacoes`.
_FUSO_PADRAO: Final[dt.timezone] = dt.timezone(dt.timedelta(hours=-3))


async def _obter_rep_p_do_tenant(sessao: AsyncSession, tenant_id: UUID, rep_p_id: UUID) -> RepP:
    rep_p = await sessao.get(RepP, rep_p_id)
    if rep_p is None or rep_p.tenant_id != tenant_id or rep_p.excluido_em is not None:
        raise ErroDeAplicacao("PONTO-REC-001", contexto_log={"repPId": str(rep_p_id)})
    return rep_p


async def _recusar_se_geracao_em_andamento(
    sessao: AsyncSession, tenant_id: UUID, rep_p_id: UUID, inicio: dt.date, fim: dt.date
) -> None:
    """`PONTO-FISC-002` quando já existe uma linha `status='gerando'` para o
    mesmo REP-P e período. Em operação normal `gerar_afd_arquivo` só grava
    linhas já em seu estado final (`gerado`/`assinado`) — uma linha presa em
    `gerando` só existe se um processo do worker morreu no meio de uma
    geração anterior (achado defensivo, não um estado alcançável pelo fluxo
    feliz); é exatamente por isso que este teste só é exercitável inserindo
    essa linha diretamente via SQL num teste, nunca em produção."""
    resultado = await sessao.execute(
        select(AfdArquivo.id)
        .where(
            AfdArquivo.tenant_id == tenant_id,
            AfdArquivo.rep_p_id == rep_p_id,
            AfdArquivo.periodo_inicio == inicio,
            AfdArquivo.periodo_fim == fim,
            AfdArquivo.status == "gerando",
        )
        .limit(1)
    )
    if resultado.first() is not None:
        raise ErroDeAplicacao(
            "PONTO-FISC-002", contexto_log={"repPId": str(rep_p_id), "inicio": inicio.isoformat()}
        )


async def _consultar_marcacoes_do_periodo(
    sessao: AsyncSession, tenant_id: UUID, rep_p_id: UUID, inicio: dt.date, fim: dt.date
) -> list[Marcacao]:
    """Marcações tipo "7" do REP-P cujo FATO (`datahora_marcacao`, "o
    horário que aparece no AFD", comentário da coluna em `schema.sql`)
    ocorreu no intervalo `[inicio, fim]`, ordenadas por NSR (§2.8: o AFD
    ordena por NSR, não por data/hora — exceção deliberada de ADR-003).
    `canal='importacao'` é excluído explicitamente (§2.8: defesa em
    profundidade, mesmo que hoje não existam linhas com esse canal)."""
    inicio_ts = dt.datetime.combine(inicio, dt.time.min, tzinfo=_FUSO_PADRAO)
    fim_ts_exclusivo = dt.datetime.combine(
        fim + dt.timedelta(days=1), dt.time.min, tzinfo=_FUSO_PADRAO
    )
    resultado = await sessao.execute(
        select(Marcacao)
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.rep_p_id == rep_p_id,
            Marcacao.tipo_registro == "7",
            Marcacao.canal != "importacao",
            Marcacao.datahora_marcacao >= inicio_ts,
            Marcacao.datahora_marcacao < fim_ts_exclusivo,
        )
        .order_by(Marcacao.nsr.asc())
    )
    return list(resultado.scalars().all())


def _nome_arquivo(
    rep_p: RepP,
    *,
    inicio: dt.date,
    fim: dt.date,
    fracao_numero: int | None,
    fracao_total: int | None,
) -> str:
    """§2.10 do PCF: reconcilia a regra 10 do Anexo V (INPI + CNPJ + "REP_P",
    sem separador exato definido) com o exemplo de `events.yaml`
    (`AFD_<cnpj>_<periodoInicio>_<periodoFim>.txt`, sem INPI):
    `AFD_<numeroInpi>_<cnpjEmpregador>_REP_P_<periodoInicio>_<periodoFim>.txt`,
    com `_PARTE<N>DE<TOTAL>` antes da extensão quando fracionado."""
    base = f"AFD_{rep_p.numero_inpi}_{rep_p.cnpj_empregador}_REP_P_" f"{inicio:%Y%m%d}_{fim:%Y%m%d}"
    if fracao_numero is not None and fracao_total is not None:
        base += f"_PARTE{fracao_numero}DE{fracao_total}"
    return base + ".txt"


def _fracionar(
    registros_tipo7: list[RegistroTipo7], *, fracionar: bool, tamanho_fracao: int | None
) -> list[list[RegistroTipo7]]:
    """§2.11 do PCF: o critério de corte já é dado pelo contrato
    (`tamanhoFracaoRegistros`, registros por fração) — cada fração é um AFD
    completo e válido por si só (cabeçalho e trailer próprios, T6)."""
    if not fracionar or not tamanho_fracao:
        return [registros_tipo7]
    if tamanho_fracao < 1:
        raise ValueError("tamanho_fracao_registros deve ser >= 1.")
    return [
        registros_tipo7[indice : indice + tamanho_fracao]
        for indice in range(0, len(registros_tipo7), tamanho_fracao)
    ]


async def _tentar_assinar(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    arquivo: AfdArquivo,
    conteudo: bytes,
    solicitante_id: UUID | None,
) -> bool:
    """Assina o AFD recém-gerado em CAdES quando há certificado configurado
    e válido (§2.4 do PCF). Sem certificado (estado real de hoje, SEEG ainda
    não tem o e-CNPJ A1) ou com certificado EXPIRADO, devolve `False` sem
    levantar erro — a geração em si NUNCA falha por falta/expiração de
    certificado (`PONTO-FISC-004`/`PONTO-FISC-005` só são respondidos por
    `assinarArquivoFiscal`, quando o usuário pede explicitamente para
    assinar e não há como; aqui a assinatura é só "se der", best-effort).

    Import local (não no topo do módulo) por isolamento entre agentes desta
    mesma fase: `app.fiscal.assinatura.*` é ownership exclusivo de A3
    (T11) — importar só dentro da função em vez de no topo evita acoplar a
    ORDEM de import deste módulo ao estado daquele em desenvolvimento
    paralelo, mesmo padrão cauteloso que `apps/worker/worker/tarefas/
    fechamento.py` já usa para módulos de outro agente/fase."""
    from app.fiscal.assinatura.cades import assinar_cades
    from app.fiscal.assinatura.certificado import obter_certificado_configurado

    certificado = obter_certificado_configurado()
    if certificado is None or certificado.expirado:
        return False

    assinatura_bytes = assinar_cades(conteudo, certificado)
    chave_assinatura = f"{arquivo.conteudo_ref}.p7s"
    await salvar_objeto(
        chave_assinatura, assinatura_bytes, content_type="application/pkcs7-signature"
    )

    hash_arquivo = hashlib.sha256(conteudo).hexdigest()
    assinatura = ArquivoAssinatura(
        tenant_id=tenant_id,
        tipo_arquivo="afd",
        arquivo_id=arquivo.id,
        padrao="CAdES",
        formato="detached",
        assinatura_ref=chave_assinatura,
        certificado_titular=certificado.titular,
        certificado_serial=certificado.serial,
        certificado_emissor=certificado.emissor,
        certificado_validade_inicio=certificado.validade_inicio,
        certificado_validade_fim=certificado.validade_fim,
        hash_arquivo=hash_arquivo,
        algoritmo_hash="SHA-256",
        status="assinado",
        criado_por=solicitante_id,
    )
    arquivo.status = "assinado"
    sessao.add(assinatura)
    await sessao.flush()
    return True


async def _gravar_fracao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    rep_p: RepP,
    inicio: dt.date,
    fim: dt.date,
    registros_fracao: list[RegistroTipo7],
    fracao_numero: int | None,
    fracao_total: int | None,
    gerado_em: dt.datetime,
    assinar: bool,
    solicitante_id: UUID | None,
) -> AfdArquivo:
    """Monta cabeçalho (tipo "1") + registros tipo "7" da fração + trailer
    (tipo "9") + linha de assinatura, nessa ordem — grava o objeto, a linha
    de `afd_arquivos` (`status='gerado'`) e, se aplicável, a assinatura."""
    cabecalho = registros.montar_registro_tipo1(
        tipo_identificador_empregador="1",
        cnpj_ou_cpf_empregador=rep_p.cnpj_empregador,
        cno_ou_caepf=rep_p.cei_caepf,
        razao_social_empregador=rep_p.razao_social_empregador,
        numero_inpi=rep_p.numero_inpi,
        periodo_inicio=inicio,
        periodo_fim=fim,
        gerado_em=gerado_em,
        tipo_identificador_fabricante="1",
        cnpj_ou_cpf_fabricante=rep_p.cnpj_desenvolvedor,
    )
    trailer = registros.montar_trailer_tipo9(qtd_tipo7=len(registros_fracao))
    linha_assinatura = registros.montar_linha_assinatura()

    linhas_tipo7 = [registro.linha for registro in registros_fracao]
    linhas = [cabecalho, *linhas_tipo7, trailer, linha_assinatura]
    try:
        conteudo = montar_arquivo_texto(linhas)
    except ValueError as exc:
        raise ErroDeAplicacao(
            "PONTO-FISC-006", detalhe=str(exc), contexto_log={"repPId": str(rep_p.id)}
        ) from exc

    nsr_inicial = registros_fracao[0].nsr
    nsr_final = registros_fracao[-1].nsr
    # Cabecalho + trailer + linha de assinatura + N registros tipo 7
    # (confirmado contra o exemplo do evento `afd.gerado` em
    # `packages/contracts/events.yaml`: nsrInicial=1, nsrFinal=8421 (8421
    # marcacoes), totalRegistros=8424 = 8421 + 3).
    total_registros = len(registros_fracao) + 3

    nome_arquivo = _nome_arquivo(
        rep_p, inicio=inicio, fim=fim, fracao_numero=fracao_numero, fracao_total=fracao_total
    )
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    chave = f"fiscal/afd/{tenant_id}/{rep_p.id}/{nome_arquivo}"
    conteudo_ref = await salvar_objeto(
        chave, conteudo, content_type="text/plain; charset=iso-8859-1"
    )

    arquivo = AfdArquivo(
        tenant_id=tenant_id,
        empresa_id=rep_p.empresa_id,
        rep_p_id=rep_p.id,
        periodo_inicio=inicio,
        periodo_fim=fim,
        nsr_inicial=nsr_inicial,
        nsr_final=nsr_final,
        total_registros=total_registros,
        nome_arquivo=nome_arquivo,
        conteudo_ref=conteudo_ref,
        tamanho_bytes=len(conteudo),
        hash_sha256=hash_sha256,
        fracionado=fracao_numero is not None,
        fracao_numero=fracao_numero,
        fracao_total=fracao_total,
        status="gerado",
        solicitado_por=solicitante_id,
        gerado_em=dt.datetime.now(tz=dt.UTC),
        criado_por=solicitante_id,
    )
    sessao.add(arquivo)
    await sessao.flush()

    assinado = False
    if assinar:
        assinado = await _tentar_assinar(
            sessao,
            tenant_id=tenant_id,
            arquivo=arquivo,
            conteudo=conteudo,
            solicitante_id=solicitante_id,
        )

    publicar_afd_gerado(
        tenant_id=tenant_id,
        arquivo_id=arquivo.id,
        empresa_id=rep_p.empresa_id,
        rep_p_id=rep_p.id,
        nome_arquivo=nome_arquivo,
        periodo_inicio=inicio,
        periodo_fim=fim,
        nsr_inicial=nsr_inicial,
        nsr_final=nsr_final,
        total_registros=total_registros,
        hash_sha256=hash_sha256,
        tamanho_bytes=len(conteudo),
        assinado=assinado,
        fracionado=fracao_numero is not None,
    )
    return arquivo


async def gerar_afd_arquivo(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    rep_p_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    assinar: bool = True,
    solicitante_id: UUID | None = None,
    fracionar: bool = False,
    tamanho_fracao_registros: int | None = None,
) -> list[AfdArquivo]:
    """Gera o(s) AFD(s) do REP-P para o período `[inicio, fim]`. Devolve UMA
    linha de `afd_arquivos` por fração (uma única, sem fracionamento).

    `fracionar`/`tamanho_fracao_registros` são suportados por esta função
    (T6 os testa diretamente) mas hoje NÃO alcançam o worker de ponta a
    ponta pelo endpoint HTTP `gerarAfd` — ver a nota grande no topo do
    módulo sobre a assinatura fixada de `worker/tarefas/fiscal.py::gerar_afd`.

    Ordem de validação (a mais barata primeiro, para nunca gastar trabalho
    de consulta/geração numa requisição que já falharia por um motivo
    simples): REP-P existe no tenant -> `numeroInpi` preenchido -> período
    válido -> nenhuma geração em andamento -> existem marcações no período
    -> continuidade de NSR íntegra (dentro de `montar_registros_tipo7`, que
    é quem levanta `PONTO-FISC-001` — nenhuma linha de `afd_arquivos` é
    criada antes disso).

    Não commita: quem abre a sessão decide quando commitar (mesmo padrão
    que `app.fiscal.rep_p.servico.criar_rep_p` já documenta) — o worker
    (`apps/worker/worker/tarefas/fiscal.py::gerar_afd`) commita logo após
    chamar esta função, dentro do MESMO `async with fabrica() as sessao:`
    que a abriu (mesmo padrão que `app.workflow.fechamento.tarefas.
    processar_fechamento`, F10, já usa). Testes que chamam esta função
    diretamente com uma sessão de fixture reaproveitada por várias operações
    devem chamar `aplicar_tenant_teste` de novo depois, se for consultar
    algo além do que esta função devolve — commitar reseta o `SET LOCAL
    app.tenant_id` da sessão (ver docstring de `tests/f12/conftest.py`).
    """
    rep_p = await _obter_rep_p_do_tenant(sessao, tenant_id, rep_p_id)

    if not rep_p.numero_inpi:
        raise ErroDeAplicacao("PONTO-FISC-003", contexto_log={"repPId": str(rep_p_id)})

    if fim < inicio:
        raise ErroDeAplicacao(
            "PONTO-VAL-007", detalhe="periodoFim deve ser maior ou igual a periodoInicio."
        )

    await _recusar_se_geracao_em_andamento(sessao, tenant_id, rep_p_id, inicio, fim)

    marcacoes = await _consultar_marcacoes_do_periodo(sessao, tenant_id, rep_p_id, inicio, fim)
    if not marcacoes:
        raise ErroDeAplicacao(
            "PONTO-FISC-006",
            detalhe=(
                "Nenhuma marcacao tipo 7 encontrada para o REP-P e periodo informados. "
                "O leiaute do AFD nao define um arquivo REP-P vazio e nsrInicial/"
                "nsrFinal sao NOT NULL em afd_arquivos -- escolha um periodo com "
                "marcacoes (decisao documentada, docs/fases/F12-conformidade-rep-p.md)."
            ),
            contexto_log={
                "repPId": str(rep_p_id),
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
            },
        )

    registros_tipo7 = await montar_registros_tipo7(
        sessao, tenant_id=tenant_id, rep_p_id=rep_p_id, marcacoes=marcacoes
    )

    fracoes = _fracionar(
        registros_tipo7, fracionar=fracionar, tamanho_fracao=tamanho_fracao_registros
    )
    total_fracoes = len(fracoes)
    gerado_em = dt.datetime.now(tz=dt.UTC)

    arquivos: list[AfdArquivo] = []
    for indice, fracao in enumerate(fracoes, start=1):
        arquivo = await _gravar_fracao(
            sessao,
            tenant_id=tenant_id,
            rep_p=rep_p,
            inicio=inicio,
            fim=fim,
            registros_fracao=fracao,
            fracao_numero=indice if total_fracoes > 1 else None,
            fracao_total=total_fracoes if total_fracoes > 1 else None,
            gerado_em=gerado_em,
            assinar=assinar,
            solicitante_id=solicitante_id,
        )
        arquivos.append(arquivo)

    return arquivos


async def _enfileirar_gerar_afd(
    *,
    tenant_id: UUID,
    rep_p_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    assinar: bool,
    solicitante_id: UUID | None,
    redis_url: str,
) -> None:
    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_GERAR_AFD,
            tenant_id=str(tenant_id),
            rep_p_id=str(rep_p_id),
            inicio=inicio.isoformat(),
            fim=fim.isoformat(),
            assinar=assinar,
            solicitante_id=str(solicitante_id) if solicitante_id else None,
        )
    finally:
        await pool.aclose()


async def solicitar_geracao_afd(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.AfdCriar,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.ProcessamentoAssincrono:
    """Parte SÍNCRONA de `gerarAfd` (handler HTTP, T6): valida o que precisa
    ser síncrono (REP-P existe e tem `numeroInpi`, período coerente, nenhuma
    geração em andamento) e enfileira `gerar_afd` (worker). NÃO roda a
    verificação de continuidade de NSR nem monta nenhum registro aqui —
    isso é trabalho pesado, fica inteiramente em `gerar_afd_arquivo`,
    dentro do worker.
    """
    if dados.rep_p_id is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="repPId e obrigatorio.")

    usa_nsr = dados.nsr_inicial is not None or dados.nsr_final is not None
    usa_periodo = dados.periodo_inicio is not None or dados.periodo_fim is not None
    if usa_nsr and usa_periodo:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="Informe periodoInicio/periodoFim OU nsrInicial/nsrFinal, nao os dois.",
        )
    if usa_nsr:
        # Achado de contrato/scaffold documentado (ver docstring do topo do
        # modulo): a assinatura fixada de worker/tarefas/fiscal.py::
        # gerar_afd nao tem parametro de faixa de NSR.
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=(
                "Geracao de AFD por nsrInicial/nsrFinal ainda nao alcanca o worker "
                "de ponta a ponta no scaffold atual de gerar_afd(ctx, tenant_id, "
                "rep_p_id, inicio, fim, assinar, solicitante_id) -- use "
                "periodoInicio/periodoFim. Ver docs/backlog.md."
            ),
        )
    if dados.periodo_inicio is None or dados.periodo_fim is None:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="periodoInicio e periodoFim sao obrigatorios."
        )
    if dados.periodo_fim < dados.periodo_inicio:
        raise ErroDeAplicacao(
            "PONTO-VAL-007", detalhe="periodoFim deve ser maior ou igual a periodoInicio."
        )
    if dados.fracionar:
        # Idem: fracionar/tamanhoFracaoRegistros nao alcancam o worker hoje.
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=(
                "Fracionamento de AFD (fracionar=true) ainda nao alcanca o worker "
                "de ponta a ponta no scaffold atual da tarefa gerar_afd -- "
                "app.fiscal.afd.gerador.gerar_afd_arquivo ja implementa e testa "
                "fracionamento quando chamado diretamente. Ver docs/backlog.md."
            ),
        )

    rep_p = await _obter_rep_p_do_tenant(sessao, tenant_id, dados.rep_p_id)
    if not rep_p.numero_inpi:
        raise ErroDeAplicacao("PONTO-FISC-003", contexto_log={"repPId": str(rep_p.id)})

    await _recusar_se_geracao_em_andamento(
        sessao, tenant_id, rep_p.id, dados.periodo_inicio, dados.periodo_fim
    )

    assinar = dados.assinar if dados.assinar is not None else True
    await _enfileirar_gerar_afd(
        tenant_id=tenant_id,
        rep_p_id=rep_p.id,
        inicio=dados.periodo_inicio,
        fim=dados.periodo_fim,
        assinar=assinar,
        solicitante_id=usuario_id,
        redis_url=redis_url,
    )

    # `id` efemero, nao uma linha de afd_arquivos -- ver docstring do topo
    # do modulo.
    return esquemas.ProcessamentoAssincrono.model_validate(
        {"id": uuid4(), "tipo": "afd", "status": "enfileirado"}
    )
