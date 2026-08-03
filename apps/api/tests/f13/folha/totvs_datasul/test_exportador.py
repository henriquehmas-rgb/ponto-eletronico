"""Testes do exportador TOTVS Datasul / PE0540 (T17, agente A6, F13).

Testes puros de transformacao -- ver nota identica em
`apps/api/tests/f13/folha/totvs_rm/test_exportador.py` sobre por que nao ha
dependencia de `apps/api/tests/f13/conftest.py`. Fabricas de dados
reaproveitadas de `tests.f13.folha.totvs_rm._apoio` (mesmo agente, A6).
"""

from __future__ import annotations

import datetime as dt

from app.integracoes.folha.totvs_datasul import exportador
from tests.f13.folha.totvs_rm import _apoio


def test_parceiro_bate_com_enum_do_contrato() -> None:
    assert exportador.PARCEIRO == "totvs_datasul"


def test_gerar_registrado_no_motor_generico() -> None:
    from app.integracoes.folha.comum import registro

    assert registro.obter_gerador("totvs_datasul") is exportador.gerar


def test_gerar_vazio_produz_so_cabecalho() -> None:
    resultado = exportador.gerar(_apoio.contexto(parceiro="totvs_datasul", linhas=()))
    texto = resultado.conteudo.decode("utf-8-sig")
    assert texto.splitlines() == [";".join(exportador._CABECALHO)]


def test_mapeamento_rubricas_traduz_para_evento() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_datasul",
        linhas=(_apoio.linha(componente_codigo="he_50"),),
        mapeamento_rubricas={"he_50": "EV100"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "EV100" in linha_dados


def test_sem_mapeamento_sai_codigo_interno() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_datasul", linhas=(_apoio.linha(componente_codigo="he_50"),)
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "he_50" in linha_dados


def test_rubrica_ja_resolvida_na_linha_e_usada_diretamente() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_datasul",
        linhas=(_apoio.linha(componente_codigo="he_50", rubrica="JA_RESOLVIDO"),),
        mapeamento_rubricas={"he_50": "NAO_DEVERIA_APARECER"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "JA_RESOLVIDO" in linha_dados


def test_minutos_equivalentes_negativos_preservam_sinal() -> None:
    # Debito de banco de horas, por exemplo: minutos_equivalentes pode ser
    # negativo.
    ctx = _apoio.contexto(
        parceiro="totvs_datasul",
        linhas=(
            _apoio.linha(
                componente_codigo="banco_horas_debito", minutos=-90, minutos_equivalentes=-90
            ),
        ),
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "-1,50" in linha_dados


def test_arredondamento_comercial_half_up() -> None:
    # 1 minuto = 0.01666...h -> arredonda para 0,02 (ROUND_HALF_UP, nao
    # banker's rounding).
    ctx = _apoio.contexto(
        parceiro="totvs_datasul", linhas=(_apoio.linha(minutos=1, minutos_equivalentes=1),)
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "0,02" in linha_dados


def test_data_formatada_dd_mm_aaaa() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_datasul", linhas=(_apoio.linha(data=dt.date(2026, 1, 5)),)
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "05/01/2026" in linha_dados


def test_nome_arquivo_segue_convencao_pe0540() -> None:
    ctx = _apoio.contexto(parceiro="totvs_datasul", linhas=())
    resultado = exportador.gerar(ctx)
    assert resultado.nome_arquivo == (
        f"integracoes-folha/{ctx.tenant_id}/{ctx.integracao_id}/"
        f"totvs_datasul-{ctx.competencia_folha}-{ctx.processamento_id}.csv"
    )


def test_delimitador_e_ponto_e_virgula_nao_virgula() -> None:
    ctx = _apoio.contexto(parceiro="totvs_datasul", linhas=(_apoio.linha(),))
    resultado = exportador.gerar(ctx)
    primeira_linha = resultado.conteudo.decode("utf-8-sig").splitlines()[0]
    assert "," not in primeira_linha
    assert ";" in primeira_linha
