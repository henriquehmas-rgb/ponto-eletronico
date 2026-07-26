"""Persistencia atomica da marcacao (T3): aloca NSR, calcula CRC-16 e hash
encadeado, grava `marcacoes` + `nsr_emissoes` e fecha a cadeia -- tudo na
MESMA transacao (ADR-002, ADR-003).

Este modulo NAO resolve regra de negocio de ingestao (identificacao do
colaborador, politica de registro, geocerca, allowlist, score de confianca):
isso e do pipeline canal-agnostico (`app.marcacao.pipeline`, agente A2, T6).
`persistir_marcacao` recebe os campos ja resolvidos em `DadosMarcacao` e so
garante as tres propriedades legais inegociaveis: sequencia sem lacuna,
CRC-16 congelado e cadeia de hash. `rep_p_ativo` tambem mora aqui porque e
consulta pura sobre o mesmo REP-P que este modulo sequencia -- quem chama
(o pipeline de ingestao) decide o erro `PONTO-MARC-010` quando o resultado
e `None`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from ponto_contracts import Marcacao, NsrEmissao, RepP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marcacao.dominio.nsr import (
    alocar_nsr,
    calcular_hash,
    canonicalizar_registro,
    crc16,
    fechar_nsr,
)


@dataclass(frozen=True, slots=True)
class DadosMarcacao:
    """Campos ja resolvidos para gravar uma marcacao.

    Quem monta este objeto (o pipeline de ingestao, T6) ja fez toda a
    resolucao de negocio -- colaborador, REP-P ativo, vinculo, politica,
    geocerca, allowlist, reautenticacao, score. Este modulo so grava.
    `datahora_marcacao` e sempre o momento do FATO: o relogio do servidor no
    caminho online, ou o instante da captura preservado no caminho offline
    (T7) -- nunca o momento em que este modulo roda.
    """

    rep_p_id: UUID
    empresa_id: UUID
    cpf: str
    canal: str
    datahora_marcacao: dt.datetime
    unidade_id: UUID | None = None
    colaborador_id: UUID | None = None
    vinculo_id: UUID | None = None
    tipo_registro: str = "7"
    sentido_informado: str | None = None
    pis_nit: str | None = None
    datahora_dispositivo: dt.datetime | None = None
    fuso_horario: str = "America/Sao_Paulo"
    dispositivo_id: UUID | None = None
    terminal_id: UUID | None = None
    external_id: str | None = None
    log_externo_id: int | None = None
    idempotency_key: str | None = None
    coletada_offline: bool = False
    criado_por: UUID | None = None


async def rep_p_ativo(sessao: AsyncSession, tenant_id: UUID, empresa_id: UUID) -> RepP | None:
    """REP-P com `status='ativo'` da empresa, ou `None` quando nao existe.

    Sem REP-P ativo nao ha sequencia de NSR nem cabecalho de AFD para a
    empresa: quem chama responde `PONTO-MARC-010` (este modulo so consulta,
    nunca levanta o erro sozinho, porque `verificarSequenciaNsr` (T4) tambem
    usa esta funcao para validar `repPId` sem forcar o erro de ingestao).
    """
    resultado = await sessao.execute(
        select(RepP)
        .where(
            RepP.tenant_id == tenant_id,
            RepP.empresa_id == empresa_id,
            RepP.status == "ativo",
            RepP.excluido_em.is_(None),
        )
        .order_by(RepP.criado_em)
        .limit(1)
    )
    return resultado.scalars().first()


def montar_linha_afd(*, nsr: int, dados: DadosMarcacao) -> str:
    """Linha simplificada e deterministica -- NAO o leiaute legal final do
    AFD (Portaria MTP 671/2021, anexo do REP-P), que e implementado pela
    F12. A exigencia aqui e "a mesma entrada sempre produz a mesma linha",
    nao conformidade certificada com o layout posicional oficial.

    Campos fixos separados por um unico espaco: tipo de registro, NSR com 9
    digitos, CPF, data (AAAAMMDD), hora (HHMMSS) em UTC, canal. Nenhum campo
    aqui contem espaco, entao o separador nao e ambiguo.
    """
    instante = dados.datahora_marcacao.astimezone(dt.UTC)
    return (
        f"{dados.tipo_registro} {nsr:09d} {dados.cpf} "
        f"{instante:%Y%m%d} {instante:%H%M%S} {dados.canal}"
    )


async def persistir_marcacao(
    sessao: AsyncSession, *, tenant_id: UUID, dados: DadosMarcacao
) -> Marcacao:
    """Grava a marcacao. Tudo dentro da transacao corrente (o chamador
    commita -- normalmente `app.db.sessao.obter_sessao`, uma transacao por
    requisicao):

    1. aloca o NSR (`alocar_nsr`, ADR-003);
    2. monta `linha_afd` (determinismo, nao leiaute legal) e calcula o
       CRC-16 sobre ela;
    3. canonicaliza os campos legais (`canonicalizar_registro`) e calcula o
       hash encadeado (`calcular_hash`) a partir do `hash_anterior` que a
       alocacao devolveu;
    4. insere em `marcacoes`;
    5. insere em `nsr_emissoes` com o MESMO NSR e hash (unicidade global,
       porque `marcacoes` particionada so pode garantir unicidade dentro do
       mes -- ver `packages/contracts/glossario.md`, secao 3.1);
    6. fecha a cadeia em `nsr_sequencias.ultimo_hash` (`fechar_nsr`), para a
       PROXIMA alocacao do mesmo REP-P (nesta transacao ou em outra) ler
       este hash como `hash_anterior`.

    Nao valida `dados.rep_p_id`: o contrato desta funcao e recebe-lo ja
    confirmado ativo por `rep_p_ativo` (quem chama responde
    `PONTO-MARC-010` antes de chegar aqui). Sem REP-P valido a alocacao de
    NSR falharia com `PONTO-MARC-008` (nenhuma linha em `nsr_sequencias`
    para o `rep_p_id` informado) ou a FK de `marcacoes` recusaria o insert.
    """
    alocado = await alocar_nsr(sessao, tenant_id=tenant_id, rep_p_id=dados.rep_p_id)

    linha_afd = montar_linha_afd(nsr=alocado.nsr, dados=dados)
    crc = crc16(linha_afd.encode("utf-8"))

    dados_canonicos = canonicalizar_registro(
        tenant_id=tenant_id,
        rep_p_id=dados.rep_p_id,
        nsr=alocado.nsr,
        cpf=dados.cpf,
        tipo_registro=dados.tipo_registro,
        canal=dados.canal,
        datahora_marcacao=dados.datahora_marcacao,
    )
    hash_registro = calcular_hash(dados_canonicos, alocado.hash_anterior)

    marcacao = Marcacao(
        tenant_id=tenant_id,
        rep_p_id=dados.rep_p_id,
        empresa_id=dados.empresa_id,
        unidade_id=dados.unidade_id,
        colaborador_id=dados.colaborador_id,
        vinculo_id=dados.vinculo_id,
        nsr=alocado.nsr,
        tipo_registro=dados.tipo_registro,
        sentido_informado=dados.sentido_informado,
        cpf=dados.cpf,
        pis_nit=dados.pis_nit,
        datahora_marcacao=dados.datahora_marcacao,
        datahora_dispositivo=dados.datahora_dispositivo,
        fuso_horario=dados.fuso_horario,
        canal=dados.canal,
        dispositivo_id=dados.dispositivo_id,
        terminal_id=dados.terminal_id,
        external_id=dados.external_id,
        log_externo_id=dados.log_externo_id,
        idempotency_key=dados.idempotency_key,
        crc16=crc,
        hash_anterior=alocado.hash_anterior,
        hash_registro=hash_registro,
        linha_afd=linha_afd,
        coletada_offline=dados.coletada_offline,
        criado_por=dados.criado_por,
    )
    sessao.add(marcacao)
    await sessao.flush()

    nsr_emissao = NsrEmissao(
        tenant_id=tenant_id,
        rep_p_id=dados.rep_p_id,
        nsr=alocado.nsr,
        marcacao_id=marcacao.id,
        datahora_marcacao=marcacao.datahora_marcacao,
        hash_registro=hash_registro,
        hash_anterior=alocado.hash_anterior,
    )
    sessao.add(nsr_emissao)
    await sessao.flush()

    await fechar_nsr(
        sessao, tenant_id=tenant_id, rep_p_id=dados.rep_p_id, hash_registro=hash_registro
    )

    return marcacao
