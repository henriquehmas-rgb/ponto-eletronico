"""Servico de dominio de `escala_atribuicoes`: `atribuirEscalaVinculo`.

Unico verbo desta subrota -- **nao existe** listagem de historico de
atribuicao de escala no contrato (PCF da fase, secao 3/9). A escala vem do
path (`/v1/escalas/{escalaId}/atribuicoes`); o `escalaId` opcional do corpo
(`EscalaAtribuicaoCriar.escalaId`) e ignorado como fonte da FK -- o path e
quem manda, exatamente como o contrato desenha a rota.
"""

from __future__ import annotations

from uuid import UUID

from ponto_contracts import EscalaAtribuicao
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.modelagem.erros_bd import traduzir_integridade
from app.jornada.modelagem.escalas import obter_escala
from app.jornada.modelagem.fechamento import verificar_periodo_aberto
from app.jornada.modelagem.vinculo_jornadas import obter_vinculo
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"


async def atribuir_escala_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    escala_id: UUID,
    dados: esquemas.EscalaAtribuicaoCriar,
) -> EscalaAtribuicao:
    await obter_escala(sessao, escala_id)
    vinculo = await obter_vinculo(sessao, dados.vinculo_id)

    await verificar_periodo_aberto(
        sessao,
        tenant_id,
        empresa_id=vinculo.empresa_id,
        data=dados.vigencia_inicio,
        unidade_id=vinculo.unidade_id,
        departamento_id=vinculo.departamento_id,
    )

    campos = dados.model_dump(exclude_unset=True, exclude={"vinculo_id", "escala_id"})
    atribuicao = EscalaAtribuicao(
        tenant_id=tenant_id, vinculo_id=vinculo.id, escala_id=escala_id, **campos
    )
    sessao.add(atribuicao)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return atribuicao
