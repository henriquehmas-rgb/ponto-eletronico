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

    # --- Banco -- sessao de SUPORTE da SEEG (bypass de RLS) ------------------
    #: Credencial da role `ponto_app_suporte` (LOGIN + BYPASSRLS, criada por
    #: `migrations/versions/0005_role_suporte_bypassrls.py`). Usada SOMENTE por
    #: `app/db/sessao_suporte.py`, que serve exclusivamente `listarTenants` e
    #: `criarTenant` -- nunca pelo `SessaoDb` do resto do sistema.
    #:
    #: `database_url_suporte` vazia (o normal) faz a URL ser derivada de
    #: `database_url` trocando so usuario e senha: em producao basta definir
    #: `POSTGRES_SUPORTE_PASSWORD`, a mesma variavel que a migration le para
    #: criar a role.
    database_url_suporte: str = ""
    postgres_suporte_password: SecretStr = SecretStr("")

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

    #: mTLS de cliente para falar com o `facial-svc`. Mesmos tres caminhos que
    #: `gateway.dominio.cliente_facial` ja usa no device-gw, e mesma postura do
    #: proprio `facial-svc` (`infra/docker-compose.prod.yml`): os tres juntos
    #: ligam mTLS de verdade; todos vazios sobem em HTTP puro, aceito SO fora de
    #: producao. Preenchimento PARCIAL e sempre erro -- ver
    #: `app.biometria.cliente_facial.montar_cliente_facial_svc`.
    facial_mtls_cert_path: str = ""
    facial_mtls_key_path: str = ""
    facial_mtls_ca_path: str = ""

    #: Teto de espera do `/enroll`. Medido em 0,7s p50 / 0,88s p90 na VPS de 8
    #: vCPU sem GPU (`docs/backlog.md`, 08/08); 8s cobre carregamento frio do
    #: modelo ONNX no primeiro pedido apos o container subir.
    facial_timeout_enroll_s: float = 8.0

    #: Teto de espera do `/verificar`. Menor que o do enroll de proposito: e o
    #: caminho quente de `POST /v1/marcacoes`, com uma pessoa esperando na
    #: frente do coletor. Estourar aqui NAO recusa a marcacao (ADR-008) -- ver
    #: `app.marcacao.pipeline.facial`.
    facial_timeout_verificar_s: float = 3.0

    #: Teto de espera do `/liveness`. Muito maior que o do `/verificar`, e o
    #: numero e MEDIDO, nao estimado: a operacao e multi-quadro (a deteccao roda
    #: uma vez por quadro, `facial/motor/liveness.py`), e sequencias de tres
    #: quadros contra o motor real na VPS de 8 vCPU sem GPU levaram de 3,9s a
    #: 10,6s (`docs/backlog.md`, 09/08 -- a variacao e a maquina compartilhada).
    #: O primeiro palpite, 6s, derrubava o sinal em metade das chamadas.
    #:
    #: 12s e teto de espera, nao latencia esperada, e estourar aqui NAO recusa a
    #: marcacao -- prova de vida heuristica e sinal de confianca, nunca portao
    #: (ADR-008; ver `app.marcacao.pipeline.facial`). Ainda assim, quem captura
    #: (F7/F8) e que decide o custo real: mandar tres quadros de rosto recortado
    #: em resolucao de camera, e nao a foto inteira ampliada, e o que mantem a
    #: chamada perto do piso da faixa.
    facial_timeout_liveness_s: float = 12.0

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

    # --- Hardening (F14/A2) ----------------------------------------------------
    #: Limite de taxa para SESSAO HUMANA (JWT), companion de
    #: `api_clients.rate_limit_por_minuto` (que so serve `ClienteAutenticado`,
    #: OAuth/API-key -- ver `app.comum.limitador_taxa.exigir_limite_taxa_sessao`).
    #: Nao existe coluna por usuario para isto hoje (RFC futura se precisar
    #: variar por perfil/tenant); um teto global e aditivo, nunca mais
    #: restritivo que o que ja funciona.
    rate_limit_sessao_por_minuto: int = 300

    #: Lista separada por virgula de IPs/CIDRs do(s) proxy(s) reverso(s) de
    #: producao (Traefik, `infra/docker-compose.yml`). `X-Forwarded-For`/
    #: `X-Real-IP` só sao aceitos quando o IP do socket imediato (o "peer" da
    #: conexao TCP que chega no processo) esta nesta lista -- caso contrario o
    #: cabecalho e ignorado e o IP do peer e usado como esta (nunca se confia
    #: cegamente num cabecalho que qualquer cliente pode forjar). Vazio (padrao
    #: de `dev`) desliga a confianca: todo `X-Forwarded-For` e ignorado.
    proxies_confiaveis: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lista_proxies_confiaveis(self) -> list[str]:
        """`proxies_confiaveis` normalizada em lista, sem entradas vazias."""
        return [ip.strip() for ip in self.proxies_confiaveis.split(",") if ip.strip()]

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
