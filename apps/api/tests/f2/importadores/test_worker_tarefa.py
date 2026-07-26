"""Testes de `apps/worker/worker/tarefas/importacoes.py` (`importar_colaboradores`,
T10 do PCF da F2).

Chama a tarefa diretamente como funcao Python (mesma tecnica de
`apps/worker/tests/test_andaime_worker.py`, que tambem nao sobe um worker ARQ
de verdade) -- o que importa provar e o comportamento da tarefa, nao o
transporte do ARQ, que ja e testado pela propria biblioteca. `test_servico.py`
prova que a API enfileira de verdade no Redis.
"""

from __future__ import annotations

import csv
import io
import time
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from ponto_contracts import Colaborador, Importacao, Vinculo
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f2.conftest import ContextoOrganizacional, aplicar_tenant_teste

pytestmark = pytest.mark.asyncio


def _gerar_cpf(indice: int) -> str:
    base = str(100_000_000 + indice)[-9:]
    pesos1 = list(range(10, 1, -1))
    pesos2 = list(range(11, 1, -1))
    dv1 = _dv_modulo11(base, pesos1)
    dv2 = _dv_modulo11(base + str(dv1), pesos2)
    return f"{base}{dv1}{dv2}"


def _gerar_pis(indice: int) -> str:
    base = str(2_000_000_000 + indice)[-10:]
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(d) * p for d, p in zip(base, pesos, strict=True))
    resto = soma % 11
    dv = 11 - resto
    if dv >= 10:
        dv = 0
    return f"{base}{dv}"


