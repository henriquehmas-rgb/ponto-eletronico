"""Tradução de violação de integridade do banco para o catálogo de erros,
cópia própria do domínio `fechamento` (mesmo padrão de `app.apuracao.
tratamento.erros_bd`/`app.pessoas.erros_bd`, nunca importado de outra fase).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (idêntico ao de `packages/contracts/models/fechamento.py`
#: e `schema.sql` seção 12) -> código do catálogo. Só as constraints que
#: `periodos`/`fechamentos`/`espelhos`/`assinaturas_espelho` podem violar em
#: tempo de escrita.
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_periodos_codigo": "PONTO-CONF-001",
    "ck_periodos_intervalo": "PONTO-VAL-007",
    "periodos_tipo_check": "PONTO-VAL-001",
    "periodos_status_check": "PONTO-VAL-001",
    "ck_fechamentos_reabertura": "PONTO-PER-003",
    "fechamentos_escopo_check": "PONTO-VAL-001",
    "fechamentos_status_check": "PONTO-VAL-001",
    "uq_espelhos_versao": "PONTO-CONF-001",
    "espelhos_tipo_check": "PONTO-VAL-001",
    # "Espelho ja assinado" (o codigo especifico que `assinarEspelho` declara
    # em `x-erros`, mais preciso que o generico PONTO-CONF-001 para esta
    # unique index -- ver `errors.yaml` categoria FISC).
    "uq_assinaturas_espelho": "PONTO-FISC-007",
    "assinaturas_espelho_metodo_check": "PONTO-VAL-001",
    "assinaturas_espelho_signatario_tipo_check": "PONTO-VAL-001",
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
