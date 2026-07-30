"""Tradução de violação de integridade do banco para o catálogo de erros,
cópia própria do domínio `workflow.aprovacoes` (mesmo padrão de
`app.workflow.solicitacoes.erros_bd`/`app.apuracao.tratamento.erros_bd`,
nunca importado de outra fase).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint -> código do catálogo. `aprovacoes`/`delegacoes`
#: (schema.sql seções 11 e 4).
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_aprovacoes_etapa": "PONTO-CONF-001",
    "aprovacoes_etapa_check": "PONTO-VAL-001",
    "aprovacoes_papel_check": "PONTO-VAL-001",
    "aprovacoes_decisao_check": "PONTO-VAL-001",
    "ck_delegacoes_periodo": "PONTO-VAL-001",
    "ck_delegacoes_pessoas": "PONTO-VAL-001",
    "delegacoes_status_check": "PONTO-VAL-001",
    #: `ex_delegacoes_sobreposicao` (EXCLUDE CONSTRAINT, GIST) -- "Vigencia
    #: sobreposta ... o banco impede a sobreposicao por constraint de
    #: exclusao", descricao literal de `errors.yaml`/`PONTO-VAL-010`.
    "ex_delegacoes_sobreposicao": "PONTO-VAL-010",
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
    detalhe = None
    if codigo == "PONTO-VAL-010":
        detalhe = "Ja existe uma delegacao vigente sobreposta para o mesmo par de usuarios."
    return ErroDeAplicacao(codigo, detalhe=detalhe, contexto_log={"constraint": nome})
