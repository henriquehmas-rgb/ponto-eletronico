"""Testes do servico `app.pessoas.colaboradores` (T5).

Batem contra o Postgres real da fixture da fase (`tests/f2/conftest.py`),
autenticados como a role de LOGIN sob Row Level Security -- nunca como
superusuario. Testam a regra de negocio diretamente na camada de servico,
sem passar pela camada HTTP (autenticacao e RBAC sao da F1, rodando em
paralelo; ver PCF da F2, secao 2).
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.pessoas import colaboradores as servico
from app.schemas.contrato import ColaboradorAtualizar, ColaboradorCriar
from tests.f2.conftest import ContextoOrganizacional

#: Mesmo default de desenvolvimento local de `tests/f2/conftest.py` -- nunca
#: aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario_sincrona() -> str:
    """URL de conexao sincrona (psycopg) do superusuario de teste.

    Uso restrito a uma unica prova de plano de consulta
    (`test_indice_trigram_...`), que precisa rodar fora do Row Level
    Security -- nunca para ler ou escrever dado de negocio.
    """
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    if bruta.startswith("postgresql+asyncpg://"):
        bruta = "postgresql://" + bruta[len("postgresql+asyncpg://") :]
    return bruta


def _dados_colaborador(
    contexto: ContextoOrganizacional,
    *,
    matricula: str | None = None,
    cpf: str = "11144477735",
    nome_completo: str = "Maria Aparecida de Souza",
    **extra: object,
) -> ColaboradorCriar:
    sufixo = uuid.uuid4().hex[:8]
    return ColaboradorCriar(
        empresaId=contexto.empresa_matriz_id,
        matricula=matricula or f"MAT-{sufixo}",
        cpf=cpf,
        nomeCompleto=nome_completo,
        **extra,
    )


@pytest.mark.asyncio
async def test_criar_colaborador_com_cpf_valido(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await servico.criar_colaborador(
        sessao_f2, contexto_organizacional.tenant_id, _dados_colaborador(contexto_organizacional)
    )
    assert colaborador.id is not None
    assert colaborador.cpf == "11144477735"
    assert colaborador.empresa_id == contexto_organizacional.empresa_matriz_id


@pytest.mark.asyncio
async def test_criar_colaborador_cpf_digitos_e_gravado_sem_mascara(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    """`app.comum.documentos.somente_digitos` normaliza antes de gravar --
    ver criterio de aceite 2 e T5 ("CPF com mascara e aceito na entrada e
    gravado sem mascara").

    Nota: o schema `ColaboradorCriar` gerado do `openapi.yaml` ja restringe
    `cpf` a `^[0-9]{11}$` (sem mascara) na fronteira HTTP -- uma mascara
    enviada no corpo da requisicao e recusada pelo Pydantic antes de chegar
    ao servico, com `PONTO-VAL-001` (corpo invalido). A normalizacao "aceita
    mascara, grava so digitos" e responsabilidade de `app/comum/documentos.py`
    e esta coberta, mascara incluida, em `test_documentos.py`. Este teste
    prova a metade que cabe a esta camada: o valor chega e sai sem mascara.
    """
    dados = _dados_colaborador(contexto_organizacional, cpf="11144477735")
    colaborador = await servico.criar_colaborador(
        sessao_f2, contexto_organizacional.tenant_id, dados
    )
    assert colaborador.cpf == "11144477735"


@pytest.mark.asyncio
async def test_criar_colaborador_cpf_invalido_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    dados = _dados_colaborador(contexto_organizacional, cpf="11144477734")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_colaborador(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-002"


@pytest.mark.asyncio
async def test_criar_colaborador_pis_invalido_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    dados = _dados_colaborador(contexto_organizacional, pisNit="11111111111")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_colaborador(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-004"


@pytest.mark.asyncio
async def test_matricula_duplicada_na_mesma_empresa_e_conflito(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    primeiro = await servico.criar_colaborador(
        sessao_f2, tenant_id, _dados_colaborador(contexto_organizacional, matricula="DUP-001")
    )
    assert primeiro.matricula == "DUP-001"

    duplicado = _dados_colaborador(contexto_organizacional, matricula="DUP-001", cpf="52998224725")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.criar_colaborador(sessao_f2, tenant_id, duplicado)
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_cpf_duplicado_na_mesma_empresa_e_conflito(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    await servico.criar_colaborador(
        sessao_f2, tenant_id, _dados_colaborador(contexto_organizacional, cpf="52998224725")
    )
    duplicado = _dados_colaborador(contexto_organizacional, cpf="52998224725")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.criar_colaborador(sessao_f2, tenant_id, duplicado)
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_nome_social_e_persistido_e_devolvido(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    dados = _dados_colaborador(
        contexto_organizacional, nome_completo="Joao da Silva", nomeSocial="Joana da Silva"
    )
    colaborador = await servico.criar_colaborador(
        sessao_f2, contexto_organizacional.tenant_id, dados
    )
    assert colaborador.nome_completo == "Joao da Silva"
    assert colaborador.nome_social == "Joana da Silva"


@pytest.mark.asyncio
async def test_soft_delete_marca_excluido_em_e_some_da_leitura_padrao(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await servico.criar_colaborador(
        sessao_f2, contexto_organizacional.tenant_id, _dados_colaborador(contexto_organizacional)
    )
    colaborador_id = colaborador.id

    await servico.excluir_colaborador(sessao_f2, colaborador_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_colaborador(sessao_f2, colaborador_id)
    assert excinfo.value.codigo == "PONTO-REC-001"

    ainda_existe = await servico.obter_colaborador(
        sessao_f2, colaborador_id, incluir_excluidos=True
    )
    assert ainda_existe.excluido_em is not None


@pytest.mark.asyncio
async def test_atualizar_colaborador_altera_so_os_campos_enviados(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await servico.criar_colaborador(
        sessao_f2, contexto_organizacional.tenant_id, _dados_colaborador(contexto_organizacional)
    )
    nome_original = colaborador.nome_completo

    atualizado = await servico.atualizar_colaborador(
        sessao_f2, colaborador.id, ColaboradorAtualizar(telefone="11999998888")
    )
    assert atualizado.telefone == "11999998888"
    assert atualizado.nome_completo == nome_original


@pytest.mark.asyncio
async def test_busca_por_nome_parcial_devolve_o_resultado_certo(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    """`busca` filtra por substring de `nome_completo` ou `nome_social`."""
    tenant_id = contexto_organizacional.tenant_id
    cpfs = {"Ana Paula Ferreira": "11144477735", "Ana Carolina Lima": "98765432100"}
    for nome in ("Ana Paula Ferreira", "Ana Carolina Lima", "Carlos Eduardo Nogueira"):
        dados = ColaboradorCriar(
            empresaId=contexto_organizacional.empresa_matriz_id,
            matricula=f"MAT-{uuid.uuid4().hex[:8]}",
            cpf=cpfs.get(nome, "52998224725"),
            nomeCompleto=nome,
        )
        await servico.criar_colaborador(sessao_f2, tenant_id, dados)

    linhas, _ = await servico.listar_colaboradores(sessao_f2, tenant_id, busca="Ana")
    nomes = {linha.nome_completo for linha in linhas}
    assert nomes == {"Ana Paula Ferreira", "Ana Carolina Lima"}


def test_indice_trigram_atende_ilike_por_substring_de_nome(
    url_login_sessao: object,  # garante que a fixture de sessao ja migrou o banco
) -> None:
    """Prova por `EXPLAIN` que `ix_colaboradores_nome_trgm` (GIN,
    `gin_trgm_ops`) e o indice compativel com o `ILIKE '%substring%'` que
    `busca` usa -- exigido pelo criterio de aceite do T5.

    Roda numa conexao a parte, fora do Row Level Security: o indice em si
    nao carrega `tenant_id` (so `nome_completo`), entao qualquer condicao
    adicional de tenant so daria a um OUTRO indice (`ix_colaboradores_cpf`,
    que comeca por `tenant_id`) a chance de vencer por custo, mascarando a
    resposta. Sem nenhuma outra condicao no `WHERE`, `enable_seqscan = off`
    isola exatamente a pergunta "este predicado pode usar o indice
    trigram?" -- nao mistura com a decisao de custo do planejador para uma
    tabela pequena, nem com RLS.
    """
    url = _url_superusuario_sincrona()
    with psycopg.connect(url) as conexao, conexao.cursor() as cursor:
        cursor.execute("SET enable_seqscan = off")
        cursor.execute(
            "EXPLAIN SELECT id FROM colaboradores WHERE nome_completo ILIKE %s", ("%Ana%",)
        )
        plano = "\n".join(linha[0] for linha in cursor.fetchall())
    assert "ix_colaboradores_nome_trgm" in plano, plano
