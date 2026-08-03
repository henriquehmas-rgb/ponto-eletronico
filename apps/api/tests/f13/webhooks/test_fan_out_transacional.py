"""T11 -- o teste mais importante da fase (PCF F13 secao 8): prova que a
linha em `webhook_entregas` so existe depois que o fato de dominio esta
commitado, nunca antes/em vez de.

Nota de RLS (achado real desta suite, nao do mecanismo): `SET LOCAL
app.tenant_id` vale so para a transacao CORRENTE -- cada `sessao.commit()`
encerra a transacao e a proxima instrucao comeca uma transacao NOVA sem
`app.tenant_id` publicado, entao qualquer leitura/escrita PELA MESMA sessao
depois de um commit precisa reaplicar `SET LOCAL` (`_reaplicar_tenant`
abaixo) ou RLS devolve zero linhas silenciosamente -- nao um erro, o que
torna esse esquecimento facil de confundir com "o fan-out nao funcionou".

Rodar so este arquivo: `pytest tests/f13/webhooks -q -k "rollback or transacional" -s`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integracoes.webhooks import fan_out

pytestmark = pytest.mark.asyncio


async def _reaplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )


async def _commit_e_reaplicar(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.commit()
    await _reaplicar_tenant(sessao, tenant_id)


async def _criar_webhook_ativo(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, api_client_id: uuid.UUID, eventos: list[str]
) -> uuid.UUID:
    webhook_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO webhooks "
            "(id, tenant_id, api_client_id, nome, url, eventos, segredo_hmac_cifrado, "
            " chave_id, max_tentativas, timeout_segundos, status) "
            "VALUES (:id, :tenant_id, :api_client_id, :nome, :url, :eventos, :segredo, "
            "        'webh-v1', 8, 10, 'ativo')"
        ),
        {
            "id": webhook_id,
            "tenant_id": tenant_id,
            "api_client_id": api_client_id,
            "nome": f"webhook-teste-{webhook_id.hex[:8]}",
            "url": "https://example.invalid/receber",
            "eventos": eventos,
            "segredo": b"\x00" * 28,  # blob qualquer -- este teste nao decifra
        },
    )
    return webhook_id


async def _contar_entregas(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, evento_id: uuid.UUID
) -> int:
    linha = (
        await sessao.execute(
            text(
                "SELECT count(*) AS n FROM webhook_entregas "
                "WHERE tenant_id = :tenant_id AND evento_id = :evento_id"
            ),
            {"tenant_id": tenant_id, "evento_id": evento_id},
        )
    ).one()
    return int(linha.n)


def _envelope(tipo: str, tenant_id: uuid.UUID) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "versao": 1,
        "ocorridoEm": datetime.now(tz=UTC).isoformat(),
        "publicadoEm": datetime.now(tz=UTC).isoformat(),
        "tenantId": str(tenant_id),
        "dados": {},
    }


async def test_rollback_da_transacao_de_dominio_nunca_gera_entrega(
    sessao_f13a3, contexto_webhooks_f13a3
):
    """O requisito nao negociavel do PCF, provado contra o mecanismo REAL de
    A3 (`app.pessoas.eventos.publicar`, um dos nove pontos do catalogo)."""
    from app.pessoas.eventos import publicar

    ctx = contexto_webhooks_f13a3
    await _criar_webhook_ativo(
        sessao_f13a3,
        tenant_id=ctx.tenant_id,
        api_client_id=ctx.api_client_id,
        eventos=["colaborador.admitido"],
    )
    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    envelope = _envelope("colaborador.admitido", ctx.tenant_id)
    publicar(envelope)  # empilha no ContextVar, NAO grava nada ainda

    # Simula a transacao de dominio falhando: rollback em vez de commit --
    # exatamente o caminho de `app/db/sessao.py::obter_sessao` numa excecao.
    await sessao_f13a3.rollback()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    total = await _contar_entregas(
        sessao_f13a3, tenant_id=ctx.tenant_id, evento_id=uuid.UUID(envelope["id"])
    )
    assert total == 0, "rollback do fato de dominio NUNCA pode deixar uma entrega para tras"


async def test_commit_da_transacao_de_dominio_gera_entrega_pendente(
    sessao_f13a3, contexto_webhooks_f13a3
):
    """O caminho feliz do mesmo requisito: commit real produz a linha
    durável, com os campos que o worker (T12) precisa para entregar."""
    from app.pessoas.eventos import publicar

    ctx = contexto_webhooks_f13a3
    webhook_id = await _criar_webhook_ativo(
        sessao_f13a3,
        tenant_id=ctx.tenant_id,
        api_client_id=ctx.api_client_id,
        eventos=["colaborador.admitido"],
    )
    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    envelope = _envelope("colaborador.admitido", ctx.tenant_id)
    publicar(envelope)
    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)  # <- dispara after_commit (fan_out)

    linha = (
        await sessao_f13a3.execute(
            text(
                "SELECT webhook_id, evento, status, tentativa, payload, proxima_tentativa_em "
                "FROM webhook_entregas WHERE tenant_id = :tenant_id AND evento_id = :evento_id"
            ),
            {"tenant_id": ctx.tenant_id, "evento_id": envelope["id"]},
        )
    ).one()
    assert str(linha.webhook_id) == str(webhook_id)
    assert linha.evento == "colaborador.admitido"
    assert linha.status == "pendente"
    assert linha.tentativa == 1
    assert linha.payload["id"] == envelope["id"]
    assert linha.proxima_tentativa_em is not None


async def test_webhook_inativo_ou_nao_assinante_nao_recebe_entrega(
    sessao_f13a3, contexto_webhooks_f13a3
):
    """Fan-out so cria linha para webhook `status='ativo'` que assina O
    evento -- nao para todo webhook do tenant."""
    from app.pessoas.eventos import publicar

    ctx = contexto_webhooks_f13a3
    await _criar_webhook_ativo(
        sessao_f13a3,
        tenant_id=ctx.tenant_id,
        api_client_id=ctx.api_client_id,
        eventos=["colaborador.demitido"],  # NAO o evento que sera publicado
    )
    suspenso_id = await _criar_webhook_ativo(
        sessao_f13a3,
        tenant_id=ctx.tenant_id,
        api_client_id=ctx.api_client_id,
        eventos=["colaborador.admitido"],
    )
    await sessao_f13a3.execute(
        text("UPDATE webhooks SET status = 'suspenso' WHERE id = :id"), {"id": suspenso_id}
    )
    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    envelope = _envelope("colaborador.admitido", ctx.tenant_id)
    publicar(envelope)
    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    total = await _contar_entregas(
        sessao_f13a3, tenant_id=ctx.tenant_id, evento_id=uuid.UUID(envelope["id"])
    )
    assert total == 0


@pytest.mark.parametrize(
    "modulo,tipo",
    [
        ("app.marcacao.eventos", "marcacao.criada"),
        ("app.pessoas.eventos", "colaborador.admitido"),
        ("app.apuracao.dominio.eventos", "ocorrencia.aberta"),
        ("app.apuracao.tratamento.eventos", "apuracao.recalculada"),
        ("app.apuracao.banco_horas.eventos", "banco_horas.quitado"),
        ("app.workflow.solicitacoes.eventos", "ajuste.solicitado"),
        ("app.workflow.fechamento.eventos", "periodo.fechado"),
        ("app.fiscal.afd.eventos", "afd.gerado"),
        ("app.fiscal.aej.eventos", "aej.gerado"),
    ],
)
async def test_nove_pontos_de_publicacao_apps_api_alimentam_fan_out(
    sessao_f13a3, contexto_webhooks_f13a3, modulo, tipo
):
    """Os nove `publicar()` de `apps/api` (marcacao/pessoas/apuracao x3/
    workflow x2/fiscal x2) sao byte-a-byte o mesmo corpo (T11 aditivo,
    identico nos nove) -- exercitados aqui um a um, pelo NOME do evento que
    cada modulo realmente publica (`ocorrencia.aberta`/`comprovante.emitido`
    sao internos: nenhum webhook pode assina-los, mas o `publicar()` ainda
    roda sem erro, provando que a chamada aditiva nunca quebra
    `BARRAMENTO_INTERNO`)."""
    import importlib

    mod = importlib.import_module(modulo)

    ctx = contexto_webhooks_f13a3
    mod.limpar_barramento()

    webhook_id = None
    if tipo not in fan_out.EVENTOS_INTERNOS:
        webhook_id = await _criar_webhook_ativo(
            sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id, eventos=[tipo]
        )
        await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    envelope = _envelope(tipo, ctx.tenant_id)
    mod.publicar(envelope)

    # Prova que `BARRAMENTO_INTERNO` continua funcionando EXATAMENTE como
    # antes (proibicao 3 do PCF): o teste de fan-out nao pode quebrar isso.
    assert [envelope] == mod.BARRAMENTO_INTERNO

    await _commit_e_reaplicar(sessao_f13a3, ctx.tenant_id)

    total = await _contar_entregas(
        sessao_f13a3, tenant_id=ctx.tenant_id, evento_id=uuid.UUID(envelope["id"])
    )
    if webhook_id is not None:
        assert total == 1, f"{modulo}: publicar() nao alimentou webhook_entregas"
    else:
        assert total == 0, f"{modulo}: evento interno nao deveria gerar entrega"

    mod.limpar_barramento()
