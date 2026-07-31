"""Testes puros dos builders de registro do AEJ (T8).

Nenhum destes testes toca banco -- `app.fiscal.aej.registros` e um modulo
puro (dados resolvidos entram, uma linha de texto sai). Cobre o "pronto
quando" de T8 (PCF F12 secao 6): cada linha termina em `"|"` entre campos e
SEM `"|"` depois do ultimo campo; o registro tipo "05" referencia
corretamente os tipos "02"/"03"/"04" ja emitidos antes dele (testado no
orquestrador, T9 -- aqui so a forma da linha).
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fiscal.aej import registros as r


def _dh(ano: int, mes: int, dia: int, hora: int, minuto: int) -> dt.datetime:
    return dt.datetime(ano, mes, dia, hora, minuto, tzinfo=dt.timezone(dt.timedelta(hours=-3)))


class TestRegraDelimitador:
    """Regra 3 da secao 9 do leiaute: campos terminados por `"|"`, exceto o
    ultimo campo do registro."""

    def test_registro_01_nao_termina_em_pipe(self) -> None:
        linha = r.montar_registro_01(
            r.Cabecalho(
                tp_idt_empregador="1",
                idt_empregador="60258502000149",
                razao_ou_nome="SEEG Sistemas Ltda",
                data_inicial_aej=dt.date(2026, 7, 1),
                data_final_aej=dt.date(2026, 7, 31),
                data_hora_ger_aej=_dh(2026, 7, 31, 23, 59),
            )
        )
        assert not linha.endswith("|")
        assert linha.count("|") == 9  # 10 campos -> 9 delimitadores

    def test_registro_05_com_ultimo_campo_preenchido_nao_termina_em_pipe(self) -> None:
        """Ultimo campo (`motivo`) preenchido: a linha nao pode ter `"|"`
        depois dele."""
        linha = r.montar_registro_05(
            r.MarcacaoAej(
                idt_vinculo_aej=1,
                data_hora_marc=_dh(2026, 7, 1, 8, 0),
                id_rep_aej=1,
                tp_marc="D",
                seq_ent_saida=0,
                fonte_marc="O",
                motivo="Marcacao duplicada",
            )
        )
        assert not linha.endswith("|")
        assert linha.count("|") == 8  # 9 campos (tipoReg + 8) -> 8 delimitadores
        campos = linha.split("|")
        assert campos[0] == "05"
        assert campos[8] == "Marcacao duplicada"

    def test_registro_05_com_ultimo_campo_vazio_tem_9_campos(self) -> None:
        """Ultimo campo (`motivo`) ausente: o campo fica string vazia (nunca
        `"None"`), e a linha ainda assim tem exatamente 9 campos (tipoReg +
        8) quando dividida por `"|"` -- o `"|"` final visivel na string
        bruta e o TERMINADOR do campo 8 (`codHorContratual`), nao um
        delimitador extra depois do campo 9 (regra 3 da secao 9: cada campo,
        exceto o ultimo, termina em `"|"`; um ultimo campo vazio nao tem
        como deixar de "parecer" que a linha termina em `"|"`, porque nao ha
        um DECIMO caractere para vir depois dele)."""
        linha = r.montar_registro_05(
            r.MarcacaoAej(
                idt_vinculo_aej=1,
                data_hora_marc=_dh(2026, 7, 1, 8, 0),
                id_rep_aej=1,
                tp_marc="E",
                seq_ent_saida=1,
                fonte_marc="O",
                cod_hor_contratual="COM-8H",
            )
        )
        campos = linha.split("|")
        assert len(campos) == 9
        assert campos[0] == "05"
        assert campos[7] == "COM-8H"
        assert campos[8] == ""  # motivo ausente -> string vazia, nunca "None"

    def test_linha_assinatura_nao_usa_pipe(self) -> None:
        linha = r.montar_linha_assinatura()
        assert "|" not in linha
        assert len(linha) == 100
        assert linha.startswith("ASSINATURA_DIGITAL_EM_ARQUIVO_P7S")
        assert linha.rstrip() == "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"


class TestFormatoCampos:
    def test_data_hora_no_registro_01(self) -> None:
        linha = r.montar_registro_01(
            r.Cabecalho(
                tp_idt_empregador="1",
                idt_empregador="60258502000149",
                razao_ou_nome="SEEG Sistemas Ltda",
                data_inicial_aej=dt.date(2026, 7, 1),
                data_final_aej=dt.date(2026, 7, 31),
                data_hora_ger_aej=_dh(2026, 7, 31, 16, 44),
            )
        )
        campos = linha.split("|")
        # dataInicialAej / dataFinalAej: AAAA-MM-dd
        assert campos[6] == "2026-07-01"
        assert campos[7] == "2026-07-31"
        # dataHoraGerAej: AAAA-MM-ddThh:mm:00ZZZZZ (24 caracteres)
        assert campos[8] == "2026-07-31T16:44:00-0300"
        assert len(campos[8]) == 24

    def test_hora_hhmm_no_registro_04(self) -> None:
        linha = r.montar_registro_04(
            r.HorarioContratual(
                cod_hor_contratual="COM-8H",
                dur_jornada=480,
                hr_entrada_01=dt.time(8, 0),
                hr_saida_01=dt.time(12, 0),
                hr_entrada_02=dt.time(13, 0),
                hr_saida_02=dt.time(17, 0),
            )
        )
        campos = linha.split("|")
        assert campos == ["04", "COM-8H", "480", "0800", "1200", "1300", "1700"]

    def test_horario_sem_segundo_par_fica_vazio(self) -> None:
        linha = r.montar_registro_04(
            r.HorarioContratual(
                cod_hor_contratual="12X36",
                dur_jornada=720,
                hr_entrada_01=dt.time(7, 0),
                hr_saida_01=dt.time(19, 0),
            )
        )
        campos = linha.split("|")
        assert campos[5] == ""
        assert campos[6] == ""

    def test_campo_numerico_opcional_ausente_fica_vazio(self) -> None:
        linha = r.montar_registro_07(
            r.AusenciaOuBancoHoras(
                idt_vinculo_aej=1, tipo_ausen_ou_comp="1", data=dt.date(2026, 7, 5)
            )
        )
        campos = linha.split("|")
        assert campos == ["07", "1", "1", "2026-07-05", "", ""]

    def test_campo_numerico_presente_no_lancamento_banco_horas(self) -> None:
        linha = r.montar_registro_07(
            r.AusenciaOuBancoHoras(
                idt_vinculo_aej=1,
                tipo_ausen_ou_comp="3",
                data=dt.date(2026, 7, 10),
                qt_minutos=120,
                tipo_mov_bh="1",
            )
        )
        campos = linha.split("|")
        assert campos == ["07", "1", "3", "2026-07-10", "120", "1"]


class TestTrailer:
    def test_trailer_inclui_contagem_do_tipo_01(self) -> None:
        """Leitura literal da tabela (secao 10, tipo '99'): o trailer do AEJ
        inclui `qtRegistrosTipo01` (sempre 1), diferente do trailer do AFD
        (que omite a contagem do cabecalho) -- so omite a contagem de si
        mesmo (tipo '99')."""
        linha = r.montar_registro_99(
            r.TrailerAej(
                qt_registros_tipo_01=1,
                qt_registros_tipo_02=2,
                qt_registros_tipo_03=3,
                qt_registros_tipo_04=4,
                qt_registros_tipo_05=5,
                qt_registros_tipo_06=6,
                qt_registros_tipo_07=7,
                qt_registros_tipo_08=1,
            )
        )
        assert linha == "99|1|2|3|4|5|6|7|1"


class TestTipo08EmailDesenvNaoCorrigido:
    def test_campo_email_desenv_escrito_como_texto_livre(self) -> None:
        """`emailDesenv` e tipado `N` no leiaute oficial (provavel erro de
        digitacao da norma) -- este modulo NUNCA "corrige" a observacao,
        so escreve o valor recebido como texto livre (PCF F12, T8)."""
        linha = r.montar_registro_08(
            r.IdentificacaoPtrp(
                nome_prog="SEEG Ponto",
                versao_prog="1.0.0",
                tp_idt_desenv="1",
                idt_desenv="60258502000149",
                razao_nome_desenv="SEEG Sistemas Ltda",
                email_desenv="contato@exemplo.invalido",
            )
        )
        campos = linha.split("|")
        assert campos[6] == "contato@exemplo.invalido"


class TestSemCrc16:
    """PCF F12 secao 2.9 / 9: o AEJ nunca implementa CRC-16 -- confirma que
    o modulo nao expoe nenhum simbolo relacionado."""

    def test_modulo_nao_expoe_crc16(self) -> None:
        assert not hasattr(r, "crc16")
        assert not hasattr(r, "crc16_ccitt")


@pytest.mark.parametrize(
    ("tipo_reg", "builder", "dados", "esperado_tamanho_campos"),
    [
        (
            "02",
            r.montar_registro_02,
            r.RepUtilizado(id_rep_aej=1, tp_rep="3", nr_rep="00000000012345678"[:17]),
            4,
        ),
        (
            "03",
            r.montar_registro_03,
            r.VinculoAej(idt_vinculo_aej=1, cpf="12345678901", nome_emp="Fulano"),
            4,
        ),
        ("06", r.montar_registro_06, r.MatriculaEsocial(idt_vinculo_aej=1, mat_esocial="MAT-1"), 3),
    ],
)
def test_quantidade_de_campos_por_tipo(tipo_reg, builder, dados, esperado_tamanho_campos) -> None:  # type: ignore[no-untyped-def]
    linha = builder(dados)
    campos = linha.split("|")
    assert campos[0] == tipo_reg
    assert len(campos) == esperado_tamanho_campos
