"""Testes do registro de exportadores (F13/A5, T15) -- o mecanismo que A6/
A7 usam para "plugar" cada parceiro sem editar nenhum arquivo de A5. Ver
docstring de `app.integracoes.folha.comum.registro`."""

from __future__ import annotations

import pytest

from app.integracoes.folha import carregar_exportadores
from app.integracoes.folha.comum import registro
from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha


def _gerador_fake(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    return ArquivoFolhaGerado(conteudo=b"fake", nome_arquivo="fake.csv")


def test_registrar_e_obter_gerador() -> None:
    registro.registrar("__parceiro_teste__", _gerador_fake, sobrescrever=True)
    assert registro.obter_gerador("__parceiro_teste__") is _gerador_fake


def test_registrar_duas_vezes_com_gerador_diferente_sem_sobrescrever_e_erro() -> None:
    def outro_gerador(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
        return ArquivoFolhaGerado(conteudo=b"outro", nome_arquivo="outro.csv")

    registro.registrar("__parceiro_teste_2__", _gerador_fake, sobrescrever=True)
    with pytest.raises(ValueError):
        registro.registrar("__parceiro_teste_2__", outro_gerador)


def test_registrar_mesmo_gerador_duas_vezes_e_idempotente() -> None:
    registro.registrar("__parceiro_teste_3__", _gerador_fake, sobrescrever=True)
    # Mesmo objeto de novo -- nao levanta, mesmo sem sobrescrever=True (o
    # cenario real de `carregar_exportadores()` chamado mais de uma vez no
    # mesmo processo, por exemplo entre testes).
    registro.registrar("__parceiro_teste_3__", _gerador_fake)


def test_parceiro_nao_registrado_levanta_erro_proprio() -> None:
    with pytest.raises(registro.ParceiroNaoRegistrado):
        registro.obter_gerador("__parceiro_que_nunca_existiu__")


def test_carregar_exportadores_registra_generico_csv_dominio_e_alterdata() -> None:
    carregar_exportadores()
    disponiveis = registro.parceiros_disponiveis()
    assert "generico_csv" in disponiveis
    assert "dominio" in disponiveis
    assert "alterdata" in disponiveis


def test_carregar_exportadores_e_idempotente() -> None:
    carregar_exportadores()
    primeira_leitura = registro.parceiros_disponiveis()
    carregar_exportadores()
    segunda_leitura = registro.parceiros_disponiveis()
    assert primeira_leitura == segunda_leitura
