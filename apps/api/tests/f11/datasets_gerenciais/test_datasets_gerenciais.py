"""Testes dos 12 datasets gerenciais/fiscais/financeiro/lgpd (itens 13-24,
F11, T9/T10, A3), executados através do motor genérico real (`app.
relatorios.motor.executar_dataset`) -- não chamando a função de consulta
isolada, para provar a integração real dataset <-> catálogo semeado por A1
<-> motor.
"""

from __future__ import annotations

import datetime as dt
import uuid

from ponto_contracts import RelatorioDefinicao
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta, executar_dataset
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_gerenciais.conftest import ExtrasGerenciais


async def _definicao(
    sessao: AsyncSession, contexto: ContextoF11, codigo: str
) -> RelatorioDefinicao:
    definicao = await sessao.get(RelatorioDefinicao, contexto.relatorio_ids[codigo])
    assert definicao is not None
    return definicao


def _por_nome(linhas: list[dict[str, object]], nome: str) -> list[dict]:
    """Filtra linhas do resultado por `colaboradorNome` -- o caminho padrão
    de `executar_dataset` (sem `colunas` explícito) só projeta as chaves
    declaradas em `RelatorioDefinicao.colunas_disponiveis` (semeada por A1),
    que para a maioria destes relatórios NÃO inclui `colaboradorId` (só o
    nome, pensado para leitura humana) -- filtrar pelo nome é o que o
    catálogo real permite sem pedir uma coluna fora do catálogo (o que o
    motor recusaria com `PONTO-VAL-005`)."""
    return [linha for linha in linhas if linha.get("colaboradorNome") == nome]


# =============================================================================
# 13. escalas-previsto-realizado
# =============================================================================


async def test_escalas_previsto_realizado(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "escalas-previsto-realizado")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id,
            de=extras_gerenciais.dia_extra,
            ate=extras_gerenciais.dia_extra,
        ),
    )
    colaborador_a = contexto_f11.colaboradores[0]
    linhas = _por_nome(resultado.linhas, colaborador_a.nome)
    assert len(linhas) == 1
    assert linhas[0]["previstoMinutos"] == 480
    assert linhas[0]["trabalhadoMinutos"] == 500


# =============================================================================
# 14. violacoes-intrajornada
# =============================================================================


async def test_violacoes_intrajornada(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "violacoes-intrajornada")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )
    # So os dias uteis padrao (intrajornada=0) sao filtrados fora; so o dia
    # extra (2 colaboradores, intrajornada=25 -- ver extras_gerenciais) aparece.
    # `ocorrenciaStatus` nao esta em `colunas_disponiveis` deste relatorio
    # (semeado por A1 so com colaboradorNome/data/intrajornadaSuprimida
    # Minutos) -- provado a parte, direto na função, em
    # `test_violacoes_intrajornada_join_com_ocorrencia_via_funcao_direta`.
    assert len(resultado.linhas) == 2
    assert all(linha["intrajornadaSuprimidaMinutos"] == 25 for linha in resultado.linhas)


async def test_violacoes_intrajornada_join_com_ocorrencia_via_funcao_direta(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    """Chama a função de dataset diretamente (sem passar pelo motor/
    catálogo), para provar que o `JOIN` com `ocorrencias` funciona mesmo
    quando o catálogo semeado não expõe essas colunas por padrão."""
    from app.relatorios.datasets.gerenciais import violacoes_intrajornada

    consulta = violacoes_intrajornada(
        sessao_f11, contexto_f11.tenant_id, ContextoConsulta(tenant_id=contexto_f11.tenant_id)
    )
    linhas = (await sessao_f11.execute(consulta)).mappings().all()
    assert len(linhas) == 2
    assert all(linha["ocorrenciaStatus"] == "aberta" for linha in linhas)
    assert all(linha["ocorrenciaSeveridade"] == "alta" for linha in linhas)


# =============================================================================
# 15. violacoes-interjornada
# =============================================================================


async def test_violacoes_interjornada(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "violacoes-interjornada")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )
    assert len(resultado.linhas) == 2
    assert all(linha["interjornadaMinutos"] == 480 for linha in resultado.linhas)


# =============================================================================
# 16. horas-por-centro-custo
# =============================================================================


