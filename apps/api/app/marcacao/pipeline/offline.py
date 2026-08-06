"""Sincronizacao de fila offline (F5, T7): `POST /v1/marcacoes/sincronizar-offline`.

Processa um **lote sincrono** (resposta `207`, todo item resolvido na MESMA
chamada -- nunca um job de worker) de itens capturados sem rede. Cada item
tem seu proprio *savepoint* (`sessao.begin_nested()`): uma falha de negocio
num item (HMAC invalido, contador repetido, TTL vencido, ou qualquer
`ErroDeAplicacao` do pipeline de ingestao) desfaz SO as escritas daquele
item e o lote continua com os demais -- nunca aborta a chamada inteira.

**Verificacao de HMAC: STUB documentado, nao criptografia de producao.** Ver
RFC-012 (`docs/rfc/RFC-012-fila-offline-sem-contrato-de-chave-simetrica.md`):
o contrato (`packages/contracts/schema.sql`) nao define nenhuma coluna de
segredo SIMETRICO por dispositivo -- `dispositivos.chave_publica` e
ASSIMETRICA e serve para verificar `MarcacaoCriar.assinaturaPayload`, nao um
HMAC. Sem esse material de chave, `verificar_hmac_item` computa um HMAC-SHA256
deterministico usando `chave_publica` como material de verificacao so para
que o CONTROLE de fluxo desta fase (aceitar, rejeitar por assinatura
invalida, rejeitar por replay, expirar por TTL) seja provavel por teste --
NENHUM aparelho real produziria hoje um HMAC que esta funcao aceite. Mesma
filosofia do `crc16` de `app.marcacao.dominio.nsr` e do motor de confianca
stub de `app.marcacao.confianca.motor`: "calculado e congelado de forma
estavel", nao certificado.

**Decifragem AES-256-GCM: tambem STUB.** Pelo mesmo motivo (RFC-012), esta
fase nao decifra `payloadCifrado` de verdade: trata o campo como o JSON
canonico (com as chaves de `MarcacaoCriar`) codificado em base64 -- o
mecanismo de decifragem real entra quando a RFC-012 for decidida.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import hmac as hmac_mod
import json
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Dispositivo, DispositivoVinculo, FilaOffline
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.pipeline import eventos_marcacao, idempotencia
from app.marcacao.pipeline.ingestao import _politica_efetiva, registrar_marcacao
from app.schemas import contrato

#: TTL de fallback quando o dispositivo nao resolve nenhuma empresa (aparelho
#: orfao de vinculo) -- o mesmo `DEFAULT` de `politicas_registro.ttl_offline_horas`.
_TTL_PADRAO_HORAS = 72

#: Achado da verificacao adversarial (F14/A4, `test_confianca_temporal.py`):
#: acima deste atraso, a classificacao de confianca temporal cai para "baixa"
#: e o sinal passa a pontuar no motor de score (`app.antifraude.motor`), em
#: vez de so alimentar o evento de webhook. Proxy HEURISTICO por magnitude do
#: atraso -- nao a reconciliacao completa dos tres relogios que o ADR-007
#: descreve (essa reconciliacao completa exigiria guardar, por dispositivo,
#: o instante em que o servidor o conheceu pela primeira vez, e comparar
#: deltas monotonicos entre sincronizacoes; ainda nao existe, registrado em
#: docs/backlog.md). Bem abaixo do TTL padrao (72h) de proposito: um item
#: legitimo sincroniza muito antes do TTL estourar em operacao normal: um
#: atraso desta magnitude e incomum mesmo sem ser evidencia definitiva de
#: adulteracao -- por isso pontua (nao bloqueia; ADR-008 regra 7 so torna
#: `mock_location` comprovado, HMAC invalido e assinatura invalida
#: decisivos, nunca atraso por si so).
_LIMIAR_ATRASO_SUSPEITO_MINUTOS = 24 * 60

#: `dispositivos.tipo` -> canal de `politicas_registro`/`MarcacaoCriar`, para
#: resolver a politica (TTL, geocerca, etc.) aplicavel ao item offline.
_CANAL_POR_TIPO_DISPOSITIVO: dict[str, str] = {
    "celular": "mobile",
    "tablet": "mobile",
    "terminal": "terminal",
    "totem": "totem",
    "navegador": "web",
    "integracao": "api",
}


@dataclass(frozen=True, slots=True)
class ItemProcessado:
    """Desfecho de um item, ja no vocabulario de `ResultadoItemOffline`."""

    contador_monotonico: int
    status: str
    marcacao_id: UUID | None = None
    nsr: int | None = None
    codigo_erro: str | None = None
    mensagem: str | None = None


def _bytes_do_campo(valor: str | bytes | None) -> bytes:
    """`ItemFilaOffline.payloadCifrado`/`iv` chegam como `Base64Str` do
    Pydantic. Dependendo da versao, o valor python pode ja vir decodificado
    (str/bytes) ou ainda codificado em base64 -- tenta decodificar e cai para
    UTF-8 bruto quando nao e base64 valido, para o mesmo valor produzir
    sempre o mesmo resultado (e o teste, que monta o item com a mesma
    funcao, sempre bate)."""
    if valor is None:
        return b""
    bruto = valor if isinstance(valor, bytes) else valor.encode("utf-8")
    try:
        return base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError):
        return bruto


def calcular_hmac_item(chave_material: str, item: contrato.ItemFilaOffline) -> str:
    """Formula do HMAC-SHA256 do item (STUB -- ver docstring do modulo).
    `chave_material` e `dispositivos.chave_publica` (ou `""` quando o
    dispositivo nao tem uma cadastrada)."""
    datahora_txt = (
        item.datahora_dispositivo.isoformat().encode("utf-8") if item.datahora_dispositivo else b""
    )
    mensagem = (
        str(item.contador_monotonico).encode("utf-8")
        + b":"
        + _bytes_do_campo(item.payload_cifrado)
        + b":"
        + _bytes_do_campo(item.iv)
        + b":"
        + datahora_txt
    )
    return hmac_mod.new(chave_material.encode("utf-8"), mensagem, hashlib.sha256).hexdigest()


def verificar_hmac_item(chave_material: str, item: contrato.ItemFilaOffline) -> bool:
    """`True` quando `item.hmac` bate com `calcular_hmac_item`. Comparacao em
    tempo constante (`hmac.compare_digest`)."""
    esperado = calcular_hmac_item(chave_material, item)
    return hmac_mod.compare_digest(esperado, item.hmac or "")


def _decodificar_payload(item: contrato.ItemFilaOffline) -> contrato.MarcacaoCriar:
    """Converte `payloadCifrado` (STUB: JSON canonico em base64, nao AES-GCM
    real -- ver docstring do modulo) de volta em `MarcacaoCriar`."""
    bruto = _bytes_do_campo(item.payload_cifrado)
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroDeAplicacao(
            "PONTO-MARC-006", detalhe="Payload do item offline corrompido ou ilegivel."
        ) from exc
    return contrato.MarcacaoCriar.model_validate(dados)


async def _empresa_do_dispositivo(
    sessao: AsyncSession, *, tenant_id: UUID, dispositivo: Dispositivo
) -> UUID | None:
    """`dispositivos.empresa_id` quando presente; senao, a empresa do
    colaborador com vinculo ATIVO daquele dispositivo (`dispositivo_vinculos`)."""
    empresa_id_dispositivo: UUID | None = dispositivo.empresa_id
    if empresa_id_dispositivo is not None:
        return empresa_id_dispositivo
    vinculo = (
        await sessao.execute(
            sa.select(DispositivoVinculo).where(
                DispositivoVinculo.tenant_id == tenant_id,
                DispositivoVinculo.dispositivo_id == dispositivo.id,
                DispositivoVinculo.status == "ativo",
            )
        )
    ).scalar_one_or_none()
    if vinculo is None:
        return None
    from ponto_contracts import Colaborador

    colaborador = (
        await sessao.execute(
            sa.select(Colaborador).where(
                Colaborador.tenant_id == tenant_id, Colaborador.id == vinculo.colaborador_id
            )
        )
    ).scalar_one_or_none()
    return colaborador.empresa_id if colaborador is not None else None


async def _processar_item(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dispositivo: Dispositivo,
    item: contrato.ItemFilaOffline,
    ttl_horas: int,
    sujeito: Sujeito,
    ip_origem: str | None,
    agora: dt.datetime,
) -> ItemProcessado:
    contador = item.contador_monotonico if item.contador_monotonico is not None else -1

    existente = (
        await sessao.execute(
            sa.select(FilaOffline).where(
                FilaOffline.tenant_id == tenant_id,
                FilaOffline.dispositivo_id == dispositivo.id,
                FilaOffline.contador_monotonico == contador,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return ItemProcessado(
            contador_monotonico=contador,
            status="duplicado",
            marcacao_id=existente.marcacao_id,
            codigo_erro="PONTO-MARC-007",
            mensagem="Contador monotonico ja consumido por este dispositivo.",
        )

    chave_material = dispositivo.chave_publica or ""
    if not verificar_hmac_item(chave_material, item):
        sessao.add(
            FilaOffline(
                tenant_id=tenant_id,
                colaborador_id=None,
                dispositivo_id=dispositivo.id,
                payload_cifrado=_bytes_do_campo(item.payload_cifrado),
                iv=_bytes_do_campo(item.iv),
                hmac=item.hmac or "",
                contador_monotonico=contador,
                datahora_dispositivo=item.datahora_dispositivo,
                tempo_monotonico_ms=item.tempo_monotonico_ms,
                status="rejeitado",
                erro="PONTO-MARC-006",
            )
        )
        await sessao.flush()
        return ItemProcessado(
            contador_monotonico=contador,
            status="rejeitado",
            codigo_erro="PONTO-MARC-006",
            mensagem="Assinatura do item offline invalida.",
        )

    datahora_captura = item.datahora_dispositivo or agora
    atraso = agora - datahora_captura
    if atraso > dt.timedelta(hours=ttl_horas):
        sessao.add(
            FilaOffline(
                tenant_id=tenant_id,
                dispositivo_id=dispositivo.id,
                payload_cifrado=_bytes_do_campo(item.payload_cifrado),
                iv=_bytes_do_campo(item.iv),
                hmac=item.hmac or "",
                contador_monotonico=contador,
                datahora_dispositivo=item.datahora_dispositivo,
                tempo_monotonico_ms=item.tempo_monotonico_ms,
                status="expirado",
                erro="PONTO-MARC-005",
                expira_em=datahora_captura + dt.timedelta(hours=ttl_horas),
            )
        )
        await sessao.flush()
        return ItemProcessado(
            contador_monotonico=contador,
            status="expirado",
            codigo_erro="PONTO-MARC-005",
            mensagem="Item fora do prazo de sincronizacao offline.",
        )

    try:
        corpo = _decodificar_payload(item)
    except ErroDeAplicacao as exc:
        sessao.add(
            FilaOffline(
                tenant_id=tenant_id,
                dispositivo_id=dispositivo.id,
                payload_cifrado=_bytes_do_campo(item.payload_cifrado),
                iv=_bytes_do_campo(item.iv),
                hmac=item.hmac or "",
                contador_monotonico=contador,
                datahora_dispositivo=item.datahora_dispositivo,
                tempo_monotonico_ms=item.tempo_monotonico_ms,
                status="rejeitado",
                erro=exc.codigo,
            )
        )
        await sessao.flush()
        return ItemProcessado(
            contador_monotonico=contador,
            status="rejeitado",
            codigo_erro=exc.codigo,
            mensagem=exc.detalhe or "Payload invalido.",
        )

    idempotency_key_item = f"{dispositivo.id}:{item.hmac}:{contador}"
    atraso_minutos = max(0, int(atraso.total_seconds() // 60))
    try:
        resultado = await registrar_marcacao(
            sessao,
            tenant_id=tenant_id,
            corpo=corpo,
            idempotency_key=idempotency_key_item,
            sujeito=sujeito,
            ip_origem=ip_origem,
            datahora_marcacao_forcada=datahora_captura,
            coletada_offline=True,
            confianca_temporal_baixa=atraso_minutos > _LIMIAR_ATRASO_SUSPEITO_MINUTOS,
        )
    except ErroDeAplicacao as exc:
        sessao.add(
            FilaOffline(
                tenant_id=tenant_id,
                dispositivo_id=dispositivo.id,
                payload_cifrado=_bytes_do_campo(item.payload_cifrado),
                iv=_bytes_do_campo(item.iv),
                hmac=item.hmac or "",
                contador_monotonico=contador,
                datahora_dispositivo=item.datahora_dispositivo,
                tempo_monotonico_ms=item.tempo_monotonico_ms,
                status="rejeitado",
                erro=exc.codigo,
            )
        )
        await sessao.flush()
        return ItemProcessado(
            contador_monotonico=contador,
            status="rejeitado",
            codigo_erro=exc.codigo,
            mensagem=exc.detalhe or "Falha ao registrar marcacao do item offline.",
        )

    marcacao = resultado.resposta.marcacao
    if (
        marcacao is None
        or marcacao.id is None
        or marcacao.colaborador_id is None
        or marcacao.datahora_marcacao is None
        or marcacao.nsr is None
    ):
        # Nunca deveria acontecer: `registrar_marcacao` so devolve sem
        # levantar `ErroDeAplicacao` quando `persistir_marcacao` (A1) ja
        # preencheu todos estes campos. Defensivo, nao alcancavel na pratica
        # -- so aqui para estreitar os tipos (`Marcacao` gerado do OpenAPI
        # declara tudo opcional) sem `# type: ignore` espalhado.
        raise ErroDeAplicacao(
            "PONTO-INT-001", contexto_log={"item": "marcacao incompleta apos gravar"}
        )
    colaborador_id = marcacao.colaborador_id
    datahora_marcacao = marcacao.datahora_marcacao
    sessao.add(
        FilaOffline(
            tenant_id=tenant_id,
            colaborador_id=colaborador_id,
            dispositivo_id=dispositivo.id,
            payload_cifrado=_bytes_do_campo(item.payload_cifrado),
            iv=_bytes_do_campo(item.iv),
            hmac=item.hmac or "",
            contador_monotonico=contador,
            datahora_dispositivo=item.datahora_dispositivo,
            tempo_monotonico_ms=item.tempo_monotonico_ms,
            status="processado",
            processado_em=agora,
            marcacao_id=marcacao.id,
            marcacao_datahora=datahora_marcacao,
        )
    )
    await sessao.flush()

    await idempotencia.registrar_chave(
        sessao,
        tenant_id=tenant_id,
        escopo=idempotencia.ESCOPO_OFFLINE_HMAC,
        chave=idempotencia.chave_offline_hmac(dispositivo.id, item.hmac or ""),
        marcacao_id=marcacao.id,
        datahora_marcacao=datahora_marcacao,
        usuario_id=sujeito.usuario_id,
        codigo_conflito="PONTO-MARC-007",
    )

    if atraso_minutos > _LIMIAR_ATRASO_SUSPEITO_MINUTOS:
        confianca_temporal = "baixa"
    elif item.tempo_monotonico_ms is not None:
        confianca_temporal = "alta"
    else:
        confianca_temporal = "media"
    # Import tardio: fila_offline.id existe so depois do flush acima.
    fila_offline_id = (
        await sessao.execute(
            sa.select(FilaOffline.id).where(
                FilaOffline.tenant_id == tenant_id,
                FilaOffline.dispositivo_id == dispositivo.id,
                FilaOffline.contador_monotonico == contador,
            )
        )
    ).scalar_one()
    eventos_marcacao.publicar_marcacao_sincronizada_offline(
        tenant_id=tenant_id,
        marcacao_id=marcacao.id,
        fila_offline_id=fila_offline_id,
        colaborador_id=colaborador_id,
        datahora_marcacao=datahora_marcacao,
        atraso_minutos=atraso_minutos,
        dispositivo_id=dispositivo.id,
        datahora_dispositivo=item.datahora_dispositivo,
        recebido_em=agora,
        confianca_temporal=confianca_temporal,
    )

    return ItemProcessado(
        contador_monotonico=contador,
        status="processado",
        marcacao_id=marcacao.id,
        nsr=marcacao.nsr,
    )


async def sincronizar_lote(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    corpo: contrato.SincronizacaoOfflineRequisicao,
    idempotency_key: str | None,
    sujeito: Sujeito,
    ip_origem: str | None = None,
) -> contrato.SincronizacaoOfflineResposta:
    """Corpo de `sincronizarMarcacoesOffline`. Processa o lote INTEIRO de
    forma sincrona (nunca cria tarefa de worker) e devolve o desfecho de cada
    item, sem jamais abortar por causa de um item ruim."""
    if not idempotency_key:
        raise ErroDeAplicacao("PONTO-IDEM-001")
    if not await idempotencia.travar_idempotency_key(
        sessao, tenant_id=tenant_id, idempotency_key=idempotency_key
    ):
        raise ErroDeAplicacao("PONTO-IDEM-003")

    if corpo.dispositivo_id is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Campo 'dispositivoId' e obrigatorio.")

    dispositivo = (
        await sessao.execute(
            sa.select(Dispositivo).where(
                Dispositivo.tenant_id == tenant_id, Dispositivo.id == corpo.dispositivo_id
            )
        )
    ).scalar_one_or_none()
    if dispositivo is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Dispositivo nao encontrado.")

    empresa_id = await _empresa_do_dispositivo(sessao, tenant_id=tenant_id, dispositivo=dispositivo)
    ttl_horas = _TTL_PADRAO_HORAS
    if empresa_id is not None:
        canal = _CANAL_POR_TIPO_DISPOSITIVO.get(dispositivo.tipo, "mobile")
        politica = await _politica_efetiva(
            sessao,
            tenant_id=tenant_id,
            empresa_id=empresa_id,
            unidade_id=dispositivo.unidade_id,
            canal=canal,
        )
        ttl_horas = politica.ttl_offline_horas

    agora = dt.datetime.now(dt.UTC)
    resultados: list[ItemProcessado] = []
    for item in corpo.itens or []:
        try:
            async with sessao.begin_nested():
                resultado_item = await _processar_item(
                    sessao,
                    tenant_id=tenant_id,
                    dispositivo=dispositivo,
                    item=item,
                    ttl_horas=ttl_horas,
                    sujeito=sujeito,
                    ip_origem=ip_origem,
                    agora=agora,
                )
        except ErroDeAplicacao as exc:
            resultado_item = ItemProcessado(
                contador_monotonico=item.contador_monotonico or -1,
                status="rejeitado",
                codigo_erro=exc.codigo,
                mensagem=exc.detalhe or "Falha ao processar item offline.",
            )
        resultados.append(resultado_item)

    processados = sum(1 for r in resultados if r.status == "processado")
    duplicados = sum(1 for r in resultados if r.status == "duplicado")
    rejeitados = sum(1 for r in resultados if r.status == "rejeitado")
    expirados = sum(1 for r in resultados if r.status == "expirado")

    return contrato.SincronizacaoOfflineResposta(
        processados=processados,
        duplicados=duplicados,
        rejeitados=rejeitados,
        expirados=expirados,
        resultados=[
            contrato.ResultadoItemOffline(
                contadorMonotonico=r.contador_monotonico,
                status=contrato.Status61(r.status),
                marcacaoId=r.marcacao_id,
                nsr=r.nsr,
                codigoErro=r.codigo_erro,
                mensagem=r.mensagem,
            )
            for r in resultados
        ],
    )
