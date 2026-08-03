"""Configuracao da API, lida do ambiente por pydantic-settings.

Regra inegociavel do projeto: **nenhum segredo e versionado**. Toda credencial
chega por variavel de ambiente (ver `infra/.env.example`), e os campos sensiveis
usam `SecretStr` para nao vazarem em `repr`, log ou tela de erro.

Os nomes das variaveis sao os mesmos declarados em `infra/docker-compose.yml`
(bloco `x-python-env`). A leitura e case-insensitive: o campo `database_url` le
`DATABASE_URL`.

Valores padrao existem para que a aplicacao **carregue** numa maquina limpa, sem
`.env` e sem banco -- e o que permite `python -c "from app.main import app"`
funcionar em CI. Eles nao servem para producao: o compose exige as variaveis
obrigatorias com `${VAR:?}` e falha cedo se faltarem.
"""

from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["dev", "ci", "hml", "prd"]
NivelLog = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
FormatoLog = Literal["json", "texto"]


class Configuracao(BaseSettings):
    """Configuracao completa do processo da API."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identidade do processo ---------------------------------------------
    ambiente: Ambiente = "dev"
    debug: bool = False
    tz: str = "America/Sao_Paulo"
    versao: str = "0.1.0"
    commit: str = Field(default="", description="SHA da build, injetado no Dockerfile.")
    otel_service_name: str = "ponto-api"

    # --- Log -----------------------------------------------------------------
    log_level: NivelLog = "INFO"
    log_formato: FormatoLog = "json"

    # --- Banco ---------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_s: int = 30
    database_echo: bool = False
    database_timeout_saude_s: float = 3.0

    # --- Fila e cache ---------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_saude_s: float = 3.0

    # --- Objetos --------------------------------------------------------------
    minio_endpoint: str = "localhost:9000"
    minio_access_key: SecretStr = SecretStr("")
    minio_secret_key: SecretStr = SecretStr("")
    minio_bucket: str = "ponto"
    minio_secure: bool = False

    # --- Chaves e certificados -------------------------------------------------
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    cert_icp_path: str = ""
    cert_icp_senha: SecretStr = SecretStr("")
    inpi_numero: str = ""

    # --- Servicos internos -----------------------------------------------------
    facial_svc_url: str = "http://facial-svc:8000"
    device_gw_url: str = "http://device-gw:8000"

    # --- URLs publicas ----------------------------------------------------------
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    docs_base_url: str = "http://localhost:8000/docs"

    # --- Multi-tenant -------------------------------------------------------------
    #: Sufixo de host usado para inferir o tenant pelo subdominio
    #: (`seeg.ponto.seeg.com.br` -> tenant `seeg`).
    dominio_tenants: str = "ponto.seeg.com.br"
    cabecalho_tenant: str = "X-Tenant"
    cabecalho_request_id: str = "X-Request-Id"

    # --- HTTP -----------------------------------------------------------------------
    #: Lista separada por virgula. Nao e `list[str]` de proposito: o compose
    #: entrega uma string simples, e `list` faria o pydantic exigir JSON.
    cors_origens: str = "http://localhost:3000"
    raiz_api: str = "/"

    # --- Observabilidade --------------------------------------------------------------
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    # --- SSO -- OIDC (F13/A9, RFC-018/ADR-013) --------------------------------------
    #: App OAuth/OIDC COMPARTILHADO da aplicacao (um par por provedor, nunca por
    #: tenant -- ADR-013). A restricao por tenant e so a allowlist guardada em
    #: `tenant_configuracoes` (`sso.google.dominios_permitidos`/`sso.entra_id.tenant_id`).
    sso_google_client_id: str = ""
    sso_google_client_secret: SecretStr = SecretStr("")
    sso_entra_client_id: str = ""
    sso_entra_client_secret: SecretStr = SecretStr("")
    #: Chave simetrica (HS256) que assina o `state` anti-CSRF do fluxo OIDC
    #: (`app.identidade.sso.oidc.estado`). Nao e o mesmo par RS256 do access
    #: token: o `state` e curto (10 min) e so este processo precisa validá-lo.
    sso_estado_chave_secreta: SecretStr = SecretStr("")

    # --- SSO -- SAML 2.0 (F13/A10, RFC-018/ADR-013) ---------------------------------
    #: Chave simetrica (HS256) que assina o RelayState do fluxo SAML
    #: (`app.identidade.sso.saml.estado`). Mesma familia da chave OIDC acima
    #: (curta, 5 min, so este processo valida), mas campo proprio: o RelayState
    #: carrega tenant_id + o ID do AuthnRequest (correlacao InResponseTo), que o
    #: `state` OIDC nao tem. Nunca e o certificado X.509 do IdP (esse e dado
    #: publico do tenant, vive em `tenant_configuracoes`, nunca aqui).
    sso_saml_estado_chave: SecretStr = SecretStr("")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lista_cors_origens(self) -> list[str]:
        """`cors_origens` normalizada em lista, sem entradas vazias."""
        return [origem.strip() for origem in self.cors_origens.split(",") if origem.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def producao(self) -> bool:
        """Verdadeiro em homologacao e producao: endurece defaults de seguranca."""
        return self.ambiente in ("hml", "prd")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expor_documentacao(self) -> bool:
        """O portal OpenAPI fica publico; `docs.ponto.<dominio>` depende disso."""
        return True


@functools.lru_cache(maxsize=1)
def obter_configuracao() -> Configuracao:
    """Configuracao do processo, resolvida uma unica vez.

    O cache existe para que a leitura do ambiente aconteca no import da
    aplicacao e nao a cada requisicao. Em teste, use
    `obter_configuracao.cache_clear()` depois de mexer em `os.environ`.
    """
    return Configuracao()
