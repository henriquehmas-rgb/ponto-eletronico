"""Regra de negocio da tag `lgpd` (F14/A3).

Consentimento versionado, direitos do titular (acesso, correcao,
portabilidade, eliminacao) e leitura do registro de acesso a dado sensivel.

A cifra do template biometrico (AES-256-GCM, `app.biometria.cifra`) e da F2
(ADR-006) e nao e reescrita aqui -- este pacote so decide QUANDO expurgar
(revogacao de consentimento, politica de retencao vencida) e chama o que ja
existe para apagar o texto cifrado.
"""

from __future__ import annotations
