"""Terceira passada (2026-08-08) sobre `IdempotenciaRetrofitMiddleware`: o
casamento de rota deixou de ser só `(método, caminho)` EXATO e passou a
aceitar TEMPLATE de caminho (`ROTAS_COM_DEDUP_REAL_TEMPLATE`,
`/v1/feriado-conjuntos/{conjuntoId}`), habilitando dedup real nas ~51 rotas
de escrita com parâmetro de path (`PATCH`/`DELETE .../{id}`, ações
`.../{id}/decidir|cancelar|conferir|...`) que antes só validavam a presença
do cabeçalho.

Três níveis de prova, mesmo espírito dos testes das passadas anteriores
(`test_idempotencia_middleware_http_e2e.py`,
`test_idempotencia_middleware_expansao_http_e2e.py`):

1. **`PATCH /v1/feriado-conjuntos/{conjuntoId}` (HTTP e2e real).** A prova
   forte de que o handler NÃO roda no replay: entre a primeira e a segunda
   chamada, a linha é alterada POR FORA da API (UPDATE direto). Se o replay
   reexecutasse o handler, o `UPDATE` do handler sobrescreveria a alteração
   externa; como o middleware devolve a resposta armazenada sem chamar a
   rota, a alteração externa sobrevive intacta. Nenhum teste de "PATCH duas
   vezes com o mesmo corpo dá o mesmo resultado" provaria isso -- `PATCH` já
   é idempotente quanto ao ESTADO por semântica HTTP; o que esta passada
   entrega é dedup de EXECUÇÃO (e portanto dos efeitos colaterais).
2. **`DELETE /v1/feriado-conjuntos/{conjuntoId}` (HTTP e2e real).** Segunda
   chamada com a MESMA chave devolve `204` (replay); com chave DIFERENTE
   devolve `404` -- o que prova ao mesmo tempo que o recurso realmente foi
   excluído (o `204` do replay não é um "não fez nada") e que a dedup é por
   chave, não um engolir cego de erro.
3. **Teste de unidade do casamento por template** (sem HTTP, sem banco):
   casa o caminho concreto, recusa caminho vizinho de mesma profundidade,
   recusa método errado, não deixa o curinga vazar para um caminho mais
   curto/mais longo, e confere que toda entrada de
   `ROTAS_COM_DEDUP_REAL_TEMPLATE` continua reconhecida por
   `tem_dedup_real` (regressão contra remoção acidental numa edição futura,
   mesmo papel do teste barato da passada anterior).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from ponto_contracts.jornada import FeriadoConjunto
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.idempotencia_middleware import (
    ROTAS_COM_DEDUP_REAL,
    ROTAS_COM_DEDUP_REAL_TEMPLATE,
    tem_dedup_real,
)
from tests.f14.hardening.conftest import (
    ContextoF14A2,
    cabecalhos,
    sobrescrever_sujeito,
    sujeito_de_teste,
)

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# 3. Casamento por template -- unidade pura (sem HTTP, sem banco)
# --------------------------------------------------------------------------


def test_template_casa_caminho_concreto_e_recusa_vizinhos() -> None:
    ident = str(uuid.uuid4())

    # Casa o caminho concreto do template.
    assert tem_dedup_real("POST", f"/v1/tratamentos/{ident}/decidir")
    assert tem_dedup_real("PATCH", f"/v1/tratamentos/{ident}")
    assert tem_dedup_real("DELETE", f"/v1/unidades/{ident}/redes-permitidas/{ident}")

    # Método errado no mesmo caminho não casa.
    assert not tem_dedup_real("GET", f"/v1/tratamentos/{ident}")
    assert not tem_dedup_real("PUT", f"/v1/tratamentos/{ident}")

    # Sufixo diferente na mesma profundidade não casa (o curinga vale por UM
    # segmento, o resto continua tendo que bater literal).
    assert not tem_dedup_real("POST", f"/v1/tratamentos/{ident}/qualquer-outra")
    assert not tem_dedup_real("PATCH", f"/v1/nao-existe/{ident}")

    # O curinga não vaza para caminho mais curto nem mais longo.
    assert not tem_dedup_real("PATCH", "/v1/tratamentos")
    assert not tem_dedup_real("PATCH", f"/v1/tratamentos/{ident}/extra")
    assert not tem_dedup_real("POST", f"/v1/tratamentos/{ident}/decidir/extra")

    # Rotas de caminho exato (passadas anteriores) continuam casando, e
    # continuam NÃO casando com um id pendurado no fim.
    assert tem_dedup_real("POST", "/v1/empresas")
    assert not tem_dedup_real("POST", f"/v1/empresas/{ident}")


def test_todas_as_rotas_com_template_continuam_reconhecidas() -> None:
    """Regressão barata: cada template declarado tem que ser reconhecido
    quando instanciado com ids reais -- pega tanto uma remoção acidental da
    lista quanto uma quebra do índice de prefixos."""
    faltando: list[tuple[str, str]] = []
    for metodo, template in sorted(ROTAS_COM_DEDUP_REAL_TEMPLATE):
        concreto = "/".join(
            str(uuid.uuid4()) if seg.startswith("{") else seg for seg in template.split("/")
        )
        if not tem_dedup_real(metodo, concreto):
            faltando.append((metodo, template))
    assert not faltando, f"template(s) não reconhecido(s) por tem_dedup_real: {faltando}"


def test_listas_exata_e_template_nao_se_sobrepoem() -> None:
    """Um caminho com `{` na lista EXATA nunca casaria nada (a lista exata é
    comparada contra o caminho concreto), e um caminho sem `{` na lista de
    templates seria uma entrada exata escrita no lugar errado."""
    assert not [caminho for _, caminho in ROTAS_COM_DEDUP_REAL if "{" in caminho]
    assert not [caminho for _, caminho in ROTAS_COM_DEDUP_REAL_TEMPLATE if "{" not in caminho]


# --------------------------------------------------------------------------
# 1 e 2. HTTP e2e real contra rota COM parâmetro de path
# --------------------------------------------------------------------------


async def _criar_conjunto(
    cliente: AsyncClient, ctx: ContextoF14A2, *, codigo: str
) -> dict[str, object]:
    sobrescrever_sujeito(cliente, sujeito_de_teste(ctx, permissoes=frozenset({"feriados.criar"})))
    resposta = await cliente.post(
        "/v1/feriado-conjuntos",
        json={"codigo": codigo, "nome": "Nome Original", "abrangencia": "nacional"},
        headers=cabecalhos(ctx.tenant_slug),
    )
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())


async def _nome_no_banco(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, conjunto_id: uuid.UUID
) -> str | None:
    await sessao.rollback()  # garante leitura fora de qualquer transação anterior
    await sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    resultado = await sessao.execute(
        sa.select(FeriadoConjunto.nome).where(
            FeriadoConjunto.tenant_id == tenant_id, FeriadoConjunto.id == conjunto_id
        )
    )
    return resultado.scalar_one_or_none()


async def test_replay_de_patch_com_parametro_de_path_nao_reexecuta_o_handler(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2, sessao_f14a2: AsyncSession
) -> None:
    criado = await _criar_conjunto(
        cliente_http_f14a2, contexto_f14a2, codigo=f"conj-{uuid.uuid4().hex[:10]}"
    )
    conjunto_id = uuid.UUID(str(criado["id"]))

    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"feriados.editar"})),
    )
    corpo = {"nome": "Nome Via API"}
    chave = f"e2e-template-patch-{uuid.uuid4()}"
    caminho = f"/v1/feriado-conjuntos/{conjunto_id}"

    resp1 = await cliente_http_f14a2.patch(
        caminho, json=corpo, headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave)
    )
    assert resp1.status_code == 200, resp1.text
    assert resp1.headers.get("Idempotency-Replayed") == "false"
    assert resp1.json()["nome"] == "Nome Via API"

    # Altera a linha POR FORA da API. Se o replay reexecutasse o handler,
    # este valor seria sobrescrito de volta para "Nome Via API".
    await sessao_f14a2.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(contexto_f14a2.tenant_id)},
    )
    await sessao_f14a2.execute(
        sa.update(FeriadoConjunto)
        .where(
            FeriadoConjunto.tenant_id == contexto_f14a2.tenant_id,
            FeriadoConjunto.id == conjunto_id,
        )
        .values(nome="Mexido Por Fora")
    )
    await sessao_f14a2.commit()

    resp2 = await cliente_http_f14a2.patch(
        caminho, json=corpo, headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave)
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.headers.get("Idempotency-Replayed") == "true"
    assert resp2.json() == resp1.json(), "replay deve devolver a resposta ARMAZENADA, byte a byte"

    nome_final = await _nome_no_banco(
        sessao_f14a2, tenant_id=contexto_f14a2.tenant_id, conjunto_id=conjunto_id
    )
    assert (
        nome_final == "Mexido Por Fora"
    ), "o handler do PATCH rodou de novo no replay -- a dedup por template não pegou"


async def test_replay_de_delete_com_parametro_de_path_devolve_204_e_chave_nova_da_404(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2
) -> None:
    criado = await _criar_conjunto(
        cliente_http_f14a2, contexto_f14a2, codigo=f"conj-{uuid.uuid4().hex[:10]}"
    )
    conjunto_id = uuid.UUID(str(criado["id"]))

    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"feriados.excluir"})),
    )
    chave = f"e2e-template-delete-{uuid.uuid4()}"
    caminho = f"/v1/feriado-conjuntos/{conjunto_id}"

    resp1 = await cliente_http_f14a2.delete(
        caminho, headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave)
    )
    assert resp1.status_code == 204, resp1.text
    assert resp1.headers.get("Idempotency-Replayed") == "false"

    resp2 = await cliente_http_f14a2.delete(
        caminho, headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave)
    )
    assert resp2.status_code == 204, resp2.text
    assert resp2.headers.get("Idempotency-Replayed") == "true"

    # Controle: com chave DIFERENTE o handler roda de verdade e encontra o
    # conjunto já excluído -- prova que o `204` acima veio do replay, não de
    # um DELETE que "não fez nada".
    resp3 = await cliente_http_f14a2.delete(
        caminho,
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=f"outra-chave-{uuid.uuid4()}"),
    )
    assert resp3.status_code == 404, resp3.text
