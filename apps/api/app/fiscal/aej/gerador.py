"""Orquestrador do gerador de AEJ (T9, F12/A2).

`solicitar_geracao_aej` e a metade SINCRONA (chamada pelo handler HTTP de
`gerarAej`, `app/routers/fiscal.py`): valida o que precisa ser validado antes
de responder, cria a linha de controle em `aej_arquivos` (`status='gerando'`)
e enfileira a tarefa pesada no worker -- mesmo padrao que
`app.workflow.fechamento.servico.criar_fechamento` (F10) ja usa para
`processar_fechamento`. `gerar_aej_arquivo` e a metade PESADA (chamada pelo
corpo de `apps/worker/worker/tarefas/fiscal.py::gerar_aej`): monta o arquivo
inteiro, reconcilia o bloco de banco de horas contra o extrato real de F4 e
grava o resultado.

**Nota sobre a assinatura da tarefa do worker (achado documentado, nao bug):**
`apps/worker/worker/tarefas/fiscal.py::gerar_aej` tem assinatura FIXADA pelo
andaime da Fase 0 (`tenant_id, empresa_id, inicio, fim, assinar,
solicitante_id`) e o PCF da fase proibe mudar parametro/nome/tipo de retorno
sem RFC (secao 5). Isso significa que a tarefa nao recebe nem `arquivo_id`
(o id da linha de controle criada por `solicitar_geracao_aej`) nem
`incluir_banco_horas` (campo de `AejCriar`). `gerar_aej_arquivo` contorna a
ausencia do primeiro RE-LOCALIZANDO a linha `status='gerando'` mais recente
para o mesmo `(tenant_id, empresa_id, periodo_inicio, periodo_fim)` -- seguro
porque `PONTO-FISC-002` ja garante no maximo uma geracao em andamento para
essa mesma chave. A ausencia do segundo significa que a tarefa do worker
SEMPRE chama esta funcao com `incluir_banco_horas=True` (nao ha como o
parametro do request chegar ate aqui pelo caminho assincrono) -- documentado
tambem no relatorio da fase como achado de contrato, nao decisao silenciosa.
`incluir_banco_horas` continua existindo como parametro real desta funcao
(para quem a chama diretamente, como os testes desta fase) porque e a
assinatura que o PCF (secao 6, T9) fixou.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import (
    AejArquivo,
    ApuracaoDia,
    BhConta,
    Colaborador,
    Empresa,
    Horario,
    Marcacao,
    Periodo,
    RepP,
    TipoTratamento,
    Tratamento,
    Unidade,
    Vinculo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.consulta import obter_extrato_banco_horas
from app.apuracao.dominio.pareamento import (
    MarcacaoParaPareamento,
    MarcacaoPareada,
    parear_marcacoes,
)
from app.comum.armazenamento import salvar_objeto
from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.fiscal.aej.eventos import publicar_aej_gerado
from app.fiscal.aej.registros import (
    AusenciaOuBancoHoras,
    Cabecalho,
    HorarioContratual,
    IdentificacaoPtrp,
    MarcacaoAej,
    MatriculaEsocial,
    RepUtilizado,
    TrailerAej,
    VinculoAej,
    montar_linha_assinatura,
    montar_registro_01,
    montar_registro_02,
    montar_registro_03,
    montar_registro_04,
    montar_registro_05,
    montar_registro_06,
    montar_registro_07,
    montar_registro_08,
    montar_registro_99,
)
from app.fiscal.comum.formatos import montar_arquivo_texto
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_GERACAO_EM_ANDAMENTO = "PONTO-FISC-002"
CODIGO_FALHA_GERACAO = "PONTO-FISC-006"

#: Nome de fila/tarefa: contrato com `apps/worker/worker/filas.py` (que ja
#: mapeia `"gerar_aej"` para `FILA_FISCAL`/F12, sem edicao necessaria) --
#: renomear um dos lados sem o outro faz o job cair num buraco.
NOME_TAREFA_GERAR_AEJ = "gerar_aej"

#: Identificacao do PTRP (Programa de Tratamento de Registro de Ponto): o
#: proprio SEEG Ponto, que gera tanto o AFD (REP-P) quanto o AEJ (PTRP) --
#: mesmo software, mesmo desenvolvedor. Nome oficial fixado (memoria do
#: projeto, identidade visual, 26/07/2026): "SEEG Ponto".
_NOME_PROGRAMA = "SEEG Ponto"
_VERSAO_PROGRAMA_PADRAO = "1.0.0"

#: Achado de contrato (ver relatorio da fase / `docs/backlog.md`): o leiaute
#: do AEJ exige um e-mail de contato do desenvolvedor do PTRP (tipo "08",
#: campo `emailDesenv`), mas NENHUMA tabela do schema desta fase guarda esse
#: dado (`rep_ps` nao tem coluna de e-mail do desenvolvedor; nenhuma outra
#: tabela lida por esta fase tem). Ate o contrato ganhar uma coluna real
#: (RFC), usa-se este placeholder, deliberadamente no dominio reservado
#: `.invalido` (RFC 2606) para nunca ser confundido com um endereco real --
#: NUNCA apresentado como dado real do desenvolvedor.
_EMAIL_DESENVOLVEDOR_PLACEHOLDER = "email-desenvolvedor-nao-configurado@exemplo.invalido"

#: `tipos_tratamento.categoria` que afetam o pareamento do dia (mesmos
#: nomes que `app.apuracao.dominio.servico` usa -- copia local deliberada:
#: aquele modulo e privado a F4, estas sao so as duas strings do `CHECK` do
#: schema, nao logica a duplicar).
_CATEGORIA_INCLUSAO_MARCACAO = "inclusao_marcacao"
_CATEGORIA_DESCONSIDERACAO_MARCACAO = "desconsideracao_marcacao"
_STATUS_TRATAMENTO_APLICAVEIS = ("aprovado", "aplicado")

#: `apuracoes_dia.tipo_dia` -> `tipoAusenOuComp` do tipo "07" (decisao de A2,
#: documentada aqui porque o leiaute nao da uma tabela de mapeamento -- ver
#: docstring de `_montar_bloco_ausencias`).
_TIPO_DIA_PARA_AUSENCIA: dict[str, str] = {
    "dsr": "1",
    "compensado": "4",
}


@dataclass(frozen=True, slots=True)
class _VinculoResolvido:
    vinculo: Vinculo
    colaborador: Colaborador
    idx: int


async def _fuso_do_vinculo(sessao: AsyncSession, vinculo: Vinculo, empresa: Empresa) -> str:
    """Mesma regra de `app.jornada.resolvedor.servico._fuso_efetivo` (F3):
    sem `unidade_id`, usa o fuso da empresa. Copia local deliberada (funcao
    privada de outra fase, duas linhas de logica, nao vale importar)."""
    if vinculo.unidade_id is not None:
        unidade = await sessao.get(Unidade, vinculo.unidade_id)
        if unidade is not None:
            return str(unidade.fuso_horario)
    return str(empresa.fuso_horario)


def _numero_inpi_para_nr_rep(numero_inpi: str) -> str:
    """`nrRep` (tipo "02") e o UNICO campo do AEJ com tamanho literal fixo
    ("17", nao uma faixa "X a Y" como todos os outros campos delimitados da
    secao 10) -- o mesmo tamanho do campo equivalente no AFD (posicao
    190-206, 17 caracteres). `rep_ps.numero_inpi` nao tem tamanho fixo no
    schema (so o padrao `^[0-9]+$`), entao alinha-se a direita com zero a
    esquerda ate 17 digitos, mesma convencao que o exemplo do proprio
    leiaute usa para o valor "ausente" do REP-A ("99999999999999999", 17
    noves)."""
    return numero_inpi.rjust(17, "0")[-17:]


async def _empresa_do_tenant(sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID) -> Empresa:
    empresa = await sessao.get(Empresa, empresa_id)
    if empresa is None or empresa.tenant_id != tenant_id or empresa.excluido_em is not None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Empresa nao encontrada.")
    return empresa


async def _resolver_periodo(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.AejCriar,
) -> tuple[dt.date, dt.date, UUID | None]:
    if dados.periodo_id is not None:
        periodo = await sessao.get(Periodo, dados.periodo_id)
        if periodo is None or periodo.tenant_id != tenant_id:
            raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Periodo nao encontrado.")
        return periodo.data_inicio, periodo.data_fim, periodo.id
    if dados.periodo_inicio is None or dados.periodo_fim is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Informe periodoId ou o par periodoInicio/periodoFim.",
        )
    if dados.periodo_fim < dados.periodo_inicio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="periodoFim deve ser >= periodoInicio."
        )
    return dados.periodo_inicio, dados.periodo_fim, None


async def _verificar_geracao_em_andamento(
    sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID, inicio: dt.date, fim: dt.date
) -> None:
    resultado = await sessao.execute(
        sa.select(AejArquivo.id).where(
            AejArquivo.tenant_id == tenant_id,
            AejArquivo.empresa_id == empresa_id,
            AejArquivo.periodo_inicio == inicio,
            AejArquivo.periodo_fim == fim,
            AejArquivo.status == "gerando",
        )
    )
    if resultado.first() is not None:
        raise ErroDeAplicacao(
            CODIGO_GERACAO_EM_ANDAMENTO,
            detalhe="Ja existe geracao de AEJ em andamento para esta empresa e periodo.",
        )


def _nome_arquivo(cnpj_empregador: str, inicio: dt.date, fim: dt.date) -> str:
    """Nome do AEJ: nenhuma regra de nome foi encontrada no leiaute oficial
    pela T0 (`docs/leiaute-afd-aej.md` secao 13, lacuna 5) -- segue
    literalmente o exemplo do contrato (`events.yaml`, `aej.gerado`), sem
    reconciliacao necessaria (PCF da fase, secao 2.10)."""
    return f"AEJ_{cnpj_empregador}_{inicio:%Y%m%d}_{fim:%Y%m%d}.txt"


async def solicitar_geracao_aej(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.AejCriar,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.ProcessamentoAssincrono:
    """Metade sincrona de `gerarAej` (T9): valida, cria a linha de controle
    `aej_arquivos(status='gerando')` e enfileira `gerar_aej` no worker.
    Devolve `ProcessamentoAssincrono` com o MESMO `id` que `obterAej`
    devolvera depois (`ProcessamentoAssincrono.description`: "consulte o
    mesmo identificador ate o status sair de enfileirado/processando")."""
    if dados.empresa_id is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="empresaId e obrigatorio.")

    empresa = await _empresa_do_tenant(sessao, tenant_id, dados.empresa_id)
    inicio, fim, periodo_id = await _resolver_periodo(sessao, tenant_id, dados)

    await _verificar_geracao_em_andamento(sessao, tenant_id, empresa.id, inicio, fim)

    arquivo = await _criar_linha_controle(
        sessao,
        tenant_id,
        empresa=empresa,
        periodo_id=periodo_id,
        inicio=inicio,
        fim=fim,
        solicitado_por=usuario_id,
    )
    await sessao.commit()

    await _enfileirar_gerar_aej(
        tenant_id=tenant_id,
        empresa_id=empresa.id,
        inicio=inicio,
        fim=fim,
        assinar=bool(dados.assinar),
        solicitante_id=usuario_id,
        redis_url=redis_url,
    )

    return esquemas.ProcessamentoAssincrono.model_validate(
        {"id": arquivo.id, "tipo": "aej", "status": "enfileirado"}
    )