async def test_horas_por_centro_custo_agrupado(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "horas-por-centro-custo")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id,
            de=extras_gerenciais.dia_extra,
            ate=extras_gerenciais.dia_extra,
        ),
        agrupamento="centroCusto",
    )
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["centroCusto"] == "Centro de Custo Teste"
    # 2 colaboradores x 500 minutos trabalhados no dia extra.
    assert linha["trabalhadoMinutos"] == 1000
    assert linha["quantidadeRegistros"] == 2


# =============================================================================
# 17. extrato-para-folha
# =============================================================================


async def test_extrato_para_folha(sessao_f11: AsyncSession, contexto_f11: ContextoF11) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "extrato-para-folha")
    colaborador_b = contexto_f11.colaboradores[1]
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id, colaborador_id=colaborador_b.colaborador_id
        ),
    )
    # Colaborador B: 3 dias uteis, cada um com 2 componentes (he50 extra +
    # adnoturno) = 6 linhas.
    assert len(resultado.linhas) == 6
    codigos = {linha["codigo"] for linha in resultado.linhas}
    assert codigos == {"he50", "adnoturno"}
    competencias = {linha["competencia"] for linha in resultado.linhas}
    assert len(competencias) == 1  # os 3 dias uteis caem no mesmo mes


# =============================================================================
# 18. movimentacao-pessoal
# =============================================================================


async def test_movimentacao_pessoal(sessao_f11: AsyncSession, contexto_f11: ContextoF11) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "movimentacao-pessoal")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=contexto_f11.tenant_id,
            de=dt.date(2020, 1, 1),
            ate=dt.date(2020, 1, 1),
        ),
    )
    # Os 3 vinculos da fixture comecam em 2020-01-01.
    admissoes = [linha for linha in resultado.linhas if linha["evento"] == "admissao"]
    assert len(admissoes) == 3


# =============================================================================
# 19. auditoria
# =============================================================================


async def test_auditoria_filtra_por_entidade_e_acao(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    tenant_id = contexto_f11.tenant_id
    agora = dt.datetime.now(tz=dt.UTC)
    linhas_auditoria = [
        ("colaboradores", "criar", 1),
        ("colaboradores", "atualizar", 2),
        ("vinculos", "criar", 3),
    ]
    for entidade, acao, sequencia in linhas_auditoria:
        hash_registro = f"{sequencia:064d}"
        await sessao_f11.execute(
            text(
                "INSERT INTO auditoria "
                "(id, tenant_id, sequencia, evento, entidade, acao, origem, resultado, "
                " ocorrido_em, hash_registro) "
                "VALUES (:id, :tenant_id, :sequencia, :evento, :entidade, :acao, 'sistema', "
                "        'sucesso', :ocorrido_em, :hash_registro)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "sequencia": sequencia,
                "evento": f"{entidade}.{acao}",
                "entidade": entidade,
                "acao": acao,
                "ocorrido_em": agora,
                "hash_registro": hash_registro,
            },
        )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    definicao = await _definicao(sessao_f11, contexto_f11, "auditoria")

    resultado_entidade = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id, filtros={"entidade": "colaboradores"}),
    )
    assert len(resultado_entidade.linhas) == 2
    assert all(linha["entidade"] == "colaboradores" for linha in resultado_entidade.linhas)

    resultado_acao = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id, filtros={"acao": "criar"}),
    )
    assert len(resultado_acao.linhas) == 2
    assert all(linha["acao"] == "criar" for linha in resultado_acao.linhas)

    resultado_ambos = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(
            tenant_id=tenant_id, filtros={"entidade": "colaboradores", "acao": "criar"}
        ),
    )
    assert len(resultado_ambos.linhas) == 1
    assert resultado_ambos.linhas[0]["entidade"] == "colaboradores"
    assert resultado_ambos.linhas[0]["acao"] == "criar"


# =============================================================================
# 20. dispositivos-canais
# =============================================================================


