"""Direitos do titular (F14/A3, `criarSolicitacaoTitular`/`listarSolicitacoesTitular`).

Acesso, correcao, portabilidade, eliminacao, anonimizacao, revogacao de
consentimento, informacao sobre compartilhamento e oposicao (os oito valores
de `solicitacoes_titular.tipo`). O PCF desta fase pede regra real para
"acesso/correcao/portabilidade/eliminacao"; os quatro tipos restantes
tambem sao aceitos (o contrato os declara), mas ficam registrados como
`recebida` aguardando triagem humana -- corrigir o QUE, ou avaliar uma
oposicao, exige julgamento que nenhuma regra automatica deveria fingir ter.

**Eliminacao nunca apaga marcacao.** ADR-002 e a guarda legal de 5 anos
(CLT art. 74) exigem isso; `_processar_eliminacao` abaixo sempre produz um
RELATORIO do que foi feito e do que foi retido e por que -- nunca um
apagamento silencioso, e nunca finge sucesso total quando o titular tem
marcacao.

**Nota de interpretacao do contrato (nao e mudanca de contrato).**
`criarSolicitacaoTitular` declara `PONTO-LGPD-003` em `x-erros` (409) e a
descricao da operacao diz que ela e devolvida "quando o escopo pedido
alcanca dado retido por obrigacao legal". Duas leituras sao possiveis: (a)
a CRIACAO do pedido falha com 409 quando ha dado retido; ou (b) o pedido e
sempre criado (201) e o CODIGO aparece citado dentro do texto de
`resposta`, fundamentando a recusa parcial -- que e literalmente o que
`acao_sugerida` do catalogo (`errors.yaml`) instrui ("registre o
atendimento parcial, elimine o que pode, fundamente o resto"). Este modulo
implementa (b): nunca lanca 409 para uma eliminacao legitima, porque (a)
contradiria a propria PCF desta fase ("produza um relatorio... nunca um
apagamento silencioso onde a lei proibe") -- um 409 duro nao produz
relatorio nenhum, so recusa a own criacao do pedido. Registrado em
`docs/backlog.md` para o orquestrador confirmar ou corrigir esta leitura.

**Prazo de resposta.** A LGPD nao fixa um numero de dias unico e
inequivoco para todo pedido de titular (o art. 19 fala em resposta
imediata so para CONFIRMACAO de existencia de tratamento); a pratica do
mercado e a orientacao da ANPD giram em torno de 15 dias corridos. Usado
aqui como padrao (`PRAZO_RESPOSTA_DIAS`), documentado como decisao de
produto, nao citacao literal de lei.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    AcessoDadoSensivel,
    Biometria,
    Colaborador,
    Consentimento,
    Documento,
    Marcacao,
    SolicitacaoTitular,
    Vinculo,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum import armazenamento
from app.core.erros import ErroDeAplicacao
from app.lgpd.comum import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    normalizar_limite,
    traduzir_integridade,
)
from app.lgpd.consentimentos import expurgar_templates_biometricos

__all__ = [
    "CAMPOS_ORDENACAO_SOLICITACAO",
    "PRAZO_RESPOSTA_DIAS",
    "DadosSolicitacaoCriar",
    "criar_solicitacao_titular",
    "listar_solicitacoes_titular",
]

CAMPOS_ORDENACAO_SOLICITACAO = frozenset({"criadoEm", "prazoEm"})

PRAZO_RESPOSTA_DIAS: Final[int] = 15

#: Cap de seguranca na exportacao de marcacoes: um titular com anos de
#: historico nao deveria travar a requisicao HTTP nem estourar memoria.
#: `totalMarcacoes` no pacote sempre reflete a contagem REAL (nao o cap), e
#: a resposta deixa explicito quando o pacote foi truncado -- nunca finge
#: que o corte nao aconteceu.
_LIMITE_MARCACOES_EXPORTACAO: Final[int] = 5000

_TIPOS_PROCESSADOS_AUTOMATICAMENTE = frozenset(
    {"acesso", "portabilidade", "eliminacao", "anonimizacao", "revogacao_consentimento"}
)


@dataclass(frozen=True, slots=True)
class DadosSolicitacaoCriar:
    colaborador_id: UUID | None
    usuario_id: UUID | None
    requerente_nome: str
    requerente_cpf: str | None
    requerente_email: str | None
    tipo: str
    descricao: str | None
    # Quando o CHAMADOR fornece explicitamente algum destes tres, o
    # processamento automatico desta funcao e pulado -- o chamador (RH
    # registrando um atendimento ja resolvido manualmente, por exemplo por
    # carta) assume a responsabilidade pelo conteudo.
    status_informado: str | None
    resposta_informada: str | None
    resposta_ref_informada: str | None


def _gerar_protocolo() -> str:
    hoje = dt.date.today().strftime("%Y%m%d")
    sufixo = secrets.token_hex(4).upper()
    return f"LGPD-{hoje}-{sufixo}"


async def _criar_registro(
    sessao: AsyncSession, *, tenant_id: UUID, dados: DadosSolicitacaoCriar, usuario_id: UUID | None
) -> SolicitacaoTitular:
    prazo_em = dt.date.today() + dt.timedelta(days=PRAZO_RESPOSTA_DIAS)
    for _tentativa in range(3):
        solicitacao = SolicitacaoTitular(
            tenant_id=tenant_id,
            colaborador_id=dados.colaborador_id,
            usuario_id=dados.usuario_id,
            protocolo=_gerar_protocolo(),
            requerente_nome=dados.requerente_nome,
            requerente_cpf=dados.requerente_cpf,
            requerente_email=dados.requerente_email,
            tipo=dados.tipo,
            descricao=dados.descricao,
            status="recebida",
            prazo_em=prazo_em,
            criado_por=usuario_id,
        )
        sessao.add(solicitacao)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            await sessao.rollback()
            origem = str(exc.orig or exc)
            if "uq_solicitacoes_titular_protocolo" in origem:
                continue
            raise traduzir_integridade(exc) from exc
        return solicitacao
    raise ErroDeAplicacao(
        "PONTO-CONF-001", detalhe="Nao foi possivel gerar um protocolo unico. Tente novamente."
    )


async def _montar_pacote_titular(
    sessao: AsyncSession, *, tenant_id: UUID, colaborador_id: UUID
) -> dict[str, Any]:
    """Reune o dado do titular espalhado pelo sistema. NUNCA inclui o vetor
    biometrico (ADR-006 regra 5: nao sai por API nem para super admin) nem o
    conteudo binario de documento (so metadados) -- so referencias."""
    colaborador = (
        await sessao.execute(
            sa.select(Colaborador).where(
                Colaborador.id == colaborador_id, Colaborador.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()

    vinculos = (
        (
            await sessao.execute(
                sa.select(Vinculo).where(
                    Vinculo.tenant_id == tenant_id, Vinculo.colaborador_id == colaborador_id
                )
            )
        )
        .scalars()
        .all()
    )

    total_marcacoes = (
        await sessao.execute(
            sa.select(sa.func.count(Marcacao.id)).where(
                Marcacao.tenant_id == tenant_id, Marcacao.colaborador_id == colaborador_id
            )
        )
    ).scalar_one()
    marcacoes = (
        (
            await sessao.execute(
                sa.select(Marcacao)
                .where(Marcacao.tenant_id == tenant_id, Marcacao.colaborador_id == colaborador_id)
                .order_by(Marcacao.datahora_marcacao.desc())
                .limit(_LIMITE_MARCACOES_EXPORTACAO)
            )
        )
        .scalars()
        .all()
    )

    biometrias = (
        (
            await sessao.execute(
                sa.select(Biometria).where(
                    Biometria.tenant_id == tenant_id, Biometria.colaborador_id == colaborador_id
                )
            )
        )
        .scalars()
        .all()
    )

    consentimentos = (
        (
            await sessao.execute(
                sa.select(Consentimento).where(
                    Consentimento.tenant_id == tenant_id,
                    Consentimento.colaborador_id == colaborador_id,
                )
            )
        )
        .scalars()
        .all()
    )

    documentos = (
        (
            await sessao.execute(
                sa.select(Documento).where(
                    Documento.tenant_id == tenant_id,
                    Documento.colaborador_id == colaborador_id,
                    Documento.excluido_em.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    solicitacoes_anteriores = (
        (
            await sessao.execute(
                sa.select(SolicitacaoTitular).where(
                    SolicitacaoTitular.tenant_id == tenant_id,
                    SolicitacaoTitular.colaborador_id == colaborador_id,
                )
            )
        )
        .scalars()
        .all()
    )

    return {
        "geradoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        "titular": None
        if colaborador is None
        else {
            "id": str(colaborador.id),
            "matricula": colaborador.matricula,
            "nomeCompleto": colaborador.nome_completo,
            "cpf": colaborador.cpf,
            "email": colaborador.email,
            "status": colaborador.status,
            "dataAdmissao": colaborador.data_admissao,
            "dataDesligamento": colaborador.data_desligamento,
        },
        "vinculos": [
            {
                "id": str(v.id),
                "tipoVinculo": v.tipo_vinculo,
                "status": v.status,
                "dataInicio": v.data_inicio,
                "dataFim": v.data_fim,
            }
            for v in vinculos
        ],
        "marcacoes": {
            "totalReal": total_marcacoes,
            "truncado": total_marcacoes > len(marcacoes),
            "itens": [
                {
                    "id": str(m.id),
                    "nsr": m.nsr,
                    "datahoraMarcacao": m.datahora_marcacao,
                    "canal": m.canal,
                    "tipoRegistro": m.tipo_registro,
                }
                for m in marcacoes
            ],
        },
        "biometrias": [
            {
                "id": str(b.id),
                "modalidade": b.modalidade,
                "status": b.status,
                "cadastradaEm": b.cadastrada_em,
                # Deliberadamente SEM o vetor: ADR-006 regra 5.
            }
            for b in biometrias
        ],
        "consentimentos": [
            {
                "id": str(c.id),
                "finalidade": c.finalidade,
                "versaoTermo": c.versao_termo,
                "status": c.status,
                "concedidoEm": c.concedido_em,
                "revogadoEm": c.revogado_em,
            }
            for c in consentimentos
        ],
        "documentos": [
            {
                "id": str(d.id),
                "tipo": d.tipo,
                "nomeArquivo": d.nome_arquivo,
                "criadoEm": d.criado_em,
            }
            for d in documentos
        ],
        "solicitacoesAnteriores": [
            {
                "id": str(s.id),
                "protocolo": s.protocolo,
                "tipo": s.tipo,
                "status": s.status,
                "criadoEm": s.criado_em,
            }
            for s in solicitacoes_anteriores
        ],
    }


async def _processar_acesso_portabilidade(
    sessao: AsyncSession,
    solicitacao: SolicitacaoTitular,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    if solicitacao.colaborador_id is None:
        solicitacao.status = "recusada"
        solicitacao.resposta = (
            "Nao foi possivel localizar o titular: informe 'colaboradorId' para que a "
            "exportacao seja gerada."
        )
        solicitacao.respondido_em = agora
        solicitacao.respondido_por = usuario_id
        return

    pacote = await _montar_pacote_titular(
        sessao, tenant_id=tenant_id, colaborador_id=solicitacao.colaborador_id
    )
    conteudo = json.dumps(pacote, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    chave = f"lgpd/exportacoes/{tenant_id}/{solicitacao.colaborador_id}/{solicitacao.id}.json"
    await armazenamento.salvar_objeto(chave, conteudo, content_type="application/json")

    quantidade = (
        1
        + len(pacote["vinculos"])
        + pacote["marcacoes"]["totalReal"]
        + len(pacote["biometrias"])
        + len(pacote["consentimentos"])
        + len(pacote["documentos"])
    )
    sessao.add(
        AcessoDadoSensivel(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            colaborador_id=solicitacao.colaborador_id,
            categoria="dados_pessoais",
            entidade="solicitacoes_titular",
            entidade_id=solicitacao.id,
            finalidade=f"Atendimento a solicitacao de titular ({solicitacao.tipo})",
            base_legal="exercicio_direitos",
            acao="exportacao",
            quantidade_registros=quantidade,
            origem="api",
        )
    )

    solicitacao.status = "atendida"
    solicitacao.resposta_ref = chave
    truncado = (
        " (marcacoes truncadas nas mais recentes "
        f"{_LIMITE_MARCACOES_EXPORTACAO}: "
        f"total real {pacote['marcacoes']['totalReal']})"
        if pacote["marcacoes"]["truncado"]
        else ""
    )
    solicitacao.resposta = (
        "Exportacao gerada automaticamente com os dados do titular disponiveis no sistema"
        f"{truncado}. Ver pacote em 'respostaRef'."
    )
    solicitacao.respondido_em = agora
    solicitacao.respondido_por = usuario_id
    await sessao.flush()


async def _revogar_todos_consentimentos(
    sessao: AsyncSession, *, tenant_id: UUID, colaborador_id: UUID, usuario_id: UUID | None
) -> tuple[int, int]:
    """Revoga todo consentimento `concedido` do colaborador (qualquer
    finalidade) e, para os biometricos, dispara o expurgo real do template.
    Devolve (consentimentos_revogados, templates_removidos)."""
    consentimentos = (
        (
            await sessao.execute(
                sa.select(Consentimento).where(
                    Consentimento.tenant_id == tenant_id,
                    Consentimento.colaborador_id == colaborador_id,
                    Consentimento.status == "concedido",
                )
            )
        )
        .scalars()
        .all()
    )
    agora = dt.datetime.now(tz=dt.UTC)
    for consentimento in consentimentos:
        consentimento.status = "revogado"
        consentimento.revogado_em = agora
        consentimento.atualizado_por = usuario_id
    await sessao.flush()

    total_templates = 0
    for consentimento in consentimentos:
        total_templates += await expurgar_templates_biometricos(
            sessao,
            tenant_id=tenant_id,
            colaborador_id=colaborador_id,
            finalidade=consentimento.finalidade,
            usuario_id=usuario_id,
        )
    return len(consentimentos), total_templates


async def _processar_revogacao_consentimento(
    sessao: AsyncSession,
    solicitacao: SolicitacaoTitular,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    if solicitacao.colaborador_id is None:
        solicitacao.status = "recusada"
        solicitacao.resposta = "Informe 'colaboradorId' para revogar os consentimentos do titular."
        solicitacao.respondido_em = agora
        solicitacao.respondido_por = usuario_id
        return

    revogados, templates = await _revogar_todos_consentimentos(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=solicitacao.colaborador_id,
        usuario_id=usuario_id,
    )
    solicitacao.status = "atendida"
    solicitacao.resposta = (
        f"{revogados} consentimento(s) revogado(s); {templates} template(s) biometrico(s) "
        "expurgado(s) em decorrencia. O colaborador segue registrando ponto pelo fallback "
        "de matricula e PIN ou cartao."
    )
    solicitacao.respondido_em = agora
    solicitacao.respondido_por = usuario_id
    await sessao.flush()


async def _processar_eliminacao(
    sessao: AsyncSession,
    solicitacao: SolicitacaoTitular,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
) -> None:
    """Elimina o que a lei permite, retem o que ela exige, e sempre produz
    um relatorio (PCF secao 5: "nunca um apagamento silencioso"). Cobre
    tanto `tipo='eliminacao'` quanto `tipo='anonimizacao'` -- um vetor
    biometrico nao tem forma "anonimizada" parcial (ele IDENTIFICA por
    definicao), entao anonimizar biometria e, na pratica, elimina-la; a
    diferenca fica so no texto da resposta."""
    agora = dt.datetime.now(tz=dt.UTC)
    if solicitacao.colaborador_id is None:
        solicitacao.status = "recusada"
        solicitacao.resposta = "Informe 'colaboradorId' para processar o pedido de eliminacao."
        solicitacao.respondido_em = agora
        solicitacao.respondido_por = usuario_id
        return

    colaborador_id = solicitacao.colaborador_id
    acoes: list[str] = []
    retido: list[str] = []

    total_marcacoes = (
        await sessao.execute(
            sa.select(sa.func.count(Marcacao.id)).where(
                Marcacao.tenant_id == tenant_id, Marcacao.colaborador_id == colaborador_id
            )
        )
    ).scalar_one()
    if total_marcacoes:
        retido.append(
            f"{total_marcacoes} marcacao(oes) de ponto: guarda obrigatoria de 5 anos "
            "(CLT art. 74, ADR-002). Registro append-only, protegido por gatilho de banco "
            "contra UPDATE/DELETE -- nao alterado, nao apagado."
        )

    total_templates = 0
    for finalidade in ("biometria_facial", "biometria_digital"):
        total_templates += await expurgar_templates_biometricos(
            sessao,
            tenant_id=tenant_id,
            colaborador_id=colaborador_id,
            finalidade=finalidade,
            usuario_id=usuario_id,
        )
    if total_templates:
        acoes.append(f"{total_templates} template(s) biometrico(s) eliminado(s) (cifra apagada).")

    revogados, _ = await _revogar_todos_consentimentos(
        sessao, tenant_id=tenant_id, colaborador_id=colaborador_id, usuario_id=usuario_id
    )
    if revogados:
        acoes.append(f"{revogados} consentimento(s) revogado(s).")

    partes: list[str] = []
    if acoes:
        partes.append("Eliminado: " + "; ".join(acoes) + ".")
    if retido:
        partes.append("Retido por obrigacao legal (PONTO-LGPD-003): " + "; ".join(retido))
    if not acoes and not retido:
        partes.append(
            "Nenhum dado pessoal elegivel para eliminacao foi localizado para este titular."
        )

    solicitacao.status = "parcialmente_atendida" if retido else "atendida"
    solicitacao.resposta = " ".join(partes)
    solicitacao.respondido_em = agora
    solicitacao.respondido_por = usuario_id

    sessao.add(
        AcessoDadoSensivel(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            colaborador_id=colaborador_id,
            categoria="dados_pessoais",
            entidade="solicitacoes_titular",
            entidade_id=solicitacao.id,
            finalidade=f"Atendimento a solicitacao de titular ({solicitacao.tipo})",
            base_legal="exercicio_direitos",
            acao="eliminacao",
            quantidade_registros=total_templates,
            origem="api",
        )
    )
    await sessao.flush()


async def criar_solicitacao_titular(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dados: DadosSolicitacaoCriar,
    usuario_id: UUID | None,
) -> SolicitacaoTitular:
    if dados.colaborador_id is not None:
        existe = (
            await sessao.execute(
                sa.select(sa.literal(1)).where(
                    sa.exists().where(
                        Colaborador.id == dados.colaborador_id,
                        Colaborador.tenant_id == tenant_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if existe is None:
            raise ErroDeAplicacao("PONTO-REC-001", detalhe="Colaborador nao encontrado.")

    solicitacao = await _criar_registro(
        sessao, tenant_id=tenant_id, dados=dados, usuario_id=usuario_id
    )

    # Backfill manual: o chamador ja informou status/resposta -- respeita, nao
    # reprocessa (ex.: RH registrando um pedido em papel ja atendido).
    if dados.status_informado is not None:
        solicitacao.status = dados.status_informado
        if dados.resposta_informada is not None:
            solicitacao.resposta = dados.resposta_informada
        if dados.resposta_ref_informada is not None:
            solicitacao.resposta_ref = dados.resposta_ref_informada
        if dados.status_informado not in ("recebida", "em_analise"):
            solicitacao.respondido_em = dt.datetime.now(tz=dt.UTC)
            solicitacao.respondido_por = usuario_id
        await sessao.flush()
        return solicitacao

    if dados.tipo not in _TIPOS_PROCESSADOS_AUTOMATICAMENTE:
        # correcao / informacao_compartilhamento / oposicao: exigem
        # julgamento humano sobre O QUE corrigir ou avaliar. Fica
        # 'recebida', com protocolo e prazo, aguardando triagem do RH/DPO.
        return solicitacao

    if dados.tipo in ("acesso", "portabilidade"):
        await _processar_acesso_portabilidade(
            sessao, solicitacao, tenant_id=tenant_id, usuario_id=usuario_id
        )
    elif dados.tipo in ("eliminacao", "anonimizacao"):
        await _processar_eliminacao(sessao, solicitacao, tenant_id=tenant_id, usuario_id=usuario_id)
    elif dados.tipo == "revogacao_consentimento":
        await _processar_revogacao_consentimento(
            sessao, solicitacao, tenant_id=tenant_id, usuario_id=usuario_id
        )
    return solicitacao


async def listar_solicitacoes_titular(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID | None,
    tipo: str | None,
    status: str | None,
    vencendo: bool | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> tuple[list[SolicitacaoTitular], bool, str | None]:
    limite_normalizado = normalizar_limite(limite)
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=CAMPOS_ORDENACAO_SOLICITACAO, padrao="criadoEm"
    )
    mapa = {
        "criadoEm": CampoOrdenacao(SolicitacaoTitular.criado_em, lambda v: v),
        "prazoEm": CampoOrdenacao(SolicitacaoTitular.prazo_em, lambda v: v),
    }
    consulta = sa.select(SolicitacaoTitular).where(SolicitacaoTitular.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(SolicitacaoTitular.colaborador_id == colaborador_id)
    if tipo is not None:
        consulta = consulta.where(SolicitacaoTitular.tipo == tipo)
    if status is not None:
        consulta = consulta.where(SolicitacaoTitular.status == status)
    if vencendo:
        limite_vencendo = dt.date.today() + dt.timedelta(days=3)
        consulta = consulta.where(
            SolicitacaoTitular.status.in_(("recebida", "em_analise")),
            SolicitacaoTitular.prazo_em.is_not(None),
            SolicitacaoTitular.prazo_em <= limite_vencendo,
        )

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=mapa[ordenacao.campo],
        coluna_id=SolicitacaoTitular.id,
        cursor=cursor,
        limite=limite_normalizado,
    )
    proximo: str | None = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor = getattr(ultimo, "criado_em" if ordenacao.campo == "criadoEm" else "prazo_em")
        proximo = codificar_cursor(ordenacao, valor, ultimo.id)
    return list(linhas), tem_mais, proximo