async def _criar_linha_controle(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa: Empresa,
    periodo_id: UUID | None,
    inicio: dt.date,
    fim: dt.date,
    solicitado_por: UUID | None,
) -> AejArquivo:
    arquivo = AejArquivo(
        tenant_id=tenant_id,
        empresa_id=empresa.id,
        periodo_id=periodo_id,
        periodo_inicio=inicio,
        periodo_fim=fim,
        nome_arquivo=_nome_arquivo(empresa.cnpj, inicio, fim),
        ptrp_identificacao=_NOME_PROGRAMA,
        status="gerando",
        solicitado_por=solicitado_por,
    )
    sessao.add(arquivo)
    await sessao.flush()
    return arquivo


async def _enfileirar_gerar_aej(
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    assinar: bool,
    solicitante_id: UUID | None,
    redis_url: str,
) -> None:
    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_GERAR_AEJ,
            tenant_id=str(tenant_id),
            empresa_id=str(empresa_id),
            inicio=inicio.isoformat(),
            fim=fim.isoformat(),
            assinar=assinar,
            solicitante_id=str(solicitante_id) if solicitante_id else None,
        )
    finally:
        await pool.aclose()


async def _localizar_ou_criar_arquivo(
    sessao: AsyncSession, tenant_id: UUID, empresa: Empresa, inicio: dt.date, fim: dt.date
) -> AejArquivo:
    """Re-localiza a linha `status='gerando'` criada por
    `solicitar_geracao_aej` (a tarefa do worker nao recebe `arquivo_id`, ver
    docstring do modulo). Sem uma linha `gerando` (uso direto desta funcao,
    fora do fluxo HTTP -- por exemplo em teste), cria uma nova."""
    resultado = await sessao.execute(
        sa.select(AejArquivo)
        .where(
            AejArquivo.tenant_id == tenant_id,
            AejArquivo.empresa_id == empresa.id,
            AejArquivo.periodo_inicio == inicio,
            AejArquivo.periodo_fim == fim,
            AejArquivo.status == "gerando",
        )
        .order_by(AejArquivo.criado_em.desc())
        .limit(1)
    )
    arquivo = resultado.scalar_one_or_none()
    if arquivo is not None:
        return arquivo
    return await _criar_linha_controle(
        sessao,
        tenant_id,
        empresa=empresa,
        periodo_id=None,
        inicio=inicio,
        fim=fim,
        solicitado_por=None,
    )


