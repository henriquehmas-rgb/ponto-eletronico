"""Testes de `app.fiscal.assinatura.servico.assinar_arquivo_fiscal` (F12/A3,
T12) -- a orquestração de `POST /v1/fiscal/arquivos/{arquivoId}/assinar`.

Cobre: assinatura de `comprovante`/`afd`/`aej` com certificado de teste;
`PONTO-FISC-004` sem certificado configurado; `PONTO-FISC-005` com
certificado expirado; `tipoArquivo` ausente (`PONTO-VAL-001`);
`tipoArquivo='espelho'`/`'relatorio'` não implementado (`PONTO-INT-005`);
arquivo inexistente (`PONTO-REC-001`); estado não assinável
(`PONTO-CONF-003`); e o critério "reassinar gera linha nova" (append-only
de aplicação, nunca `UPDATE`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import AejArquivo, AfdArquivo, ArquivoAssinatura, Comprovante
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import salvar_objeto
from app.core.erros import ErroDeAplicacao
from app.fiscal.assinatura import servico
from app.fiscal.assinatura.certificado import CertificadoConfig
from app.schemas import contrato as esquemas
from tests.f12.assinatura.conftest import ContextoF12A3


def _requisicao(
    tipo_arquivo: str | None = "comprovante", **extra: object
) -> esquemas.AssinaturaArquivoRequisicao:
    dados: dict[str, object] = {"tipoArquivo": tipo_arquivo}
    dados.update(extra)
    return esquemas.AssinaturaArquivoRequisicao.model_validate(dados)


async def _criar_afd_de_teste(
    sessao: AsyncSession, contexto: ContextoF12A3, *, status: str = "gerado"
) -> AfdArquivo:
    conteudo = b"0000000001000000000001..." + b"7" * 100 + b"\r\n"
    chave = f"fiscal/teste/afd/{uuid.uuid4()}.txt"
    await salvar_objeto(chave, conteudo, content_type="text/plain")

    afd = AfdArquivo(
        tenant_id=contexto.tenant_id,
        empresa_id=contexto.empresa_id,
        rep_p_id=contexto.rep_p_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nsr_inicial=1,
        nsr_final=1,
        total_registros=1,
        nome_arquivo="AFD_TESTE.txt",
        conteudo_ref=chave,
        tamanho_bytes=len(conteudo),
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        status=status,
    )
    sessao.add(afd)
    await sessao.flush()
    return afd


async def _criar_aej_de_teste(
    sessao: AsyncSession, contexto: ContextoF12A3, *, status: str = "gerado"
) -> AejArquivo:
    conteudo = b"01|1|" + b"0" * 14 + b"|\r\n"
    chave = f"fiscal/teste/aej/{uuid.uuid4()}.txt"
    await salvar_objeto(chave, conteudo, content_type="text/plain")

    aej = AejArquivo(
        tenant_id=contexto.tenant_id,
        empresa_id=contexto.empresa_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nome_arquivo="AEJ_TESTE.txt",
        conteudo_ref=chave,
        tamanho_bytes=len(conteudo),
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        ptrp_identificacao="SEEG Ponto (fixture de teste)",
        status=status,
    )
    sessao.add(aej)
    await sessao.flush()
    return aej


@pytest.mark.asyncio
async def test_assina_comprovante_com_certificado_de_teste(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)

    assinatura = await servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_f12_a3.tenant_id,
        contexto_f12_a3.comprovante_id,
        _requisicao("comprovante"),
        usuario_id=contexto_f12_a3.usuario_id,
    )

    assert assinatura.tipo_arquivo == "comprovante"
    assert assinatura.arquivo_id == contexto_f12_a3.comprovante_id
    assert assinatura.status == "assinado"
    assert assinatura.padrao == "CAdES"
    assert assinatura.formato == "detached"
    assert assinatura.certificado_titular
    assert assinatura.validacao_resultado is not None
    assert assinatura.validacao_resultado["valido"] is True
    assert assinatura.validado_em is not None

    # `comprovantes` e imutavel: assinar NUNCA grava em `comprovantes.assinatura_ref`.
    comprovante = await sessao_f12_a3.get(Comprovante, contexto_f12_a3.comprovante_id)
    assert comprovante is not None
    assert comprovante.assinatura_ref is None


@pytest.mark.asyncio
async def test_assina_afd_e_atualiza_status_e_assinatura_ref(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)
    afd = await _criar_afd_de_teste(sessao_f12_a3, contexto_f12_a3)

    assinatura = await servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_f12_a3.tenant_id,
        afd.id,
        _requisicao("afd"),
        usuario_id=contexto_f12_a3.usuario_id,
    )

    assert assinatura.status == "assinado"
    await sessao_f12_a3.refresh(afd)
    assert afd.status == "assinado"
    assert afd.assinatura_ref == assinatura.assinatura_ref


@pytest.mark.asyncio
async def test_assina_aej(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)
    aej = await _criar_aej_de_teste(sessao_f12_a3, contexto_f12_a3)

    assinatura = await servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_f12_a3.tenant_id,
        aej.id,
        _requisicao("aej"),
        usuario_id=contexto_f12_a3.usuario_id,
    )

    assert assinatura.tipo_arquivo == "aej"
    await sessao_f12_a3.refresh(aej)
    assert aej.status == "assinado"


@pytest.mark.asyncio
async def test_sem_certificado_configurado_e_fisc_004(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: None)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao("comprovante"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-FISC-004"


@pytest.mark.asyncio
async def test_certificado_expirado_e_fisc_005(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste_expirado: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        servico, "obter_certificado_configurado", lambda: certificado_teste_expirado
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao("comprovante"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-FISC-005"


@pytest.mark.asyncio
async def test_tipo_arquivo_ausente_e_val_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao(None),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo_arquivo", ["espelho", "relatorio"])
async def test_espelho_e_relatorio_nao_implementados_e_int_005(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3, tipo_arquivo: str
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            uuid.uuid4(),
            _requisicao(tipo_arquivo),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-INT-005"


@pytest.mark.asyncio
async def test_arquivo_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            uuid.uuid4(),
            _requisicao("afd"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_afd_ainda_gerando_e_conf_003(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)
    afd = await _criar_afd_de_teste(sessao_f12_a3, contexto_f12_a3, status="gerando")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            afd.id,
            _requisicao("afd"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


@pytest.mark.asyncio
async def test_reassinar_gera_linha_nova_nunca_sobrescreve(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critério de aceite: 'reassinar gera linha nova' (descrição de
    `ArquivoAssinatura` no contrato). Prova por contagem de linhas E por
    `assinatura_ref`/`id` diferentes -- a primeira linha permanece intocada
    (nenhum UPDATE de aplicação nunca é emitido contra `arquivo_assinaturas`,
    ver docstring de `servico.py`)."""
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)

    primeira = await servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_f12_a3.tenant_id,
        contexto_f12_a3.comprovante_id,
        _requisicao("comprovante"),
        usuario_id=contexto_f12_a3.usuario_id,
    )
    segunda = await servico.assinar_arquivo_fiscal(
        sessao_f12_a3,
        contexto_f12_a3.tenant_id,
        contexto_f12_a3.comprovante_id,
        _requisicao("comprovante"),
        usuario_id=contexto_f12_a3.usuario_id,
    )

    assert primeira.id != segunda.id
    assert primeira.assinatura_ref != segunda.assinatura_ref

    total = (
        await sessao_f12_a3.execute(
            sa.select(sa.func.count())
            .select_from(ArquivoAssinatura)
            .where(
                ArquivoAssinatura.tenant_id == contexto_f12_a3.tenant_id,
                ArquivoAssinatura.arquivo_id == contexto_f12_a3.comprovante_id,
            )
        )
    ).scalar_one()
    assert total == 2

    primeira_recarregada = await sessao_f12_a3.get(ArquivoAssinatura, primeira.id)
    assert primeira_recarregada is not None
    assert primeira_recarregada.assinatura_ref == primeira.assinatura_ref
    assert primeira_recarregada.status == primeira.status


