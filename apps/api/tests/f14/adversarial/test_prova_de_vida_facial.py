"""F14/A4 -- vetor 4: foto impressa/video contra o motor facial via canal
web/terminal.

O mandato descreve este vetor como "prova de vida de `analise-facial-edge`,
ja em producao via F6/F8" -- ou seja, a expectativa e que exista uma prova de
vida REAL para tentar enganar com uma foto impressa ou um video. A4/A1 ja
confirmou por leitura de codigo (achado F14/A1, 2026-08-05, `docs/backlog.md`)
que isto e falso: `apps/facial-svc/facial/rotas/biometria.py` segue 501 desde
a Fase 0, nenhum consumidor chama `/verificar`/`/liveness`.

Este arquivo prova o CONSUMO pratico disso pelo pipeline de registro
(`app.marcacao.pipeline.ingestao`), no territorio proprio de A4 (teste, nao
codigo de producao). Dois achados, status distinto apos o fechamento de F14:

1. **CORRIGIDO no mesmo fechamento.** `politicas_registro.exige_facial`/
   `exige_liveness` eram aceitos pelo motor
   (`app.antifraude.motor._sinais_categoria_biometria`) mas nunca
   consultados -- uma empresa com `exigeFacial=true` (ou o DEFAULT, ja
   `true`) aceitava registros do canal `web` sem nenhum `fotoBase64` com
   score identico a um registro "correto". Corrigido: ausencia de sinal
   exigido agora pontua `_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE` em vez de
   ser excluida da media -- ver `test_marcacao_web_sem_foto_com_exige_
   facial_true_e_penalizada`/`test_exige_facial_true_pontua_pior_que_exige_
   facial_false`.
2. **AINDA ABERTO, decisao deliberada.** `fotoBase64` ENVIADO continua sem
   nenhum consumo real (`MarcacaoCriar.foto_base64` nunca lido em
   `_sinais_do_corpo`) -- uma foto impressa (ou qualquer imagem, ou nenhuma)
   ainda produz o mesmo resultado. Nao corrigido agora porque wire-ar isso
   ate `facial-svc` faria toda chamada com foto FALHAR (o servico segue
   stub) -- ver `test_foto_qualquer_enviada_nao_altera_o_score_de_forma_
   alguma`.

Isto NAO depende de F7 (ADR-014): o vetor e sobre o canal `web`, ja
"produzido" por F8, que o proprio ADR-014 confirma como fase ja commitada.
"""

from __future__ import annotations

import base64

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.antifraude import explicabilidade as antifraude_explicabilidade
from app.core.seguranca import Sujeito
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f14.adversarial.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoDoisTenants,
    ContextoTenant,
    gerar_idempotency_key,
)

#: Um JPEG minimo, sintetico -- representa tanto "foto impressa fotografada
#: de volta pela camera" quanto "qualquer imagem generica": o ponto do teste
#: e que o CONTEUDO e irrelevante, porque nada no pipeline o examina.
_FOTO_QUALQUER_BASE64 = base64.b64encode(b"nao-importa-o-conteudo-desta-foto").decode("ascii")


def _sujeito_web(contexto: ContextoTenant) -> Sujeito:
    return Sujeito(
        usuario_id=contexto.usuario_id,
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar", "marcacoes.ler"}),
    )


async def _registrar_web(
    sessao: AsyncSession,
    contexto: ContextoTenant,
    *,
    foto_base64: str | None,
    liveness_evidencia: dict | None = None,
) -> ingestao.ResultadoRegistro:
    corpo = contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": "web",
            "latitude": GEOCERCA_LATITUDE,
            "longitude": GEOCERCA_LONGITUDE,
            "precisaoMetros": 5.0,
            "fotoBase64": foto_base64,
            "livenessMetodo": "passivo" if foto_base64 else None,
            "livenessEvidencia": liveness_evidencia,
        }
    )
    return await ingestao.registrar_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=_sujeito_web(contexto),
        ip_origem="203.0.113.60",
    )


async def _definir_exige_facial_e_liveness(
    sessao: AsyncSession, contexto: ContextoTenant, *, exige: bool = True
) -> None:
    """Grava uma `politicas_registro` explicita para (empresa, canal='web')
    com `exige_facial`/`exige_liveness` = `exige` -- confirma que o resultado
    do teste nao depende do DEFAULT da coluna, e sim de uma politica
    deliberadamente configurada pelo tenant para EXIGIR biometria."""
    await sessao.execute(
        text(
            "INSERT INTO politicas_registro "
            "(tenant_id, empresa_id, unidade_id, canal, exige_facial, exige_liveness, "
            " exige_geocerca, exige_rede_permitida, limiar_facial, ativo) "
            "VALUES (:tenant_id, :empresa_id, NULL, 'web', :exige, :exige, "
            "        TRUE, FALSE, 75, TRUE)"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "exige": exige,
        },
    )
    await sessao.flush()