async def gerar_aej_arquivo(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    incluir_banco_horas: bool = True,
    assinar: bool = False,
    solicitante_id: UUID | None = None,
) -> AejArquivo:
    """Metade pesada de `gerarAej` (T9): monta o arquivo inteiro, reconcilia
    o bloco de banco de horas contra o extrato real de F4 e grava o
    resultado. Chamada pelo corpo de `apps/worker/worker/tarefas/fiscal.py::
    gerar_aej`."""
    empresa = await _empresa_do_tenant(sessao, tenant_id, empresa_id)
    arquivo = await _localizar_ou_criar_arquivo(sessao, tenant_id, empresa, inicio, fim)

    try:
        linhas, totais, ptrp = await _montar_conteudo(
            sessao,
            tenant_id,
            empresa=empresa,
            inicio=inicio,
            fim=fim,
            incluir_banco_horas=incluir_banco_horas,
        )
        linhas_com_assinatura = [*linhas, montar_linha_assinatura()]
        # `montar_arquivo_texto` (A1) levanta `ValueError` (nao
        # `ErroDeAplicacao`) para caractere nao representavel em ISO-8859-1
        # -- traduzido aqui para `PONTO-FISC-006`, mesma orientacao que a
        # docstring daquela funcao ja documenta.
        dados_arquivo = montar_arquivo_texto(linhas_com_assinatura)
    except ErroDeAplicacao as erro_aplicacao:
        # `commit()`, nao so `flush()`: se o chamador (a tarefa do worker)
        # deixar a excecao propagar ate o `async with sessao:` que a
        # envolve, o `__aexit__` da sessao faz ROLLBACK do que estiver
        # pendente -- sem commit aqui, `status='falhou'` nunca seria
        # persistido e a linha ficaria `'gerando'` para sempre, bloqueando
        # `PONTO-FISC-002` indefinidamente para o mesmo periodo.
        arquivo.status = "falhou"
        arquivo.erro = erro_aplicacao.detalhe or erro_aplicacao.codigo
        await sessao.commit()
        raise
    except Exception as exc:  # pragma: no cover - defesa contra falha inesperada
        arquivo.status = "falhou"
        arquivo.erro = str(exc)
        await sessao.commit()
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO, detalhe="Falha inesperada na geracao do AEJ."
        ) from exc

    hash_sha256 = hashlib.sha256(dados_arquivo).hexdigest()

    chave = f"fiscal/aej/{tenant_id}/{arquivo.id}/{arquivo.nome_arquivo}"
    conteudo_ref = await salvar_objeto(
        chave, dados_arquivo, content_type="text/plain; charset=iso-8859-1"
    )

    arquivo.conteudo_ref = conteudo_ref
    arquivo.tamanho_bytes = len(dados_arquivo)
    arquivo.hash_sha256 = hash_sha256
    arquivo.total_vinculos = totais["vinculos"]
    arquivo.total_marcacoes = totais["marcacoes"]
    arquivo.total_ausencias = totais["ausencias"]
    arquivo.total_lancamentos_banco = totais["lancamentos_banco"]
    arquivo.ptrp_identificacao = ptrp.nome_prog
    arquivo.ptrp_cnpj = ptrp.idt_desenv if ptrp.tp_idt_desenv == "1" else None
    arquivo.ptrp_versao = ptrp.versao_prog
    arquivo.status = "gerado"
    arquivo.gerado_em = dt.datetime.now(tz=dt.UTC)
    if solicitante_id is not None:
        arquivo.solicitado_por = arquivo.solicitado_por or solicitante_id
    await sessao.flush()

    assinado = False
    if assinar:
        assinado = await _tentar_assinar(sessao, tenant_id, arquivo, solicitante_id)

    await sessao.commit()

    publicar_aej_gerado(
        tenant_id=tenant_id,
        arquivo_id=arquivo.id,
        empresa_id=empresa.id,
        periodo_id=arquivo.periodo_id,
        periodo_inicio=inicio,
        periodo_fim=fim,
        nome_arquivo=arquivo.nome_arquivo,
        total_vinculos=totais["vinculos"],
        total_marcacoes=totais["marcacoes"],
        total_ausencias=totais["ausencias"],
        total_lancamentos_banco=totais["lancamentos_banco"],
        hash_sha256=hash_sha256,
        assinado=assinado,
    )
    return arquivo


