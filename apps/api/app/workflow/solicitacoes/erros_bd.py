"""Tradução de violação de integridade do banco para o catálogo de erros,
cópia própria do domínio `workflow.solicitacoes` (mesmo padrão de
`app.apuracao.tratamento.erros_bd`/`app.pessoas.erros_bd`, nunca importado
de outra fase).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (idêntico ao de `packages/contracts/models`) -> código
#: do catálogo. Só as constraints que `tipos_solicitacao`/`solicitacoes`
#: podem violar em tempo de escrita (seção 11 do `schema.sql`).
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_tipos_solicitacao_codigo": "PONTO-CONF-001",
    "uq_solicitacoes_protocolo": "PONTO-CONF-001",
    "tipos_solicitacao_categoria_check": "PONTO-VAL-001",
    "tipos_solicitacao_prazo_resposta_horas_check": "PONTO-VAL-001",
    "tipos_solicitacao_escalonar_apos_horas_check": "PONTO-VAL-001",
    "tipos_solicitacao_permite_retroativo_dias_check": "PONTO-VAL-001",
    "solicitacoes_status_check": "PONTO-VAL-001",
    "solicitacoes_etapa_atual_check": "PONTO-VAL-001",
    "ck_solicitacoes_periodo": "PONTO-VAL-007",
    "tipos_solicitacao_tipo_tratamento_id_fkey": "PONTO-REC-001",
    "solicitacoes_tipo_solicitacao_id_fkey": "PONTO-REC-001",
    "solicitacoes_colaborador_id_fkey": "PONTO-REC-001",
    "solicitacoes_vinculo_id_fkey": "PONTO-REC-001",
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
