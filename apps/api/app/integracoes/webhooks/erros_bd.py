"""Traducao de violacao de integridade do banco para o catalogo de erros,
self-contained para o dominio `webhooks` (mesmo padrao de
`app/terminais/erros_bd.py`/`app/pessoas/erros_bd.py`)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: `uq_webhooks_nome` -- nome duplicado no mesmo tenant (`packages/contracts/
#: schema.sql`, secao 14).
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_webhooks_nome": "PONTO-CONF-001",
    "webhooks_url_check": "PONTO-WEBH-001",
}


def _nome_constraint(origem: BaseException) -> str | None:
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
