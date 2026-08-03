"""Testes do exportador TOTVS RM (T17, agente A6, F13).

Testes puros de transformacao -- `gerar()` (implementacao de `app.
integracoes.folha.comum.protocolo.GeradorFolha`) nao acessa banco nem rede,
entao estes testes nao dependem de `apps/api/tests/f13/conftest.py`
(fixture compartilhada da fase, ownership de A1). Fabricas de dados em
`tests.f13.folha.totvs_rm._apoio`.
"""

from __future__ import annotations

from decimal import Decimal

from app.integracoes.folha.totvs_rm import exportador
from tests.f13.folha.totvs_rm import _apoio


def test_parceiro_bate_com_enum_do_contrato() -> None:
    # `packages/contracts/schema.sql` (CHECK de `integracoes_folha.parceiro`)
    # e `packages/contracts/openapi.yaml` (`IntegracaoFolha.parceiro`) usam
    # exatamente este literal.
    assert exportador.PARCEIRO == "totvs_rm"


def test_gerar_registrado_no_motor_generico() -> None:
    # `__init__.py` do pacote chama `registro.registrar` no import -- se
    # este teste roda, o pacote ja foi importado (via `exportador`), entao
    # o registro ja aconteceu.
    from app.integracoes.folha.comum import registro

    assert registro.obter_gerador("totvs_rm") is exportador.gerar


def test_gerar_vazio_produz_so_cabecalho() -> None:
    resultado = exportador.gerar(_apoio.contexto(parceiro="totvs_rm", linhas=()))
    texto = resultado.conteudo.decode("utf-8-sig")
    assert texto.splitlines() == [";".join(exportador._CABECALHO)]


def test_gerar_usa_delimitador_ponto_e_virgula() -> None:
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=(_apoio.linha(),))
    resultado = exportador.gerar(ctx)
    primeira_linha = resultado.conteudo.decode("utf-8-sig").splitlines()[0]
    assert primeira_linha.count(";") == len(exportador._CABECALHO) - 1


def test_gerar_tem_bom_utf8() -> None:
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=(_apoio.linha(),))
    resultado = exportador.gerar(ctx)
    assert resultado.conteudo.startswith(b"\xef\xbb\xbf")


def test_content_type_csv_utf8() -> None:
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=(_apoio.linha(),))
    resultado = exportador.gerar(ctx)
    assert resultado.content_type == "text/csv; charset=utf-8"


def test_nome_arquivo_segue_convencao_da_chave_de_objeto() -> None:
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=())
    resultado = exportador.gerar(ctx)
    assert resultado.nome_arquivo == (
        f"integracoes-folha/{ctx.tenant_id}/{ctx.integracao_id}/"
        f"totvs_rm-{ctx.competencia_folha}-{ctx.processamento_id}.csv"
    )


def test_rubrica_ja_resolvida_na_linha_e_usada_diretamente() -> None:
    # `dados.coletar_linhas_apuracao` sempre entrega `rubrica=None`, mas o
    # protocolo permite que um `rubrica` ja resolvido chegue pronto -- o
    # exportador nao deve re-resolver nesse caso.
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(componente_codigo="he_50", rubrica="JA_RESOLVIDO"),),
        mapeamento_rubricas={"he_50": "NAO_DEVERIA_APARECER"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "JA_RESOLVIDO" in linha_dados
    assert "NAO_DEVERIA_APARECER" not in linha_dados


def test_mapeamento_rubricas_traduz_componente() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(componente_codigo="he_50"),),
        mapeamento_rubricas={"he_50": "HE50"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "HE50" in linha_dados
    assert "he_50" not in linha_dados


def test_sem_mapeamento_sai_codigo_interno() -> None:
    # Mesma regra que `criarIntegracaoFolha` ja documenta no contrato: sem
    # mapeamento, sai o codigo interno -- mesmo comportamento que
    # `generico_csv` (A5) usa para a coluna `rubrica`.
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=(_apoio.linha(componente_codigo="he_50"),))
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "he_50" in linha_dados


def test_mapeamento_sem_entrada_para_componente_cai_no_codigo_interno() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(componente_codigo="falta"),),
        mapeamento_rubricas={"he_50": "HE50"},
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "falta" in linha_dados


def test_minutos_equivalentes_viram_horas_decimais_com_virgula() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(minutos_equivalentes=90),),
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "1,50" in linha_dados  # 90 minutos = 1.5 horas


def test_minutos_equivalentes_negativos_preservam_sinal() -> None:
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(componente_codigo="falta", minutos=-480, minutos_equivalentes=-480),),
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "-8,00" in linha_dados


def test_multiplas_linhas_mesmo_vinculo_diferentes_componentes() -> None:
    linhas = (
        _apoio.linha(componente_codigo="he_50", minutos_equivalentes=60),
        _apoio.linha(componente_codigo="falta", minutos=-480, minutos_equivalentes=-480),
    )
    ctx = _apoio.contexto(parceiro="totvs_rm", linhas=linhas)
    resultado = exportador.gerar(ctx)
    texto = resultado.conteudo.decode("utf-8-sig")
    assert len(texto.splitlines()) == 1 + len(linhas)  # cabecalho + 2 linhas


def test_fator_da_linha_nao_aparece_diretamente_so_o_equivalente() -> None:
    # `minutos_equivalentes` ja e `minutos * fator` (resolvido por A5 em
    # `dados.coletar_linhas_apuracao`) -- este exportador usa o equivalente
    # pronto, nunca recalcula a partir de `fator` bruto.
    ctx = _apoio.contexto(
        parceiro="totvs_rm",
        linhas=(_apoio.linha(minutos=60, fator=Decimal("1.5"), minutos_equivalentes=90),),
    )
    resultado = exportador.gerar(ctx)
    linha_dados = resultado.conteudo.decode("utf-8-sig").splitlines()[1]
    assert "1,50" in linha_dados
    assert "1,00" not in linha_dados  # 60 minutos brutos, se usado por engano, dariam 1,00
