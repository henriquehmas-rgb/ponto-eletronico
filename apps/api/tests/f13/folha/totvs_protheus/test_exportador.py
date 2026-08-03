"""Testes do exportador TOTVS Protheus / GPEA200 (T17, agente A6, F13).

Testes puros de transformacao -- ver nota identica em
`apps/api/tests/f13/folha/totvs_rm/test_exportador.py` sobre por que nao ha
dependencia de `apps/api/tests/f13/conftest.py`. Fabricas de dados
reaproveitadas de `tests.f13.folha.totvs_rm._apoio` (mesmo agente, A6).
"""

from __future__ import annotations

from app.integracoes.folha.totvs_protheus import exportador
from tests.f13.folha.totvs_rm import _apoio


def test_parceiro_bate_com_enum_do_contrato() -> None:
    assert exportador.PARCEIRO == "totvs_protheus"


def test_gerar_registrado_no_motor_generico() -> None:
    from app.integracoes.folha.comum import registro

    assert registro.obter_gerador("totvs_protheus") is exportador.gerar


def test_gerar_vazio_produz_so_cabecalho() -> None:
    resultado = exportador.gerar(_apoio.contexto(parceiro="totvs_protheus", linhas=()))
    texto = resultado.conteudo.decode("utf-8-sig")
    assert texto.splitlines() == [";".join(exportador._CABECALHO)]


def test_cabecalho_inclui_filial() -> None:
    # GPEA200 e uma rotina multi-filial por desenho do Protheus (ver
    # docstring do modulo) -- unica diferenca estrutural relevante frente
    # aos outros dois exportadores da familia.
    assert exportador._CABECALHO[0] == "Filial"


def test_filial_vem_da_configuracao() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_protheus", linhas=(_apoio.linha(),), configuracao={"filial": "02"}
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert linha_dados.split(";")[0] == "02"


def test_sem_configuracao_filial_sai_vazia_sem_inventar_codigo() -> None:
    ctx = _apoio.contexto(parceiro="totvs_protheus", linhas=(_apoio.linha(),))
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert linha_dados.split(";")[0] == ""


def test_configuracao_com_filial_nao_string_e_ignorada_sem_quebrar() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_protheus", linhas=(_apoio.linha(),), configuracao={"filial": 123}
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert linha_dados.split(";")[0] == ""


def test_mapeamento_rubricas_traduz_para_verba() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_protheus",
        linhas=(_apoio.linha(componente_codigo="he_50"),),
        mapeamento_rubricas={"he_50": "0100"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "0100" in linha_dados


def test_rubrica_ja_resolvida_na_linha_e_usada_diretamente() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_protheus",
        linhas=(_apoio.linha(componente_codigo="he_50", rubrica="JA_RESOLVIDO"),),
        mapeamento_rubricas={"he_50": "NAO_DEVERIA_APARECER"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "JA_RESOLVIDO" in linha_dados


def test_minutos_equivalentes_viram_horas_decimais_com_virgula() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_protheus", linhas=(_apoio.linha(minutos_equivalentes=90),)
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "1,50" in linha_dados


def test_nome_arquivo_segue_convencao_gpea200() -> None:
    ctx = _apoio.contexto(parceiro="totvs_protheus", linhas=())
    resultado = exportador.gerar(ctx)
    assert resultado.nome_arquivo == (
        f"integracoes-folha/{ctx.tenant_id}/{ctx.integracao_id}/"
        f"totvs_protheus-{ctx.competencia_folha}-{ctx.processamento_id}.csv"
    )


def test_gerar_com_multiplos_vinculos() -> None:
    linhas = (
        _apoio.linha(matricula="00123", componente_codigo="he_50"),
        _apoio.linha(
            matricula="00456",
            cpf="98765432100",
            nome_completo="Maria Souza",
            componente_codigo="falta",
        ),
    )
    ctx = _apoio.contexto(parceiro="totvs_protheus", linhas=linhas)
    resultado = exportador.gerar(ctx)
    corpo = resultado.conteudo.decode("utf-8-sig").splitlines()[1:]
    assert len(corpo) == 2
    assert any("00456" in linha for linha in corpo)
