"""Registro tipo "7" do AFD — marcação de ponto do REP-P (137 caracteres,
SEM CRC-16, COM hash SHA-256 encadeado — `docs/leiaute-afd-aej.md` §7) — e a
verificação prévia de continuidade de NSR que o precede.

**Este é o registro central do REP-P** (`docs/leiaute-afd-aej.md` §7). A
fórmula do hash (campo nº 8) é melhor esforço documentado — ver
`app.fiscal.afd.hash_tipo7` e o ADR-012 antes de tocar aqui.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from ponto_contracts import Marcacao
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.fiscal.afd.hash_tipo7 import InsumosHashTipo7, calcular_hash_tipo7
from app.fiscal.afd.registros import preencher_alfanumerico, preencher_numerico
from app.fiscal.comum.formatos import formatar_data_hora
from app.marcacao.dominio.verificacao_nsr import verificar_sequencia_nsr

#: Campo nº 6 do tipo "7": identificador do coletor da marcação
#: (`docs/leiaute-afd-aej.md` §7: "01"=app mobile, "02"=browser,
#: "03"=app desktop, "04"=dispositivo eletronico, "05"=outro nao
#: especificado). Mapeamento `marcacoes.canal -> codigo` FIXADO pelo PCF
#: F12 §6/T5 (não invente outro mapeamento):
#:
#: | canal        | codigo | motivo                                        |
#: |--------------|--------|------------------------------------------------|
#: | mobile       | "01"   | app mobile                                    |
#: | web          | "02"   | browser                                       |
#: | terminal     | "04"   | dispositivo eletronico                        |
#: | totem        | "04"   | equipamento fisico fixo, mesmo motivo         |
#: | api          | "05"   | outro nao especificado                        |
#: | importacao   | nunca  | excluido da consulta (§2.8) -- nunca chega aqui|
CODIGO_COLETOR_POR_CANAL: Final[dict[str, str]] = {
    "mobile": "01",
    "web": "02",
    "terminal": "04",
    "totem": "04",
    "api": "05",
}

_TAMANHO_REGISTRO_TIPO7: Final[int] = 137


@dataclass(frozen=True, slots=True)
class RegistroTipo7:
    """Uma linha do tipo "7" já montada, mais o hash que ela produziu (para
    encadear ao próximo registro da mesma sequência)."""

    nsr: int
    linha: str
    hash_registro: str


def montar_registro_tipo7(
    *,
    nsr: int,
    cpf: str,
    datahora_marcacao: dt.datetime,
    datahora_gravacao: dt.datetime,
    canal: str,
    coletada_offline: bool,
    hash_anterior: str | None,
) -> RegistroTipo7:
    """Monta um único registro tipo "7" (137 caracteres) e calcula seu hash
    SHA-256 encadeado (ADR-012). `canal='importacao'` nunca deveria chegar
    aqui (excluído na consulta que alimenta o AFD, §2.8) — levanta
    `ValueError` em vez de silenciosamente inventar um código de coletor,
    porque um mapeamento adivinhado seria pior que um erro explícito."""
    codigo_coletor = CODIGO_COLETOR_POR_CANAL.get(canal)
    if codigo_coletor is None:
        raise ValueError(
            f"canal {canal!r} nao tem codigo de coletor mapeado para o tipo 7 do AFD "
            "(canal='importacao' deveria ter sido excluido da consulta antes de chegar aqui)."
        )
    indicador_offline = "1" if coletada_offline else "0"

    hash_registro = calcular_hash_tipo7(
        InsumosHashTipo7(
            nsr=nsr,
            tipo_registro="7",
            datahora_marcacao=datahora_marcacao,
            cpf=cpf,
            datahora_gravacao=datahora_gravacao,
            identificador_coletor=codigo_coletor,
            indicador_offline=indicador_offline,
        ),
        hash_anterior,
    )

    linha = (
        preencher_numerico(str(nsr), 9)  # 1
        + preencher_alfanumerico("7", 1)  # 2: tipo A na fonte, nao N
        + preencher_alfanumerico(formatar_data_hora(datahora_marcacao), 24)  # 3
        + preencher_numerico(cpf, 12)  # 4
        + preencher_alfanumerico(formatar_data_hora(datahora_gravacao), 24)  # 5
        + preencher_numerico(codigo_coletor, 2)  # 6
        + preencher_numerico(indicador_offline, 1)  # 7
        + preencher_alfanumerico(hash_registro, 64)  # 8
    )
    if len(linha) != _TAMANHO_REGISTRO_TIPO7:
        raise ValueError(
            f"registro tipo 7 com tamanho inesperado: {len(linha)} "
            f"(esperado {_TAMANHO_REGISTRO_TIPO7})."
        )
    return RegistroTipo7(nsr=nsr, linha=linha, hash_registro=hash_registro)


async def _hash_anterior_semente(
    sessao: AsyncSession, *, tenant_id: UUID, rep_p_id: UUID, primeiro_nsr: int
) -> str | None:
    """Recompõe o hash do ADR-012 do registro tipo "7" com
    `nsr = primeiro_nsr - 1` (o elo anterior de verdade da cadeia do REP-P),
    para semear o encadeamento quando o AFD gerado NÃO começa no NSR 1 do
    REP-P (ex.: segundo AFD gerado para o mesmo REP-P, cobrindo um período
    posterior).

    **Por que isto é necessário** (achado de correção, não um detalhe
    cosmético): o ADR-012 diz que "o primeiro registro tipo '7' da
    SEQUÊNCIA DO REP-P" — o histórico inteiro, não desta chamada — omite o
    8º insumo. Sem esta função, CADA geração de AFD trataria o primeiro
    registro do PERÍODO PEDIDO como se fosse o primeiro da vida do REP-P,
    quebrando o encadeamento sempre que `nsrInicial > 1`. Como o hash do
    ADR-012 é calculado apenas em memória durante a geração (nunca
    persistido em coluna própria — `marcacoes.hash_registro` é a cadeia
    DIFERENTE de F5, §2.5, nunca reaproveitada aqui), a única forma correta
    de recuperar o elo anterior é recalcular a cadeia inteira desde o NSR 1
    até `primeiro_nsr - 1`. Isto é O(histórico do REP-P) por geração — uma
    função determinística pura (SHA-256), então o custo é aceitável em
    tarefa de fila/background, mas cresce com o tempo de vida do REP-P; se
    isso se provar caro demais na prática, é achado de desempenho a
    registrar em `docs/backlog.md`, não motivo para pular a correção aqui.
    """
    if primeiro_nsr <= 1:
        return None

    resultado = await sessao.execute(
        select(Marcacao)
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.rep_p_id == rep_p_id,
            Marcacao.tipo_registro == "7",
            Marcacao.canal != "importacao",
            Marcacao.nsr < primeiro_nsr,
        )
        .order_by(Marcacao.nsr.asc())
    )
    anteriores = resultado.scalars().all()

    hash_anterior: str | None = None
    for marcacao in anteriores:
        hash_anterior = calcular_hash_tipo7(
            InsumosHashTipo7(
                nsr=marcacao.nsr,
                tipo_registro="7",
                datahora_marcacao=marcacao.datahora_marcacao,
                cpf=marcacao.cpf,
                datahora_gravacao=marcacao.datahora_gravacao,
                identificador_coletor=CODIGO_COLETOR_POR_CANAL.get(marcacao.canal, "05"),
                indicador_offline="1" if marcacao.coletada_offline else "0",
            ),
            hash_anterior,
        )
    return hash_anterior


async def montar_registros_tipo7(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    rep_p_id: UUID,
    marcacoes: Sequence[Marcacao],
) -> list[RegistroTipo7]:
    """Verifica a continuidade da sequência de NSR do REP-P **antes** de
    montar qualquer registro tipo "7" e, se íntegra, monta todos os
    registros de `marcacoes` (já ordenada por NSR pelo chamador, T6),
    encadeando o hash de cada um ao hash do registro tipo "7" imediatamente
    anterior — o primeiro registro da lista encadeia a partir do hash
    recomputado do NSR imediatamente anterior NO REP-P (via
    `_hash_anterior_semente`), não necessariamente `None`: só é `None` de
    verdade quando `marcacoes[0].nsr == 1` (aí sim é o primeiro registro tipo
    "7" da vida inteira do REP-P, ADR-012).

    **Verificação de continuidade é sobre a sequência INTEIRA do REP-P**
    (`verificar_sequencia_nsr` chamada sem `nsr_de`/`nsr_ate`, que usa o
    default `[1, ultimo_nsr_emitido]`), não só sobre a faixa de NSR presente
    em `marcacoes`. Decisão documentada (achado de julgamento desta fase,
    não uma leitura literal do PCF): como o NSR não é cronológico
    (ADR-003), um AFD filtrado por DATA pode legitimamente excluir NSRs
    intercalados de outros períodos (marcação offline registrada fora da
    janela pedida) — escopar a verificação de lacuna só à faixa
    min(nsr)..max(nsr) das marcações SELECIONADAS acusaria "lacuna" para
    esses NSRs legitimamente excluídos, um falso positivo. Tratar a
    integridade do NSR como invariante do REP-P inteiro (ADR-003), não
    como propriedade de um arquivo por período, evita esse falso positivo
    e é consistente com o comportamento *default* da própria função de
    verificação quando chamada sem faixa.

    `verificar_cadeia_hash=False`: só a checagem de lacuna numérica
    (`integro`/`lacunas`) interessa aqui — a cadeia de hash INTERNA de F5
    (`marcacoes.hash_anterior`/`hash_registro`) não é o leiaute (§2.5) e não
    tem relação com o hash do ADR-012.

    Não escreve nenhum byte: se `integro=False`, levanta `PONTO-FISC-001`
    ANTES de montar qualquer linha — é o teste do critério de aceite
    "lacuna de NSR é impossível de produzir" aplicado ao AFD gerado.
    """
    resultado = await verificar_sequencia_nsr(
        sessao,
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        verificar_cadeia_hash=False,
    )
    if not resultado.integro:
        raise ErroDeAplicacao(
            "PONTO-FISC-001",
            detalhe=(
                f"Lacuna de NSR detectada na sequencia do REP-P {rep_p_id} "
                f"entre {resultado.nsr_inicial} e {resultado.nsr_final}."
            ),
            contexto_log={
                "repPId": str(rep_p_id),
                "nsrInicial": resultado.nsr_inicial,
                "nsrFinal": resultado.nsr_final,
                "lacunas": resultado.lacunas,
            },
        )

    registros: list[RegistroTipo7] = []
    hash_anterior: str | None = None
    if marcacoes:
        hash_anterior = await _hash_anterior_semente(
            sessao, tenant_id=tenant_id, rep_p_id=rep_p_id, primeiro_nsr=marcacoes[0].nsr
        )
    for marcacao in marcacoes:
        registro = montar_registro_tipo7(
            nsr=marcacao.nsr,
            cpf=marcacao.cpf,
            datahora_marcacao=marcacao.datahora_marcacao,
            datahora_gravacao=marcacao.datahora_gravacao,
            canal=marcacao.canal,
            coletada_offline=marcacao.coletada_offline,
            hash_anterior=hash_anterior,
        )
        registros.append(registro)
        hash_anterior = registro.hash_registro
    return registros