async def test_dispositivos_canais_agrupado_por_canal(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    tenant_id = contexto_f11.tenant_id
    colaborador_a = contexto_f11.colaboradores[0]
    agora = dt.datetime.now(tz=dt.UTC)
    marcacoes = [
        ("terminal", 1, agora),
        ("terminal", 2, agora + dt.timedelta(minutes=1)),
        ("mobile", 3, agora + dt.timedelta(minutes=2)),
    ]
    for canal, nsr, quando in marcacoes:
        await sessao_f11.execute(
            text(
                "INSERT INTO marcacoes "
                "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, vinculo_id, nsr, cpf, "
                " datahora_marcacao, canal, crc16, hash_registro) "
                "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :vinculo_id, "
                "        :nsr, :cpf, :datahora_marcacao, :canal, 1, :hash_registro)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "rep_p_id": extras_gerenciais.rep_p_id,
                "empresa_id": contexto_f11.empresa_id,
                "colaborador_id": colaborador_a.colaborador_id,
                "vinculo_id": colaborador_a.vinculo_id,
                "nsr": nsr,
                "cpf": f"{nsr:011d}",
                "datahora_marcacao": quando,
                "canal": canal,
                "hash_registro": f"{nsr:064d}",
            },
        )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    definicao = await _definicao(sessao_f11, contexto_f11, "dispositivos-canais")
    resultado = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id),
        agrupamento="canal",
    )
    por_canal = {linha["canal"]: linha["quantidadeMarcacoes"] for linha in resultado.linhas}
    assert por_canal["terminal"] == 2
    assert por_canal["mobile"] == 1


# =============================================================================
# 21. custo-horas-extras
# =============================================================================


async def test_custo_horas_extras_caso_de_mesa(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    tenant_id = contexto_f11.tenant_id
    colaborador_a = contexto_f11.colaboradores[0]
    await sessao_f11.execute(
        text("UPDATE vinculos SET cargo_id = :cargo_id WHERE id = :vinculo_id"),
        {"cargo_id": extras_gerenciais.cargo_id, "vinculo_id": colaborador_a.vinculo_id},
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    definicao = await _definicao(sessao_f11, contexto_f11, "custo-horas-extras")
    resultado = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id, colaborador_id=colaborador_a.colaborador_id),
    )
    # Colaborador A: 30 min de extra/dia (bruto, ApuracaoComponente.minutos)
    # x 3 dias uteis = 3 linhas he50; minutos_equivalentes = int(30*1.5)=45
    # e a base do valorTotal, mesmo sem estar exposto no catalogo padrao
    # (colunasDisponiveis semeadas por A1 so tem colaboradorNome/minutos/
    # valorHora/valorTotal -- "minutos" aqui e o BRUTO, nao o equivalente).
    assert len(resultado.linhas) == 3
    linha = resultado.linhas[0]
    assert linha["minutos"] == 30
    # Caso de mesa: salario 4400.00, valorHora = 4400/220 = 20.00 exatos;
    # minutosEquivalentes=45 -> valorTotal = (45/60) * 20.00 = 15.00.
    assert float(linha["valorHora"]) == 20.00
    assert float(linha["valorTotal"]) == 15.00


# =============================================================================
# 22. headcount-por-area
# =============================================================================


async def test_headcount_por_area_agrupado(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao = await _definicao(sessao_f11, contexto_f11, "headcount-por-area")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
        agrupamento="departamento",
    )
    por_departamento = {
        linha["departamento"]: linha["quantidadeVinculos"] for linha in resultado.linhas
    }
    assert por_departamento["Operacoes"] == 2
    assert por_departamento["Financeiro"] == 1


# =============================================================================
# 23. arquivos-fiscais-historico
# =============================================================================


async def test_arquivos_fiscais_historico_vazio_por_padrao(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """F12 roda em paralelo -- zero linhas e o comportamento correto quando
    nenhum AFD/AEJ foi gerado ainda (PCF §2.2)."""
    definicao = await _definicao(sessao_f11, contexto_f11, "arquivos-fiscais-historico")
    resultado = await executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=contexto_f11.tenant_id),
    )
    assert resultado.linhas == []


async def test_arquivos_fiscais_historico_com_afd_e_aej(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, extras_gerenciais: ExtrasGerenciais
) -> None:
    tenant_id = contexto_f11.tenant_id
    await sessao_f11.execute(
        text(
            "INSERT INTO afd_arquivos "
            "(id, tenant_id, empresa_id, rep_p_id, periodo_inicio, periodo_fim, nsr_inicial, "
            " nsr_final, nome_arquivo, status, gerado_em) "
            "VALUES (:id, :tenant_id, :empresa_id, :rep_p_id, :inicio, :fim, 1, 10, "
            "        'afd_teste.txt', 'gerado', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "empresa_id": contexto_f11.empresa_id,
            "rep_p_id": extras_gerenciais.rep_p_id,
            "inicio": contexto_f11.periodo_data_inicio,
            "fim": contexto_f11.periodo_data_fim,
        },
    )
    await sessao_f11.execute(
        text(
            "INSERT INTO aej_arquivos "
            "(id, tenant_id, empresa_id, periodo_inicio, periodo_fim, nome_arquivo, "
            " ptrp_identificacao, status, gerado_em) "
            "VALUES (:id, :tenant_id, :empresa_id, :inicio, :fim, 'aej_teste.txt', "
            "        'PTRP-TESTE', 'gerado', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "empresa_id": contexto_f11.empresa_id,
            "inicio": contexto_f11.periodo_data_inicio,
            "fim": contexto_f11.periodo_data_fim,
        },
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    definicao = await _definicao(sessao_f11, contexto_f11, "arquivos-fiscais-historico")
    resultado = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id),
    )
    tipos = {linha["tipo"] for linha in resultado.linhas}
    assert tipos == {"AFD", "AEJ"}

    resultado_so_afd = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id, filtros={"tipo": "afd"}),
    )
    assert {linha["tipo"] for linha in resultado_so_afd.linhas} == {"AFD"}


