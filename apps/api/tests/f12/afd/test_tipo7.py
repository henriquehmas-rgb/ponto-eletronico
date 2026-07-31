"""T5 -- registro tipo "7" do AFD e verificação prévia de continuidade de
NSR.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from ponto_contracts import AfdArquivo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.fiscal.afd.tipo7 import (
    CODIGO_COLETOR_POR_CANAL,
    montar_registro_tipo7,
    montar_registros_tipo7,
)
from tests.f12.conftest import ContextoF12, aplicar_tenant_teste, gerar_marcacoes_reais

_FUSO = dt.timezone(dt.timedelta(hours=-3))


def test_registro_tipo7_tem_137_caracteres() -> None:
    registro = montar_registro_tipo7(
        nsr=1,
        cpf="12345678901",
        datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
        canal="terminal",
        coletada_offline=False,
        hash_anterior=None,
    )
    assert len(registro.linha) == 137


def test_registro_tipo7_campo_2_e_alfanumerico_nao_numerico() -> None:
    """`docs/leiaute-afd-aej.md` §7: campo 2 (tipo do registro) do tipo "7"
    e tipo A na fonte, nao N -- ainda que o conteudo seja um digito."""
    registro = montar_registro_tipo7(
        nsr=1,
        cpf="12345678901",
        datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
        canal="terminal",
        coletada_offline=False,
        hash_anterior=None,
    )
    assert registro.linha[9:10] == "7"


@pytest.mark.parametrize(
    "canal,codigo_esperado",
    [("mobile", "01"), ("web", "02"), ("terminal", "04"), ("totem", "04"), ("api", "05")],
)
def test_mapeamento_canal_para_codigo_coletor(canal: str, codigo_esperado: str) -> None:
    """Mapeamento FIXADO pelo PCF F12 §6/T5 -- nao invente outro."""
    assert CODIGO_COLETOR_POR_CANAL[canal] == codigo_esperado
    registro = montar_registro_tipo7(
        nsr=1,
        cpf="12345678901",
        datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
        canal=canal,
        coletada_offline=False,
        hash_anterior=None,
    )
    assert registro.linha[70:72] == codigo_esperado


def test_canal_importacao_levanta_erro_em_vez_de_adivinhar() -> None:
    with pytest.raises(ValueError, match="importacao"):
        montar_registro_tipo7(
            nsr=1,
            cpf="12345678901",
            datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
            datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
            canal="importacao",
            coletada_offline=False,
            hash_anterior=None,
        )


def test_offline_true_grava_indicador_1() -> None:
    registro = montar_registro_tipo7(
        nsr=1,
        cpf="12345678901",
        datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
        canal="mobile",
        coletada_offline=True,
        hash_anterior=None,
    )
    assert registro.linha[72:73] == "1"


def test_offline_false_grava_indicador_0() -> None:
    registro = montar_registro_tipo7(
        nsr=1,
        cpf="12345678901",
        datahora_marcacao=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        datahora_gravacao=dt.datetime(2026, 7, 1, 8, 0, 1, tzinfo=_FUSO),
        canal="mobile",
        coletada_offline=False,
        hash_anterior=None,
    )
    assert registro.linha[72:73] == "0"


@pytest.mark.asyncio
async def test_montar_registros_tipo7_encadeia_hash_e_verifica_continuidade(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    marcacoes = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=5)
    assert [m.nsr for m in marcacoes] == list(range(1, 6))

    registros = await montar_registros_tipo7(
        sessao_f12,
        tenant_id=contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        marcacoes=marcacoes,
    )

    assert len(registros) == 5
    assert [r.nsr for r in registros] == [1, 2, 3, 4, 5]
    # Cada linha traz o hash do proprio registro no campo 8 (ultimos 64 caracteres).
    for registro in registros:
        assert registro.linha[-64:] == registro.hash_registro
    # Encadeamento: o campo 8 do segundo registro embute (parte da entrada
    # de) o hash do primeiro -- provado indiretamente pela determinacao de
    # que dois registros com o mesmo conteudo de campos 1-7 mas hash
    # anterior diferente produzem hash_registro diferente (ver
    # tests/f12/afd/test_hash_tipo7.py) -- aqui confirmamos que os hashes
    # da cadeia real sao todos distintos entre si.
    assert len({r.hash_registro for r in registros}) == 5


@pytest.mark.asyncio
async def test_segunda_chamada_encadeia_a_partir_do_hash_real_anterior(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Achado de correção (não cosmético): o ADR-012 diz que só o primeiro
    registro tipo "7" da SEQUÊNCIA DO REP-P (a vida inteira, não desta
    chamada) omite o 8º insumo. Gerar um "segundo AFD" para o mesmo REP-P
    (marcações de NSR 6..8, depois de NSR 1..5 já existirem) precisa
    encadear a partir do hash recomputado do NSR 5 -- nunca reiniciar com
    `hash_anterior=None` só porque é a primeira marcação DESTA chamada."""
    primeiro_lote = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=5)
    segundo_lote = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=3)
    assert [m.nsr for m in segundo_lote] == [6, 7, 8]

    registros_primeiro_lote = await montar_registros_tipo7(
        sessao_f12,
        tenant_id=contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        marcacoes=primeiro_lote,
    )
    hash_do_nsr_5 = registros_primeiro_lote[-1].hash_registro

    registros_segundo_lote = await montar_registros_tipo7(
        sessao_f12,
        tenant_id=contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        marcacoes=segundo_lote,
    )

    hash_esperado_nsr_6 = montar_registro_tipo7(
        nsr=segundo_lote[0].nsr,
        cpf=segundo_lote[0].cpf,
        datahora_marcacao=segundo_lote[0].datahora_marcacao,
        datahora_gravacao=segundo_lote[0].datahora_gravacao,
        canal=segundo_lote[0].canal,
        coletada_offline=segundo_lote[0].coletada_offline,
        hash_anterior=hash_do_nsr_5,
    ).hash_registro

    assert registros_segundo_lote[0].hash_registro == hash_esperado_nsr_6
    # Nunca reinicia a cadeia: o hash do NSR 6 encadeado a partir do NSR 5
    # real e DIFERENTE do que seria calculado com hash_anterior=None.
    hash_se_reiniciasse = montar_registro_tipo7(
        nsr=segundo_lote[0].nsr,
        cpf=segundo_lote[0].cpf,
        datahora_marcacao=segundo_lote[0].datahora_marcacao,
        datahora_gravacao=segundo_lote[0].datahora_gravacao,
        canal=segundo_lote[0].canal,
        coletada_offline=segundo_lote[0].coletada_offline,
        hash_anterior=None,
    ).hash_registro
    assert registros_segundo_lote[0].hash_registro != hash_se_reiniciasse


