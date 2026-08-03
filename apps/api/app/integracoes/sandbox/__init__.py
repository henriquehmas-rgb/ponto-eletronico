"""Sandbox de demonstracao da API publica (F13, T8, agente A2).

Semeia UM tenant de demonstracao inteiramente sintetico (empresa, unidade,
REP-P, colaboradores, vinculos e marcacoes) mais um usuario administrador de
demonstracao com a unica permissao necessaria para o portal de desenvolvedor
(`/desenvolvedores`, T7) provisionar, em nome do visitante, um `ApiClient`
`ambiente='sandbox'` de verdade via `POST /v1/admin/api-clients` (A1, T2) e
emitir um token contra ele via `POST /v1/auth/token` (F1, ja implementado).

Este pacote NUNCA cria `api_clients`/`oauth_tokens` diretamente: quem cria e
sempre a rota real do contrato, chamada pelo proxy do portal
(`apps/web/src/app/desenvolvedores/api/sandbox/route.ts`) em nome do usuario
administrador de demonstracao que este pacote semeia. Isso mantem a garantia
"cliente de sandbox nunca acessa dados de producao" (events.yaml, campo
`ambiente` do envelope) como consequencia estrutural de o tenant de
demonstracao ser um tenant genuinamente separado, isolado por Row Level
Security como qualquer outro -- nao como uma regra especial que este pacote
precisaria impor.

Nota de ownership (PCF F13 secao 5.2, linha A2): `apps/api/app/integracoes/
__init__.py` e criacao exclusiva de A1 ("unico criador"). Este subpacote nao
o toca; se ele ainda nao existir quando este modulo for importado, `app.
integracoes` funciona como pacote de namespace implicito (PEP 420) -- `app.
integracoes.sandbox` continua importavel normalmente.

Deliberadamente SEM reexportar `semear_tenant_sandbox`/`ResultadoSemeadura`
aqui: reexportar faria `python -m app.integracoes.sandbox.semear` importar o
modulo duas vezes (uma pelo pacote, outra pelo `runpy`), o que o proprio
Python avisa como comportamento imprevisivel. Importe direto de
`app.integracoes.sandbox.semear`.
"""

from __future__ import annotations