async def test_marcacao_web_sem_foto_com_exige_facial_true_e_penalizada(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Regressao do achado original (F14/A4, corrigido no mesmo fechamento):
    politica explicita `exigeFacial=true`/`exigeLiveness=true` para o canal
    web, registro SEM `fotoBase64` agora PONTUA a ausencia
    (`_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE` em `app.antifraude.motor`) em vez
    de excluir a categoria da media -- `disponibilidade` passa a `real`,
    nunca mais `nao_aplicavel`, quando a politica exige o sinal.

    O registro AINDA E ACEITO (nao vira bloqueio duro): `facial-svc` segue
    stub 501 desde a Fase 0 (achado F14/A1, docs/backlog.md) -- bloquear todo
    canal web por uma dependencia que nao existe quebraria o check-in
    inteiro. A correcao e sobre o SCORE refletir a exigencia nao cumprida,
    nao sobre impedir o registro."""
    tenant = contexto_dois_tenants.tenant_a
    await _definir_exige_facial_e_liveness(sessao_f14a4, tenant, exige=True)

    resultado = await _registrar_web(sessao_f14a4, tenant, foto_base64=None)

    assert resultado.resposta.marcacao is not None, "registro sem foto continua aceito."

    marcacao_id = resultado.resposta.marcacao.id
    linha = (
        (
            await sessao_f14a4.execute(
                text(
                    "SELECT flags_integridade, score_facial FROM marcacoes_meta "
                    "WHERE tenant_id = :tenant AND marcacao_id = :marcacao"
                ),
                {"tenant": str(tenant.tenant_id), "marcacao": str(marcacao_id)},
            )
        )
        .mappings()
        .one()
    )
    assert linha["score_facial"] is None
    bloco = linha["flags_integridade"][antifraude_explicabilidade.CHAVE_EXPLICABILIDADE]
    explicabilidade = bloco["scoreExplicabilidade"]
    sinais_biometria = [s for s in explicabilidade if s["categoria"] == "biometria"]
    assert sinais_biometria, "categoria biometria deveria aparecer na explicabilidade"
    assert all(s["disponibilidade"] == "real" for s in sinais_biometria), (
        "com exigeFacial=true, a ausencia de foto deveria contar como sinal "
        "REAL (a politica exige, o sinal esta ausente), nunca nao_aplicavel."
    )
    assert all(
        s["pontuacao"] < 100 for s in sinais_biometria
    ), "ausencia de biometria exigida deveria pontuar abaixo de 100."


async def test_foto_qualquer_enviada_nao_altera_o_score_de_forma_alguma(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Parte deste achado permanece ABERTA apos o fechamento de F14 (achado
    distinto do "exige_facial morto", ja corrigido -- ver
    `test_marcacao_web_sem_foto_com_exige_facial_true_e_penalizada`):
    `foto_base64`/`livenessEvidencia` ENVIADOS continuam sem nenhum consumo
    real -- decisao deliberada deste fechamento, nao lacuna esquecida: wire-ar
    isso ate `facial-svc` (stub 501 desde a Fase 0, achado F14/A1,
    docs/backlog.md) faria toda chamada com foto FALHAR, o que seria pior que
    o estado atual. Enviar UMA foto (poderia ser a foto impressa de outra
    pessoa, um quadro de video, qualquer JPEG) ainda produz EXATAMENTE o
    mesmo score/classificacao de nao enviar nenhuma -- o conteudo da foto e
    irrelevante porque nada o processa. Controle: os dois casos tem o MESMO
    `revisao_requerida` entre si (efeito da penalidade de exige_facial, ja
    corrigida, aplicada igualmente aos dois), nao necessariamente `False`.

    Usa DOIS tenants (nao duas chamadas sequenciais no mesmo tenant/
    dispositivo/colaborador): a reputacao de dispositivo
    (`app.antifraude.reputacao`) e calculada por HISTORICO real, entao duas
    chamadas sequenciais no MESMO dispositivo mudariam a reputacao entre a
    primeira e a segunda so pelo efeito colateral de a primeira ter
    acontecido -- confundindo a comparacao "o conteudo da foto importa?"
    com "o historico do dispositivo mudou?". Tenants separados (mesmo
    padrao de `test_exige_facial_true_pontua_pior_que_exige_facial_false`)
    isolam a variavel que o teste quer medir."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await _definir_exige_facial_e_liveness(sessao_f14a4, tenant_a, exige=True)
    sem_foto = await _registrar_web(sessao_f14a4, tenant_a, foto_base64=None)

    from tests.f14.adversarial.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    await _definir_exige_facial_e_liveness(sessao_f14a4, tenant_b, exige=True)
    com_foto = await _registrar_web(
        sessao_f14a4,
        tenant_b,
        foto_base64=_FOTO_QUALQUER_BASE64,
        liveness_evidencia={"desafio": "piscar", "resultado": "qualquer_coisa"},
    )

    assert sem_foto.resposta.score_confianca == com_foto.resposta.score_confianca
    assert sem_foto.resposta.classificacao_confianca == com_foto.resposta.classificacao_confianca
    assert sem_foto.resposta.revisao_requerida == com_foto.resposta.revisao_requerida


async def test_exige_facial_true_pontua_pior_que_exige_facial_false(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Regressao do achado original (F14/A4, corrigido no mesmo fechamento):
    `exige_facial`/`exige_liveness` deixou de ser configuracao morta.
    Alternar a politica entre `true` e `false` para o MESMO cenario (registro
    sem foto) agora produz scores DIFERENTES -- `exige_facial=true` pontua
    pior, porque a ausencia de um sinal exigido passa a contar contra o
    score (`_PONTUACAO_BIOMETRIA_EXIGIDA_AUSENTE`), em vez de ser excluida da
    media como "canal sem suporte"."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await _definir_exige_facial_e_liveness(sessao_f14a4, tenant_a, exige=True)
    resultado_exige_true = await _registrar_web(sessao_f14a4, tenant_a, foto_base64=None)

    from tests.f14.adversarial.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    await _definir_exige_facial_e_liveness(sessao_f14a4, tenant_b, exige=False)
    resultado_exige_false = await _registrar_web(sessao_f14a4, tenant_b, foto_base64=None)

    assert (
        resultado_exige_true.resposta.score_confianca
        < resultado_exige_false.resposta.score_confianca
    ), (
        "exigeFacial=true sem foto deveria pontuar PIOR que exigeFacial=false "
        "sem foto -- se isto falhar, o fix de exige_facial/exige_liveness "
        "regrediu."
    )
