"""Ramo `ferias`/`folga` do despachante genérico de materialização (F10, T12,
agente A4 -- PCF §2.3).

`materializar_ferias_ou_folga` é chamada por
`app.workflow.solicitacoes.materializacao.materializar_solicitacao_aprovada`
(A1, T4) quando a `Solicitacao` aprovada pertence a uma das duas categorias
que **não** mapeiam para `tipo_tratamento_id` (`tipos_solicitacao.categoria
IN ('ferias', 'folga')`, ver a tabela do PCF §2.2). É o ÚNICO arquivo deste
pacote (`app.workflow.solicitacoes`) com ownership de A4 -- todo o resto do
pacote (`tipos.py`, `servico.py`, `materializacao.py`, `eventos.py`) é de A1.

Duas categorias, dois efeitos completamente diferentes (nenhum dos dois passa
por `criar_tratamento`/`decidir_tratamento` -- a diferença exata entre
"corrigir um dia já apurado no passado" e "programar uma ausência futura,
ainda não apurada" está documentada no PCF §2.2, penúltimo parágrafo):

* `ferias`: cria um `Afastamento` novo (`status='aprovado'`, `origem=
  'solicitacao'`), respeitando a `EXCLUDE CONSTRAINT
  ex_afastamentos_sobreposicao` já existente no banco (dois afastamentos
  integrais aprovados do mesmo colaborador não podem se sobrepor). O resolvedor
  de jornada (F3, `resolver_jornada_do_dia`) já lê `afastamentos.status=
  'aprovado'` como insumo normal a partir da data de início -- nenhum
  recálculo retroativo é necessário porque o dia nunca foi apurado sem essa
  informação (PCF §2.2).
* `folga`: NÃO cria afastamento -- consome banco de horas, reaproveitando
  `app.apuracao.banco_horas.quitacoes.criar_quitacao_banco_horas` (F4, já
  implementado e testado; este módulo nunca duplica a lógica de consumo
  FIFO/LIFO nem a de validação de saldo, só monta o `BhQuitacaoCriar` e
  chama). A quantidade de minutos a debitar não vem em nenhum campo do
  contrato (`SolicitacaoCriar.payload` é `additionalProperties: true` sem
  formato fixo, e `apps/web/src/app/eu/solicitacoes/nova/page.tsx` -- F8,
  já concluída -- só envia `dataInicio`/`dataFim`/`descricao` para esta
  categoria, nenhum campo de minutos): a decisão desta fase é somar
  `cargaPrevistaMinutos` de cada dia `tipoDia == 'util'` do intervalo pedido,
  lendo o resolvedor de jornada (F3, só leitura) -- dias que já são
  folga/DSR/feriado/afastamento na jornada base não entram na soma, porque a
  folga só faz sentido substituindo um dia que seria trabalhado.

Em ambos os casos publica `ajuste.aprovado` (evento próprio de A1, `app.
workflow.solicitacoes.eventos.publicar_ajuste_aprovado`, mesma assinatura de
`app.apuracao.tratamento.eventos.publicar_ajuste_aprovado` de F4, mas com
`tratamento_id` OPCIONAL) com `tratamentoId` ausente do payload -- decisão
fixada pelo PCF §2.7 item 4 (o campo é `required` em `events.yaml`, mas
`ferias`/`folga` nunca produzem um `Tratamento`; a divergência já está
registrada em `docs/backlog.md` como candidato a RFC, não redecidida aqui).
O import de `app.workflow.solicitacoes.eventos` é TARDIO (dentro da função,
não no topo do módulo) -- mesmo padrão que
`app.apuracao.tratamento.servico.cancelar_tratamento`/`decisao._aprovar` (F4)
já usam para uma dependência de outro agente da mesma fase que roda em
paralelo: o módulo compila e é testável isoladamente mesmo que `eventos.py`
(ownership de A1) ainda não exista no momento em que este arquivo é escrito.

Nenhuma linha deste módulo escreve em `apuracoes_dia`, `apuracao_componentes`
ou `bh_lancamentos`, nem faz `INSERT`/`UPDATE` direto em `tratamentos` --
proibições 4/5 do PCF (§9). A única escrita de negócio própria é o `INSERT`
em `afastamentos` explicitamente autorizado pelo PCF §2.3/§4 para o caso
`ferias`; a quitação de banco de horas é inteiramente escrita por dentro de
`criar_quitacao_banco_horas` (F4).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from ponto_contracts import Afastamento, BhConta, Solicitacao, TipoAfastamento, TipoSolicitacao
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.quitacoes import criar_quitacao_banco_horas
from app.core.erros import ErroDeAplicacao
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from app.schemas import contrato as esquemas

#: Corpo da requisição inválido / pré-condição de negócio não atendida --
#: catálogo `errors.yaml`, categoria VAL (PCF §3, leituras obrigatórias).
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
#: `PONTO-VAL-007`, "Intervalo de datas inválido" -- mesmo código que
#: `app.jornada.calendario.afastamentos._validar_periodo` (F3) já usa para a
#: MESMA checagem (`ck_afastamentos_periodo`); replicado aqui como validação
#: preventiva antes do `INSERT`, nunca importado de F3 (ownership congelado).
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"
#: `PONTO-VAL-010`, "Vigência sobreposta ... o banco impede a sobreposição
#: por constraint de exclusão" -- descrição literal de `ex_afastamentos_
#: sobreposicao`; mesmo código que `app.workflow.aprovacoes.delegacoes.
#: criarDelegacao` (A1, T3) usa para a sobreposição de `delegacoes` no mesmo
#: PCF, mesmo mecanismo de EXCLUDE CONSTRAINT.
CODIGO_SOBREPOSICAO = "PONTO-VAL-010"
#: Recurso não encontrado -- nenhum `tipo_afastamento` ativo de categoria
#: `ferias`, ou nenhuma `bh_conta` para o vínculo (PCF §2.3).
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
#: Mais de um `tipo_afastamento` ativo de categoria `ferias` -- "erro de
#: configuração do tenant" (PCF §2.3); `PONTO-CONF-001` ("registro duplicado
#: ... já existe registro com a mesma chave") é o código do catálogo mais
#: próximo dessa semântica (o tenant deveria manter só um ativo), sem
#: inventar código novo (proibição 3 do PCF §9).
CODIGO_CONFIGURACAO_AMBIGUA = "PONTO-CONF-001"

#: `bh_contas.codigo` preferido quando a materialização de `folga` não
#: recebe uma conta explícita -- mesma convenção de "conta principal do
#: colaborador" que `app.apuracao.banco_horas.consulta._resolver_conta`
#: (F4, privada, não importada de outra fase) já usa; replicada aqui só
#: como critério de busca de leitura, nunca como lógica de domínio de banco
#: de horas.
_CODIGO_CONTA_BH_PADRAO = "normal"

#: Nome da constraint -> código do catálogo, só as que este módulo pode
#: violar em tempo de escrita (o único `INSERT` de negócio próprio é em
#: `afastamentos`, caso `ferias`).
_CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "ex_afastamentos_sobreposicao": CODIGO_SOBREPOSICAO,
    "ck_afastamentos_periodo": CODIGO_INTERVALO_INVALIDO,
    "fk_afastamentos_solicitacao": CODIGO_RECURSO_NAO_ENCONTRADO,
}


def _nome_constraint(origem: BaseException) -> str | None:
    """Extrai o nome da constraint do erro nativo do driver (mesmo padrão de
    `app.apuracao.tratamento.erros_bd._nome_constraint`, F4 -- cópia própria
    do domínio, nunca importada de outra fase)."""
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in _CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def _traduzir_integridade(
    exc: IntegrityError, *, padrao: str = CODIGO_CORPO_INVALIDO
) -> ErroDeAplicacao:
    nome = _nome_constraint(exc.orig or exc)
    codigo = _CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    detalhe = None
    if codigo == CODIGO_SOBREPOSICAO:
        detalhe = "Ja existe um afastamento aprovado que se sobrepoe ao periodo pedido."
    return ErroDeAplicacao(codigo, detalhe=detalhe, contexto_log={"constraint": nome})


async def _categoria_da_solicitacao(sessao: AsyncSession, solicitacao: Solicitacao) -> str:
    tipo = await sessao.get(TipoSolicitacao, solicitacao.tipo_solicitacao_id)
    if tipo is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Tipo de solicitacao nao encontrado."
        )
    return tipo.categoria


async def _resolver_tipo_afastamento_ferias(sessao: AsyncSession, tenant_id: UUID) -> UUID:
    """`tipos_afastamento WHERE tenant_id = ? AND categoria = 'ferias' AND
    ativo = true` (PCF §2.3). Nenhum ou mais de um resultado é erro de
    configuração do tenant -- não inventa uma escolha arbitrária entre
    vários tipos ativos."""
    resultado = await sessao.scalars(
        select(TipoAfastamento.id).where(
            TipoAfastamento.tenant_id == tenant_id,
            TipoAfastamento.categoria == "ferias",
            TipoAfastamento.ativo.is_(True),
            TipoAfastamento.excluido_em.is_(None),
        )
    )
    ids = list(resultado.all())
    if not ids:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO,
            detalhe=(
                "Nenhum tipo de afastamento ativo de categoria 'ferias' configurado "
                "para o tenant."
            ),
        )
    if len(ids) > 1:
        raise ErroDeAplicacao(
            CODIGO_CONFIGURACAO_AMBIGUA,
            detalhe=(
                "Mais de um tipo de afastamento ativo de categoria 'ferias' configurado; "
                "mantenha apenas um ativo."
            ),
        )
    return ids[0]


async def _materializar_ferias(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    *,
    aprovador_usuario_id: UUID | None,
) -> Afastamento:
    if solicitacao.vinculo_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="vinculoId e obrigatorio para materializar ferias."
        )
    if solicitacao.data_inicio is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="dataInicio e obrigatoria para materializar ferias."
        )
    if solicitacao.data_fim is not None and solicitacao.data_fim < solicitacao.data_inicio:
        # Defesa em profundidade, nao alcancavel por um teste que insere uma
        # `Solicitacao` de verdade: `ck_solicitacoes_periodo` (a mesma tabela
        # de onde este `solicitacao` veio) ja impede fisicamente gravar
        # `data_fim < data_inicio`. Mantido para o caso de um `Solicitacao`
        # construido em memoria fora do INSERT normal (ex.: objeto montado
        # a mao por um teste ou um caminho futuro que ainda nao existe).
        raise ErroDeAplicacao(  # pragma: no cover
            CODIGO_INTERVALO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )

    tipo_afastamento_id = await _resolver_tipo_afastamento_ferias(sessao, tenant_id)
    agora = dt.datetime.now(tz=dt.UTC)

    afastamento = Afastamento(
        tenant_id=tenant_id,
        colaborador_id=solicitacao.colaborador_id,
        vinculo_id=solicitacao.vinculo_id,
        tipo_afastamento_id=tipo_afastamento_id,
        data_inicio=solicitacao.data_inicio,
        data_fim=solicitacao.data_fim,
        motivo=solicitacao.descricao,
        origem="solicitacao",
        status="aprovado",
        solicitacao_id=solicitacao.id,
        aprovado_por=aprovador_usuario_id,
        aprovado_em=agora,
    )
    sessao.add(afastamento)
    try:
        # `ex_afastamentos_sobreposicao` (EXCLUDE CONSTRAINT, GIST) so e
        # avaliada no flush/commit -- nunca detectavel por SELECT previo sem
        # condicao de corrida (PCF §2.3: "antes de inserir, verifique" e
        # satisfeito capturando a violacao real do banco, a unica forma
        # livre de corrida).
        await sessao.flush()
    except IntegrityError as exc:
        raise _traduzir_integridade(exc) from exc
    return afastamento


async def _resolver_conta_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, colaborador_id: UUID, vinculo_id: UUID
) -> BhConta:
    """Leitura simples de `bh_contas` para achar a chave que `criar_quitacao_
    banco_horas` (F4) exige explicita no corpo -- a escrita em si (lancamento,
    saldo) continua inteiramente dentro de F4; este modulo so PRECISA saber
    QUAL conta, nunca calcula saldo/lancamento. Mesma preferencia por
    `codigo='normal'` que `app.apuracao.banco_horas.consulta._resolver_conta`
    (privada) ja usa, replicada aqui so como criterio de busca."""
    base = select(BhConta).where(
        BhConta.tenant_id == tenant_id,
        BhConta.colaborador_id == colaborador_id,
        BhConta.vinculo_id == vinculo_id,
    )
    resultado_padrao = await sessao.execute(
        base.where(BhConta.codigo == _CODIGO_CONTA_BH_PADRAO)
        .order_by(BhConta.periodo_inicio.desc())
        .limit(1)
    )
    conta = resultado_padrao.scalar_one_or_none()
    if conta is not None:
        return conta

    resultado = await sessao.execute(base.order_by(BhConta.periodo_inicio.desc()).limit(1))
    conta = resultado.scalar_one_or_none()
    if conta is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO,
            detalhe="Nenhuma conta de banco de horas encontrada para o vinculo da solicitacao.",
        )
    return conta


async def _minutos_a_debitar_no_periodo(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    data_inicio: dt.date,
    data_fim: dt.date,
) -> int:
    """Soma `cargaPrevistaMinutos` de cada dia `tipoDia == 'util'` do
    intervalo, lendo `resolver_jornada_do_dia` (F3, T4/A1, so leitura --
    nunca duplica a logica de resolucao de escala/jornada/feriado/
    afastamento). Dias que ja sao folga/DSR/feriado/afastamento na jornada
    base nao entram na soma: a folga so faz sentido substituindo um dia que
    seria trabalhado (docstring do modulo)."""
    total = 0
    dia = data_inicio
    while dia <= data_fim:
        resolucao = await resolver_jornada_do_dia(sessao, tenant_id, vinculo_id, dia)
        if resolucao.tipo_dia == "util":
            total += resolucao.carga_prevista_minutos or 0
        dia += dt.timedelta(days=1)
    return total


async def _materializar_folga(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    *,
    aprovador_usuario_id: UUID | None,
) -> None:
    if solicitacao.vinculo_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="vinculoId e obrigatorio para materializar folga."
        )
    if solicitacao.data_inicio is None or solicitacao.data_fim is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="dataInicio e dataFim sao obrigatorias para materializar folga.",
        )

    minutos = await _minutos_a_debitar_no_periodo(
        sessao, tenant_id, solicitacao.vinculo_id, solicitacao.data_inicio, solicitacao.data_fim
    )
    if minutos <= 0:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                "Nenhum dia util com carga prevista dentro do periodo pedido para debitar "
                "do banco de horas."
            ),
        )

    conta = await _resolver_conta_banco_horas(
        sessao, tenant_id, solicitacao.colaborador_id, solicitacao.vinculo_id
    )

    dados = esquemas.BhQuitacaoCriar.model_validate(
        {
            "bhContaId": conta.id,
            "colaboradorId": solicitacao.colaborador_id,
            "tipo": "folga",
            "minutos": minutos,
            "dataPrevista": solicitacao.data_inicio,
            "dataEfetivacao": solicitacao.data_inicio,
            "observacao": f"Folga da solicitacao {solicitacao.protocolo}.",
        }
    )
    # `criar_quitacao_banco_horas` (F4) e quem escreve o lancamento e atualiza
    # o saldo -- este modulo nunca toca `bh_lancamentos` (proibicao 5, §9).
    await criar_quitacao_banco_horas(sessao, tenant_id, dados, criado_por=aprovador_usuario_id)


async def materializar_ferias_ou_folga(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    *,
    aprovador_usuario_id: UUID | None,
) -> None:
    """Assinatura fixada pelo PCF (§2.3/§4) -- se mudar, atualizar o único
    ponto de chamada (`app.workflow.solicitacoes.materializacao.
    materializar_solicitacao_aprovada`, A1/T4) no mesmo commit.

    Resolve a categoria da própria `Solicitacao` (nunca recebida como
    parâmetro à parte -- a assinatura fixada não tem esse campo) e despacha
    para `_materializar_ferias`/`_materializar_folga`; qualquer outra
    categoria chegando aqui é erro de uso do despachante de A1 (T4), que só
    deveria chamar esta função para `categoria IN ('ferias', 'folga')`.
    """
    categoria = await _categoria_da_solicitacao(sessao, solicitacao)
    if categoria == "ferias":
        await _materializar_ferias(
            sessao, tenant_id, solicitacao, aprovador_usuario_id=aprovador_usuario_id
        )
    elif categoria == "folga":
        await _materializar_folga(
            sessao, tenant_id, solicitacao, aprovador_usuario_id=aprovador_usuario_id
        )
    else:
        # Despachante de A1 (T4) nunca deveria chamar este modulo fora de
        # `ferias`/`folga` -- guarda defensiva, exercitada por teste (T12).
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                f"Categoria '{categoria}' nao e materializada por este modulo "
                "(apenas ferias/folga)."
            ),
        )

    agora = dt.datetime.now(tz=dt.UTC)
    data_evento = solicitacao.data_inicio or solicitacao.data_referencia
    # Import tardio: `app.workflow.solicitacoes.eventos` e ownership de A1
    # (T4) -- ver docstring do modulo sobre o mesmo padrao ja usado por F4
    # (`decisao.py`/`servico.py`) para uma dependencia de outro agente da
    # mesma fase que roda em paralelo.
    from app.workflow.solicitacoes.eventos import publicar_ajuste_aprovado

    envelope = publicar_ajuste_aprovado(
        tenant_id=tenant_id,
        solicitacao_id=solicitacao.id,
        protocolo=solicitacao.protocolo,
        colaborador_id=solicitacao.colaborador_id,
        data_referencia=data_evento,
        decidido_em=agora,
        vinculo_id=solicitacao.vinculo_id,
        aprovador_usuario_id=aprovador_usuario_id,
        tratamento_id=None,
    )
    # Achado de integracao consertado ao fechar a fase (T15/T16): nenhum
    # publicador de evento desta fase chamava
    # `app.notificacao.motor.processar_evento` (ownership de A3), apesar de
    # o PCF §2.7 e a docstring de `app/notificacao/__init__.py` (A3) ja
    # fixarem esse chamado ("o proprio codigo de A1/A2/A4 chama o motor em
    # processo, logo apos publicar o envelope"). Mesma correcao aplicada em
    # `app/workflow/solicitacoes/servico.py`/`materializacao.py` (A1),
    # `app/workflow/fechamento/servico.py`/`assinatura.py` (A2) e
    # `apps/worker/worker/tarefas/fechamento.py` (A2). Import tardio:
    # `app.notificacao` e ownership de A3.
    from app.notificacao.motor import processar_evento

    await processar_evento(sessao, tenant_id, envelope)
