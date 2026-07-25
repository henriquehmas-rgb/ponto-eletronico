"""Dominios de formato e apelidos de tipo usados pelos models.

`schema.sql` cria DOMINIOS do PostgreSQL para os formatos recorrentes do
dominio brasileiro (CPF, CNPJ, PIS, CEP, UF, IBGE, CBO, e-mail, SHA-256, fuso
e competencia de folha). Os models referenciam os mesmos dominios para que o
DDL gerado pelo Alembic saia identico ao contrato.

`create_type=False` em todos eles e deliberado: quem cria e destroi os dominios
e a migration inicial (`apps/api/migrations/versions/0001_inicial.py`), nunca o
`CREATE TABLE`. Sem isso o SQLAlchemy tentaria criar o dominio junto da
primeira tabela que o usa, sem a clausula CHECK, e o contrato ficaria mais
fraco do que schema.sql.

A validacao de digito verificador (CPF, CNPJ, PIS) e responsabilidade da
aplicacao (Fase 2). O dominio valida apenas o formato.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import DOMAIN

__all__ = [
    "DDL_DOMINIOS",
    "DOM_CBO",
    "DOM_CEP",
    "DOM_CNPJ",
    "DOM_COMPETENCIA",
    "DOM_CPF",
    "DOM_EMAIL",
    "DOM_FUSO",
    "DOM_IBGE",
    "DOM_PIS",
    "DOM_SHA256",
    "DOM_UF",
    "EXTENSOES",
    "NOMES_DOMINIOS",
]


def _dominio(nome: str, check: str) -> DOMAIN:
    return DOMAIN(nome, sa.TEXT(), check=check, create_type=False)


#: CPF em 11 digitos, sem pontuacao. Vai literalmente para o registro tipo 7 do AFD.
DOM_CPF = _dominio("dom_cpf", r"VALUE ~ '^[0-9]{11}$'")
#: CNPJ em 14 digitos, sem pontuacao.
DOM_CNPJ = _dominio("dom_cnpj", r"VALUE ~ '^[0-9]{14}$'")
#: PIS, PASEP ou NIT em 11 digitos, sem pontuacao.
DOM_PIS = _dominio("dom_pis", r"VALUE ~ '^[0-9]{11}$'")
#: CEP em 8 digitos, sem pontuacao.
DOM_CEP = _dominio("dom_cep", r"VALUE ~ '^[0-9]{8}$'")
#: Sigla da unidade federativa em 2 letras maiusculas.
DOM_UF = _dominio("dom_uf", r"VALUE ~ '^[A-Z]{2}$'")
#: Codigo IBGE do municipio em 7 digitos. Base dos feriados municipais.
DOM_IBGE = _dominio("dom_ibge", r"VALUE ~ '^[0-9]{7}$'")
#: Classificacao Brasileira de Ocupacoes, 6 digitos.
DOM_CBO = _dominio("dom_cbo", r"VALUE ~ '^[0-9]{6}$'")
#: Endereco de e-mail em formato minimo verificavel.
DOM_EMAIL = _dominio("dom_email", r"VALUE ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'")
#: Hash SHA-256 em hexadecimal (64 caracteres).
DOM_SHA256 = _dominio("dom_sha256", r"VALUE ~ '^[0-9a-fA-F]{64}$'")
#: Fuso horario IANA, por exemplo America/Sao_Paulo.
DOM_FUSO = _dominio("dom_fuso", r"VALUE ~ '^[A-Za-z]+/[A-Za-z_+-]+$'")
#: Competencia de folha no formato AAAA-MM.
DOM_COMPETENCIA = _dominio("dom_competencia", r"VALUE ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'")


#: Ordem de criacao dos dominios. A migration inicial usa esta lista.
DDL_DOMINIOS: tuple[tuple[str, str], ...] = tuple(
    (dominio.name, dominio.check)  # type: ignore[misc]
    for dominio in (
        DOM_CPF,
        DOM_CNPJ,
        DOM_PIS,
        DOM_CEP,
        DOM_UF,
        DOM_IBGE,
        DOM_CBO,
        DOM_EMAIL,
        DOM_SHA256,
        DOM_FUSO,
        DOM_COMPETENCIA,
    )
)

#: Nomes dos dominios, na ordem de criacao.
NOMES_DOMINIOS: tuple[str, ...] = tuple(nome for nome, _ in DDL_DOMINIOS)

#: Extensoes exigidas pelo contrato.
#:   pgcrypto    - gen_random_uuid(), digest(), crypt()
#:   uuid-ossp   - uuid_generate_v4() (compatibilidade)
#:   btree_gist  - EXCLUDE de vigencias combinando uuid + range
#:   pg_trgm     - busca por nome de colaborador
EXTENSOES: tuple[str, ...] = ("pgcrypto", "uuid-ossp", "btree_gist", "pg_trgm")
