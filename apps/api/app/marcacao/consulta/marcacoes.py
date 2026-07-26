"""Consulta de marcacoes e do contexto antifraude.

Cobre as tres operacoes de leitura da tag `marcacoes` que sao ownership do
agente A3: `listarMarcacoes`, `obterMarcacao` e `obterMetaMarcacao`. As tres
sao somente leitura por definicao -- a tag nao declara (e nunca declarara)
`PUT`/`PATCH`/`DELETE` (ver `packages/contracts/openapi.yaml`,
`x-vedacao-legal` da tag `marcacoes`; ADR-002).

`Marcacao.comprovanteId` nao existe como coluna em `marcacoes` (e o inverso:
`comprovantes.marcacao_id` referencia a marcacao). Por isso toda leitura desta
fase resolve o id do comprovante com uma consulta separada e barata em
`comprovantes`, nunca com `relationship()` do ORM (os models do contrato nao
declaram relacionamento algum -- ver `packages/contracts/models/marcacao.py`).

`incluirMeta=true` em `listarMarcacoes` exige de verdade a permissao sensivel
`marcacoes.ler_sensivel` (chamando o mesmo verificador de
`app.core.seguranca.exigir_permissao` que `obterMetaMarcacao` usa, o que
tambem registra o acesso sensivel via LGPD). **RFC-011** decidiu que o
resultado nao fica embutido em cada `Marcacao` (que continua estavel em todo
consumidor, inclusive dentro de `MarcacaoCriada`): fica em `ListaMarcacao.metas`,
um mapa `marcacaoId -> MarcacaoMeta` irmao de `dados`, presente so quando
`incluirMeta=true` e a permissao esta presente.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Marcacao as MarcacaoOrm
from ponto_contracts import MarcacaoMeta as MarcacaoMetaOrm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_permissao
from app.marcacao.consulta.paginacao import (
    CODIGO_CONSULTA_INVALIDA,
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato
from app.schemas.contrato import (
    AttestationVeredito,
    Canal2,
    ClassificacaoConfianca,
    LivenessMetodo,
    RevisaoStatus,
    SentidoInformado,
    TipoRegistro,
)

CODIGO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"

PERMISSAO_LER_SENSIVEL = "marcacoes.ler_sensivel"

CAMPOS_ORDENACAO_MARCACOES = frozenset({"nsr", "datahoraMarcacao", "datahoraGravacao"})
ORDENACAO_PADRAO = "datahoraMarcacao"

CANAIS_VALIDOS = frozenset({"terminal", "mobile", "web", "totem", "api", "importacao"})

#: Atributo Python (ORM) por nome de campo aceito em `ordenar`. Usado para ler
#: o valor da ultima linha da pagina na hora de codificar o proximo cursor.
_ATRIBUTO_ORM: dict[str, str] = {
    "nsr": "nsr",
    "datahoraMarcacao": "datahora_marcacao",
    "datahoraGravacao": "datahora_gravacao",
}


def _campo_ordenacao(nome: str) -> CampoOrdenacao:
    mapa: dict[str, CampoOrdenacao] = {
        "nsr": CampoOrdenacao(coluna=MarcacaoOrm.nsr, conversor=int),
        "datahoraMarcacao": CampoOrdenacao(
            coluna=MarcacaoOrm.datahora_marcacao, conversor=dt.datetime.fromisoformat
        ),
        "datahoraGravacao": CampoOrdenacao(
            coluna=MarcacaoOrm.datahora_gravacao, conversor=dt.datetime.fromisoformat
        ),
    }
    return mapa[nome]


async def _mapa_comprovante_por_marcacao(
    sessao: AsyncSession, tenant_id: UUID, marcacao_ids: Sequence[UUID]
) -> dict[UUID, UUID]:
    """`{marcacaoId: comprovanteId}` para as marcacoes pedidas, numa unica
    consulta -- nunca uma consulta por linha (ver docstring do modulo)."""
    if not marcacao_ids:
        return {}
    # Import tardio: evita ciclo entre os dois modulos de consulta da fase.
    from ponto_contracts import Comprovante as ComprovanteOrm

    resultado = await sessao.execute(
        sa.select(ComprovanteOrm.marcacao_id, ComprovanteOrm.id).where(
            ComprovanteOrm.tenant_id == tenant_id,
            ComprovanteOrm.marcacao_id.in_(marcacao_ids),
        )
    )
    return dict(resultado.tuples().all())


async def _mapa_meta_por_marcacao(
    sessao: AsyncSession, tenant_id: UUID, marcacao_ids: Sequence[UUID]
) -> dict[UUID, contrato.MarcacaoMeta]:
    """`{marcacaoId: MarcacaoMeta}` para as marcacoes pedidas, numa unica
    consulta -- RFC-011 (`ListaMarcacao.metas`), nunca uma consulta por linha."""
    if not marcacao_ids:
        return {}
    resultado = await sessao.execute(
        sa.select(MarcacaoMetaOrm).where(
            MarcacaoMetaOrm.tenant_id == tenant_id,
            MarcacaoMetaOrm.marcacao_id.in_(marcacao_ids),
        )
    )
    return {linha.marcacao_id: _serializar_meta(linha) for linha in resultado.scalars()}


def _serializar_marcacao(linha: MarcacaoOrm, *, comprovante_id: UUID | None) -> contrato.Marcacao:
    return contrato.Marcacao(
        id=linha.id,
        tenantId=linha.tenant_id,
        repPId=linha.rep_p_id,
        empresaId=linha.empresa_id,
        unidadeId=linha.unidade_id,
        colaboradorId=linha.colaborador_id,
        vinculoId=linha.vinculo_id,
        nsr=linha.nsr,
        tipoRegistro=TipoRegistro(linha.tipo_registro),
        sentidoInformado=SentidoInformado(linha.sentido_informado)
        if linha.sentido_informado is not None
        else None,
        cpf=linha.cpf,
        pisNit=linha.pis_nit,
        datahoraMarcacao=linha.datahora_marcacao,
        datahoraGravacao=linha.datahora_gravacao,
        datahoraDispositivo=linha.datahora_dispositivo,
        fusoHorario=linha.fuso_horario,
        canal=Canal2(linha.canal),
        dispositivoId=linha.dispositivo_id,
        terminalId=linha.terminal_id,
        externalId=linha.external_id,
        logExternoId=linha.log_externo_id,
        crc16=linha.crc16,
        hashAnterior=linha.hash_anterior,
        hashRegistro=linha.hash_registro,
        linhaAfd=linha.linha_afd,
        coletadaOffline=linha.coletada_offline,
        comprovanteId=comprovante_id,
        criadoEm=linha.criado_em,
        criadoPor=linha.criado_por,
    )


def _para_float(valor: decimal.Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _serializar_meta(linha: MarcacaoMetaOrm) -> contrato.MarcacaoMeta:
    return contrato.MarcacaoMeta(
        id=linha.id,
        tenantId=linha.tenant_id,
        marcacaoId=linha.marcacao_id,
        latitude=_para_float(linha.latitude),
        longitude=_para_float(linha.longitude),
        precisaoMetros=_para_float(linha.precisao_metros),
        altitude=_para_float(linha.altitude),
        enderecoAproximado=linha.endereco_aproximado,
        unidadeGeocercaId=linha.unidade_geocerca_id,
        dentroGeocerca=linha.dentro_geocerca,
        distanciaGeocercaMetros=_para_float(linha.distancia_geocerca_metros),
        fotoRef=linha.foto_ref,
        scoreFacial=_para_float(linha.score_facial),
        limiarFacial=_para_float(linha.limiar_facial),
        versaoModeloFacial=linha.versao_modelo_facial,
        livenessAprovado=linha.liveness_aprovado,
        livenessMetodo=LivenessMetodo(linha.liveness_metodo)
        if linha.liveness_metodo is not None
        else None,
        scoreConfianca=linha.score_confianca,
        classificacaoConfianca=ClassificacaoConfianca(linha.classificacao_confianca)
        if linha.classificacao_confianca is not None
        else None,
        flagsIntegridade=linha.flags_integridade,
        attestationVeredito=AttestationVeredito(linha.attestation_veredito)
        if linha.attestation_veredito is not None
        else None,
        rootDetectado=linha.root_detectado,
        emuladorDetectado=linha.emulador_detectado,
        modoDesenvolvedor=linha.modo_desenvolvedor,
        mockLocation=linha.mock_location,
        cameraVirtual=linha.camera_virtual,
        velocidadeDesdeUltimaKmh=_para_float(linha.velocidade_desde_ultima_kmh),
        wifiBssid=linha.wifi_bssid,
        ip=str(linha.ip) if linha.ip is not None else None,
        asn=linha.asn,
        pais=linha.pais,
        revisaoStatus=RevisaoStatus(linha.revisao_status),
        revisadoPor=linha.revisado_por,
        revisadoEm=linha.revisado_em,
        revisaoObservacao=linha.revisao_observacao,
        criadoEm=linha.criado_em,
        criadoPor=linha.criado_por,
        atualizadoEm=linha.atualizado_em,
        atualizadoPor=linha.atualizado_por,
    )


async def listar_marcacoes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    sujeito: Sujeito,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    rep_p_id: UUID | None = None,
    cpf: str | None = None,
    canal: str | None = None,
    de: dt.datetime | None = None,
    ate: dt.datetime | None = None,
    nsr_de: int | None = None,
    nsr_ate: int | None = None,
    coletada_offline: bool | None = None,
    incluir_meta: bool | None = None,
) -> contrato.ListaMarcacao:
    """`GET /v1/marcacoes`. Ver docstring do modulo sobre `incluirMeta`."""
    if incluir_meta:
        await exigir_permissao(PERMISSAO_LER_SENSIVEL)(sujeito)
    if canal is not None and canal not in CANAIS_VALIDOS:
        raise ErroDeAplicacao(CODIGO_CONSULTA_INVALIDA, detalhe=f"canal invalido: {canal!r}.")
    if de is not None and ate is not None and ate < de:
        raise ErroDeAplicacao(CODIGO_INTERVALO_INVALIDO, detalhe="ate nao pode ser anterior a de.")

    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_MARCACOES, padrao=ORDENACAO_PADRAO
    )
    campo = _campo_ordenacao(ordenacao.campo)

    consulta = sa.select(MarcacaoOrm).where(MarcacaoOrm.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(MarcacaoOrm.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(MarcacaoOrm.vinculo_id == vinculo_id)
    if empresa_id is not None:
        consulta = consulta.where(MarcacaoOrm.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(MarcacaoOrm.unidade_id == unidade_id)
    if rep_p_id is not None:
        consulta = consulta.where(MarcacaoOrm.rep_p_id == rep_p_id)
    if cpf is not None:
        consulta = consulta.where(MarcacaoOrm.cpf == cpf)
    if canal is not None:
        consulta = consulta.where(MarcacaoOrm.canal == canal)
    if de is not None:
        consulta = consulta.where(MarcacaoOrm.datahora_marcacao >= de)
    if ate is not None:
        consulta = consulta.where(MarcacaoOrm.datahora_marcacao <= ate)
    if nsr_de is not None:
        consulta = consulta.where(MarcacaoOrm.nsr >= nsr_de)
    if nsr_ate is not None:
        consulta = consulta.where(MarcacaoOrm.nsr <= nsr_ate)
    if coletada_offline is not None:
        consulta = consulta.where(MarcacaoOrm.coletada_offline == coletada_offline)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=MarcacaoOrm.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    mapa_comprovantes = await _mapa_comprovante_por_marcacao(
        sessao, tenant_id, [linha.id for linha in linhas]
    )
    dados = [
        _serializar_marcacao(linha, comprovante_id=mapa_comprovantes.get(linha.id))
        for linha in linhas
    ]

    metas: dict[str, contrato.MarcacaoMeta] | None = None
    if incluir_meta:
        mapa_metas = await _mapa_meta_por_marcacao(
            sessao, tenant_id, [linha.id for linha in linhas]
        )
        metas = {str(marcacao_id): meta for marcacao_id, meta in mapa_metas.items()}

    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        valor_ordenacao = getattr(ultima, _ATRIBUTO_ORM[ordenacao.campo])
        proximo_cursor = codificar_cursor(ordenacao, valor_ordenacao, ultima.id)

    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_normalizado
    )
    return contrato.ListaMarcacao(dados=dados, paginacao=paginacao, metas=metas)


async def obter_marcacao(
    sessao: AsyncSession, *, tenant_id: UUID, marcacao_id: UUID
) -> contrato.Marcacao:
    """`GET /v1/marcacoes/{marcacaoId}`. `PONTO-REC-001` fora do tenant ou
    inexistente -- os dois casos respondem 404, por isolamento (ver
    `packages/contracts/errors.yaml`, `PONTO-REC-001`)."""
    resultado = await sessao.execute(
        sa.select(MarcacaoOrm).where(
            MarcacaoOrm.tenant_id == tenant_id, MarcacaoOrm.id == marcacao_id
        )
    )
    linha = resultado.scalars().first()
    if linha is None:
        raise ErroDeAplicacao(CODIGO_NAO_ENCONTRADO, contexto_log={"marcacaoId": str(marcacao_id)})
    mapa = await _mapa_comprovante_por_marcacao(sessao, tenant_id, [linha.id])
    return _serializar_marcacao(linha, comprovante_id=mapa.get(linha.id))


async def obter_meta_marcacao(
    sessao: AsyncSession, *, tenant_id: UUID, marcacao_id: UUID
) -> contrato.MarcacaoMeta:
    """`GET /v1/marcacoes/{marcacaoId}/meta`. A permissao `marcacoes.ler_sensivel`
    ja e verificada pela rota via `Depends(exigir_permissao(...))`; aqui so
    resolve o dado."""
    resultado = await sessao.execute(
        sa.select(MarcacaoMetaOrm).where(
            MarcacaoMetaOrm.tenant_id == tenant_id, MarcacaoMetaOrm.marcacao_id == marcacao_id
        )
    )
    linha = resultado.scalars().first()
    if linha is None:
        raise ErroDeAplicacao(CODIGO_NAO_ENCONTRADO, contexto_log={"marcacaoId": str(marcacao_id)})
    return _serializar_meta(linha)
