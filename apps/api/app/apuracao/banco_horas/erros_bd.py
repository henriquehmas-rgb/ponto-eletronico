"""Traducao de violacao de integridade do banco para o catalogo de erros.

Copia dedicada do padrao de `app.pessoas.erros_bd` (F2): o Postgres recusa a
linha antes de qualquer regra de aplicacao rodar de novo (unicidade,
`EXCLUDE`, `CHECK`) -- ultima linha de defesa, nao a primeira. So as
constraints que as tabelas desta fase (`bh_politicas`, `bh_contas`,
`bh_lancamentos`, `bh_quitacoes`) podem violar em tempo de escrita.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (identico ao de `packages/contracts/models`) -> codigo
#: do catalogo.
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_bh_politicas_codigo": "PONTO-CONF-001",
    "ck_bh_politicas_periodo_legal": "PONTO-BH-003",
    "ck_bh_politicas_vigencia": "PONTO-VAL-001",
    "uq_bh_contas": "PONTO-CONF-001",
    "ck_bh_contas_periodo": "PONTO-VAL-001",
    "bh_lancamentos_minutos_check": "PONTO-VAL-001",
    "bh_lancamentos_fator_check": "PONTO-VAL-001",
    "uq_bh_lancamentos_sequencia": "PONTO-CONF-001",
    "bh_quitacoes_minutos_check": "PONTO-VAL-001",
    "bh_quitacoes_fator_check": "PONTO-VAL-001",
}


def _nome_constraint(origem: BaseException) -> str | None:
    """Extrai o nome da constraint do erro nativo do driver (ver
    `app.pessoas.erros_bd._nome_constraint`, mesma logica)."""
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    """Converte `IntegrityError` no `ErroDeAplicacao` do codigo
    correspondente. `padrao` cobre uma constraint nao mapeada (uma
    migration futura que acrescente uma constraint sem atualizar este
    mapa): preferimos um 409 generico de conflito a um 500, com o nome real
    da constraint preservado em `contexto_log` para investigacao."""
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
