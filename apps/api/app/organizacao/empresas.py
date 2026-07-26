"""Regra de negocio da tag `empresas`: CRUD, validacao de CNPJ, coerencia
matriz/filial e soft delete com recusa quando ha dependente.
"""

from __future__ import annotations

from uuid import UUID

from ponto_contracts.organizacao import Cargo, CentroCusto, Departamento, Empresa, Unidade
from ponto_contracts.pessoas import Equipe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.documentos import cnpj_valido, somente_digitos
from app.core.erros import ErroDeAplicacao
from app.organizacao import crud_base
from app.organizacao.erros_integridade import mapear_integridade
from app.organizacao.paginacao import PedidoDePagina

CAMPOS_ORDENAVEIS: dict[str, object] = {
    "criado_em": Empresa.criado_em,
    "razao_social": Empresa.razao_social,
    "cnpj": Empresa.cnpj,
    "nome_fantasia": Empresa.nome_fantasia,
}


def _validar_cnpj(cnpj: str) -> str:
    digitos = somente_digitos(cnpj)
    if not cnpj_valido(digitos):
        raise ErroDeAplicacao("PONTO-VAL-003", detalhe="CNPJ invalido.")
    return digitos


def _validar_coerencia_matriz(tipo: str, matriz_id: UUID | None) -> None:
    if tipo == "matriz" and matriz_id is not None:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="Empresa do tipo matriz nao pode ter matrizId."
        )
    if tipo == "filial" and matriz_id is None:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Empresa do tipo filial exige matrizId.")


async def listar_empresas(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    pedido: PedidoDePagina,
    empresa_id: UUID | None = None,
    cnpj: str | None = None,
    tipo: str | None = None,
    matriz_id: UUID | None = None,
    ativo: bool | None = None,
    busca: str | None = None,
    incluir_excluidos: bool = False,
) -> list[Empresa]:
    filtros = []
    if empresa_id is not None:
        filtros.append(Empresa.id == empresa_id)
    if cnpj is not None:
        filtros.append(Empresa.cnpj == somente_digitos(cnpj))
    if tipo is not None:
        filtros.append(Empresa.tipo == tipo)
    if matriz_id is not None:
        filtros.append(Empresa.matriz_id == matriz_id)
    if ativo is not None:
        filtros.append(Empresa.ativo == ativo)
    if busca:
        padrao = f"%{busca}%"
        filtros.append(Empresa.razao_social.ilike(padrao) | Empresa.nome_fantasia.ilike(padrao))
    return await crud_base.listar(
        sessao,
        Empresa,
        tenant_id=tenant_id,
        filtros=filtros,
        pedido=pedido,
        campos_ordenaveis=CAMPOS_ORDENAVEIS,
        incluir_excluidos=incluir_excluidos,
    )


async def obter_empresa(
    sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID, incluir_excluidos: bool = False
) -> Empresa:
    return await crud_base.obter_ou_404(
        sessao, Empresa, tenant_id=tenant_id, id_=empresa_id, incluir_excluidos=incluir_excluidos
    )


async def _validar_matriz_existe(sessao: AsyncSession, *, tenant_id: UUID, matriz_id: UUID) -> None:
    matriz = await crud_base.obter_ou_404(sessao, Empresa, tenant_id=tenant_id, id_=matriz_id)
    if matriz.tipo != "matriz":
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="matrizId deve apontar para uma empresa do tipo matriz."
        )


