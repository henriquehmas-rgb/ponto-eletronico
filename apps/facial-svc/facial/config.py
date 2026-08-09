"""Configuracao do facial-svc, lida do ambiente por pydantic-settings.

Os nomes das variaveis sao exatamente os declarados para o servico `facial-svc`
em `infra/docker-compose.yml`. Repare no que **nao** esta aqui: este servico nao
recebe `DATABASE_URL`, `REDIS_URL` nem credencial de MinIO — diferente de `api`,
`worker` e `device-gw`, ele nao entra no bloco `x-python-env`.

A ausencia e deliberada e vale mais que um paragrafo de politica: um servico que
nao tem credencial de banco nao pode vazar banco, mesmo comprometido. Ele recebe
imagem, devolve vetor e nao guarda nada. Quem persiste (cifrado) e a API.
"""

from __future__ import annotations

import functools
import pathlib
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["dev", "ci", "hml", "prd"]
NivelLog = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
FormatoLog = Literal["json", "texto"]


class Configuracao(BaseSettings):
    """Configuracao completa do processo do facial-svc."""

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
    otel_service_name: str = "ponto-facial-svc"

    # --- Log ------------------------------------------------------------------
    log_level: NivelLog = "INFO"
    log_formato: FormatoLog = "json"

    # --- Motor facial ----------------------------------------------------------
    #: Diretorio dos pesos ONNX dentro do container. E o volume `facial-models`
    #: do compose: os pesos sao grandes, ficam fora do git e sao montados em
    #: tempo de execucao. Diretorio vazio significa servico que sobe e nao serve.
    facial_model_dir: str = "/models"

    #: Versao do modelo em uso. **Fica gravada em cada enrollment** para permitir
    #: troca de motor sem perder rastreabilidade (ADR-006, item 3): vetores de
    #: versoes diferentes nao sao comparaveis entre si, e sem esse carimbo a
    #: troca de motor invalidaria silenciosamente a base biometrica inteira.
    #:
    #: O default deixou de ser `arcface-r100-v1` quando o motor passou a existir
    #: de verdade: o reconhecedor do pacote `buffalo_l` e o `w600k_r50` (ArcFace
    #: ResNet**50** treinado em WebFace600K), e nao um R100. Carimbo que descreve
    #: um modelo que nao e o carregado e pior que carimbo nenhum — ele mente com
    #: aparencia de rastreabilidade.
    facial_model_versao: str = "buffalo_l-w600k_r50-v1"

    #: Pacote de modelos do InsightFace. `buffalo_l` = RetinaFace `det_10g` +
    #: ArcFace `w600k_r50` (512-d), licenca aberta, roda em CPU.
    facial_modelo_pacote: str = "buffalo_l"

    #: Baixar os pesos na primeira execucao quando faltarem no volume.
    #: **Desligado por padrao, e proibido em producao** (ver o validador abaixo):
    #: em producao os pesos chegam pelo volume `facial-models`, versionados junto
    #: com o deploy. Uma marcacao de ponto nao pode disparar um download de
    #: ~300 MB, e um servico que busca peso na internet em tempo de execucao
    #: depende de um repositorio de terceiro para funcionar.
    facial_baixar_modelo: bool = False

    #: Lado (px) da entrada do detector. 640 e o default do InsightFace e o ponto
    #: de equilibrio entre alcance e custo de CPU.
    facial_det_size: int = Field(default=640, ge=128, le=1920)

    #: Confianca minima do detector para considerar que ha um rosto.
    facial_det_thresh: float = Field(default=0.5, ge=0.0, le=1.0)

    #: Quadros minimos para julgar prova de vida. Dois e o piso conceitual: prova
    #: de vida sobre imagem estatica unica e ilusao de seguranca — nem foto
    #: impressa nem video em tela sao detectaveis de forma confiavel num quadro so.
    facial_liveness_min_quadros: int = Field(default=2, ge=2, le=32)

    #: Limiar de similaridade para aceitar o par. Calibrado por cliente: a
    #: relacao entre falso positivo e falso negativo nao e a mesma numa portaria
    #: com 30 pessoas e num chao de fabrica com 3.000.
    #: **Nunca aparece em resposta de API** (`PONTO-SCORE-003` tem
    #: `expoe_regra: false`).
    facial_limiar_similaridade: float = Field(default=0.42, ge=0.0, le=1.0)

    #: CA para mTLS entre os chamadores internos e este servico. Vazio desliga o
    #: mTLS — aceitavel so em `dev`. A F7 promove ausencia em `prd` a recusa
    #: (`ciclo_de_vida`, `main.py`, decisao original da Fase 0 -- nao alterada
    #: por F14/A2: o QUE conta como "recusar" continua adiado, o MECANISMO em
    #: si e que passa a existir de verdade a partir daqui).
    facial_mtls_ca_path: str = ""

    #: Certificado/chave que ESTE servico apresenta como servidor TLS (F14/A2,
    #: hardening). Os tres campos (`facial_tls_cert_path`/`facial_tls_key_path`/
    #: `facial_mtls_ca_path`) juntos ligam o mTLS de verdade em `facial.servidor`
    #: -- qualquer um vazio, o processo sobe em HTTP puro, exatamente como hoje
    #: (nenhuma regressao: o comportamento so muda quando os tres sao providos).
    facial_tls_cert_path: str = ""
    facial_tls_key_path: str = ""

    #: Tamanho maximo da imagem aceita, em bytes. Acima disso a resposta e
    #: `PONTO-VAL-008` antes de qualquer decodificacao: decodificar imagem
    #: enviada por cliente nao confiavel e superficie de ataque classica.
    facial_tamanho_maximo_bytes: int = 5 * 1024 * 1024

    #: Tipos de imagem aceitos. Fora da lista, `PONTO-VAL-009`.
    facial_tipos_aceitos: str = "image/jpeg,image/png,image/webp"

    # --- Observabilidade -------------------------------------------------------
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    @model_validator(mode="after")
    def _download_nao_vale_em_producao(self) -> Configuracao:
        """`FACIAL_BAIXAR_MODELO` e recusado em `hml`/`prd`.

        Nao e preferencia de estilo. Ligado em producao, o servico passa a
        depender de um repositorio de terceiro estar no ar para que uma marcacao
        de ponto funcione, e passa a aceitar como valido qualquer peso que aquele
        repositorio sirva no dia — inclusive um substituido. Em producao os pesos
        chegam pelo volume `facial-models`, junto com o deploy.
        """
        if self.ambiente in ("hml", "prd") and self.facial_baixar_modelo:
            raise ValueError(
                "FACIAL_BAIXAR_MODELO nao pode ser verdadeiro em hml/prd: "
                "popule o volume `facial-models` no deploy."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def producao(self) -> bool:
        """Verdadeiro em homologacao e producao: endurece defaults de seguranca."""
        return self.ambiente in ("hml", "prd")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mtls_configurado(self) -> bool:
        """Verdadeiro só quando os TRÊS caminhos de mTLS estão preenchidos
        (F14/A2) -- `facial.servidor` só liga TLS/mTLS de verdade neste caso;
        caso contrário sobe em HTTP puro, mesmo comportamento de sempre."""
        return bool(
            self.facial_tls_cert_path and self.facial_tls_key_path and self.facial_mtls_ca_path
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lista_tipos_aceitos(self) -> list[str]:
        """`facial_tipos_aceitos` normalizada em lista, sem entradas vazias."""
        return [tipo.strip() for tipo in self.facial_tipos_aceitos.split(",") if tipo.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def modelos_presentes(self) -> bool:
        """Ha ao menos um arquivo `.onnx` no diretorio de modelos?

        E a unica dependencia dura deste servico. Um facial-svc sem pesos sobe,
        responde `/health` e reprova em `/ready` — que e exatamente o
        comportamento desejado: o container nao entra em *crash loop*, e quem
        estiver depurando ve na hora que o volume `facial-models` esta vazio.
        """
        diretorio = pathlib.Path(self.facial_model_dir)
        if not diretorio.is_dir():
            return False
        return any(diretorio.glob("**/*.onnx"))


@functools.lru_cache(maxsize=1)
def obter_configuracao() -> Configuracao:
    """Configuracao do processo, resolvida uma unica vez.

    Em teste, use `obter_configuracao.cache_clear()` depois de mexer em
    `os.environ`.
    """
    return Configuracao()
