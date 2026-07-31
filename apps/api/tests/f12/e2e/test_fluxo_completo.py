"""T13 -- e2e completo da fase F12 (A1+A2+A3, "conjunto") -- PCF
`docs/fases/F12-conformidade-rep-p.md` §6/T13, §7 (criterios 1, 4, 5, 6, 7,
8, 9, 10) e §8 (`pytest tests/f12/e2e -q -v`).

Percorre, numa unica cadeia continua sobre o banco real, exatamente a
sequencia que o PCF descreve:

1. Cadastra um REP-P novo (`app.fiscal.rep_p.servico.criar_rep_p`, T1/T7) --
   prova que `nsr_sequencias` nasce corretamente inicializada
   (`proximoNsr=1`). Este REP-P fica deliberadamente com
   `dataInicioOperacao` no futuro (nunca usado para gerar marcacao) so para
   nao competir com o REP-P da fixture compartilhada na consulta de REP-Ps
   ativos do AEJ (T8) -- o objetivo deste passo e provar o CRUD, nao gerar
   dado fiscal com ele.
2. Gera 20 marcacoes REAIS (`app.marcacao.dominio.registro.
   persistir_marcacao`, F5, via `gerar_marcacoes_reais` -- NUNCA `INSERT`
   direto) no REP-P da fixture compartilhada (`contexto_f12.rep_p_id`),
   NSR 1..20 sequencial e sem lacuna, incluindo a primeira `coletada_
   offline=true`.
3. Cria uma solicitacao -> aprovacao (1 etapa, papel `rh`) -> tratamento via
   F10 (`app.workflow.solicitacoes`/`app.workflow.aprovacoes`, que
   materializa um `Tratamento` categoria `inclusao_marcacao` via F4) -- para
   o AEJ ter algo de tratamento para exportar que o AFD nunca ve (§2.13).
4. Semeia jornada/apuracao/banco de horas (dado de F3/F4, leitura de F12,
   `INSERT`/`lancar()` reais via os helpers ja publicados por
   `tests/f12/aej/conftest.py`, A2) para o bloco tipo "04"/"07" do AEJ.
5. `gerar_afd_arquivo` (T6) -- prova tipos corretos, tamanho de registro
   exato por tipo, ordenado por NSR, sem lacuna, nenhum tratamento dentro.
6. `gerar_aej_arquivo` (T9) -- prova que o bloco de banco de horas bate com
   o extrato real de F4, e que o tratamento aparece (fonteMarc="I") so no
   AEJ, nunca no AFD.
7. `assinar_arquivo_fiscal` (T12) para os dois, com um certificado de teste
   autoassinado (nunca apresentado como ICP-Brasil real) -- prova `.p7s`
   estruturalmente valido (CMS/PKCS#7, CAdES-BES, verificado de forma
   independente com `app.fiscal.assinatura.cades.validar_cades`),
   `arquivo_assinaturas` gravado, `status` avancando para `assinado`.
8. `baixar_afd`/`obter_aej` (T12) -- prova que o conteudo devolvido bate
   byte a byte com o que foi gravado no armazenamento de objetos na geracao.

O teste do vetor de teste oficial do CRC-16 (T2, `tests/f12/afd/
test_crc16.py::test_vetor_oficial`) e o teste de lacuna de NSR impossivel de
produzir (T5, `tests/f12/afd/test_gerador.py`/`test_tipo7.py`) ja existem em
suas proprias tarefas -- este e2e NAO os duplica, so os referencia no
relatorio final da fase (PCF, "pronto quando" de T13).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import uuid
import zipfile
from uuid import UUID

import pytest
import sqlalchemy as sa
from ponto_contracts import (
    AejArquivo,
    AfdArquivo,
    Aprovacao,
    ArquivoAssinatura,
    Solicitacao,
    Tratamento,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.consulta import obter_extrato_banco_horas
from app.comum.armazenamento import obter_objeto
from app.fiscal.aej.gerador import gerar_aej_arquivo
from app.fiscal.afd.gerador import gerar_afd_arquivo
from app.fiscal.assinatura import servico as assinatura_servico
from app.fiscal.assinatura.cades import validar_cades
from app.fiscal.cofre import consulta as cofre_consulta
from app.fiscal.rep_p import servico as rep_p_servico
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes import servico as aprovacoes_servico
from app.workflow.solicitacoes import servico as solicitacoes_servico
from tests.f12.aej.conftest import (
    lancar_banco_horas,
    semear_banco_horas,
    semear_horario_jornada,
)
from tests.f12.assinatura.conftest import TITULAR_TESTE, _gerar_certificado_teste
from tests.f12.conftest import ContextoF12, aplicar_tenant_teste, gerar_marcacoes_reais

_FUSO = dt.timezone(dt.timedelta(hours=-3))


async def _criar_papel_rh(
    sessao: AsyncSession, contexto: ContextoF12, *, colaborador_alvo_id: UUID
) -> UUID:
    """Cria um colaborador/usuario "RH" e liga via `colaborador_gestores`
    (`tipo='rh'`) ao colaborador da fixture -- mesmo padrao de `tests/f10/
    e2e/test_fluxo_completo.py::_ligar_usuario_a_um_gestor`, copia local
    (esta fase nao importa fixtures de F10). Devolve `usuarios.id` do RH."""
    rotulo = uuid.uuid4().hex[:8]
    rh_colaborador_id = uuid.uuid4()
    await sessao.execute(
        sa.text(
            "INSERT INTO colaboradores (id, tenant_id, empresa_id, matricula, cpf, "
            "nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        {
            "id": rh_colaborador_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "matricula": f"RH-{rotulo}",
            "cpf": f"{uuid.uuid4().int % 10**11:011d}",
            "nome": "RH de Teste E2E F12",
        },
    )
    rh_usuario_id = uuid.uuid4()
    await sessao.execute(
        sa.text(
            "INSERT INTO usuarios (id, tenant_id, colaborador_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :email, 'Usuario RH de Teste E2E F12', "
            "'ativo')"
        ),
        {
            "id": rh_usuario_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": rh_colaborador_id,
            "email": f"rh-{rotulo}@f12e2e.teste",
        },
    )
    await sessao.execute(
        sa.text(
            "INSERT INTO colaborador_gestores "
            "(id, tenant_id, colaborador_id, gestor_colaborador_id, tipo, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :colaborador_id, :gestor_colaborador_id, 'rh', :inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto.tenant_id,
            "colaborador_id": colaborador_alvo_id,
            "gestor_colaborador_id": rh_colaborador_id,
            "inicio": dt.date(2020, 1, 1),
        },
    )
    return rh_usuario_id


def _linhas_do_arquivo(conteudo: bytes) -> list[str]:
    """Decodifica ISO-8859-1 e separa por CR+LF, descartando o terminador
    final (regra 2 do leiaute: toda linha termina em CR+LF, inclusive a
    ultima -- `montar_arquivo_texto`, `app.fiscal.comum.formatos`)."""
    texto = conteudo.decode("iso-8859-1")
    assert texto.endswith("\r\n"), "arquivo fiscal deveria terminar em CR+LF (regra 2 do leiaute)."
    linhas = texto.split("\r\n")
    assert linhas[-1] == ""
    return linhas[:-1]


@pytest.mark.asyncio
async def test_fluxo_completo_afd_aej_assinatura(
    sessao_f12: AsyncSession,
    contexto_f12: ContextoF12,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = contexto_f12.tenant_id
    print("\n=== T13 -- fluxo completo F12 (REP-P, AFD, AEJ, assinatura, cofre) ===")

    # ==================================================================
    # PASSO 1 -- cadastra um REP-P novo via `criarRepP` (T1/T7).
    # ==================================================================
    numero_inpi_novo = f"{uuid.uuid4().int % 10**12:012d}"
    rep_p_novo = await rep_p_servico.criar_rep_p(
        sessao_f12,
        tenant_id,
        esquemas.RepPCriar.model_validate(
            {
                "empresaId": str(contexto_f12.empresa_id),
                "identificador": f"REP-NOVO-{uuid.uuid4().hex[:8]}",
                "numeroInpi": numero_inpi_novo,
                "cnpjEmpregador": contexto_f12.empresa_cnpj,
                "razaoSocialEmpregador": contexto_f12.rep_p_razao_social_empregador,
                "versaoPrograma": "1.0.0-e2e",
                # Deliberadamente no futuro -- nunca usado para gerar marcacao
                # neste teste, so para provar o cadastro sem competir com o
                # REP-P da fixture na consulta de REP-Ps ativos do AEJ (T8).
                "dataInicioOperacao": (dt.date.today() + dt.timedelta(days=400)).isoformat(),
            }
        ),
        usuario_id=None,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert rep_p_novo.numero_inpi == numero_inpi_novo
    assert rep_p_novo.proximo_nsr == 1
    assert rep_p_novo.ultimo_nsr_emitido == 0
    print(
        f"\n[1] criarRepP -> id={rep_p_novo.id} identificador={rep_p_novo.identificador!r} "
        f"proximoNsr={rep_p_novo.proximo_nsr} ultimoNsrEmitido={rep_p_novo.ultimo_nsr_emitido}"
    )

    # ==================================================================
    # PASSO 2 -- 20 marcacoes REAIS (pipeline de F5), NSR 1..20 sequencial,
    # a primeira coletada offline.
    # ==================================================================
    dia_marcacoes = dt.date.today() - dt.timedelta(days=2)
    inicio_marcacoes = dt.datetime.combine(dia_marcacoes, dt.time(6, 0), tzinfo=_FUSO)

    # `contexto_f12.rep_p_id` (a fixture compartilhada de A1) nasce com
    # `data_inicio_operacao=hoje` -- empurra para o passado so que o AEJ
    # (T8, `_resolver_reps`: `data_inicio_operacao <= fim`) enxergue este
    # REP-P como "ja existente da empresa no periodo" pedido
    # (`dia_marcacoes`, no passado). Ajuste de massa de teste, nunca escrita
    # de producao -- mesmo espirito de `rep_ps`/`nsr_sequencias` semeados por
    # `INSERT` direto na propria fixture.
    await sessao_f12.execute(
        sa.text("UPDATE rep_ps SET data_inicio_operacao = :inicio WHERE id = :rep_p_id"),
        {"inicio": dt.date(2020, 1, 1), "rep_p_id": contexto_f12.rep_p_id},
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)

    marcacao_offline = await gerar_marcacoes_reais(
        sessao_f12,
        contexto_f12,
        quantidade=1,
        canal="terminal",
        coletada_offline=True,
        inicio=inicio_marcacoes,
    )
    marcacoes_online = await gerar_marcacoes_reais(
        sessao_f12,
        contexto_f12,
        quantidade=19,
        canal="terminal",
        coletada_offline=False,
        inicio=inicio_marcacoes + dt.timedelta(minutes=30),
    )
    todas_marcacoes = [*marcacao_offline, *marcacoes_online]
    assert len(todas_marcacoes) == 20
    assert [m.nsr for m in todas_marcacoes] == list(
        range(1, 21)
    ), "NSR precisa ser 1..20 sem lacuna."
    assert todas_marcacoes[0].coletada_offline is True
    assert all(not m.coletada_offline for m in todas_marcacoes[1:])
    print(
        f"\n[2] {len(todas_marcacoes)} marcacoes reais geradas via persistir_marcacao (F5) -- "
        f"NSR {todas_marcacoes[0].nsr}..{todas_marcacoes[-1].nsr}, "
        f"1a offline={todas_marcacoes[0].coletada_offline}"
    )

    # Jornada semeada ANTES do tratamento (dado de F3, leitura de F12, para
    # o bloco tipo "04" do AEJ): `decidir_aprovacao` -> `decidir_tratamento`
    # (F4) reagenda `recalcular_periodo` sozinho (mesmo achado documentado
    # por `tests/f10/e2e/test_fluxo_completo.py`), que grava a linha REAL de
    # `apuracoes_dia` do dia -- semear a jornada antes garante que essa linha
    # real ja nasce com `horario_id` associado, sem precisar de um segundo
    # `INSERT` de fixture em cima (que colidiria com a UNIQUE de
    # `apuracoes_dia`, achado real desta sessao).
    horario_id = await semear_horario_jornada(
        sessao_f12,
        contexto_f12,
        entrada=dt.time(6, 0),
        saida=dt.time(15, 30),
        intervalo_inicio=dt.time(11, 0),
        intervalo_fim=dt.time(12, 0),
        carga_minutos=480,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)

    # ==================================================================
    # PASSO 3 -- solicitacao -> aprovacao (1 etapa, papel 'rh') -> tratamento
    # via F10, materializando um Tratamento real (F4) que o AEJ precisa ver
    # e o AFD nunca ve.
    # ==================================================================
    colaborador_usuario_id = uuid.uuid4()
    await sessao_f12.execute(
        sa.text(
            "INSERT INTO usuarios (id, tenant_id, colaborador_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :email, 'Colaborador de Teste E2E F12', "
            "'ativo')"
        ),
        {
            "id": colaborador_usuario_id,
            "tenant_id": tenant_id,
            "colaborador_id": contexto_f12.colaborador_id,
            "email": f"colab-{uuid.uuid4().hex[:8]}@f12e2e.teste",
        },
    )
    rh_usuario_id = await _criar_papel_rh(
        sessao_f12, contexto_f12, colaborador_alvo_id=contexto_f12.colaborador_id
    )

    tipo_tratamento_id = uuid.uuid4()
    await sessao_f12.execute(
        sa.text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, exige_motivo, "
            " afeta_afd, afeta_aej, permite_retroativo_dias, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Inclusao manual e2e F12', 'inclusao_marcacao', "
            "        TRUE, TRUE, FALSE, TRUE, 30, TRUE)"
        ),
        {
            "id": tipo_tratamento_id,
            "tenant_id": tenant_id,
            "codigo": f"INCL-E2E-{uuid.uuid4().hex[:8]}",
        },
    )
    tipo_solicitacao_id = uuid.uuid4()
    await sessao_f12.execute(
        sa.text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, prazo_resposta_horas, "
            " escalonar_apos_horas, exige_anexo, exige_justificativa, "
            " permite_retroativo_dias, tipo_tratamento_id, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Ajuste de ponto e2e F12', 'ajuste_ponto', "
            "        :etapas, 48, 72, FALSE, TRUE, 30, :tipo_tratamento_id, TRUE)"
        ),
        {
            "id": tipo_solicitacao_id,
            "tenant_id": tenant_id,
            "codigo": f"AJUSTE-E2E-{uuid.uuid4().hex[:8]}",
            "etapas": '[{"etapa": 1, "papel": "rh"}]',
            "tipo_tratamento_id": tipo_tratamento_id,
        },
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)

    datahora_saida_proposta = dt.datetime.combine(dia_marcacoes, dt.time(16, 0), tzinfo=_FUSO)
    corpo_solicitacao = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(tipo_solicitacao_id),
            "colaboradorId": str(contexto_f12.colaborador_id),
            "dataReferencia": dia_marcacoes.isoformat(),
            "descricao": "Inclusao manual da saida esquecida -- e2e F12 T13.",
            "payload": {
                "datahoraProposta": datahora_saida_proposta.isoformat(),
                "sentido": "saida",
            },
        }
    )
    solicitacao = await solicitacoes_servico.criar_solicitacao(
        sessao_f12, tenant_id, corpo_solicitacao, usuario_id=colaborador_usuario_id
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    print(
        f"\n[3] criarSolicitacao -> protocolo={solicitacao.protocolo} status={solicitacao.status}"
    )

    etapa1 = (
        (
            await sessao_f12.execute(
                sa.select(Aprovacao).where(
                    Aprovacao.tenant_id == tenant_id,
                    Aprovacao.solicitacao_id == solicitacao.id,
                    Aprovacao.etapa == 1,
                )
            )
        )
        .scalars()
        .one()
    )
    assert etapa1.papel == "rh"
    assert etapa1.aprovador_usuario_id == rh_usuario_id

    etapa1_decidida = await aprovacoes_servico.decidir_aprovacao(
        sessao_f12,
        tenant_id,
        etapa1.id,
        esquemas.DecisaoRequisicao.model_validate(
            {"decisao": "aprovar", "comentario": "Aprovado pelo RH -- e2e F12 T13."}
        ),
        usuario_id=rh_usuario_id,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert etapa1_decidida.decisao == "aprovada"

    tratamento = (
        (
            await sessao_f12.execute(
                sa.select(Tratamento).where(
                    Tratamento.tenant_id == tenant_id, Tratamento.solicitacao_id == solicitacao.id
                )
            )
        )
        .scalars()
        .one()
    )
    assert tratamento.status in ("aprovado", "aplicado")
    solicitacao_final = (
        (await sessao_f12.execute(sa.select(Solicitacao).where(Solicitacao.id == solicitacao.id)))
        .scalars()
        .one()
    )
    assert solicitacao_final.status == "aprovada"
    print(
        f"    decidirAprovacao (RH, 1 etapa) -> decisao={etapa1_decidida.decisao} | "
        f"Tratamento materializado -> id={tratamento.id} status={tratamento.status} "
        f"categoria=inclusao_marcacao datahoraProposta={tratamento.datahora_proposta}"
    )

    # ==================================================================
    # PASSO 4 -- banco de horas (dado de F4, leitura de F12) para o bloco
    # tipo "07" do AEJ. `apuracoes_dia` (bloco tipo "04"/ausencias) ja foi
    # gravada de verdade por F4 dentro do PASSO 3 (recalculo automatico ao
    # aprovar o tratamento) -- confirmado abaixo por leitura direta.
    # ==================================================================
    apuracao_real = (
        await sessao_f12.execute(
            sa.text(
                "SELECT horario_id, tipo_dia FROM apuracoes_dia "
                "WHERE tenant_id = :tenant_id AND vinculo_id = :vinculo_id AND data = :data"
            ),
            {
                "tenant_id": tenant_id,
                "vinculo_id": contexto_f12.vinculo_id,
                "data": dia_marcacoes,
            },
        )
    ).one()
    assert apuracao_real.horario_id == horario_id, (
        "apuracoes_dia real (gravada por F4 ao aprovar o tratamento) precisa ter o horario_id "
        "da jornada semeada -- senao o bloco tipo 04 do AEJ nao teria o que exportar."
    )
    print(
        f"\n[4a] apuracoes_dia REAL (gravada por F4 dentro de decidir_tratamento, nao por fixture) "
        f"-> horarioId={apuracao_real.horario_id} tipoDia={apuracao_real.tipo_dia!r}"
    )

    bh_conta_id = await semear_banco_horas(
        sessao_f12,
        contexto_f12,
        periodo_inicio=dia_marcacoes,
        periodo_fim=dia_marcacoes + dt.timedelta(days=30),
    )
    await lancar_banco_horas(
        sessao_f12,
        contexto_f12,
        bh_conta_id,
        tipo="credito",
        minutos=60,
        data_competencia=dia_marcacoes,
        descricao="Credito de teste -- e2e F12 T13",
    )
    await lancar_banco_horas(
        sessao_f12,
        contexto_f12,
        bh_conta_id,
        tipo="debito",
        # `minutos` negativo e quem determina "debito" (o sinal de
        # `minutos_equivalentes` = sinal de `minutos`, `app.apuracao.
        # banco_horas.lancamentos.lancar` -- `tipo` e so metadado
        # descritivo, achado real desta sessao).
        minutos=-20,
        data_competencia=dia_marcacoes,
        descricao="Debito de teste -- e2e F12 T13",
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    print(
        f"\n[4b] Banco de horas semeado -- bhContaId={bh_conta_id} "
        "(credito 60min, debito 20min, saldo liquido +40min)"
    )

    # ==================================================================
    # PASSO 5 -- gerarAfd (T6): deriva EXCLUSIVAMENTE das marcacoes.
    # ==================================================================
    afd_arquivos = await gerar_afd_arquivo(
        sessao_f12,
        tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=dia_marcacoes,
        fim=dia_marcacoes,
        assinar=False,
        solicitante_id=rh_usuario_id,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert len(afd_arquivos) == 1, "sem fracionamento pedido, deveria gerar exatamente 1 AFD."
    afd = afd_arquivos[0]
    assert afd.status == "gerado"
    assert afd.nsr_inicial == 1
    assert afd.nsr_final == 20
    assert afd.total_registros == 23  # 1 cabecalho + 20 tipo7 + 1 trailer + 1 assinatura

    conteudo_afd = await obter_objeto(afd.conteudo_ref)
    assert hashlib.sha256(conteudo_afd).hexdigest() == afd.hash_sha256
    assert len(conteudo_afd) == afd.tamanho_bytes
    linhas_afd = _linhas_do_arquivo(conteudo_afd)
    assert len(linhas_afd) == 23

    cabecalho_afd = linhas_afd[0]
    assert len(cabecalho_afd) == 302, "tipo 1 (cabecalho) precisa ter 302 caracteres exatos."
    assert cabecalho_afd[9] == "1", "posicao 10 (indice 9) e o tipo do registro do cabecalho."

    linhas_tipo7 = linhas_afd[1:21]
    for linha in linhas_tipo7:
        assert len(linha) == 137, "tipo 7 (marcacao REP-P) precisa ter 137 caracteres exatos."
        assert linha[9] == "7", "posicao 10 (indice 9) e o tipo do registro do tipo 7."
    nsrs_afd = [int(linha[0:9]) for linha in linhas_tipo7]
    assert nsrs_afd == list(range(1, 21)), "AFD precisa estar ordenado por NSR, 1..20, sem lacuna."

    trailer_afd = linhas_afd[21]
    assert len(trailer_afd) == 64, "tipo 9 (trailer) precisa ter 64 caracteres exatos."
    assert trailer_afd.startswith("999999999")

    linha_assinatura_afd = linhas_afd[22]
    assert len(linha_assinatura_afd) == 100
    assert linha_assinatura_afd.startswith("ASSINATURA_DIGITAL_EM_ARQUIVO_P7S")

    # Critério "tratamento nunca aparece no AFD": nenhuma das 20 linhas tipo 7
    # tem o horario 16:00 (o horario da saida incluida manualmente por
    # tratamento no passo 3) -- o AFD deriva exclusivamente de `marcacoes`,
    # que nunca recebeu essa linha (tratamento nao escreve em `marcacoes`).
    assert nsrs_afd == [
        m.nsr for m in todas_marcacoes
    ], "AFD contem exatamente as 20 marcacoes reais, nada mais."
    print(
        f"\n[5] gerarAfd -> arquivoId={afd.id} status={afd.status} nome={afd.nome_arquivo} "
        f"nsr={afd.nsr_inicial}..{afd.nsr_final} totalRegistros={afd.total_registros} "
        f"hashSha256={afd.hash_sha256}"
    )
    print(
        "    23 linhas: tipo1(302) + 20x tipo7(137, NSR 1..20 sem lacuna) + "
        "tipo9(64) + assinatura(100)"
    )

    # ==================================================================
    # PASSO 6 -- gerarAej (T9): enxerga tratamento, jornada, banco de horas.
    # ==================================================================
    aej = await gerar_aej_arquivo(
        sessao_f12,
        tenant_id,
        empresa_id=contexto_f12.empresa_id,
        inicio=dia_marcacoes,
        fim=dia_marcacoes,
        incluir_banco_horas=True,
        assinar=False,
        solicitante_id=rh_usuario_id,
    )
    await aplicar_tenant_teste(sessao_f12, tenant_id)  # gerar_aej_arquivo ja commita internamente
    assert aej.status == "gerado"
    assert aej.total_vinculos == 1
    # 20 marcacoes reais pareadas + a inclusao manual do tratamento (fonteMarc="I")
    assert (
        aej.total_marcacoes == 21
    ), f"esperado 20 marcacoes reais + 1 inclusao manual = 21; encontrado {aej.total_marcacoes}."
    assert aej.total_lancamentos_banco == 2, "credito + debito lancados no passo 4."

    conteudo_aej = await obter_objeto(aej.conteudo_ref)
    assert hashlib.sha256(conteudo_aej).hexdigest() == aej.hash_sha256
    linhas_aej = _linhas_do_arquivo(conteudo_aej)

    linhas_tipo05 = [linha for linha in linhas_aej if linha.split("|")[0] == "05"]
    assert len(linhas_tipo05) == 21
    fontes = [linha.split("|")[6] for linha in linhas_tipo05]
    assert fontes.count("O") == 20, "as 20 marcacoes reais precisam ter fonteMarc='O'."
    assert fontes.count("I") == 1, (
        "a inclusao manual (tratamento) precisa aparecer com fonteMarc='I' -- "
        "so no AEJ, nunca no AFD."
    )

    linhas_tipo07 = [linha for linha in linhas_aej if linha.split("|")[0] == "07"]
    linhas_banco_horas = [
        linha
        for linha in linhas_tipo07
        if linha.split("|")[2] == "3"  # tipoAusenOuComp="3"
    ]
    assert len(linhas_banco_horas) == 2
    soma_exportada_aej = 0
    for linha in linhas_banco_horas:
        campos = linha.split("|")
        qt_minutos = int(campos[4])
        tipo_mov = campos[5]
        soma_exportada_aej += qt_minutos if tipo_mov == "1" else -qt_minutos

    extrato = await obter_extrato_banco_horas(
        sessao_f12,
        tenant_id,
        contexto_f12.colaborador_id,
        vinculo_id=contexto_f12.vinculo_id,
        conta_id=bh_conta_id,
        de=dia_marcacoes,
        ate=dia_marcacoes,
        cursor=None,
        limite=200,
    )
    assert extrato.lancamentos is not None
    soma_extrato = sum(lanc.minutos_equivalentes or 0 for lanc in extrato.lancamentos)
    assert soma_exportada_aej == soma_extrato == 40, (
        "criterio de aceite 4: bloco de banco de horas do AEJ precisa bater EXATAMENTE com o "
        f"extrato real de F4; exportado={soma_exportada_aej}, extrato={soma_extrato}."
    )

    print(
        f"\n[6] gerarAej -> arquivoId={aej.id} status={aej.status} nome={aej.nome_arquivo} "
        f"totalVinculos={aej.total_vinculos} totalMarcacoes={aej.total_marcacoes} "
        f"totalLancamentosBanco={aej.total_lancamentos_banco} hashSha256={aej.hash_sha256}"
    )
    print(
        f"    Bloco tipo 05: {fontes.count('O')}x fonteMarc='O' (marcacao real) + "
        f"{fontes.count('I')}x fonteMarc='I' (inclusao manual/tratamento) -- "
        f"tratamento aparece SO no AEJ, nunca no AFD (confirmado no passo 5)."
    )
    print(
        f"    Bloco tipo 07 (banco de horas): exportado={soma_exportada_aej}min == "
        f"extrato real de F4={soma_extrato}min -- reconciliacao exata (criterio de aceite 4)."
    )

    # ==================================================================
    # PASSO 7 -- assinarArquivoFiscal (T12) para AFD e AEJ, com certificado
    # de teste AUTOASSINADO (rotulado como tal, nunca ICP-Brasil real).
    # ==================================================================
    certificado_teste = _gerar_certificado_teste(
        titular=TITULAR_TESTE, dias_validade_inicio=-1, dias_validade_fim=365
    )
    monkeypatch.setattr(
        assinatura_servico, "obter_certificado_configurado", lambda: certificado_teste
    )

    assinatura_afd = await assinatura_servico.assinar_arquivo_fiscal(
        sessao_f12,
        tenant_id,
        afd.id,
        esquemas.AssinaturaArquivoRequisicao.model_validate(
            {"tipoArquivo": "afd", "padrao": "CAdES", "formato": "detached"}
        ),
        usuario_id=rh_usuario_id,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert assinatura_afd.status == "assinado"
    assert assinatura_afd.padrao == "CAdES"
    assert assinatura_afd.formato == "detached"

    assinatura_aej = await assinatura_servico.assinar_arquivo_fiscal(
        sessao_f12,
        tenant_id,
        aej.id,
        esquemas.AssinaturaArquivoRequisicao.model_validate(
            {"tipoArquivo": "aej", "padrao": "CAdES", "formato": "detached"}
        ),
        usuario_id=rh_usuario_id,
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert assinatura_aej.status == "assinado"

    # `arquivo_assinaturas` gravado -- confirma por leitura direta da tabela.
    linhas_assinatura_bd = (
        (
            await sessao_f12.execute(
                sa.select(ArquivoAssinatura).where(
                    ArquivoAssinatura.tenant_id == tenant_id,
                    ArquivoAssinatura.arquivo_id.in_([afd.id, aej.id]),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_assinatura_bd) == 2

    # `status` avancou de 'gerado' para 'assinado' nas proprias linhas de
    # afd_arquivos/aej_arquivos.
    afd_recarregado = await sessao_f12.get(AfdArquivo, afd.id)
    aej_recarregado = await sessao_f12.get(AejArquivo, aej.id)
    assert afd_recarregado is not None and afd_recarregado.status == "assinado"
    assert aej_recarregado is not None and aej_recarregado.status == "assinado"

    # `.p7s` estruturalmente valido -- verificacao INDEPENDENTE (nao
    # reaproveita nenhum estado interno de assinar_arquivo_fiscal, que ja fez
    # sua propria autoverificacao antes de gravar -- aqui e uma segunda
    # verificacao, do zero, a partir dos bytes persistidos no armazenamento).
    p7s_afd = await obter_objeto(assinatura_afd.assinatura_ref)
    resultado_validacao_afd = validar_cades(conteudo_afd, p7s_afd)
    assert resultado_validacao_afd.estruturalmente_valido is True
    assert resultado_validacao_afd.message_digest_confere is True
    assert resultado_validacao_afd.assinatura_criptografica_valida is True
    assert resultado_validacao_afd.certificado_dentro_da_validade is True
    assert resultado_validacao_afd.cadeia_confianca_icp_brasil_verificada is False, (
        "NAO verificavel nesta fase -- nao ha certificado e-CNPJ A1 real da SEEG "
        "(ADR-012/PCF §2.4)."
    )

    p7s_aej = await obter_objeto(assinatura_aej.assinatura_ref)
    resultado_validacao_aej = validar_cades(conteudo_aej, p7s_aej)
    assert resultado_validacao_aej.valido is True

    print(
        f"\n[7] assinarArquivoFiscal(afd) -> assinaturaId={assinatura_afd.id} "
        f"status={assinatura_afd.status} certificadoTitular={assinatura_afd.certificado_titular!r} "
        f"(TESTE, nao ICP-Brasil real)"
    )
    print(
        f"    assinarArquivoFiscal(aej) -> assinaturaId={assinatura_aej.id} "
        f"status={assinatura_aej.status}"
    )
    print(
        f"    .p7s AFD -- validacao INDEPENDENTE (asn1crypto, fora de assinar_arquivo_fiscal): "
        f"estruturalmenteValido={resultado_validacao_afd.estruturalmente_valido} "
        f"messageDigestConfere={resultado_validacao_afd.message_digest_confere} "
        f"assinaturaCriptograficaValida={resultado_validacao_afd.assinatura_criptografica_valida} "
        f"certificadoDentroDaValidade={resultado_validacao_afd.certificado_dentro_da_validade} "
        "cadeiaConfiancaIcpBrasilVerificada="
        f"{resultado_validacao_afd.cadeia_confianca_icp_brasil_verificada} "
        "(NAO verificavel -- sem certificado ICP-Brasil real, ver ADR-012/PCF §2.4/criterio 3)"
    )
    print(f"    .p7s AEJ -- validacao INDEPENDENTE: valido={resultado_validacao_aej.valido}")

    # ==================================================================
    # PASSO 8 -- baixarAfd/obterAej: conteudo bate byte a byte com o que foi
    # gravado na geracao (passos 5/6).
    # ==================================================================
    baixado_afd, content_type_afd, nome_afd = await cofre_consulta.baixar_afd(
        sessao_f12,
        tenant_id,
        afd.id,
        incluir_assinatura=False,
        usuario_id=rh_usuario_id,
        ip="203.0.113.10",
        user_agent="pytest-e2e-f12",
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert (
        baixado_afd == conteudo_afd
    ), "baixarAfd precisa devolver os MESMOS bytes gravados na geracao."
    assert content_type_afd == "text/plain; charset=iso-8859-1"
    assert nome_afd == afd.nome_arquivo

    baixado_afd_com_assinatura, content_type_zip, nome_zip = await cofre_consulta.baixar_afd(
        sessao_f12,
        tenant_id,
        afd.id,
        incluir_assinatura=True,
        usuario_id=rh_usuario_id,
        ip="203.0.113.10",
        user_agent="pytest-e2e-f12",
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)
    assert content_type_zip == "application/zip"
    assert nome_zip.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(baixado_afd_com_assinatura)) as pacote:
        assert set(pacote.namelist()) == {afd.nome_arquivo, f"{afd.nome_arquivo}.p7s"}
        assert pacote.read(afd.nome_arquivo) == conteudo_afd
        assert pacote.read(f"{afd.nome_arquivo}.p7s") == p7s_afd

    # `obterAej`: o contrato NAO define download bruto de AEJ (so AFD tem
    # `/download`, confirmado em `app.fiscal.cofre.consulta`, docstring do
    # modulo) -- a prova "byte a byte" para o AEJ le o MESMO objeto que
    # qualquer consumidor real leria (o armazenamento apontado por
    # `conteudoRef`), e `obterAej` (metadados) confirma o estado final.
    aej_obtido = await cofre_consulta.obter_aej(sessao_f12, tenant_id, aej.id)
    assert aej_obtido.status == "assinado"
    assert aej_obtido.hash_sha256 == aej.hash_sha256
    reobtido_conteudo_aej = await obter_objeto(aej_obtido.conteudo_ref)
    assert reobtido_conteudo_aej == conteudo_aej

    afd_obtido = await cofre_consulta.obter_afd(sessao_f12, tenant_id, afd.id)
    assert afd_obtido.status == "assinado"
    assert afd_obtido.hash_sha256 == afd.hash_sha256

    print(
        f"\n[8] baixarAfd(incluirAssinatura=False) -> {len(baixado_afd)} bytes, "
        f"identico byte a byte ao conteudo gravado na geracao (passo 5)."
    )
    print(
        f"    baixarAfd(incluirAssinatura=True) -> pacote .zip com {afd.nome_arquivo} + "
        f".p7s, ambos identicos byte a byte."
    )
    print(
        f"    obterAej -> status={aej_obtido.status}; leitura direta do armazenamento "
        f"(conteudoRef) -> {len(reobtido_conteudo_aej)} bytes, identico byte a byte ao "
        "conteudo gravado na geracao (passo 6). AEJ nao tem endpoint de download bruto no "
        "contrato -- so AFD tem (confirmado em app.fiscal.cofre.consulta)."
    )
    print(
        "\n=== T13 concluido: REP-P -> marcacoes -> tratamento -> AFD -> AEJ -> "
        "assinatura -> cofre ===\n"
    )