async def _tentar_assinar(
    sessao: AsyncSession,
    tenant_id: UUID,
    arquivo: AejArquivo,
    solicitante_id: UUID | None,
) -> bool:
    """Assina em CAdES quando ha certificado configurado (A3, T11); sem
    certificado, conclui normalmente sem erro (`status` fica `gerado`, nunca
    `assinado` -- PCF da fase, secao 2.4, "gerarAfd/gerarAej com assinar=true
    e sem certificado configurado concluem normalmente").

    Reaproveita `app.fiscal.assinatura.servico.assinar_arquivo_fiscal`
    (A3, T12) -- o MESMO orquestrador que `assinarArquivoFiscal` usa --
    em vez de duplicar a logica de assinar + verificar + gravar
    `arquivo_assinaturas` aqui. A UNICA diferenca de comportamento entre
    "assinar pelo endpoint dedicado" e "assinar automaticamente ao gerar" e
    que esta funcao PRECISA checar a existencia do certificado ANTES de
    chamar `assinar_arquivo_fiscal`: aquele orquestrador levanta
    `PONTO-FISC-004` quando nao ha certificado (o comportamento correto do
    endpoint dedicado, onde o usuario pediu explicitamente para assinar),
    mas `gerarAej` nunca pode propagar esse erro (§2.4) -- por isso o
    caminho "sem certificado" e interceptado aqui, silenciosamente, antes de
    delegar. Certificado EXPIRADO (`PONTO-FISC-005`) nao e interceptado: um
    certificado configurado porem invalido e uma falha operacional real que
    deve aparecer, mesmo no caminho automatico.

    Import tardio: `app.fiscal.assinatura` e ownership de A3 e pode nao
    existir ainda enquanto este modulo e desenvolvido/testado em paralelo
    (mesmo padrao de import tardio que `app.apuracao.tratamento.servico.
    cancelar_tratamento` ja usa para `app.apuracao.tratamento.recalculo`)."""
    try:
        from app.fiscal.assinatura.certificado import obter_certificado_configurado
        from app.fiscal.assinatura.servico import assinar_arquivo_fiscal
    except ImportError:  # pragma: no cover - so enquanto A3 nao publicou o modulo
        return False

    try:
        certificado = obter_certificado_configurado()
    except Exception:  # pragma: no cover - defesa contra interface ainda instavel de A3
        return False
    if certificado is None:
        return False

    pedido = esquemas.AssinaturaArquivoRequisicao.model_validate(
        {"tipoArquivo": "aej", "padrao": "CAdES", "formato": "detached"}
    )
    await assinar_arquivo_fiscal(sessao, tenant_id, arquivo.id, pedido, usuario_id=solicitante_id)
    return True


# =============================================================================
# Montagem do conteudo
# =============================================================================


async def _montar_conteudo(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa: Empresa,
    inicio: dt.date,
    fim: dt.date,
    incluir_banco_horas: bool,
) -> tuple[list[str], dict[str, int], IdentificacaoPtrp]:
    vinculos = await _resolver_vinculos(sessao, tenant_id, empresa.id, inicio, fim)
    if not vinculos:
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO,
            detalhe="Nenhum vinculo ativo encontrado para a empresa no periodo informado.",
        )

    reps_ativos = await _resolver_reps(sessao, tenant_id, empresa.id, inicio, fim)

    linhas_05: list[str] = []
    linhas_06: list[str] = []
    linhas_07: list[str] = []
    horarios_usados: dict[UUID, HorarioContratual] = {}
    horarios_codigo_cache: dict[UUID, str] = {}
    rep_map: dict[UUID, int] = {rep.id: indice for indice, rep in enumerate(reps_ativos, start=1)}
    reps_referenciados: set[UUID] = set()

    total_marcacoes = 0
    total_ausencias = 0
    total_lancamentos_banco = 0

    for resolvido in vinculos:
        fuso = await _fuso_do_vinculo(sessao, resolvido.vinculo, empresa)
        zona = ZoneInfo(fuso)

        marcacoes_periodo, rep_por_marcacao = await _carregar_marcacoes(
            sessao, tenant_id, resolvido.vinculo.id, inicio, fim, zona
        )
        tratamentos_periodo = await _carregar_tratamentos(
            sessao, tenant_id, resolvido.vinculo.id, inicio, fim
        )
        apuracoes = await _carregar_apuracoes(sessao, tenant_id, resolvido.vinculo.id, inicio, fim)

        (
            linhas_marcacoes,
            marcacoes_emitidas,
            horarios_do_vinculo,
            reps_do_vinculo,
        ) = await _montar_marcacoes_do_vinculo(
            sessao,
            resolvido=resolvido,
            marcacoes_periodo=marcacoes_periodo,
            rep_por_marcacao=rep_por_marcacao,
            tratamentos_periodo=tratamentos_periodo,
            apuracoes=apuracoes,
            zona=zona,
            rep_map=rep_map,
            horarios_codigo_cache=horarios_codigo_cache,
        )
        linhas_05.extend(linhas_marcacoes)
        total_marcacoes += marcacoes_emitidas
        reps_referenciados |= reps_do_vinculo
        for horario_id, entrada in horarios_do_vinculo.items():
            horarios_usados.setdefault(horario_id, entrada)

        linhas_ausencia, qtd_ausencias = _montar_ausencias_do_vinculo(resolvido, apuracoes)
        linhas_07.extend(linhas_ausencia)
        total_ausencias += qtd_ausencias

        if incluir_banco_horas:
            linhas_banco, qtd_lancamentos = await _montar_banco_horas_do_vinculo(
                sessao, tenant_id, resolvido, inicio, fim
            )
            linhas_07.extend(linhas_banco)
            total_lancamentos_banco += qtd_lancamentos

    linhas_06 = _montar_matriculas_multiplos_vinculos(vinculos)

    linhas: list[str] = []
    linhas.append(
        montar_registro_01(
            Cabecalho(
                tp_idt_empregador="1",
                idt_empregador=empresa.cnpj,
                caepf=empresa.cei_caepf,
                razao_ou_nome=empresa.razao_social,
                data_inicial_aej=inicio,
                data_final_aej=fim,
                data_hora_ger_aej=dt.datetime.now(tz=dt.UTC),
            )
        )
    )

    reps_para_emitir = [rep for rep in reps_ativos if rep.id in reps_referenciados] or reps_ativos
    for rep in reps_para_emitir:
        linhas.append(
            montar_registro_02(
                RepUtilizado(
                    id_rep_aej=rep_map[rep.id],
                    tp_rep="3",
                    nr_rep=_numero_inpi_para_nr_rep(rep.numero_inpi),
                )
            )
        )

    for resolvido in vinculos:
        linhas.append(
            montar_registro_03(
                VinculoAej(
                    idt_vinculo_aej=resolvido.idx,
                    cpf=resolvido.colaborador.cpf,
                    nome_emp=resolvido.colaborador.nome_completo,
                )
            )
        )

    for entrada in horarios_usados.values():
        linhas.append(montar_registro_04(entrada))

    linhas.extend(linhas_05)
    linhas.extend(linhas_06)
    linhas.extend(linhas_07)

    ptrp = _identificacao_ptrp(reps_ativos)
    linhas.append(montar_registro_08(ptrp))

    linhas.append(
        montar_registro_99(
            TrailerAej(
                qt_registros_tipo_01=1,
                qt_registros_tipo_02=len(reps_para_emitir),
                qt_registros_tipo_03=len(vinculos),
                qt_registros_tipo_04=len(horarios_usados),
                qt_registros_tipo_05=len(linhas_05),
                qt_registros_tipo_06=len(linhas_06),
                qt_registros_tipo_07=len(linhas_07),
                qt_registros_tipo_08=1,
            )
        )
    )

    totais = {
        "vinculos": len(vinculos),
        "marcacoes": total_marcacoes,
        "ausencias": total_ausencias,
        "lancamentos_banco": total_lancamentos_banco,
    }
    return linhas, totais, ptrp


