"""Verificacao de continuidade do NSR e integridade da cadeia de hash (T4).

`verificar_sequencia_nsr` e o lado "verificador" do contrato descrito em
`app.marcacao.dominio.nsr`: ele reconstroi a mesma string canonica que
`persistir_marcacao` usou para gravar (via `join` com `marcacoes`, porque
`nsr_emissoes` guarda so a copia do hash, nao os campos de origem) e
recalcula `calcular_hash` para provar que o conteudo nao mudou -- alem de
varrer `nsr_emissoes` (a tabela nao particionada que impoe unicidade GLOBAL
de `(tenant_id, rep_p_id, nsr)`, ver glossario secao 3.1) em busca de lacuna
numerica.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.marcacao.dominio.nsr import calcular_hash, canonicalizar_registro


@dataclass(frozen=True, slots=True)
class ResultadoVerificacaoNsr:
    """Espelha, campo a campo (nomes em `snake_case`), o schema `VerificacaoNsr`
    do contrato -- o router monta a resposta com
    `contrato.VerificacaoNsr.model_validate(resultado, from_attributes=True)`."""

    rep_p_id: UUID
    nsr_inicial: int
    nsr_final: int
    total_esperado: int
    total_encontrado: int
    integro: bool
    lacunas: dict[str, Any] | None
    cadeia_hash_integra: bool | None
    verificado_em: dt.datetime


def _detectar_lacunas(nsr_de: int, nsr_ate: int, encontrados: list[int]) -> list[tuple[int, int]]:
    """Varre `[nsr_de, nsr_ate]` e devolve as faixas ausentes, fechadas nos
    dois lados. `encontrados` precisa vir ordenado (a consulta ja ordena por
    `nsr`); a varredura e O(faixa), o que e aceitavel ate dezenas de milhares
    de NSR por chamada (T9 verifica 10.000 de uma vez)."""
    presentes = set(encontrados)
    faixas: list[tuple[int, int]] = []
    inicio_gap: int | None = None
    for nsr in range(nsr_de, nsr_ate + 1):
        if nsr not in presentes:
            if inicio_gap is None:
                inicio_gap = nsr
        elif inicio_gap is not None:
            faixas.append((inicio_gap, nsr - 1))
            inicio_gap = None
    if inicio_gap is not None:
        faixas.append((inicio_gap, nsr_ate))
    return faixas


def _cadeia_integra(*, tenant_id: UUID, rep_p_id: UUID, linhas: Sequence[Any]) -> bool:
    """Recalcula o hash de cada linha (na ordem de `nsr`) e compara com
    `hash_registro` armazenado em `nsr_emissoes`.

    `linhas` traz, para cada NSR encontrado no intervalo, os campos de
    origem (via `join` com `marcacoes`) mais `hash_anterior`/`hash_registro`
    copiados em `nsr_emissoes`. O primeiro elemento usa o `hash_anterior`
    ARMAZENADO como semente (nao ha como recalcula-lo sem o registro
    anterior, que pode estar fora da faixa pedida); os elementos seguintes
    encadeiam a partir do hash RECALCULADO do anterior -- o que faz uma
    lacuna no meio (linha removida) invalidar a cadeia a partir dali, e nao
    so a continuidade numerica.
    """
    hash_anterior: str | None = None
    for indice, linha in enumerate(linhas):
        semente = linha.hash_anterior if indice == 0 else hash_anterior
        canonico = canonicalizar_registro(
            tenant_id=tenant_id,
            rep_p_id=rep_p_id,
            nsr=linha.nsr,
            cpf=linha.cpf,
            tipo_registro=linha.tipo_registro,
            canal=linha.canal,
            datahora_marcacao=linha.datahora_marcacao,
        )
        esperado = calcular_hash(canonico, semente)
        if esperado != linha.hash_registro:
            return False
        hash_anterior = linha.hash_registro
    return True


async def verificar_sequencia_nsr(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    rep_p_id: UUID,
    nsr_de: int | None = None,
    nsr_ate: int | None = None,
    verificar_cadeia_hash: bool = False,
) -> ResultadoVerificacaoNsr:
    """Implementa `GET /v1/marcacoes/nsr/verificar`.

    Sem `nsrDe`/`nsrAte`, a faixa e `[1, ultimo_nsr_emitido]` (o REP-P
    inteiro). `rep_p_id` que nao existe no tenant: `PONTO-REC-001`. Faixa
    invalida (`nsrAte < nsrDe` quando ambos informados explicitamente):
    `PONTO-VAL-005`.
    """
    existe_rep_p = await sessao.execute(
        text("SELECT 1 FROM rep_ps WHERE tenant_id = :t AND id = :r AND excluido_em IS NULL"),
        {"t": str(tenant_id), "r": str(rep_p_id)},
    )
    if existe_rep_p.first() is None:
        raise ErroDeAplicacao("PONTO-REC-001", contexto_log={"rep_p_id": str(rep_p_id)})

    sequencia = await sessao.execute(
        text(
            "SELECT ultimo_nsr_emitido FROM nsr_sequencias "
            "WHERE tenant_id = :t AND rep_p_id = :r"
        ),
        {"t": str(tenant_id), "r": str(rep_p_id)},
    )
    linha_sequencia = sequencia.first()
    ultimo_emitido = linha_sequencia.ultimo_nsr_emitido if linha_sequencia is not None else 0

    faixa_de = nsr_de if nsr_de is not None else 1
    faixa_ate = nsr_ate if nsr_ate is not None else ultimo_emitido

    if faixa_de < 1 or (nsr_ate is not None and faixa_ate < faixa_de):
        raise ErroDeAplicacao(
            "PONTO-VAL-005",
            detalhe="nsrAte deve ser maior ou igual a nsrDe, e nsrDe deve ser >= 1.",
        )

    agora = dt.datetime.now(tz=dt.UTC)
    total_esperado = max(0, faixa_ate - faixa_de + 1)

    if total_esperado == 0:
        return ResultadoVerificacaoNsr(
            rep_p_id=rep_p_id,
            nsr_inicial=faixa_de,
            nsr_final=faixa_ate,
            total_esperado=0,
            total_encontrado=0,
            integro=True,
            lacunas=None,
            cadeia_hash_integra=True if verificar_cadeia_hash else None,
            verificado_em=agora,
        )

    if verificar_cadeia_hash:
        resultado = await sessao.execute(
            text(
                "SELECT ne.nsr, ne.hash_anterior, ne.hash_registro, "
                "       m.cpf, m.canal, m.tipo_registro, m.datahora_marcacao "
                "FROM nsr_emissoes ne "
                "JOIN marcacoes m "
                "  ON m.id = ne.marcacao_id AND m.datahora_marcacao = ne.datahora_marcacao "
                "WHERE ne.tenant_id = :t AND ne.rep_p_id = :r "
                "  AND ne.nsr BETWEEN :de AND :ate "
                "ORDER BY ne.nsr"
            ),
            {"t": str(tenant_id), "r": str(rep_p_id), "de": faixa_de, "ate": faixa_ate},
        )
        linhas = resultado.all()
    else:
        resultado = await sessao.execute(
            text(
                "SELECT nsr FROM nsr_emissoes "
                "WHERE tenant_id = :t AND rep_p_id = :r AND nsr BETWEEN :de AND :ate "
                "ORDER BY nsr"
            ),
            {"t": str(tenant_id), "r": str(rep_p_id), "de": faixa_de, "ate": faixa_ate},
        )
        linhas = resultado.all()

    encontrados = [linha.nsr for linha in linhas]
    total_encontrado = len(encontrados)
    faixas_lacuna = _detectar_lacunas(faixa_de, faixa_ate, encontrados)
    integro = not faixas_lacuna and total_encontrado == total_esperado

    lacunas: dict[str, Any] | None = None
    if faixas_lacuna:
        lacunas = {"faixas": [{"nsrDe": inicio, "nsrAte": fim} for inicio, fim in faixas_lacuna]}

    cadeia_hash_integra: bool | None = None
    if verificar_cadeia_hash:
        cadeia_hash_integra = _cadeia_integra(tenant_id=tenant_id, rep_p_id=rep_p_id, linhas=linhas)

    return ResultadoVerificacaoNsr(
        rep_p_id=rep_p_id,
        nsr_inicial=faixa_de,
        nsr_final=faixa_ate,
        total_esperado=total_esperado,
        total_encontrado=total_encontrado,
        integro=integro,
        lacunas=lacunas,
        cadeia_hash_integra=cadeia_hash_integra,
        verificado_em=agora,
    )
