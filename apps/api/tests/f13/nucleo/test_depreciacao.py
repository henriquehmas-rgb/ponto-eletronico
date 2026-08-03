"""T5 -- `app.comum.depreciacao` (F13/A1).

Nenhuma operação real do `/v1` está marcada como depreciada nesta fase (ver
docstring do módulo) -- este teste prova só o MECANISMO: uma operação
FICTÍCIA (montada aqui, dentro do teste) marcada `deprecated`, exercitada
como o ADR-005 item 4 exige, com os três cabeçalhos (`Deprecation`/`Sunset`/
`Link`).
"""

from __future__ import annotations

import datetime as dt

from starlette.responses import Response

from app.comum.depreciacao import aplicar_cabecalhos_depreciacao, exigir_aviso_depreciacao


def test_aplica_cabecalhos_deprecation_sunset_link() -> None:
    response = Response()
    aplicar_cabecalhos_depreciacao(
        response,
        descontinuado_em=dt.date(2026, 8, 1),
        remocao_em=dt.date(2027, 2, 1),
        link_migracao="https://docs.ponto.seeg.com.br/migracao/exemplo",
    )

    assert response.headers["Deprecation"] == "Sat, 01 Aug 2026 00:00:00 GMT"
    assert response.headers["Sunset"] == "Mon, 01 Feb 2027 00:00:00 GMT"
    assert response.headers["Link"] == (
        '<https://docs.ponto.seeg.com.br/migracao/exemplo>; rel="deprecation"'
    )


def test_aceita_datetime_com_fuso_e_normaliza_para_utc() -> None:
    response = Response()
    fuso_br = dt.timezone(dt.timedelta(hours=-3))
    aplicar_cabecalhos_depreciacao(
        response,
        descontinuado_em=dt.datetime(2026, 8, 1, 9, 0, tzinfo=fuso_br),
        remocao_em=dt.datetime(2027, 2, 1, 9, 0, tzinfo=fuso_br),
        link_migracao="https://docs.ponto.seeg.com.br/migracao/exemplo",
    )
    # 09:00 -03:00 == 12:00 UTC.
    assert response.headers["Deprecation"] == "Sat, 01 Aug 2026 12:00:00 GMT"


def test_janela_menor_que_180_dias_registra_aviso_mas_nao_bloqueia(caplog) -> None:
    response = Response()
    with caplog.at_level("WARNING"):
        aplicar_cabecalhos_depreciacao(
            response,
            descontinuado_em=dt.date(2026, 8, 1),
            remocao_em=dt.date(2026, 8, 15),  # so 14 dias -- abaixo do minimo do ADR-005
            link_migracao="https://docs.ponto.seeg.com.br/migracao/exemplo",
        )
    assert "Deprecation" in response.headers
    assert any("180 dias" in registro.message for registro in caplog.records)


async def test_exigir_aviso_depreciacao_e_um_depends_compativel() -> None:
    dependencia = exigir_aviso_depreciacao(
        descontinuado_em=dt.date(2026, 8, 1),
        remocao_em=dt.date(2027, 2, 1),
        link_migracao="https://docs.ponto.seeg.com.br/migracao/exemplo",
    )
    response = Response()
    await dependencia(response=response)
    assert response.headers["Sunset"] == "Mon, 01 Feb 2027 00:00:00 GMT"
