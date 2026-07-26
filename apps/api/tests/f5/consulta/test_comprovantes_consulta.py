"""Testes de `app/marcacao/comprovantes/consulta.py` e do router
`app/routers/comprovantes.py` (T11, agente A3).

Cobre: comprovante emitido ha 50h nao aparece na janela padrao de 48h mas
aparece com `horas=72`; `Accept: text/plain` devolve o corpo textual cru e
`application/json` devolve o schema `Comprovante` completo.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from fastapi.responses import PlainTextResponse
from ponto_contracts import Comprovante as ComprovanteOrm
from ponto_contracts import Marcacao as MarcacaoOrm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.marcacao.comprovantes import consulta as consulta_comprovantes
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from app.routers.comprovantes import obter_comprovante
from app.schemas import contrato
from tests.f5.conftest import ContextoF5


def _sujeito(contexto: ContextoF5) -> Sujeito:
    # `alcance=None` (padrao): `exigir_alcance` fica permissivo, e sem
    # `usuarios` casando `usuario_id` o caminho de "proprio colaborador" e
    # falso -- exercita o ramo de alcance amplo, nao o de auto-acesso.
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"comprovantes.ler"}),
    )


async def _criar_marcacao(sessao: AsyncSession, contexto: ContextoF5) -> MarcacaoOrm:
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
            datahora_marcacao=dt.datetime.now(tz=dt.UTC),
            dispositivo_id=contexto.dispositivo_id,
        ),
    )


async def _criar_comprovante(
    sessao: AsyncSession, marcacao: MarcacaoOrm, *, emitido_em: dt.datetime
) -> ComprovanteOrm:
    """Insere o comprovante direto pelo ORM, com `emitido_em` explicito --
    `emitir_comprovante` (T8) sempre usa o `now()` do servidor, e aqui
    precisamos simular um comprovante antigo. INSERT nao e bloqueado pelo
    gatilho de imutabilidade (so UPDATE/DELETE/TRUNCATE); nenhum teste desta
    fase tenta alterar a linha depois de criada."""
    numero = f"{emitido_em:%Y%m%d}{marcacao.nsr:08d}"
    conteudo_texto = f"COMPROVANTE DE TESTE\nNSR: {marcacao.nsr}\nCPF: {marcacao.cpf}"
    comprovante = ComprovanteOrm(
        tenant_id=marcacao.tenant_id,
        marcacao_id=marcacao.id,
        marcacao_datahora=marcacao.datahora_marcacao,
        colaborador_id=marcacao.colaborador_id,
        cpf=marcacao.cpf,
        numero=numero,
        nsr=marcacao.nsr,
        conteudo_texto=conteudo_texto,
        hash_sha256=hashlib.sha256(conteudo_texto.encode("utf-8")).hexdigest(),
        canal_entrega="app",
        emitido_em=emitido_em,
    )
    sessao.add(comprovante)
    await sessao.flush()
    return comprovante


async def test_comprovante_50h_fora_da_janela_padrao_mas_aparece_com_72h(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao = await _criar_marcacao(sessao_f5, contexto_f5)
    emitido_ha_50h = dt.datetime.now(tz=dt.UTC) - dt.timedelta(hours=50)
    comprovante = await _criar_comprovante(sessao_f5, marcacao, emitido_em=emitido_ha_50h)
    sujeito = _sujeito(contexto_f5)

    pagina_padrao = await consulta_comprovantes.listar_comprovantes_recentes(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        sujeito=sujeito,
        colaborador_id=contexto_f5.colaborador_id,
    )
    assert comprovante.id not in {item.id for item in pagina_padrao.dados}

    pagina_72h = await consulta_comprovantes.listar_comprovantes_recentes(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        sujeito=sujeito,
        colaborador_id=contexto_f5.colaborador_id,
        horas=72,
    )
    assert comprovante.id in {item.id for item in pagina_72h.dados}


async def test_obter_comprovante_accept_text_plain_devolve_texto_cru(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao = await _criar_marcacao(sessao_f5, contexto_f5)
    comprovante = await _criar_comprovante(
        sessao_f5, marcacao, emitido_em=dt.datetime.now(tz=dt.UTC)
    )
    sujeito = _sujeito(contexto_f5)

    resposta_texto = await obter_comprovante(
        comprovante_id=comprovante.id,
        sujeito=sujeito,
        sessao=sessao_f5,
        accept="text/plain",
    )
    assert isinstance(resposta_texto, PlainTextResponse)
    corpo = resposta_texto.body
    assert isinstance(corpo, bytes)
    assert corpo.decode("utf-8") == comprovante.conteudo_texto

    resposta_json = await obter_comprovante(
        comprovante_id=comprovante.id,
        sujeito=sujeito,
        sessao=sessao_f5,
        accept="application/json",
    )
    assert isinstance(resposta_json, contrato.Comprovante)
    assert resposta_json.conteudo_texto == comprovante.conteudo_texto
    assert resposta_json.numero == comprovante.numero

    resposta_sem_accept = await obter_comprovante(
        comprovante_id=comprovante.id,
        sujeito=sujeito,
        sessao=sessao_f5,
    )
    assert isinstance(resposta_sem_accept, contrato.Comprovante)
    assert resposta_sem_accept.numero == comprovante.numero