# =============================================================================
# 24. lgpd-acessos-e-titulares
# =============================================================================


async def test_lgpd_acessos_e_titulares(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    tenant_id = contexto_f11.tenant_id
    colaborador_a = contexto_f11.colaboradores[0]
    await sessao_f11.execute(
        text(
            "INSERT INTO acessos_dados_sensiveis "
            "(id, tenant_id, colaborador_id, categoria, finalidade, base_legal, acao, "
            " ocorrido_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, 'biometria', 'auditoria de teste', "
            "        'obrigacao_legal', 'leitura', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
        },
    )
    await sessao_f11.execute(
        text(
            "INSERT INTO solicitacoes_titular "
            "(id, tenant_id, colaborador_id, protocolo, requerente_nome, tipo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :protocolo, 'Colaborador de Teste F11', "
            "        'acesso', 'recebida')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
            "protocolo": f"PROT-{uuid.uuid4().hex[:8]}",
        },
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    definicao = await _definicao(sessao_f11, contexto_f11, "lgpd-acessos-e-titulares")
    resultado = await executar_dataset(
        sessao_f11,
        tenant_id,
        definicao,
        filtros=ContextoConsulta(tenant_id=tenant_id, colaborador_id=colaborador_a.colaborador_id),
    )
    # `colunasDisponiveis` semeadas por A1 para este relatorio sao
    # [usuarioId, permissaoCodigo, criadoEm] -- "tipo" (acesso/solicitacao)
    # nao esta no catalogo padrao, ver achado de contrato no docstring de
    # `lgpd_acessos_e_titulares`. Prova aqui so o que o catalogo expoe.
    assert len(resultado.linhas) == 2
    assert all(linha["usuarioId"] is None for linha in resultado.linhas)
    assert all(linha["criadoEm"] is not None for linha in resultado.linhas)
    # `permissaoCodigo` nao existe nas tabelas reais (achado de contrato
    # registrado): a coluna resolve para NULL em vez de quebrar.
    assert all(linha["permissaoCodigo"] is None for linha in resultado.linhas)


async def test_lgpd_acessos_e_titulares_uniao_via_funcao_direta(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Chama a função diretamente para provar que a união realmente traz
    UMA linha de cada tabela (`tipo` não está no catálogo padrão, ver teste
    acima)."""
    tenant_id = contexto_f11.tenant_id
    colaborador_a = contexto_f11.colaboradores[0]
    await sessao_f11.execute(
        text(
            "INSERT INTO acessos_dados_sensiveis "
            "(id, tenant_id, colaborador_id, categoria, finalidade, base_legal, acao, "
            " ocorrido_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, 'biometria', 'auditoria de teste', "
            "        'obrigacao_legal', 'leitura', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
        },
    )
    await sessao_f11.execute(
        text(
            "INSERT INTO solicitacoes_titular "
            "(id, tenant_id, colaborador_id, protocolo, requerente_nome, tipo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :protocolo, 'Colaborador de Teste F11', "
            "        'acesso', 'recebida')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
            "protocolo": f"PROT-{uuid.uuid4().hex[:8]}",
        },
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    from app.relatorios.datasets.gerenciais import lgpd_acessos_e_titulares

    consulta = lgpd_acessos_e_titulares(
        sessao_f11,
        tenant_id,
        ContextoConsulta(tenant_id=tenant_id, colaborador_id=colaborador_a.colaborador_id),
    )
    linhas = (await sessao_f11.execute(consulta)).mappings().all()
    tipos = {linha["tipo"] for linha in linhas}
    assert tipos == {"acesso", "solicitacao"}
