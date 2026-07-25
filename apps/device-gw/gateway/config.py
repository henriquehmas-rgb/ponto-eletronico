"""Configuracao do device-gw, lida do ambiente por pydantic-settings.

Os nomes das variaveis sao exatamente os declarados para o servico `device-gw`
em `infra/docker-compose.yml` (bloco `x-python-env` mais o bloco proprio de
`CONTROLID_*`). A leitura e case-insensitive: o campo `controlid_senha` le
`CONTROLID_SENHA`.

Regra inegociavel do projeto: **nenhum segredo e versionado**. Toda credencial
chega por variavel de ambiente (ver `infra/.env.example`), e os campos sensiveis
usam `SecretStr` para nao vazarem em `repr`, log ou tela de erro. Duas delas
merecem atencao especial:

* `CONTROLID_SENHA` — senha do usuario administrativo do terminal. Quem a tem
  cadastra face, apaga `access_log` e abre porta.
* `CONTROLID_PUSH_TOKEN` — segredo compartilhado que o equipamento apresenta ao
  chamar `dev.ponto.<dominio>`. E o unico fator que separa um terminal legitimo
  de qualquer um na internet postando marcacao.

Valores padrao existem para que o servico **carregue** numa maquina limpa, sem
`.env` — e o que permite `python -c "from gateway.main import app"` funcionar no
CI. Eles nao servem para producao: o compose exige as variaveis obrigatorias com
`${VAR:?}` e falha cedo se faltarem.
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
    """Configuracao completa do processo do device-gw."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identidade do processo ----------------------------------------------
    ambiente: Ambiente = "dev"
    debug: bool = False
    tz: str = "America/Sao_Paulo"
    versao: str = "0.1.0"
    commit: str = Field(default="", description="SHA da build, injetado no Dockerfile.")
    otel_service_name: str = "ponto-device-gw"

    # --- Log ------------------------------------------------------------------
    log_level: NivelLog = "INFO"
    log_formato: FormatoLog = "json"

    # --- Dependencias compartilhadas com a API --------------------------------
    database_url: str = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_saude_s: float = 3.0

    #: URL interna da API. O gateway nao grava marcacao: ele converte o
    #: `access_log` do terminal e entrega para a API atribuir NSR e persistir.
    api_base_url: str = "http://api:8000"
    api_timeout_saude_s: float = 3.0

    # --- Control iD -----------------------------------------------------------
    #: Usuario administrativo usado em `login.fcgi`.
    controlid_usuario: str = "admin"
    controlid_senha: SecretStr = SecretStr("")
    #: Prazo de cada chamada `*.fcgi` ao terminal. Terminal em LAN saturada
    #: responde devagar; prazo longo demais segura conexao do gateway a toa.
    controlid_timeout_s: int = 10
    #: Segredo compartilhado apresentado pelo equipamento no modo Push.
    controlid_push_token: SecretStr = SecretStr("")
    #: `true` usa o simulador embutido em vez de hardware (padrao em dev).
    controlid_simulador: bool = False

    #: Quantos `access_logs` o catch-up pede por pagina em `load_objects.fcgi`.
    #: O iDFace pagina; pedir tudo de uma vez em um terminal com 30 dias de
    #: backlog estoura a memoria do equipamento, nao a nossa.
    catchup_tamanho_pagina: int = 1000
    #: Minutos sem contato para o scheduler considerar o terminal offline. O
    #: valor final e por terminal e por modo de comunicacao (F6); este e o piso.
    terminal_offline_minutos: int = 15

    # --- Observabilidade -------------------------------------------------------
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def producao(self) -> bool:
        """Verdadeiro em homologacao e producao: endurece defaults de seguranca."""
        return self.ambiente in ("hml", "prd")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def push_token_configurado(self) -> bool:
        """Ha segredo de Push definido?

        Em `prd` e `hml`, ausencia de token e configuracao invalida: qualquer um
        conseguiria postar `access_log` na rota publica. A F6 transforma isto em
        recusa de subida; na Fase 0 o dado apenas aparece em `/ready`.
        """
        return bool(self.controlid_push_token.get_secret_value())


@functools.lru_cache(maxsize=1)
def obter_configuracao() -> Configuracao:
    """Configuracao do processo, resolvida uma unica vez.

    O cache existe para que a leitura do ambiente aconteca no import e nao a
    cada requisicao. Em teste, use `obter_configuracao.cache_clear()` depois de
    mexer em `os.environ`.
    """
    return Configuracao()
