"""Retrofit de deduplicação genuína de `idempotencia_generica.py` (F13) para
uma amostra representativa de rotas de escrita de F1-F12 (F14/A2).

**Por que middleware, e não `Depends()` nos routers, para ESTA parte.** O
PCF de F14 (§5, A2) pede o retrofit "via `Depends()`, sem tocar lógica de
negócio" -- e é exatamente isso que `app/comum/limitador_taxa.py::
exigir_limite_taxa_sessao` faz (só acrescenta um parâmetro à assinatura da
rota). Idempotência é diferente por construção: `abrir_operacao`/
`concluir_operacao` (`idempotencia_generica.py`, docstring do módulo)
precisam rodar ANTES e DEPOIS da lógica de negócio, na MESMA transação dela
-- é assim que F13 já implementou nas próprias rotas (`webhooks.py` etc.),
chamando as duas funções de dentro do CORPO do handler. Reproduzir isso nas
~130 rotas de F1-F12 exigiria editar o corpo de cada handler (não só
acrescentar `Depends()`), o que a ownership desta fase proíbe explicitamente
("routers/*.py: EDITAR SÓ PARA ACRESCENTAR Depends()... nunca tocar a
lógica de negócio dentro de cada rota").

A saída: um middleware ASGI que envolve a rota por fora, sem tocar nenhum
arquivo de router. Ele não reaproveita a MESMA sessão/transação do handler
(motivo pelo qual `idempotencia_generica.py` foi desenhado do jeito que foi
-- ver a docstring daquele módulo) porque não tem como: a sessão do handler
é aberta por uma dependência (`app/db/sessao.py::obter_sessao`) interna à
árvore de dependências do FastAPI, inacessível a um middleware que roda por
fora dela. Em vez disso, este middleware abre a PRÓPRIA sessão/transação,
curta, só para `idempotencia_chaves`, e decide se deixa o handler rodar:

1. Antes de chamar a rota: tenta abrir a operação (mesmo
   `pg_try_advisory_xact_lock` de `idempotencia_generica.abrir_operacao`).
   Se já concluída, a resposta ARMAZENADA é devolvida direto -- a rota
   NUNCA roda (dedup real, não só validação de cabeçalho). Se em conflito
   (chave em voo ou corpo diferente), `409` sem chamar a rota.
2. Só então chama a rota de verdade, na sessão PRÓPRIA dela (como sempre).
3. Depois que a rota responde: sucesso (`2xx`) grava a resposta para
   replay futuro e COMMITA; qualquer outro status faz ROLLBACK -- a
   tentativa falhada nunca "envenena" a chave (mesma semântica que
   `idempotencia_generica.py` já documenta para o caso do handler chamar as
   funções diretamente).

**Por que uma ALLOWLIST explícita, não todo `POST/PUT/PATCH/DELETE`.** Um
middleware genérico tocando toda escrita da API é um raio de explosão que
esta sessão não tem como revisar/testar com segurança (streaming, corpos
grandes, rotas que já têm idempotência própria -- `marcacoes.py`/F5,
`webhooks.py`/F13). A allowlist abaixo é a amostra representativa que o
critério de aceite de A2 pede (PCF F14 §5: "numa amostra representativa de
rotas de F1-F12"), escolhida a dedo por span de fase (F2/F3/F6) e por serem
rotas de criação simples (path sem parâmetro, corpo JSON pequeno, sem
upload). O resto de F1-F12 recebe só `Depends(exigir_idempotencia())`
(retrofit de verdade, mas limitado à validação do cabeçalho -- ver
`docs/backlog.md`, 2026-08-05, para o motivo da não-cobertura total).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Final
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
)
from app.core import contexto, erros
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger
from app.db.sessao import aplicar_tenant, fabrica_de_sessoes

logger = obter_logger("idempotencia_middleware")

ProximoMiddleware = Callable[[Request], Awaitable[Response]]

#: Amostra representativa (F14/A2) -- ver docstring do módulo. `(método,
#: caminho)` EXATO (nenhuma rota aqui tem parâmetro de path, de propósito:
#: mantém o casamento O(1), sem regex, sem risco de casar caminho errado).
ROTAS_COM_DEDUP_REAL: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("POST", "/v1/colaboradores"),  # F2
        ("POST", "/v1/empresas"),  # F2
        ("POST", "/v1/unidades"),  # F2
        ("POST", "/v1/departamentos"),  # F2
        ("POST", "/v1/contratos"),  # F2
        ("POST", "/v1/escalas"),  # F3
        ("POST", "/v1/feriados"),  # F3
        ("POST", "/v1/horarios"),  # F3
        ("POST", "/v1/afastamentos"),  # F9b
        ("POST", "/v1/dispositivos"),  # F6
    }
)

_CABECALHOS_NAO_REPASSADOS: Final[frozenset[str]] = frozenset(
    {"content-length", "content-encoding", "transfer-encoding"}
)


def _resposta_direta(
    status: int, corpo: dict[str, object], cabecalhos: dict[str, str] | None = None
) -> Response:
    return erros.RespostaProblema(status_code=status, content=corpo, headers=cabecalhos or None)


class IdempotenciaRetrofitMiddleware(BaseHTTPMiddleware):
    """Ver docstring do módulo. Só age nas rotas de `ROTAS_COM_DEDUP_REAL`."""

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        alvo = (request.method, request.url.path)
        if alvo not in ROTAS_COM_DEDUP_REAL:
            return await call_next(request)

        chave_bruta = (request.headers.get("Idempotency-Key") or "").strip()
        if not chave_bruta:
            status, corpo = erros.montar_problema(codigo="PONTO-IDEM-001", caminho=request.url.path)
            return _resposta_direta(status, corpo)

        tenant_bruto = contexto.tenant_atual()
        if not tenant_bruto:
            # Sem tenant resolvido, deixa a rota seguir e falhar do jeito
            # normal (`obter_sessao` recusa com `PONTO-VAL-011`) -- não é
            # papel deste middleware inventar esse erro.
            return await call_next(request)

        try:
            tenant_id = UUID(tenant_bruto)
        except ValueError:
            return await call_next(request)

        corpo_bruto = await request.body()
        chave = ChaveIdempotencia(
            valor=chave_bruta[:255],
            corpo_hash=hashlib.sha256(corpo_bruto).hexdigest(),
        )
        escopo = f"{request.method}:{request.url.path}"

        fabrica = fabrica_de_sessoes()
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant_id))
            try:
                resultado = await abrir_operacao(
                    sessao, tenant_id=tenant_id, escopo=escopo, chave=chave
                )
            except ErroDeAplicacao as exc:
                await sessao.rollback()
                status, corpo = erros.montar_problema(
                    codigo=exc.codigo,
                    caminho=request.url.path,
                    detalhe=exc.detalhe,
                    tentar_novamente_em=exc.tentar_novamente_em,
                )
                cabecalhos = dict(exc.cabecalhos)
                logger.info(
                    "idempotencia (middleware): conflito",
                    extra={"codigo": exc.codigo, "escopo": escopo},
                )
                return _resposta_direta(status, corpo, cabecalhos)

            if resultado.ja_concluido:
                await sessao.rollback()  # nada a persistir, só leitura
                logger.info("idempotencia (middleware): replay", extra={"escopo": escopo})
                corpo_replay = resultado.resposta_corpo
                resposta = Response(
                    content=json.dumps(corpo_replay) if corpo_replay is not None else b"",
                    status_code=resultado.resposta_status or 200,
                    media_type="application/json" if corpo_replay is not None else None,
                )
                resposta.headers["Idempotency-Replayed"] = "true"
                return resposta

            # Operação nova: a rota roda de verdade, na PRÓPRIA sessão dela
            # (aberta por `Depends(obter_sessao)`, como sempre) -- este
            # middleware só observa o resultado por fora.
            resposta_real = await call_next(request)

            if not (200 <= resposta_real.status_code < 300):
                # Tentativa falhou: nunca persiste como concluída -- o
                # rollback libera a chave para a próxima tentativa (mesma
                # semântica de `idempotencia_generica.py`, docstring do
                # módulo, "uma tentativa que falhou nunca envenena a
                # chave").
                await sessao.rollback()
                return resposta_real

            pedacos = [secao async for secao in resposta_real.body_iterator]  # type: ignore[attr-defined]
            corpo_bytes = b"".join(
                secao if isinstance(secao, bytes) else secao.encode("utf-8") for secao in pedacos
            )
            try:
                corpo_para_guardar = json.loads(corpo_bytes) if corpo_bytes else None
            except ValueError:
                corpo_para_guardar = None

            await concluir_operacao(
                sessao,
                registro_id=resultado.registro_id,
                status_http=resposta_real.status_code,
                corpo_resposta=corpo_para_guardar,
            )
            await sessao.commit()

            cabecalhos_repassados = {
                nome: valor
                for nome, valor in resposta_real.headers.items()
                if nome.lower() not in _CABECALHOS_NAO_REPASSADOS
            }
            cabecalhos_repassados["Idempotency-Replayed"] = "false"
            return Response(
                content=corpo_bytes,
                status_code=resposta_real.status_code,
                headers=cabecalhos_repassados,
                media_type=resposta_real.media_type,
            )
