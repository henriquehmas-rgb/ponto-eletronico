"""Prova o caminho HTTP real da RFC-015 (critério de aceite oficial 4,
PCF §7): `PUT` seguido de `GET` numa sessão nova devolve exatamente a mesma
configuração por `usuario_id` + `relatorioDefinicaoId`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.f11.conftest import ContextoF11, cabecalhos, construir_sujeito, sobrescrever_sujeito


def _autenticar(cliente: TestClient, contexto_f11: ContextoF11) -> None:
    sobrescrever_sujeito(
        cliente,
        construir_sujeito(
            usuario_id=contexto_f11.usuario_rh_id,
            tenant_id=contexto_f11.tenant_id,
            permissoes=frozenset({"relatorios.ler"}),
        ),
    )


def test_put_seguido_de_get_devolve_exatamente_a_mesma_configuracao(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    _autenticar(cliente, contexto_f11)
    relatorio_id = str(contexto_f11.relatorio_ids["espelho-jornada"])
    corpo = {
        "relatorioDefinicaoId": relatorio_id,
        "nome": "padrao",
        "colunas": ["nomeCompleto", "matricula", "extrasMinutos"],
        "ordenacao": {"campo": "nomeCompleto", "direcao": "asc"},
        "larguras": {"nomeCompleto": 220, "matricula": 120},
        "padrao": True,
    }

    resposta_put = cliente.put(
        "/v1/relatorios/preferencias-colunas",
        json=corpo,
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert resposta_put.status_code == 200, resposta_put.text
    gravado = resposta_put.json()
    assert gravado["relatorioDefinicaoId"] == relatorio_id
    assert gravado["usuarioId"] == str(contexto_f11.usuario_rh_id)
    assert gravado["colunas"] == corpo["colunas"]
    assert gravado["larguras"] == corpo["larguras"]
    assert gravado["padrao"] is True

    # "Sessao nova": cada requisicao HTTP ja abre/fecha sua propria SessaoDb
    # (app/db/sessao.py::obter_sessao) -- este GET nao reaproveita nenhum
    # estado em memoria da chamada PUT acima, so o que foi commitado no banco.
    resposta_get = cliente.get(
        "/v1/relatorios/preferencias-colunas",
        params={"relatorioDefinicaoId": relatorio_id},
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert resposta_get.status_code == 200, resposta_get.text
    lido = resposta_get.json()
    assert len(lido["dados"]) == 1
    relida = lido["dados"][0]
    assert relida["id"] == gravado["id"]
    assert relida["colunas"] == corpo["colunas"]
    assert relida["ordenacao"] == corpo["ordenacao"]
    assert relida["larguras"] == corpo["larguras"]
    assert relida["padrao"] is True


def test_put_reenviado_atualiza_em_vez_de_duplicar(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    _autenticar(cliente, contexto_f11)
    relatorio_id = str(contexto_f11.relatorio_ids["banco-de-horas"])
    corpo_inicial = {
        "relatorioDefinicaoId": relatorio_id,
        "colunas": ["colaboradorNome"],
    }
    primeira = cliente.put(
        "/v1/relatorios/preferencias-colunas",
        json=corpo_inicial,
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert primeira.status_code == 200, primeira.text

    corpo_atualizado = {
        "relatorioDefinicaoId": relatorio_id,
        "colunas": ["colaboradorNome", "data", "minutos"],
    }
    segunda = cliente.put(
        "/v1/relatorios/preferencias-colunas",
        json=corpo_atualizado,
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["id"] == primeira.json()["id"]

    listagem = cliente.get(
        "/v1/relatorios/preferencias-colunas",
        params={"relatorioDefinicaoId": relatorio_id},
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert len(listagem.json()["dados"]) == 1


def test_put_com_relatorio_e_tela_ao_mesmo_tempo_responde_400(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    _autenticar(cliente, contexto_f11)
    resposta = cliente.put(
        "/v1/relatorios/preferencias-colunas",
        json={
            "relatorioDefinicaoId": str(contexto_f11.relatorio_ids["espelho-jornada"]),
            "tela": "grade_apuracao",
            "colunas": ["a"],
        },
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert resposta.status_code == 400, resposta.text
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


def test_get_com_relatorio_e_tela_ao_mesmo_tempo_responde_400(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    _autenticar(cliente, contexto_f11)
    resposta = cliente.get(
        "/v1/relatorios/preferencias-colunas",
        params={
            "relatorioDefinicaoId": str(contexto_f11.relatorio_ids["espelho-jornada"]),
            "tela": "grade_apuracao",
        },
        headers=cabecalhos(contexto_f11.tenant_slug),
    )
    assert resposta.status_code == 400, resposta.text
    assert resposta.json()["codigo"] == "PONTO-VAL-005"
