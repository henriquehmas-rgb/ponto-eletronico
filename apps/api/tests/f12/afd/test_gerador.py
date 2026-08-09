"""T6 -- orquestrador do gerador de AFD: montagem completa, fracionamento,
nome de arquivo, evento, comportamento sem certificado configurado.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum import armazenamento
from app.core.erros import ErroDeAplicacao
from app.fiscal.afd import eventos as afd_eventos
from app.fiscal.afd.gerador import gerar_afd_arquivo
from tests.f12.conftest import ContextoF12, gerar_marcacoes_reais

_INICIO = dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3)))


@pytest.fixture(autouse=True)
def _limpar_barramento_afd() -> None:
    afd_eventos.limpar_barramento()
    yield
    afd_eventos.limpar_barramento()


async def _baixar_texto(conteudo_ref: str) -> str:
    conteudo = await armazenamento.obter_objeto(conteudo_ref)
    return conteudo.decode("iso-8859-1")


def _linhas_tipo7(texto: str) -> list[str]:
    return [linha for linha in texto.split("\r\n") if linha and linha[9:10] == "7"]


@pytest.mark.asyncio
async def test_gera_um_afd_com_tipos_1_7_9_e_assinatura_nessa_ordem(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    marcacoes = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=5, inicio=_INICIO)
    assert len(marcacoes) == 5

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=False,
    )

    assert len(arquivos) == 1
    arquivo = arquivos[0]
    assert arquivo.status == "gerado"
    assert arquivo.nsr_inicial == 1
    assert arquivo.nsr_final == 5
    # cabecalho + 5 tipo7 + trailer + assinatura = 1 + 5 + 1 + 1
    assert arquivo.total_registros == 8
    assert arquivo.fracionado is False
    assert arquivo.fracao_numero is None
    assert arquivo.fracao_total is None
    assert arquivo.hash_sha256 is not None
    assert len(arquivo.hash_sha256) == 64

    texto = await _baixar_texto(arquivo.conteudo_ref)
    linhas = texto.split("\r\n")
    # ultimo elemento vazio por causa do CR+LF final apos a ultima linha
    assert linhas[-1] == ""
    linhas_de_conteudo = linhas[:-1]
    assert len(linhas_de_conteudo) == 8  # 1 cabecalho + 5 tipo7 + 1 trailer + 1 assinatura

    assert linhas_de_conteudo[0][9:10] == "1"  # cabecalho
    for indice in range(1, 6):
        assert linhas_de_conteudo[indice][9:10] == "7"
    assert linhas_de_conteudo[6][0:9] == "999999999"  # trailer
    assert linhas_de_conteudo[6][-1] == "9"
    assert linhas_de_conteudo[7].startswith("ASSINATURA_DIGITAL_EM_ARQUIVO_P7S")

    # ISO-8859-1: round-trip sem excecao ja e uma prova; reforca decodificando
    # de volta para bytes e comparando.
    assert texto.encode("iso-8859-1") == await armazenamento.obter_objeto(arquivo.conteudo_ref)


@pytest.mark.asyncio
async def test_ordenado_por_nsr_nao_por_data_hora(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """ADR-003 consequencia (d) + PCF §2.8: o AFD e a excecao deliberada que
    ordena por NSR, nao por data/hora. Gera duas marcacoes online (NSR 1 e
    2, na ordem cronologica) e confirma que a ordem no arquivo bate com o
    NSR da alocacao, nao com a suposicao de que datahora_marcacao cresce
    monotonicamente (o que aqui coincide, mas o teste prova pela leitura do
    NSR gravado em cada linha, nao por inferencia)."""
    marcacoes = await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=3, inicio=_INICIO)
    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=False,
    )
    texto = await _baixar_texto(arquivos[0].conteudo_ref)
    linhas_tipo7 = [linha for linha in texto.split("\r\n") if linha and linha[9:10] == "7"]
    nsrs_no_arquivo = [int(linha[0:9]) for linha in linhas_tipo7]
    assert nsrs_no_arquivo == sorted(nsrs_no_arquivo)
    assert nsrs_no_arquivo == [m.nsr for m in marcacoes]


@pytest.mark.asyncio
async def test_marcacao_offline_de_outro_dia_nao_quebra_a_cadeia_do_afd(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Caminho REAL do resíduo do ADR-012 (o filtro de período de
    `_consultar_marcacoes_do_periodo`, não uma lista montada à mão): uma
    marcação coletada offline recebe NSR na GRAVAÇÃO (ADR-003 — NSR não é
    cronológico) mas entra no AFD pela `datahora_marcacao`, que aqui cai
    cinco dias fora da janela pedida. O AFD do dia contém NSR 1 e 3, pulando
    o NSR 2 — e o campo nº 8 do NSR 3 tem de ser o MESMO que ele teria num
    AFD que cobrisse os dois dias, senão a cadeia não é auditável."""
    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=1, inicio=_INICIO)
    # NSR 2: coletada offline, com datahora_marcacao 5 dias depois (fora da
    # janela do AFD pedido abaixo), gravada agora -- exatamente o cenario que
    # torna o NSR nao cronologico.
    await gerar_marcacoes_reais(
        sessao_f12,
        contexto_f12,
        quantidade=1,
        inicio=_INICIO + dt.timedelta(days=5),
        coletada_offline=True,
        canal="mobile",
    )
    await gerar_marcacoes_reais(
        sessao_f12, contexto_f12, quantidade=1, inicio=_INICIO + dt.timedelta(hours=1)
    )

    apenas_o_dia = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=False,
    )
    linhas_do_dia = _linhas_tipo7(await _baixar_texto(apenas_o_dia[0].conteudo_ref))
    assert [int(linha[0:9]) for linha in linhas_do_dia] == [1, 3]

    periodo_inteiro = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=(_INICIO + dt.timedelta(days=5)).date(),
        assinar=False,
    )
    linhas_inteiro = _linhas_tipo7(await _baixar_texto(periodo_inteiro[0].conteudo_ref))
    assert [int(linha[0:9]) for linha in linhas_inteiro] == [1, 2, 3]

    # O NSR 3 sai byte a byte identico nos dois arquivos -- inclusive o campo
    # no 8 (hash), que e o ponto do resíduo do ADR-012.
    por_nsr_inteiro = {int(linha[0:9]): linha for linha in linhas_inteiro}
    for linha in linhas_do_dia:
        assert linha == por_nsr_inteiro[int(linha[0:9])]