@pytest.mark.asyncio
async def test_aej_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            uuid.uuid4(),
            _requisicao("aej"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_comprovante_inexistente_e_rec_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            uuid.uuid4(),
            _requisicao("comprovante"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_afd_sem_conteudo_ref_e_fisc_006(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Estado defensivo: `status='gerado'` mas `conteudo_ref` ainda vazio
    (ex.: falha parcial de upload no gerador) -- `_obter_conteudo` recusa
    com `PONTO-FISC-006` em vez de tentar buscar uma chave vazia no MinIO."""
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)
    afd = AfdArquivo(
        tenant_id=contexto_f12_a3.tenant_id,
        empresa_id=contexto_f12_a3.empresa_id,
        rep_p_id=contexto_f12_a3.rep_p_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nsr_inicial=1,
        nsr_final=1,
        total_registros=1,
        nome_arquivo="AFD_SEM_CONTEUDO.txt",
        conteudo_ref=None,
        status="gerado",
    )
    sessao_f12_a3.add(afd)
    await sessao_f12_a3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            afd.id,
            _requisicao("afd"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-FISC-006"


@pytest.mark.asyncio
async def test_padrao_diferente_de_cades_e_val_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao("comprovante", padrao="XAdES"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_formato_diferente_de_detached_e_val_001(
    sessao_f12_a3: AsyncSession, contexto_f12_a3: ContextoF12A3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao("comprovante", formato="attached"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_autoverificacao_reprovada_interrompe_com_fisc_006_sem_gravar_nada(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simula uma autoverificação que reprova (bug hipotético de
    `assinar_cades`/`validar_cades`) monkeypatchando `cades.validar_cades`
    para sempre devolver inválido -- prova que `assinar_arquivo_fiscal`
    trata isso como `PONTO-FISC-006` e NÃO grava nenhuma linha em
    `arquivo_assinaturas` (ver docstring do módulo: verifica ANTES de
    gravar)."""
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado_teste)

    from app.fiscal.assinatura import cades as cades_modulo

    resultado_falso = cades_modulo.ResultadoValidacao(
        estruturalmente_valido=True,
        message_digest_confere=False,
        assinatura_criptografica_valida=True,
        certificado_dentro_da_validade=True,
        algoritmo_digest="sha256",
        algoritmo_assinatura="rsassa_pkcs1v15",
        instante_assinatura=None,
        certificado_titular="teste",
        certificado_serial="teste",
        motivo_falha="forcado pelo teste",
    )
    monkeypatch.setattr(cades_modulo, "validar_cades", lambda *a, **k: resultado_falso)

    antes = (
        await sessao_f12_a3.execute(
            sa.select(sa.func.count())
            .select_from(ArquivoAssinatura)
            .where(ArquivoAssinatura.tenant_id == contexto_f12_a3.tenant_id)
        )
    ).scalar_one()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.assinar_arquivo_fiscal(
            sessao_f12_a3,
            contexto_f12_a3.tenant_id,
            contexto_f12_a3.comprovante_id,
            _requisicao("comprovante"),
            usuario_id=contexto_f12_a3.usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-FISC-006"

    depois = (
        await sessao_f12_a3.execute(
            sa.select(sa.func.count())
            .select_from(ArquivoAssinatura)
            .where(ArquivoAssinatura.tenant_id == contexto_f12_a3.tenant_id)
        )
    ).scalar_one()
    assert depois == antes
