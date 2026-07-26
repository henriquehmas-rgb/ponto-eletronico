"""Regra de negocio das tags `unidades` e da allowlist CIDR
(`redes_permitidas`): CRUD, geocerca (ponto+raio e poligono) e faixas de rede.
"""

from __future__ import annotations

from uuid import UUID

from ponto_contracts.organizacao import Empresa, RedePermitida, Unidade
from ponto_contracts.pessoas import Equipe, Vinculo
from sqlalchemy import null as sa_null
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.organizacao import crud_base
from app.organizacao.erros_integridade import mapear_integridade
from app.organizacao.geocerca import GeocercaUnidade
from app.organizacao.paginacao import PedidoDePagina
from app.organizacao.redes import FaixaPermitida, cidr_valido

CAMPOS_ORDENAVEIS_UNIDADE: dict[str, object] = {
    "criado_em": Unidade.criado_em,
    "nome": Unidade.nome,
    "codigo": Unidade.codigo,
}

CAMPOS_ORDENAVEIS_REDE: dict[str, object] = {
    "criado_em": RedePermitida.criado_em,
    "cidr": RedePermitida.cidr,
}


async def _validar_empresa_existe(
    sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID
) -> None:
    await crud_base.obter_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=empresa_id)


def geocerca_da_unidade(unidade: Unidade) -> GeocercaUnidade:
    """Converte o model do ORM na estrutura pura que `app.organizacao.geocerca`
    consome -- desacopla a funcao de teste de pertencimento do SQLAlchemy."""
    return GeocercaUnidade(
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


async def listar_unidades(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    uf: str | None = None,
    com_geocerca: bool | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
    incluir_excluidos: bool = False,
) -> list[Unidade]:
    filtros = []
    if empresa_id is not None:
        filtros.append(Unidade.empresa_id == empresa_id)
    if tipo is not None:
        filtros.append(Unidade.tipo == tipo)
    if uf is not None:
        filtros.append(Unidade.uf == uf)
    if com_geocerca is not None:
        tem_geocerca = Unidade.geocerca_poligono.is_not(None) | Unidade.geocerca_latitude.is_not(
            None
        )
        filtros.append(tem_geocerca if com_geocerca else ~tem_geocerca)
    if ativo is not None:
        filtros.append(Unidade.ativo == ativo)
    if busca:
        filtros.append(Unidade.nome.ilike(f"%{busca}%"))
    return await crud_base.listar(
        sessao,
        Unidade,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_UNIDADE,
        incluir_excluidos=incluir_excluidos,
    )


async def obter_unidade(
    sessao: AsyncSession, *, tenant_id: UUID, unidade_id: UUID, incluir_excluidos: bool = False
) -> Unidade:
    return await crud_base.obter_ou_404(
        sessao, Unidade, tenant_id=tenant_id, id_=unidade_id, incluir_excluidos=incluir_excluidos
    )


def _validar_geocerca(
    *,
    geocerca_latitude: float | None,
    geocerca_longitude: float | None,
    geocerca_raio_metros: int | None,
) -> None:
    informados = (
        geocerca_latitude is not None,
        geocerca_longitude is not None,
        geocerca_raio_metros is not None,
    )
    if any(informados) and not all(informados):
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="Geocerca de ponto e raio exige latitude, longitude e raio juntos.",
        )