async def _resolver_reps(
    sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID, inicio: dt.date, fim: dt.date
) -> list[RepP]:
    """REP-Ps "ativos/ja existentes da empresa no periodo" (PCF T8): nao
    excluidos, com janela de operacao sobrepondo `[inicio, fim]`. Ordenados
    por `criado_em`/`id` para numeracao de `idRepAej` deterministica e
    reprodutivel entre geracoes do mesmo periodo."""
    resultado = await sessao.execute(
        sa.select(RepP)
        .where(
            RepP.tenant_id == tenant_id,
            RepP.empresa_id == empresa_id,
            RepP.excluido_em.is_(None),
            RepP.data_inicio_operacao <= fim,
            sa.or_(RepP.data_fim_operacao.is_(None), RepP.data_fim_operacao >= inicio),
        )
        .order_by(RepP.criado_em, RepP.id)
    )
    return list(resultado.scalars().all())


async def _resolver_vinculos(
    sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID, inicio: dt.date, fim: dt.date
) -> list[_VinculoResolvido]:
    """Vinculos ativos da empresa no periodo: `apura_ponto=true` (vinculo que
    nao apura ponto nao tem marcacao/apuracao para exportar), nao excluidos,
    com sobreposicao de `[data_inicio, data_fim]` contra `[inicio, fim]`.
    Ordenados por `data_inicio`/`id` para numeracao de `idtVinculoAej`
    deterministica."""
    resultado = await sessao.execute(
        sa.select(Vinculo, Colaborador)
        .join(Colaborador, Colaborador.id == Vinculo.colaborador_id)
        .where(
            Vinculo.tenant_id == tenant_id,
            Vinculo.empresa_id == empresa_id,
            Vinculo.excluido_em.is_(None),
            Vinculo.apura_ponto.is_(True),
            Vinculo.data_inicio <= fim,
            sa.or_(Vinculo.data_fim.is_(None), Vinculo.data_fim >= inicio),
            Colaborador.excluido_em.is_(None),
        )
        .order_by(Vinculo.data_inicio, Vinculo.id)
    )
    linhas = resultado.all()
    return [
        _VinculoResolvido(vinculo=vinculo, colaborador=colaborador, idx=indice)
        for indice, (vinculo, colaborador) in enumerate(linhas, start=1)
    ]


async def _carregar_marcacoes(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    inicio: dt.date,
    fim: dt.date,
    zona: ZoneInfo,
) -> tuple[list[Marcacao], dict[UUID, UUID]]:
    """Marcacoes do vinculo cuja DATA LOCAL (fuso do vinculo) cai em
    `[inicio, fim]`. A janela de consulta em UTC e alargada em 1 dia para
    cada lado para nunca perder uma marcacao perto da fronteira do fuso."""
    janela_inicio = dt.datetime.combine(inicio - dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)
    janela_fim = dt.datetime.combine(fim + dt.timedelta(days=2), dt.time.min, tzinfo=dt.UTC)
    resultado = await sessao.execute(
        sa.select(Marcacao)
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.vinculo_id == vinculo_id,
            Marcacao.datahora_marcacao >= janela_inicio,
            Marcacao.datahora_marcacao < janela_fim,
        )
        .order_by(Marcacao.datahora_marcacao, Marcacao.nsr)
    )
    brutas = list(resultado.scalars().all())
    do_periodo = [m for m in brutas if inicio <= m.datahora_marcacao.astimezone(zona).date() <= fim]
    rep_por_marcacao = {m.id: m.rep_p_id for m in do_periodo}
    return do_periodo, rep_por_marcacao


async def _carregar_tratamentos(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, inicio: dt.date, fim: dt.date
) -> list[tuple[Tratamento, str]]:
    resultado = await sessao.execute(
        sa.select(Tratamento, TipoTratamento.categoria)
        .join(TipoTratamento, TipoTratamento.id == Tratamento.tipo_tratamento_id)
        .where(
            Tratamento.tenant_id == tenant_id,
            Tratamento.vinculo_id == vinculo_id,
            Tratamento.data_referencia >= inicio,
            Tratamento.data_referencia <= fim,
            Tratamento.status.in_(_STATUS_TRATAMENTO_APLICAVEIS),
        )
    )
    # Comprehension (nao `list(resultado.all())`) de proposito: converte cada
    # `Row[Tratamento, str]` em `tuple[Tratamento, str]` de verdade, o que o
    # `list()` sozinho nao faz aos olhos do mypy.
    return [(tratamento, categoria) for tratamento, categoria in resultado.all()]  # noqa: C416


async def _carregar_apuracoes(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, inicio: dt.date, fim: dt.date
) -> dict[dt.date, ApuracaoDia]:
    resultado = await sessao.execute(
        sa.select(ApuracaoDia).where(
            ApuracaoDia.tenant_id == tenant_id,
            ApuracaoDia.vinculo_id == vinculo_id,
            ApuracaoDia.data >= inicio,
            ApuracaoDia.data <= fim,
        )
    )
    return {ap.data: ap for ap in resultado.scalars().all()}


