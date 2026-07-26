"""Biometria e dispositivos (Fase F2 / agente A3).

Credenciais biometricas (`biometrias` + `biometria_templates`), dispositivos
(`dispositivos` + `dispositivo_vinculos`) e o registro de acesso a dado
sensivel (`acessos_dados_sensiveis`) exigido pela LGPD.

Decisao fechada em `docs/adr/ADR-006-criptografia-ciclo-vida-template-biometrico.md`:
o vetor biometrico e cifrado em AES-256-GCM com envelope, chave mestra fora do
banco, AAD amarrado a tenant e colaborador, e nunca sai pela API.
"""

from __future__ import annotations
