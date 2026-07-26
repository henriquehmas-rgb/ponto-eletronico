"""Traducao de violacao de integridade do banco para o catalogo de erros.

O Postgres recusa a linha antes de qualquer regra de aplicacao rodar de novo
(unicidade, `EXCLUDE`, `CHECK`) -- e a ultima linha de defesa, nao a primeira.
Este modulo devolve o `ErroDeAplicacao` correspondente ao nome da constraint
violada, para que a resposta HTTP saia com o codigo certo do catalogo em vez
de um 500 generico.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (identico ao de `packages/contracts/models`) -> codigo
#: do catalogo. So constraints que as tabelas desta fase (pessoas) podem
#: violar em tempo de escrita.
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_colaboradores_matricula": "PONTO-CONF-001",
    "uq_colaboradores_cpf": "PONTO-CONF-001",
    "uq_vinculos_matricula_esocial": "PONTO-CONF-001",
    "uq_equipes_codigo": "PONTO-CONF-001",
    "ex_vinculos_sobreposicao": "PONTO-VAL-010",
    "ex_colaborador_gestores_imediato": "PONTO-VAL-010",
    "ex_equipe_membros_sobreposicao": "PONTO-VAL-010",
    "ck_colaborador_gestores_distintos": "PONTO-CONF-003",
    "ck_contratos_dispensa": "PONTO-VAL-001",
    "ck_contratos_periodo": "PONTO-VAL-007",
    "ck_vinculos_periodo": "PONTO-VAL-007",
    "ck_colaborador_gestores_vigencia": "PONTO-VAL-007",
}


def _nome_constraint(origem: BaseException) -> str | None:
    """Extrai o nome da constraint do erro nativo do driver.

    `asyncpg` preenche `constraint_name` a partir do campo de diagnostico do
    protocolo do Postgres; quando o atributo nao esta presente (driver
    diferente, ou excecao ja reembalada), cai para busca textual na mensagem
    -- os nomes de constraint deste projeto sao sempre explicitos (nunca
    gerados pela convencao automatica do banco), entao aparecem literalmente
    na mensagem de erro.
    """
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    """Converte `IntegrityError` no `ErroDeAplicacao` do codigo correspondente.

    `padrao` e usado quando a constraint nao e reconhecida -- acontece se uma
    migration futura acrescentar uma constraint nova sem atualizar este mapa;
    nesse caso preferimos um 409 generico de conflito a um 500, e o
    `contexto_log` guarda o nome real para investigacao.
    """
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