async def _montar_marcacoes_do_vinculo(
    sessao: AsyncSession,
    *,
    resolvido: _VinculoResolvido,
    marcacoes_periodo: list[Marcacao],
    rep_por_marcacao: dict[UUID, UUID],
    tratamentos_periodo: list[tuple[Tratamento, str]],
    apuracoes: dict[dt.date, ApuracaoDia],
    zona: ZoneInfo,
    rep_map: dict[UUID, int],
    horarios_codigo_cache: dict[UUID, str],
) -> tuple[list[str], int, dict[UUID, HorarioContratual], set[UUID]]:
    """Monta o bloco tipo '05' de um vinculo: desconsideradas viram registros
    `D` isolados (nunca entram no pareamento); as demais (reais +
    inclusoes manuais fictícias) sao pareadas por
    `app.apuracao.dominio.pareamento.parear_marcacoes` (F4, reaproveitada,
    nunca reimplementada) e viram pares E/S.

    `fonteMarc`: `"O"` para marcacao real sem tratamento; `"I"` para
    inclusao manual (`tipos_tratamento.categoria = 'inclusao_marcacao'`,
    unico caso com fonte de dado concreta nesta fase -- decisao de A2,
    documentada aqui em vez de mapear `P`/`X`/`T` sem uma fonte real que os
    distinga, conforme o PCF autoriza explicitamente: "documente a regra
    exata que voce escolher").
    """
    linhas: list[str] = []
    horarios_do_vinculo: dict[UUID, HorarioContratual] = {}
    reps_referenciados: set[UUID] = set()

    ids_desconsiderados: dict[UUID, str | None] = {}
    inclusoes: list[Tratamento] = []
    for tratamento, categoria in tratamentos_periodo:
        if categoria == _CATEGORIA_DESCONSIDERACAO_MARCACAO and tratamento.marcacao_id is not None:
            ids_desconsiderados[tratamento.marcacao_id] = tratamento.motivo
        elif categoria == _CATEGORIA_INCLUSAO_MARCACAO and tratamento.datahora_proposta is not None:
            inclusoes.append(tratamento)

    por_dia: dict[dt.date, list[MarcacaoParaPareamento]] = defaultdict(list)
    mapa_tratamento_por_objeto: dict[int, Tratamento] = {}

    for marcacao in marcacoes_periodo:
        if marcacao.id in ids_desconsiderados:
            continue
        dia_local = marcacao.datahora_marcacao.astimezone(zona).date()
        entrada = MarcacaoParaPareamento(
            id=marcacao.id,
            datahora=marcacao.datahora_marcacao,
            nsr=marcacao.nsr,
            sentido_informado=marcacao.sentido_informado,  # type: ignore[arg-type]
            origem="marcacao",
        )
        por_dia[dia_local].append(entrada)

    for tratamento in inclusoes:
        # `inclusoes` ja foi filtrada para so conter tratamentos com
        # `datahora_proposta` preenchida (ver o loop de classificacao acima);
        # a checagem aqui e so para estreitar o tipo Optional do ORM sem usar
        # `assert` (bandit S101) em codigo de aplicacao.
        if tratamento.datahora_proposta is None:  # pragma: no cover - defensivo
            continue
        dia_local = tratamento.datahora_proposta.astimezone(zona).date()
        entrada = MarcacaoParaPareamento(
            id=None,
            datahora=tratamento.datahora_proposta,
            nsr=-1,
            sentido_informado=tratamento.sentido,  # type: ignore[arg-type]
            origem="tratamento",
        )
        mapa_tratamento_por_objeto[id(entrada)] = tratamento
        por_dia[dia_local].append(entrada)

    marcacoes_por_id: dict[UUID, Marcacao] = {m.id: m for m in marcacoes_periodo}
    for marcacao_id, motivo in ids_desconsiderados.items():
        marcacao_desconsiderada = marcacoes_por_id.get(marcacao_id)
        if marcacao_desconsiderada is None:
            continue
        rep_id = rep_por_marcacao.get(marcacao_desconsiderada.id)
        linhas.append(
            montar_registro_05(
                MarcacaoAej(
                    idt_vinculo_aej=resolvido.idx,
                    data_hora_marc=marcacao_desconsiderada.datahora_marcacao,
                    id_rep_aej=rep_map.get(rep_id, 0) if rep_id else 0,
                    tp_marc="D",
                    seq_ent_saida=0,
                    fonte_marc="O",
                    motivo=motivo,
                )
            )
        )
        if rep_id is not None:
            reps_referenciados.add(rep_id)

    for dia in sorted(por_dia):
        apuracao = apuracoes.get(dia)
        cod_horario: str | None = None
        if apuracao is not None and apuracao.horario_id is not None:
            cod_horario = await _codigo_horario(sessao, apuracao.horario_id, horarios_codigo_cache)
            if cod_horario is not None and apuracao.horario_id not in horarios_do_vinculo:
                entrada_horario = await _montar_horario_contratual(
                    sessao, apuracao.horario_id, cod_horario, apuracao
                )
                if entrada_horario is not None:
                    horarios_do_vinculo[apuracao.horario_id] = entrada_horario

        resultado = parear_marcacoes(por_dia[dia])
        for numero_par, periodo in enumerate(resultado.periodos, start=1):
            entrada_linha, rep_id = _linha_marcacao(
                resolvido=resolvido,
                pareada=periodo.entrada,
                seq=numero_par,
                cod_horario=cod_horario if numero_par == 1 else None,
                rep_por_marcacao=rep_por_marcacao,
                mapa_tratamento_por_objeto=mapa_tratamento_por_objeto,
                rep_map=rep_map,
            )
            linhas.append(entrada_linha)
            if rep_id is not None:
                reps_referenciados.add(rep_id)
            if periodo.saida is not None:
                saida_linha, rep_id_saida = _linha_marcacao(
                    resolvido=resolvido,
                    pareada=periodo.saida,
                    seq=numero_par,
                    cod_horario=None,
                    rep_por_marcacao=rep_por_marcacao,
                    mapa_tratamento_por_objeto=mapa_tratamento_por_objeto,
                    rep_map=rep_map,
                )
                linhas.append(saida_linha)
                if rep_id_saida is not None:
                    reps_referenciados.add(rep_id_saida)

    total_emitidas = len(linhas)
    return linhas, total_emitidas, horarios_do_vinculo, reps_referenciados


def _linha_marcacao(
    *,
    resolvido: _VinculoResolvido,
    pareada: MarcacaoPareada,
    seq: int,
    cod_horario: str | None,
    rep_por_marcacao: dict[UUID, UUID],
    mapa_tratamento_por_objeto: dict[int, Tratamento],
    rep_map: dict[UUID, int],
) -> tuple[str, UUID | None]:
    marcacao_pareamento = pareada.marcacao
    tp_marc = "E" if pareada.sentido_atribuido == "entrada" else "S"
    if marcacao_pareamento.origem == "marcacao" and marcacao_pareamento.id is not None:
        rep_id = rep_por_marcacao.get(marcacao_pareamento.id)
        id_rep_aej = rep_map.get(rep_id, 0) if rep_id is not None else 0
        fonte = "O"
        motivo = None
    else:
        rep_id = None
        id_rep_aej = 0
        fonte = "I"
        tratamento = mapa_tratamento_por_objeto.get(id(marcacao_pareamento))
        motivo = tratamento.motivo if tratamento is not None else None

    linha = montar_registro_05(
        MarcacaoAej(
            idt_vinculo_aej=resolvido.idx,
            data_hora_marc=marcacao_pareamento.datahora,
            id_rep_aej=id_rep_aej,
            tp_marc=tp_marc,  # type: ignore[arg-type]
            seq_ent_saida=seq,
            fonte_marc=fonte,  # type: ignore[arg-type]
            cod_hor_contratual=cod_horario,
            motivo=motivo,
        )
    )
    return linha, rep_id


