"""Teste de ponta a ponta da fase F10 (T15, "conjunto" A1+A2+A3) -- PCF
§6/T15, §7 (critérios de aceite 1, 3, 4, 5) e §8 (`pytest tests/f10/e2e -q -v`).

Percorre, numa única cadeia contínua e sobre o banco real, exatamente a
sequência que o PCF descreve:

1. Colaborador cria uma solicitação `ajuste_ponto` (cadeia gestor -> rh,
   configurada de fábrica pela fixture compartilhada `contexto_f10`).
   `criarSolicitacao` publica `ajuste.solicitado` -- confirma que isso gera
   notificação real (linha em `notificacoes`) para o aprovador da primeira
   etapa, nos três canais (`push`/`email`/`in_app`).
2. Gestor aprova a etapa 1 -- por DELEGAÇÃO (o gestor está "de férias" e
   delegou a decisão a um terceiro usuário; `app.workflow.aprovacoes.
   delegacoes.criar_delegacao` + `decidir_aprovacao(..., delegacaoId=...)`).
3. RH aprova a etapa 2 (final) -- materializa um `Tratamento` via
   `criar_tratamento`/`decidir_tratamento` (F4, reaproveitado, nunca
   duplicado) -- publica `ajuste.aprovado`, que notifica o colaborador. A
   apuração do dia muda de resultado: capturamos `ApuracaoDia` via
   `apurar_dia` (F4) ANTES de criar a solicitação (dia com falta plena, sem
   nenhuma marcação) e comparamos com o estado real depois da aprovação
   (F4 já reagenda `recalcular_periodo` sozinho dentro de
   `decidir_tratamento`).
4. Fechamento do período (`criarFechamento` + a tarefa assíncrona
   `processar_fechamento`, chamada diretamente, mesmo padrão de
   `tests/f10/fechamento/test_worker_tarefas.py`) -- publica
   `periodo.fechado`, notifica quem fechou.
5. Geração do espelho oficial com PDF real gravado no MinIO (dentro do
   próprio `processar_fechamento`, `gerarEspelhos=true`).
6. Assinatura eletrônica do colaborador (`assinarEspelho`) -- confirma que o
   hash bate (`verificar_assinatura`); publica `espelho.assinado`.
7. Reabertura do período com justificativa (`reabrirFechamento`) -- confirma
   que grava exatamente uma linha em `auditoria` com `acao='reabrir'`;
   publica `periodo.reaberto`, notifica quem reabriu.
8. Novo espelho retificado (`gerar_espelho_do_vinculo` de novo, mesmo
   período/vínculo) -- confirma `versao=2`, `tipo='retificado'`, sem apagar
   a `versao=1`.

Ao final, drena a fila real de notificações (`worker.tarefas.notificacoes.
processar_fila_notificacoes`, T11/A3) e IMPRIME (rode com `-v -s`) a linha de
`notificacoes` de cada transição com seu `status` final -- exigência literal
do "pronto quando" de T15.

**Achado de integração consertado para este teste (e para o critério de
aceite 5) passar, documentado no relatório da fase**: nenhum dos
publicadores de evento desta fase (`criarSolicitacao`/`materializacao.py`/
A1, `reabrirFechamento`/`assinarEspelho`/`processar_fechamento`/A2,
`materializar_ferias_ou_folga`/A4) chamava
`app.notificacao.motor.processar_evento` (A3) -- apesar de o PCF §2.7 e a
própria docstring de `app/notificacao/__init__.py` (escrita por A3) já
fixarem esse chamado. Sem essa chamada, nenhuma linha de `notificacoes` era
criada nunca, em produção real -- não é peculiaridade deste teste. A
correção mínima (seis pontos de chamada, um por publicador) foi aplicada nos
próprios módulos de A1/A2/A4, documentada em cada ponto.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import AsyncIterator
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
import sqlalchemy as sa
from ponto_contracts import (
    Aprovacao,
    Auditoria,
    Espelho,
    Notificacao,
    Solicitacao,
    Tratamento,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.servico import apurar_dia
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes import delegacoes
from app.workflow.aprovacoes import servico as aprovacoes_servico
from app.workflow.fechamento import assinatura as assinatura_servico
from app.workflow.fechamento import servico as fechamento_servico
from app.workflow.fechamento.espelho import gerar_espelho_do_vinculo
from app.workflow.solicitacoes import servico as solicitacoes_servico
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste

_FUSO = ZoneInfo("America/Sao_Paulo")

# ---------------------------------------------------------------------------
# Fixtures locais deste subpacote (`tests/f10/e2e/**`, território comum das
# tarefas conjuntas T15/T16 -- não é ownership exclusivo de nenhum dos
# quatro agentes; mesma FORMA de fixture que `tests/f10/fechamento/
# conftest.py`/`tests/f10/notificacao/conftest.py` já usam, cópia local
# porque `redis_teste_url_f10` não é definida no `conftest.py`
# compartilhado, T1/A1).
# ---------------------------------------------------------------------------

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def redis_teste_url_f10() -> str:
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)


@pytest_asyncio.fixture
async def ambiente_worker_f10(url_login_sessao_f10: URL) -> AsyncIterator[None]:
    """Aponta `app.core.config.Configuracao`/`worker.config.Configuracao`
    (`DATABASE_URL`) para o MESMO banco de teste e a MESMA role de LOGIN que
    `sessao_f10` usa -- necessário porque `worker.tarefas.fechamento.
    processar_fechamento`/`worker.tarefas.notificacoes.
    processar_fila_notificacoes` abrem sua PRÓPRIA sessão via
    `app.db.sessao.fabrica_de_sessoes()` (o caminho real de produção, onde o
    worker é um processo à parte). Mesmo padrão de `tests/f10/notificacao/
    conftest.py::ambiente_worker_notificacao` (A3) e do autouse
    `_encerrar_engine_worker` de `tests/f10/fechamento/
    test_worker_tarefas.py` (A2), combinados aqui porque este teste chama
    AMBAS as tarefas assíncronas na mesma função."""
    os.environ["DATABASE_URL"] = url_login_sessao_f10.render_as_string(hide_password=False)
    from worker.config import obter_configuracao as obter_configuracao_worker

    from app.core.config import obter_configuracao as obter_configuracao_api
    from app.db.sessao import encerrar_engine

    obter_configuracao_api.cache_clear()
    obter_configuracao_worker.cache_clear()
    await encerrar_engine()
    yield
    await encerrar_engine()


# ---------------------------------------------------------------------------
# Setup local: hierarquia gestor/rh (para pré-atribuir o aprovador de cada
# etapa via `colaborador_gestores`) -- mesmo padrão de
# `tests/f10/aprovacoes/test_servico.py::_ligar_usuario_a_um_gestor_imediato`
# (A1), generalizado aqui para os dois papéis (`imediato` para `gestor`,
# `rh` para `rh`) porque o e2e precisa da cadeia completa, não só da
# primeira etapa.
# ---------------------------------------------------------------------------


async def _criar_rep_p(sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID) -> UUID:
    """REP-P mínimo para poder inserir uma marcação real de teste -- mesmo
    padrão de `tests/f4/tratamento/test_servico_erros_e_filtros.py::
    _criar_rep_p` (cópia local, nunca importada de outra fase)."""
    import secrets

    rep_p_id = uuid.uuid4()
    sufixo = uuid.uuid4().hex[:10]
    await sessao.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        :cnpj_dev, 'SEEG Servicos de TI', :cnpj_emp, 'Empresa de Teste', "
            "        '1.0.0', :data_inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_dev": f"{secrets.randbelow(10**14):014d}",
            "cnpj_emp": f"{secrets.randbelow(10**14):014d}",
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    return rep_p_id


async def _inserir_marcacao_real(
    sessao: AsyncSession,
    contexto: ContextoF10,
    *,
    rep_p_id: UUID,
    datahora: dt.datetime,
    nsr: int,
) -> UUID:
    """Marcação REAL mínima e válida (satisfaz todo `CHECK`/`NOT NULL` da
    tabela), inserida diretamente via SQL só para MONTAR o cenário de teste
    (o colaborador bateu a entrada no terminal e esqueceu de bater a saída)
    -- nunca através do código de workflow desta fase, que jamais toca
    `marcacoes` (PCF, "Não toca" §4). Mesmo padrão de `tests/f4/tratamento/
    test_servico_erros_e_filtros.py::_inserir_marcacao` (cópia local)."""
    import secrets

    marcacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO marcacoes "
            "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, vinculo_id, nsr, "
            " cpf, datahora_marcacao, fuso_horario, canal, crc16, hash_registro) "
            "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :vinculo_id, "
            "        :nsr, :cpf, :datahora, 'America/Sao_Paulo', 'terminal', :crc16, :hash)"
        ),
        {
            "id": marcacao_id,
            "tenant_id": contexto.tenant_id,
            "rep_p_id": rep_p_id,
            "empresa_id": contexto.empresa_id,
            "colaborador_id": contexto.colaborador_id,
            "vinculo_id": contexto.vinculo_id,
            "nsr": nsr,
            "cpf": f"{uuid.uuid4().int % 10**11:011d}",
            "datahora": datahora,
            "crc16": nsr % 65536,
            "hash": secrets.token_hex(32),
        },
    )
    return marcacao_id


async def _ligar_usuario_a_um_gestor(
    sessao: AsyncSession,
    contexto: ContextoF10,
    *,
    usuario_id: UUID,
    tipo_colaborador_gestores: str,
    rotulo: str,
) -> None:
    colaborador_papel_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO colaboradores (id, tenant_id, empresa_id, matricula, cpf, "
            "nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        {
            "id": colaborador_papel_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "matricula": f"{rotulo}-{uuid.uuid4().hex[:8]}",
            "cpf": f"{uuid.uuid4().int % 10**11:011d}",
            "nome": f"{rotulo} de Teste E2E",
        },
    )
    await sessao.execute(
        text("UPDATE usuarios SET colaborador_id = :colaborador_id WHERE id = :id"),
        {"colaborador_id": colaborador_papel_id, "id": usuario_id},
    )
    await sessao.execute(
        text(
            "INSERT INTO colaborador_gestores "
            "(id, tenant_id, colaborador_id, gestor_colaborador_id, tipo, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :colaborador_id, :gestor_colaborador_id, "
            "        :tipo, :vigencia_inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "gestor_colaborador_id": colaborador_papel_id,
            "tipo": tipo_colaborador_gestores,
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )


async def _notificacoes(
    sessao: AsyncSession, tenant_id: UUID, *, evento: str, usuario_id: UUID | None = None
) -> list[Notificacao]:
    consulta = sa.select(Notificacao).where(
        Notificacao.tenant_id == tenant_id, Notificacao.evento == evento
    )
    if usuario_id is not None:
        consulta = consulta.where(Notificacao.usuario_id == usuario_id)
    consulta = consulta.order_by(Notificacao.canal)
    return list((await sessao.execute(consulta)).scalars().all())


def _linha_relatorio(rotulo_transicao: str, notificacao: Notificacao) -> str:
    return (
        f"  [{rotulo_transicao}] evento={notificacao.evento!r} canal={notificacao.canal!r} "
        f"usuarioId={notificacao.usuario_id} status={notificacao.status!r} "
        f"provedor={notificacao.provedor!r} enviadaEm={notificacao.enviada_em}"
    )


@pytest.mark.asyncio
async def test_fluxo_completo_multicanal(
    sessao_f10: AsyncSession,
    contexto_f10: ContextoF10,
    redis_teste_url_f10: str,
    ambiente_worker_f10: None,
) -> None:
    tenant_id = contexto_f10.tenant_id
    print("\n=== T15 -- fluxo completo multicanal (F10) ===")

    # ------------------------------------------------------------------
    # Setup: hierarquia gestor/rh, para a fila de aprovação pré-atribuir
    # `aprovacoes.aprovador_usuario_id` (necessário para
    # `_aprovadores_pendentes` do motor de notificações encontrar alguém a
    # notificar em `ajuste.solicitado` -- sem isto a etapa nasce com
    # `aprovador_usuario_id=NULL` e nenhuma notificação seria criada).
    # ------------------------------------------------------------------
    await _ligar_usuario_a_um_gestor(
        sessao_f10,
        contexto_f10,
        usuario_id=contexto_f10.gestor_usuario_id,
        tipo_colaborador_gestores="imediato",
        rotulo="Gestor",
    )
    await _ligar_usuario_a_um_gestor(
        sessao_f10,
        contexto_f10,
        usuario_id=contexto_f10.rh_usuario_id,
        tipo_colaborador_gestores="rh",
        rotulo="RH",
    )
    # Delegado: terceiro usuário sem vínculo de colaborador (não precisa --
    # `criar_delegacao` só exige `usuarios.id` real).
    delegado_usuario_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :email, 'Delegado de Teste E2E', 'ativo')"
        ),
        {
            "id": delegado_usuario_id,
            "tenant_id": tenant_id,
            "email": f"delegado-{uuid.uuid4().hex[:8]}@f10.teste",
        },
    )
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)

    # ------------------------------------------------------------------
    # Dia-alvo: segunda-feira dentro do período aberto da fixture e dentro
    # do limite de retroatividade do tipo de solicitação (30 dias) -- dia
    # útil real da jornada semeada (08:00-17:00, 1h de intervalo).
    # ------------------------------------------------------------------
    dia_alvo = dt.date.today() - dt.timedelta(days=1)
    assert contexto_f10.periodo_data_inicio <= dia_alvo <= contexto_f10.periodo_data_fim, (
        "dia_alvo precisa cair dentro do periodo aberto pela fixture -- ajuste a massa se a "
        "execucao acontecer perto da virada do mes."
    )

    # ------------------------------------------------------------------
    # Cenario real de origem: o colaborador bateu a ENTRADA no terminal
    # (marcacao real, inserida so como massa de teste -- nunca atraves do
    # codigo de workflow desta fase, que nunca toca `marcacoes`) mas
    # esqueceu de bater a SAIDA. Isso e o que torna o antes/depois
    # inequivoco: antes, o dia fica com uma marcacao IMPAR (so entrada);
    # depois da inclusao manual da saida (o Tratamento desta fase), o dia
    # pareia por completo.
    # ------------------------------------------------------------------
    rep_p_id = await _criar_rep_p(sessao_f10, tenant_id, contexto_f10.empresa_id)
    await _inserir_marcacao_real(
        sessao_f10,
        contexto_f10,
        rep_p_id=rep_p_id,
        datahora=dt.datetime.combine(dia_alvo, dt.time(8, 0), tzinfo=_FUSO),
        nsr=1,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)

    # ------------------------------------------------------------------
    # Snapshot ANTES: uma marcacao real (entrada), sem tratamento -- dia
    # com marcacao impar e falta plena (a saida nunca foi registrada).
    # Capturado chamando `apurar_dia` (F4) diretamente, real, contra o
    # banco (nao fabricado a mao).
    # ------------------------------------------------------------------
    apuracao_antes = await apurar_dia(sessao_f10, tenant_id, contexto_f10.vinculo_id, dia_alvo)
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    print(
        f"\n[1] ANTES apurar_dia({dia_alvo}): tipoDia={apuracao_antes.tipo_dia!r} "
        f"previstoMinutos={apuracao_antes.previsto_minutos} "
        f"trabalhadoMinutos={apuracao_antes.trabalhado_minutos} "
        f"faltaMinutos={apuracao_antes.falta_minutos} "
        f"marcacoesImpares={apuracao_antes.marcacoes_impares} status={apuracao_antes.status!r}"
    )

    # ==================================================================
    # PASSO 1 -- colaborador cria a solicitacao `ajuste_ponto` (inclusao
    # manual da marcacao de saida que ele esqueceu de bater).
    # ==================================================================
    datahora_saida_proposta = dt.datetime.combine(
        dia_alvo, dt.time(17, 0), tzinfo=_FUSO
    ).isoformat()
    corpo_solicitacao = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto_f10.tipo_solicitacao_id),
            "colaboradorId": str(contexto_f10.colaborador_id),
            "dataReferencia": dia_alvo.isoformat(),
            "descricao": "Esqueci de bater o ponto na saida -- inclusao manual (teste e2e T15).",
            "payload": {"datahoraProposta": datahora_saida_proposta, "sentido": "saida"},
        }
    )
    solicitacao = await solicitacoes_servico.criar_solicitacao(
        sessao_f10, tenant_id, corpo_solicitacao, usuario_id=contexto_f10.colaborador_usuario_id
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    print(
        f"\n[2] criarSolicitacao -> protocolo={solicitacao.protocolo} status={solicitacao.status}"
    )

    notificacoes_solicitado = await _notificacoes(
        sessao_f10, tenant_id, evento="ajuste.solicitado", usuario_id=contexto_f10.gestor_usuario_id
    )
    assert len(notificacoes_solicitado) == 3, (
        "ajuste.solicitado deveria notificar o gestor (etapa 1 pre-atribuida) nos 3 canais "
        f"padrao (push/email/in_app); encontrado: {len(notificacoes_solicitado)}"
    )
    assert {n.canal for n in notificacoes_solicitado} == {"push", "email", "in_app"}
    for n in notificacoes_solicitado:
        assert n.status == "pendente"
        print(_linha_relatorio("1-ajuste.solicitado (recem-criada)", n))

    consulta_etapa1 = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == tenant_id,
        Aprovacao.solicitacao_id == solicitacao.id,
        Aprovacao.etapa == 1,
    )
    etapa1 = (await sessao_f10.execute(consulta_etapa1)).scalars().one()
    assert etapa1.aprovador_usuario_id == contexto_f10.gestor_usuario_id
    assert etapa1.papel == "gestor"

    # ==================================================================
    # PASSO 2 -- gestor aprova a etapa 1, POR DELEGACAO (gestor de ferias,
    # delegou a decisao a um terceiro).
    # ==================================================================
    agora = dt.datetime.now(tz=dt.UTC)
    delegacao = await delegacoes.criar_delegacao(
        sessao_f10,
        tenant_id,
        esquemas.DelegacaoCriar.model_validate(
            {
                "deleganteUsuarioId": str(contexto_f10.gestor_usuario_id),
                "delegadoUsuarioId": str(delegado_usuario_id),
                "motivo": "Gestor de ferias -- delegacao para o e2e da F10 (T15).",
                "inicioEm": (agora - dt.timedelta(hours=1)).isoformat(),
                "fimEm": (agora + dt.timedelta(days=5)).isoformat(),
                "status": "ativa",
            }
        ),
        usuario_id=contexto_f10.gestor_usuario_id,
    )
    await sessao_f10.flush()

    etapa1_decidida = await aprovacoes_servico.decidir_aprovacao(
        sessao_f10,
        tenant_id,
        etapa1.id,
        esquemas.DecisaoRequisicao.model_validate(
            {
                "decisao": "aprovar",
                "comentario": "Aprovado pelo delegado, gestor titular de ferias.",
                "delegacaoId": str(delegacao.id),
            }
        ),
        usuario_id=delegado_usuario_id,
        ip="203.0.113.55",
        user_agent="pytest-e2e-f10",
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert etapa1_decidida.decisao == "aprovada"
    assert etapa1_decidida.aprovador_delegacao_id == delegacao.id
    print(
        f"\n[3] decidirAprovacao etapa 1 (POR DELEGACAO, delegado={delegado_usuario_id}) "
        f"-> decisao={etapa1_decidida.decisao} delegacaoId={etapa1_decidida.aprovador_delegacao_id}"
    )

    linha_auditoria_delegacao = (
        (
            await sessao_f10.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == tenant_id,
                    Auditoria.entidade == "aprovacoes",
                    Auditoria.entidade_id == etapa1.id,
                )
            )
        )
        .scalars()
        .one()
    )
    assert linha_auditoria_delegacao.acao == "aprovar"
    assert linha_auditoria_delegacao.usuario_id == delegado_usuario_id
    assert linha_auditoria_delegacao.delegacao_id == delegacao.id

    consulta_etapa2 = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == tenant_id,
        Aprovacao.solicitacao_id == solicitacao.id,
        Aprovacao.etapa == 2,
    )
    etapa2 = (await sessao_f10.execute(consulta_etapa2)).scalars().one()
    assert etapa2.papel == "rh"
    assert etapa2.aprovador_usuario_id == contexto_f10.rh_usuario_id
    print(
        f"[4] etapa 2 criada -> papel={etapa2.papel} "
        f"aprovadorUsuarioId={etapa2.aprovador_usuario_id}"
    )

    # ==================================================================
    # PASSO 3 -- RH aprova a etapa 2 (final): materializa o Tratamento via
    # F4 (criar_tratamento + decidir_tratamento), publica ajuste.aprovado.
    # ==================================================================
    etapa2_decidida = await aprovacoes_servico.decidir_aprovacao(
        sessao_f10,
        tenant_id,
        etapa2.id,
        esquemas.DecisaoRequisicao.model_validate(
            {"decisao": "aprovar", "comentario": "Inclusao manual da saida confirmada pelo RH."}
        ),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert etapa2_decidida.decisao == "aprovada"
    print(f"\n[5] decidirAprovacao etapa 2 (RH, final) -> decisao={etapa2_decidida.decisao}")

    consulta_solicitacao = sa.select(Solicitacao).where(Solicitacao.id == solicitacao.id)
    solicitacao_final = (await sessao_f10.execute(consulta_solicitacao)).scalars().one()
    assert solicitacao_final.status == "aprovada"

    consulta_tratamento = sa.select(Tratamento).where(
        Tratamento.tenant_id == tenant_id, Tratamento.solicitacao_id == solicitacao.id
    )
    tratamento = (await sessao_f10.execute(consulta_tratamento)).scalars().one()
    assert tratamento.status in ("aprovado", "aplicado")
    print(f"    Tratamento materializado -> id={tratamento.id} status={tratamento.status}")

    notificacoes_aprovado = await _notificacoes(
        sessao_f10,
        tenant_id,
        evento="ajuste.aprovado",
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    assert len(notificacoes_aprovado) == 3, (
        "ajuste.aprovado deveria notificar o colaborador solicitante nos 3 canais padrao; "
        f"encontrado: {len(notificacoes_aprovado)}"
    )
    for n in notificacoes_aprovado:
        assert n.status == "pendente"
        print(_linha_relatorio("3-ajuste.aprovado (recem-criada)", n))

    # ------------------------------------------------------------------
    # Snapshot DEPOIS: mesmo `apurar_dia`, mesmo dia -- deve refletir o
    # tratamento aprovado (a apuracao ja foi recalculada pelo proprio
    # `decidir_tratamento`/F4; chamamos `apurar_dia` de novo so para ler o
    # estado real gravado, nao para forcar um novo calculo).
    # ------------------------------------------------------------------
    apuracao_depois = await apurar_dia(sessao_f10, tenant_id, contexto_f10.vinculo_id, dia_alvo)
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    print(
        f"\n[6] DEPOIS apurar_dia({dia_alvo}): tipoDia={apuracao_depois.tipo_dia!r} "
        f"previstoMinutos={apuracao_depois.previsto_minutos} "
        f"trabalhadoMinutos={apuracao_depois.trabalhado_minutos} "
        f"faltaMinutos={apuracao_depois.falta_minutos} "
        f"marcacoesImpares={apuracao_depois.marcacoes_impares} status={apuracao_depois.status!r}"
    )

    diferencas = {
        campo: (getattr(apuracao_antes, campo), getattr(apuracao_depois, campo))
        for campo in (
            "trabalhado_minutos",
            "falta_minutos",
            "marcacoes_impares",
            "status",
        )
        if getattr(apuracao_antes, campo) != getattr(apuracao_depois, campo)
    }
    print(f"    Diferencas antes/depois em apuracoes_dia: {diferencas}")
    assert apuracao_antes != apuracao_depois, (
        "criterio de aceite 1: apuracoes_dia precisa ser diferente antes/depois da aprovacao "
        "da solicitacao ajuste_ponto -- ficou identico."
    )
    assert (
        diferencas
    ), "nenhum campo numerico/de status mudou -- apuracao nao refletiu o tratamento."

    # ==================================================================
    # PASSO 4 -- fechamento do periodo que cobre o dia_alvo (criarFechamento
    # + a tarefa assincrona processar_fechamento, chamada diretamente --
    # mesmo padrao de tests/f10/fechamento/test_worker_tarefas.py, A2).
    # ==================================================================
    resposta_fechamento = await fechamento_servico.criar_fechamento(
        sessao_f10,
        tenant_id,
        esquemas.FechamentoCriar.model_validate(
            {
                "periodoId": str(contexto_f10.periodo_id),
                "escopo": "empresa",
                "empresaId": str(contexto_f10.empresa_id),
                "gerarEspelhos": True,
                "forcar": True,
            }
        ),
        usuario_id=contexto_f10.rh_usuario_id,
        redis_url=redis_teste_url_f10,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    fechamento_id = resposta_fechamento.id
    print(f"\n[7] criarFechamento -> id={fechamento_id} status={resposta_fechamento.status}")

    from worker.tarefas.fechamento import processar_fechamento

    resultado_worker = await processar_fechamento(
        {"job_id": "e2e-f10-fechamento"},
        tenant_id=str(tenant_id),
        fechamento_id=str(fechamento_id),
        gerar_espelhos=True,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert resultado_worker["implementado"] is True
    assert resultado_worker["espelhosGerados"] == 1
    print(f"    processar_fechamento (worker) -> {resultado_worker}")

    notificacoes_fechado = await _notificacoes(
        sessao_f10, tenant_id, evento="periodo.fechado", usuario_id=contexto_f10.rh_usuario_id
    )
    assert len(notificacoes_fechado) == 3
    for n in notificacoes_fechado:
        assert n.status == "pendente"
        print(_linha_relatorio("4-periodo.fechado (recem-criada)", n))

    # ==================================================================
    # PASSO 5 -- espelho oficial (ja gerado dentro de processar_fechamento,
    # com PDF real no MinIO). Confirma o registro e o hash.
    # ==================================================================
    espelho_oficial = (
        (
            await sessao_f10.execute(
                sa.select(Espelho).where(
                    Espelho.tenant_id == tenant_id,
                    Espelho.fechamento_id == fechamento_id,
                    Espelho.tipo == "oficial",
                )
            )
        )
        .scalars()
        .one()
    )
    assert espelho_oficial.versao == 1
    assert espelho_oficial.conteudo_ref, "gerarPdf=True deveria ter gravado a chave do MinIO."
    print(
        f"\n[8] Espelho oficial gerado -> id={espelho_oficial.id} "
        f"versao={espelho_oficial.versao} hashSha256={espelho_oficial.hash_sha256} "
        f"conteudoRef(MinIO)={espelho_oficial.conteudo_ref}"
    )

    # ==================================================================
    # PASSO 6 -- assinatura eletronica do colaborador.
    # ==================================================================
    assinatura = await assinatura_servico.assinar_espelho(
        sessao_f10,
        tenant_id,
        espelho_oficial.id,
        esquemas.AssinaturaEspelhoRequisicao.model_validate(
            {"hashSha256": espelho_oficial.hash_sha256, "aceite": True}
        ),
        usuario_id=contexto_f10.colaborador_usuario_id,
        ip="203.0.113.99",
        user_agent="pytest-e2e-f10",
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert assinatura.status == "assinado"
    assert assinatura.hash_assinado == espelho_oficial.hash_sha256
    print(
        f"\n[9] assinarEspelho -> assinaturaId={assinatura.id} status={assinatura.status} "
        f"hashAssinado={assinatura.hash_assinado}"
    )

    verificado = await assinatura_servico.verificar_assinatura(sessao_f10, tenant_id, assinatura.id)
    assert verificado is True, "recomputar SHA256(conteudo) deveria bater com o hash assinado."
    print(f"    verificar_assinatura (recomputacao SHA256) -> {verificado}")

    # Criterio de aceite 8 (trilha de auditoria): `assinar_espelho` tambem
    # precisa gravar `gravar_auditoria(entidade="espelhos", acao="assinar")`
    # -- nenhum teste de `tests/f10/espelhos/test_assinatura.py` (A2) checa
    # isto diretamente; verificado aqui para fechar a prova do criterio.
    linha_auditoria_assinatura = (
        (
            await sessao_f10.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == tenant_id,
                    Auditoria.entidade == "espelhos",
                    Auditoria.acao == "assinar",
                    Auditoria.entidade_id == espelho_oficial.id,
                )
            )
        )
        .scalars()
        .one()
    )
    assert linha_auditoria_assinatura.usuario_id == contexto_f10.colaborador_usuario_id
    print(
        f"    auditoria(acao=assinar) -> usuarioId={linha_auditoria_assinatura.usuario_id} "
        f"entidadeId={linha_auditoria_assinatura.entidade_id}"
    )

    notificacoes_assinado = await _notificacoes(sessao_f10, tenant_id, evento="espelho.assinado")
    assert len(notificacoes_assinado) == 3
    for n in notificacoes_assinado:
        assert n.status == "pendente"
        print(_linha_relatorio("6-espelho.assinado (recem-criada)", n))

    # ==================================================================
    # PASSO 7 -- reabertura do periodo, com justificativa.
    # ==================================================================
    fechamento_antes_reabrir = await fechamento_servico.obter_fechamento(
        sessao_f10, tenant_id, fechamento_id
    )
    assert fechamento_antes_reabrir.status == "fechado"

    # Sem motivo: recusa com PONTO-PER-003 (prova do criterio de aceite 3,
    # metade "recusa sem motivo").
    with pytest.raises(ErroDeAplicacao) as excinfo_sem_motivo:
        await fechamento_servico.reabrir_fechamento(
            sessao_f10,
            tenant_id,
            fechamento_id,
            esquemas.ReaberturaRequisicao.model_validate({}),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo_sem_motivo.value.codigo == "PONTO-PER-003"
    print(f"\n[10] reabrirFechamento SEM motivo -> {excinfo_sem_motivo.value.codigo} (esperado)")

    fechamento_reaberto = await fechamento_servico.reabrir_fechamento(
        sessao_f10,
        tenant_id,
        fechamento_id,
        esquemas.ReaberturaRequisicao.model_validate(
            {
                "motivo": (
                    "Divergencia identificada na conferencia pos-fechamento: horario de saida "
                    "precisa ser revisado com o colaborador antes do espelho definitivo."
                )
            }
        ),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert fechamento_reaberto.status == "reaberto"
    print(f"[11] reabrirFechamento COM motivo -> status={fechamento_reaberto.status}")

    linhas_auditoria_reabrir = (
        (
            await sessao_f10.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == tenant_id,
                    Auditoria.entidade == "fechamentos",
                    Auditoria.acao == "reabrir",
                    Auditoria.entidade_id == fechamento_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_auditoria_reabrir) == 1, (
        "criterio de aceite 3: reabertura precisa gravar EXATAMENTE uma linha em auditoria "
        f"com acao='reabrir'; encontrado {len(linhas_auditoria_reabrir)}."
    )
    linha_reabrir = linhas_auditoria_reabrir[0]
    assert linha_reabrir.usuario_id == contexto_f10.rh_usuario_id
    assert linha_reabrir.valor_novo is not None and "motivo" in linha_reabrir.valor_novo
    print(
        f"     auditoria(acao=reabrir) -> usuarioId={linha_reabrir.usuario_id} "
        f"valorNovo={linha_reabrir.valor_novo}"
    )

    notificacoes_reaberto = await _notificacoes(
        sessao_f10, tenant_id, evento="periodo.reaberto", usuario_id=contexto_f10.rh_usuario_id
    )
    assert len(notificacoes_reaberto) == 3
    for n in notificacoes_reaberto:
        assert n.status == "pendente"
        print(_linha_relatorio("7-periodo.reaberto (recem-criada)", n))

    # ==================================================================
    # PASSO 8 -- novo espelho retificado, apos a reabertura.
    # ==================================================================
    periodo = await fechamento_servico.obter_periodo_do_tenant(
        sessao_f10, tenant_id, contexto_f10.periodo_id
    )
    espelho_retificado = await gerar_espelho_do_vinculo(
        sessao_f10,
        tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        fechamento_id=fechamento_id,
        gerar_pdf=True,
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    assert espelho_retificado.versao == 2
    assert espelho_retificado.tipo == "retificado"
    print(
        f"\n[12] Novo espelho retificado -> id={espelho_retificado.id} "
        f"versao={espelho_retificado.versao} tipo={espelho_retificado.tipo}"
    )

    espelhos_do_par = (
        (
            await sessao_f10.execute(
                sa.select(Espelho)
                .where(
                    Espelho.tenant_id == tenant_id,
                    Espelho.periodo_id == periodo.id,
                    Espelho.vinculo_id == contexto_f10.vinculo_id,
                )
                .order_by(Espelho.versao)
            )
        )
        .scalars()
        .all()
    )
    assert [e.versao for e in espelhos_do_par] == [1, 2], "versao=1 nao pode ter sido apagada."
    assert espelhos_do_par[0].tipo == "oficial"
    assert espelhos_do_par[1].tipo == "retificado"

    # ==================================================================
    # Drena a fila real de notificacoes (T11/A3) -- avanca todas as linhas
    # `pendente` desta corrida para `enviada` (ou `falhou`, honestamente,
    # se algo falhar) chamando o adaptador de canal de verdade.
    # ==================================================================
    from worker.tarefas.notificacoes import processar_fila_notificacoes

    resultado_fila = await processar_fila_notificacoes(
        {"job_id": "e2e-f10-notificacoes"}, tenant_id=str(tenant_id)
    )
    await aplicar_tenant_teste(sessao_f10, tenant_id)
    # `processar_fila_notificacoes` grava numa sessao PROPRIA (`app.db.
    # sessao`, producao real de worker) -- `sessao_f10` ainda tem as linhas
    # de `Notificacao` que os passos anteriores ja leram no identity map,
    # com o valor de ANTES do drenamento (`expire_on_commit=False` na
    # fixture, mesmo gotcha ja documentado por
    # `tests/f10/fechamento/test_worker_tarefas.py`). `expire_all` forca
    # reler tudo do banco na proxima consulta.
    sessao_f10.expire_all()
    print(f"\n[13] processar_fila_notificacoes (worker) -> {resultado_fila}")
    assert resultado_fila["encontradas"] == 15, (
        "5 transicoes x 3 canais = 15 notificacoes esperadas nesta corrida "
        f"(ajuste.solicitado, ajuste.aprovado, periodo.fechado, espelho.assinado, "
        f"periodo.reaberto); encontrado {resultado_fila['encontradas']}."
    )
    assert resultado_fila["enviadas"] == 15
    assert resultado_fila["falhadas"] == 0

    # ------------------------------------------------------------------
    # Relatorio final: TODA notificacao criada nesta corrida, na ordem de
    # criacao, com o status FINAL (depois da fila drenada) -- exigencia
    # literal do "pronto quando" de T15 ("a saida real e colada no
    # relatorio... mostrando, para cada transicao, a linha de notificacoes
    # criada e seu status final").
    # ------------------------------------------------------------------
    todas = (
        (
            await sessao_f10.execute(
                sa.select(Notificacao)
                .where(Notificacao.tenant_id == tenant_id)
                .order_by(Notificacao.criado_em, Notificacao.canal)
            )
        )
        .scalars()
        .all()
    )
    print(
        f"\n=== [14] RELATORIO FINAL -- {len(todas)} notificacoes desta corrida (status final) ==="
    )
    for n in todas:
        assert n.status == "enviada", f"notificacao {n.id} ({n.evento}/{n.canal}) nao foi enviada."
        assert n.enviada_em is not None
        assert n.provedor is not None
        print(
            f"  evento={n.evento!r:22s} canal={n.canal!r:8s} usuarioId={n.usuario_id} "
            f"status={n.status!r} provedor={n.provedor!r} enviadaEm={n.enviada_em}"
        )
    print("=== fim do relatorio de notificacoes -- T15 concluido ===\n")
