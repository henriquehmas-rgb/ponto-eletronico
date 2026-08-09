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


async def _marcacoes_da_cadeia_ate(
    sessao: AsyncSession, *, tenant_id: UUID, rep_p_id: UUID, ate_nsr: int
) -> Sequence[Marcacao]:
    """Todas as marcações tipo "7" do REP-P com `nsr <= ate_nsr`, ordenadas
    por NSR — **a cadeia de verdade do ADR-012**, não só as marcações que o
    AFD sendo gerado vai imprimir.

    Mesmos filtros da consulta que alimenta o AFD
    (`app.fiscal.afd.gerador._consultar_marcacoes_do_periodo`): só
    `tipo_registro='7'` (a cadeia do campo nº 8 é só de registros tipo "7") e
    nunca `canal='importacao'` (§2.8 — AFD de terceiro usa *namespace* de NSR
    próprio e não entra neste arquivo, portanto também não entra nesta
    cadeia). O único filtro que NÃO se aplica aqui é o de período: a cadeia
    ignora `periodoInicio`/`periodoFim` de propósito (ver
    `montar_registros_tipo7`).

    Como o hash do ADR-012 é calculado apenas em memória durante a geração
    (nunca persistido em coluna própria — `marcacoes.hash_registro` é a
    cadeia DIFERENTE de F5, §2.5, nunca reaproveitada aqui), a única forma
    correta de recuperar cada elo é recalcular a cadeia desde o NSR 1. Isto é
    O(histórico do REP-P) por geração — SHA-256 puro e determinístico, custo
    aceitável numa tarefa de fila/background, mas que cresce com o tempo de
    vida do REP-P; se isso se provar caro demais na prática, é achado de
    desempenho a registrar em `docs/backlog.md`, não motivo para voltar a
    encadear errado.
    """
    resultado = await sessao.execute(
        select(Marcacao)
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.rep_p_id == rep_p_id,
            Marcacao.tipo_registro == "7",
            Marcacao.canal != "importacao",
            Marcacao.nsr <= ate_nsr,
        )
        .order_by(Marcacao.nsr.asc())
    )
    return resultado.scalars().all()


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
    anterior **NA SEQUÊNCIA DO REP-P** — nunca ao anterior *desta lista*.

    **O elo anterior é sempre o NSR imediatamente anterior do REP-P, mesmo
    quando esse NSR não aparece neste AFD.** Só existe `hash_anterior=None`
    de verdade no NSR 1, o primeiro registro tipo "7" da vida inteira do
    REP-P (ADR-012, decisão 1). Por isso esta função varre a cadeia inteira
    (`_marcacoes_da_cadeia_ate`, do NSR 1 até o maior NSR pedido) e devolve
    apenas os registros pedidos: os elos intermediários são calculados, mas
    não impressos.

    **Por que "anterior no REP-P" e não "anterior no arquivo"** (correção do
    resíduo do ADR-012, não detalhe cosmético): o NSR não é cronológico
    (ADR-003) — uma marcação coletada *offline* recebe NSR na hora da
    GRAVAÇÃO, mas entra no AFD pela `datahora_marcacao`, que pode cair fora
    do período pedido. Um AFD filtrado por data pode então pular NSRs
    intercalados. Encadear pelo "anterior da lista" faria o MESMO NSR receber
    hashes DIFERENTES conforme o período escolhido na geração (um AFD do mês
    que pula o NSR intercalado e um AFD do ano inteiro que o contém
    divergiriam no campo nº 8 de todos os registros seguintes) — a cadeia
    deixaria de ser reproduzível e auditável, a única propriedade que ela
    existe para oferecer. A semântica "cadeia do REP-P" já era a fixada pelo
    ADR-012 e já era aplicada ao PRIMEIRO registro de cada geração; esta
    função apenas passou a aplicá-la a TODOS, em vez de misturar duas
    semânticas dentro do mesmo arquivo.

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

    if not marcacoes:
        return []

    pedidas: dict[int, Marcacao] = {marcacao.nsr: marcacao for marcacao in marcacoes}
    cadeia = await _marcacoes_da_cadeia_ate(
        sessao, tenant_id=tenant_id, rep_p_id=rep_p_id, ate_nsr=max(pedidas)
    )

    registros: list[RegistroTipo7] = []
    hash_anterior: str | None = None
    for elo in cadeia:
        # Para os NSRs pedidos usa-se o objeto que o chamador passou (mesma
        # linha do banco); para os elos apenas encadeados, a linha lida aqui.
        marcacao = pedidas.get(elo.nsr, elo)
        registro = montar_registro_tipo7(
            nsr=marcacao.nsr,
            cpf=marcacao.cpf,
            datahora_marcacao=marcacao.datahora_marcacao,
            datahora_gravacao=marcacao.datahora_gravacao,
            canal=marcacao.canal,
            coletada_offline=marcacao.coletada_offline,
            hash_anterior=hash_anterior,
        )
        hash_anterior = registro.hash_registro
        if elo.nsr in pedidas:
            registros.append(registro)

    if len(registros) != len(pedidas):
        # Só acontece se o chamador passar uma marcação que a própria cadeia
        # do REP-P não contém (outro REP-P/tenant, `tipo_registro != '7'` ou
        # `canal='importacao'`). Erro explícito em vez de gerar um AFD com
        # menos linhas do que o chamador pediu, silenciosamente.
        faltantes = sorted(set(pedidas) - {registro.nsr for registro in registros})
        raise ValueError(
            f"marcacoes com NSR {faltantes} nao pertencem a cadeia tipo 7 do REP-P "
            f"{rep_p_id} (outro REP-P/tenant, tipo_registro != '7' ou canal='importacao')."
        )
    return registros