@pytest.mark.asyncio
async def test_fracionamento_produz_n_arquivos_com_faixas_complementares(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """§2.11 do PCF: `tamanhoFracaoRegistros` e o criterio de corte ja
    escolhido pelo contrato -- cada fracao e um AFD completo e valido por
    si so, com faixas de NSR complementares e sem sobreposicao."""
    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=7, inicio=_INICIO)

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=False,
        fracionar=True,
        tamanho_fracao_registros=3,
    )

    assert len(arquivos) == 3  # 3 + 3 + 1
    for indice, arquivo in enumerate(arquivos, start=1):
        assert arquivo.fracionado is True
        assert arquivo.fracao_numero == indice
        assert arquivo.fracao_total == 3
        assert arquivo.status == "gerado"

    faixas = [(a.nsr_inicial, a.nsr_final) for a in arquivos]
    assert faixas == [(1, 3), (4, 6), (7, 7)]

    # Sem sobreposicao e cobertura completa da sequencia 1..7.
    todos_os_nsr: list[int] = []
    for de, ate in faixas:
        todos_os_nsr.extend(range(de, ate + 1))
    assert todos_os_nsr == list(range(1, 8))

    # Contagens do trailer de cada fracao batem com o tamanho da fracao,
    # nao com o total geral.
    contagens_tipo7 = [a.total_registros - 3 for a in arquivos]
    assert contagens_tipo7 == [3, 3, 1]

    nomes = [a.nome_arquivo for a in arquivos]
    assert nomes[0].endswith("_PARTE1DE3.txt")
    assert nomes[1].endswith("_PARTE2DE3.txt")
    assert nomes[2].endswith("_PARTE3DE3.txt")


