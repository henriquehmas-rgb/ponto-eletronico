"""Tradução de violação de integridade do banco para o catálogo de erros,
cópia própria do domínio `tratamento` (mesmo padrão de `app.pessoas.erros_bd`,
nunca importado de outra fase).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (idêntico ao de `packages/contracts/models`) -> código
#: do catálogo. Só as constraints que `tratamentos`/`tipos_tratamento` podem
#: violar em tempo de escrita (seção 9 do `schema.sql`).
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_tipos_tratamento_codigo": "PONTO-CONF-001",
    "ck_tratamentos_marcacao": "PONTO-VAL-001",
    "tratamentos_sentido_check": "PONTO-VAL-001",
    "tratamentos_origem_check": "PONTO-VAL-001",
    "tratamentos_status_check": "PONTO-VAL-001",
    "fk_tratamentos_marcacao": "PONTO-REC-001",
}


def _nome_constraint(origem: BaseException) -> str | None:
    """Extrai o nome da constraint do erro nativo do driver."""
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    """Converte `IntegrityError` no `ErroDeAplicacao` do código correspondente."""
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
