"""Consulta de comprovantes de registro.

Cobre as tres operacoes de leitura da tag `comprovantes`: `listarComprovantes`,
`obterComprovante` e `listarComprovantesRecentes`. Comprovante e append-only
(ver `packages/contracts/schema.sql`) e emitido na mesma transacao da
marcacao por `app/marcacao/comprovantes/emissor.py`; este modulo so le.

`Comprovante.datahoraMarcacao` (API) mapeia para a coluna
`comprovantes.marcacao_datahora` (banco) -- divergencia de nomenclatura
DELIBERADA e documentada (RFC-001 D-07, `packages/contracts/glossario.md`
secao 3.2): a conversao mecanica camelCase -> snake_case daria
`datahora_marcacao`, que e o nome da coluna em `marcacoes`, nao em
`comprovantes`. Todo `_serializar` deste modulo trata o par explicitamente.

`listarComprovantesRecentes`: o proprio colaborador sempre acessa os seus --
resolvido via `usuarios.colaborador_id` (o vinculo entre a identidade de
acesso, que e quem carrega `Sujeito.usuario_id`, e a pessoa); gestor e RH
dependem de `app.core.seguranca.exigir_alcance` pela empresa do colaborador
alvo.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Colaborador, Usuario
from ponto_contracts import Comprovante as ComprovanteOrm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_alcance
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
from app.schemas.contrato import CanalEntrega

CODIGO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"

CAMPOS_ORDENACAO_COMPROVANTES = frozenset({"emitidoEm", "nsr"})
ORDENACAO_PADRAO = "emitidoEm"

#: Janela padrao (o minimo legal da Portaria MTP 671/2021) e o teto aceito
#: pelo parametro `horas` de `listarComprovantesRecentes`.
JANELA_PADRAO_HORAS = 48
JANELA_MAXIMA_HORAS = 8760

_ATRIBUTO_ORM: dict[str, str] = {"emitidoEm": "emitido_em", "nsr": "nsr"}


def _campo_ordenacao(nome: str) -> CampoOrdenacao:
    mapa: dict[str, CampoOrdenacao] = {
        "emitidoEm": CampoOrdenacao(
            coluna=ComprovanteOrm.emitido_em, conversor=dt.datetime.fromisoformat
        ),
        "nsr": CampoOrdenacao(coluna=ComprovanteOrm.nsr, conversor=int),
    }
    return mapa[nome]


def _serializar(linha: ComprovanteOrm) -> contrato.Comprovante:
    return contrato.Comprovante(
        id=linha.id,
        tenantId=linha.tenant_id,
        marcacaoId=linha.marcacao_id,
        colaboradorId=linha.colaborador_id,
        cpf=linha.cpf,
        numero=linha.numero,
        nsr=linha.nsr,
        # RFC-001 D-07: `datahoraMarcacao` (API) <- `marcacao_datahora` (banco).
        datahoraMarcacao=linha.marcacao_datahora,
        conteudoTexto=linha.conteudo_texto,
        conteudoRef=linha.conteudo_ref,
        hashSha256=linha.hash_sha256,
        assinaturaRef=linha.assinatura_ref,
        emitidoEm=linha.emitido_em,
        disponivelAte=linha.disponivel_ate,
        canalEntrega=CanalEntrega(linha.canal_entrega),
        criadoEm=linha.criado_em,
    )


async def _montar_pagina(
    sessao: AsyncSession,
    consulta: sa.Select[tuple[ComprovanteOrm]],
    *,
    ordenacao_bruta: str | None,
    cursor: str | None,
    limite: int | None,
) -> contrato.ListaComprovante:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenacao_bruta, campos_aceitos=CAMPOS_ORDENACAO_COMPROVANTES, padrao=ORDENACAO_PADRAO
    )
    campo = _campo_ordenacao(ordenacao.campo)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=ComprovanteOrm.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    dados = [_serializar(linha) for linha in linhas]

    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        valor_ordenacao = getattr(ultima, _ATRIBUTO_ORM[ordenacao.campo])
        proximo_cursor = codificar_cursor(ordenacao, valor_ordenacao, ultima.id)

    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_normalizado
    )
    return contrato.ListaComprovante(dados=dados, paginacao=paginacao)


async def listar_comprovantes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
    colaborador_id: UUID | None = None,
    marcacao_id: UUID | None = None,
    cpf: str | None = None,
    de: dt.datetime | None = None,
    ate: dt.datetime | None = None,
) -> contrato.ListaComprovante:
    """`GET /v1/comprovantes`."""
    if de is not None and ate is not None and ate < de:
        raise ErroDeAplicacao(CODIGO_INTERVALO_INVALIDO, detalhe="ate nao pode ser anterior a de.")

    consulta = sa.select(ComprovanteOrm).where(ComprovanteOrm.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(ComprovanteOrm.colaborador_id == colaborador_id)
    if marcacao_id is not None:
        consulta = consulta.where(ComprovanteOrm.marcacao_id == marcacao_id)
    if cpf is not None:
        consulta = consulta.where(ComprovanteOrm.cpf == cpf)
    if de is not None:
        consulta = consulta.where(ComprovanteOrm.emitido_em >= de)
    if ate is not None:
        consulta = consulta.where(ComprovanteOrm.emitido_em <= ate)

    return await _montar_pagina(
        sessao, consulta, ordenacao_bruta=ordenar, cursor=cursor, limite=limite
    )


async def obter_comprovante(
    sessao: AsyncSession, *, tenant_id: UUID, comprovante_id: UUID
) -> contrato.Comprovante:
    """`GET /v1/comprovantes/{comprovanteId}`. `PONTO-REC-001` fora do tenant
    ou inexistente -- os dois casos respondem 404, por isolamento."""
    resultado = await sessao.execute(
        sa.select(ComprovanteOrm).where(
            ComprovanteOrm.tenant_id == tenant_id, ComprovanteOrm.id == comprovante_id
        )
    )
    linha = resultado.scalars().first()
    if linha is None:
        raise ErroDeAplicacao(
            CODIGO_NAO_ENCONTRADO, contexto_log={"comprovanteId": str(comprovante_id)}
        )
    return _serializar(linha)


async def _e_proprio_colaborador(
    sessao: AsyncSession, *, tenant_id: UUID, sujeito: Sujeito, colaborador_id: UUID
) -> bool:
    """Verdadeiro quando `sujeito` e a propria pessoa (`usuarios.colaborador_id`)."""
    if sujeito.usuario_id is None:
        return False
    resultado = await sessao.execute(
        sa.select(Usuario.colaborador_id).where(
            Usuario.tenant_id == tenant_id, Usuario.id == sujeito.usuario_id
        )
    )
    proprio = resultado.scalar_one_or_none()
    return proprio is not None and proprio == colaborador_id


async def _verificar_acesso_colaborador(
    sessao: AsyncSession, *, tenant_id: UUID, sujeito: Sujeito, colaborador_id: UUID
) -> None:
    """O proprio colaborador sempre acessa os seus; qualquer outro sujeito
    depende do alcance hierarquico (`PONTO-PERM-002` fora do alcance)."""
    if await _e_proprio_colaborador(
        sessao, tenant_id=tenant_id, sujeito=sujeito, colaborador_id=colaborador_id
    ):
        return
    resultado = await sessao.execute(
        sa.select(Colaborador.empresa_id).where(
            Colaborador.tenant_id == tenant_id, Colaborador.id == colaborador_id
        )
    )
    empresa_id = resultado.scalar_one_or_none()
    if empresa_id is None:
        raise ErroDeAplicacao(
            CODIGO_NAO_ENCONTRADO, contexto_log={"colaboradorId": str(colaborador_id)}
        )
    exigir_alcance(sujeito, empresa_id=empresa_id)


async def listar_comprovantes_recentes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    sujeito: Sujeito,
    colaborador_id: UUID,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
    horas: int | None = None,
) -> contrato.ListaComprovante:
    """`GET /v1/colaboradores/{colaboradorId}/comprovantes/recentes`. Janela
    padrao de 48h (minimo legal); o produto mantem acesso permanente, entao
    `horas` ate 8760 e aceito."""
    await _verificar_acesso_colaborador(
        sessao, tenant_id=tenant_id, sujeito=sujeito, colaborador_id=colaborador_id
    )
    janela_horas = horas if horas is not None else JANELA_PADRAO_HORAS
    if not (1 <= janela_horas <= JANELA_MAXIMA_HORAS):
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA,
            detalhe=f"horas deve estar entre 1 e {JANELA_MAXIMA_HORAS}.",
        )
    desde = dt.datetime.now(tz=dt.UTC) - dt.timedelta(hours=janela_horas)

    consulta = sa.select(ComprovanteOrm).where(
        ComprovanteOrm.tenant_id == tenant_id,
        ComprovanteOrm.colaborador_id == colaborador_id,
        ComprovanteOrm.emitido_em >= desde,
    )
    return await _montar_pagina(
        sessao, consulta, ordenacao_bruta=ordenar, cursor=cursor, limite=limite
    )