async def criar_unidade(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    empresa_id: UUID,
    codigo: str,
    nome: str,
    tipo: str | None = None,
    logradouro: str | None = None,
    numero: str | None = None,
    complemento: str | None = None,
    bairro: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    cep: str | None = None,
    codigo_ibge_municipio: str | None = None,
    fuso_horario: str | None = None,
    geocerca_latitude: float | None = None,
    geocerca_longitude: float | None = None,
    geocerca_raio_metros: int | None = None,
    geocerca_poligono: dict[str, object] | None = None,
    geocerca_obrigatoria: bool | None = None,
    geocerca_tolerancia_metros: int | None = None,
    ativo: bool | None = None,
) -> Unidade:
    await _validar_empresa_existe(sessao, tenant_id=tenant_id, empresa_id=empresa_id)
    _validar_geocerca(
        geocerca_latitude=geocerca_latitude,
        geocerca_longitude=geocerca_longitude,
        geocerca_raio_metros=geocerca_raio_metros,
    )

    unidade = Unidade(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        codigo=codigo,
        nome=nome,
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
        codigo_ibge_municipio=codigo_ibge_municipio,
        geocerca_latitude=geocerca_latitude,
        geocerca_longitude=geocerca_longitude,
        geocerca_raio_metros=geocerca_raio_metros,
        criado_por=usuario_id,
    )
    if tipo is not None:
        unidade.tipo = tipo
    if fuso_horario is not None:
        unidade.fuso_horario = fuso_horario
    # `geocerca_poligono` e JSONB: atribuir `None` explicitamente gravaria o
    # literal JSON `null` (que falha `ck_unidades_poligono`, que exige objeto
    # OU SQL NULL de verdade) em vez de deixar a coluna sem valor. So atribui
    # quando ha poligono de fato.
    if geocerca_poligono is not None:
        unidade.geocerca_poligono = geocerca_poligono
    if geocerca_obrigatoria is not None:
        unidade.geocerca_obrigatoria = geocerca_obrigatoria
    if geocerca_tolerancia_metros is not None:
        unidade.geocerca_tolerancia_metros = geocerca_tolerancia_metros
    if ativo is not None:
        unidade.ativo = ativo

    sessao.add(unidade)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarUnidade") from exc
    return unidade


_CAMPOS_ATUALIZAVEIS_UNIDADE = (
    "codigo",
    "nome",
    "tipo",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "municipio",
    "uf",
    "cep",
    "codigo_ibge_municipio",
    "fuso_horario",
    "geocerca_obrigatoria",
    "geocerca_tolerancia_metros",
    "ativo",
)


async def atualizar_unidade(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> Unidade:
    unidade = await obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)

    if "empresa_id" in dados and dados["empresa_id"] is not None:
        await _validar_empresa_existe(
            sessao,
            tenant_id=tenant_id,
            empresa_id=dados["empresa_id"],  # type: ignore[arg-type]
        )
        unidade.empresa_id = dados["empresa_id"]  # type: ignore[assignment]

    if {"geocerca_latitude", "geocerca_longitude", "geocerca_raio_metros"} & dados.keys():
        _validar_geocerca(
            geocerca_latitude=dados.get("geocerca_latitude", unidade.geocerca_latitude),  # type: ignore[arg-type]
            geocerca_longitude=dados.get("geocerca_longitude", unidade.geocerca_longitude),  # type: ignore[arg-type]
            geocerca_raio_metros=dados.get("geocerca_raio_metros", unidade.geocerca_raio_metros),  # type: ignore[arg-type]
        )
        for campo in ("geocerca_latitude", "geocerca_longitude", "geocerca_raio_metros"):
            if campo in dados:
                setattr(unidade, campo, dados[campo])

    if "geocerca_poligono" in dados:
        # JSONB: `None` atribuido direto viraria o literal JSON `null` (que
        # falha `ck_unidades_poligono`) em vez do SQL NULL que "remover o
        # poligono" precisa. `sa_null()` forca o NULL de verdade.
        valor_poligono = dados["geocerca_poligono"]
        novo_poligono = valor_poligono if valor_poligono is not None else sa_null()
        unidade.geocerca_poligono = novo_poligono  # type: ignore[assignment]

    for campo in _CAMPOS_ATUALIZAVEIS_UNIDADE:
        if campo in dados:
            setattr(unidade, campo, dados[campo])

    unidade.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarUnidade") from exc
    return unidade


