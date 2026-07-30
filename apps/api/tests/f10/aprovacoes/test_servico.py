"""Testes de `app.workflow.aprovacoes.servico` (T3, A1)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from uuid import UUID

import pytest
import sqlalchemy as sa
from ponto_contracts import Aprovacao, Solicitacao, Tratamento
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos as eventos_tratamento
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes import delegacoes, servico
from app.workflow.solicitacoes import eventos
from app.workflow.solicitacoes import servico as solicitacoes_servico
from tests.f10.conftest import ContextoF10


@pytest.fixture(autouse=True)
def _barramento_limpo() -> Iterator[None]:
    eventos.limpar_barramento()
    eventos_tratamento.limpar_barramento()
    yield
    eventos.limpar_barramento()
    eventos_tratamento.limpar_barramento()


async def _criar_solicitacao_ajuste_ponto(
    sessao: AsyncSession, contexto: ContextoF10
) -> Solicitacao:
    corpo = esquemas.SolicitacaoCriar.model_validate(
        {
            "tipoSolicitacaoId": str(contexto.tipo_solicitacao_id),
            "colaboradorId": str(contexto.colaborador_id),
            "dataReferencia": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "descricao": "Ajuste de ponto para teste da cadeia de aprovacao.",
        }
    )
    return await solicitacoes_servico.criar_solicitacao(
        sessao, contexto.tenant_id, corpo, usuario_id=None
    )


async def _primeira_etapa(sessao: AsyncSession, tenant_id: UUID, solicitacao_id: UUID) -> Aprovacao:
    consulta = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == tenant_id,
        Aprovacao.solicitacao_id == solicitacao_id,
        Aprovacao.etapa == 1,
    )
    resultado = (await sessao.execute(consulta)).scalars().first()
    assert resultado is not None
    return resultado


async def _ligar_usuario_a_um_gestor_imediato(
    sessao: AsyncSession, contexto: ContextoF10, *, usuario_gestor_id: UUID
) -> None:
    """Cria um `colaborador` para representar o gestor, liga
    `usuario_gestor_id` a ele (`usuarios.colaborador_id`) e grava
    `colaborador_gestores` (tipo `imediato`) apontando o colaborador da
    fixture para esse gestor -- monta o cenário mínimo que
    `app.workflow.aprovacoes.resolucao.resolver_aprovador_papel` precisa
    para pré-atribuir a etapa `gestor`."""
    gestor_colaborador_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO colaboradores (id, tenant_id, empresa_id, matricula, cpf, "
            "nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, 'Gestor de Teste', 'ativo')"
        ),
        {
            "id": gestor_colaborador_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "matricula": f"GESTOR-{uuid.uuid4().hex[:8]}",
            "cpf": f"{uuid.uuid4().int % 10**11:011d}",
        },
    )
    await sessao.execute(
        text("UPDATE usuarios SET colaborador_id = :colaborador_id WHERE id = :id"),
        {"colaborador_id": gestor_colaborador_id, "id": usuario_gestor_id},
    )
    await sessao.execute(
        text(
            "INSERT INTO colaborador_gestores "
            "(id, tenant_id, colaborador_id, gestor_colaborador_id, tipo, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :colaborador_id, :gestor_colaborador_id, 'imediato', "
            "        :vigencia_inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "gestor_colaborador_id": gestor_colaborador_id,
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )


async def test_aprovador_e_pre_atribuido_via_colaborador_gestores(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    await _ligar_usuario_a_um_gestor_imediato(
        sessao_f10, contexto_f10, usuario_gestor_id=contexto_f10.gestor_usuario_id
    )
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)
    assert etapa.aprovador_usuario_id == contexto_f10.gestor_usuario_id


async def test_decidir_por_usuario_nao_atribuido_sem_delegacao_e_recusado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    await _ligar_usuario_a_um_gestor_imediato(
        sessao_f10, contexto_f10, usuario_gestor_id=contexto_f10.gestor_usuario_id
    )
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)

    dados = esquemas.DecisaoRequisicao.model_validate(
        {"decisao": "aprovar", "comentario": "Conferido."}
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.decidir_aprovacao(
            sessao_f10,
            contexto_f10.tenant_id,
            etapa.id,
            dados,
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-PERM-002"


async def test_decisao_por_delegacao_fica_marcada_e_auditada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    await _ligar_usuario_a_um_gestor_imediato(
        sessao_f10, contexto_f10, usuario_gestor_id=contexto_f10.gestor_usuario_id
    )
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)

    agora = dt.datetime.now(tz=dt.UTC)
    delegacao_dados = esquemas.DelegacaoCriar.model_validate(
        {
            "deleganteUsuarioId": str(contexto_f10.gestor_usuario_id),
            "delegadoUsuarioId": str(contexto_f10.rh_usuario_id),
            "motivo": "Ferias do gestor.",
            "inicioEm": (agora - dt.timedelta(hours=1)).isoformat(),
            "fimEm": (agora + dt.timedelta(days=5)).isoformat(),
            "status": "ativa",
        }
    )
    delegacao = await delegacoes.criar_delegacao(
        sessao_f10,
        contexto_f10.tenant_id,
        delegacao_dados,
        usuario_id=contexto_f10.gestor_usuario_id,
    )

    dados_decisao = esquemas.DecisaoRequisicao.model_validate(
        {
            "decisao": "aprovar",
            "comentario": "Aprovado no lugar do gestor.",
            "delegacaoId": str(delegacao.id),
        }
    )
    decidida = await servico.decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        etapa.id,
        dados_decisao,
        usuario_id=contexto_f10.rh_usuario_id,
        ip="203.0.113.10",
    )
    assert decidida.decisao == "aprovada"
    assert decidida.aprovador_delegacao_id == delegacao.id

    linha_auditoria = (
        (
            await sessao_f10.execute(
                text(
                    "SELECT acao, usuario_id, delegacao_id, metadados FROM auditoria "
                    "WHERE tenant_id = :tenant_id AND entidade = 'aprovacoes' AND entidade_id = :id"
                ),
                {"tenant_id": contexto_f10.tenant_id, "id": etapa.id},
            )
        )
        .mappings()
        .first()
    )
    assert linha_auditoria is not None
    assert linha_auditoria["acao"] == "aprovar"
    assert linha_auditoria["usuario_id"] == contexto_f10.rh_usuario_id
    assert linha_auditoria["delegacao_id"] == delegacao.id
    assert linha_auditoria["metadados"]["porDelegacao"] is True


async def test_aprovar_etapa_intermediaria_avanca_sem_materializar(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa1 = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)

    dados = esquemas.DecisaoRequisicao.model_validate(
        {"decisao": "aprovar", "comentario": "Etapa 1 ok."}
    )
    await servico.decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        etapa1.id,
        dados,
        usuario_id=contexto_f10.gestor_usuario_id,
    )

    await sessao_f10.refresh(solicitacao)
    assert solicitacao.status == "em_aprovacao"
    assert solicitacao.etapa_atual == 2

    consulta_tratamentos = sa.select(Tratamento).where(
        Tratamento.tenant_id == contexto_f10.tenant_id, Tratamento.solicitacao_id == solicitacao.id
    )
    assert (await sessao_f10.execute(consulta_tratamentos)).scalars().all() == []

    consulta_etapa2 = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == contexto_f10.tenant_id,
        Aprovacao.solicitacao_id == solicitacao.id,
        Aprovacao.etapa == 2,
    )
    etapa2 = (await sessao_f10.execute(consulta_etapa2)).scalars().first()
    assert etapa2 is not None
    assert etapa2.papel == "rh"
    assert etapa2.decisao == "pendente"


async def test_aprovar_ultima_etapa_materializa_e_conclui_solicitacao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa1 = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)
    dados = esquemas.DecisaoRequisicao.model_validate(
        {"decisao": "aprovar", "comentario": "Etapa 1 ok."}
    )
    await servico.decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        etapa1.id,
        dados,
        usuario_id=contexto_f10.gestor_usuario_id,
    )

    consulta_etapa2 = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == contexto_f10.tenant_id,
        Aprovacao.solicitacao_id == solicitacao.id,
        Aprovacao.etapa == 2,
    )
    etapa2 = (await sessao_f10.execute(consulta_etapa2)).scalars().first()
    assert etapa2 is not None

    await servico.decidir_aprovacao(
        sessao_f10, contexto_f10.tenant_id, etapa2.id, dados, usuario_id=contexto_f10.rh_usuario_id
    )

    await sessao_f10.refresh(solicitacao)
    assert solicitacao.status == "aprovada"
    assert solicitacao.concluida_em is not None

    consulta_tratamentos = sa.select(Tratamento).where(
        Tratamento.tenant_id == contexto_f10.tenant_id, Tratamento.solicitacao_id == solicitacao.id
    )
    tratamentos = (await sessao_f10.execute(consulta_tratamentos)).scalars().all()
    assert len(tratamentos) == 1
    assert tratamentos[0].status in ("aprovado", "aplicado")


async def test_reprovacao_em_qualquer_etapa_nunca_materializa(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa1 = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)

    dados = esquemas.DecisaoRequisicao.model_validate(
        {"decisao": "reprovar", "comentario": "Horario nao confere com o controle de acesso."}
    )
    decidida = await servico.decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        etapa1.id,
        dados,
        usuario_id=contexto_f10.gestor_usuario_id,
    )
    assert decidida.decisao == "reprovada"

    await sessao_f10.refresh(solicitacao)
    assert solicitacao.status == "reprovada"

    consulta_tratamentos = sa.select(Tratamento).where(
        Tratamento.tenant_id == contexto_f10.tenant_id, Tratamento.solicitacao_id == solicitacao.id
    )
    tratamentos = (await sessao_f10.execute(consulta_tratamentos)).scalars().all()
    # Um Tratamento pode existir (criado+reprovado, reaproveitando o mesmo
    # caminho de publicacao de evento de F4), mas NUNCA em status que afete
    # apuracao.
    assert all(t.status not in ("aprovado", "aplicado", "pendente") for t in tratamentos)

    # A categoria `ajuste_ponto` tem `tipo_tratamento_id` configurado --
    # `ajuste.reprovado` sai pelo barramento de F4 (`decidir_tratamento`
    # publica automaticamente), nao pelo modulo proprio deste pacote (esse
    # so e usado para ferias/folga/categorias sem tratamento).
    publicados = [
        e for e in eventos_tratamento.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.reprovado"
    ]
    assert len(publicados) == 1
    # `eventos` (este pacote) só teve `ajuste.solicitado` publicado na
    # criação -- nenhum `ajuste.reprovado` próprio, já que a categoria
    # `ajuste_ponto` tem tratamento configurado.
    assert [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.reprovado"] == []

    # Nenhuma segunda etapa foi criada.
    consulta_etapa2 = sa.select(Aprovacao).where(
        Aprovacao.tenant_id == contexto_f10.tenant_id,
        Aprovacao.solicitacao_id == solicitacao.id,
        Aprovacao.etapa == 2,
    )
    assert (await sessao_f10.execute(consulta_etapa2)).scalars().first() is None


async def test_reprovacao_exige_comentario(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa1 = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)
    dados = esquemas.DecisaoRequisicao.model_validate({"decisao": "reprovar"})
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.decidir_aprovacao(
            sessao_f10,
            contexto_f10.tenant_id,
            etapa1.id,
            dados,
            usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_decidir_etapa_ja_decidida_e_recusado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)
    etapa1 = await _primeira_etapa(sessao_f10, contexto_f10.tenant_id, solicitacao.id)
    dados = esquemas.DecisaoRequisicao.model_validate({"decisao": "aprovar", "comentario": "ok"})
    await servico.decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        etapa1.id,
        dados,
        usuario_id=contexto_f10.gestor_usuario_id,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.decidir_aprovacao(
            sessao_f10,
            contexto_f10.tenant_id,
            etapa1.id,
            dados,
            usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_listar_aprovacoes_pendentes_visivel_por_papel_sem_pre_atribuicao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Sem `colaborador_gestores` configurado, a primeira etapa
    (`papel='gestor'`) fica com `aprovador_usuario_id=None` -- ainda assim
    precisa aparecer na fila de qualquer usuario cujo perfil RBAC seja
    `gestor` (ver docstring de `app.workflow.aprovacoes.servico`)."""
    solicitacao = await _criar_solicitacao_ajuste_ponto(sessao_f10, contexto_f10)

    linhas_sem_perfil, _ = await servico.listar_aprovacoes_pendentes(
        sessao_f10,
        contexto_f10.tenant_id,
        sujeito_usuario_id=contexto_f10.rh_usuario_id,
        sujeito_perfis=frozenset(),
    )
    assert solicitacao.id not in {linha.solicitacao_id for linha in linhas_sem_perfil}

    linhas_com_perfil, _ = await servico.listar_aprovacoes_pendentes(
        sessao_f10,
        contexto_f10.tenant_id,
        sujeito_usuario_id=contexto_f10.rh_usuario_id,
        sujeito_perfis=frozenset({"gestor"}),
    )
    assert solicitacao.id in {linha.solicitacao_id for linha in linhas_com_perfil}
