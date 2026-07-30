"""Testes de `app.workflow.fechamento.espelho` (T7, F10/A2).

Cobre os critérios "pronto quando": a soma dos totais do `conteudo` bate
com os totais das colunas; gerar um segundo espelho `oficial` para o mesmo
período/vínculo cria `versao=2` sem apagar `versao=1` (e vira
`tipo='retificado'`); o PDF gerado contém os campos mínimos exigidos (nome
do colaborador, período, totais) -- teste de conteúdo textual extraído do
PDF, não só "gerou bytes".

**Primeira integração real com MinIO desta base de código** (PCF §2.5): os
testes que passam `gerar_pdf=True` exercitam `app.comum.armazenamento` de
verdade contra o MinIO do ambiente de verificação. Credenciais vêm das
mesmas variáveis `MINIO_*` que `app.core.config.Configuracao` já lê (nunca
hardcoded aqui) -- defina `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/
`MINIO_SECRET_KEY`/`MINIO_BUCKET`/`MINIO_SECURE` no ambiente antes de rodar.
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from ponto_contracts import ApuracaoDia, Espelho, Periodo
from pypdf import PdfReader

from app.workflow.fechamento.espelho import gerar_espelho_do_vinculo
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


async def _semear_apuracoes(sessao, contexto: ContextoF10, periodo: Periodo) -> None:
    """Duas apurações reais no período, valores conhecidos para o teste de
    soma de totais."""
    dia1 = periodo.data_inicio
    dia2 = periodo.data_inicio + dt.timedelta(days=1)
    sessao.add_all(
        [
            ApuracaoDia(
                tenant_id=contexto.tenant_id,
                vinculo_id=contexto.vinculo_id,
                colaborador_id=contexto.colaborador_id,
                data=dia1,
                empresa_id=contexto.empresa_id,
                tipo_dia="util",
                previsto_minutos=480,
                trabalhado_minutos=480,
                extras_minutos=30,
                extras_noturnas_minutos=0,
                falta_minutos=0,
                noturno_minutos=0,
                noturno_ficta_minutos=0,
                saldo_minutos=30,
                status="apurado",
            ),
            ApuracaoDia(
                tenant_id=contexto.tenant_id,
                vinculo_id=contexto.vinculo_id,
                colaborador_id=contexto.colaborador_id,
                data=dia2,
                empresa_id=contexto.empresa_id,
                tipo_dia="util",
                previsto_minutos=480,
                trabalhado_minutos=420,
                extras_minutos=0,
                extras_noturnas_minutos=0,
                falta_minutos=60,
                noturno_minutos=15,
                noturno_ficta_minutos=0,
                saldo_minutos=-60,
                status="apurado",
            ),
        ]
    )
    await sessao.flush()


@pytest.mark.asyncio
async def test_conteudo_totais_batem_com_colunas(sessao_f10, contexto_f10: ContextoF10) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

    espelho = await gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "previo",
        usuario_id=contexto_f10.rh_usuario_id,
    )

    totais = espelho.conteudo["totais"]
    assert totais["previstoMinutos"] == espelho.total_previsto_minutos == 960
    assert totais["trabalhadoMinutos"] == espelho.total_trabalhado_minutos == 900
    assert totais["extrasMinutos"] == espelho.total_extras_minutos == 30
    assert totais["faltasMinutos"] == espelho.total_faltas_minutos == 60
    assert totais["noturnoMinutos"] == espelho.total_noturno_minutos == 15
    assert espelho.hash_sha256 is not None
    assert len(espelho.hash_sha256) == 64


@pytest.mark.asyncio
async def test_segundo_oficial_cria_versao_2_retificado_sem_apagar_versao_1(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

    primeiro = await gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert primeiro.versao == 1
    assert primeiro.tipo == "oficial"
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    segundo = await gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert segundo.versao == 2
    assert segundo.tipo == "retificado"

    # A versao 1 continua intacta.
    ainda_existe = await sessao_f10.get(Espelho, primeiro.id)
    assert ainda_existe is not None
    assert ainda_existe.versao == 1
    assert ainda_existe.tipo == "oficial"


@pytest.mark.asyncio
async def test_pdf_gerado_contem_campos_minimos_e_grava_no_minio(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

    espelho = await gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        gerar_pdf=True,
        usuario_id=contexto_f10.rh_usuario_id,
    )

    assert espelho.conteudo_ref
    assert espelho.conteudo_ref.startswith(f"espelhos/{contexto_f10.tenant_id}/")

    from app.comum.armazenamento import obter_objeto

    pdf_bytes = await obter_objeto(espelho.conteudo_ref)
    assert pdf_bytes[:4] == b"%PDF"

    leitor = PdfReader(io.BytesIO(pdf_bytes))
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    assert "Colaborador de Teste F10" in texto
    assert "Empresa de Teste F10 Ltda" in texto
    assert periodo.data_inicio.isoformat() in texto
    assert periodo.data_fim.isoformat() in texto
    assert "960" in texto  # total previsto
    assert espelho.hash_sha256 in texto