async def _codigo_horario(
    sessao: AsyncSession, horario_id: UUID, cache: dict[UUID, str]
) -> str | None:
    if horario_id in cache:
        return cache[horario_id]
    horario = await sessao.get(Horario, horario_id)
    if horario is None:
        return None
    cache[horario_id] = horario.codigo
    return horario.codigo


async def _montar_horario_contratual(
    sessao: AsyncSession, horario_id: UUID, codigo: str, apuracao: ApuracaoDia
) -> HorarioContratual | None:
    horario = await sessao.get(Horario, horario_id)
    if horario is None or horario.entrada is None or horario.saida is None:
        return None
    return HorarioContratual(
        cod_hor_contratual=codigo,
        dur_jornada=apuracao.previsto_minutos or horario.carga_minutos,
        hr_entrada_01=horario.entrada,
        hr_saida_01=horario.intervalo_inicio or horario.saida,
        hr_entrada_02=horario.intervalo_fim if horario.intervalo_inicio is not None else None,
        hr_saida_02=horario.saida if horario.intervalo_inicio is not None else None,
    )


def _montar_matriculas_multiplos_vinculos(vinculos: list[_VinculoResolvido]) -> list[str]:
    """Tipo '06': "para empregados com mais de um vinculo no AEJ" (titulo
    literal da tabela, `docs/leiaute-afd-aej.md` secao 10). Agrupa por
    `colaborador_id`; colaboradores com mais de um vinculo INCLUIDO neste
    arquivo ganham uma linha '06' por vinculo."""
    por_colaborador: dict[UUID, list[_VinculoResolvido]] = defaultdict(list)
    for resolvido in vinculos:
        por_colaborador[resolvido.colaborador.id].append(resolvido)

    linhas: list[str] = []
    for grupo in por_colaborador.values():
        if len(grupo) < 2:
            continue
        for resolvido in grupo:
            linhas.append(
                montar_registro_06(
                    MatriculaEsocial(
                        idt_vinculo_aej=resolvido.idx,
                        mat_esocial=resolvido.vinculo.matricula_esocial,
                    )
                )
            )
    return linhas


def _montar_ausencias_do_vinculo(
    resolvido: _VinculoResolvido, apuracoes: dict[dt.date, ApuracaoDia]
) -> tuple[list[str], int]:
    """Tipo '07', ausencias (`tipoAusenOuComp` 1/2/4): mapeamento de
    `apuracoes_dia.tipo_dia`/`falta_minutos` decidido por A2 (o leiaute nao
    da uma tabela de correspondencia -- PCF autoriza documentar a regra
    escolhida em vez de inventar valor arbitrario por linha):

    - `tipo_dia = 'dsr'` -> `"1"` (DSR).
    - `tipo_dia = 'compensado'` -> `"4"` (folga compensatoria de feriado).
    - `falta_minutos > 0` E o dia nao e `'afastamento'` (afastamento
      aprovado ja cobre a ausencia por outra via -- nao ha codigo
      `tipoAusenOuComp` para afastamento generico neste leiaute) E
      `abono_minutos == 0` (falta abonada nao e "falta nao justificada") ->
      `"2"`.

    Afastamentos gerais (doenca, licenca, etc. -- `afastamentos`/
    `tipos_afastamento.codigo_esocial`) nao tem codigo proprio no tipo '07'
    desta versao do leiaute; a unica funcao que cumprem aqui e a de EXCLUIR
    o dia da contagem de "falta nao justificada" (achado registrado no
    relatorio da fase, nao invencao de um codigo que a norma nao define).
    """
    linhas: list[str] = []
    for data, apuracao in sorted(apuracoes.items()):
        codigo = _TIPO_DIA_PARA_AUSENCIA.get(apuracao.tipo_dia)
        if codigo is not None:
            linhas.append(
                montar_registro_07(
                    AusenciaOuBancoHoras(
                        idt_vinculo_aej=resolvido.idx,
                        tipo_ausen_ou_comp=codigo,  # type: ignore[arg-type]
                        data=data,
                    )
                )
            )
        if (
            apuracao.tipo_dia != "afastamento"
            and (apuracao.falta_minutos or 0) > 0
            and (apuracao.abono_minutos or 0) == 0
        ):
            linhas.append(
                montar_registro_07(
                    AusenciaOuBancoHoras(
                        idt_vinculo_aej=resolvido.idx, tipo_ausen_ou_comp="2", data=data
                    )
                )
            )
    return linhas, len(linhas)