@pytest.mark.asyncio
async def test_sem_certificado_configurado_conclui_com_status_gerado(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério de aceite 10 do PCF: com certificado ausente (o estado real
    de hoje, `docs/fases/F12-conformidade-rep-p.md` §2.4), `gerarAfd` com
    `assinar=true` conclui com `status='gerado'`, NUNCA erro."""
    from app.fiscal.assinatura import certificado as modulo_certificado

    monkeypatch.setattr(modulo_certificado, "obter_certificado_configurado", lambda *a, **k: None)

    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=3, inicio=_INICIO)

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=True,
    )

    assert len(arquivos) == 1
    assert arquivos[0].status == "gerado"


@pytest.mark.asyncio
async def test_rep_p_sem_numero_inpi_responde_fisc_003(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """`rep_ps.numero_inpi` tem `CHECK (numero_inpi ~ '^[0-9]+$')` no banco
    -- um REP-P persistido NUNCA tem `numeroInpi` vazio de verdade (o
    próprio banco impede). Esta checagem em `gerar_afd_arquivo` é defesa
    em profundidade (o PCF pede a checagem mesmo assim). Para exercitar o
    código sem violar o `CHECK` (que bloquearia até um `UPDATE` direto),
    muda o atributo só em memória, sem `flush()` -- `gerar_afd_arquivo`
    localiza o REP-P via `sessao.get(...)`, que devolve o MESMO objeto do
    *identity map* da sessão com o atributo mutado, sem tocar o banco."""
    from ponto_contracts import RepP

    rep_p = await sessao_f12.get(RepP, contexto_f12.rep_p_id)
    assert rep_p is not None
    rep_p.numero_inpi = ""

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await gerar_afd_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            rep_p_id=contexto_f12.rep_p_id,
            inicio=_INICIO.date(),
            fim=_INICIO.date(),
        )
    assert excinfo.value.codigo == "PONTO-FISC-003"


@pytest.mark.asyncio
async def test_periodo_sem_marcacoes_responde_fisc_006(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await gerar_afd_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            rep_p_id=contexto_f12.rep_p_id,
            inicio=dt.date(2020, 1, 1),
            fim=dt.date(2020, 1, 31),
        )
    assert excinfo.value.codigo == "PONTO-FISC-006"


@pytest.mark.asyncio
async def test_evento_afd_gerado_publicado_com_campos_do_contrato(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=2, inicio=_INICIO)

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=False,
    )

    assert len(afd_eventos.BARRAMENTO_INTERNO) == 1
    envelope = afd_eventos.BARRAMENTO_INTERNO[0]
    assert envelope["tipo"] == "afd.gerado"
    dados = envelope["dados"]
    assert dados["arquivoId"] == str(arquivos[0].id)
    assert dados["repPId"] == str(contexto_f12.rep_p_id)
    assert dados["nsrInicial"] == 1
    assert dados["nsrFinal"] == 2
    assert dados["totalRegistros"] == arquivos[0].total_registros
    assert dados["hashSha256"] == arquivos[0].hash_sha256
    assert dados["assinado"] is False
    assert dados["fracionado"] is False


@pytest.mark.asyncio
async def test_rep_p_de_outro_tenant_ou_inexistente_responde_rec_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    import uuid

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await gerar_afd_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            rep_p_id=uuid.uuid4(),
            inicio=_INICIO.date(),
            fim=_INICIO.date(),
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_geracao_ja_em_andamento_responde_fisc_002(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Linha `status='gerando'` presa (só alcançável, em produção, se um
    processo do worker morreu no meio de uma geração anterior -- aqui
    simulada por `INSERT` direto, exatamente o tipo de cenário defensivo
    que este teste existe para cobrir, nunca alcançável pelo fluxo feliz)."""
    from ponto_contracts import AfdArquivo

    linha_presa = AfdArquivo(
        tenant_id=contexto_f12.tenant_id,
        empresa_id=contexto_f12.empresa_id,
        rep_p_id=contexto_f12.rep_p_id,
        periodo_inicio=_INICIO.date(),
        periodo_fim=_INICIO.date(),
        nsr_inicial=1,
        nsr_final=1,
        nome_arquivo="AFD_PENDENTE.txt",
        status="gerando",
    )
    sessao_f12.add(linha_presa)
    await sessao_f12.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await gerar_afd_arquivo(
            sessao_f12,
            contexto_f12.tenant_id,
            rep_p_id=contexto_f12.rep_p_id,
            inicio=_INICIO.date(),
            fim=_INICIO.date(),
        )
    assert excinfo.value.codigo == "PONTO-FISC-002"


def _gerar_certificado_teste_local() -> object:
    """Certificado AUTOASSINADO gerado NESTA fixture (cópia local, não
    importa o helper privado de `app.fiscal.assinatura` -- cada agente
    mantém seu próprio, mesmo padrão de não-acoplamento entre agentes desta
    fase). Nunca apresentado como um e-CNPJ A1 real (PCF F12 §2.4)."""
    import datetime as _dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    from app.fiscal.assinatura.certificado import CertificadoConfig

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SEEG TESTE A1 - CERT AUTOASSINADO")])
    agora = _dt.datetime.now(_dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - _dt.timedelta(days=1))
        .not_valid_after(agora + _dt.timedelta(days=365))
        .sign(chave, hashes.SHA256())
    )
    return CertificadoConfig(
        certificado=certificado,
        chave_privada=chave,
        titular="SEEG TESTE A1 - CERT AUTOASSINADO",
        serial=format(certificado.serial_number, "x"),
        emissor="SEEG TESTE A1 - CERT AUTOASSINADO",
        validade_inicio=certificado.not_valid_before_utc,
        validade_fim=certificado.not_valid_after_utc,
        rotulo_teste="SEEG TESTE A1 - CERT AUTOASSINADO",
    )


