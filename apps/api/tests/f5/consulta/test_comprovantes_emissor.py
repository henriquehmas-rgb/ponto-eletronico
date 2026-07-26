"""Testes de `app/marcacao/comprovantes/emissor.py` e
`eventos_comprovante.py` (T8, agente A3).

Cobre: `numero` unico mesmo com duas marcacoes no mesmo dia (NSRs diferentes);
o payload de `comprovante.emitido` validado campo a campo contra
`packages/contracts/events.yaml`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from ponto_contracts import Marcacao as MarcacaoOrm
from sqlalchemy.ext.asyncio import AsyncSession

from app.marcacao.comprovantes.emissor import emitir_comprovante
from app.marcacao.comprovantes.eventos_comprovante import (
    NOME_COMPROVANTE_EMITIDO,
    VERSAO_COMPROVANTE_EMITIDO,
    publicar_comprovante_emitido,
)
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from tests.f5.conftest import ContextoF5


async def _criar_marcacao(
    sessao: AsyncSession, contexto: ContextoF5, *, datahora: dt.datetime
) -> MarcacaoOrm:
    return await persistir_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        dados=DadosMarcacao(
            rep_p_id=contexto.rep_p_id,
            empresa_id=contexto.empresa_id,
            unidade_id=contexto.unidade_id,
            colaborador_id=contexto.colaborador_id,
            vinculo_id=contexto.vinculo_id,
            cpf=contexto.colaborador_cpf,
            canal="mobile",
            datahora_marcacao=datahora,
            dispositivo_id=contexto.dispositivo_id,
        ),
    )


async def test_numero_unico_para_duas_marcacoes_no_mesmo_dia(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    hoje_meio_dia = dt.datetime.now(tz=dt.UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    marcacao_1 = await _criar_marcacao(sessao_f5, contexto_f5, datahora=hoje_meio_dia)
    marcacao_2 = await _criar_marcacao(
        sessao_f5, contexto_f5, datahora=hoje_meio_dia + dt.timedelta(minutes=1)
    )
    assert marcacao_1.nsr != marcacao_2.nsr

    comprovante_1 = await emitir_comprovante(sessao_f5, marcacao_1)
    comprovante_2 = await emitir_comprovante(sessao_f5, marcacao_2)

    assert comprovante_1.numero != comprovante_2.numero
    # Tenant com um unico REP-P (o caso desta fixture): formato sem prefixo,
    # AAAAMMDD + NSR em 8 digitos, identico ao exemplo de events.yaml.
    assert comprovante_1.numero.endswith(f"{marcacao_1.nsr:08d}")
    assert comprovante_2.numero.endswith(f"{marcacao_2.nsr:08d}")
    assert len(comprovante_1.numero) == 16
    assert comprovante_1.hash_sha256 != comprovante_2.hash_sha256


async def test_payload_comprovante_emitido_bate_com_o_contrato(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao = await _criar_marcacao(sessao_f5, contexto_f5, datahora=dt.datetime.now(tz=dt.UTC))
    comprovante = await emitir_comprovante(sessao_f5, marcacao)

    envelope = publicar_comprovante_emitido(
        tenant_id=contexto_f5.tenant_id,
        comprovante_id=comprovante.id,
        marcacao_id=marcacao.id,
        colaborador_id=contexto_f5.colaborador_id,
        numero=comprovante.numero,
        nsr=comprovante.nsr,
        emitido_em=comprovante.emitido_em,
        hash_sha256=comprovante.hash_sha256,
        canal_entrega=comprovante.canal_entrega,
    )

    # Envelope: id, tipo, versao, ocorridoEm, tenantId, dados (os 5 `required`
    # de `events.yaml`), mais publicadoEm (opcional, sempre emitido aqui).
    assert uuid.UUID(envelope["id"])
    assert envelope["tipo"] == NOME_COMPROVANTE_EMITIDO == "comprovante.emitido"
    assert envelope["versao"] == VERSAO_COMPROVANTE_EMITIDO == 1
    assert envelope["ocorridoEm"] == comprovante.emitido_em.isoformat()
    assert envelope["tenantId"] == str(contexto_f5.tenant_id)
    assert "publicadoEm" in envelope

    dados = envelope["dados"]
    # `required` de events.yaml para comprovante.emitido: comprovanteId,
    # marcacaoId, colaboradorId, numero, nsr, emitidoEm, hashSha256.
    assert dados["comprovanteId"] == str(comprovante.id)
    assert dados["marcacaoId"] == str(marcacao.id)
    assert dados["colaboradorId"] == str(contexto_f5.colaborador_id)
    assert dados["numero"] == comprovante.numero
    assert dados["nsr"] == comprovante.nsr
    assert dados["emitidoEm"] == comprovante.emitido_em.isoformat()
    assert dados["hashSha256"] == comprovante.hash_sha256
    assert dados["canalEntrega"] == comprovante.canal_entrega