@pytest.mark.asyncio
async def test_lacuna_de_nsr_impede_a_geracao_sem_criar_nenhum_registro(
    sessao_f12: AsyncSession,
    contexto_f12: ContextoF12,
    admin_engine_sync_f12: sa.engine.Engine,
) -> None:
    """Critério de aceite 5 do PCF: uma lacuna simulada (marcação removida
    via SQL direto SÓ NO TESTE, nunca em produção -- marcação é imutável)
    impede a geração, sem criar linha em `afd_arquivos` nem escrever
    arquivo. `verificar_sequencia_nsr` é reaproveitada de F5, não
    reimplementada."""
    marcacoes = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=5)
    assert [m.nsr for m in marcacoes] == list(range(1, 6))

    # Simula lacuna: remove o NSR 3 de `nsr_emissoes` (tabela nao
    # particionada que `verificar_sequencia_nsr` varre para detectar
    # lacuna) via superusuario, desligando o gatilho de imutabilidade na
    # mao -- mesmo padrao adversarial que `tests/f5/dominio/
    # test_imutabilidade.py::test_verificador_detecta_remocao_por_superusuario`
    # ja usa.
    with admin_engine_sync_f12.begin() as conexao:
        conexao.execute(
            text("ALTER TABLE nsr_emissoes DISABLE TRIGGER trg_nsr_emissoes_bloqueia_delete")
        )
        try:
            conexao.execute(
                text(
                    "DELETE FROM nsr_emissoes "
                    "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id AND nsr = 3"
                ),
                {
                    "tenant_id": str(contexto_f12.tenant_id),
                    "rep_p_id": str(contexto_f12.rep_p_id),
                },
            )
        finally:
            conexao.execute(
                text("ALTER TABLE nsr_emissoes ENABLE TRIGGER trg_nsr_emissoes_bloqueia_delete")
            )

    await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await montar_registros_tipo7(
            sessao_f12,
            tenant_id=contexto_f12.tenant_id,
            rep_p_id=contexto_f12.rep_p_id,
            marcacoes=marcacoes,
        )
    assert excinfo.value.codigo == "PONTO-FISC-001"

    # Nenhuma linha de afd_arquivos foi criada por esta chamada -- a funcao
    # nunca chega a montar nem a persistir nada apos a verificacao falhar.
    contagem = await sessao_f12.execute(
        sa.select(sa.func.count())
        .select_from(AfdArquivo)
        .where(
            AfdArquivo.tenant_id == contexto_f12.tenant_id,
            AfdArquivo.rep_p_id == contexto_f12.rep_p_id,
        )
    )
    assert contagem.scalar_one() == 0
