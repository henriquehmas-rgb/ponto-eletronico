"""Testes puros (sem banco) de `app.notificacao.mensagens` (T10)."""

from __future__ import annotations

from app.notificacao import mensagens


def test_todos_os_templates_produzem_titulo_e_corpo_nao_vazios() -> None:
    dados_exemplo = {
        "protocolo": "2026-000123",
        "tipoSolicitacaoCodigo": "ajuste_ponto",
        "dataReferencia": "2026-07-22",
        "motivo": "Divergência com o controle de acesso.",
        "dataInicio": "2026-07-01",
        "dataFim": "2026-07-31",
        "totalColaboradores": 12,
        "carimboTempo": "2026-08-04T11:07:55-03:00",
        "versaoEspelho": 1,
        "codigo": "jornada_excedida",
        "data": "2026-07-22",
        "descricao": "Jornada excedida em 45 minutos.",
        "prazoEm": "2026-07-27T18:00:00-03:00",
    }
    for tipo, montador in mensagens.TEMPLATES.items():
        mensagem = montador(dados_exemplo)
        assert mensagem.titulo.strip(), f"titulo vazio para {tipo}"
        assert mensagem.corpo.strip(), f"corpo vazio para {tipo}"


def test_templates_toleram_payload_incompleto_sem_levantar() -> None:
    for montador in mensagens.TEMPLATES.values():
        mensagem = montador({})
        assert mensagem.titulo
        assert mensagem.corpo


def test_montar_mensagem_evento_desconhecido_devolve_none() -> None:
    assert mensagens.montar_mensagem("evento.que.nao.existe", {}) is None


def test_montar_mensagem_evento_conhecido_devolve_mensagem() -> None:
    mensagem = mensagens.montar_mensagem(
        mensagens.NOME_AJUSTE_APROVADO, {"protocolo": "2026-000001", "dataReferencia": "2026-07-01"}
    )
    assert mensagem is not None
    assert "2026-000001" in mensagem.corpo
