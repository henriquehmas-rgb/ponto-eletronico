"""Leitura de `acessos_dados_sensiveis` (F14/A3, `listarAcessosSensiveis`).

**A tabela ja e gravada por quem existe hoje.** Confirmado por leitura de
codigo antes de escrever qualquer linha deste modulo (PCF secao 5, "A3 --
LGPD" pede exatamente essa confirmacao):

* `app/biometria/servico.py::_registrar_acesso` grava toda leitura de
  credencial biometrica e toda decifragem de template (`obterBiometria`,
  `ler_template_decifrado`) desde a F2.
* `app/core/seguranca.py::exigir_permissao` grava GENERICAMENTE, para
  QUALQUER rota protegida por uma permissao marcada `sensivel=true` no
  catalogo (`permissoes.sensivel`, semeado por
  `apps/api/migrations/seed_dev.py`), via
  `app/identidade/auditoria/hash_chain.py::registrar_acesso_sensivel_generico`
  -- inclusive `lgpd.ler`/`lgpd.criar`/`lgpd.excluir` (linha
  `("auditoria", "lgpd", (CRIAR, EXCLUIR, LER), True, ...)` do catalogo), o
  que cobre `listarConsentimentos`/`listarSolicitacoesTitular` desta mesma
  fase sem nenhum codigo adicional aqui.
* `app/relatorios/datasets/gerenciais.py`, `app/jornada/calendario/
  afastamentos.py`, `app/jornada/resolvedor/servico.py`,
  `app/integracoes/webhooks/seguranca.py` e `app/routers/marcacoes.py`
  tambem ja gravam pontos proprios (finalidades diferentes de biometria --
  documento, saude, geolocalizacao).

Conclusao (achado do PCF, "confirme primeiro"): a tabela **ja estava
instrumentada** antes desta fase, em varios modulos de fases anteriores mais
o mecanismo generico de F1/A3. Este modulo so EXPOE a leitura via API --
nenhuma instrumentacao nova foi necessaria.

Este modulo tambem NAO se auto-audita: ler `listarAcessosSensiveis` nao
grava uma nova linha em `acessos_dados_sensiveis` alem da que o mecanismo
generico de `exigir_permissao` (acima) ja grava para o exercicio de
`lgpd.ler` em si -- gravar uma segunda vez aqui seria duplicata do mesmo
evento, nao um acesso a mais.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import AcessoDadoSensivel
from sqlalchemy.ext.asyncio import AsyncSession

from app.lgpd.comum import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    normalizar_limite,
)

__all__ = ["CAMPOS_ORDENACAO_ACESSO_SENSIVEL", "listar_acessos_sensiveis"]

CAMPOS_ORDENACAO_ACESSO_SENSIVEL = frozenset({"ocorridoEm"})


async def listar_acessos_sensiveis(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    colaborador_id: UUID | None,
    categoria: str | None,
    acao: str | None,
    de: datetime | None,
    ate: datetime | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> tuple[list[AcessoDadoSensivel], bool, str | None]:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_ACESSO_SENSIVEL, padrao="ocorridoEm"
    )
    mapa = {"ocorridoEm": CampoOrdenacao(AcessoDadoSensivel.ocorrido_em, lambda v: v)}

    consulta = sa.select(AcessoDadoSensivel).where(AcessoDadoSensivel.tenant_id == tenant_id)
    if usuario_id is not None:
        consulta = consulta.where(AcessoDadoSensivel.usuario_id == usuario_id)
    if colaborador_id is not None:
        consulta = consulta.where(AcessoDadoSensivel.colaborador_id == colaborador_id)
    if categoria is not None:
        consulta = consulta.where(AcessoDadoSensivel.categoria == categoria)
    if acao is not None:
        consulta = consulta.where(AcessoDadoSensivel.acao == acao)
    if de is not None:
        consulta = consulta.where(AcessoDadoSensivel.ocorrido_em >= de)
    if ate is not None:
        consulta = consulta.where(AcessoDadoSensivel.ocorrido_em <= ate)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=mapa[ordenacao.campo],
        coluna_id=AcessoDadoSensivel.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    proximo: str | None = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo = codificar_cursor(ordenacao, ultimo.ocorrido_em, ultimo.id)
    return list(linhas), tem_mais, proximo
