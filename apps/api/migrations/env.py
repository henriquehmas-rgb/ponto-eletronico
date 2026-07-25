"""Ambiente de migracao do Alembic.

O `target_metadata` e a `Base.metadata` do pacote `ponto-contracts`
(`packages/contracts/models`), que espelha `packages/contracts/schema.sql`. E
por isso que `alembic revision --autogenerate` funciona: a fonte da verdade do
modelo e o contrato, nao o banco.

Resolucao da URL (nesta ordem, primeira que existir vence):

1. ``alembic -x url=postgresql+psycopg://...``
2. ``DATABASE_URL_SYNC``
3. ``DATABASE_URL`` (driver assincrono e convertido para o sincrono equivalente)

Nenhum segredo e lido de arquivo versionado.

O que o autogenerate NAO enxerga, e que por isso vive escrito a mao na
migration inicial: extensoes, dominios, funcoes PL/pgSQL, particionamento de
`marcacoes`, gatilhos de imutabilidade, gatilhos de `atualizado_em`, policies
de Row Level Security, roles e privilegios. Ao gerar uma revisao nova, confira
se algum desses objetos precisa acompanhar a mudanca.
"""

from __future__ import annotations

import os
import pathlib
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Importacao dos models
#
# Em ambiente normal o pacote esta instalado (`pip install -e packages/contracts`).
# O fallback por sys.path existe para que a migration rode tambem em um checkout
# cru, sem instalacao previa - situacao comum em pipeline de CI recem-criado.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - caminho feliz
    from ponto_contracts import Base
except ModuleNotFoundError:  # pragma: no cover - fallback de checkout cru
    RAIZ_MONOREPO = pathlib.Path(__file__).resolve().parents[3]
    CAMINHO_CONTRATOS = RAIZ_MONOREPO / "packages" / "contracts"
    if not (CAMINHO_CONTRATOS / "models" / "__init__.py").exists():
        raise
    sys.path.insert(0, str(CAMINHO_CONTRATOS))
    # `assignment` alem de `no-redef`: com `ponto-contracts` instalado, o mypy
    # enxerga as duas origens do mesmo modulo (`ponto_contracts.base.Base` e
    # `models.base.Base`) e as trata como tipos distintos. Em execucao so uma
    # das duas linhas roda.
    from models import Base  # type: ignore[no-redef,assignment]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# URL do banco
# ---------------------------------------------------------------------------
_DRIVERS_ASSINCRONOS = {
    "postgresql+asyncpg": "postgresql+psycopg",
    "postgresql+psycopg_async": "postgresql+psycopg",
    "postgres+asyncpg": "postgresql+psycopg",
}


def _para_driver_sincrono(url: str) -> str:
    """Troca o driver assincrono pelo sincrono equivalente.

    O Alembic roda sobre uma conexao sincrona. A aplicacao usa asyncpg; manter
    duas variaveis de ambiente separadas seria uma pegadinha, entao converte-se
    aqui.
    """
    for assincrono, sincrono in _DRIVERS_ASSINCRONOS.items():
        if url.startswith(assincrono + "://"):
            return sincrono + url[len(assincrono) :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def resolve_url() -> str:
    """Descobre a URL do banco. Falha alto e claro quando nao ha nenhuma."""
    argumentos = context.get_x_argument(as_dictionary=True)
    url = (
        argumentos.get("url")
        or os.getenv("DATABASE_URL_SYNC")
        or os.getenv("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )
    if not url:
        raise RuntimeError(
            "URL do banco nao definida. Informe DATABASE_URL_SYNC, DATABASE_URL "
            "ou rode com `alembic -x url=postgresql+psycopg://usuario:senha@host/base`."
        )
    return _para_driver_sincrono(url)


def incluir_objeto(objeto, nome, tipo, reflexivo, objeto_comparado) -> bool:
    """Mantem as particoes mensais de `marcacoes` fora do autogenerate.

    As particoes sao criadas em tempo de execucao por
    `fn_cria_particao_marcacoes()`; se o autogenerate as enxergasse, produziria
    um `drop_table` para cada mes a cada revisao nova.
    """
    if tipo == "table" and nome is not None and nome.startswith("marcacoes_"):
        return nome == "marcacoes_meta"
    return True


def executar_migracoes_offline() -> None:
    """Modo offline: emite SQL em vez de conectar (`alembic upgrade head --sql`)."""
    context.configure(
        url=resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        include_object=incluir_objeto,
        version_table="alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


def executar_migracoes_online() -> None:
    """Modo online: abre conexao e aplica as migracoes."""
    secao = config.get_section(config.config_ini_section) or {}
    secao["sqlalchemy.url"] = resolve_url()

    conectavel = engine_from_config(
        secao,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with conectavel.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
            include_object=incluir_objeto,
            transaction_per_migration=True,
            version_table="alembic_version",
        )
        with context.begin_transaction():
            context.run_migrations()

    conectavel.dispose()


if context.is_offline_mode():
    executar_migracoes_offline()
else:
    executar_migracoes_online()
