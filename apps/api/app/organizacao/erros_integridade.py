"""Traduz violacao de constraint do PostgreSQL para o codigo do catalogo.

Cadastro depende de banco para aplicar boa parte das suas proprias regras
(unicidade de CNPJ, EXCLUDE de vigencia sobreposta, FK RESTRICT em exclusao com
dependente): em vez de duplicar cada verificacao em Python antes do INSERT
(condicao de corrida entre a checagem e a escrita), este modulo mapeia
`IntegrityError` do SQLAlchemy para o `ErroDeAplicacao` certo, pelo nome da
constraint que o Postgres devolve.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Prefixo de indice/constraint unico -> "registro duplicado". `uq_..._codigo`,
#: `uq_..._cnpj` etc. sao todos a mesma familia; violacao de CHECK (por
#: exemplo `ck_empresas_matriz`) cai no default de PONTO-VAL-001, no fim da
#: funcao -- e o comportamento certo, nao precisa de entrada propria aqui.
_PREFIXOS_DUPLICADO = ("uq_",)
_EXCLUDE_VIGENCIA = (
    "ex_equipe_membros_sobreposicao",
    "ex_colaborador_gestores_imediato",
    "ex_vinculos_sobreposicao",
)


def mapear_integridade(
    exc: IntegrityError, *, operacao: str = "", ao_excluir: bool = False
) -> ErroDeAplicacao:
    """Devolve o `ErroDeAplicacao` correspondente a uma `IntegrityError`.

    `operacao` e um rotulo livre (nome do recurso) usado so no log interno,
    nunca na resposta ao cliente (`expoe_regra` de cada codigo decide o que
    sai no `detail`). `ao_excluir` desambigua a violacao de chave
    estrangeira (23503): numa exclusao ela significa "tem dependente"
    (`PONTO-CONF-004`); numa escrita significa referencia para algo que nao
    existe (`PONTO-REC-001`) -- a checagem de existencia do service layer
    deveria pegar isso antes, mas o mapeamento cobre a corrida residual.
    """
    # `exc.orig` e o wrapper DBAPI do dialeto asyncpg do SQLAlchemy
    # (`AsyncAdapt_asyncpg_dbapi.IntegrityError`), que nao carrega os campos de
    # diagnostico do Postgres. A excecao real do asyncpg -- com
    # `constraint_name`, `table_name` e `sqlstate` -- vem encadeada em
    # `exc.orig.__cause__`.
    origem = getattr(exc, "orig", None)
    origem_real = getattr(origem, "__cause__", None) or origem
    nome_constraint = str(getattr(origem_real, "constraint_name", "") or "")
    nome_tabela = str(getattr(origem_real, "table_name", "") or "")
    sqlstate = str(getattr(origem_real, "sqlstate", "") or "")

    contexto = {"operacao": operacao, "constraint": nome_constraint, "tabela": nome_tabela}

    if nome_constraint in _EXCLUDE_VIGENCIA:
        return ErroDeAplicacao(
            "PONTO-VAL-010",
            detalhe="Ha vigencia sobreposta com um registro existente.",
            contexto_log=contexto,
        )
    if nome_constraint.startswith(_PREFIXOS_DUPLICADO):
        return ErroDeAplicacao(
            "PONTO-CONF-001",
            detalhe="Ja existe um registro com esses dados unicos neste escopo.",
            contexto_log=contexto,
        )
    if sqlstate == "23503":
        if ao_excluir:
            return ErroDeAplicacao(
                "PONTO-CONF-004",
                detalhe="O registro tem dependentes e nao pode ser removido.",
                contexto_log=contexto,
            )
        return ErroDeAplicacao(
            "PONTO-REC-001",
            detalhe="Referencia para um registro relacionado que nao existe.",
            contexto_log=contexto,
        )
    return ErroDeAplicacao(
        "PONTO-VAL-001",
        detalhe="A escrita viola uma restricao do cadastro.",
        contexto_log=contexto,
    )
