"""Configuracao dos workers, lida do ambiente.

Os nomes das variaveis sao os mesmos do bloco `x-python-env` de
`infra/docker-compose.yml`: o worker compartilha `DATABASE_URL`, `REDIS_URL` e
`MINIO_*` com a API, porque processa o mesmo dado.

Nenhum segredo em codigo. `SecretStr` para o que nao pode aparecer em log.
"""

from __future__ import annotations

import functools
from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["dev", "ci", "hml", "prd"]
NivelLog = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
FormatoLog = Literal["json", "texto"]


class RedisDestino(BaseSettings):
    """Endereco do Redis quebrado em partes, como o ARQ exige."""

    host: str = "localhost"
    port: int = 6379
    database: int = 0
    senha: SecretStr = SecretStr("")


class Configuracao(BaseSettings):
    """Configuracao do processo de worker ou de scheduler."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    ambiente: Ambiente = "dev"
    tz: str = "America/Sao_Paulo"
    versao: str = "0.1.0"
    commit: str = ""
    otel_service_name: str = "ponto-worker"

    log_level: NivelLog = "INFO"
    log_formato: FormatoLog = "json"

    database_url: str = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"
    redis_url: str = "redis://localhost:6379/0"
    #: Segunda credencial de banco, SO leitura, com BYPASSRLS -- role
    #: `ponto_suporte` (`packages/contracts/schema.sql`, secao 20). Usada
    #: exclusivamente por `verificar_terminal_offline` (F6/T9) para enumerar
    #: terminais de TODOS os tenants antes de saber qual `app.tenant_id`
    #: aplicar -- ver RFC-013 (interino, opcao a, enquanto a RFC nao decide).
    #: Vazio cai para `database_url` (conveniencia de dev/teste apenas; em
    #: producao as duas credenciais precisam ser DIFERENTES).
    database_url_suporte: str = ""

    minio_endpoint: str = "localhost:9000"
    minio_access_key: SecretStr = SecretStr("")
    minio_secret_key: SecretStr = SecretStr("")
    minio_bucket: str = "ponto"
    minio_secure: bool = False

    api_base_url: str = "http://api:8000"

    #: URL interna do gateway Control iD (F6). `sincronizar_terminal`
    #: (`worker/tarefas/integracoes.py`) nao fala com o terminal
    #: diretamente: entrega o comando ao device-gw via
    #: `POST /interno/terminais/{numeroSerie}/comandos`, que enfileira para o
    #: proximo ciclo de Push. Mesmo default de hostname/porta interna que
    #: `api_base_url` usa para `api` -- o nome do servico no compose e
    #: `device-gw`, ouvindo 8000 dentro do container
    #: (`infra/docker-compose.yml`; `DEVICE_GW_PORT` so publica a porta
    #: externa, 8001, que este processo nunca usa).
    device_gw_base_url: str = "http://device-gw:8000"
    device_gw_timeout_s: float = 10.0

    #: Jobs simultaneos por processo. O compose entrega `ARQ_MAX_JOBS`.
    arq_max_jobs: int = 10
    #: Tentativas por job antes de virar falha definitiva.
    arq_max_tentativas: int = 3
    #: Prazo de execucao de um job, em segundos. Geracao de AFD de 12 meses e
    #: relatorio de 1.000 colaboradores sao operacoes longas por natureza.
    arq_timeout_job_s: int = 1800
    #: Quanto tempo o resultado fica no Redis depois de concluido.
    arq_retencao_resultado_s: int = 86_400

    cert_icp_path: str = ""
    cert_icp_senha: SecretStr = SecretStr("")
    inpi_numero: str = ""

    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis(self) -> RedisDestino:
        """`REDIS_URL` quebrada nas partes que o `RedisSettings` do ARQ pede."""
        partes = urlparse(self.redis_url)
        caminho = (partes.path or "/0").lstrip("/")
        return RedisDestino(
            host=partes.hostname or "localhost",
            port=partes.port or 6379,
            database=int(caminho or 0),
            senha=SecretStr(partes.password or ""),
        )


@functools.lru_cache(maxsize=1)
def obter_configuracao() -> Configuracao:
    """Configuracao do processo, resolvida uma unica vez."""
    return Configuracao()
