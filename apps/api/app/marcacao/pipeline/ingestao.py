"""Pipeline canal-agnostico de `criarMarcacao` (F5, T6).

`registrar_marcacao` e o corpo inteiro da unica porta de entrada do registro
de ponto: terminal, app, navegador, totem e API chamam exatamente esta
funcao (via `POST /v1/marcacoes`), com o mesmo corpo (`MarcacaoCriar`). A F6
(Control iD), rodando em paralelo, nao escreve em nenhuma tabela desta fase:
ela converte `access_log` em `MarcacaoCriar` e chama a rota HTTP como
qualquer outro cliente.

Ordem de execucao (cada passo pode levantar o `ErroDeAplicacao` do catalogo
indicado; nenhum passo tem efeito colateral no banco antes do commit da
transacao inteira, que e responsabilidade de `app.db.sessao.obter_sessao`):

1.  `Idempotency-Key` ausente -> `PONTO-IDEM-001`.
2.  Lock consultivo da chave (`idempotencia.travar_idempotency_key`) -- outra
    requisicao com a MESMA chave em voo -> `PONTO-IDEM-003`.
3.  Resolve o colaborador (`colaboradorId`/`cpf`/`matricula`) e a empresa.
4.  Calcula o hash de identidade do pedido (`idempotencia.calcular_hash_identidade`)
    e verifica o escopo `idempotency_key`: chave ja usada com o MESMO hash ->
    devolve a marcacao original (`duplicada=true`, replay puro, nenhuma
    escrita nova); chave ja usada com hash DIFERENTE -> `PONTO-IDEM-002`.
5.  So entao verifica os escopos de dominio (`external_id` no canal `api`,
    `dispositivo_log` no canal `terminal`) -- colisao aqui e com uma
    `Idempotency-Key` DIFERENTE da atual (a mesma ja teria retornado no passo
    4), portanto e duplicata de verdade: `PONTO-MARC-003`.
6.  Vinculo ativo (`apuraPonto=true`) na data -> sem ele, `PONTO-MARC-009`.
7.  REP-P ativo da empresa (`app.marcacao.dominio.registro.rep_p_ativo`) ->
    sem ele, `PONTO-MARC-010`.
8.  Carimba `datahora_marcacao` do relogio do SERVIDOR (nunca do corpo),
    exceto quando o chamador (fluxo offline, T7) ja fornece o instante da
    captura preservado.
9.  Le `politicas_registro` (a linha mais especifica que casar com
    `(empresa, unidade, canal)`, com `DEFAULT` de coluna na ausencia de
    qualquer linha).
10. Geocerca (`app.organizacao.geocerca.dentro_da_geocerca`, F2) quando
    `exigeGeocerca` e latitude/longitude informados.
11. Allowlist CIDR (`app.organizacao.redes.ip_autorizado`, F2) quando
    `exigeRedePermitida`.
12. Vinculo do dispositivo pessoal (`dispositivo_vinculos.status='ativo'`),
    so para `canal='mobile'`.
13. Reautenticacao recente (`sessoes.reautenticado_em`), so para
    `canal='web'` e `exigeReautenticacao`.
14. Score de confianca (`app.marcacao.confianca.motor.avaliar_confianca`,
    stub permissivo de A3 nesta fase).
15. `app.marcacao.dominio.registro.persistir_marcacao` (A1): NSR, CRC-16,
    hash encadeado, `marcacoes` + `nsr_emissoes`.
16. `marcacoes_meta`, registro das chaves de idempotencia, comprovante
    (`app.marcacao.comprovantes.emissor.emitir_comprovante`, A3) e os eventos
    `marcacao.criada` / `marcacao.suspeita` / `comprovante.emitido`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import (
    Colaborador,
    Comprovante,
    Dispositivo,
    DispositivoVinculo,
    Marcacao,
    MarcacaoMeta,
    PoliticaRegistro,
    RedePermitida,
    Sessao,
    Unidade,
    Vinculo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.confianca.motor import ResultadoConfianca, SinaisRegistro, avaliar_confianca
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao, rep_p_ativo
from app.marcacao.pipeline import eventos_marcacao, idempotencia
from app.organizacao.geocerca import GeocercaUnidade, dentro_da_geocerca
from app.organizacao.redes import FaixaPermitida, ip_autorizado
from app.schemas import contrato

#: Canais que exigem o vinculo ativo de `dispositivo_vinculos`. Um terminal ou
#: totem e um coletor institucional, nao um aparelho pessoal do colaborador
#: -- por isso a checagem so vale para `mobile` (T6, PCF secao 2).
CANAIS_COM_VINCULO_DE_DISPOSITIVO = ("mobile",)

#: Janela de "reautenticacao recente" para `sessoes.reautenticado_em`. O
#: contrato exige o comportamento (PONTO-AUTH-011) mas nao fixa um numero;
#: 15 minutos e o mesmo valor pratico usado por passos de step-up auth
#: equivalentes (ex.: confirmacao de pagamento) na industria. Se um dia
#: precisar ser configuravel por tenant, e achado de backlog (a tabela
#: `politicas_registro` seria o lugar natural), nao invencao silenciosa aqui.
JANELA_REAUTENTICACAO = dt.timedelta(minutes=15)

#: `DEFAULT` de cada coluna de `politicas_registro` (schema.sql, secao 8),
#: aplicado quando NENHUMA linha casa com `(tenant_id, empresa_id, unidade_id,
#: canal)` -- nunca inventado, copiado literalmente da definicao da coluna.
_POLITICA_PADRAO: dict[str, Any] = {
    "exige_geocerca": True,
    "exige_facial": True,
    "exige_liveness": True,
    "exige_attestation": True,
    "exige_rede_permitida": False,
    "limiar_facial": 75,
    "limiar_bloqueio": 40,
    "limiar_revisao": 70,
    "politica_modo_desenvolvedor": "bloquear",
    "politica_root": "bloquear",
    "politica_mock_location": "bloquear",
    "politica_fora_geocerca": "sinalizar",
    "bloquear_vpn_proxy": False,
    "exige_reautenticacao": True,
    "ttl_offline_horas": 72,
}


@dataclass(frozen=True, slots=True)
class _PoliticaEfetiva:
    """`PoliticaRegistro` ja resolvida -- linha do banco ou `_POLITICA_PADRAO`."""

    exige_geocerca: bool
    exige_rede_permitida: bool
    limiar_bloqueio: int
    limiar_revisao: int
    politica_fora_geocerca: str
    exige_reautenticacao: bool
    ttl_offline_horas: int


@dataclass(frozen=True, slots=True)
class ResultadoRegistro:
    """Saida de `registrar_marcacao`: o corpo de `MarcacaoCriada` ja pronto e
    se a resposta e um replay puro de idempotencia (o chamador HTTP usa isto
    para decidir o cabecalho `Idempotency-Replayed`)."""

    resposta: contrato.MarcacaoCriada
    replay: bool


async def _politica_efetiva(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    unidade_id: UUID | None,
    canal: str,
) -> _PoliticaEfetiva:
    """A linha mais especifica de `politicas_registro` que casar com
    `(tenant_id, empresa_id, unidade_id, canal)` -- a `UNIQUE` da tabela usa
    `COALESCE` para tratar `unidade_id`/`canal` nulos como coringa, entao a
    consulta aceita a linha exata OU a coringa e prefere a mais especifica
    (`ORDER BY ... IS NULL` deixa os valores nao nulos primeiro). Nenhuma
    linha casando: aplica `_POLITICA_PADRAO`, os mesmos `DEFAULT` que a
    coluna ja tem no `schema.sql`."""
    consulta = (
        sa.select(PoliticaRegistro)
        .where(
            PoliticaRegistro.tenant_id == tenant_id,
            PoliticaRegistro.empresa_id == empresa_id,
            PoliticaRegistro.ativo.is_(True),
            sa.or_(
                PoliticaRegistro.unidade_id.is_(None), PoliticaRegistro.unidade_id == unidade_id
            ),
            sa.or_(PoliticaRegistro.canal.is_(None), PoliticaRegistro.canal == canal),
        )
        .order_by(
            PoliticaRegistro.unidade_id.is_(None).asc(),
            PoliticaRegistro.canal.is_(None).asc(),
        )
        .limit(1)
    )
    linha = (await sessao.execute(consulta)).scalars().first()
    if linha is None:
        return _PoliticaEfetiva(
            exige_geocerca=_POLITICA_PADRAO["exige_geocerca"],
            exige_rede_permitida=_POLITICA_PADRAO["exige_rede_permitida"],
            limiar_bloqueio=_POLITICA_PADRAO["limiar_bloqueio"],
            limiar_revisao=_POLITICA_PADRAO["limiar_revisao"],
            politica_fora_geocerca=_POLITICA_PADRAO["politica_fora_geocerca"],
            exige_reautenticacao=_POLITICA_PADRAO["exige_reautenticacao"],
            ttl_offline_horas=_POLITICA_PADRAO["ttl_offline_horas"],
        )
    return _PoliticaEfetiva(
        exige_geocerca=linha.exige_geocerca,
        exige_rede_permitida=linha.exige_rede_permitida,
        limiar_bloqueio=linha.limiar_bloqueio,
        limiar_revisao=linha.limiar_revisao,
        politica_fora_geocerca=linha.politica_fora_geocerca,
        exige_reautenticacao=linha.exige_reautenticacao,
        ttl_offline_horas=linha.ttl_offline_horas,
    )


async def _resolver_colaborador(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID | None,
    cpf: str | None,
    matricula: str | None,
    empresa_id: UUID | None,
) -> Colaborador:
    """Resolve o colaborador por `colaboradorId`, `cpf` ou `matricula`
    (nesta ordem de preferencia quando mais de um vem preenchido)."""
    if colaborador_id is not None:
        consulta = sa.select(Colaborador).where(
            Colaborador.tenant_id == tenant_id,
            Colaborador.id == colaborador_id,
            Colaborador.excluido_em.is_(None),
        )
    elif cpf is not None:
        consulta = sa.select(Colaborador).where(
            Colaborador.tenant_id == tenant_id,
            Colaborador.cpf == cpf,
            Colaborador.excluido_em.is_(None),
        )
        if empresa_id is not None:
            consulta = consulta.where(Colaborador.empresa_id == empresa_id)
    elif matricula is not None:
        if empresa_id is None:
            raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Informe empresaId junto com matricula.")
        consulta = sa.select(Colaborador).where(
            Colaborador.tenant_id == tenant_id,
            Colaborador.empresa_id == empresa_id,
            Colaborador.matricula == matricula,
            Colaborador.excluido_em.is_(None),
        )
    else:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Informe colaboradorId, cpf ou matricula.")

    linhas = (await sessao.execute(consulta.limit(2))).scalars().all()
    if not linhas:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Colaborador nao encontrado.")
    if len(linhas) > 1:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="CPF ambiguo entre empresas do tenant; informe empresaId.",
        )
    return linhas[0]


async def _vinculo_ativo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    empresa_id: UUID,
    data_referencia: dt.date,
) -> Vinculo:
    """Vinculo com `apuraPonto=true` e `status='ativo'` vigente na data. Sem
    ele, quem chama responde `PONTO-MARC-009` (a Portaria so reconhece
    marcacao de quem tem relacao de trabalho vigente sujeita a apuracao)."""
    consulta = (
        sa.select(Vinculo)
        .where(
            Vinculo.tenant_id == tenant_id,
            Vinculo.colaborador_id == colaborador_id,
            Vinculo.empresa_id == empresa_id,
            Vinculo.apura_ponto.is_(True),
            Vinculo.status == "ativo",
            Vinculo.excluido_em.is_(None),
            Vinculo.data_inicio <= data_referencia,
            sa.or_(Vinculo.data_fim.is_(None), Vinculo.data_fim >= data_referencia),
        )
        .order_by(Vinculo.principal.desc())
        .limit(1)
    )
    vinculo = (await sessao.execute(consulta)).scalars().first()
    if vinculo is None:
        raise ErroDeAplicacao("PONTO-MARC-009")
    return vinculo


async def _redes_autorizadas(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    unidade_id: UUID | None,
    canal: str,
) -> list[FaixaPermitida]:
    """Faixas ativas de `redes_permitidas` no escopo (empresa, unidade
    opcional, canal opcional), prontas para `app.organizacao.redes.ip_autorizado`."""
    consulta = sa.select(RedePermitida).where(
        RedePermitida.tenant_id == tenant_id,
        RedePermitida.empresa_id == empresa_id,
        RedePermitida.ativo.is_(True),
        sa.or_(RedePermitida.unidade_id.is_(None), RedePermitida.unidade_id == unidade_id),
        sa.or_(RedePermitida.canal.is_(None), RedePermitida.canal == canal),
    )
    linhas = (await sessao.execute(consulta)).scalars().all()
    return [FaixaPermitida(cidr=str(linha.cidr), ativo=linha.ativo) for linha in linhas]


async def _verificar_dispositivo_pessoal(
    sessao: AsyncSession, *, tenant_id: UUID, colaborador_id: UUID, dispositivo_id: UUID | None
) -> None:
    """So para `canal='mobile'`: o aparelho precisa ser o unico vinculo ATIVO
    do colaborador (`uq_dispositivo_vinculos_ativo`). Ausente ou apontando
    para outro aparelho -> `PONTO-DISP-001`; aparelho bloqueado, revogado ou
    substituido -> `PONTO-DISP-002`."""
    if dispositivo_id is None:
        raise ErroDeAplicacao(
            "PONTO-DISP-001", detalhe="dispositivoId obrigatorio no canal mobile."
        )
    vinculo = (
        await sessao.execute(
            sa.select(DispositivoVinculo)
            .where(
                DispositivoVinculo.tenant_id == tenant_id,
                DispositivoVinculo.colaborador_id == colaborador_id,
                DispositivoVinculo.status == "ativo",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if vinculo is None or vinculo.dispositivo_id != dispositivo_id:
        raise ErroDeAplicacao("PONTO-DISP-001")
    dispositivo = (
        await sessao.execute(
            sa.select(Dispositivo).where(
                Dispositivo.tenant_id == tenant_id, Dispositivo.id == dispositivo_id
            )
        )
    ).scalar_one_or_none()
    if dispositivo is None or dispositivo.status in ("bloqueado", "revogado", "substituido"):
        raise ErroDeAplicacao("PONTO-DISP-002")


async def _verificar_reautenticacao(
    sessao: AsyncSession, *, tenant_id: UUID, usuario_id: UUID | None
) -> None:
    """So para `canal='web'` com `exigeReautenticacao`: confere
    `sessoes.reautenticado_em` recente (`JANELA_REAUTENTICACAO`) da sessao
    mais recentemente ativa do usuario. `Sujeito` (unico contrato consumido
    desta fase de `app.core.seguranca`) nao carrega `sessao_id` -- por isso a
    sessao e resolvida pela mais recente ainda aberta do usuario no tenant,
    em vez de por identificador exato. Ausente ou expirada -> `PONTO-AUTH-011`."""
    if usuario_id is None:
        raise ErroDeAplicacao("PONTO-AUTH-011")
    sessao_usuario = (
        await sessao.execute(
            sa.select(Sessao)
            .where(
                Sessao.tenant_id == tenant_id,
                Sessao.usuario_id == usuario_id,
                Sessao.encerrada_em.is_(None),
            )
            .order_by(Sessao.ultima_atividade_em.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    limite = dt.datetime.now(dt.UTC) - JANELA_REAUTENTICACAO
    if (
        sessao_usuario is None
        or sessao_usuario.reautenticado_em is None
        or sessao_usuario.reautenticado_em < limite
    ):
        raise ErroDeAplicacao("PONTO-AUTH-011")


def _sinais_do_corpo(corpo: contrato.MarcacaoCriar) -> SinaisRegistro:
    """Monta `SinaisRegistro` a partir dos campos do corpo, tal como
    informados pelo cliente (nenhum e verificado criptograficamente nesta
    fase -- ver docstring de `app.marcacao.confianca.motor`)."""
    flags = corpo.flags_integridade or {}
    return SinaisRegistro(
        dentro_geocerca=None,
        distancia_geocerca_metros=None,
        precisao_insuficiente=False,
        score_facial=None,
        liveness_aprovado=None,
        attestation_veredito="indisponivel",
        root_detectado=flags.get("rootDetectado"),
        emulador_detectado=flags.get("emuladorDetectado"),
        modo_desenvolvedor=flags.get("modoDesenvolvedor"),
        mock_location=flags.get("mockLocation"),
        camera_virtual=flags.get("cameraVirtual"),
        velocidade_desde_ultima_kmh=None,
        flags_integridade=dict(flags),
    )


def _marcacao_para_schema(marcacao: Marcacao) -> contrato.Marcacao:
    return contrato.Marcacao(
        id=marcacao.id,
        tenantId=marcacao.tenant_id,
        repPId=marcacao.rep_p_id,
        empresaId=marcacao.empresa_id,
        unidadeId=marcacao.unidade_id,
        colaboradorId=marcacao.colaborador_id,
        vinculoId=marcacao.vinculo_id,
        nsr=marcacao.nsr,
        tipoRegistro=contrato.TipoRegistro(marcacao.tipo_registro),
        sentidoInformado=contrato.SentidoInformado(marcacao.sentido_informado)
        if marcacao.sentido_informado
        else None,
        cpf=marcacao.cpf,
        pisNit=marcacao.pis_nit,
        datahoraMarcacao=marcacao.datahora_marcacao,
        datahoraGravacao=marcacao.datahora_gravacao,
        datahoraDispositivo=marcacao.datahora_dispositivo,
        fusoHorario=marcacao.fuso_horario,
        canal=contrato.Canal2(marcacao.canal),
        dispositivoId=marcacao.dispositivo_id,
        terminalId=marcacao.terminal_id,
        externalId=marcacao.external_id,
        logExternoId=marcacao.log_externo_id,
        crc16=marcacao.crc16,
        hashAnterior=marcacao.hash_anterior,
        hashRegistro=marcacao.hash_registro,
        linhaAfd=marcacao.linha_afd,
        coletadaOffline=marcacao.coletada_offline,
        comprovanteId=None,
        criadoEm=marcacao.criado_em,
        criadoPor=marcacao.criado_por,
    )


def _comprovante_para_schema(comprovante: Comprovante) -> contrato.Comprovante:
    """`Comprovante.datahoraMarcacao` (API) x `comprovantes.marcacao_datahora`
    (banco): divergencia deliberada de RFC-001 D-07 (`glossario.md`, secao
    3.2) -- a conversao NAO e mecanica, tratada explicitamente aqui."""
    return contrato.Comprovante(
        id=comprovante.id,
        tenantId=comprovante.tenant_id,
        marcacaoId=comprovante.marcacao_id,
        colaboradorId=comprovante.colaborador_id,
        cpf=comprovante.cpf,
        numero=comprovante.numero,
        nsr=comprovante.nsr,
        datahoraMarcacao=comprovante.marcacao_datahora,
        conteudoTexto=comprovante.conteudo_texto,
        conteudoRef=comprovante.conteudo_ref,
        hashSha256=comprovante.hash_sha256,
        assinaturaRef=comprovante.assinatura_ref,
        emitidoEm=comprovante.emitido_em,
        disponivelAte=comprovante.disponivel_ate,
        canalEntrega=contrato.CanalEntrega(comprovante.canal_entrega),
        criadoEm=comprovante.criado_em,
    )


async def _resposta_de_marcacao_existente(
    sessao: AsyncSession, marcacao: Marcacao, *, replay: bool
) -> contrato.MarcacaoCriada:
    """Monta `MarcacaoCriada` a partir de uma marcacao JA persistida (replay
    de idempotencia): busca o comprovante correspondente e devolve
    `duplicada=true`, sem tocar em `marcacoes_meta` nem publicar evento --
    nada de novo aconteceu."""
    comprovante = (
        await sessao.execute(
            sa.select(Comprovante).where(
                Comprovante.tenant_id == marcacao.tenant_id,
                Comprovante.marcacao_id == marcacao.id,
            )
        )
    ).scalar_one_or_none()
    return contrato.MarcacaoCriada(
        marcacao=_marcacao_para_schema(marcacao),
        comprovante=_comprovante_para_schema(comprovante) if comprovante else None,
        scoreConfianca=100,
        classificacaoConfianca=contrato.ClassificacaoConfianca1.alta,
        revisaoRequerida=False,
        dentroGeocerca=None,
        avisos=[],
        duplicada=True,
    )


async def registrar_marcacao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    corpo: contrato.MarcacaoCriar,
    idempotency_key: str | None,
    sujeito: Sujeito,
    ip_origem: str | None = None,
    datahora_marcacao_forcada: dt.datetime | None = None,
    coletada_offline: bool = False,
) -> ResultadoRegistro:
    """Corpo de `criarMarcacao`. Ver docstring do modulo para a ordem exata.

    `datahora_marcacao_forcada`/`coletada_offline` existem para o fluxo
    offline (T7, `app.marcacao.pipeline.offline.sincronizar_lote`): o
    servidor carimba o relogio nesse caso tambem, so que com o instante REAL
    da captura, preservado do aparelho, nunca com "agora"."""
    if not idempotency_key:
        raise ErroDeAplicacao("PONTO-IDEM-001")

    if not await idempotencia.travar_idempotency_key(
        sessao, tenant_id=tenant_id, idempotency_key=idempotency_key
    ):
        raise ErroDeAplicacao("PONTO-IDEM-003")

    canal = str(corpo.canal) if corpo.canal is not None else None
    if not canal:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Campo 'canal' e obrigatorio.")

    colaborador = await _resolver_colaborador(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=corpo.colaborador_id,
        cpf=corpo.cpf,
        matricula=corpo.matricula,
        empresa_id=corpo.empresa_id,
    )
    empresa_id = corpo.empresa_id or colaborador.empresa_id
    if corpo.empresa_id is not None and colaborador.empresa_id != corpo.empresa_id:
        raise ErroDeAplicacao(
            "PONTO-REC-001", detalhe="Colaborador nao pertence a empresa informada."
        )

    hash_identidade = idempotencia.calcular_hash_identidade(
        colaborador_id=colaborador.id,
        empresa_id=empresa_id,
        unidade_id=corpo.unidade_id,
        canal=canal,
        dispositivo_id=corpo.dispositivo_id,
        terminal_id=corpo.terminal_id,
        sentido_informado=str(corpo.sentido_informado) if corpo.sentido_informado else None,
        cpf=colaborador.cpf,
        external_id=corpo.external_id,
        log_externo_id=corpo.log_externo_id,
    )

    existente_por_chave = await idempotencia.buscar_marcacao_por_chave(
        sessao,
        tenant_id=tenant_id,
        escopo=idempotencia.ESCOPO_IDEMPOTENCY_KEY,
        chave=idempotencia.chave_idempotency_key(idempotency_key),
    )
    if existente_por_chave is not None:
        if idempotencia.hash_identidade_da_marcacao(existente_por_chave) == hash_identidade:
            resposta = await _resposta_de_marcacao_existente(
                sessao, existente_por_chave, replay=True
            )
            return ResultadoRegistro(resposta=resposta, replay=True)
        raise ErroDeAplicacao("PONTO-IDEM-002")

    if canal == "api" and corpo.external_id:
        colisao = await idempotencia.buscar_marcacao_por_chave(
            sessao,
            tenant_id=tenant_id,
            escopo=idempotencia.ESCOPO_EXTERNAL_ID,
            chave=idempotencia.chave_external_id(canal, corpo.external_id),
        )
        if colisao is not None:
            raise ErroDeAplicacao("PONTO-MARC-003", contexto_log={"marcacao_id": str(colisao.id)})
    if (
        canal == "terminal"
        and corpo.dispositivo_id is not None
        and corpo.log_externo_id is not None
    ):
        colisao = await idempotencia.buscar_marcacao_por_chave(
            sessao,
            tenant_id=tenant_id,
            escopo=idempotencia.ESCOPO_DISPOSITIVO_LOG,
            chave=idempotencia.chave_dispositivo_log(corpo.dispositivo_id, corpo.log_externo_id),
        )
        if colisao is not None:
            raise ErroDeAplicacao("PONTO-MARC-003", contexto_log={"marcacao_id": str(colisao.id)})

    datahora_marcacao = datahora_marcacao_forcada or dt.datetime.now(dt.UTC)
    data_referencia = datahora_marcacao.date()

    vinculo = await _vinculo_ativo(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador.id,
        empresa_id=empresa_id,
        data_referencia=data_referencia,
    )

    rep_p = await rep_p_ativo(sessao, tenant_id, empresa_id)
    if rep_p is None:
        raise ErroDeAplicacao("PONTO-MARC-010")

    unidade_id = corpo.unidade_id or vinculo.unidade_id
    politica = await _politica_efetiva(
        sessao, tenant_id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id, canal=canal
    )

    avisos: list[str] = []
    dentro_geocerca: bool | None = None
    if politica.exige_geocerca and corpo.latitude is not None and corpo.longitude is not None:
        unidade = (
            (
                await sessao.execute(
                    sa.select(Unidade).where(
                        Unidade.tenant_id == tenant_id, Unidade.id == unidade_id
                    )
                )
            ).scalar_one_or_none()
            if unidade_id is not None
            else None
        )
        if unidade is not None:
            geocerca_unidade = GeocercaUnidade(
                geocerca_latitude=float(unidade.geocerca_latitude)
                if unidade.geocerca_latitude is not None
                else None,
                geocerca_longitude=float(unidade.geocerca_longitude)
                if unidade.geocerca_longitude is not None
                else None,
                geocerca_raio_metros=unidade.geocerca_raio_metros,
                geocerca_poligono=unidade.geocerca_poligono,
                geocerca_obrigatoria=unidade.geocerca_obrigatoria,
                geocerca_tolerancia_metros=unidade.geocerca_tolerancia_metros,
            )
            resultado_geocerca = dentro_da_geocerca(
                geocerca_unidade, corpo.latitude, corpo.longitude, corpo.precisao_metros
            )
            if resultado_geocerca.precisao_insuficiente:
                raise ErroDeAplicacao("PONTO-GEO-002")
            if resultado_geocerca.tem_geocerca:
                dentro_geocerca = resultado_geocerca.dentro
                if not resultado_geocerca.dentro:
                    if politica.politica_fora_geocerca == "bloquear":
                        raise ErroDeAplicacao("PONTO-GEO-001")
                    if politica.politica_fora_geocerca == "sinalizar":
                        avisos.append("fora_da_geocerca")

    if politica.exige_rede_permitida and ip_origem is not None:
        faixas = await _redes_autorizadas(
            sessao, tenant_id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id, canal=canal
        )
        if not ip_autorizado(faixas, ip_origem):
            raise ErroDeAplicacao("PONTO-REDE-001")

    if canal in CANAIS_COM_VINCULO_DE_DISPOSITIVO:
        await _verificar_dispositivo_pessoal(
            sessao,
            tenant_id=tenant_id,
            colaborador_id=colaborador.id,
            dispositivo_id=corpo.dispositivo_id,
        )

    if politica.exige_reautenticacao and canal == "web":
        await _verificar_reautenticacao(sessao, tenant_id=tenant_id, usuario_id=sujeito.usuario_id)

    sinais = _sinais_do_corpo(corpo)
    resultado_confianca: ResultadoConfianca = avaliar_confianca(
        sinais, limiar_bloqueio=politica.limiar_bloqueio, limiar_revisao=politica.limiar_revisao
    )
    if resultado_confianca.score < politica.limiar_bloqueio:
        raise ErroDeAplicacao("PONTO-SCORE-001")
    revisao_requerida = resultado_confianca.score < politica.limiar_revisao
    revisao_status = "pendente" if revisao_requerida else "nao_requer"
    avisos.extend(resultado_confianca.avisos)

    dados = DadosMarcacao(
        rep_p_id=rep_p.id,
        empresa_id=empresa_id,
        cpf=colaborador.cpf,
        canal=canal,
        datahora_marcacao=datahora_marcacao,
        unidade_id=unidade_id,
        colaborador_id=colaborador.id,
        vinculo_id=vinculo.id,
        sentido_informado=str(corpo.sentido_informado) if corpo.sentido_informado else None,
        pis_nit=colaborador.pis_nit,
        datahora_dispositivo=corpo.datahora_dispositivo,
        dispositivo_id=corpo.dispositivo_id,
        terminal_id=corpo.terminal_id,
        external_id=corpo.external_id,
        log_externo_id=corpo.log_externo_id,
        idempotency_key=idempotency_key,
        coletada_offline=coletada_offline,
        criado_por=sujeito.usuario_id,
    )
    marcacao = await persistir_marcacao(sessao, tenant_id=tenant_id, dados=dados)

    sessao.add(
        MarcacaoMeta(
            tenant_id=tenant_id,
            marcacao_id=marcacao.id,
            marcacao_datahora=marcacao.datahora_marcacao,
            latitude=corpo.latitude,
            longitude=corpo.longitude,
            precisao_metros=corpo.precisao_metros,
            unidade_geocerca_id=unidade_id,
            dentro_geocerca=dentro_geocerca,
            distancia_geocerca_metros=None,
            score_facial=None,
            liveness_metodo=str(corpo.liveness_metodo) if corpo.liveness_metodo else None,
            score_confianca=resultado_confianca.score,
            classificacao_confianca=resultado_confianca.classificacao,
            flags_integridade=dict(corpo.flags_integridade or {}),
            attestation_veredito="indisponivel",
            root_detectado=sinais.root_detectado,
            emulador_detectado=sinais.emulador_detectado,
            modo_desenvolvedor=sinais.modo_desenvolvedor,
            mock_location=sinais.mock_location,
            camera_virtual=sinais.camera_virtual,
            wifi_bssid=corpo.wifi_bssid,
            ip=ip_origem,
            revisao_status=revisao_status,
            criado_por=sujeito.usuario_id,
        )
    )
    await sessao.flush()

    await idempotencia.registrar_chave(
        sessao,
        tenant_id=tenant_id,
        escopo=idempotencia.ESCOPO_IDEMPOTENCY_KEY,
        chave=idempotencia.chave_idempotency_key(idempotency_key),
        marcacao_id=marcacao.id,
        datahora_marcacao=marcacao.datahora_marcacao,
        usuario_id=sujeito.usuario_id,
        codigo_conflito="PONTO-IDEM-003",
    )
    if canal == "api" and corpo.external_id:
        await idempotencia.registrar_chave(
            sessao,
            tenant_id=tenant_id,
            escopo=idempotencia.ESCOPO_EXTERNAL_ID,
            chave=idempotencia.chave_external_id(canal, corpo.external_id),
            marcacao_id=marcacao.id,
            datahora_marcacao=marcacao.datahora_marcacao,
            usuario_id=sujeito.usuario_id,
        )
    if (
        canal == "terminal"
        and corpo.dispositivo_id is not None
        and corpo.log_externo_id is not None
    ):
        await idempotencia.registrar_chave(
            sessao,
            tenant_id=tenant_id,
            escopo=idempotencia.ESCOPO_DISPOSITIVO_LOG,
            chave=idempotencia.chave_dispositivo_log(corpo.dispositivo_id, corpo.log_externo_id),
            marcacao_id=marcacao.id,
            datahora_marcacao=marcacao.datahora_marcacao,
            usuario_id=sujeito.usuario_id,
        )

    # Import tardio: `app.marcacao.comprovantes` e propriedade de A3 (T8) --
    # evita ciclo de import caso aquele pacote um dia precise de algo daqui.
    from app.marcacao.comprovantes.emissor import emitir_comprovante
    from app.marcacao.comprovantes.eventos_comprovante import publicar_comprovante_emitido

    comprovante = await emitir_comprovante(sessao, marcacao)

    eventos_marcacao.publicar_marcacao_criada(
        tenant_id=tenant_id,
        marcacao_id=marcacao.id,
        colaborador_id=colaborador.id,
        cpf=marcacao.cpf,
        nsr=marcacao.nsr,
        datahora_marcacao=marcacao.datahora_marcacao,
        canal=canal,
        rep_p_id=rep_p.id,
        empresa_id=empresa_id,
        vinculo_id=vinculo.id,
        matricula=colaborador.matricula,
        unidade_id=unidade_id,
        datahora_gravacao=marcacao.datahora_gravacao,
        coletada_offline=coletada_offline,
        comprovante_id=comprovante.id,
        hash_registro=marcacao.hash_registro,
    )
    publicar_comprovante_emitido(
        tenant_id=tenant_id,
        comprovante_id=comprovante.id,
        marcacao_id=marcacao.id,
        colaborador_id=colaborador.id,
        numero=comprovante.numero,
        nsr=comprovante.nsr,
        emitido_em=comprovante.emitido_em,
        hash_sha256=comprovante.hash_sha256,
        canal_entrega=comprovante.canal_entrega,
    )
    if revisao_requerida:
        eventos_marcacao.publicar_marcacao_suspeita(
            tenant_id=tenant_id,
            marcacao_id=marcacao.id,
            colaborador_id=colaborador.id,
            score_confianca=resultado_confianca.score,
            classificacao=resultado_confianca.classificacao,
            sinais=list(resultado_confianca.avisos),
            empresa_id=empresa_id,
            nsr=marcacao.nsr,
            canal=canal,
            revisao_status=revisao_status,
        )

    resposta = contrato.MarcacaoCriada(
        marcacao=_marcacao_para_schema(marcacao),
        comprovante=_comprovante_para_schema(comprovante),
        scoreConfianca=resultado_confianca.score,
        classificacaoConfianca=contrato.ClassificacaoConfianca1(resultado_confianca.classificacao),
        revisaoRequerida=revisao_requerida,
        dentroGeocerca=dentro_geocerca,
        avisos=avisos,
        duplicada=False,
    )
    return ResultadoRegistro(resposta=resposta, replay=False)
