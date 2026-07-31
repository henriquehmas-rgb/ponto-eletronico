"""Testes de `app.fiscal.cofre.consulta` (F12/A3, T12).

Cobre: `listarAfd`/`listarAej` (filtros, paginação); `obterAfd`/`obterAej`
(inclusive `PONTO-REC-001` para id inexistente); `baixarAfd` devolvendo
bytes IDÊNTICOS aos gravados (round-trip sem transformação -- "pronto
quando" do PCF) e o pacote `.zip` com `incluirAssinatura=true`; a ausência
de `baixar_aej` (não existe `GET /v1/fiscal/aej/{arquivoId}/download` no
contrato -- confirmado lendo `openapi.yaml`, não presumido)."""

from __future__ import annotations

import datetime as dt
import io
import uuid
import zipfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.fiscal.assinatura import servico as assinatura_servico
from app.fiscal.assinatura.certificado import CertificadoConfig
from app.fiscal.cofre import consulta
from app.schemas import contrato as esquemas
from tests.f12.assinatura.conftest import ContextoF12A3
from tests.f12.cofre.conftest import ContextoCofre


def test_openapi_nao_declara_download_de_aej() -> None:
    """Confirma, lendo o contrato real (não por memória), que só o AFD tem
    download bruto -- este módulo não deve (e não implementa) `baixar_aej`."""
    from pathlib import Path

    import yaml

    raiz = Path(__file__).resolve().parents[5]
    caminho_openapi = raiz / "packages" / "contracts" / "openapi.yaml"
    documento = yaml.safe_load(caminho_openapi.read_text(encoding="utf-8"))
    caminhos = documento["paths"]
    assert "/v1/fiscal/afd/{arquivoId}/download" in caminhos
    assert "/v1/fiscal/aej/{arquivoId}/download" not in caminhos
    assert not hasattr(consulta, "baixar_aej")


@pytest.mark.asyncio
async def test_obter_afd_e_aej(sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre) -> None:
    tenant_id = contexto_cofre.contexto.tenant_id
    afd = await consulta.obter_afd(sessao_f12_a3, tenant_id, contexto_cofre.afd.id)
    assert afd.id == contexto_cofre.afd.id
    assert afd.nome_arquivo == "AFD_TESTE_COFRE.txt"

    aej = await consulta.obter_aej(sessao_f12_a3, tenant_id, contexto_cofre.aej.id)
    assert aej.id == contexto_cofre.aej.id