async def criar_empresa(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None,
    matriz_id: UUID | None,
    tipo: str | None,
    cnpj: str,
    razao_social: str,
    nome_fantasia: str | None = None,
    inscricao_estadual: str | None = None,
    inscricao_municipal: str | None = None,
    cnae_principal: str | None = None,
    cei_caepf: str | None = None,
    natureza_juridica: str | None = None,
    logradouro: str | None = None,
    numero: str | None = None,
    complemento: str | None = None,
    bairro: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    cep: str | None = None,
    codigo_ibge_municipio: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
    fuso_horario: str | None = None,
    logo_ref: str | None = None,
    ativo: bool | None = None,
) -> Empresa:
    tipo_resolvido = tipo or "matriz"
    _validar_coerencia_matriz(tipo_resolvido, matriz_id)
    cnpj_digitos = _validar_cnpj(cnpj)
    if matriz_id is not None:
        await _validar_matriz_existe(sessao, tenant_id=tenant_id, matriz_id=matriz_id)

    empresa = Empresa(
        tenant_id=tenant_id,
        matriz_id=matriz_id,
        tipo=tipo_resolvido,
        cnpj=cnpj_digitos,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        inscricao_estadual=inscricao_estadual,
        inscricao_municipal=inscricao_municipal,
        cnae_principal=cnae_principal,
        cei_caepf=cei_caepf,
        natureza_juridica=natureza_juridica,
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
        codigo_ibge_municipio=codigo_ibge_municipio,
        telefone=telefone,
        email=email,
        criado_por=usuario_id,
    )
    if fuso_horario is not None:
        empresa.fuso_horario = fuso_horario
    if logo_ref is not None:
        empresa.logo_ref = logo_ref
    if ativo is not None:
        empresa.ativo = ativo

    sessao.add(empresa)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="criarEmpresa") from exc
    return empresa


_CAMPOS_ATUALIZAVEIS = (
    "nome_fantasia",
    "inscricao_estadual",
    "inscricao_municipal",
    "cnae_principal",
    "cei_caepf",
    "natureza_juridica",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "municipio",
    "uf",
    "cep",
    "codigo_ibge_municipio",
    "telefone",
    "email",
    "fuso_horario",
    "logo_ref",
    "ativo",
)


async def atualizar_empresa(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    usuario_id: UUID | None,
    dados: dict[str, object],
) -> Empresa:
    empresa = await obter_empresa(sessao, tenant_id=tenant_id, empresa_id=empresa_id)

    tipo_novo = dados.get("tipo", empresa.tipo)
    matriz_id_novo = dados.get("matriz_id", empresa.matriz_id)
    if "tipo" in dados or "matriz_id" in dados:
        _validar_coerencia_matriz(str(tipo_novo), matriz_id_novo)  # type: ignore[arg-type]
        if matriz_id_novo is not None:
            await _validar_matriz_existe(sessao, tenant_id=tenant_id, matriz_id=matriz_id_novo)  # type: ignore[arg-type]
        empresa.tipo = str(tipo_novo)
        empresa.matriz_id = matriz_id_novo  # type: ignore[assignment]

    if "cnpj" in dados and dados["cnpj"] is not None:
        empresa.cnpj = _validar_cnpj(str(dados["cnpj"]))

    for campo in _CAMPOS_ATUALIZAVEIS:
        if campo in dados:
            setattr(empresa, campo, dados[campo])

    empresa.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="atualizarEmpresa") from exc
    return empresa


async def _tem_dependente(sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID) -> bool:
    tabelas_filhas = (Unidade, Departamento, CentroCusto, Cargo, Equipe)
    for tabela in tabelas_filhas:
        consulta = select(tabela.id).where(
            tabela.tenant_id == tenant_id,
            tabela.empresa_id == empresa_id,
            tabela.excluido_em.is_(None),
        )
        if await crud_base.existe(sessao, consulta):
            return True
    consulta_filial = select(Empresa.id).where(
        Empresa.tenant_id == tenant_id,
        Empresa.matriz_id == empresa_id,
        Empresa.excluido_em.is_(None),
    )
    return await crud_base.existe(sessao, consulta_filial)


async def excluir_empresa(
    sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID, usuario_id: UUID | None
) -> None:
    empresa = await obter_empresa(sessao, tenant_id=tenant_id, empresa_id=empresa_id)
    if await _tem_dependente(sessao, tenant_id=tenant_id, empresa_id=empresa_id):
        raise ErroDeAplicacao(
            "PONTO-CONF-004",
            detalhe="Empresa tem unidade, departamento, centro de custo, cargo, equipe ou "
            "filial ativos e nao pode ser excluida.",
        )
    crud_base.marcar_excluido(empresa, usuario_id=usuario_id)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise mapear_integridade(exc, operacao="excluirEmpresa", ao_excluir=True) from exc