async def _unidade_tem_dependente(
    sessao: AsyncSession, *, tenant_id: UUID, unidade_id: UUID
) -> bool:
    for tabela, coluna in ((Equipe, Equipe.unidade_id), (Vinculo, Vinculo.unidade_id)):
        consulta = select(tabela.id).where(tabela.tenant_id == tenant_id, coluna == unidade_id)
        if await crud_base.existe(sessao, consulta):
            return True
    return False


async def excluir_unidade(
    sessao: AsyncSession, *, tenant_id: UUID, unidade_id: UUID, usuario_id: UUID | None
) -> None:
    unidade = await obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)
    if await _unidade_tem_dependente(sessao, tenant_id=tenant_id, unidade_id=unidade_id):
        raise ErroDeAplicacao(
            "PONTO-CONF-004",
            detalhe="Unidade tem equipe ou vinculo ativos e nao pode ser excluida.",
        )
    crud_base.marcar_excluido(unidade, usuario_id=usuario_id)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="excluirUnidade", ao_excluir=True) from exc


# --------------------------------------------------------------------------
# Allowlist CIDR (redes_permitidas)
# --------------------------------------------------------------------------


async def listar_redes_permitidas(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_id: UUID,
    pedido: PedidoDePagina,
    canal: str | None = None,
    ativo: bool | None = None,
) -> list[RedePermitida]:
    await obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)
    filtros = [RedePermitida.unidade_id == unidade_id]
    if canal is not None:
        filtros.append(RedePermitida.canal == canal)
    if ativo is not None:
        filtros.append(RedePermitida.ativo == ativo)
    return await crud_base.listar(
        sessao,
        RedePermitida,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS_REDE,
        tem_soft_delete=False,
    )


async def criar_rede_permitida(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    unidade_id: UUID,
    empresa_id: UUID | None,
    cidr: str,
    descricao: str | None = None,
    canal: str | None = None,
    ativo: bool | None = None,
) -> RedePermitida:
    unidade = await obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)
    empresa_resolvida = empresa_id or unidade.empresa_id
    if empresa_resolvida != unidade.empresa_id:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="empresaId da faixa deve ser a mesma empresa da unidade."
        )
    if not cidr_valido(cidr):
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="CIDR invalido (aceita IPv4 e IPv6).")

    rede = RedePermitida(
        tenant_id=tenant_id,
        empresa_id=empresa_resolvida,
        unidade_id=unidade_id,
        cidr=cidr,
        descricao=descricao,
        canal=canal,
        criado_por=usuario_id,
    )
    if ativo is not None:
        rede.ativo = ativo
    sessao.add(rede)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarRedePermitida") from exc
    return rede


async def excluir_rede_permitida(
    sessao: AsyncSession, *, tenant_id: UUID, unidade_id: UUID, rede_id: UUID
) -> None:
    await obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)
    consulta = select(RedePermitida).where(
        RedePermitida.tenant_id == tenant_id,
        RedePermitida.id == rede_id,
        RedePermitida.unidade_id == unidade_id,
    )
    rede = (await sessao.execute(consulta)).scalar_one_or_none()
    if rede is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Faixa de rede nao encontrada.")
    await sessao.delete(rede)
    await sessao.flush()


async def redes_autorizadas_para(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    unidade_id: UUID | None = None,
    canal: str | None = None,
) -> list[FaixaPermitida]:
    """Faixas ativas no escopo (empresa, unidade opcional, canal opcional),
    prontas para `app.organizacao.redes.ip_autorizado`. So leitura: quem
    **aplica** a regra no momento de bater ponto e a F8."""
    filtros = [
        RedePermitida.tenant_id == tenant_id,
        RedePermitida.empresa_id == empresa_id,
        RedePermitida.ativo.is_(True),
        RedePermitida.unidade_id.is_(None) | (RedePermitida.unidade_id == unidade_id),
        RedePermitida.canal.is_(None) | (RedePermitida.canal == canal),
    ]
    consulta = select(RedePermitida).where(*filtros)
    linhas = (await sessao.execute(consulta)).scalars().all()
    return [FaixaPermitida(cidr=str(linha.cidr), ativo=linha.ativo) for linha in linhas]