@pytest.mark.asyncio
async def test_com_certificado_de_teste_configurado_assina_e_grava_arquivo_assinaturas(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com um certificado (de teste, autoassinado) configurado, `assinar=True`
    produz `status='assinado'` e grava `arquivo_assinaturas` -- prova que o
    mecanismo de assinatura de A3 é chamado de verdade quando há
    certificado, não só o caminho "sem certificado" do critério de aceite
    10."""
    from app.fiscal.assinatura import certificado as modulo_certificado

    certificado_teste = _gerar_certificado_teste_local()
    monkeypatch.setattr(
        modulo_certificado, "obter_certificado_configurado", lambda *a, **k: certificado_teste
    )

    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=2, inicio=_INICIO)

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=True,
    )

    assert len(arquivos) == 1
    assert arquivos[0].status == "assinado"

    from ponto_contracts import ArquivoAssinatura

    assinatura = (
        await sessao_f12.execute(
            sa.select(ArquivoAssinatura).where(
                ArquivoAssinatura.tenant_id == contexto_f12.tenant_id,
                ArquivoAssinatura.tipo_arquivo == "afd",
                ArquivoAssinatura.arquivo_id == arquivos[0].id,
            )
        )
    ).scalar_one()
    assert assinatura.padrao == "CAdES"
    assert assinatura.formato == "detached"
    assert assinatura.status == "assinado"
    assert assinatura.assinatura_ref.endswith(".p7s")

    # O evento publicado reflete a assinatura.
    assert afd_eventos.BARRAMENTO_INTERNO[0]["dados"]["assinado"] is True


@pytest.mark.asyncio
async def test_certificado_expirado_e_tratado_como_ausente(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Certificado presente mas fora da validade: a geração conclui do
    mesmo jeito que sem certificado (`status='gerado'`, nunca erro) -- a
    assinatura explícita via `assinarArquivoFiscal` é quem responde
    `PONTO-FISC-005` para certificado expirado, não a geração implícita."""
    from app.fiscal.assinatura import certificado as modulo_certificado

    certificado_teste = _gerar_certificado_teste_local()
    # Forca expirado sem reconstruir o certificado inteiro.
    object.__setattr__(
        certificado_teste, "validade_fim", dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    )
    monkeypatch.setattr(
        modulo_certificado, "obter_certificado_configurado", lambda *a, **k: certificado_teste
    )

    await gerar_marcacoes_reais(sessao_f12, contexto_f12, quantidade=1, inicio=_INICIO)

    arquivos = await gerar_afd_arquivo(
        sessao_f12,
        contexto_f12.tenant_id,
        rep_p_id=contexto_f12.rep_p_id,
        inicio=_INICIO.date(),
        fim=_INICIO.date(),
        assinar=True,
    )
    assert arquivos[0].status == "gerado"


def test_nunca_referencia_colunas_derivadas_de_f5() -> None:
    """Critério de aceite 8 do PCF: prova por análise estática que
    `app/fiscal/afd/**` nunca acessa `Marcacao.crc16`/`hash_anterior`/
    `hash_registro`/`linha_afd` (nem em maiúsculo, acesso de classe para
    `select()`/filtro, nem em minúsculo, acesso de instância de uma
    `Marcacao` já carregada) para preencher um campo do AFD. Note que
    `RegistroTipo7.hash_registro` (o hash do ADR-012, TIPO PRÓPRIO desta
    fase) é permitido e esperado -- só o acesso via um objeto/classe
    `Marcacao` é proibido, daí o prefixo `marcacao.`/`Marcacao.` explícito
    no padrão de busca."""
    import pathlib
    import re

    proibidas = ("crc16", "hash_anterior", "hash_registro", "linha_afd")
    padrao = re.compile(r"\b[Mm]arcacao\.(" + "|".join(proibidas) + r")\b")
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app" / "fiscal" / "afd"
    achados: list[str] = []
    for arquivo_py in raiz.glob("*.py"):
        texto = arquivo_py.read_text(encoding="utf-8")
        for linha_numero, linha in enumerate(texto.splitlines(), start=1):
            if padrao.search(linha):
                achados.append(f"{arquivo_py.name}:{linha_numero}: {linha.strip()}")
    assert not achados, (
        "app/fiscal/afd referencia coluna derivada de F5 (proibido pelo criterio de "
        f"aceite 8 do PCF F12): {achados}"
    )