@pytest.mark.asyncio
async def test_obter_afd_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta.obter_afd(sessao_f12_a3, contexto_f12_a3.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_obter_aej_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta.obter_aej(sessao_f12_a3, contexto_f12_a3.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_listar_afd_encontra_pelo_rep_p_e_periodo(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    linhas, paginacao = await consulta.listar_afd(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        rep_p_id=contexto_cofre.contexto.rep_p_id,
    )
    assert any(linha.id == contexto_cofre.afd.id for linha in linhas)
    assert paginacao.limite == 50  # LIMITE_PADRAO de app.fiscal.cofre.paginacao

    # Filtro de data que NAO cobre o periodo do arquivo -> lista vazia.
    linhas_fora, _ = await consulta.listar_afd(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        de=dt.date(2099, 1, 1),
    )
    assert not any(linha.id == contexto_cofre.afd.id for linha in linhas_fora)


@pytest.mark.asyncio
async def test_listar_afd_filtra_por_status(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    linhas_gerado, _ = await consulta.listar_afd(
        sessao_f12_a3, contexto_cofre.contexto.tenant_id, status="gerado"
    )
    assert any(linha.id == contexto_cofre.afd.id for linha in linhas_gerado)

    linhas_assinado, _ = await consulta.listar_afd(
        sessao_f12_a3, contexto_cofre.contexto.tenant_id, status="assinado"
    )
    assert not any(linha.id == contexto_cofre.afd.id for linha in linhas_assinado)


@pytest.mark.asyncio
async def test_listar_aej_por_empresa(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    linhas, _ = await consulta.listar_aej(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        empresa_id=contexto_cofre.contexto.empresa_id,
    )
    assert any(linha.id == contexto_cofre.aej.id for linha in linhas)


@pytest.mark.asyncio
async def test_baixar_afd_devolve_bytes_identicos(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    conteudo, content_type, nome = await consulta.baixar_afd(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        contexto_cofre.afd.id,
        incluir_assinatura=False,
        usuario_id=contexto_cofre.contexto.usuario_id,
        ip="203.0.113.5",
        user_agent="pytest",
    )
    assert conteudo == contexto_cofre.conteudo_afd
    assert content_type.startswith("text/plain")
    assert nome == contexto_cofre.afd.nome_arquivo


@pytest.mark.asyncio
async def test_baixar_afd_sem_assinatura_ainda_devolve_arquivo_isolado_quando_incluir_assinatura(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    """Decisao de design documentada em `consulta.py`: sem assinatura ainda
    gravada, `incluirAssinatura=true` nao produz erro, devolve o AFD
    isolado."""
    conteudo, content_type, _ = await consulta.baixar_afd(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        contexto_cofre.afd.id,
        incluir_assinatura=True,
        usuario_id=contexto_cofre.contexto.usuario_id,
        ip=None,
        user_agent=None,
    )
    assert conteudo == contexto_cofre.conteudo_afd
    assert content_type.startswith("text/plain")


@pytest.mark.asyncio
async def test_baixar_afd_com_assinatura_devolve_zip_com_os_dois_arquivos(
    sessao_f12_a3: AsyncSession,
    contexto_cofre: ContextoCofre,
    certificado_teste: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assinatura_servico, "obter_certificado_configurado", lambda: certificado_teste
    )
    assinatura = await assinatura_servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        contexto_cofre.afd.id,
        esquemas.AssinaturaArquivoRequisicao.model_validate({"tipoArquivo": "afd"}),
        usuario_id=contexto_cofre.contexto.usuario_id,
    )

    conteudo, content_type, nome = await consulta.baixar_afd(
        sessao_f12_a3,
        contexto_cofre.contexto.tenant_id,
        contexto_cofre.afd.id,
        incluir_assinatura=True,
        usuario_id=contexto_cofre.contexto.usuario_id,
        ip="203.0.113.5",
        user_agent="pytest",
    )

    assert content_type == "application/zip"
    assert nome.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        nomes = set(pacote.namelist())
        assert contexto_cofre.afd.nome_arquivo in nomes
        assert f"{contexto_cofre.afd.nome_arquivo}.p7s" in nomes
        assert pacote.read(contexto_cofre.afd.nome_arquivo) == contexto_cofre.conteudo_afd

    assert assinatura.status == "assinado"


@pytest.mark.asyncio
async def test_baixar_afd_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta.baixar_afd(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            uuid.uuid4(),
            incluir_assinatura=False,
            usuario_id=contexto_f12_a3.usuario_id,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_baixar_afd_sem_conteudo_ref_e_fisc_006(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    from ponto_contracts import AfdArquivo

    afd = AfdArquivo(
        tenant_id=contexto_f12_a3.tenant_id,
        empresa_id=contexto_f12_a3.empresa_id,
        rep_p_id=contexto_f12_a3.rep_p_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nsr_inicial=1,
        nsr_final=1,
        total_registros=1,
        nome_arquivo="AFD_SEM_CONTEUDO_COFRE.txt",
        conteudo_ref=None,
        status="gerado",
    )
    sessao_f12_a3.add(afd)
    await sessao_f12_a3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await consulta.baixar_afd(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            afd.id,
            incluir_assinatura=False,
            usuario_id=contexto_f12_a3.usuario_id,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-FISC-006"


@pytest.mark.asyncio
async def test_listar_afd_filtra_por_empresa_e_por_ate(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    tenant_id = contexto_cofre.contexto.tenant_id
    linhas, _ = await consulta.listar_afd(
        sessao_f12_a3, tenant_id, empresa_id=contexto_cofre.contexto.empresa_id
    )
    assert any(linha.id == contexto_cofre.afd.id for linha in linhas)

    linhas_ate, _ = await consulta.listar_afd(sessao_f12_a3, tenant_id, ate=dt.date(2026, 7, 31))
    assert any(linha.id == contexto_cofre.afd.id for linha in linhas_ate)

    linhas_ate_fora, _ = await consulta.listar_afd(
        sessao_f12_a3, tenant_id, ate=dt.date(2026, 1, 1)
    )
    assert not any(linha.id == contexto_cofre.afd.id for linha in linhas_ate_fora)


@pytest.mark.asyncio
async def test_listar_aej_filtra_por_periodo_de_ate_e_status(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    tenant_id = contexto_cofre.contexto.tenant_id
    aej_id = contexto_cofre.aej.id

    # `periodo_id` da fixture é `None` (nunca setado) -- filtrar por um UUID
    # aleatório de verdade (não `None`) é o que exercita a cláusula
    # `WHERE periodo_id = ...` de `listar_aej` (o `if periodo_id is not
    # None` só entra nesse ramo com um valor real); a fixture não referencia
    # nenhum período, então a lista vem vazia, o que já é a prova correta de
    # que o filtro filtrou.
    linhas_periodo_aleatorio, _ = await consulta.listar_aej(
        sessao_f12_a3, tenant_id, periodo_id=uuid.uuid4()
    )
    assert not any(linha.id == aej_id for linha in linhas_periodo_aleatorio)

    linhas_de, _ = await consulta.listar_aej(sessao_f12_a3, tenant_id, de=dt.date(2026, 7, 1))
    assert any(linha.id == aej_id for linha in linhas_de)

    linhas_ate, _ = await consulta.listar_aej(sessao_f12_a3, tenant_id, ate=dt.date(2026, 7, 31))
    assert any(linha.id == aej_id for linha in linhas_ate)

    linhas_ate_fora, _ = await consulta.listar_aej(
        sessao_f12_a3, tenant_id, ate=dt.date(2026, 1, 1)
    )
    assert not any(linha.id == aej_id for linha in linhas_ate_fora)

    linhas_status, _ = await consulta.listar_aej(sessao_f12_a3, tenant_id, status="gerado")
    assert any(linha.id == aej_id for linha in linhas_status)


@pytest.mark.asyncio
async def test_listar_afd_pagina_de_verdade_com_cursor(
    sessao_f12_a3: AsyncSession, contexto_cofre: ContextoCofre
) -> None:
    """Cria um segundo AFD no mesmo tenant/REP-P e força `limite=1` para
    que `tem_mais=True` e `_proximo_cursor` monte um cursor de verdade --
    depois usa esse cursor para buscar a segunda página e confirma que os
    dois AFD aparecem, um por página, sem repetição."""
    from ponto_contracts import AfdArquivo

    segundo = AfdArquivo(
        tenant_id=contexto_cofre.contexto.tenant_id,
        empresa_id=contexto_cofre.contexto.empresa_id,
        rep_p_id=contexto_cofre.contexto.rep_p_id,
        periodo_inicio=dt.date(2026, 8, 1),
        periodo_fim=dt.date(2026, 8, 31),
        nsr_inicial=2,
        nsr_final=2,
        total_registros=1,
        nome_arquivo="AFD_SEGUNDO.txt",
        conteudo_ref="fiscal/teste/nao-importa.txt",
        status="gerado",
        gerado_em=dt.datetime.now(dt.UTC),
    )
    sessao_f12_a3.add(segundo)
    await sessao_f12_a3.flush()

    tenant_id = contexto_cofre.contexto.tenant_id
    pagina1, paginacao1 = await consulta.listar_afd(
        sessao_f12_a3, tenant_id, rep_p_id=contexto_cofre.contexto.rep_p_id, limite=1
    )
    assert len(pagina1) == 1
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor is not None

    pagina2, paginacao2 = await consulta.listar_afd(
        sessao_f12_a3,
        tenant_id,
        rep_p_id=contexto_cofre.contexto.rep_p_id,
        limite=1,
        cursor=paginacao1.proximo_cursor,
    )
    assert len(pagina2) == 1

    ids_vistos = {pagina1[0].id, pagina2[0].id}
    assert ids_vistos == {contexto_cofre.afd.id, segundo.id}
