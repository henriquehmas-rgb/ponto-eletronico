"""Testes de integração do orquestrador do gerador de AEJ (T9, F12/A2).

Usa `contexto_f12`/`sessao_f12`/`gerar_marcacoes_reais` (A1, `tests/f12/
conftest.py`, compartilhada) e os helpers locais de `tests/f12/aej/
conftest.py` (horário/jornada, banco de horas). Chama `gerar_aej_arquivo`
diretamente (sem passar pela API HTTP nem pela fila do worker) -- mesmo
padrão que os testes de serviço de outras fases já usam para exercitar a
regra de negócio isolada da camada de transporte.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import garantir_bucket, obter_objeto
from app.core.erros import ErroDeAplicacao
from app.fiscal.aej.gerador import (
    CODIGO_FALHA_GERACAO,
    CODIGO_GERACAO_EM_ANDAMENTO,
    gerar_aej_arquivo,
    solicitar_geracao_aej,
    verificar_reconciliacao_banco_horas,
)
from app.schemas import contrato as esquemas
from tests.f12.aej.conftest import (
    lancar_banco_horas,
    semear_apuracao_dia,
    semear_banco_horas,
    semear_horario_jornada,
    semear_tratamento_desconsideracao,
    semear_tratamento_inclusao,
)
from tests.f12.conftest import ContextoF12, aplicar_tenant_teste, gerar_marcacoes_reais

pytestmark = pytest.mark.skipif(
    not os.environ.get("PONTO_TEST_DATABASE_URL"),
    reason="Requer PONTO_TEST_DATABASE_URL (Postgres real) e MINIO_* (MinIO real).",
)


def _fuso() -> dt.timezone:
    return dt.timezone(dt.timedelta(hours=-3))


async def _preparar_bucket() -> None:
    await garantir_bucket()


class TestEstruturaDoArquivo:
    """Criterio de aceite 1 (parcial, PCF §7): comparacao byte a byte contra
    o leiaute e alcancavel para o AEJ inteiro (T0 confirmou o leiaute com
    alta confianca) -- este teste monta um AEJ de fixture conhecida e
    confere posicao/campo manualmente."""

    @pytest.mark.asyncio
    async def test_arquivo_gerado_tem_estrutura_e_ordem_corretas(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        horario_id = await semear_horario_jornada(sessao_f12, contexto_f12)
        hoje = dt.datetime.now(tz=_fuso()).replace(hour=7, minute=55, second=0, microsecond=0)
        await semear_apuracao_dia(sessao_f12, contexto_f12, data=hoje.date(), horario_id=horario_id)
        await sessao_f12.commit()
        # `commit()` encerra a transacao onde `SET LOCAL app.tenant_id`
        # valia (RLS) -- reaplica antes de qualquer consulta seguinte,
        # senao ela enxerga zero linhas (nao erro, so devolve vazio).
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)
        await gerar_marcacoes_reais(
            sessao_f12,
            contexto_f12,
            quantidade=2,
            canal="terminal",
            inicio=hoje,
            intervalo=dt.timedelta(hours=8),
        )

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje.date(),
            fim=hoje.date(),
            incluir_banco_horas=False,
            assinar=False,
        )

        assert arquivo.status == "gerado"
        assert arquivo.hash_sha256 is not None
        assert arquivo.conteudo_ref is not None
        assert arquivo.total_vinculos == 1
        assert arquivo.total_marcacoes == 2

        conteudo = await obter_objeto(arquivo.conteudo_ref)
        # Regra 1/2 da secao 9 do leiaute: ISO-8859-1, linhas terminadas em
        # CR+LF, decodificavel sem erro.
        texto = conteudo.decode("iso-8859-1")
        assert texto.endswith("\r\n")
        assert "\n\n" not in texto  # sem linha em branco
        linhas = texto.split("\r\n")[:-1]  # ultimo elemento e "" apos o CRLF final

        tipos = [linha.split("|", 1)[0] for linha in linhas]
        assert tipos[0] == "01"
        assert tipos[-2] == "99"  # trailer
        # ultima linha (assinatura) nao tem "|", entao split("|",1)[0] e a
        # propria linha de 100 caracteres.
        assert tipos[-1].startswith("ASSINATURA_DIGITAL_EM_ARQUIVO_P7S")
        assert "02" in tipos  # REP-P utilizado
        assert "03" in tipos  # vinculo
        assert "04" in tipos  # horario contratual
        assert tipos.count("05") == 2  # as duas marcacoes viraram E/S

        trailer = linhas[tipos.index("99")].split("|")
        assert trailer[0] == "99"
        assert trailer[1] == "1"  # qtRegistrosTipo01
        assert trailer[5] == "2"  # qtRegistrosTipo05
        assert int(trailer[2]) == tipos.count("02")
        assert int(trailer[3]) == tipos.count("03")
        assert int(trailer[4]) == tipos.count("04")

    @pytest.mark.asyncio
    async def test_nome_arquivo_segue_convencao_do_pcf(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=False,
        )
        esperado = f"AEJ_{contexto_f12.empresa_cnpj}_{hoje:%Y%m%d}_{hoje:%Y%m%d}.txt"
        assert arquivo.nome_arquivo == esperado


class TestReconciliacaoBancoHoras:
    """Criterio de aceite 4 (PCF §7): AEJ contem banco de horas coerente com
    o extrato real de F4."""

    @pytest.mark.asyncio
    async def test_bloco_banco_horas_bate_com_extrato_real(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        bh_conta_id = await semear_banco_horas(
            sessao_f12, contexto_f12, periodo_inicio=hoje, periodo_fim=hoje + dt.timedelta(days=180)
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        await lancar_banco_horas(
            sessao_f12,
            contexto_f12,
            bh_conta_id,
            tipo="credito",
            minutos=120,
            data_competencia=hoje,
        )
        await lancar_banco_horas(
            sessao_f12,
            contexto_f12,
            bh_conta_id,
            tipo="debito",
            minutos=-30,
            data_competencia=hoje,
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=True,
            assinar=False,
        )

        assert arquivo.status == "gerado"
        assert arquivo.total_lancamentos_banco == 2
        assert arquivo.conteudo_ref is not None

        conteudo = await obter_objeto(arquivo.conteudo_ref)
        texto = conteudo.decode("iso-8859-1")
        linhas = texto.split("\r\n")[:-1]
        linhas_banco = [
            linha.split("|")
            for linha in linhas
            if linha.startswith("07|") and linha.split("|")[2] == "3"
        ]
        assert len(linhas_banco) == 2
        soma = sum(
            int(campos[4]) if campos[5] == "1" else -int(campos[4]) for campos in linhas_banco
        )
        assert soma == 120 - 30

    @pytest.mark.asyncio
    async def test_sem_conta_banco_horas_nao_gera_bloco(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=True,
            assinar=False,
        )
        assert arquivo.status == "gerado"
        assert arquivo.total_lancamentos_banco == 0


class TestReconciliacaoDivergenciaForcada:
    """`verificar_reconciliacao_banco_horas` isolada: no desenho atual, as
    duas somas vem do MESMO extrato de F4 (uma divergencia real so seria
    alcancavel por um defeito de transformacao interno a este modulo) --
    testada diretamente com valores adulterados, sem precisar manipular o
    banco para produzir uma divergencia artificial que o proprio desenho
    torna estruturalmente improvavel (ver docstring da funcao)."""

    def test_divergencia_levanta_ponto_fisc_006(self) -> None:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            verificar_reconciliacao_banco_horas(100, 90, vinculo_id=uuid.uuid4())
        assert excinfo.value.codigo == CODIGO_FALHA_GERACAO
        assert excinfo.value.codigo == "PONTO-FISC-006"

    def test_soma_igual_nao_levanta(self) -> None:
        verificar_reconciliacao_banco_horas(50, 50, vinculo_id=uuid.uuid4())


class TestGeracaoEmAndamento:
    """Criterio de aceite / PONTO-FISC-002: geracao ja em andamento para o
    mesmo periodo bloqueia uma segunda."""

    @pytest.mark.asyncio
    async def test_segunda_geracao_para_mesmo_periodo_e_recusada(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        from app.fiscal.aej.gerador import _verificar_geracao_em_andamento

        hoje = dt.date.today()
        await sessao_f12.execute(
            text(
                "INSERT INTO aej_arquivos "
                "(id, tenant_id, empresa_id, periodo_inicio, periodo_fim, nome_arquivo, "
                " ptrp_identificacao, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :inicio, :fim, 'teste.txt', "
                "        'SEEG Ponto', 'gerando')"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto_f12.tenant_id,
                "empresa_id": contexto_f12.empresa_id,
                "inicio": hoje,
                "fim": hoje,
            },
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        with pytest.raises(ErroDeAplicacao) as excinfo:
            await _verificar_geracao_em_andamento(
                sessao_f12, contexto_f12.tenant_id, contexto_f12.empresa_id, hoje, hoje
            )
        assert excinfo.value.codigo == CODIGO_GERACAO_EM_ANDAMENTO
        assert excinfo.value.codigo == "PONTO-FISC-002"


class TestAssinaturaSemCertificado:
    """Criterio de aceite 10 (PCF §7): sem certificado, `gerarAej` conclui
    com `status='gerado'`, nunca erro."""

    @pytest.mark.asyncio
    async def test_assinar_true_sem_certificado_conclui_sem_erro(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        # Ambiente de teste nao tem FISCAL_CERTIFICADO_PFX_PATH/CERT_ICP_PATH
        # configurado -- e o estado real de hoje (PCF F12 secao 2.4).
        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=True,
        )
        assert arquivo.status == "gerado"
        assert arquivo.status != "assinado"


class TestReaproveitamentoNuncaEscritaEmOutrasTabelas:
    """Criterio de aceite 7 (PCF §7): nenhuma linha desta fase escreve em
    marcacoes, apuracoes_dia, apuracao_componentes, bh_lancamentos,
    bh_contas, tratamentos -- prova por analise estatica (grep)."""

    def test_gerador_nunca_escreve_em_tabelas_de_outras_fases(self) -> None:
        import pathlib

        caminho = (
            pathlib.Path(__file__).resolve().parents[3] / "app" / "fiscal" / "aej" / "gerador.py"
        )
        codigo = caminho.read_text(encoding="utf-8")
        proibido = [
            "Marcacao(",
            "ApuracaoDia(",
            "ApuracaoComponente(",
            "BhLancamento(",
            "BhConta(",
            "Tratamento(",
        ]
        for termo in proibido:
            assert termo not in codigo, f"achado inesperado de escrita: {termo!r} em gerador.py"


class TestSolicitarGeracaoAej:
    """Metade sincrona (`solicitar_geracao_aej`, chamada pelo handler HTTP de
    `gerarAej`): validacao, criacao da linha de controle e enfileiramento
    real no Redis (`PONTO_TEST_REDIS_URL`)."""

    @pytest.mark.asyncio
    async def test_happy_path_cria_linha_e_enfileira(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        hoje = dt.date.today()
        dados = esquemas.AejCriar.model_validate(
            {
                "empresaId": str(contexto_f12.empresa_id),
                "periodoInicio": hoje.isoformat(),
                "periodoFim": hoje.isoformat(),
                "assinar": False,
            }
        )
        resposta = await solicitar_geracao_aej(
            sessao_f12,
            contexto_f12.tenant_id,
            dados,
            usuario_id=None,
            redis_url=os.environ["PONTO_TEST_REDIS_URL"],
        )
        assert resposta.status == "enfileirado"
        assert resposta.tipo == "aej"
        assert resposta.id is not None

        # A linha de controle foi criada e commitada (mesmo id devolvido).
        # `solicitar_geracao_aej` faz `commit()` internamente, encerrando a
        # transacao onde `SET LOCAL app.tenant_id` valia -- reaplica antes
        # de consultar de volta.
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)
        linha = await sessao_f12.execute(
            text("SELECT status, nome_arquivo FROM aej_arquivos WHERE id = :id"),
            {"id": resposta.id},
        )
        registro = linha.first()
        assert registro is not None
        assert registro.status == "gerando"

    @pytest.mark.asyncio
    async def test_com_periodo_id_resolve_datas_do_periodo(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        periodo_id = uuid.uuid4()
        inicio = dt.date.today().replace(day=1)
        fim = dt.date.today()
        await sessao_f12.execute(
            text(
                "INSERT INTO periodos "
                "(id, tenant_id, empresa_id, codigo, tipo, data_inicio, data_fim) "
                "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'mensal', :inicio, :fim)"
            ),
            {
                "id": periodo_id,
                "tenant_id": contexto_f12.tenant_id,
                "empresa_id": contexto_f12.empresa_id,
                "codigo": f"PER-{uuid.uuid4().hex[:8]}",
                "inicio": inicio,
                "fim": fim,
            },
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        dados = esquemas.AejCriar.model_validate(
            {"empresaId": str(contexto_f12.empresa_id), "periodoId": str(periodo_id)}
        )
        resposta = await solicitar_geracao_aej(
            sessao_f12,
            contexto_f12.tenant_id,
            dados,
            usuario_id=None,
            redis_url=os.environ["PONTO_TEST_REDIS_URL"],
        )
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)
        linha = await sessao_f12.execute(
            text("SELECT periodo_id, periodo_inicio, periodo_fim FROM aej_arquivos WHERE id = :id"),
            {"id": resposta.id},
        )
        registro = linha.first()
        assert registro is not None
        assert registro.periodo_id == periodo_id
        assert registro.periodo_inicio == inicio
        assert registro.periodo_fim == fim

    @pytest.mark.asyncio
    async def test_sem_empresa_id_e_corpo_invalido(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        dados = esquemas.AejCriar.model_validate({})
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await solicitar_geracao_aej(
                sessao_f12,
                contexto_f12.tenant_id,
                dados,
                usuario_id=None,
                redis_url=os.environ["PONTO_TEST_REDIS_URL"],
            )
        assert excinfo.value.codigo == "PONTO-VAL-001"

    @pytest.mark.asyncio
    async def test_sem_periodo_informado_e_corpo_invalido(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        dados = esquemas.AejCriar.model_validate({"empresaId": str(contexto_f12.empresa_id)})
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await solicitar_geracao_aej(
                sessao_f12,
                contexto_f12.tenant_id,
                dados,
                usuario_id=None,
                redis_url=os.environ["PONTO_TEST_REDIS_URL"],
            )
        assert excinfo.value.codigo == "PONTO-VAL-001"

    @pytest.mark.asyncio
    async def test_periodo_invertido_e_corpo_invalido(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        hoje = dt.date.today()
        dados = esquemas.AejCriar.model_validate(
            {
                "empresaId": str(contexto_f12.empresa_id),
                "periodoInicio": hoje.isoformat(),
                "periodoFim": (hoje - dt.timedelta(days=5)).isoformat(),
            }
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await solicitar_geracao_aej(
                sessao_f12,
                contexto_f12.tenant_id,
                dados,
                usuario_id=None,
                redis_url=os.environ["PONTO_TEST_REDIS_URL"],
            )
        assert excinfo.value.codigo == "PONTO-VAL-001"

    @pytest.mark.asyncio
    async def test_empresa_nao_encontrada_e_recurso_nao_encontrado(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        hoje = dt.date.today()
        dados = esquemas.AejCriar.model_validate(
            {
                "empresaId": str(uuid.uuid4()),
                "periodoInicio": hoje.isoformat(),
                "periodoFim": hoje.isoformat(),
            }
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await solicitar_geracao_aej(
                sessao_f12,
                contexto_f12.tenant_id,
                dados,
                usuario_id=None,
                redis_url=os.environ["PONTO_TEST_REDIS_URL"],
            )
        assert excinfo.value.codigo == "PONTO-REC-001"


class TestTratamentoNoAej:
    """PCF T8: fonteMarc distingue 'O' original de 'I' incluida
    manualmente; tpMarc='D' para desconsiderada -- o AEJ enxerga
    tratamento, o AFD nunca (§2.13)."""

    @pytest.mark.asyncio
    async def test_inclusao_manual_aparece_como_fonte_i(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.datetime.now(tz=_fuso()).replace(hour=8, minute=0, second=0, microsecond=0)
        await semear_tratamento_inclusao(
            sessao_f12,
            contexto_f12,
            data_referencia=hoje.date(),
            datahora_proposta=hoje,
            sentido="entrada",
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje.date(),
            fim=hoje.date(),
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.status == "gerado"
        assert arquivo.conteudo_ref is not None

        conteudo = await obter_objeto(arquivo.conteudo_ref)
        texto = conteudo.decode("iso-8859-1")
        linhas_05 = [linha for linha in texto.split("\r\n") if linha.startswith("05|")]
        assert len(linhas_05) == 1
        campos = linhas_05[0].split("|")
        assert campos[4] == "E"  # tpMarc
        assert campos[6] == "I"  # fonteMarc

    @pytest.mark.asyncio
    async def test_desconsideracao_aparece_como_tp_marc_d(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.datetime.now(tz=_fuso()).replace(hour=8, minute=0, second=0, microsecond=0)
        marcacoes = await gerar_marcacoes_reais(
            sessao_f12, contexto_f12, quantidade=1, canal="terminal", inicio=hoje
        )
        marcacao = marcacoes[0]
        await semear_tratamento_desconsideracao(
            sessao_f12,
            contexto_f12,
            data_referencia=hoje.date(),
            marcacao_id=marcacao.id,
            marcacao_datahora=marcacao.datahora_marcacao,
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje.date(),
            fim=hoje.date(),
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.status == "gerado"
        assert arquivo.total_marcacoes == 1
        assert arquivo.conteudo_ref is not None

        conteudo = await obter_objeto(arquivo.conteudo_ref)
        texto = conteudo.decode("iso-8859-1")
        linhas_05 = [linha for linha in texto.split("\r\n") if linha.startswith("05|")]
        assert len(linhas_05) == 1
        campos = linhas_05[0].split("|")
        assert campos[4] == "D"  # tpMarc
        assert campos[8] != ""  # motivo obrigatorio quando tpMarc=D


class TestAusenciasPorApuracaoDia:
    """Tipo '07' (ausencias): mapeamento de `apuracoes_dia.tipo_dia`/
    `falta_minutos` decidido por A2, ver docstring de
    `_montar_ausencias_do_vinculo`."""

    @pytest.mark.asyncio
    async def test_dsr_gera_tipo_ausen_1(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        await semear_apuracao_dia(sessao_f12, contexto_f12, data=hoje, tipo_dia="dsr")
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.total_ausencias == 1
        assert arquivo.conteudo_ref is not None
        texto = (await obter_objeto(arquivo.conteudo_ref)).decode("iso-8859-1")
        linhas_dsr = [
            linha
            for linha in texto.split("\r\n")
            if linha.startswith("07|") and linha.split("|")[2] == "1"
        ]
        assert len(linhas_dsr) == 1

    @pytest.mark.asyncio
    async def test_falta_nao_abonada_gera_tipo_ausen_2(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        await semear_apuracao_dia(
            sessao_f12, contexto_f12, data=hoje, tipo_dia="util", falta_minutos=480
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.total_ausencias == 1
        assert arquivo.conteudo_ref is not None
        texto = (await obter_objeto(arquivo.conteudo_ref)).decode("iso-8859-1")
        linhas_falta = [
            linha
            for linha in texto.split("\r\n")
            if linha.startswith("07|") and linha.split("|")[2] == "2"
        ]
        assert len(linhas_falta) == 1

    @pytest.mark.asyncio
    async def test_falta_abonada_nao_gera_ausencia(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        await semear_apuracao_dia(
            sessao_f12,
            contexto_f12,
            data=hoje,
            tipo_dia="util",
            falta_minutos=480,
            abono_minutos=480,
        )
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.total_ausencias == 0

    @pytest.mark.asyncio
    async def test_compensado_gera_tipo_ausen_4(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        hoje = dt.date.today()
        await semear_apuracao_dia(sessao_f12, contexto_f12, data=hoje, tipo_dia="compensado")
        await sessao_f12.commit()
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

        arquivo = await gerar_aej_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            empresa_id=contexto_f12.empresa_id,
            inicio=hoje,
            fim=hoje,
            incluir_banco_horas=False,
            assinar=False,
        )
        assert arquivo.total_ausencias == 1
        assert arquivo.conteudo_ref is not None
        texto = (await obter_objeto(arquivo.conteudo_ref)).decode("iso-8859-1")
        linhas_comp = [
            linha
            for linha in texto.split("\r\n")
            if linha.startswith("07|") and linha.split("|")[2] == "4"
        ]
        assert len(linhas_comp) == 1


class TestSemVinculosNoPeriodo:
    """Sem nenhum vinculo ativo no periodo (aqui: um periodo inteiramente
    ANTES da data de inicio do vinculo da fixture), a geracao falha com
    `PONTO-FISC-006` em vez de publicar um AEJ vazio/sem sentido."""

    @pytest.mark.asyncio
    async def test_periodo_sem_vinculo_ativo_falha_com_fisc_006(
        self, sessao_f12: AsyncSession, contexto_f12: ContextoF12
    ) -> None:
        await _preparar_bucket()
        # `contexto_f12.vinculo_id` comeca ha 365 dias; um periodo 1000 dias
        # atras fica inteiramente fora da janela do vinculo.
        data_remota = dt.date.today() - dt.timedelta(days=1000)
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await gerar_aej_arquivo(
                sessao_f12,
                contexto_f12.tenant_id,
                empresa_id=contexto_f12.empresa_id,
                inicio=data_remota,
                fim=data_remota,
                incluir_banco_horas=False,
                assinar=False,
            )
        assert excinfo.value.codigo == CODIGO_FALHA_GERACAO

        # `status` da linha de controle foi marcado 'falhou' e commitado
        # (nunca fica 'gerando' para sempre -- ver docstring de
        # `gerar_aej_arquivo` sobre `commit()` no caminho de erro).
        await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)
        linha = await sessao_f12.execute(
            text(
                "SELECT status FROM aej_arquivos "
                "WHERE tenant_id = :t AND empresa_id = :e AND periodo_inicio = :d"
            ),
            {"t": contexto_f12.tenant_id, "e": contexto_f12.empresa_id, "d": data_remota},
        )
        registro = linha.first()
        assert registro is not None
        assert registro.status == "falhou"


class TestFuncoesPurasSemBanco:
    """Unidades pequenas, sem banco: `_numero_inpi_para_nr_rep` e
    `_identificacao_ptrp` (caso sem REP-P)."""

    def test_numero_inpi_e_alinhado_a_17_digitos(self) -> None:
        from app.fiscal.aej.gerador import _numero_inpi_para_nr_rep

        assert _numero_inpi_para_nr_rep("12345678") == "00000000012345678"[-17:]
        assert len(_numero_inpi_para_nr_rep("12345678")) == 17
        assert len(_numero_inpi_para_nr_rep("1" * 20)) == 17

    def test_identificacao_ptrp_sem_rep_p_levanta_fisc_006(self) -> None:
        from app.fiscal.aej.gerador import _identificacao_ptrp

        with pytest.raises(ErroDeAplicacao) as excinfo:
            _identificacao_ptrp([])
        assert excinfo.value.codigo == CODIGO_FALHA_GERACAO
