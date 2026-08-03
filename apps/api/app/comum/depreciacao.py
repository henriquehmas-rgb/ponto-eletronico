"""Mecanismo de depreciação de operação (F13/A1, T5 — ADR-005 item 4).

`ADR-005` (`docs/adr/ADR-005-versionamento-api-publica-depreciacao.md`)
decide a política: recurso a ser removido responde `Deprecation: <data>` e
`Sunset: <data>` (RFC 8594) e `Link` para o guia de migração, com no mínimo
180 dias entre o anúncio e a remoção, e a marca `deprecated: true` no
OpenAPI. **Nenhuma operação do `/v1` está marcada como depreciada hoje** —
este módulo entrega só o MECANISMO, pronto para o dia em que alguém
depreciar algo de verdade; não há nenhuma chamada real a
`aplicar_cabecalhos_depreciacao`/`exigir_aviso_depreciacao` em nenhum router
desta fase.

Os dois cabeçalhos de data usam o formato HTTP-date (RFC 7231 / RFC 9110
`IMF-fixdate`), o mesmo formato exigido pela RFC 8594 para `Sunset` e pela
prática corrente para `Deprecation`.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Awaitable, Callable
from email.utils import format_datetime

from fastapi import Response

__all__ = ["aplicar_cabecalhos_depreciacao", "exigir_aviso_depreciacao"]


def _como_datetime_utc(valor: _dt.date | _dt.datetime) -> _dt.datetime:
    """Normaliza `date`/`datetime` (com ou sem fuso) para `datetime` em UTC."""
    if isinstance(valor, _dt.datetime):
        return valor.astimezone(_dt.UTC) if valor.tzinfo else valor.replace(tzinfo=_dt.UTC)
    return _dt.datetime(valor.year, valor.month, valor.day, tzinfo=_dt.UTC)


def _http_date(valor: _dt.date | _dt.datetime) -> str:
    """`date`/`datetime` -> `IMF-fixdate` (ex.: `Wed, 21 Oct 2026 07:28:00 GMT`)."""
    return format_datetime(_como_datetime_utc(valor), usegmt=True)


def aplicar_cabecalhos_depreciacao(
    response: Response,
    *,
    descontinuado_em: _dt.date | _dt.datetime,
    remocao_em: _dt.date | _dt.datetime,
    link_migracao: str,
) -> None:
    """Escreve `Deprecation`/`Sunset`/`Link` em `response`.

    `remocao_em` deve estar a pelo menos 180 dias de `descontinuado_em`
    (ADR-005 item 4) — esta função não impõe o mínimo (é uma decisão de quem
    marca a operação como depreciada, tomada no momento da depreciação real,
    não aqui), mas registra um aviso no log quando a janela é mais curta, para
    o desvio não passar despercebido.
    """
    inicio = _como_datetime_utc(descontinuado_em)
    fim = _como_datetime_utc(remocao_em)
    if (fim - inicio) < _dt.timedelta(days=180):
        from app.core.log import obter_logger

        obter_logger("depreciacao").warning(
            "janela de depreciacao menor que os 180 dias minimos do ADR-005",
            extra={"descontinuadoEm": inicio.isoformat(), "remocaoEm": fim.isoformat()},
        )

    response.headers["Deprecation"] = _http_date(descontinuado_em)
    response.headers["Sunset"] = _http_date(remocao_em)
    response.headers["Link"] = f'<{link_migracao}>; rel="deprecation"'


def exigir_aviso_depreciacao(
    *,
    descontinuado_em: _dt.date | _dt.datetime,
    remocao_em: _dt.date | _dt.datetime,
    link_migracao: str,
) -> Callable[..., Awaitable[None]]:
    """Fábrica de dependência FastAPI equivalente a
    `aplicar_cabecalhos_depreciacao`, para quem preferir `Depends(...)` no
    lugar de uma chamada explícita no corpo do handler."""

    async def _dependencia(response: Response) -> None:
        aplicar_cabecalhos_depreciacao(
            response,
            descontinuado_em=descontinuado_em,
            remocao_em=remocao_em,
            link_migracao=link_migracao,
        )

    return _dependencia