async def _montar_banco_horas_do_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    resolvido: _VinculoResolvido,
    inicio: dt.date,
    fim: dt.date,
) -> tuple[list[str], int]:
    """Tipo '07', banco de horas (`tipoAusenOuComp='3'`): le TODAS as contas
    do vinculo e, para cada uma, o extrato REAL de F4
    (`app.apuracao.banco_horas.consulta.obter_extrato_banco_horas`, paginado
    ate a ultima pagina) -- nunca uma query paralela sobre `bh_lancamentos`
    (PCF da fase, secao 2.13). `tipoMovBH`: `"1"` (inclusao) quando
    `minutos_equivalentes > 0`, `"2"` (compensacao) quando `< 0` -- decisao
    de A2 baseada no SINAL do valor que efetivamente moveu o saldo (`fator`
    e sempre `>= 0` por CHECK do schema, entao o sinal de
    `minutos_equivalentes` sempre bate com o de `minutos`), em vez de um
    mapeamento incompleto por `bh_lancamentos.tipo` (que tem 6 valores:
    credito/debito/quitacao/expiracao/estorno/ajuste, mas o leiaute so
    oferece 2 categorias).

    **Reconciliacao obrigatoria** (T9, criterio de aceite 4): a soma dos
    `qtMinutos` que este bloco esta prestes a exportar precisa bater EXATAMENTE
    com a soma de `minutos_equivalentes` dos lancamentos que o proprio
    extrato de F4 devolveu para o mesmo vinculo/periodo -- divergencia
    (so alcancavel por um defeito de transformacao deste modulo, ja que os
    dois lados leem os MESMOS lancamentos) interrompe com
    `PONTO-FISC-006`, antes de qualquer linha ser escrita no arquivo.
    """
    contas_resultado = await sessao.execute(
        sa.select(BhConta).where(
            BhConta.tenant_id == tenant_id, BhConta.vinculo_id == resolvido.vinculo.id
        )
    )
    contas = list(contas_resultado.scalars().all())
    if not contas:
        return [], 0

    lancamentos_todos: list[esquemas.BhLancamento] = []
    for conta in contas:
        cursor: str | None = None
        while True:
            extrato = await obter_extrato_banco_horas(
                sessao,
                tenant_id,
                resolvido.colaborador.id,
                vinculo_id=resolvido.vinculo.id,
                conta_id=conta.id,
                de=inicio,
                ate=fim,
                cursor=cursor,
                limite=200,
            )
            # `ExtratoBancoHoras.lancamentos`/`.paginacao` sao `Optional` no
            # schema Pydantic gerado (todo campo do contrato e opcional na
            # geracao, ver padrao do resto da base), mas `obter_extrato_
            # banco_horas` (F4) SEMPRE os preenche numa resposta bem
            # sucedida -- narrowing explicito em vez de silenciosamente
            # tratar `None` como lista/paginacao vazia, que esconderia um
            # contrato quebrado do lado de F4.
            if extrato.lancamentos is None or extrato.paginacao is None:
                raise ErroDeAplicacao(
                    CODIGO_FALHA_GERACAO,
                    detalhe=(
                        "obter_extrato_banco_horas devolveu resposta sem " "lancamentos/paginacao."
                    ),
                )
            lancamentos_todos.extend(extrato.lancamentos)
            if not extrato.paginacao.tem_mais or not extrato.paginacao.proximo_cursor:
                break
            cursor = extrato.paginacao.proximo_cursor

    linhas: list[str] = []
    soma_exportada = 0
    soma_extrato = 0
    for lancamento in lancamentos_todos:
        # `minutos_equivalentes`/`data_competencia` sao `Optional` no schema
        # Pydantic (reaproveitado tambem para outros contextos), mas SEMPRE
        # preenchidos num lancamento persistido -- `bh_lancamentos.minutos_
        # equivalentes`/`data_competencia` sao `NOT NULL` no schema real
        # (`schema.sql`, secao 10). Ausencia aqui e dado corrompido/contrato
        # quebrado, nunca um caso normal a pular silenciosamente (pular
        # SUBcontaria o banco de horas exportado) -- falha alto e claro com
        # `PONTO-FISC-006` em vez de `assert` (bandit S101 barra `assert` em
        # codigo de aplicacao).
        if lancamento.minutos_equivalentes is None or lancamento.data_competencia is None:
            raise ErroDeAplicacao(
                CODIGO_FALHA_GERACAO,
                detalhe=(
                    "Lancamento de banco de horas sem minutosEquivalentes/"
                    "dataCompetencia ao montar o bloco tipo '07' do AEJ."
                ),
            )
        soma_extrato += lancamento.minutos_equivalentes
        tipo_mov = "1" if lancamento.minutos_equivalentes > 0 else "2"
        linhas.append(
            montar_registro_07(
                AusenciaOuBancoHoras(
                    idt_vinculo_aej=resolvido.idx,
                    tipo_ausen_ou_comp="3",
                    data=lancamento.data_competencia,
                    qt_minutos=abs(lancamento.minutos_equivalentes),
                    tipo_mov_bh=tipo_mov,  # type: ignore[arg-type]
                )
            )
        )
        soma_exportada += lancamento.minutos_equivalentes

    verificar_reconciliacao_banco_horas(
        soma_exportada, soma_extrato, vinculo_id=resolvido.vinculo.id
    )

    return linhas, len(linhas)


def verificar_reconciliacao_banco_horas(
    soma_exportada: int, soma_extrato: int, *, vinculo_id: UUID
) -> None:
    """Guarda da reconciliacao obrigatoria do bloco de banco de horas (T9,
    criterio de aceite 4 do PCF F12 §7): levanta `PONTO-FISC-006` quando as
    duas somas nao batem, ANTES de qualquer linha ser escrita no arquivo.

    Extraida como funcao propria, testavel diretamente (sem banco), porque
    no desenho atual de `_montar_banco_horas_do_vinculo` as duas somas vem
    do MESMO lote de lancamentos (o extrato real de F4,
    `obter_extrato_banco_horas`) -- uma divergencia genuina so seria
    alcancavel por um defeito de transformacao introduzido neste modulo
    entre a leitura e a escrita, o que o teste desta funcao prova
    diretamente (soma adulterada -> `PONTO-FISC-006`), sem precisar
    manipular o banco para produzir uma divergencia artificial que o
    proprio desenho torna estruturalmente improvavel.
    """
    if soma_exportada != soma_extrato:
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO,
            detalhe=(
                "Divergencia na reconciliacao do bloco de banco de horas do AEJ: "
                f"exportado={soma_exportada}, extrato={soma_extrato}, vinculoId="
                f"{vinculo_id}."
            ),
        )


def _identificacao_ptrp(reps_ativos: list[RepP]) -> IdentificacaoPtrp:
    """PTRP = o proprio SEEG Ponto (mesmo software, mesmo desenvolvedor do
    REP-P). Reaproveita `cnpj_desenvolvedor`/`razao_social_desenvolvedor`/
    `versao_programa` de um REP-P da empresa (nao ha uma segunda fonte de
    identidade do desenvolvedor no schema) -- decisao de A2, documentada
    aqui em vez de inventar um CNPJ/razao social novos sem fonte."""
    if reps_ativos:
        referencia = reps_ativos[0]
        return IdentificacaoPtrp(
            nome_prog=_NOME_PROGRAMA,
            versao_prog=referencia.versao_programa or _VERSAO_PROGRAMA_PADRAO,
            tp_idt_desenv="1",
            idt_desenv=referencia.cnpj_desenvolvedor,
            razao_nome_desenv=referencia.razao_social_desenvolvedor,
            email_desenv=_EMAIL_DESENVOLVEDOR_PLACEHOLDER,
        )
    # Sem nenhum REP-P cadastrado para a empresa: nao ha fonte de identidade
    # do desenvolvedor. `gerar_aej_arquivo` so chega aqui se `_resolver_
    # vinculos` encontrou vinculos (o que nao implica REP-P existir) --
    # achado de contrato registrado no relatorio da fase.
    raise ErroDeAplicacao(
        CODIGO_FALHA_GERACAO,
        detalhe=(
            "Nenhum REP-P cadastrado para a empresa: nao ha fonte de identificacao "
            "do desenvolvedor do PTRP (tipo '08')."
        ),
    )