def _dv_modulo11(digitos: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _montar_linha(indice: int, *, empresa_cnpj: str, defeito: str | None = None) -> dict[str, str]:
    linha = {
        "matricula": f"M{indice:06d}",
        "cpf": _gerar_cpf(indice),
        "pis": _gerar_pis(indice),
        "nome_completo": f"Colaborador Teste {indice}",
        "empresa_cnpj": empresa_cnpj,
        "data_admissao": "2024-03-01",
    }
    if defeito == "cpf":
        linha["cpf"] = "11111111111"
    elif defeito == "pis":
        linha["pis"] = "11111111111"
    elif defeito == "matricula_duplicada":
        linha["matricula"] = "M000001"
    elif defeito == "empresa_inexistente":
        linha["empresa_cnpj"] = "99999999000199"
    elif defeito == "data_incoerente":
        linha["data_admissao"] = "31/02/2024"
    return linha


def _csv_bytes(linhas: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    escritor = csv.DictWriter(
        buffer,
        fieldnames=["matricula", "cpf", "pis", "nome_completo", "empresa_cnpj", "data_admissao"],
    )
    escritor.writeheader()
    escritor.writerows(linhas)
    return buffer.getvalue().encode("utf-8")


async def _criar_importacao_para_teste(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    conteudo_ref: str,
) -> Importacao:
    """Cria e COMMITA a linha de `importacoes`: a tarefa do worker abre a
    PROPRIA conexao (engine separada de `sessao_f2`), entao precisa enxergar
    a linha ja durável, nao apenas `flush`ada nesta transacao. Reaplica o
    tenant depois, porque o commit encerra o `SET LOCAL` (RLS) desta sessao."""
    importacao = Importacao(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        tipo="colaboradores",
        origem="csv",
        nome_arquivo="teste.csv",
        conteudo_ref=conteudo_ref,
        status="recebido",
    )
    sessao.add(importacao)
    await sessao.commit()
    await aplicar_tenant_teste(sessao, tenant_id)
    return importacao


async def _recarregar_importacao(sessao: AsyncSession, importacao_id: UUID) -> Importacao:
    """Busca `Importacao` com `populate_existing=True`.

    Necessario porque o WORKER processa e commita a linha por uma engine e
    conexao PROPRIAS (`worker.tarefas.importacoes._fabrica_de_sessoes()`),
    inteiramente separada de `sessao_f2`. Com `expire_on_commit=False`
    (`tests/f2/conftest.py`), o objeto Python que este teste ja carregou em
    `_criar_importacao_para_teste` continua no identity map de `sessao_f2`
    com os valores de ANTES do worker rodar -- um `sessao.get(...)` simples
    devolveria essa copia obsoleta em vez de reconsultar o banco.
    `populate_existing=True` forca a atualizacao dos atributos a partir da
    linha real, mesmo com o objeto ja carregado.
    """
    resultado = await sessao.execute(
        sa.select(Importacao)
        .where(Importacao.id == importacao_id)
        .execution_options(populate_existing=True)
    )
    return resultado.scalar_one()


def _gravar_objeto(conteudo_ref: str, conteudo: bytes) -> None:
    from worker.tarefas.importacoes import _raiz_armazenamento

    caminho = _raiz_armazenamento() / conteudo_ref
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)


async def test_importacao_pequena_com_defeitos_nao_aborta_a_carga(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    ambiente_worker: URL,
) -> None:
    from worker.tarefas.importacoes import importar_colaboradores

    linhas = [
        _montar_linha(1, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj),
        _montar_linha(2, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj, defeito="cpf"),
        _montar_linha(3, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj, defeito="pis"),
        _montar_linha(
            4,
            empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj,
            defeito="matricula_duplicada",
        ),
        _montar_linha(
            5,
            empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj,
            defeito="empresa_inexistente",
        ),
        _montar_linha(
            6, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj, defeito="data_incoerente"
        ),
    ]
    conteudo_ref = f"testes/{uuid4()}.csv"
    _gravar_objeto(conteudo_ref, _csv_bytes(linhas))

    importacao = await _criar_importacao_para_teste(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        conteudo_ref=conteudo_ref,
    )
    importacao_id = str(importacao.id)
    tenant_id_str = str(contexto_organizacional.tenant_id)

    resultado = await importar_colaboradores(
        {}, tenant_id=tenant_id_str, importacao_id=importacao_id
    )

    assert resultado["totalLinhas"] == 6
    assert resultado["linhasSucesso"] == 1
    assert resultado["linhasErro"] == 5
    assert resultado["status"] == "concluido_com_erros"

    # A carga NAO abortou: todas as 6 linhas foram avaliadas, mesmo com 5 ruins.
    await aplicar_tenant_teste(sessao_f2, contexto_organizacional.tenant_id)
    linha_importacao = await _recarregar_importacao(sessao_f2, importacao.id)
    assert linha_importacao is not None
    assert linha_importacao.linhas_processadas == 6
    assert linha_importacao.erros is not None
    erros = linha_importacao.erros["linhas"]
    codigos_por_linha = {erro["linha"]: erro["codigo"] for erro in erros}
    assert codigos_por_linha[3] == "PONTO-VAL-002"  # linha 2 do arquivo = linha 3 (cabecalho=1)
    assert codigos_por_linha[4] == "PONTO-VAL-004"
    assert codigos_por_linha[5] == "PONTO-CONF-001"
    assert codigos_por_linha[6] == "PONTO-REC-001"
    assert codigos_por_linha[7] == "PONTO-VAL-007"

    colaborador = (
        await sessao_f2.execute(
            sa.select(Colaborador).where(
                Colaborador.tenant_id == contexto_organizacional.tenant_id,
                Colaborador.matricula == "M000001",
            )
        )
    ).scalar_one()
    assert colaborador.cpf == _gerar_cpf(1)

    vinculo = (
        await sessao_f2.execute(
            sa.select(Vinculo).where(
                Vinculo.tenant_id == contexto_organizacional.tenant_id,
                Vinculo.colaborador_id == colaborador.id,
            )
        )
    ).scalar_one()
    assert vinculo.status == "ativo"


async def test_reprocessar_o_mesmo_arquivo_nao_duplica_colaborador(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    ambiente_worker: URL,
) -> None:
    from worker.tarefas.importacoes import importar_colaboradores

    linhas = [_montar_linha(100, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj)]
    conteudo_ref = f"testes/{uuid4()}.csv"
    _gravar_objeto(conteudo_ref, _csv_bytes(linhas))

    for _ in range(2):
        importacao = await _criar_importacao_para_teste(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            conteudo_ref=conteudo_ref,
        )
        await importar_colaboradores(
            {},
            tenant_id=str(contexto_organizacional.tenant_id),
            importacao_id=str(importacao.id),
        )
        await aplicar_tenant_teste(sessao_f2, contexto_organizacional.tenant_id)

    total_colaboradores = (
        await sessao_f2.execute(
            sa.select(sa.func.count(Colaborador.id)).where(
                Colaborador.tenant_id == contexto_organizacional.tenant_id,
                Colaborador.matricula == "M000100",
            )
        )
    ).scalar_one()
    assert total_colaboradores == 1

    total_vinculos = (
        await sessao_f2.execute(
            sa.select(sa.func.count(Vinculo.id)).where(
                Vinculo.tenant_id == contexto_organizacional.tenant_id,
                Vinculo.matricula_esocial == "M000100",
            )
        )
    ).scalar_one()
    assert total_vinculos == 1


async def test_layout_desconhecido_e_ponto_imp_001(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    ambiente_worker: URL,
) -> None:
    from worker.tarefas.importacoes import importar_colaboradores

    conteudo_ref = f"testes/{uuid4()}.csv"
    _gravar_objeto(conteudo_ref, b"coluna_a,coluna_b\n1,2\n")

    importacao = await _criar_importacao_para_teste(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        conteudo_ref=conteudo_ref,
    )
    resultado = await importar_colaboradores(
        {}, tenant_id=str(contexto_organizacional.tenant_id), importacao_id=str(importacao.id)
    )
    assert resultado["status"] == "falhou"

    await aplicar_tenant_teste(sessao_f2, contexto_organizacional.tenant_id)
    linha_importacao = await _recarregar_importacao(sessao_f2, importacao.id)
    assert linha_importacao is not None
    assert linha_importacao.erros is not None
    assert linha_importacao.erros["arquivo"][0]["codigo"] == "PONTO-IMP-001"


async def test_importacao_de_cinco_mil_colaboradores_com_relatorio_de_erros(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    ambiente_worker: URL,
) -> None:
    """Criterio de aceite 7 da secao 7 do PCF: 5.000 linhas, >= 50 defeituosas
    distribuidas, sem abortar a carga, idempotente, concluindo em < 5 min."""
    from worker.tarefas.importacoes import importar_colaboradores

    total_linhas = 5_000
    categorias = ["cpf", "pis", "matricula_duplicada", "empresa_inexistente", "data_incoerente"]
    linhas: list[dict[str, str]] = []
    esperado_defeituosas = 0
    for indice in range(1, total_linhas + 1):
        defeito = categorias[(indice // 100) % len(categorias)] if indice % 100 == 0 else None
        if defeito:
            esperado_defeituosas += 1
        linhas.append(
            _montar_linha(
                indice, empresa_cnpj=contexto_organizacional.empresa_matriz_cnpj, defeito=defeito
            )
        )
    assert esperado_defeituosas >= 50

    conteudo_ref = f"testes/{uuid4()}.csv"
    _gravar_objeto(conteudo_ref, _csv_bytes(linhas))

    importacao = await _criar_importacao_para_teste(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        conteudo_ref=conteudo_ref,
    )

    inicio = time.perf_counter()
    resultado = await importar_colaboradores(
        {}, tenant_id=str(contexto_organizacional.tenant_id), importacao_id=str(importacao.id)
    )
    duracao_s = time.perf_counter() - inicio

    print(
        f"\n[cinco_mil] {total_linhas} linhas, {resultado['linhasErro']} erros, "
        f"{duracao_s:.2f}s (limite: 300s)"
    )

    assert resultado["totalLinhas"] == total_linhas
    assert resultado["linhasErro"] == esperado_defeituosas
    assert resultado["linhasSucesso"] == total_linhas - esperado_defeituosas
    assert duracao_s < 300, f"importacao levou {duracao_s:.1f}s, acima do limite de 5 minutos"

    # Idempotencia: reprocessar o MESMO arquivo (nova linha de `importacoes`,
    # mesmo conteudo_ref) nao duplica colaborador nem vinculo.
    await aplicar_tenant_teste(sessao_f2, contexto_organizacional.tenant_id)
    importacao_2 = await _criar_importacao_para_teste(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        conteudo_ref=conteudo_ref,
    )
    resultado_2 = await importar_colaboradores(
        {}, tenant_id=str(contexto_organizacional.tenant_id), importacao_id=str(importacao_2.id)
    )
    assert resultado_2["linhasSucesso"] == resultado["linhasSucesso"]

    await aplicar_tenant_teste(sessao_f2, contexto_organizacional.tenant_id)
    total_colaboradores = (
        await sessao_f2.execute(
            sa.select(sa.func.count(Colaborador.id)).where(
                Colaborador.tenant_id == contexto_organizacional.tenant_id,
                Colaborador.empresa_id == contexto_organizacional.empresa_matriz_id,
            )
        )
    ).scalar_one()
    assert total_colaboradores == resultado["linhasSucesso"]
