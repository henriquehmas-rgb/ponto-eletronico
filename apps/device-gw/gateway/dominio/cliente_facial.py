"""Cliente HTTP mTLS para o `facial-svc` (F14/A2, hardening).

**Por que este módulo existe sem nenhuma rota chamá-lo ainda.** Confirmado
por leitura de código nesta fase: NENHUM caminho do sistema hoje liga
`device-gw` a `facial-svc` de verdade -- `facial-svc/facial/rotas/
biometria.py` (`/enroll`, `/verificar`, `/liveness`) continua exatamente
como a Fase 0 deixou, `501 PONTO-INT-005`, nunca implementado por F2/F6/F8
apesar da leitura otimista do PCF da F14 (registrada em `docs/backlog.md`
desta sessão). O PCF de F14 pede "mTLS device-gw ↔ facial-svc" mesmo assim
(ADR-014: infraestrutura servidor-a-servidor, não bloqueada por F7) -- a
peça que FALTA não é a conexão em si (não existe o que proteger ainda), é a
CAPACIDADE de abrir uma conexão mTLS corretamente quando uma fase futura
(a que finalmente implementar `/verificar`/`/liveness` de verdade) precisar
dela. Este módulo entrega essa capacidade, testada isoladamente contra um
servidor TLS real (`tests/f14/hardening/test_mtls_facial_svc.py`).

**Falha fechada, não aberta.** `montar_cliente_facial_svc` RECUSA construir
um cliente quando qualquer um dos três caminhos (`facial_mtls_cert_path`/
`facial_mtls_key_path`/`facial_mtls_ca_path`) está ausente -- nunca cai
silenciosamente para uma conexão HTTP sem mTLS. Biometria é dado sensível
(ADR-006); um cliente que "funciona" sem apresentar certificado não é uma
conveniência de desenvolvimento aceitável para este par de serviços em
produção.
"""

from __future__ import annotations

import httpx

from gateway.config import Configuracao
from gateway.log import obter_logger

logger = obter_logger("dominio.cliente_facial")


class MtlsNaoConfigurado(RuntimeError):
    """`facial_mtls_cert_path`/`facial_mtls_key_path`/`facial_mtls_ca_path`
    incompletos -- ver docstring do módulo ("falha fechada")."""


def montar_cliente_facial_svc(
    config: Configuracao, *, timeout_s: float = 10.0
) -> httpx.AsyncClient:
    """`httpx.AsyncClient` apontado para `facial_svc_url`, apresentando o
    certificado de CLIENTE mTLS de `config` e verificando o certificado do
    SERVIDOR contra a CA configurada.

    Levanta `MtlsNaoConfigurado` (nunca constrói um cliente "degradado" sem
    mTLS) quando qualquer um dos três caminhos está ausente.
    """
    if not (
        config.facial_mtls_cert_path and config.facial_mtls_key_path and config.facial_mtls_ca_path
    ):
        raise MtlsNaoConfigurado(
            "facial_mtls_cert_path/facial_mtls_key_path/facial_mtls_ca_path "
            "precisam estar todos preenchidos para falar com o facial-svc."
        )
    return httpx.AsyncClient(
        base_url=config.facial_svc_url,
        timeout=timeout_s,
        cert=(config.facial_mtls_cert_path, config.facial_mtls_key_path),
        verify=config.facial_mtls_ca_path,
    )
