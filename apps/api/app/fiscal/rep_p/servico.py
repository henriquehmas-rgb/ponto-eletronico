"""`criarRepP`/`listarRepPs` (T1/T7, F12/A1).

`criarRepP` cria a linha de `rep_ps` e a linha correspondente de
`nsr_sequencias` (`proximo_nsr=1`, `ultimo_nsr_emitido=0`) NA MESMA
transação — é o cadastro que `app.marcacao.dominio.nsr.alocar_nsr` (F5)
pressupõe já existir para todo REP-P (ver a docstring de `alocar_nsr`:
"Não há linha em `nsr_sequencias` para o REP-P (nunca deveria acontecer: o
cadastro do REP-P, feito pela F12, é quem a cria)").

**Achado de contrato, decisão documentada (não invenção silenciosa):**
`RepPCriar.cnpjDesenvolvedor`/`razaoSocialDesenvolvedor` NÃO são
`required` no schema (`packages/contracts/openapi.yaml`,
`ExemploRepPCriar` também não os inclui), mas `rep_ps.cnpj_desenvolvedor`/
`razao_social_desenvolvedor` SÃO `NOT NULL` no banco
(`packages/contracts/schema.sql` seção 8). O exemplo de resposta
`ExemploRepP` do próprio contrato preenche os dois com o CNPJ da SEEG
(`60258502000149`, confirmado como o CNPJ real da SEEG por
`docs/BRIEFING-IDENTIDADE-VISUAL.md`) — o desenvolvedor do REP-P é sempre a
SEEG, para qualquer empresa (tenant) que opere o software, então quando o
chamador não informa esses dois campos este serviço preenche com a
identidade fixa da SEEG (constantes abaixo), em vez de rejeitar a
requisição por um campo que o próprio exemplo do contrato trata como
opcional.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import NsrSequencia, RepP
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.fiscal.rep_p.erros_bd import traduzir_integridade
from app.fiscal.rep_p.paginacao import (
    CampoOrdenacao,
    Ordenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

#: Identidade fixa da SEEG como desenvolvedora do REP-P — mesmo CNPJ usado
#: em `ExemploRepP`/`ExemploListaRepP` (`packages/contracts/openapi.yaml`)
#: e no exemplo de `afd.gerado` (`packages/contracts/events.yaml`).
_SEEG_CNPJ: Final[str] = "60258502000149"
_SEEG_RAZAO_SOCIAL: Final[str] = "SEEG Servicos de Tecnologia da Informacao LTDA"

_CAMPOS_ORDENACAO_REP_P: Final[frozenset[str]] = frozenset({"identificador", "dataInicioOperacao"})


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


def rep_p_para_contrato(
    rep_p: RepP, *, proximo_nsr: int | None, ultimo_nsr_emitido: int | None
) -> esquemas.RepP:
    """`RepP.proximoNsr`/`ultimoNsrEmitido` são "projeção somente leitura do
    alocador transacional" (`nsr_sequencias`) — não existem como coluna do
    ORM `RepP`, então nunca vêm de `model_validate(rep_p, from_attributes=True)`
    sozinho; este helper sempre os junta explicitamente."""
    modelo = esquemas.RepP.model_validate(rep_p, from_attributes=True)
    return modelo.model_copy(
        update={"proximo_nsr": proximo_nsr, "ultimo_nsr_emitido": ultimo_nsr_emitido}
    )


async def criar_rep_p(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.RepPCriar,
    *,
    usuario_id: UUID | None,
) -> esquemas.RepP:
    """Cadastra o REP-P e inicializa `nsr_sequencias` (`proximo_nsr=1`,
    `ultimo_nsr_emitido=0`) na mesma transação. `numeroInpi` já chega
    validado pelo Pydantic (`pattern=^[0-9]+$`, `required`) — este serviço
    não repete a validação de formato, só a persiste.

    Não commita: o commit é responsabilidade de quem abriu a sessão
    (`app.db.sessao.obter_sessao`, uma transação por requisição — mesmo
    padrão que `app.workflow.fechamento.servico.criar_fechamento` já usa).
    Commitar aqui dentro quebraria um chamador que precisasse fazer mais
    alguma coisa na mesma transação antes de finalizar."""
    rep_p = RepP(
        tenant_id=tenant_id,
        empresa_id=dados.empresa_id,
        identificador=dados.identificador,
        tipo=_valor(dados.tipo) or "rep_p",
        numero_inpi=dados.numero_inpi,
        cnpj_desenvolvedor=dados.cnpj_desenvolvedor or _SEEG_CNPJ,
        razao_social_desenvolvedor=dados.razao_social_desenvolvedor or _SEEG_RAZAO_SOCIAL,
        cnpj_empregador=dados.cnpj_empregador,
        razao_social_empregador=dados.razao_social_empregador,
        cei_caepf=dados.cei_caepf,
        versao_programa=dados.versao_programa,
        data_inicio_operacao=dados.data_inicio_operacao,
        data_fim_operacao=dados.data_fim_operacao,
        status=_valor(dados.status) or "ativo",
        criado_por=usuario_id,
    )
    sessao.add(rep_p)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao="PONTO-CONF-001") from exc

    sequencia = NsrSequencia(
        tenant_id=tenant_id,
        rep_p_id=rep_p.id,
        proximo_nsr=1,
        ultimo_nsr_emitido=0,
        criado_por=usuario_id,
    )
    sessao.add(sequencia)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao="PONTO-CONF-001") from exc

    return rep_p_para_contrato(rep_p, proximo_nsr=1, ultimo_nsr_emitido=0)


async def listar_rep_ps(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[RepP], dict[UUID, NsrSequencia], esquemas.Paginacao]:
    """Lista REP-P com os filtros do contrato (`empresaId`, `status`),
    paginação por cursor (mesmo padrão de outras listagens do projeto).
    Devolve também um mapa `rep_p_id -> NsrSequencia` para o chamador
    montar `proximoNsr`/`ultimoNsrEmitido` sem uma segunda viagem ao banco
    por item."""
    ordenacao: Ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=_CAMPOS_ORDENACAO_REP_P, padrao="dataInicioOperacao"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(RepP).where(RepP.tenant_id == tenant_id, RepP.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(RepP.empresa_id == empresa_id)
    if status is not None:
        consulta = consulta.where(RepP.status == status)

    campo = (
        CampoOrdenacao(coluna=RepP.identificador, conversor=str)
        if ordenacao.campo == "identificador"
        else CampoOrdenacao(coluna=RepP.data_inicio_operacao, conversor=str)
    )
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=RepP.id,
        cursor=cursor,
        limite=limite_efetivo,
    )

    sequencias: dict[UUID, NsrSequencia] = {}
    if linhas:
        resultado_sequencias = await sessao.execute(
            sa.select(NsrSequencia).where(
                NsrSequencia.tenant_id == tenant_id,
                NsrSequencia.rep_p_id.in_([linha.id for linha in linhas]),
            )
        )
        sequencias = {seq.rep_p_id: seq for seq in resultado_sequencias.scalars().all()}

    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        valor_ordenacao = (
            ultima.identificador
            if ordenacao.campo == "identificador"
            else ultima.data_inicio_operacao
        )
        proximo_cursor = codificar_cursor(ordenacao, valor_ordenacao, ultima.id)

    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, sequencias, paginacao
