"""Modelos Pydantic v2 de `components.schemas`. GERADO -- nao editar.

Regerar com `python tools/gerar_do_contrato.py` (extra `codegen` instalado).

Convencao da casa: atributo Python em `snake_case`, `alias` JSON em `camelCase`.
`populate_by_name=True` permite construir pelos dois nomes; o FastAPI serializa
resposta por alias, entao o corpo que sai do servidor e camelCase, como o
contrato manda.
"""

# ruff: noqa
# mypy: disable-error-code=misc

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import (
    AnyUrl,
    AwareDatetime,
    Base64Str,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
)


class Plano(StrEnum):
    """
    Plano contratado.
    """

    trial = "trial"
    padrao = "padrao"
    avancado = "avancado"
    enterprise = "enterprise"


class Status(StrEnum):
    """
    Situacao contratual do tenant.
    """

    trial = "trial"
    ativo = "ativo"
    suspenso = "suspenso"
    cancelado = "cancelado"


class Tenant(BaseModel):
    """
    Cliente do SaaS. Raiz da multi-tenancy: todo dado de dominio pertence a um tenant e vive sob Row Level Security.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do tenant.
    """
    slug: str | None = Field(None, pattern="^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    """
    Identificador usado no subdominio de acesso. Imutavel na pratica.
    """
    razao_social: str | None = Field(None, alias="razaoSocial")
    """
    Razao social do contratante do SaaS.
    """
    nome_exibicao: str | None = Field(None, alias="nomeExibicao")
    """
    Nome exibido na interface.
    """
    documento: str | None = Field(None, pattern="^[0-9]{14}$")
    """
    CNPJ do contratante. Pode nao coincidir com nenhuma empresa operacional.
    """
    plano: Plano | None = None
    """
    Plano contratado.
    """
    status: Status | None = None
    """
    Situacao contratual do tenant.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao do tenant. Unidades podem sobrescrever.
    """
    locale: str | None = None
    """
    Locale padrao da interface.
    """
    dominio_proprio: str | None = Field(None, alias="dominioProprio")
    """
    Dominio proprio para white label. Reservado para fase futura.
    """
    limite_colaboradores: int | None = Field(None, alias="limiteColaboradores")
    """
    Teto contratual de colaboradores ativos. Ausente significa ilimitado.
    """
    data_contratacao: date | None = Field(None, alias="dataContratacao")
    """
    Data de inicio do contrato.
    """
    data_cancelamento: date | None = Field(None, alias="dataCancelamento")
    """
    Data de encerramento do contrato.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class TenantCriar(BaseModel):
    """
    Dados aceitos na criacao de Tenant.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    slug: str = Field(..., pattern="^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    """
    Identificador usado no subdominio de acesso. Imutavel na pratica.
    """
    razao_social: str = Field(..., alias="razaoSocial")
    """
    Razao social do contratante do SaaS.
    """
    nome_exibicao: str = Field(..., alias="nomeExibicao")
    """
    Nome exibido na interface.
    """
    documento: str | None = Field(None, pattern="^[0-9]{14}$")
    """
    CNPJ do contratante. Pode nao coincidir com nenhuma empresa operacional.
    """
    plano: Plano | None = None
    """
    Plano contratado.
    """
    status: Status | None = None
    """
    Situacao contratual do tenant.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao do tenant. Unidades podem sobrescrever.
    """
    locale: str | None = None
    """
    Locale padrao da interface.
    """
    dominio_proprio: str | None = Field(None, alias="dominioProprio")
    """
    Dominio proprio para white label. Reservado para fase futura.
    """
    limite_colaboradores: int | None = Field(None, alias="limiteColaboradores")
    """
    Teto contratual de colaboradores ativos. Ausente significa ilimitado.
    """
    data_contratacao: date | None = Field(None, alias="dataContratacao")
    """
    Data de inicio do contrato.
    """
    data_cancelamento: date | None = Field(None, alias="dataCancelamento")
    """
    Data de encerramento do contrato.
    """


class TenantAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Tenant. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    slug: str | None = Field(None, pattern="^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    """
    Identificador usado no subdominio de acesso. Imutavel na pratica.
    """
    razao_social: str | None = Field(None, alias="razaoSocial")
    """
    Razao social do contratante do SaaS.
    """
    nome_exibicao: str | None = Field(None, alias="nomeExibicao")
    """
    Nome exibido na interface.
    """
    documento: str | None = Field(None, pattern="^[0-9]{14}$")
    """
    CNPJ do contratante. Pode nao coincidir com nenhuma empresa operacional.
    """
    plano: Plano | None = None
    """
    Plano contratado.
    """
    status: Status | None = None
    """
    Situacao contratual do tenant.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao do tenant. Unidades podem sobrescrever.
    """
    locale: str | None = None
    """
    Locale padrao da interface.
    """
    dominio_proprio: str | None = Field(None, alias="dominioProprio")
    """
    Dominio proprio para white label. Reservado para fase futura.
    """
    limite_colaboradores: int | None = Field(None, alias="limiteColaboradores")
    """
    Teto contratual de colaboradores ativos. Ausente significa ilimitado.
    """
    data_contratacao: date | None = Field(None, alias="dataContratacao")
    """
    Data de inicio do contrato.
    """
    data_cancelamento: date | None = Field(None, alias="dataCancelamento")
    """
    Data de encerramento do contrato.
    """


class Categoria(StrEnum):
    """
    Agrupamento funcional da chave.
    """

    geral = "geral"
    seguranca = "seguranca"
    jornada = "jornada"
    banco_horas = "banco_horas"
    fiscal = "fiscal"
    notificacao = "notificacao"
    integracao = "integracao"
    lgpd = "lgpd"
    aparencia = "aparencia"


class TenantConfiguracao(BaseModel):
    """
    Parametro chave/valor do tenant. Usado para o que nao merece coluna propria: limiares, textos e feature flags.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da configuracao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono da configuracao.
    """
    categoria: Categoria | None = None
    """
    Agrupamento funcional da chave.
    """
    chave: str | None = None
    """
    Chave hierarquica com ponto, por exemplo seguranca.mfa.obrigatorio.
    """
    valor: dict[str, Any] | None = None
    """
    Valor em JSON. O tipo esperado por chave e documentado no catalogo de configuracoes.
    """
    descricao: str | None = None
    """
    Explicacao da configuracao.
    """
    somente_leitura: bool | None = Field(None, alias="somenteLeitura")
    """
    Quando verdadeiro, so o super admin da SEEG altera.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class TenantConfiguracaoCriar(BaseModel):
    """
    Dados aceitos na criacao de TenantConfiguracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    categoria: Categoria
    """
    Agrupamento funcional da chave.
    """
    chave: str
    """
    Chave hierarquica com ponto, por exemplo seguranca.mfa.obrigatorio.
    """
    valor: dict[str, Any]
    """
    Valor em JSON. O tipo esperado por chave e documentado no catalogo de configuracoes.
    """
    descricao: str | None = None
    """
    Explicacao da configuracao.
    """
    somente_leitura: bool | None = Field(None, alias="somenteLeitura")
    """
    Quando verdadeiro, so o super admin da SEEG altera.
    """


class Tipo(StrEnum):
    """
    Natureza do estabelecimento.
    """

    matriz = "matriz"
    filial = "filial"


class Empresa(BaseModel):
    """
    Pessoa juridica empregadora dentro do tenant. Matriz e filiais sao linhas distintas, cada uma com CNPJ proprio e arquivos fiscais proprios.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da empresa.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono da empresa.
    """
    matriz_id: UUID | None = Field(None, alias="matrizId")
    """
    Empresa matriz. Ausente quando a propria empresa e matriz.
    """
    tipo: Tipo | None = None
    """
    Natureza do estabelecimento.
    """
    cnpj: str | None = Field(None, pattern="^[0-9]{14}$")
    """
    CNPJ sem pontuacao, unico por tenant.
    """
    razao_social: str | None = Field(None, alias="razaoSocial")
    """
    Razao social registrada.
    """
    nome_fantasia: str | None = Field(None, alias="nomeFantasia")
    """
    Nome fantasia.
    """
    inscricao_estadual: str | None = Field(None, alias="inscricaoEstadual")
    """
    Inscricao estadual.
    """
    inscricao_municipal: str | None = Field(None, alias="inscricaoMunicipal")
    """
    Inscricao municipal.
    """
    cnae_principal: str | None = Field(None, alias="cnaePrincipal")
    """
    CNAE principal da atividade.
    """
    cei_caepf: str | None = Field(None, alias="ceiCaepf")
    """
    CEI ou CAEPF, quando aplicavel. Vai ao cabecalho do AFD de obras e produtores rurais.
    """
    natureza_juridica: str | None = Field(None, alias="naturezaJuridica")
    """
    Codigo da natureza juridica.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio sede. Base dos feriados municipais.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    email: EmailStr | None = None
    """
    E-mail de contato.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao da empresa.
    """
    logo_ref: str | None = Field(None, alias="logoRef")
    """
    Chave do logotipo no armazenamento de objetos.
    """
    ativo: bool | None = None
    """
    Empresa inativa nao aceita novas marcacoes.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class EmpresaCriar(BaseModel):
    """
    Dados aceitos na criacao de Empresa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    matriz_id: UUID | None = Field(None, alias="matrizId")
    """
    Empresa matriz. Ausente quando a propria empresa e matriz.
    """
    tipo: Tipo | None = None
    """
    Natureza do estabelecimento.
    """
    cnpj: str = Field(..., pattern="^[0-9]{14}$")
    """
    CNPJ sem pontuacao, unico por tenant.
    """
    razao_social: str = Field(..., alias="razaoSocial")
    """
    Razao social registrada.
    """
    nome_fantasia: str | None = Field(None, alias="nomeFantasia")
    """
    Nome fantasia.
    """
    inscricao_estadual: str | None = Field(None, alias="inscricaoEstadual")
    """
    Inscricao estadual.
    """
    inscricao_municipal: str | None = Field(None, alias="inscricaoMunicipal")
    """
    Inscricao municipal.
    """
    cnae_principal: str | None = Field(None, alias="cnaePrincipal")
    """
    CNAE principal da atividade.
    """
    cei_caepf: str | None = Field(None, alias="ceiCaepf")
    """
    CEI ou CAEPF, quando aplicavel. Vai ao cabecalho do AFD de obras e produtores rurais.
    """
    natureza_juridica: str | None = Field(None, alias="naturezaJuridica")
    """
    Codigo da natureza juridica.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio sede. Base dos feriados municipais.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    email: EmailStr | None = None
    """
    E-mail de contato.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao da empresa.
    """
    logo_ref: str | None = Field(None, alias="logoRef")
    """
    Chave do logotipo no armazenamento de objetos.
    """
    ativo: bool | None = None
    """
    Empresa inativa nao aceita novas marcacoes.
    """


class EmpresaAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Empresa. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    matriz_id: UUID | None = Field(None, alias="matrizId")
    """
    Empresa matriz. Ausente quando a propria empresa e matriz.
    """
    tipo: Tipo | None = None
    """
    Natureza do estabelecimento.
    """
    cnpj: str | None = Field(None, pattern="^[0-9]{14}$")
    """
    CNPJ sem pontuacao, unico por tenant.
    """
    razao_social: str | None = Field(None, alias="razaoSocial")
    """
    Razao social registrada.
    """
    nome_fantasia: str | None = Field(None, alias="nomeFantasia")
    """
    Nome fantasia.
    """
    inscricao_estadual: str | None = Field(None, alias="inscricaoEstadual")
    """
    Inscricao estadual.
    """
    inscricao_municipal: str | None = Field(None, alias="inscricaoMunicipal")
    """
    Inscricao municipal.
    """
    cnae_principal: str | None = Field(None, alias="cnaePrincipal")
    """
    CNAE principal da atividade.
    """
    cei_caepf: str | None = Field(None, alias="ceiCaepf")
    """
    CEI ou CAEPF, quando aplicavel. Vai ao cabecalho do AFD de obras e produtores rurais.
    """
    natureza_juridica: str | None = Field(None, alias="naturezaJuridica")
    """
    Codigo da natureza juridica.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio sede. Base dos feriados municipais.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    email: EmailStr | None = None
    """
    E-mail de contato.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso padrao da empresa.
    """
    logo_ref: str | None = Field(None, alias="logoRef")
    """
    Chave do logotipo no armazenamento de objetos.
    """
    ativo: bool | None = None
    """
    Empresa inativa nao aceita novas marcacoes.
    """


class Tipo3(StrEnum):
    """
    Natureza do local.
    """

    sede = "sede"
    filial = "filial"
    obra = "obra"
    cliente = "cliente"
    home_office = "home_office"
    movel = "movel"
    deposito = "deposito"


class Unidade(BaseModel):
    """
    Local fisico de trabalho. Carrega o fuso efetivo da apuracao, a geocerca do registro por app e o conjunto de feriados aplicavel.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da unidade.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono da unidade.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a unidade pertence.
    """
    codigo: str | None = None
    """
    Codigo curto usado em importacoes e relatorios. Unico por empresa.
    """
    nome: str | None = None
    """
    Nome da unidade.
    """
    tipo: Tipo3 | None = None
    """
    Natureza do local.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio. Resolve os feriados municipais aplicaveis.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso efetivo da apuracao. Sobrescreve o fuso da empresa e do tenant.
    """
    geocerca_latitude: float | None = Field(None, alias="geocercaLatitude", ge=-90.0, le=90.0)
    """
    Latitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_longitude: float | None = Field(None, alias="geocercaLongitude", ge=-180.0, le=180.0)
    """
    Longitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_raio_metros: int | None = Field(None, alias="geocercaRaioMetros", ge=1, le=100000)
    """
    Raio da geocerca circular em metros.
    """
    geocerca_poligono: dict[str, Any] | None = Field(None, alias="geocercaPoligono")
    """
    Geocerca poligonal em GeoJSON (Polygon ou MultiPolygon). Quando presente, tem precedencia sobre a circular.
    """
    geocerca_obrigatoria: bool | None = Field(None, alias="geocercaObrigatoria")
    """
    Falso aceita marcacao fora da cerca e a sinaliza para tratamento do gestor (caso do trabalhador externo).
    """
    geocerca_tolerancia_metros: int | None = Field(None, alias="geocercaToleranciaMetros", ge=0)
    """
    Folga somada ao raio para absorver imprecisao do GPS.
    """
    ativo: bool | None = None
    """
    Unidade inativa nao aceita novas marcacoes.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class UnidadeCriar(BaseModel):
    """
    Dados aceitos na criacao de Unidade.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que a unidade pertence.
    """
    codigo: str
    """
    Codigo curto usado em importacoes e relatorios. Unico por empresa.
    """
    nome: str
    """
    Nome da unidade.
    """
    tipo: Tipo3 | None = None
    """
    Natureza do local.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio. Resolve os feriados municipais aplicaveis.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso efetivo da apuracao. Sobrescreve o fuso da empresa e do tenant.
    """
    geocerca_latitude: float | None = Field(None, alias="geocercaLatitude", ge=-90.0, le=90.0)
    """
    Latitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_longitude: float | None = Field(None, alias="geocercaLongitude", ge=-180.0, le=180.0)
    """
    Longitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_raio_metros: int | None = Field(None, alias="geocercaRaioMetros", ge=1, le=100000)
    """
    Raio da geocerca circular em metros.
    """
    geocerca_poligono: dict[str, Any] | None = Field(None, alias="geocercaPoligono")
    """
    Geocerca poligonal em GeoJSON (Polygon ou MultiPolygon). Quando presente, tem precedencia sobre a circular.
    """
    geocerca_obrigatoria: bool | None = Field(None, alias="geocercaObrigatoria")
    """
    Falso aceita marcacao fora da cerca e a sinaliza para tratamento do gestor (caso do trabalhador externo).
    """
    geocerca_tolerancia_metros: int | None = Field(None, alias="geocercaToleranciaMetros", ge=0)
    """
    Folga somada ao raio para absorver imprecisao do GPS.
    """
    ativo: bool | None = None
    """
    Unidade inativa nao aceita novas marcacoes.
    """


class UnidadeAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Unidade. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a unidade pertence.
    """
    codigo: str | None = None
    """
    Codigo curto usado em importacoes e relatorios. Unico por empresa.
    """
    nome: str | None = None
    """
    Nome da unidade.
    """
    tipo: Tipo3 | None = None
    """
    Natureza do local.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio. Resolve os feriados municipais aplicaveis.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso efetivo da apuracao. Sobrescreve o fuso da empresa e do tenant.
    """
    geocerca_latitude: float | None = Field(None, alias="geocercaLatitude", ge=-90.0, le=90.0)
    """
    Latitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_longitude: float | None = Field(None, alias="geocercaLongitude", ge=-180.0, le=180.0)
    """
    Longitude do centro da geocerca circular, em graus decimais WGS84.
    """
    geocerca_raio_metros: int | None = Field(None, alias="geocercaRaioMetros", ge=1, le=100000)
    """
    Raio da geocerca circular em metros.
    """
    geocerca_poligono: dict[str, Any] | None = Field(None, alias="geocercaPoligono")
    """
    Geocerca poligonal em GeoJSON (Polygon ou MultiPolygon). Quando presente, tem precedencia sobre a circular.
    """
    geocerca_obrigatoria: bool | None = Field(None, alias="geocercaObrigatoria")
    """
    Falso aceita marcacao fora da cerca e a sinaliza para tratamento do gestor (caso do trabalhador externo).
    """
    geocerca_tolerancia_metros: int | None = Field(None, alias="geocercaToleranciaMetros", ge=0)
    """
    Folga somada ao raio para absorver imprecisao do GPS.
    """
    ativo: bool | None = None
    """
    Unidade inativa nao aceita novas marcacoes.
    """


class Canal(StrEnum):
    """
    Canal restrito. Ausente aplica a todos os canais; na pratica a restricao interessa ao canal web.
    """

    web = "web"
    mobile = "mobile"
    totem = "totem"
    api = "api"
    terminal = "terminal"


class RedePermitida(BaseModel):
    """
    Faixa CIDR autorizada a registrar ponto. Aceita IPv4 e IPv6; multiplas linhas por escopo cobrem multiplos links.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da faixa.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono da faixa.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a faixa se aplica.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade especifica. Ausente aplica a faixa a toda a empresa.
    """
    cidr: str | None = Field(None, examples=["200.150.10.0/24", "2804:14d:1::/48"])
    """
    Faixa em notacao CIDR, IPv4 ou IPv6.
    """
    descricao: str | None = None
    """
    Identificacao do link, por exemplo Link primario Vivo.
    """
    canal: Canal | None = None
    """
    Canal restrito. Ausente aplica a todos os canais; na pratica a restricao interessa ao canal web.
    """
    ativo: bool | None = None
    """
    Faixa desativada nao autoriza registro.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class RedePermitidaCriar(BaseModel):
    """
    Dados aceitos na criacao de RedePermitida.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a faixa se aplica.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade especifica. Ausente aplica a faixa a toda a empresa.
    """
    cidr: str = Field(..., examples=["200.150.10.0/24", "2804:14d:1::/48"])
    """
    Faixa em notacao CIDR, IPv4 ou IPv6.
    """
    descricao: str | None = None
    """
    Identificacao do link, por exemplo Link primario Vivo.
    """
    canal: Canal | None = None
    """
    Canal restrito. Ausente aplica a todos os canais; na pratica a restricao interessa ao canal web.
    """
    ativo: bool | None = None
    """
    Faixa desativada nao autoriza registro.
    """


class Departamento(BaseModel):
    """
    No da estrutura departamental. Usado para escopo de perfil, agrupamento de relatorio e roteamento de aprovacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do departamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o departamento pertence.
    """
    departamento_pai_id: UUID | None = Field(None, alias="departamentoPaiId")
    """
    Departamento superior na arvore. Ausente na raiz.
    """
    responsavel_colaborador_id: UUID | None = Field(None, alias="responsavelColaboradorId")
    """
    Colaborador responsavel pelo departamento.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do departamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    ativo: bool | None = None
    """
    Departamento ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class DepartamentoCriar(BaseModel):
    """
    Dados aceitos na criacao de Departamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o departamento pertence.
    """
    departamento_pai_id: UUID | None = Field(None, alias="departamentoPaiId")
    """
    Departamento superior na arvore. Ausente na raiz.
    """
    responsavel_colaborador_id: UUID | None = Field(None, alias="responsavelColaboradorId")
    """
    Colaborador responsavel pelo departamento.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome do departamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    ativo: bool | None = None
    """
    Departamento ativo.
    """


class DepartamentoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Departamento. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o departamento pertence.
    """
    departamento_pai_id: UUID | None = Field(None, alias="departamentoPaiId")
    """
    Departamento superior na arvore. Ausente na raiz.
    """
    responsavel_colaborador_id: UUID | None = Field(None, alias="responsavelColaboradorId")
    """
    Colaborador responsavel pelo departamento.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do departamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    ativo: bool | None = None
    """
    Departamento ativo.
    """


class CentroCusto(BaseModel):
    """
    Centro de custo, projeto ou cliente ao qual as horas sao apropriadas. Base do rateio para a folha.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do centro de custo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o centro de custo pertence.
    """
    centro_custo_pai_id: UUID | None = Field(None, alias="centroCustoPaiId")
    """
    Centro de custo superior na arvore.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do centro de custo.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Codigo correspondente no ERP ou na folha do cliente.
    """
    ativo: bool | None = None
    """
    Centro de custo ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class CentroCustoCriar(BaseModel):
    """
    Dados aceitos na criacao de CentroCusto.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o centro de custo pertence.
    """
    centro_custo_pai_id: UUID | None = Field(None, alias="centroCustoPaiId")
    """
    Centro de custo superior na arvore.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome do centro de custo.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Codigo correspondente no ERP ou na folha do cliente.
    """
    ativo: bool | None = None
    """
    Centro de custo ativo.
    """


class CentroCustoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de CentroCusto. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o centro de custo pertence.
    """
    centro_custo_pai_id: UUID | None = Field(None, alias="centroCustoPaiId")
    """
    Centro de custo superior na arvore.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do centro de custo.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Codigo correspondente no ERP ou na folha do cliente.
    """
    ativo: bool | None = None
    """
    Centro de custo ativo.
    """


class Nivel(StrEnum):
    """
    Nivel hierarquico do cargo.
    """

    estagio = "estagio"
    aprendiz = "aprendiz"
    junior = "junior"
    pleno = "pleno"
    senior = "senior"
    especialista = "especialista"
    coordenacao = "coordenacao"
    gerencia = "gerencia"
    diretoria = "diretoria"


class Cargo(BaseModel):
    """
    Cargo ocupado pelo colaborador, com CBO para o eSocial.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do cargo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o cargo pertence.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do cargo.
    """
    cbo: str | None = Field(None, pattern="^[0-9]{6}$")
    """
    Classificacao Brasileira de Ocupacoes, 6 digitos.
    """
    descricao: str | None = None
    """
    Descricao das atribuicoes.
    """
    nivel: Nivel | None = None
    """
    Nivel hierarquico do cargo.
    """
    salario_base: float | None = Field(None, alias="salarioBase", ge=0.0)
    """
    Referencia salarial usada apenas no relatorio de custo de horas extras.
    """
    cargo_confianca: bool | None = Field(None, alias="cargoConfianca")
    """
    Cargo de gestao do art. 62, II da CLT. Sugere dispensa de controle de jornada, decidida no contrato.
    """
    ativo: bool | None = None
    """
    Cargo ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class CargoCriar(BaseModel):
    """
    Dados aceitos na criacao de Cargo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o cargo pertence.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome do cargo.
    """
    cbo: str | None = Field(None, pattern="^[0-9]{6}$")
    """
    Classificacao Brasileira de Ocupacoes, 6 digitos.
    """
    descricao: str | None = None
    """
    Descricao das atribuicoes.
    """
    nivel: Nivel | None = None
    """
    Nivel hierarquico do cargo.
    """
    salario_base: float | None = Field(None, alias="salarioBase", ge=0.0)
    """
    Referencia salarial usada apenas no relatorio de custo de horas extras.
    """
    cargo_confianca: bool | None = Field(None, alias="cargoConfianca")
    """
    Cargo de gestao do art. 62, II da CLT. Sugere dispensa de controle de jornada, decidida no contrato.
    """
    ativo: bool | None = None
    """
    Cargo ativo.
    """


class CargoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Cargo. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o cargo pertence.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do cargo.
    """
    cbo: str | None = Field(None, pattern="^[0-9]{6}$")
    """
    Classificacao Brasileira de Ocupacoes, 6 digitos.
    """
    descricao: str | None = None
    """
    Descricao das atribuicoes.
    """
    nivel: Nivel | None = None
    """
    Nivel hierarquico do cargo.
    """
    salario_base: float | None = Field(None, alias="salarioBase", ge=0.0)
    """
    Referencia salarial usada apenas no relatorio de custo de horas extras.
    """
    cargo_confianca: bool | None = Field(None, alias="cargoConfianca")
    """
    Cargo de gestao do art. 62, II da CLT. Sugere dispensa de controle de jornada, decidida no contrato.
    """
    ativo: bool | None = None
    """
    Cargo ativo.
    """


class Equipe(BaseModel):
    """
    Agrupamento operacional para escala, cobertura de turno e visao do gestor. Ortogonal ao departamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da equipe.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a equipe pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de atuacao da equipe.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento predominante da equipe.
    """
    gestor_colaborador_id: UUID | None = Field(None, alias="gestorColaboradorId")
    """
    Colaborador que responde pela equipe.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome da equipe.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Equipe ativa.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class EquipeCriar(BaseModel):
    """
    Dados aceitos na criacao de Equipe.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que a equipe pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de atuacao da equipe.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento predominante da equipe.
    """
    gestor_colaborador_id: UUID | None = Field(None, alias="gestorColaboradorId")
    """
    Colaborador que responde pela equipe.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome da equipe.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Equipe ativa.
    """


class EquipeAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Equipe. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a equipe pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de atuacao da equipe.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento predominante da equipe.
    """
    gestor_colaborador_id: UUID | None = Field(None, alias="gestorColaboradorId")
    """
    Colaborador que responde pela equipe.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome da equipe.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Equipe ativa.
    """


class Papel(StrEnum):
    """
    Papel na equipe. Lider e substituto entram na cadeia de aprovacao.
    """

    membro = "membro"
    lider = "lider"
    substituto = "substituto"


class EquipeMembro(BaseModel):
    """
    Participacao datada de um colaborador em uma equipe.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da participacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    equipe_id: UUID | None = Field(None, alias="equipeId")
    """
    Equipe.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador participante.
    """
    papel: Papel | None = None
    """
    Papel na equipe. Lider e substituto entram na cadeia de aprovacao.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da participacao.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da participacao. Ausente significa vigencia aberta.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class EquipeMembroCriar(BaseModel):
    """
    Dados aceitos na criacao de EquipeMembro.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    equipe_id: UUID | None = Field(None, alias="equipeId")
    """
    Equipe.
    """
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador participante.
    """
    papel: Papel | None = None
    """
    Papel na equipe. Lider e substituto entram na cadeia de aprovacao.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da participacao.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da participacao. Ausente significa vigencia aberta.
    """


class Sexo(StrEnum):
    """
    Sexo informado.
    """

    feminino = "feminino"
    masculino = "masculino"
    outro = "outro"
    nao_informado = "nao_informado"


class EstadoCivil(StrEnum):
    """
    Estado civil.
    """

    solteiro = "solteiro"
    casado = "casado"
    divorciado = "divorciado"
    viuvo = "viuvo"
    uniao_estavel = "uniao_estavel"
    separado = "separado"


class Status3(StrEnum):
    """
    Situacao consolidada, derivada dos vinculos e afastamentos vigentes.
    """

    pre_admissao = "pre_admissao"
    ativo = "ativo"
    afastado = "afastado"
    ferias = "ferias"
    suspenso = "suspenso"
    desligado = "desligado"


class Colaborador(BaseModel):
    """
    A PESSOA que trabalha. Guarda dados cadastrais e pessoais; as condicoes de trabalho vivem em contratos e vinculos.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do colaborador.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o colaborador esta cadastrado.
    """
    matricula: str | None = None
    """
    Matricula interna da empresa, usada no terminal, no quiosque e nos relatorios.
    """
    cpf: str | None = Field(None, pattern="^[0-9]{11}$")
    """
    CPF sem pontuacao. Vai literalmente para o registro tipo 7 do AFD.
    """
    pis_nit: str | None = Field(None, alias="pisNit", pattern="^[0-9]{11}$")
    """
    PIS, PASEP ou NIT. Exigido pelos leiautes fiscais e pela folha.
    """
    nome_completo: str | None = Field(None, alias="nomeCompleto")
    """
    Nome completo do colaborador.
    """
    nome_social: str | None = Field(None, alias="nomeSocial")
    """
    Nome social. Quando preenchido, e o nome exibido em toda a interface.
    """
    data_nascimento: date | None = Field(None, alias="dataNascimento")
    """
    Data de nascimento.
    """
    sexo: Sexo | None = None
    """
    Sexo informado.
    """
    estado_civil: EstadoCivil | None = Field(None, alias="estadoCivil")
    """
    Estado civil.
    """
    nacionalidade: str | None = None
    """
    Nacionalidade.
    """
    naturalidade: str | None = None
    """
    Municipio de nascimento.
    """
    nome_mae: str | None = Field(None, alias="nomeMae")
    """
    Nome da mae.
    """
    rg_numero: str | None = Field(None, alias="rgNumero")
    """
    Numero do RG.
    """
    rg_orgao_emissor: str | None = Field(None, alias="rgOrgaoEmissor")
    """
    Orgao emissor do RG.
    """
    rg_uf: str | None = Field(None, alias="rgUf", pattern="^[A-Z]{2}$")
    """
    UF do RG.
    """
    ctps_numero: str | None = Field(None, alias="ctpsNumero")
    """
    Numero da CTPS.
    """
    ctps_serie: str | None = Field(None, alias="ctpsSerie")
    """
    Serie da CTPS.
    """
    ctps_uf: str | None = Field(None, alias="ctpsUf", pattern="^[A-Z]{2}$")
    """
    UF da CTPS.
    """
    titulo_eleitor: str | None = Field(None, alias="tituloEleitor")
    """
    Numero do titulo de eleitor.
    """
    email: EmailStr | None = None
    """
    E-mail pessoal ou corporativo.
    """
    telefone: str | None = None
    """
    Telefone principal.
    """
    telefone_alternativo: str | None = Field(None, alias="telefoneAlternativo")
    """
    Telefone alternativo.
    """
    foto_ref: str | None = Field(None, alias="fotoRef")
    """
    Chave da foto cadastral no armazenamento de objetos. NAO e template biometrico.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio de residencia.
    """
    status: Status3 | None = None
    """
    Situacao consolidada, derivada dos vinculos e afastamentos vigentes.
    """
    data_admissao: date | None = Field(None, alias="dataAdmissao")
    """
    Data da primeira admissao.
    """
    data_desligamento: date | None = Field(None, alias="dataDesligamento")
    """
    Data do desligamento.
    """
    pcd: bool | None = None
    """
    Pessoa com deficiencia. Influencia cota legal e relatorios, nao o calculo de jornada.
    """
    observacoes: str | None = None
    """
    Observacoes do RH.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Chave correspondente no ERP ou na folha.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class ColaboradorCriar(BaseModel):
    """
    Dados aceitos na criacao de Colaborador.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o colaborador esta cadastrado.
    """
    matricula: str
    """
    Matricula interna da empresa, usada no terminal, no quiosque e nos relatorios.
    """
    cpf: str = Field(..., pattern="^[0-9]{11}$")
    """
    CPF sem pontuacao. Vai literalmente para o registro tipo 7 do AFD.
    """
    pis_nit: str | None = Field(None, alias="pisNit", pattern="^[0-9]{11}$")
    """
    PIS, PASEP ou NIT. Exigido pelos leiautes fiscais e pela folha.
    """
    nome_completo: str = Field(..., alias="nomeCompleto")
    """
    Nome completo do colaborador.
    """
    nome_social: str | None = Field(None, alias="nomeSocial")
    """
    Nome social. Quando preenchido, e o nome exibido em toda a interface.
    """
    data_nascimento: date | None = Field(None, alias="dataNascimento")
    """
    Data de nascimento.
    """
    sexo: Sexo | None = None
    """
    Sexo informado.
    """
    estado_civil: EstadoCivil | None = Field(None, alias="estadoCivil")
    """
    Estado civil.
    """
    nacionalidade: str | None = None
    """
    Nacionalidade.
    """
    naturalidade: str | None = None
    """
    Municipio de nascimento.
    """
    nome_mae: str | None = Field(None, alias="nomeMae")
    """
    Nome da mae.
    """
    rg_numero: str | None = Field(None, alias="rgNumero")
    """
    Numero do RG.
    """
    rg_orgao_emissor: str | None = Field(None, alias="rgOrgaoEmissor")
    """
    Orgao emissor do RG.
    """
    rg_uf: str | None = Field(None, alias="rgUf", pattern="^[A-Z]{2}$")
    """
    UF do RG.
    """
    ctps_numero: str | None = Field(None, alias="ctpsNumero")
    """
    Numero da CTPS.
    """
    ctps_serie: str | None = Field(None, alias="ctpsSerie")
    """
    Serie da CTPS.
    """
    ctps_uf: str | None = Field(None, alias="ctpsUf", pattern="^[A-Z]{2}$")
    """
    UF da CTPS.
    """
    titulo_eleitor: str | None = Field(None, alias="tituloEleitor")
    """
    Numero do titulo de eleitor.
    """
    email: EmailStr | None = None
    """
    E-mail pessoal ou corporativo.
    """
    telefone: str | None = None
    """
    Telefone principal.
    """
    telefone_alternativo: str | None = Field(None, alias="telefoneAlternativo")
    """
    Telefone alternativo.
    """
    foto_ref: str | None = Field(None, alias="fotoRef")
    """
    Chave da foto cadastral no armazenamento de objetos. NAO e template biometrico.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio de residencia.
    """
    status: Status3 | None = None
    """
    Situacao consolidada, derivada dos vinculos e afastamentos vigentes.
    """
    data_admissao: date | None = Field(None, alias="dataAdmissao")
    """
    Data da primeira admissao.
    """
    data_desligamento: date | None = Field(None, alias="dataDesligamento")
    """
    Data do desligamento.
    """
    pcd: bool | None = None
    """
    Pessoa com deficiencia. Influencia cota legal e relatorios, nao o calculo de jornada.
    """
    observacoes: str | None = None
    """
    Observacoes do RH.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Chave correspondente no ERP ou na folha.
    """


class ColaboradorAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Colaborador. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o colaborador esta cadastrado.
    """
    matricula: str | None = None
    """
    Matricula interna da empresa, usada no terminal, no quiosque e nos relatorios.
    """
    cpf: str | None = Field(None, pattern="^[0-9]{11}$")
    """
    CPF sem pontuacao. Vai literalmente para o registro tipo 7 do AFD.
    """
    pis_nit: str | None = Field(None, alias="pisNit", pattern="^[0-9]{11}$")
    """
    PIS, PASEP ou NIT. Exigido pelos leiautes fiscais e pela folha.
    """
    nome_completo: str | None = Field(None, alias="nomeCompleto")
    """
    Nome completo do colaborador.
    """
    nome_social: str | None = Field(None, alias="nomeSocial")
    """
    Nome social. Quando preenchido, e o nome exibido em toda a interface.
    """
    data_nascimento: date | None = Field(None, alias="dataNascimento")
    """
    Data de nascimento.
    """
    sexo: Sexo | None = None
    """
    Sexo informado.
    """
    estado_civil: EstadoCivil | None = Field(None, alias="estadoCivil")
    """
    Estado civil.
    """
    nacionalidade: str | None = None
    """
    Nacionalidade.
    """
    naturalidade: str | None = None
    """
    Municipio de nascimento.
    """
    nome_mae: str | None = Field(None, alias="nomeMae")
    """
    Nome da mae.
    """
    rg_numero: str | None = Field(None, alias="rgNumero")
    """
    Numero do RG.
    """
    rg_orgao_emissor: str | None = Field(None, alias="rgOrgaoEmissor")
    """
    Orgao emissor do RG.
    """
    rg_uf: str | None = Field(None, alias="rgUf", pattern="^[A-Z]{2}$")
    """
    UF do RG.
    """
    ctps_numero: str | None = Field(None, alias="ctpsNumero")
    """
    Numero da CTPS.
    """
    ctps_serie: str | None = Field(None, alias="ctpsSerie")
    """
    Serie da CTPS.
    """
    ctps_uf: str | None = Field(None, alias="ctpsUf", pattern="^[A-Z]{2}$")
    """
    UF da CTPS.
    """
    titulo_eleitor: str | None = Field(None, alias="tituloEleitor")
    """
    Numero do titulo de eleitor.
    """
    email: EmailStr | None = None
    """
    E-mail pessoal ou corporativo.
    """
    telefone: str | None = None
    """
    Telefone principal.
    """
    telefone_alternativo: str | None = Field(None, alias="telefoneAlternativo")
    """
    Telefone alternativo.
    """
    foto_ref: str | None = Field(None, alias="fotoRef")
    """
    Chave da foto cadastral no armazenamento de objetos. NAO e template biometrico.
    """
    logradouro: str | None = None
    """
    Logradouro do endereco.
    """
    numero: str | None = None
    """
    Numero do endereco.
    """
    complemento: str | None = None
    """
    Complemento do endereco.
    """
    bairro: str | None = None
    """
    Bairro.
    """
    municipio: str | None = None
    """
    Municipio.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    Unidade federativa.
    """
    cep: str | None = Field(None, pattern="^[0-9]{8}$")
    """
    CEP sem pontuacao.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio de residencia.
    """
    status: Status3 | None = None
    """
    Situacao consolidada, derivada dos vinculos e afastamentos vigentes.
    """
    data_admissao: date | None = Field(None, alias="dataAdmissao")
    """
    Data da primeira admissao.
    """
    data_desligamento: date | None = Field(None, alias="dataDesligamento")
    """
    Data do desligamento.
    """
    pcd: bool | None = None
    """
    Pessoa com deficiencia. Influencia cota legal e relatorios, nao o calculo de jornada.
    """
    observacoes: str | None = None
    """
    Observacoes do RH.
    """
    codigo_externo: str | None = Field(None, alias="codigoExterno")
    """
    Chave correspondente no ERP ou na folha.
    """


class Tipo6(StrEnum):
    """
    Tipo do vinculo. Existe no maximo um gestor imediato vigente por colaborador.
    """

    imediato = "imediato"
    substituto = "substituto"
    matricial = "matricial"
    rh = "rh"


class ColaboradorGestor(BaseModel):
    """
    Vinculo de gestao datado. Define a arvore que o perfil gestor enxerga e a cadeia de aprovacao das solicitacoes.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do vinculo de gestao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador subordinado.
    """
    gestor_colaborador_id: UUID | None = Field(None, alias="gestorColaboradorId")
    """
    Colaborador gestor.
    """
    tipo: Tipo6 | None = None
    """
    Tipo do vinculo. Existe no maximo um gestor imediato vigente por colaborador.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class ColaboradorGestorCriar(BaseModel):
    """
    Dados aceitos na criacao de ColaboradorGestor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador subordinado.
    """
    gestor_colaborador_id: UUID = Field(..., alias="gestorColaboradorId")
    """
    Colaborador gestor.
    """
    tipo: Tipo6
    """
    Tipo do vinculo. Existe no maximo um gestor imediato vigente por colaborador.
    """
    vigencia_inicio: date = Field(..., alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """


class Tipo8(StrEnum):
    """
    Modalidade de contratacao.
    """

    clt = "clt"
    aprendiz = "aprendiz"
    estagio = "estagio"
    temporario = "temporario"
    intermitente = "intermitente"
    avulso = "avulso"
    autonomo = "autonomo"
    pj = "pj"
    socio = "socio"
    servidor = "servidor"


class RegimeJornada(StrEnum):
    """
    Regime contratado. Determina a estrategia aplicada pelo resolvedor de jornada.
    """

    fixa = "fixa"
    flexivel = "flexivel"
    livre = "livre"
    escala = "escala"
    field_12x36 = "12x36"
    parcial = "parcial"
    teletrabalho = "teletrabalho"
    externo = "externo"
    sobreaviso = "sobreaviso"


class TipoSalario(StrEnum):
    """
    Forma de remuneracao.
    """

    mensal = "mensal"
    horista = "horista"
    diarista = "diarista"
    semanal = "semanal"
    comissionado = "comissionado"
    tarefa = "tarefa"


class DispensaControleMotivo(StrEnum):
    """
    Fundamento legal da dispensa. Obrigatorio quando controleJornada e falso.
    """

    art62_i_externo = "art62_i_externo"
    art62_ii_gestao = "art62_ii_gestao"
    art62_iii_teletrabalho = "art62_iii_teletrabalho"


class Status6(StrEnum):
    """
    Situacao do contrato.
    """

    rascunho = "rascunho"
    ativo = "ativo"
    suspenso = "suspenso"
    encerrado = "encerrado"


class Contrato(BaseModel):
    """
    Instrumento juridico entre colaborador e empresa: tipo de contratacao, cargo, remuneracao, carga e vigencia.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do contrato.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador contratado.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa contratante.
    """
    numero: str | None = None
    """
    Numero do contrato.
    """
    tipo: Tipo8 | None = None
    """
    Modalidade de contratacao.
    """
    regime_jornada: RegimeJornada | None = Field(None, alias="regimeJornada")
    """
    Regime contratado. Determina a estrategia aplicada pelo resolvedor de jornada.
    """
    cargo_id: UUID | None = Field(None, alias="cargoId")
    """
    Cargo contratado.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Inicio da vigencia contratual.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim da vigencia contratual.
    """
    experiencia_dias: int | None = Field(None, alias="experienciaDias", ge=0, le=90)
    """
    Dias de contrato de experiencia.
    """
    salario: float | None = Field(None, ge=0.0)
    """
    Remuneracao contratada.
    """
    tipo_salario: TipoSalario | None = Field(None, alias="tipoSalario")
    """
    Forma de remuneracao.
    """
    carga_horaria_semanal_minutos: int | None = Field(
        None, alias="cargaHorariaSemanalMinutos", ge=0, le=4200
    )
    """
    Carga contratada por semana, em minutos. 44 horas equivalem a 2640.
    """
    carga_horaria_mensal_minutos: int | None = Field(None, alias="cargaHorariaMensalMinutos", ge=0)
    """
    Carga contratada por mes, em minutos.
    """
    controle_jornada: bool | None = Field(None, alias="controleJornada")
    """
    Falso dispensa o controle de ponto (art. 62 da CLT): nao ha apuracao nem ocorrencia de falta.
    """
    dispensa_controle_motivo: DispensaControleMotivo | None = Field(
        None, alias="dispensaControleMotivo"
    )
    """
    Fundamento legal da dispensa. Obrigatorio quando controleJornada e falso.
    """
    status: Status6 | None = None
    """
    Situacao do contrato.
    """
    motivo_encerramento: str | None = Field(None, alias="motivoEncerramento")
    """
    Motivo registrado no encerramento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento digitalizado do contrato.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class ContratoCriar(BaseModel):
    """
    Dados aceitos na criacao de Contrato.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador contratado.
    """
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa contratante.
    """
    numero: str | None = None
    """
    Numero do contrato.
    """
    tipo: Tipo8
    """
    Modalidade de contratacao.
    """
    regime_jornada: RegimeJornada | None = Field(None, alias="regimeJornada")
    """
    Regime contratado. Determina a estrategia aplicada pelo resolvedor de jornada.
    """
    cargo_id: UUID | None = Field(None, alias="cargoId")
    """
    Cargo contratado.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao.
    """
    data_inicio: date = Field(..., alias="dataInicio")
    """
    Inicio da vigencia contratual.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim da vigencia contratual.
    """
    experiencia_dias: int | None = Field(None, alias="experienciaDias", ge=0, le=90)
    """
    Dias de contrato de experiencia.
    """
    salario: float | None = Field(None, ge=0.0)
    """
    Remuneracao contratada.
    """
    tipo_salario: TipoSalario | None = Field(None, alias="tipoSalario")
    """
    Forma de remuneracao.
    """
    carga_horaria_semanal_minutos: int | None = Field(
        None, alias="cargaHorariaSemanalMinutos", ge=0, le=4200
    )
    """
    Carga contratada por semana, em minutos. 44 horas equivalem a 2640.
    """
    carga_horaria_mensal_minutos: int | None = Field(None, alias="cargaHorariaMensalMinutos", ge=0)
    """
    Carga contratada por mes, em minutos.
    """
    controle_jornada: bool | None = Field(None, alias="controleJornada")
    """
    Falso dispensa o controle de ponto (art. 62 da CLT): nao ha apuracao nem ocorrencia de falta.
    """
    dispensa_controle_motivo: DispensaControleMotivo | None = Field(
        None, alias="dispensaControleMotivo"
    )
    """
    Fundamento legal da dispensa. Obrigatorio quando controleJornada e falso.
    """
    status: Status6 | None = None
    """
    Situacao do contrato.
    """
    motivo_encerramento: str | None = Field(None, alias="motivoEncerramento")
    """
    Motivo registrado no encerramento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento digitalizado do contrato.
    """


class ContratoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Contrato. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador contratado.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa contratante.
    """
    numero: str | None = None
    """
    Numero do contrato.
    """
    tipo: Tipo8 | None = None
    """
    Modalidade de contratacao.
    """
    regime_jornada: RegimeJornada | None = Field(None, alias="regimeJornada")
    """
    Regime contratado. Determina a estrategia aplicada pelo resolvedor de jornada.
    """
    cargo_id: UUID | None = Field(None, alias="cargoId")
    """
    Cargo contratado.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Inicio da vigencia contratual.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim da vigencia contratual.
    """
    experiencia_dias: int | None = Field(None, alias="experienciaDias", ge=0, le=90)
    """
    Dias de contrato de experiencia.
    """
    salario: float | None = Field(None, ge=0.0)
    """
    Remuneracao contratada.
    """
    tipo_salario: TipoSalario | None = Field(None, alias="tipoSalario")
    """
    Forma de remuneracao.
    """
    carga_horaria_semanal_minutos: int | None = Field(
        None, alias="cargaHorariaSemanalMinutos", ge=0, le=4200
    )
    """
    Carga contratada por semana, em minutos. 44 horas equivalem a 2640.
    """
    carga_horaria_mensal_minutos: int | None = Field(None, alias="cargaHorariaMensalMinutos", ge=0)
    """
    Carga contratada por mes, em minutos.
    """
    controle_jornada: bool | None = Field(None, alias="controleJornada")
    """
    Falso dispensa o controle de ponto (art. 62 da CLT): nao ha apuracao nem ocorrencia de falta.
    """
    dispensa_controle_motivo: DispensaControleMotivo | None = Field(
        None, alias="dispensaControleMotivo"
    )
    """
    Fundamento legal da dispensa. Obrigatorio quando controleJornada e falso.
    """
    status: Status6 | None = None
    """
    Situacao do contrato.
    """
    motivo_encerramento: str | None = Field(None, alias="motivoEncerramento")
    """
    Motivo registrado no encerramento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento digitalizado do contrato.
    """


class TipoVinculo(StrEnum):
    """
    Natureza do vinculo.
    """

    empregado = "empregado"
    estagiario = "estagiario"
    aprendiz = "aprendiz"
    temporario = "temporario"
    avulso = "avulso"
    autonomo = "autonomo"
    cooperado = "cooperado"
    diretor = "diretor"
    servidor = "servidor"


class Status9(StrEnum):
    """
    Situacao do vinculo.
    """

    ativo = "ativo"
    suspenso = "suspenso"
    encerrado = "encerrado"


class Vinculo(BaseModel):
    """
    A RELACAO DE TRABALHO efetiva, na granularidade que o AEJ e o eSocial exigem. E a chave da apuracao: apuracao, escala, jornada vigente e conta de banco de horas penduram no vinculo, nao no colaborador.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do vinculo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador vinculado.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa empregadora.
    """
    contrato_id: UUID | None = Field(None, alias="contratoId")
    """
    Contrato que originou o vinculo.
    """
    matricula_esocial: str | None = Field(None, alias="matriculaEsocial")
    """
    Matricula do vinculo no eSocial. Vai para o registro de vinculo do AEJ.
    """
    categoria_esocial: int | None = Field(None, alias="categoriaEsocial")
    """
    Codigo de categoria do trabalhador na tabela 01 do eSocial.
    """
    tipo_vinculo: TipoVinculo | None = Field(None, alias="tipoVinculo")
    """
    Natureza do vinculo.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao.
    """
    cargo_id: UUID | None = Field(None, alias="cargoId")
    """
    Cargo exercido.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Inicio do vinculo.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim do vinculo.
    """
    motivo_desligamento: str | None = Field(None, alias="motivoDesligamento")
    """
    Motivo do desligamento.
    """
    principal: bool | None = None
    """
    Marca o vinculo principal quando ha mais de um simultaneo.
    """
    apura_ponto: bool | None = Field(None, alias="apuraPonto")
    """
    Falso mantem o vinculo para folha, mas fora do motor de apuracao.
    """
    status: Status9 | None = None
    """
    Situacao do vinculo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class VinculoCriar(BaseModel):
    """
    Dados aceitos na criacao de Vinculo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador vinculado.
    """
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa empregadora.
    """
    contrato_id: UUID | None = Field(None, alias="contratoId")
    """
    Contrato que originou o vinculo.
    """
    matricula_esocial: str = Field(..., alias="matriculaEsocial")
    """
    Matricula do vinculo no eSocial. Vai para o registro de vinculo do AEJ.
    """
    categoria_esocial: int | None = Field(None, alias="categoriaEsocial")
    """
    Codigo de categoria do trabalhador na tabela 01 do eSocial.
    """
    tipo_vinculo: TipoVinculo | None = Field(None, alias="tipoVinculo")
    """
    Natureza do vinculo.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao.
    """
    cargo_id: UUID | None = Field(None, alias="cargoId")
    """
    Cargo exercido.
    """
    data_inicio: date = Field(..., alias="dataInicio")
    """
    Inicio do vinculo.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim do vinculo.
    """
    motivo_desligamento: str | None = Field(None, alias="motivoDesligamento")
    """
    Motivo do desligamento.
    """
    principal: bool | None = None
    """
    Marca o vinculo principal quando ha mais de um simultaneo.
    """
    apura_ponto: bool | None = Field(None, alias="apuraPonto")
    """
    Falso mantem o vinculo para folha, mas fora do motor de apuracao.
    """
    status: Status9 | None = None
    """
    Situacao do vinculo.
    """


class Modalidade(StrEnum):
    """
    Modalidade. Facial e a principal; cartao, pin e qrcode existem como fallback obrigatorio.
    """

    facial = "facial"
    digital = "digital"
    cartao = "cartao"
    pin = "pin"
    qrcode = "qrcode"


class Status11(StrEnum):
    """
    Situacao da credencial.
    """

    pendente = "pendente"
    ativa = "ativa"
    reprovada = "reprovada"
    revogada = "revogada"
    expirada = "expirada"


class OrigemCadastro(StrEnum):
    """
    Canal em que o cadastro foi feito.
    """

    terminal = "terminal"
    app = "app"
    web = "web"
    importacao = "importacao"
    rh = "rh"


class Biometria(BaseModel):
    """
    Credencial biometrica ou equivalente de um colaborador. Guarda o ciclo de vida; o vetor em si NUNCA e exposto pela API.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da credencial.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular da credencial.
    """
    modalidade: Modalidade | None = None
    """
    Modalidade. Facial e a principal; cartao, pin e qrcode existem como fallback obrigatorio.
    """
    status: Status11 | None = None
    """
    Situacao da credencial.
    """
    origem_cadastro: OrigemCadastro | None = Field(None, alias="origemCadastro")
    """
    Canal em que o cadastro foi feito.
    """
    qualidade: float | None = Field(None, ge=0.0, le=100.0)
    """
    Qualidade da captura no cadastro, de 0 a 100.
    """
    consentimento_id: UUID | None = Field(None, alias="consentimentoId")
    """
    Consentimento LGPD que autoriza o tratamento. Biometria facial sem consentimento vigente nao pode ser usada.
    """
    identificador_cartao: str | None = Field(None, alias="identificadorCartao")
    """
    Identificador do cartao de proximidade, quando a modalidade e cartao.
    """
    versao_modelo: str | None = Field(None, alias="versaoModelo")
    """
    Versao do modelo que gerou o template ativo, por exemplo arcface-r100-v1. Templates de versoes diferentes nao sao comparaveis.
    """
    cadastrada_em: AwareDatetime | None = Field(None, alias="cadastradaEm")
    """
    Instante do cadastro.
    """
    validada_em: AwareDatetime | None = Field(None, alias="validadaEm")
    """
    Instante da validacao pelo RH.
    """
    revogada_em: AwareDatetime | None = Field(None, alias="revogadaEm")
    """
    Instante da revogacao.
    """
    motivo_revogacao: str | None = Field(None, alias="motivoRevogacao")
    """
    Motivo registrado na revogacao.
    """
    expira_em: AwareDatetime | None = Field(None, alias="expiraEm")
    """
    Data de expurgo programado, alimentada pela politica de retencao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class BiometriaCriar(BaseModel):
    """
    Dados aceitos na criacao de Biometria.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador titular da credencial.
    """
    modalidade: Modalidade
    """
    Modalidade. Facial e a principal; cartao, pin e qrcode existem como fallback obrigatorio.
    """
    status: Status11 | None = None
    """
    Situacao da credencial.
    """
    origem_cadastro: OrigemCadastro = Field(..., alias="origemCadastro")
    """
    Canal em que o cadastro foi feito.
    """
    qualidade: float | None = Field(None, ge=0.0, le=100.0)
    """
    Qualidade da captura no cadastro, de 0 a 100.
    """
    consentimento_id: UUID | None = Field(None, alias="consentimentoId")
    """
    Consentimento LGPD que autoriza o tratamento. Biometria facial sem consentimento vigente nao pode ser usada.
    """
    identificador_cartao: str | None = Field(None, alias="identificadorCartao")
    """
    Identificador do cartao de proximidade, quando a modalidade e cartao.
    """


class Tipo11(StrEnum):
    """
    Natureza do dispositivo.
    """

    terminal = "terminal"
    celular = "celular"
    tablet = "tablet"
    navegador = "navegador"
    totem = "totem"
    integracao = "integracao"


class Plataforma(StrEnum):
    """
    Plataforma de execucao.
    """

    android = "android"
    ios = "ios"
    web = "web"
    linux = "linux"
    windows = "windows"
    macos = "macos"
    embarcado = "embarcado"


class Status13(StrEnum):
    """
    Situacao do dispositivo. substituido indica troca aprovada preservando o historico.
    """

    pendente = "pendente"
    ativo = "ativo"
    bloqueado = "bloqueado"
    revogado = "revogado"
    substituido = "substituido"


class AttestationStatus(StrEnum):
    """
    Ultimo veredito de Play Integrity ou App Attest, sempre verificado no servidor.
    """

    nao_verificado = "nao_verificado"
    aprovado = "aprovado"
    reprovado = "reprovado"
    indisponivel = "indisponivel"


class Dispositivo(BaseModel):
    """
    Qualquer aparelho capaz de originar marcacao: terminal, celular, tablet de quiosque, navegador ou cliente de API.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do dispositivo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o dispositivo pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o dispositivo opera.
    """
    tipo: Tipo11 | None = None
    """
    Natureza do dispositivo.
    """
    plataforma: Plataforma | None = None
    """
    Plataforma de execucao.
    """
    identificador: str | None = None
    """
    Identificador estavel do aparelho: android_id, identifierForVendor, fingerprint do navegador ou numero de serie.
    """
    nome: str | None = None
    """
    Nome amigavel do dispositivo.
    """
    fabricante: str | None = None
    """
    Fabricante do aparelho.
    """
    modelo: str | None = None
    """
    Modelo do aparelho.
    """
    versao_so: str | None = Field(None, alias="versaoSo")
    """
    Versao do sistema operacional.
    """
    versao_app: str | None = Field(None, alias="versaoApp")
    """
    Versao do aplicativo instalado.
    """
    status: Status13 | None = None
    """
    Situacao do dispositivo. substituido indica troca aprovada preservando o historico.
    """
    attestation_status: AttestationStatus | None = Field(None, alias="attestationStatus")
    """
    Ultimo veredito de Play Integrity ou App Attest, sempre verificado no servidor.
    """
    attestation_verificado_em: AwareDatetime | None = Field(None, alias="attestationVerificadoEm")
    """
    Instante da ultima verificacao de attestation.
    """
    root_detectado: bool | None = Field(None, alias="rootDetectado")
    """
    Ultimo estado conhecido de root ou jailbreak.
    """
    emulador_detectado: bool | None = Field(None, alias="emuladorDetectado")
    """
    Ultimo estado conhecido de execucao em emulador.
    """
    modo_desenvolvedor: bool | None = Field(None, alias="modoDesenvolvedor")
    """
    Ultimo estado conhecido das opcoes do desenvolvedor.
    """
    depuracao_usb: bool | None = Field(None, alias="depuracaoUsb")
    """
    Ultimo estado conhecido da depuracao USB.
    """
    ultimo_acesso_em: AwareDatetime | None = Field(None, alias="ultimoAcessoEm")
    """
    Ultimo acesso registrado pelo dispositivo.
    """
    ultimo_ip: str | None = Field(None, alias="ultimoIp")
    """
    Ultimo endereco IP observado.
    """
    colaborador_vinculado_id: UUID | None = Field(None, alias="colaboradorVinculadoId")
    """
    Colaborador com vinculo ativo neste aparelho, quando houver.
    """
    observacoes: str | None = None
    """
    Observacoes do RH ou do suporte.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class DispositivoCriar(BaseModel):
    """
    Dados aceitos na criacao de Dispositivo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o dispositivo pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o dispositivo opera.
    """
    tipo: Tipo11
    """
    Natureza do dispositivo.
    """
    plataforma: Plataforma | None = None
    """
    Plataforma de execucao.
    """
    identificador: str
    """
    Identificador estavel do aparelho: android_id, identifierForVendor, fingerprint do navegador ou numero de serie.
    """
    nome: str | None = None
    """
    Nome amigavel do dispositivo.
    """
    fabricante: str | None = None
    """
    Fabricante do aparelho.
    """
    modelo: str | None = None
    """
    Modelo do aparelho.
    """
    versao_so: str | None = Field(None, alias="versaoSo")
    """
    Versao do sistema operacional.
    """
    versao_app: str | None = Field(None, alias="versaoApp")
    """
    Versao do aplicativo instalado.
    """
    status: Status13 | None = None
    """
    Situacao do dispositivo. substituido indica troca aprovada preservando o historico.
    """
    root_detectado: bool | None = Field(None, alias="rootDetectado")
    """
    Ultimo estado conhecido de root ou jailbreak.
    """
    emulador_detectado: bool | None = Field(None, alias="emuladorDetectado")
    """
    Ultimo estado conhecido de execucao em emulador.
    """
    modo_desenvolvedor: bool | None = Field(None, alias="modoDesenvolvedor")
    """
    Ultimo estado conhecido das opcoes do desenvolvedor.
    """
    depuracao_usb: bool | None = Field(None, alias="depuracaoUsb")
    """
    Ultimo estado conhecido da depuracao USB.
    """
    observacoes: str | None = None
    """
    Observacoes do RH ou do suporte.
    """


class DispositivoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Dispositivo. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o dispositivo pertence.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o dispositivo opera.
    """
    tipo: Tipo11 | None = None
    """
    Natureza do dispositivo.
    """
    plataforma: Plataforma | None = None
    """
    Plataforma de execucao.
    """
    identificador: str | None = None
    """
    Identificador estavel do aparelho: android_id, identifierForVendor, fingerprint do navegador ou numero de serie.
    """
    nome: str | None = None
    """
    Nome amigavel do dispositivo.
    """
    fabricante: str | None = None
    """
    Fabricante do aparelho.
    """
    modelo: str | None = None
    """
    Modelo do aparelho.
    """
    versao_so: str | None = Field(None, alias="versaoSo")
    """
    Versao do sistema operacional.
    """
    versao_app: str | None = Field(None, alias="versaoApp")
    """
    Versao do aplicativo instalado.
    """
    status: Status13 | None = None
    """
    Situacao do dispositivo. substituido indica troca aprovada preservando o historico.
    """
    root_detectado: bool | None = Field(None, alias="rootDetectado")
    """
    Ultimo estado conhecido de root ou jailbreak.
    """
    emulador_detectado: bool | None = Field(None, alias="emuladorDetectado")
    """
    Ultimo estado conhecido de execucao em emulador.
    """
    modo_desenvolvedor: bool | None = Field(None, alias="modoDesenvolvedor")
    """
    Ultimo estado conhecido das opcoes do desenvolvedor.
    """
    depuracao_usb: bool | None = Field(None, alias="depuracaoUsb")
    """
    Ultimo estado conhecido da depuracao USB.
    """
    observacoes: str | None = None
    """
    Observacoes do RH ou do suporte.
    """


class Fabricante(StrEnum):
    """
    Fabricante do equipamento.
    """

    control_id = "control_id"
    henry = "henry"
    topdata = "topdata"
    madis = "madis"
    dimep = "dimep"
    inner = "inner"
    outro = "outro"


class ModoComunicacao(StrEnum):
    """
    push: o equipamento consulta o servidor buscando comandos, obrigatorio em LAN sem IP publico. monitor: o equipamento envia eventos assincronos. polling: o servidor consulta o equipamento.
    """

    push = "push"
    monitor = "monitor"
    polling = "polling"
    direto = "direto"


class Status16(StrEnum):
    """
    Situacao operacional do coletor.
    """

    ativo = "ativo"
    inativo = "inativo"
    manutencao = "manutencao"
    desativado = "desativado"


class Terminal(BaseModel):
    """
    Coletor fisico de marcacao. IMPORTANTE: o terminal NAO e o REP-P. Ele identifica a pessoa e produz um registro de acesso; o REP-P e o nosso software, que atribui o NSR e grava no AFD.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do terminal.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo correspondente.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa dona do coletor.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o coletor esta instalado.
    """
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P sob o qual as marcacoes deste coletor recebem NSR.
    """
    fabricante: Fabricante | None = None
    """
    Fabricante do equipamento.
    """
    modelo: str | None = None
    """
    Modelo do equipamento.
    """
    numero_serie: str | None = Field(None, alias="numeroSerie")
    """
    Numero de serie, unico por tenant.
    """
    endereco_ip: str | None = Field(None, alias="enderecoIp")
    """
    Endereco IP do equipamento na LAN do cliente.
    """
    porta: int | None = Field(None, ge=1, le=65535)
    """
    Porta de comunicacao.
    """
    mac: str | None = None
    """
    Endereco MAC do equipamento.
    """
    modo_comunicacao: ModoComunicacao | None = Field(None, alias="modoComunicacao")
    """
    push: o equipamento consulta o servidor buscando comandos, obrigatorio em LAN sem IP publico. monitor: o equipamento envia eventos assincronos. polling: o servidor consulta o equipamento.
    """
    usuario_api: str | None = Field(None, alias="usuarioApi")
    """
    Usuario da API do equipamento. A senha nunca e devolvida pela API.
    """
    capacidade_faces: int | None = Field(None, alias="capacidadeFaces")
    """
    Capacidade de faces do modelo.
    """
    ultimo_log_externo_id: int | None = Field(None, alias="ultimoLogExternoId")
    """
    Marca dagua do catch-up: maior identificador de registro de acesso ja coletado.
    """
    ultima_sincronizacao_em: AwareDatetime | None = Field(None, alias="ultimaSincronizacaoEm")
    """
    Ultima sincronizacao de cadastro concluida.
    """
    ultimo_contato_em: AwareDatetime | None = Field(None, alias="ultimoContatoEm")
    """
    Ultimo contato do equipamento. Base do alerta de terminal offline.
    """
    intervalo_push_segundos: int | None = Field(None, alias="intervaloPushSegundos", ge=1)
    """
    Intervalo de consulta do equipamento em modo push.
    """
    online: bool | None = None
    """
    Estado derivado do ultimo contato e do intervalo esperado.
    """
    status: Status16 | None = None
    """
    Situacao operacional do coletor.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class TerminalCriar(BaseModel):
    """
    Dados aceitos na criacao de Terminal.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo correspondente.
    """
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa dona do coletor.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o coletor esta instalado.
    """
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P sob o qual as marcacoes deste coletor recebem NSR.
    """
    fabricante: Fabricante
    """
    Fabricante do equipamento.
    """
    modelo: str | None = None
    """
    Modelo do equipamento.
    """
    numero_serie: str = Field(..., alias="numeroSerie")
    """
    Numero de serie, unico por tenant.
    """
    endereco_ip: str | None = Field(None, alias="enderecoIp")
    """
    Endereco IP do equipamento na LAN do cliente.
    """
    porta: int | None = Field(None, ge=1, le=65535)
    """
    Porta de comunicacao.
    """
    mac: str | None = None
    """
    Endereco MAC do equipamento.
    """
    modo_comunicacao: ModoComunicacao | None = Field(None, alias="modoComunicacao")
    """
    push: o equipamento consulta o servidor buscando comandos, obrigatorio em LAN sem IP publico. monitor: o equipamento envia eventos assincronos. polling: o servidor consulta o equipamento.
    """
    usuario_api: str | None = Field(None, alias="usuarioApi")
    """
    Usuario da API do equipamento. A senha nunca e devolvida pela API.
    """
    capacidade_faces: int | None = Field(None, alias="capacidadeFaces")
    """
    Capacidade de faces do modelo.
    """
    intervalo_push_segundos: int | None = Field(None, alias="intervaloPushSegundos", ge=1)
    """
    Intervalo de consulta do equipamento em modo push.
    """
    status: Status16 | None = None
    """
    Situacao operacional do coletor.
    """
    senha_api: SecretStr | None = Field(None, alias="senhaApi")
    """
    Senha da API do equipamento. Aceita apenas na escrita: e cifrada com chave externa ao banco e nunca aparece em nenhuma leitura.
    """


class TerminalAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Terminal. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo correspondente.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa dona do coletor.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade onde o coletor esta instalado.
    """
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P sob o qual as marcacoes deste coletor recebem NSR.
    """
    fabricante: Fabricante | None = None
    """
    Fabricante do equipamento.
    """
    modelo: str | None = None
    """
    Modelo do equipamento.
    """
    numero_serie: str | None = Field(None, alias="numeroSerie")
    """
    Numero de serie, unico por tenant.
    """
    endereco_ip: str | None = Field(None, alias="enderecoIp")
    """
    Endereco IP do equipamento na LAN do cliente.
    """
    porta: int | None = Field(None, ge=1, le=65535)
    """
    Porta de comunicacao.
    """
    mac: str | None = None
    """
    Endereco MAC do equipamento.
    """
    modo_comunicacao: ModoComunicacao | None = Field(None, alias="modoComunicacao")
    """
    push: o equipamento consulta o servidor buscando comandos, obrigatorio em LAN sem IP publico. monitor: o equipamento envia eventos assincronos. polling: o servidor consulta o equipamento.
    """
    usuario_api: str | None = Field(None, alias="usuarioApi")
    """
    Usuario da API do equipamento. A senha nunca e devolvida pela API.
    """
    capacidade_faces: int | None = Field(None, alias="capacidadeFaces")
    """
    Capacidade de faces do modelo.
    """
    intervalo_push_segundos: int | None = Field(None, alias="intervaloPushSegundos", ge=1)
    """
    Intervalo de consulta do equipamento em modo push.
    """
    status: Status16 | None = None
    """
    Situacao operacional do coletor.
    """
    senha_api: SecretStr | None = Field(None, alias="senhaApi")
    """
    Senha da API do equipamento. Aceita apenas na escrita: e cifrada com chave externa ao banco e nunca aparece em nenhuma leitura.
    """


class TerminalSaude(BaseModel):
    """
    Amostra de saude de um coletor. Serie temporal append-only: cada verificacao gera uma linha nova.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da amostra.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    terminal_id: UUID | None = Field(None, alias="terminalId")
    """
    Terminal verificado.
    """
    verificado_em: AwareDatetime | None = Field(None, alias="verificadoEm")
    """
    Instante da verificacao.
    """
    online: bool | None = None
    """
    Resultado da verificacao.
    """
    latencia_ms: int | None = Field(None, alias="latenciaMs", ge=0)
    """
    Latencia observada em milissegundos.
    """
    firmware: str | None = None
    """
    Versao de firmware reportada.
    """
    faces_cadastradas: int | None = Field(None, alias="facesCadastradas")
    """
    Faces cadastradas no equipamento.
    """
    logs_pendentes: int | None = Field(None, alias="logsPendentes")
    """
    Registros ainda nao coletados. Valor alto indica atraso no catch-up.
    """
    memoria_livre_pct: float | None = Field(None, alias="memoriaLivrePct")
    """
    Percentual de memoria livre.
    """
    temperatura: float | None = None
    """
    Temperatura reportada, em graus Celsius.
    """
    alarme: str | None = None
    """
    Alarme reportado, por exemplo violacao de gabinete.
    """
    mensagem: str | None = None
    """
    Mensagem livre da verificacao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Horario(BaseModel):
    """
    Gabarito reutilizavel de um dia de trabalho: entrada, saida e intervalos previstos.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do horario.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o horario pertence.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do horario.
    """
    entrada: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de entrada.
    """
    saida: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de saida.
    """
    intervalo_inicio: str | None = Field(
        None, alias="intervaloInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do intervalo previsto.
    """
    intervalo_fim: str | None = Field(
        None, alias="intervaloFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do intervalo previsto.
    """
    duracao_intervalo_minutos: int | None = Field(None, alias="duracaoIntervaloMinutos", ge=0)
    """
    Duracao do intervalo em minutos.
    """
    intervalos_extras: dict[str, Any] | None = Field(None, alias="intervalosExtras")
    """
    Pausas adicionais em JSON, por exemplo as pausas obrigatorias da NR-17 para digitacao e teleatendimento.
    """
    cruza_meia_noite: bool | None = Field(None, alias="cruzaMeiaNoite")
    """
    Verdadeiro quando a saida e menor que a entrada (noturno e 12x36).
    """
    carga_minutos: int | None = Field(None, alias="cargaMinutos", ge=0, le=1440)
    """
    Carga liquida prevista em minutos, ja descontado o intervalo.
    """
    ativo: bool | None = None
    """
    Horario ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class HorarioCriar(BaseModel):
    """
    Dados aceitos na criacao de Horario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o horario pertence.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome do horario.
    """
    entrada: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de entrada.
    """
    saida: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de saida.
    """
    intervalo_inicio: str | None = Field(
        None, alias="intervaloInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do intervalo previsto.
    """
    intervalo_fim: str | None = Field(
        None, alias="intervaloFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do intervalo previsto.
    """
    duracao_intervalo_minutos: int | None = Field(None, alias="duracaoIntervaloMinutos", ge=0)
    """
    Duracao do intervalo em minutos.
    """
    intervalos_extras: dict[str, Any] | None = Field(None, alias="intervalosExtras")
    """
    Pausas adicionais em JSON, por exemplo as pausas obrigatorias da NR-17 para digitacao e teleatendimento.
    """
    cruza_meia_noite: bool | None = Field(None, alias="cruzaMeiaNoite")
    """
    Verdadeiro quando a saida e menor que a entrada (noturno e 12x36).
    """
    carga_minutos: int = Field(..., alias="cargaMinutos", ge=0, le=1440)
    """
    Carga liquida prevista em minutos, ja descontado o intervalo.
    """
    ativo: bool | None = None
    """
    Horario ativo.
    """


class HorarioAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Horario. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o horario pertence.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do horario.
    """
    entrada: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de entrada.
    """
    saida: str | None = Field(None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Horario previsto de saida.
    """
    intervalo_inicio: str | None = Field(
        None, alias="intervaloInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do intervalo previsto.
    """
    intervalo_fim: str | None = Field(
        None, alias="intervaloFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do intervalo previsto.
    """
    duracao_intervalo_minutos: int | None = Field(None, alias="duracaoIntervaloMinutos", ge=0)
    """
    Duracao do intervalo em minutos.
    """
    intervalos_extras: dict[str, Any] | None = Field(None, alias="intervalosExtras")
    """
    Pausas adicionais em JSON, por exemplo as pausas obrigatorias da NR-17 para digitacao e teleatendimento.
    """
    cruza_meia_noite: bool | None = Field(None, alias="cruzaMeiaNoite")
    """
    Verdadeiro quando a saida e menor que a entrada (noturno e 12x36).
    """
    carga_minutos: int | None = Field(None, alias="cargaMinutos", ge=0, le=1440)
    """
    Carga liquida prevista em minutos, ja descontado o intervalo.
    """
    ativo: bool | None = None
    """
    Horario ativo.
    """


class TipoDia(StrEnum):
    """
    Tipo do dia. dsr identifica o repouso semanal remunerado, o que muda o fator da hora extra.
    """

    util = "util"
    dsr = "dsr"
    folga = "folga"
    compensado = "compensado"
    facultativo = "facultativo"


class JornadaDia(BaseModel):
    """
    Desdobramento da jornada por dia da semana.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do dia da jornada.
    """
    dia_semana: int | None = Field(None, alias="diaSemana", ge=0, le=6)
    """
    Dia da semana: 0 domingo, 1 segunda, ate 6 sabado.
    """
    tipo_dia: TipoDia | None = Field(None, alias="tipoDia")
    """
    Tipo do dia. dsr identifica o repouso semanal remunerado, o que muda o fator da hora extra.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario previsto do dia.
    """
    carga_minutos: int | None = Field(None, alias="cargaMinutos", ge=0, le=1440)
    """
    Carga prevista do dia em minutos.
    """


class Tipo14(StrEnum):
    """
    Estrategia de resolucao. fixa: horario por dia da semana. flexivel: carga com janela. livre: so carga total. motorista: regras da Lei 13.103.
    """

    fixa = "fixa"
    flexivel = "flexivel"
    livre = "livre"
    escala = "escala"
    field_12x36 = "12x36"
    parcial = "parcial"
    intermitente = "intermitente"
    teletrabalho = "teletrabalho"
    motorista = "motorista"


class Jornada(BaseModel):
    """
    Conjunto de regras de trabalho e de calculo aplicado a um vinculo. E o parametro central do motor de apuracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da jornada.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a jornada pertence.
    """
    codigo: str | None = None
    """
    Codigo da jornada, unico por empresa e vigencia.
    """
    nome: str | None = None
    """
    Nome da jornada.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo14 | None = None
    """
    Estrategia de resolucao. fixa: horario por dia da semana. flexivel: carga com janela. livre: so carga total. motorista: regras da Lei 13.103.
    """
    carga_diaria_minutos: int | None = Field(None, alias="cargaDiariaMinutos", ge=0, le=1440)
    """
    Carga diaria prevista.
    """
    carga_semanal_minutos: int | None = Field(None, alias="cargaSemanalMinutos", ge=0, le=4200)
    """
    Carga semanal prevista.
    """
    carga_mensal_minutos: int | None = Field(None, alias="cargaMensalMinutos", ge=0)
    """
    Carga mensal prevista.
    """
    tolerancia_marcacao_minutos: int | None = Field(
        None, alias="toleranciaMarcacaoMinutos", ge=0, le=60
    )
    """
    Tolerancia por marcacao. Padrao legal de 5 minutos (art. 58, par. 1 da CLT).
    """
    tolerancia_diaria_minutos: int | None = Field(
        None, alias="toleranciaDiariaMinutos", ge=0, le=120
    )
    """
    Tolerancia acumulada no dia. Padrao legal de 10 minutos.
    """
    descontar_tudo_se_exceder: bool | None = Field(None, alias="descontarTudoSeExceder")
    """
    Quando verdadeiro e a tolerancia diaria estoura, todo o excedente e computado, nao apenas a diferenca.
    """
    janela_flexivel_minutos: int | None = Field(None, alias="janelaFlexivelMinutos", ge=0)
    """
    Janela de flexibilidade de entrada e saida.
    """
    intervalo_automatico: bool | None = Field(None, alias="intervaloAutomatico")
    """
    Pre-assinalacao do intervalo: o sistema assume o intervalo previsto quando nao ha marcacao correspondente.
    """
    intervalo_minimo_minutos: int | None = Field(None, alias="intervaloMinimoMinutos", ge=0)
    """
    Intervalo intrajornada minimo exigido.
    """
    intervalo_flexivel: bool | None = Field(None, alias="intervaloFlexivel")
    """
    Permite intervalo em horario livre dentro da jornada.
    """
    interjornada_minima_minutos: int | None = Field(None, alias="interjornadaMinimaMinutos", ge=0)
    """
    Descanso minimo entre jornadas. Padrao de 660 minutos (11 horas).
    """
    noturno_inicio: str | None = Field(
        None, alias="noturnoInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do periodo noturno.
    """
    noturno_fim: str | None = Field(
        None, alias="noturnoFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do periodo noturno.
    """
    hora_ficta_noturna: bool | None = Field(None, alias="horaFictaNoturna")
    """
    Aplica a hora ficta urbana de 52 minutos e 30 segundos no periodo noturno.
    """
    prorrogacao_noturna: bool | None = Field(None, alias="prorrogacaoNoturna")
    """
    Mantem o adicional noturno na prorrogacao da jornada iniciada em periodo noturno (Sumula 60, II do TST).
    """
    limite_extra_diario_minutos: int | None = Field(None, alias="limiteExtraDiarioMinutos", ge=0)
    """
    Limite diario de hora extra. Padrao de 120 minutos.
    """
    limite_jornada_diaria_minutos: int | None = Field(
        None, alias="limiteJornadaDiariaMinutos", ge=1
    )
    """
    Limite total da jornada diaria. Padrao de 600 minutos.
    """
    bloqueia_extra_acima_limite: bool | None = Field(None, alias="bloqueiaExtraAcimaLimite")
    """
    Bloqueia registro de extra acima do limite configurado.
    """
    compensa_sabado: bool | None = Field(None, alias="compensaSabado")
    """
    Distribui a carga do sabado nos demais dias uteis.
    """
    fatores_extra: dict[str, Any] | None = Field(None, alias="fatoresExtra")
    """
    Faixas e percentuais de hora extra em JSON, por exemplo primeira e segunda hora a 50 por cento e o excedente a 100 por cento.
    """
    dias: list[JornadaDia] | None = None
    """
    Desdobramento por dia da semana, em jornadas fixas e flexiveis.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia. A jornada e versionada: trocar a regra no meio do mes nao reescreve o passado.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    ativo: bool | None = None
    """
    Jornada ativa.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class JornadaCriar(BaseModel):
    """
    Dados aceitos na criacao de Jornada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que a jornada pertence.
    """
    codigo: str
    """
    Codigo da jornada, unico por empresa e vigencia.
    """
    nome: str
    """
    Nome da jornada.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo14
    """
    Estrategia de resolucao. fixa: horario por dia da semana. flexivel: carga com janela. livre: so carga total. motorista: regras da Lei 13.103.
    """
    carga_diaria_minutos: int | None = Field(None, alias="cargaDiariaMinutos", ge=0, le=1440)
    """
    Carga diaria prevista.
    """
    carga_semanal_minutos: int | None = Field(None, alias="cargaSemanalMinutos", ge=0, le=4200)
    """
    Carga semanal prevista.
    """
    carga_mensal_minutos: int | None = Field(None, alias="cargaMensalMinutos", ge=0)
    """
    Carga mensal prevista.
    """
    tolerancia_marcacao_minutos: int | None = Field(
        None, alias="toleranciaMarcacaoMinutos", ge=0, le=60
    )
    """
    Tolerancia por marcacao. Padrao legal de 5 minutos (art. 58, par. 1 da CLT).
    """
    tolerancia_diaria_minutos: int | None = Field(
        None, alias="toleranciaDiariaMinutos", ge=0, le=120
    )
    """
    Tolerancia acumulada no dia. Padrao legal de 10 minutos.
    """
    descontar_tudo_se_exceder: bool | None = Field(None, alias="descontarTudoSeExceder")
    """
    Quando verdadeiro e a tolerancia diaria estoura, todo o excedente e computado, nao apenas a diferenca.
    """
    janela_flexivel_minutos: int | None = Field(None, alias="janelaFlexivelMinutos", ge=0)
    """
    Janela de flexibilidade de entrada e saida.
    """
    intervalo_automatico: bool | None = Field(None, alias="intervaloAutomatico")
    """
    Pre-assinalacao do intervalo: o sistema assume o intervalo previsto quando nao ha marcacao correspondente.
    """
    intervalo_minimo_minutos: int | None = Field(None, alias="intervaloMinimoMinutos", ge=0)
    """
    Intervalo intrajornada minimo exigido.
    """
    intervalo_flexivel: bool | None = Field(None, alias="intervaloFlexivel")
    """
    Permite intervalo em horario livre dentro da jornada.
    """
    interjornada_minima_minutos: int | None = Field(None, alias="interjornadaMinimaMinutos", ge=0)
    """
    Descanso minimo entre jornadas. Padrao de 660 minutos (11 horas).
    """
    noturno_inicio: str | None = Field(
        None, alias="noturnoInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do periodo noturno.
    """
    noturno_fim: str | None = Field(
        None, alias="noturnoFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do periodo noturno.
    """
    hora_ficta_noturna: bool | None = Field(None, alias="horaFictaNoturna")
    """
    Aplica a hora ficta urbana de 52 minutos e 30 segundos no periodo noturno.
    """
    prorrogacao_noturna: bool | None = Field(None, alias="prorrogacaoNoturna")
    """
    Mantem o adicional noturno na prorrogacao da jornada iniciada em periodo noturno (Sumula 60, II do TST).
    """
    limite_extra_diario_minutos: int | None = Field(None, alias="limiteExtraDiarioMinutos", ge=0)
    """
    Limite diario de hora extra. Padrao de 120 minutos.
    """
    limite_jornada_diaria_minutos: int | None = Field(
        None, alias="limiteJornadaDiariaMinutos", ge=1
    )
    """
    Limite total da jornada diaria. Padrao de 600 minutos.
    """
    bloqueia_extra_acima_limite: bool | None = Field(None, alias="bloqueiaExtraAcimaLimite")
    """
    Bloqueia registro de extra acima do limite configurado.
    """
    compensa_sabado: bool | None = Field(None, alias="compensaSabado")
    """
    Distribui a carga do sabado nos demais dias uteis.
    """
    fatores_extra: dict[str, Any] | None = Field(None, alias="fatoresExtra")
    """
    Faixas e percentuais de hora extra em JSON, por exemplo primeira e segunda hora a 50 por cento e o excedente a 100 por cento.
    """
    dias: list[JornadaDia] | None = None
    """
    Desdobramento por dia da semana, em jornadas fixas e flexiveis.
    """
    vigencia_inicio: date = Field(..., alias="vigenciaInicio")
    """
    Inicio da vigencia. A jornada e versionada: trocar a regra no meio do mes nao reescreve o passado.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    ativo: bool | None = None
    """
    Jornada ativa.
    """


class JornadaAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Jornada. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a jornada pertence.
    """
    codigo: str | None = None
    """
    Codigo da jornada, unico por empresa e vigencia.
    """
    nome: str | None = None
    """
    Nome da jornada.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo14 | None = None
    """
    Estrategia de resolucao. fixa: horario por dia da semana. flexivel: carga com janela. livre: so carga total. motorista: regras da Lei 13.103.
    """
    carga_diaria_minutos: int | None = Field(None, alias="cargaDiariaMinutos", ge=0, le=1440)
    """
    Carga diaria prevista.
    """
    carga_semanal_minutos: int | None = Field(None, alias="cargaSemanalMinutos", ge=0, le=4200)
    """
    Carga semanal prevista.
    """
    carga_mensal_minutos: int | None = Field(None, alias="cargaMensalMinutos", ge=0)
    """
    Carga mensal prevista.
    """
    tolerancia_marcacao_minutos: int | None = Field(
        None, alias="toleranciaMarcacaoMinutos", ge=0, le=60
    )
    """
    Tolerancia por marcacao. Padrao legal de 5 minutos (art. 58, par. 1 da CLT).
    """
    tolerancia_diaria_minutos: int | None = Field(
        None, alias="toleranciaDiariaMinutos", ge=0, le=120
    )
    """
    Tolerancia acumulada no dia. Padrao legal de 10 minutos.
    """
    descontar_tudo_se_exceder: bool | None = Field(None, alias="descontarTudoSeExceder")
    """
    Quando verdadeiro e a tolerancia diaria estoura, todo o excedente e computado, nao apenas a diferenca.
    """
    janela_flexivel_minutos: int | None = Field(None, alias="janelaFlexivelMinutos", ge=0)
    """
    Janela de flexibilidade de entrada e saida.
    """
    intervalo_automatico: bool | None = Field(None, alias="intervaloAutomatico")
    """
    Pre-assinalacao do intervalo: o sistema assume o intervalo previsto quando nao ha marcacao correspondente.
    """
    intervalo_minimo_minutos: int | None = Field(None, alias="intervaloMinimoMinutos", ge=0)
    """
    Intervalo intrajornada minimo exigido.
    """
    intervalo_flexivel: bool | None = Field(None, alias="intervaloFlexivel")
    """
    Permite intervalo em horario livre dentro da jornada.
    """
    interjornada_minima_minutos: int | None = Field(None, alias="interjornadaMinimaMinutos", ge=0)
    """
    Descanso minimo entre jornadas. Padrao de 660 minutos (11 horas).
    """
    noturno_inicio: str | None = Field(
        None, alias="noturnoInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio do periodo noturno.
    """
    noturno_fim: str | None = Field(
        None, alias="noturnoFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Fim do periodo noturno.
    """
    hora_ficta_noturna: bool | None = Field(None, alias="horaFictaNoturna")
    """
    Aplica a hora ficta urbana de 52 minutos e 30 segundos no periodo noturno.
    """
    prorrogacao_noturna: bool | None = Field(None, alias="prorrogacaoNoturna")
    """
    Mantem o adicional noturno na prorrogacao da jornada iniciada em periodo noturno (Sumula 60, II do TST).
    """
    limite_extra_diario_minutos: int | None = Field(None, alias="limiteExtraDiarioMinutos", ge=0)
    """
    Limite diario de hora extra. Padrao de 120 minutos.
    """
    limite_jornada_diaria_minutos: int | None = Field(
        None, alias="limiteJornadaDiariaMinutos", ge=1
    )
    """
    Limite total da jornada diaria. Padrao de 600 minutos.
    """
    bloqueia_extra_acima_limite: bool | None = Field(None, alias="bloqueiaExtraAcimaLimite")
    """
    Bloqueia registro de extra acima do limite configurado.
    """
    compensa_sabado: bool | None = Field(None, alias="compensaSabado")
    """
    Distribui a carga do sabado nos demais dias uteis.
    """
    fatores_extra: dict[str, Any] | None = Field(None, alias="fatoresExtra")
    """
    Faixas e percentuais de hora extra em JSON, por exemplo primeira e segunda hora a 50 por cento e o excedente a 100 por cento.
    """
    dias: list[JornadaDia] | None = None
    """
    Desdobramento por dia da semana, em jornadas fixas e flexiveis.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia. A jornada e versionada: trocar a regra no meio do mes nao reescreve o passado.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    ativo: bool | None = None
    """
    Jornada ativa.
    """


class VinculoJornada(BaseModel):
    """
    Atribuicao datada de jornada a um vinculo. Sem ela nao ha como trocar a jornada no meio do mes preservando a apuracao anterior.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da atribuicao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada atribuida.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    motivo: str | None = None
    """
    Justificativa da troca, exibida no espelho e na auditoria.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class VinculoJornadaCriar(BaseModel):
    """
    Dados aceitos na criacao de VinculoJornada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    jornada_id: UUID = Field(..., alias="jornadaId")
    """
    Jornada atribuida.
    """
    vigencia_inicio: date = Field(..., alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    motivo: str | None = None
    """
    Justificativa da troca, exibida no espelho e na auditoria.
    """


class Tipo17(StrEnum):
    """
    Natureza do turno.
    """

    diurno = "diurno"
    noturno = "noturno"
    misto = "misto"
    folga = "folga"
    dsr = "dsr"
    sobreaviso = "sobreaviso"
    prontidao = "prontidao"


class Turno(BaseModel):
    """
    Turno nomeado, com o horario que o materializa. Em revezamento, a sequencia define a ordem de rodizio.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do turno.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o turno pertence.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario que materializa o turno.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do turno.
    """
    tipo: Tipo17 | None = None
    """
    Natureza do turno.
    """
    sequencia: int | None = None
    """
    Posicao no revezamento. Ausente em turnos fixos.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Turno ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class TurnoCriar(BaseModel):
    """
    Dados aceitos na criacao de Turno.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que o turno pertence.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario que materializa o turno.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome do turno.
    """
    tipo: Tipo17 | None = None
    """
    Natureza do turno.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Turno ativo.
    """


class TurnoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Turno. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que o turno pertence.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario que materializa o turno.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome do turno.
    """
    tipo: Tipo17 | None = None
    """
    Natureza do turno.
    """
    cor: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    """
    Cor em hexadecimal usada na grade de escala.
    """
    ativo: bool | None = None
    """
    Turno ativo.
    """


class TipoDia1(StrEnum):
    """
    Natureza do dia nesta posicao.
    """

    trabalho = "trabalho"
    folga = "folga"
    dsr = "dsr"
    compensado = "compensado"


class EscalaCiclo(BaseModel):
    """
    Uma posicao do ciclo da escala. Em 12x36 sao duas linhas: posicao 1 trabalho de 12 horas, posicao 2 folga.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da posicao.
    """
    posicao: int | None = Field(None, ge=1)
    """
    Posicao dentro do ciclo, de 1 ate diasCiclo.
    """
    turno_id: UUID | None = Field(None, alias="turnoId")
    """
    Turno aplicado nesta posicao.
    """
    tipo_dia: TipoDia1 | None = Field(None, alias="tipoDia")
    """
    Natureza do dia nesta posicao.
    """
    carga_minutos: int | None = Field(None, alias="cargaMinutos", ge=0, le=1440)
    """
    Carga prevista nesta posicao.
    """


class Tipo20(StrEnum):
    """
    Padrao da escala.
    """

    field_5x2 = "5x2"
    field_6x1 = "6x1"
    field_4x2 = "4x2"
    field_12x36 = "12x36"
    espanhola = "espanhola"
    rotativa = "rotativa"
    personalizada = "personalizada"


class Escala(BaseModel):
    """
    Padrao ciclico de trabalho e folga. O ciclo se repete a partir de dataReferencia e qualquer data e resolvida por aritmetica modular, sem materializar o calendario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da escala.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a escala pertence.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada associada, que traz as regras de calculo.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome da escala.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo20 | None = None
    """
    Padrao da escala.
    """
    dias_ciclo: int | None = Field(None, alias="diasCiclo", ge=1, le=366)
    """
    Tamanho do ciclo em dias. 7 para 5x2 e 6x1, 2 para 12x36, 6 para 4x2.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Ancora do ciclo: data em que a escala esta na posicao 1.
    """
    ciclos: list[EscalaCiclo] | None = None
    """
    Composicao do ciclo, uma entrada por posicao.
    """
    ativo: bool | None = None
    """
    Escala ativa.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class EscalaCriar(BaseModel):
    """
    Dados aceitos na criacao de Escala.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que a escala pertence.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada associada, que traz as regras de calculo.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome da escala.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo20
    """
    Padrao da escala.
    """
    dias_ciclo: int = Field(..., alias="diasCiclo", ge=1, le=366)
    """
    Tamanho do ciclo em dias. 7 para 5x2 e 6x1, 2 para 12x36, 6 para 4x2.
    """
    data_referencia: date = Field(..., alias="dataReferencia")
    """
    Ancora do ciclo: data em que a escala esta na posicao 1.
    """
    ciclos: list[EscalaCiclo] | None = None
    """
    Composicao do ciclo, uma entrada por posicao.
    """
    ativo: bool | None = None
    """
    Escala ativa.
    """


class EscalaAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Escala. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a escala pertence.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada associada, que traz as regras de calculo.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome da escala.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    tipo: Tipo20 | None = None
    """
    Padrao da escala.
    """
    dias_ciclo: int | None = Field(None, alias="diasCiclo", ge=1, le=366)
    """
    Tamanho do ciclo em dias. 7 para 5x2 e 6x1, 2 para 12x36, 6 para 4x2.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Ancora do ciclo: data em que a escala esta na posicao 1.
    """
    ciclos: list[EscalaCiclo] | None = None
    """
    Composicao do ciclo, uma entrada por posicao.
    """
    ativo: bool | None = None
    """
    Escala ativa.
    """


class EscalaAtribuicao(BaseModel):
    """
    Atribuicao datada de uma escala a um vinculo. Um vinculo tem no maximo uma escala vigente por data.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da atribuicao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    escala_id: UUID | None = Field(None, alias="escalaId")
    """
    Escala atribuida.
    """
    posicao_inicial: int | None = Field(None, alias="posicaoInicial", ge=1)
    """
    Posicao do ciclo em que o vinculo entra na vigencia. Permite equipes desencontradas na mesma escala.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    motivo: str | None = None
    """
    Justificativa da atribuicao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class EscalaAtribuicaoCriar(BaseModel):
    """
    Dados aceitos na criacao de EscalaAtribuicao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    vinculo_id: UUID = Field(..., alias="vinculoId")
    """
    Vinculo alvo.
    """
    escala_id: UUID | None = Field(None, alias="escalaId")
    """
    Escala atribuida.
    """
    posicao_inicial: int | None = Field(None, alias="posicaoInicial", ge=1)
    """
    Posicao do ciclo em que o vinculo entra na vigencia. Permite equipes desencontradas na mesma escala.
    """
    vigencia_inicio: date = Field(..., alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """
    motivo: str | None = None
    """
    Justificativa da atribuicao.
    """


class Abrangencia(StrEnum):
    """
    Alcance do conjunto.
    """

    nacional = "nacional"
    estadual = "estadual"
    municipal = "municipal"
    empresa = "empresa"
    unidade = "unidade"


class FeriadoConjunto(BaseModel):
    """
    Agrupamento de feriados por abrangencia. A unidade combina varios conjuntos (nacional, estadual e municipal).
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do conjunto.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do conjunto.
    """
    abrangencia: Abrangencia | None = None
    """
    Alcance do conjunto.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    UF do conjunto estadual.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio do conjunto municipal.
    """
    unidade_ids: list[UUID] | None = Field(None, alias="unidadeIds")
    """
    Unidades que aplicam este conjunto.
    """
    ativo: bool | None = None
    """
    Conjunto ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class FeriadoConjuntoCriar(BaseModel):
    """
    Dados aceitos na criacao de FeriadoConjunto.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str
    """
    Codigo unico por tenant.
    """
    nome: str
    """
    Nome do conjunto.
    """
    abrangencia: Abrangencia
    """
    Alcance do conjunto.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    UF do conjunto estadual.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio do conjunto municipal.
    """
    unidade_ids: list[UUID] | None = Field(None, alias="unidadeIds")
    """
    Unidades que aplicam este conjunto.
    """
    ativo: bool | None = None
    """
    Conjunto ativo.
    """


class FeriadoConjuntoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de FeriadoConjunto. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do conjunto.
    """
    abrangencia: Abrangencia | None = None
    """
    Alcance do conjunto.
    """
    uf: str | None = Field(None, pattern="^[A-Z]{2}$")
    """
    UF do conjunto estadual.
    """
    codigo_ibge_municipio: str | None = Field(
        None, alias="codigoIbgeMunicipio", pattern="^[0-9]{7}$"
    )
    """
    Codigo IBGE do municipio do conjunto municipal.
    """
    unidade_ids: list[UUID] | None = Field(None, alias="unidadeIds")
    """
    Unidades que aplicam este conjunto.
    """
    ativo: bool | None = None
    """
    Conjunto ativo.
    """


class Tipo23(StrEnum):
    """
    Natureza da data.
    """

    feriado = "feriado"
    ponto_facultativo = "ponto_facultativo"
    data_comemorativa = "data_comemorativa"
    compensado = "compensado"


class RegraMovel(StrEnum):
    """
    Ancora do calculo do feriado movel.
    """

    pascoa = "pascoa"
    carnaval = "carnaval"
    sexta_santa = "sexta_santa"
    corpus_christi = "corpus_christi"
    quarta_cinzas = "quarta_cinzas"
    custom = "custom"


class Feriado(BaseModel):
    """
    Feriado, ponto facultativo ou expediente reduzido. Feriados moveis nao guardam data: sao calculados por regra a partir da Pascoa do ano de referencia.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do feriado.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    feriado_conjunto_id: UUID | None = Field(None, alias="feriadoConjuntoId")
    """
    Conjunto a que o feriado pertence.
    """
    nome: str | None = None
    """
    Nome do feriado.
    """
    data: date | None = None
    """
    Data fixa do feriado. Ausente em feriados moveis.
    """
    ano: int | None = Field(None, ge=1900, le=2200)
    """
    Ano de aplicacao para feriados fixos pontuais. Ausente repete todo ano.
    """
    tipo: Tipo23 | None = None
    """
    Natureza da data.
    """
    movel: bool | None = None
    """
    Verdadeiro para datas que mudam a cada ano.
    """
    regra_movel: RegraMovel | None = Field(None, alias="regraMovel")
    """
    Ancora do calculo do feriado movel.
    """
    offset_dias: int | None = Field(None, alias="offsetDias")
    """
    Dias somados a ancora para chegar na data efetiva.
    """
    integral: bool | None = None
    """
    Falso indica expediente reduzido.
    """
    carga_reduzida_minutos: int | None = Field(None, alias="cargaReduzidaMinutos", ge=0)
    """
    Carga do dia quando o expediente e reduzido.
    """
    data_resolvida: date | None = Field(None, alias="dataResolvida")
    """
    Data efetiva no ano consultado, ja calculada para feriados moveis.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class FeriadoCriar(BaseModel):
    """
    Dados aceitos na criacao de Feriado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    feriado_conjunto_id: UUID = Field(..., alias="feriadoConjuntoId")
    """
    Conjunto a que o feriado pertence.
    """
    nome: str
    """
    Nome do feriado.
    """
    data: date | None = None
    """
    Data fixa do feriado. Ausente em feriados moveis.
    """
    ano: int | None = Field(None, ge=1900, le=2200)
    """
    Ano de aplicacao para feriados fixos pontuais. Ausente repete todo ano.
    """
    tipo: Tipo23 | None = None
    """
    Natureza da data.
    """
    movel: bool | None = None
    """
    Verdadeiro para datas que mudam a cada ano.
    """
    regra_movel: RegraMovel | None = Field(None, alias="regraMovel")
    """
    Ancora do calculo do feriado movel.
    """
    offset_dias: int | None = Field(None, alias="offsetDias")
    """
    Dias somados a ancora para chegar na data efetiva.
    """
    integral: bool | None = None
    """
    Falso indica expediente reduzido.
    """
    carga_reduzida_minutos: int | None = Field(None, alias="cargaReduzidaMinutos", ge=0)
    """
    Carga do dia quando o expediente e reduzido.
    """


class Categoria2(StrEnum):
    """
    Categoria legal do afastamento.
    """

    ferias = "ferias"
    atestado = "atestado"
    licenca_maternidade = "licenca_maternidade"
    licenca_paternidade = "licenca_paternidade"
    inss = "inss"
    acidente_trabalho = "acidente_trabalho"
    suspensao = "suspensao"
    falta_justificada = "falta_justificada"
    falta_injustificada = "falta_injustificada"
    servico_militar = "servico_militar"
    doacao_sangue = "doacao_sangue"
    casamento = "casamento"
    obito = "obito"
    treinamento = "treinamento"
    licenca_nao_remunerada = "licenca_nao_remunerada"
    outro = "outro"


class TipoAfastamento(BaseModel):
    """
    Catalogo configuravel de motivos de ausencia e o efeito de cada um no calculo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do tipo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do tipo de afastamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria2 | None = None
    """
    Categoria legal do afastamento.
    """
    codigo_esocial: str | None = Field(None, alias="codigoEsocial")
    """
    Codigo do motivo na tabela do eSocial, exportado no AEJ.
    """
    abona_dia: bool | None = Field(None, alias="abonaDia")
    """
    Quando verdadeiro, o dia nao gera falta nem debito de carga.
    """
    remunerado: bool | None = None
    """
    Indica se o periodo e remunerado.
    """
    computa_carga: bool | None = Field(None, alias="computaCarga")
    """
    Quando verdadeiro, o afastamento gera horas na apuracao como se trabalhadas (caso de treinamento externo).
    """
    computa_dsr: bool | None = Field(None, alias="computaDsr")
    """
    Falso faz o afastamento derrubar o DSR da semana, como na falta injustificada.
    """
    suspende_contrato: bool | None = Field(None, alias="suspendeContrato")
    """
    Indica suspensao do contrato de trabalho.
    """
    exige_documento: bool | None = Field(None, alias="exigeDocumento")
    """
    Exige anexo comprobatorio.
    """
    limite_dias: int | None = Field(None, alias="limiteDias", ge=1)
    """
    Limite legal de dias, quando houver.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class TipoAfastamentoCriar(BaseModel):
    """
    Dados aceitos na criacao de TipoAfastamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str
    """
    Codigo unico por tenant.
    """
    nome: str
    """
    Nome do tipo de afastamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria2
    """
    Categoria legal do afastamento.
    """
    codigo_esocial: str | None = Field(None, alias="codigoEsocial")
    """
    Codigo do motivo na tabela do eSocial, exportado no AEJ.
    """
    abona_dia: bool | None = Field(None, alias="abonaDia")
    """
    Quando verdadeiro, o dia nao gera falta nem debito de carga.
    """
    remunerado: bool | None = None
    """
    Indica se o periodo e remunerado.
    """
    computa_carga: bool | None = Field(None, alias="computaCarga")
    """
    Quando verdadeiro, o afastamento gera horas na apuracao como se trabalhadas (caso de treinamento externo).
    """
    computa_dsr: bool | None = Field(None, alias="computaDsr")
    """
    Falso faz o afastamento derrubar o DSR da semana, como na falta injustificada.
    """
    suspende_contrato: bool | None = Field(None, alias="suspendeContrato")
    """
    Indica suspensao do contrato de trabalho.
    """
    exige_documento: bool | None = Field(None, alias="exigeDocumento")
    """
    Exige anexo comprobatorio.
    """
    limite_dias: int | None = Field(None, alias="limiteDias", ge=1)
    """
    Limite legal de dias, quando houver.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """


class TipoAfastamentoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de TipoAfastamento. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do tipo de afastamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria2 | None = None
    """
    Categoria legal do afastamento.
    """
    codigo_esocial: str | None = Field(None, alias="codigoEsocial")
    """
    Codigo do motivo na tabela do eSocial, exportado no AEJ.
    """
    abona_dia: bool | None = Field(None, alias="abonaDia")
    """
    Quando verdadeiro, o dia nao gera falta nem debito de carga.
    """
    remunerado: bool | None = None
    """
    Indica se o periodo e remunerado.
    """
    computa_carga: bool | None = Field(None, alias="computaCarga")
    """
    Quando verdadeiro, o afastamento gera horas na apuracao como se trabalhadas (caso de treinamento externo).
    """
    computa_dsr: bool | None = Field(None, alias="computaDsr")
    """
    Falso faz o afastamento derrubar o DSR da semana, como na falta injustificada.
    """
    suspende_contrato: bool | None = Field(None, alias="suspendeContrato")
    """
    Indica suspensao do contrato de trabalho.
    """
    exige_documento: bool | None = Field(None, alias="exigeDocumento")
    """
    Exige anexo comprobatorio.
    """
    limite_dias: int | None = Field(None, alias="limiteDias", ge=1)
    """
    Limite legal de dias, quando houver.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """


class Origem(StrEnum):
    """
    Como o afastamento entrou no sistema.
    """

    manual = "manual"
    solicitacao = "solicitacao"
    integracao = "integracao"
    importacao = "importacao"


class Status19(StrEnum):
    """
    Situacao do afastamento.
    """

    solicitado = "solicitado"
    aprovado = "aprovado"
    reprovado = "reprovado"
    cancelado = "cancelado"
    encerrado = "encerrado"


class Afastamento(BaseModel):
    """
    Periodo de ausencia legitima do colaborador. Entra na apuracao como insumo, nunca como marcacao, e e exportado no bloco de ausencias do AEJ.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do afastamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador afastado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo afetado.
    """
    tipo_afastamento_id: UUID | None = Field(None, alias="tipoAfastamentoId")
    """
    Tipo de afastamento aplicado.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Primeiro dia do afastamento.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do afastamento. Ausente indica afastamento em aberto.
    """
    periodo_parcial: bool | None = Field(None, alias="periodoParcial")
    """
    Verdadeiro para ausencia de algumas horas do dia.
    """
    hora_inicio: str | None = Field(
        None, alias="horaInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio da ausencia parcial.
    """
    hora_fim: str | None = Field(None, alias="horaFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Fim da ausencia parcial.
    """
    motivo: str | None = None
    """
    Motivo informado.
    """
    cid: str | None = None
    """
    Codigo CID do atestado. Dado de saude: a leitura sempre gera registro de acesso a dado sensivel.
    """
    dias_previstos: int | None = Field(None, alias="diasPrevistos")
    """
    Dias previstos de afastamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o afastamento.
    """
    origem: Origem | None = None
    """
    Como o afastamento entrou no sistema.
    """
    status: Status19 | None = None
    """
    Situacao do afastamento.
    """
    aprovado_por: UUID | None = Field(None, alias="aprovadoPor")
    """
    Usuario que aprovou.
    """
    aprovado_em: AwareDatetime | None = Field(None, alias="aprovadoEm")
    """
    Instante da aprovacao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class AfastamentoCriar(BaseModel):
    """
    Dados aceitos na criacao de Afastamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador afastado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo afetado.
    """
    tipo_afastamento_id: UUID = Field(..., alias="tipoAfastamentoId")
    """
    Tipo de afastamento aplicado.
    """
    data_inicio: date = Field(..., alias="dataInicio")
    """
    Primeiro dia do afastamento.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do afastamento. Ausente indica afastamento em aberto.
    """
    periodo_parcial: bool | None = Field(None, alias="periodoParcial")
    """
    Verdadeiro para ausencia de algumas horas do dia.
    """
    hora_inicio: str | None = Field(
        None, alias="horaInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio da ausencia parcial.
    """
    hora_fim: str | None = Field(None, alias="horaFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Fim da ausencia parcial.
    """
    motivo: str | None = None
    """
    Motivo informado.
    """
    cid: str | None = None
    """
    Codigo CID do atestado. Dado de saude: a leitura sempre gera registro de acesso a dado sensivel.
    """
    dias_previstos: int | None = Field(None, alias="diasPrevistos")
    """
    Dias previstos de afastamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o afastamento.
    """
    origem: Origem | None = None
    """
    Como o afastamento entrou no sistema.
    """
    status: Status19 | None = None
    """
    Situacao do afastamento.
    """


class AfastamentoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Afastamento. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador afastado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo afetado.
    """
    tipo_afastamento_id: UUID | None = Field(None, alias="tipoAfastamentoId")
    """
    Tipo de afastamento aplicado.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Primeiro dia do afastamento.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do afastamento. Ausente indica afastamento em aberto.
    """
    periodo_parcial: bool | None = Field(None, alias="periodoParcial")
    """
    Verdadeiro para ausencia de algumas horas do dia.
    """
    hora_inicio: str | None = Field(
        None, alias="horaInicio", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Inicio da ausencia parcial.
    """
    hora_fim: str | None = Field(None, alias="horaFim", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    """
    Fim da ausencia parcial.
    """
    motivo: str | None = None
    """
    Motivo informado.
    """
    cid: str | None = None
    """
    Codigo CID do atestado. Dado de saude: a leitura sempre gera registro de acesso a dado sensivel.
    """
    dias_previstos: int | None = Field(None, alias="diasPrevistos")
    """
    Dias previstos de afastamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o afastamento.
    """
    origem: Origem | None = None
    """
    Como o afastamento entrou no sistema.
    """
    status: Status19 | None = None
    """
    Situacao do afastamento.
    """


class Tipo25(StrEnum):
    """
    Tipo de registrador. rep_p e o programa de registro de ponto.
    """

    rep_p = "rep_p"
    rep_c = "rep_c"
    rep_a = "rep_a"


class Status22(StrEnum):
    """
    Situacao do REP-P.
    """

    ativo = "ativo"
    inativo = "inativo"
    substituido = "substituido"


class RepP(BaseModel):
    """
    Instancia de REP-P em operacao. O REP-P e o nosso software, nao o terminal. Cada um tem sua propria sequencia de NSR e seus proprios arquivos AFD.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do REP-P.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa que opera este REP-P.
    """
    identificador: str | None = None
    """
    Codigo interno do REP-P, unico por empresa.
    """
    tipo: Tipo25 | None = None
    """
    Tipo de registrador. rep_p e o programa de registro de ponto.
    """
    numero_inpi: str | None = Field(None, alias="numeroInpi", pattern="^[0-9]+$")
    """
    Numero do registro do programa no INPI, SOMENTE DIGITOS. Vai no cabecalho do AFD.
    """
    cnpj_desenvolvedor: str | None = Field(None, alias="cnpjDesenvolvedor", pattern="^[0-9]{14}$")
    """
    CNPJ do desenvolvedor do programa.
    """
    razao_social_desenvolvedor: str | None = Field(None, alias="razaoSocialDesenvolvedor")
    """
    Razao social do desenvolvedor.
    """
    cnpj_empregador: str | None = Field(None, alias="cnpjEmpregador", pattern="^[0-9]{14}$")
    """
    CNPJ da empresa empregadora que opera este REP-P.
    """
    razao_social_empregador: str | None = Field(None, alias="razaoSocialEmpregador")
    """
    Razao social do empregador.
    """
    cei_caepf: str | None = Field(None, alias="ceiCaepf")
    """
    CEI ou CAEPF, quando aplicavel.
    """
    versao_programa: str | None = Field(None, alias="versaoPrograma")
    """
    Versao do programa em operacao. Trocar de versao nao reinicia o NSR.
    """
    data_inicio_operacao: date | None = Field(None, alias="dataInicioOperacao")
    """
    Inicio da operacao do REP-P.
    """
    data_fim_operacao: date | None = Field(None, alias="dataFimOperacao")
    """
    Fim da operacao do REP-P.
    """
    proximo_nsr: int | None = Field(None, alias="proximoNsr")
    """
    Proximo NSR a ser entregue. Comeca em 1 e nunca e reiniciado, nem na virada de ano, nem na troca de versao. Projecao somente leitura do alocador transacional (tabela nsr_sequencias).
    """
    ultimo_nsr_emitido: int | None = Field(None, alias="ultimoNsrEmitido")
    """
    Ultimo NSR emitido por este REP-P. Projecao somente leitura do alocador transacional (tabela nsr_sequencias).
    """
    status: Status22 | None = None
    """
    Situacao do REP-P.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class RepPCriar(BaseModel):
    """
    Dados aceitos na criacao de RepP.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa que opera este REP-P.
    """
    identificador: str
    """
    Codigo interno do REP-P, unico por empresa.
    """
    tipo: Tipo25 | None = None
    """
    Tipo de registrador. rep_p e o programa de registro de ponto.
    """
    numero_inpi: str = Field(..., alias="numeroInpi", pattern="^[0-9]+$")
    """
    Numero do registro do programa no INPI, SOMENTE DIGITOS. Vai no cabecalho do AFD.
    """
    cnpj_desenvolvedor: str | None = Field(None, alias="cnpjDesenvolvedor", pattern="^[0-9]{14}$")
    """
    CNPJ do desenvolvedor do programa.
    """
    razao_social_desenvolvedor: str | None = Field(None, alias="razaoSocialDesenvolvedor")
    """
    Razao social do desenvolvedor.
    """
    cnpj_empregador: str = Field(..., alias="cnpjEmpregador", pattern="^[0-9]{14}$")
    """
    CNPJ da empresa empregadora que opera este REP-P.
    """
    razao_social_empregador: str = Field(..., alias="razaoSocialEmpregador")
    """
    Razao social do empregador.
    """
    cei_caepf: str | None = Field(None, alias="ceiCaepf")
    """
    CEI ou CAEPF, quando aplicavel.
    """
    versao_programa: str = Field(..., alias="versaoPrograma")
    """
    Versao do programa em operacao. Trocar de versao nao reinicia o NSR.
    """
    data_inicio_operacao: date = Field(..., alias="dataInicioOperacao")
    """
    Inicio da operacao do REP-P.
    """
    data_fim_operacao: date | None = Field(None, alias="dataFimOperacao")
    """
    Fim da operacao do REP-P.
    """
    status: Status22 | None = None
    """
    Situacao do REP-P.
    """


class TipoRegistro(StrEnum):
    """
    Tipo do registro no leiaute do AFD. 7 e a marcacao de ponto do REP-P; os demais existem para importacao de AFD de terceiros.
    """

    field_2 = "2"
    field_3 = "3"
    field_4 = "4"
    field_5 = "5"
    field_6 = "6"
    field_7 = "7"
    field_9 = "9"


class SentidoInformado(StrEnum):
    """
    Sentido QUANDO o coletor informa. O pareamento definitivo e feito na apuracao; nunca e inferido na gravacao.
    """

    entrada = "entrada"
    saida = "saida"
    indefinido = "indefinido"


class Canal2(StrEnum):
    """
    Canal de origem da marcacao.
    """

    terminal = "terminal"
    mobile = "mobile"
    web = "web"
    totem = "totem"
    api = "api"
    importacao = "importacao"


class Marcacao(BaseModel):
    """
    Registro de ponto. IMUTAVEL e append-only: nao existe operacao de alteracao nem de exclusao. Correcao vive em tratamentos.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da marcacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P que atribuiu o NSR.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do registro.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de origem.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador identificado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo ao qual a marcacao sera apurada.
    """
    nsr: int | None = Field(None, ge=1)
    """
    Numero Sequencial de Registro atribuido pelo servidor, por REP-P, comecando em 1 e sem lacunas.
    """
    tipo_registro: TipoRegistro | None = Field(None, alias="tipoRegistro")
    """
    Tipo do registro no leiaute do AFD. 7 e a marcacao de ponto do REP-P; os demais existem para importacao de AFD de terceiros.
    """
    sentido_informado: SentidoInformado | None = Field(None, alias="sentidoInformado")
    """
    Sentido QUANDO o coletor informa. O pareamento definitivo e feito na apuracao; nunca e inferido na gravacao.
    """
    cpf: str | None = Field(None, pattern="^[0-9]{11}$")
    """
    CPF do trabalhador congelado no registro. Vai literalmente para o registro tipo 7 do AFD.
    """
    pis_nit: str | None = Field(None, alias="pisNit", pattern="^[0-9]{11}$")
    """
    PIS ou NIT congelado no registro.
    """
    datahora_marcacao: AwareDatetime | None = Field(None, alias="datahoraMarcacao")
    """
    Momento do FATO, no relogio do servidor. E o horario que aparece no AFD e no espelho.
    """
    datahora_gravacao: AwareDatetime | None = Field(None, alias="datahoraGravacao")
    """
    Momento em que o servidor persistiu o registro.
    """
    datahora_dispositivo: AwareDatetime | None = Field(None, alias="datahoraDispositivo")
    """
    Relogio do aparelho no momento da captura. Guardado apenas como evidencia.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso aplicado na interpretacao do registro.
    """
    canal: Canal2 | None = None
    """
    Canal de origem da marcacao.
    """
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo que originou o registro.
    """
    terminal_id: UUID | None = Field(None, alias="terminalId")
    """
    Terminal coletor, quando o canal e terminal.
    """
    external_id: str | None = Field(None, alias="externalId")
    """
    Chave de idempotencia informada pelo integrador no canal api.
    """
    log_externo_id: int | None = Field(None, alias="logExternoId")
    """
    Identificador do registro de acesso no terminal, usado no catch-up.
    """
    crc16: int | None = Field(None, ge=0, le=65535)
    """
    CRC-16 do registro conforme o leiaute do AFD, calculado na gravacao e congelado.
    """
    hash_anterior: str | None = Field(None, alias="hashAnterior", pattern="^[0-9a-f]{64}$")
    """
    Hash do registro anterior do mesmo REP-P. Forma a cadeia de integridade.
    """
    hash_registro: str | None = Field(None, alias="hashRegistro", pattern="^[0-9a-f]{64}$")
    """
    SHA-256 do conteudo canonico do registro concatenado com hashAnterior.
    """
    linha_afd: str | None = Field(None, alias="linhaAfd")
    """
    Linha exatamente como sera escrita no AFD, congelada na gravacao. Garante que o arquivo gerado hoje seja identico ao gerado daqui a cinco anos.
    """
    coletada_offline: bool | None = Field(None, alias="coletadaOffline")
    """
    Verdadeiro quando o registro chegou por fila offline. O sistema NUNCA finge que foi online.
    """
    comprovante_id: UUID | None = Field(None, alias="comprovanteId")
    """
    Comprovante emitido para esta marcacao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario ou cliente que originou o registro.
    """


class LivenessMetodo(StrEnum):
    """
    Metodo de prova de vida aplicado.
    """

    desafio_ativo = "desafio_ativo"
    passivo = "passivo"
    hibrido = "hibrido"
    nao_aplicavel = "nao_aplicavel"


class ClassificacaoConfianca(StrEnum):
    """
    Faixa resultante da comparacao com os limiares da politica de registro.
    """

    alta = "alta"
    media = "media"
    baixa = "baixa"
    bloqueada = "bloqueada"


class AttestationVeredito(StrEnum):
    """
    Veredito de Play Integrity ou App Attest verificado no servidor.
    """

    aprovado = "aprovado"
    reprovado = "reprovado"
    indisponivel = "indisponivel"
    nao_aplicavel = "nao_aplicavel"


class RevisaoStatus(StrEnum):
    """
    Fila de revisao do gestor. A revisao NAO altera a marcacao: no maximo gera um tratamento.
    """

    nao_requer = "nao_requer"
    pendente = "pendente"
    aprovada = "aprovada"
    rejeitada = "rejeitada"


class MarcacaoMeta(BaseModel):
    """
    Contexto e evidencia antifraude da marcacao. Separada do nucleo legal para manter a marcacao enxuta e imutavel, e para permitir revisao do risco sem tocar no registro legal.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do contexto.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao a que o contexto pertence.
    """
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    """
    Latitude informada na captura.
    """
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    """
    Longitude informada na captura.
    """
    precisao_metros: float | None = Field(None, alias="precisaoMetros", ge=0.0)
    """
    Precisao do sinal de localizacao, em metros.
    """
    altitude: float | None = None
    """
    Altitude informada, em metros.
    """
    endereco_aproximado: str | None = Field(None, alias="enderecoAproximado")
    """
    Endereco aproximado resolvido a partir da posicao.
    """
    unidade_geocerca_id: UUID | None = Field(None, alias="unidadeGeocercaId")
    """
    Unidade cuja geocerca foi avaliada.
    """
    dentro_geocerca: bool | None = Field(None, alias="dentroGeocerca")
    """
    Resultado da avaliacao da geocerca. Ausente quando a unidade nao tem geocerca configurada.
    """
    distancia_geocerca_metros: float | None = Field(None, alias="distanciaGeocercaMetros")
    """
    Distancia ate a borda da geocerca, em metros.
    """
    foto_ref: str | None = Field(None, alias="fotoRef")
    """
    Chave da foto de captura. Sujeita a retencao curta, diferente da marcacao.
    """
    score_facial: float | None = Field(None, alias="scoreFacial", ge=0.0, le=100.0)
    """
    Similaridade retornada pelo servico facial, de 0 a 100.
    """
    limiar_facial: float | None = Field(None, alias="limiarFacial", ge=0.0, le=100.0)
    """
    Limiar vigente na empresa no momento da captura.
    """
    versao_modelo_facial: str | None = Field(None, alias="versaoModeloFacial")
    """
    Versao do modelo facial usado na comparacao.
    """
    liveness_aprovado: bool | None = Field(None, alias="livenessAprovado")
    """
    Resultado da prova de vida.
    """
    liveness_metodo: LivenessMetodo | None = Field(None, alias="livenessMetodo")
    """
    Metodo de prova de vida aplicado.
    """
    score_confianca: int | None = Field(None, alias="scoreConfianca", ge=0, le=100)
    """
    Score de confianca composto, de 0 a 100, calculado no servidor.
    """
    classificacao_confianca: ClassificacaoConfianca | None = Field(
        None, alias="classificacaoConfianca"
    )
    """
    Faixa resultante da comparacao com os limiares da politica de registro.
    """
    flags_integridade: dict[str, Any] | None = Field(None, alias="flagsIntegridade")
    """
    Mapa completo dos sinais brutos coletados pelo cliente.
    """
    attestation_veredito: AttestationVeredito | None = Field(None, alias="attestationVeredito")
    """
    Veredito de Play Integrity ou App Attest verificado no servidor.
    """
    root_detectado: bool | None = Field(None, alias="rootDetectado")
    """
    Root ou jailbreak detectado na captura.
    """
    emulador_detectado: bool | None = Field(None, alias="emuladorDetectado")
    """
    Execucao em emulador detectada na captura.
    """
    modo_desenvolvedor: bool | None = Field(None, alias="modoDesenvolvedor")
    """
    Opcoes do desenvolvedor ativas na captura.
    """
    mock_location: bool | None = Field(None, alias="mockLocation")
    """
    Localizacao simulada detectada na captura.
    """
    camera_virtual: bool | None = Field(None, alias="cameraVirtual")
    """
    Camera virtual detectada na captura.
    """
    velocidade_desde_ultima_kmh: float | None = Field(None, alias="velocidadeDesdeUltimaKmh")
    """
    Velocidade implicita entre esta marcacao e a anterior do mesmo colaborador. Valor absurdo denuncia deslocamento impossivel.
    """
    wifi_bssid: str | None = Field(None, alias="wifiBssid")
    """
    BSSID do ponto de acesso, usado para corroborar o GPS.
    """
    ip: str | None = None
    """
    Endereco IP de origem.
    """
    asn: str | None = None
    """
    ASN do endereco de origem.
    """
    pais: str | None = None
    """
    Pais resolvido a partir do endereco de origem.
    """
    revisao_status: RevisaoStatus | None = Field(None, alias="revisaoStatus")
    """
    Fila de revisao do gestor. A revisao NAO altera a marcacao: no maximo gera um tratamento.
    """
    revisado_por: UUID | None = Field(None, alias="revisadoPor")
    """
    Usuario que revisou.
    """
    revisado_em: AwareDatetime | None = Field(None, alias="revisadoEm")
    """
    Instante da revisao.
    """
    revisao_observacao: str | None = Field(None, alias="revisaoObservacao")
    """
    Observacao do revisor.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class CanalEntrega(StrEnum):
    """
    Canal por onde o comprovante foi disponibilizado.
    """

    app = "app"
    web = "web"
    email = "email"
    impresso = "impresso"
    api = "api"
    terminal = "terminal"


class Comprovante(BaseModel):
    """
    Comprovante de registro emitido a cada marcacao. Append-only. A impressao no momento da marcacao e dispensada porque garantimos acesso eletronico permanente, com as ultimas 48 horas sempre disponiveis.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do comprovante.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao correspondente.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador do registro.
    """
    cpf: str | None = Field(None, pattern="^[0-9]{11}$")
    """
    CPF impresso no comprovante.
    """
    numero: str | None = None
    """
    Numero do comprovante, unico no tenant.
    """
    nsr: int | None = None
    """
    NSR da marcacao.
    """
    datahora_marcacao: AwareDatetime | None = Field(None, alias="datahoraMarcacao")
    """
    Momento do fato registrado.
    """
    conteudo_texto: str | None = Field(None, alias="conteudoTexto")
    """
    Corpo textual do comprovante conforme o leiaute da Portaria, congelado na emissao.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do PDF no armazenamento de objetos.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    Hash do conteudo do comprovante.
    """
    assinatura_ref: str | None = Field(None, alias="assinaturaRef")
    """
    Chave do arquivo .p7s de assinatura CAdES, quando ja emitido com certificado.
    """
    emitido_em: AwareDatetime | None = Field(None, alias="emitidoEm")
    """
    Instante da emissao.
    """
    disponivel_ate: AwareDatetime | None = Field(None, alias="disponivelAte")
    """
    Limite do acesso garantido. Ausente significa disponibilidade permanente, que e o padrao do produto; a exigencia legal minima e de 48 horas.
    """
    canal_entrega: CanalEntrega | None = Field(None, alias="canalEntrega")
    """
    Canal por onde o comprovante foi disponibilizado.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Categoria5(StrEnum):
    """
    Categoria do tratamento. inclusao_marcacao e o lancamento manual do RH ou gestor: aparece no espelho identificado como manual e vai para o AEJ, jamais para o AFD.
    """

    inclusao_marcacao = "inclusao_marcacao"
    desconsideracao_marcacao = "desconsideracao_marcacao"
    ajuste_intervalo = "ajuste_intervalo"
    abono = "abono"
    justificativa = "justificativa"
    afastamento = "afastamento"
    compensacao = "compensacao"
    ajuste_saldo = "ajuste_saldo"


class TipoTratamento(BaseModel):
    """
    Catalogo configuravel de tipos de tratamento. Tratamento e a UNICA forma de corrigir a jornada, e ele nunca altera a marcacao: soma-se a ela na apuracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do tipo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do tipo de tratamento.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria5 | None = None
    """
    Categoria do tratamento. inclusao_marcacao e o lancamento manual do RH ou gestor: aparece no espelho identificado como manual e vai para o AEJ, jamais para o AFD.
    """
    exige_aprovacao: bool | None = Field(None, alias="exigeAprovacao")
    """
    Exige passar pela cadeia de aprovacao.
    """
    exige_anexo: bool | None = Field(None, alias="exigeAnexo")
    """
    Exige documento comprobatorio.
    """
    exige_motivo: bool | None = Field(None, alias="exigeMotivo")
    """
    Exige justificativa textual.
    """
    afeta_afd: bool | None = Field(None, alias="afetaAfd")
    """
    SEMPRE falso. A coluna existe para tornar a regra explicita e auditavel, nao para ser configurada.
    """
    afeta_aej: bool | None = Field(None, alias="afetaAej")
    """
    Verdadeiro faz o tratamento aparecer no AEJ, que e onde a correcao legitimamente aparece.
    """
    permite_retroativo_dias: int | None = Field(None, alias="permiteRetroativoDias", ge=0)
    """
    Prazo maximo de retroatividade, em dias.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class Sentido(StrEnum):
    """
    Sentido da marcacao proposta.
    """

    entrada = "entrada"
    saida = "saida"
    indefinido = "indefinido"


class Origem3(StrEnum):
    """
    Quem originou o tratamento.
    """

    colaborador = "colaborador"
    gestor = "gestor"
    rh = "rh"
    sistema = "sistema"
    integracao = "integracao"
    importacao = "importacao"


class Status24(StrEnum):
    """
    Situacao. aplicado marca que a apuracao ja consumiu o tratamento.
    """

    rascunho = "rascunho"
    pendente = "pendente"
    aprovado = "aprovado"
    reprovado = "reprovado"
    cancelado = "cancelado"
    aplicado = "aplicado"


class Tratamento(BaseModel):
    """
    CAMADA DE CORRECAO. Refere-se a um dia e, opcionalmente, a uma marcacao existente, mas NUNCA a modifica. Aqui vivem inclusao manual, desconsideracao, abono e justificativa, sempre com autor, data, motivo e anexo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do tratamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador alvo.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    tipo_tratamento_id: UUID | None = Field(None, alias="tipoTratamentoId")
    """
    Tipo de tratamento aplicado.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Dia da jornada a que o tratamento se refere.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao alvo, quando o tratamento se refere a uma existente. A marcacao permanece intacta no AFD.
    """
    datahora_proposta: AwareDatetime | None = Field(None, alias="datahoraProposta")
    """
    Horario proposto em uma inclusao manual. Entra na apuracao e no AEJ; nunca gera registro no AFD.
    """
    sentido: Sentido | None = None
    """
    Sentido da marcacao proposta.
    """
    minutos_ajuste: int | None = Field(None, alias="minutosAjuste")
    """
    Ajuste em minutos para tratamentos de saldo ou de intervalo. Positivo credita, negativo debita.
    """
    tipo_afastamento_id: UUID | None = Field(None, alias="tipoAfastamentoId")
    """
    Tipo de afastamento, quando a categoria e afastamento ou abono.
    """
    motivo: str | None = None
    """
    Justificativa obrigatoria do tratamento.
    """
    observacao: str | None = None
    """
    Observacao complementar.
    """
    origem: Origem3 | None = None
    """
    Quem originou o tratamento.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o tratamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    status: Status24 | None = None
    """
    Situacao. aplicado marca que a apuracao ja consumiu o tratamento.
    """
    aprovado_por: UUID | None = Field(None, alias="aprovadoPor")
    """
    Usuario que aprovou.
    """
    aprovado_em: AwareDatetime | None = Field(None, alias="aprovadoEm")
    """
    Instante da aprovacao.
    """
    reprovado_motivo: str | None = Field(None, alias="reprovadoMotivo")
    """
    Motivo da reprovacao.
    """
    aplicado_em: AwareDatetime | None = Field(None, alias="aplicadoEm")
    """
    Instante em que a apuracao consumiu o tratamento.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class TratamentoCriar(BaseModel):
    """
    Dados aceitos na criacao de Tratamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador alvo.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    tipo_tratamento_id: UUID = Field(..., alias="tipoTratamentoId")
    """
    Tipo de tratamento aplicado.
    """
    data_referencia: date = Field(..., alias="dataReferencia")
    """
    Dia da jornada a que o tratamento se refere.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao alvo, quando o tratamento se refere a uma existente. A marcacao permanece intacta no AFD.
    """
    datahora_proposta: AwareDatetime | None = Field(None, alias="datahoraProposta")
    """
    Horario proposto em uma inclusao manual. Entra na apuracao e no AEJ; nunca gera registro no AFD.
    """
    sentido: Sentido | None = None
    """
    Sentido da marcacao proposta.
    """
    minutos_ajuste: int | None = Field(None, alias="minutosAjuste")
    """
    Ajuste em minutos para tratamentos de saldo ou de intervalo. Positivo credita, negativo debita.
    """
    tipo_afastamento_id: UUID | None = Field(None, alias="tipoAfastamentoId")
    """
    Tipo de afastamento, quando a categoria e afastamento ou abono.
    """
    motivo: str
    """
    Justificativa obrigatoria do tratamento.
    """
    observacao: str | None = None
    """
    Observacao complementar.
    """
    origem: Origem3 | None = None
    """
    Quem originou o tratamento.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o tratamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    status: Status24 | None = None
    """
    Situacao. aplicado marca que a apuracao ja consumiu o tratamento.
    """


class TratamentoAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Tratamento. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador alvo.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    tipo_tratamento_id: UUID | None = Field(None, alias="tipoTratamentoId")
    """
    Tipo de tratamento aplicado.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Dia da jornada a que o tratamento se refere.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao alvo, quando o tratamento se refere a uma existente. A marcacao permanece intacta no AFD.
    """
    datahora_proposta: AwareDatetime | None = Field(None, alias="datahoraProposta")
    """
    Horario proposto em uma inclusao manual. Entra na apuracao e no AEJ; nunca gera registro no AFD.
    """
    sentido: Sentido | None = None
    """
    Sentido da marcacao proposta.
    """
    minutos_ajuste: int | None = Field(None, alias="minutosAjuste")
    """
    Ajuste em minutos para tratamentos de saldo ou de intervalo. Positivo credita, negativo debita.
    """
    tipo_afastamento_id: UUID | None = Field(None, alias="tipoAfastamentoId")
    """
    Tipo de afastamento, quando a categoria e afastamento ou abono.
    """
    motivo: str | None = None
    """
    Justificativa obrigatoria do tratamento.
    """
    observacao: str | None = None
    """
    Observacao complementar.
    """
    origem: Origem3 | None = None
    """
    Quem originou o tratamento.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao de workflow que originou o tratamento.
    """
    documento_id: UUID | None = Field(None, alias="documentoId")
    """
    Documento comprobatorio anexado.
    """
    status: Status24 | None = None
    """
    Situacao. aplicado marca que a apuracao ja consumiu o tratamento.
    """


class Categoria6(StrEnum):
    """
    Natureza do componente.
    """

    normal = "normal"
    extra = "extra"
    noturno = "noturno"
    falta = "falta"
    abono = "abono"
    intervalo = "intervalo"
    sobreaviso = "sobreaviso"
    prontidao = "prontidao"
    dsr = "dsr"
    banco = "banco"
    indenizacao = "indenizacao"
    pausa = "pausa"


class Origem6(StrEnum):
    """
    Insumo que gerou o componente.
    """

    marcacao = "marcacao"
    tratamento = "tratamento"
    afastamento = "afastamento"
    regra = "regra"
    banco = "banco"
    feriado = "feriado"


class ApuracaoComponente(BaseModel):
    """
    Decomposicao auditavel da apuracao do dia. Cada linha explica de onde saiu cada bloco de minutos.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do componente.
    """
    codigo: str | None = None
    """
    Identificador da rubrica, por exemplo he_50, he_100 ou adicional_noturno.
    """
    descricao: str | None = None
    """
    Descricao da rubrica.
    """
    categoria: Categoria6 | None = None
    """
    Natureza do componente.
    """
    minutos: int | None = None
    """
    Minutos brutos do componente.
    """
    fator: float | None = Field(None, ge=0.0)
    """
    Multiplicador aplicado, por exemplo 1.5 para hora extra a 50 por cento.
    """
    minutos_equivalentes: int | None = Field(None, alias="minutosEquivalentes")
    """
    Minutos multiplicados pelo fator. E o valor que a folha consome.
    """
    origem: Origem6 | None = None
    """
    Insumo que gerou o componente.
    """
    inicio: AwareDatetime | None = None
    """
    Inicio do intervalo que originou o componente.
    """
    fim: AwareDatetime | None = None
    """
    Fim do intervalo que originou o componente.
    """
    detalhes: dict[str, Any] | None = None
    """
    Detalhamento livre do calculo, para depuracao e para o espelho.
    """


class TipoDia2(StrEnum):
    """
    Classificacao do dia.
    """

    util = "util"
    dsr = "dsr"
    folga = "folga"
    feriado = "feriado"
    ponto_facultativo = "ponto_facultativo"
    afastamento = "afastamento"
    compensado = "compensado"
    nao_apurado = "nao_apurado"


class Status27(StrEnum):
    """
    Situacao da apuracao.
    """

    pendente = "pendente"
    apurado = "apurado"
    com_ocorrencia = "com_ocorrencia"
    fechado = "fechado"
    reaberto = "reaberto"


class ApuracaoDia(BaseModel):
    """
    Resultado consolidado do calculo de um dia para um vinculo. E derivada e recalculavel: apagar e recalcular a partir de marcacoes, tratamentos e regras produz exatamente o mesmo resultado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da apuracao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo apurado.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador do vinculo.
    """
    data: date | None = None
    """
    Dia apurado.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do vinculo.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de lotacao no dia.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento de lotacao no dia.
    """
    centro_custo_id: UUID | None = Field(None, alias="centroCustoId")
    """
    Centro de custo de apropriacao no dia.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada vigente no dia.
    """
    escala_id: UUID | None = Field(None, alias="escalaId")
    """
    Escala vigente no dia.
    """
    turno_id: UUID | None = Field(None, alias="turnoId")
    """
    Turno resolvido para o dia.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario previsto no dia.
    """
    feriado_id: UUID | None = Field(None, alias="feriadoId")
    """
    Feriado aplicavel no dia.
    """
    afastamento_id: UUID | None = Field(None, alias="afastamentoId")
    """
    Afastamento aplicavel no dia.
    """
    tipo_dia: TipoDia2 | None = Field(None, alias="tipoDia")
    """
    Classificacao do dia.
    """
    previsto_minutos: int | None = Field(None, alias="previstoMinutos")
    """
    Carga prevista pelo horario ou pela escala do dia.
    """
    trabalhado_minutos: int | None = Field(None, alias="trabalhadoMinutos")
    """
    Tempo apurado, ja considerando tratamentos aprovados e tolerancias.
    """
    normais_minutos: int | None = Field(None, alias="normaisMinutos")
    """
    Minutos computados como horas normais.
    """
    extras_minutos: int | None = Field(None, alias="extrasMinutos")
    """
    Minutos computados como hora extra.
    """
    extras_noturnas_minutos: int | None = Field(None, alias="extrasNoturnasMinutos")
    """
    Minutos de hora extra em periodo noturno.
    """
    noturno_minutos: int | None = Field(None, alias="noturnoMinutos")
    """
    Minutos trabalhados no periodo noturno.
    """
    noturno_ficta_minutos: int | None = Field(None, alias="noturnoFictaMinutos")
    """
    Acrescimo decorrente da hora ficta de 52 minutos e 30 segundos aplicada ao periodo noturno.
    """
    intervalo_minutos: int | None = Field(None, alias="intervaloMinutos")
    """
    Intervalo efetivamente usufruido.
    """
    intervalo_previsto_minutos: int | None = Field(None, alias="intervaloPrevistoMinutos")
    """
    Intervalo previsto pelo horario do dia.
    """
    intrajornada_suprimida_minutos: int | None = Field(None, alias="intrajornadaSuprimidaMinutos")
    """
    Minutos de intervalo nao usufruidos. Geram a indenizacao de 50 por cento do art. 71, par. 4 da CLT.
    """
    interjornada_minutos: int | None = Field(None, alias="interjornadaMinutos")
    """
    Intervalo entre o fim da jornada anterior e o inicio desta.
    """
    interjornada_violada: bool | None = Field(None, alias="interjornadaViolada")
    """
    Verdadeiro quando o descanso entre jornadas ficou abaixo do minimo.
    """
    atraso_minutos: int | None = Field(None, alias="atrasoMinutos")
    """
    Minutos de atraso na entrada.
    """
    saida_antecipada_minutos: int | None = Field(None, alias="saidaAntecipadaMinutos")
    """
    Minutos de saida antes do previsto.
    """
    falta_minutos: int | None = Field(None, alias="faltaMinutos")
    """
    Minutos de ausencia nao justificada.
    """
    abono_minutos: int | None = Field(None, alias="abonoMinutos")
    """
    Minutos abonados por tratamento ou afastamento.
    """
    sobreaviso_minutos: int | None = Field(None, alias="sobreavisoMinutos")
    """
    Minutos em regime de sobreaviso.
    """
    prontidao_minutos: int | None = Field(None, alias="prontidaoMinutos")
    """
    Minutos em regime de prontidao.
    """
    pausas_nr17_minutos: int | None = Field(None, alias="pausasNr17Minutos")
    """
    Minutos de pausas obrigatorias da NR-17.
    """
    dsr_credito_minutos: int | None = Field(None, alias="dsrCreditoMinutos")
    """
    Credito de DSR sobre horas extras.
    """
    dsr_debito_minutos: int | None = Field(None, alias="dsrDebitoMinutos")
    """
    Debito de DSR por falta injustificada.
    """
    banco_credito_minutos: int | None = Field(None, alias="bancoCreditoMinutos")
    """
    Minutos creditados ao banco de horas.
    """
    banco_debito_minutos: int | None = Field(None, alias="bancoDebitoMinutos")
    """
    Minutos debitados do banco de horas.
    """
    tolerancia_aplicada_minutos: int | None = Field(None, alias="toleranciaAplicadaMinutos")
    """
    Minutos absorvidos pela tolerancia.
    """
    saldo_minutos: int | None = Field(None, alias="saldoMinutos")
    """
    Saldo liquido do dia. Positivo credita banco de horas, negativo debita, conforme a politica vigente.
    """
    quantidade_marcacoes: int | None = Field(None, alias="quantidadeMarcacoes", ge=0)
    """
    Quantidade de marcacoes consideradas no dia.
    """
    marcacoes_impares: bool | None = Field(None, alias="marcacoesImpares")
    """
    Verdadeiro quando o dia tem numero impar de marcacoes. O sistema SINALIZA a inconsistencia e nao a corrige silenciosamente.
    """
    tem_tratamento: bool | None = Field(None, alias="temTratamento")
    """
    Verdadeiro quando ha tratamento aplicado no dia.
    """
    status: Status27 | None = None
    """
    Situacao da apuracao.
    """
    versao: int | None = Field(None, ge=1)
    """
    Incrementada a cada recalculo efetivo. O diff entre versoes vai para a auditoria.
    """
    hash_entrada: str | None = Field(None, alias="hashEntrada", pattern="^[0-9a-f]{64}$")
    """
    Hash dos insumos (marcacoes, tratamentos e regras vigentes). Se nao mudou, o recalculo pode ser dispensado.
    """
    fechamento_id: UUID | None = Field(None, alias="fechamentoId")
    """
    Fechamento que travou o dia.
    """
    marcacoes: list[Marcacao] | None = None
    """
    Marcacoes consideradas no dia.
    """
    componentes: list[ApuracaoComponente] | None = None
    """
    Decomposicao do calculo.
    """
    apurado_em: AwareDatetime | None = Field(None, alias="apuradoEm")
    """
    Instante da ultima apuracao.
    """
    apurado_por: UUID | None = Field(None, alias="apuradoPor")
    """
    Usuario ou processo que apurou.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Codigo(StrEnum):
    """
    Tipo da ocorrencia. Os codigos sao fechados porque relatorios, notificacoes e webhooks dependem deles.
    """

    marcacao_impar = "marcacao_impar"
    sem_marcacao = "sem_marcacao"
    falta = "falta"
    atraso = "atraso"
    saida_antecipada = "saida_antecipada"
    extra_excedida = "extra_excedida"
    jornada_excedida = "jornada_excedida"
    intrajornada_suprimida = "intrajornada_suprimida"
    interjornada_violada = "interjornada_violada"
    dsr_violado = "dsr_violado"
    pausa_nr17 = "pausa_nr17"
    fora_geocerca = "fora_geocerca"
    score_baixo = "score_baixo"
    marcacao_duplicada = "marcacao_duplicada"
    offline_tardio = "offline_tardio"
    banco_teto = "banco_teto"
    banco_vencendo = "banco_vencendo"
    terminal_offline = "terminal_offline"


class Severidade(StrEnum):
    """
    Gravidade atribuida pelo motor.
    """

    info = "info"
    atencao = "atencao"
    alta = "alta"
    critica = "critica"


class Status28(StrEnum):
    """
    Situacao da ocorrencia.
    """

    aberta = "aberta"
    em_tratamento = "em_tratamento"
    resolvida = "resolvida"
    ignorada = "ignorada"


class Ocorrencia(BaseModel):
    """
    Inconsistencia ou desvio detectado pelo motor. Ocorrencia nao corrige nada: ela chama o humano e alimenta a fila de trabalho do gestor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da ocorrencia.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador afetado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo afetado.
    """
    apuracao_dia_id: UUID | None = Field(None, alias="apuracaoDiaId")
    """
    Apuracao que originou a ocorrencia.
    """
    data: date | None = None
    """
    Dia da ocorrencia.
    """
    codigo: Codigo | None = None
    """
    Tipo da ocorrencia. Os codigos sao fechados porque relatorios, notificacoes e webhooks dependem deles.
    """
    severidade: Severidade | None = None
    """
    Gravidade atribuida pelo motor.
    """
    descricao: str | None = None
    """
    Texto explicativo da ocorrencia.
    """
    detalhes: dict[str, Any] | None = None
    """
    Detalhamento estruturado da deteccao.
    """
    status: Status28 | None = None
    """
    Situacao da ocorrencia.
    """
    tratamento_id: UUID | None = Field(None, alias="tratamentoId")
    """
    Tratamento que resolveu a ocorrencia, quando houve.
    """
    resolucao: str | None = None
    """
    Descricao da resolucao.
    """
    resolvida_em: AwareDatetime | None = Field(None, alias="resolvidaEm")
    """
    Instante da resolucao.
    """
    resolvida_por: UUID | None = Field(None, alias="resolvidaPor")
    """
    Usuario que resolveu.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class OcorrenciaAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Ocorrencia. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador afetado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo afetado.
    """
    apuracao_dia_id: UUID | None = Field(None, alias="apuracaoDiaId")
    """
    Apuracao que originou a ocorrencia.
    """
    data: date | None = None
    """
    Dia da ocorrencia.
    """
    codigo: Codigo | None = None
    """
    Tipo da ocorrencia. Os codigos sao fechados porque relatorios, notificacoes e webhooks dependem deles.
    """
    severidade: Severidade | None = None
    """
    Gravidade atribuida pelo motor.
    """
    descricao: str | None = None
    """
    Texto explicativo da ocorrencia.
    """
    detalhes: dict[str, Any] | None = None
    """
    Detalhamento estruturado da deteccao.
    """
    status: Status28 | None = None
    """
    Situacao da ocorrencia.
    """
    tratamento_id: UUID | None = Field(None, alias="tratamentoId")
    """
    Tratamento que resolveu a ocorrencia, quando houve.
    """
    resolucao: str | None = None
    """
    Descricao da resolucao.
    """
    resolvida_em: AwareDatetime | None = Field(None, alias="resolvidaEm")
    """
    Instante da resolucao.
    """
    resolvida_por: UUID | None = Field(None, alias="resolvidaPor")
    """
    Usuario que resolveu.
    """


class Regime(StrEnum):
    """
    individual: acordo escrito com o empregado (ate 6 meses). coletivo e convencao: instrumento sindical (ate 12 meses). especial: regime autorizado por norma propria.
    """

    individual = "individual"
    coletivo = "coletivo"
    convencao = "convencao"
    especial = "especial"


class MetodoConsumo(StrEnum):
    """
    Ordem de consumo do saldo. fifo consome primeiro as horas mais antigas e protege o empregado do vencimento.
    """

    fifo = "fifo"
    lifo = "lifo"


class AcaoVencimento(StrEnum):
    """
    O que acontece com as horas ao fim do periodo.
    """

    quitar_folha = "quitar_folha"
    expirar = "expirar"
    prorrogar = "prorrogar"
    manter = "manter"


class BhPolitica(BaseModel):
    """
    Regras do banco de horas por empresa. O limite legal e imposto: acordo individual escrito compensa em ate 6 meses; acordo ou convencao coletiva, em ate 12.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da politica.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa a que a politica se aplica.
    """
    codigo: str | None = None
    """
    Codigo unico por empresa.
    """
    nome: str | None = None
    """
    Nome da politica.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    regime: Regime | None = None
    """
    individual: acordo escrito com o empregado (ate 6 meses). coletivo e convencao: instrumento sindical (ate 12 meses). especial: regime autorizado por norma propria.
    """
    periodo_meses: int | None = Field(None, alias="periodoMeses", ge=1, le=12)
    """
    Periodo de compensacao em meses.
    """
    metodo_consumo: MetodoConsumo | None = Field(None, alias="metodoConsumo")
    """
    Ordem de consumo do saldo. fifo consome primeiro as horas mais antigas e protege o empregado do vencimento.
    """
    fator_credito_padrao: float | None = Field(None, alias="fatorCreditoPadrao", ge=0.0)
    """
    Fator aplicado aos creditos.
    """
    fator_debito_padrao: float | None = Field(None, alias="fatorDebitoPadrao", ge=0.0)
    """
    Fator aplicado aos debitos.
    """
    fatores_por_faixa: dict[str, Any] | None = Field(None, alias="fatoresPorFaixa")
    """
    Fatores diferenciados de credito por faixa, em JSON.
    """
    teto_positivo_minutos: int | None = Field(None, alias="tetoPositivoMinutos", ge=0)
    """
    Saldo credor maximo.
    """
    teto_negativo_minutos: int | None = Field(None, alias="tetoNegativoMinutos", ge=0)
    """
    Saldo devedor maximo, em valor absoluto.
    """
    limite_diario_minutos: int | None = Field(None, alias="limiteDiarioMinutos", ge=0)
    """
    Limite diario de credito em minutos.
    """
    limite_jornada_diaria_minutos: int | None = Field(
        None, alias="limiteJornadaDiariaMinutos", ge=1
    )
    """
    Teto de jornada diaria. Padrao de 600 minutos (10 horas).
    """
    acao_vencimento: AcaoVencimento | None = Field(None, alias="acaoVencimento")
    """
    O que acontece com as horas ao fim do periodo.
    """
    dias_pre_aviso: list[int] | None = Field(None, alias="diasPreAviso")
    """
    Antecedencias em dias para avisar gestor e colaborador.
    """
    bloqueia_extra_no_teto: bool | None = Field(None, alias="bloqueiaExtraNoTeto")
    """
    Bloqueia novas horas extras ao atingir o teto positivo.
    """
    permite_saldo_negativo: bool | None = Field(None, alias="permiteSaldoNegativo")
    """
    Permite saldo devedor.
    """
    documento_acordo_id: UUID | None = Field(None, alias="documentoAcordoId")
    """
    Acordo assinado que da validade juridica ao regime. Sem ele, o banco de horas e questionavel em juizo.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia da politica.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia da politica.
    """
    ativo: bool | None = None
    """
    Politica ativa.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class BhPoliticaCriar(BaseModel):
    """
    Dados aceitos na criacao de BhPolitica.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa a que a politica se aplica.
    """
    codigo: str
    """
    Codigo unico por empresa.
    """
    nome: str
    """
    Nome da politica.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    regime: Regime
    """
    individual: acordo escrito com o empregado (ate 6 meses). coletivo e convencao: instrumento sindical (ate 12 meses). especial: regime autorizado por norma propria.
    """
    periodo_meses: int = Field(..., alias="periodoMeses", ge=1, le=12)
    """
    Periodo de compensacao em meses.
    """
    metodo_consumo: MetodoConsumo | None = Field(None, alias="metodoConsumo")
    """
    Ordem de consumo do saldo. fifo consome primeiro as horas mais antigas e protege o empregado do vencimento.
    """
    fator_credito_padrao: float | None = Field(None, alias="fatorCreditoPadrao", ge=0.0)
    """
    Fator aplicado aos creditos.
    """
    fator_debito_padrao: float | None = Field(None, alias="fatorDebitoPadrao", ge=0.0)
    """
    Fator aplicado aos debitos.
    """
    fatores_por_faixa: dict[str, Any] | None = Field(None, alias="fatoresPorFaixa")
    """
    Fatores diferenciados de credito por faixa, em JSON.
    """
    teto_positivo_minutos: int | None = Field(None, alias="tetoPositivoMinutos", ge=0)
    """
    Saldo credor maximo.
    """
    teto_negativo_minutos: int | None = Field(None, alias="tetoNegativoMinutos", ge=0)
    """
    Saldo devedor maximo, em valor absoluto.
    """
    limite_diario_minutos: int | None = Field(None, alias="limiteDiarioMinutos", ge=0)
    """
    Limite diario de credito em minutos.
    """
    limite_jornada_diaria_minutos: int | None = Field(
        None, alias="limiteJornadaDiariaMinutos", ge=1
    )
    """
    Teto de jornada diaria. Padrao de 600 minutos (10 horas).
    """
    acao_vencimento: AcaoVencimento | None = Field(None, alias="acaoVencimento")
    """
    O que acontece com as horas ao fim do periodo.
    """
    dias_pre_aviso: list[int] | None = Field(None, alias="diasPreAviso")
    """
    Antecedencias em dias para avisar gestor e colaborador.
    """
    bloqueia_extra_no_teto: bool | None = Field(None, alias="bloqueiaExtraNoTeto")
    """
    Bloqueia novas horas extras ao atingir o teto positivo.
    """
    permite_saldo_negativo: bool | None = Field(None, alias="permiteSaldoNegativo")
    """
    Permite saldo devedor.
    """
    documento_acordo_id: UUID | None = Field(None, alias="documentoAcordoId")
    """
    Acordo assinado que da validade juridica ao regime. Sem ele, o banco de horas e questionavel em juizo.
    """
    vigencia_inicio: date = Field(..., alias="vigenciaInicio")
    """
    Inicio da vigencia da politica.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia da politica.
    """
    ativo: bool | None = None
    """
    Politica ativa.
    """


class Status30(StrEnum):
    """
    Situacao da conta.
    """

    aberta = "aberta"
    encerrada = "encerrada"
    quitada = "quitada"
    expirada = "expirada"
    suspensa = "suspensa"


class BhConta(BaseModel):
    """
    Conta-corrente de horas de um vinculo dentro de um periodo de compensacao. O mesmo vinculo pode ter varias contas simultaneas com fatores diferentes.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da conta.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo dono da conta.
    """
    bh_politica_id: UUID | None = Field(None, alias="bhPoliticaId")
    """
    Politica aplicada a conta.
    """
    codigo: str | None = None
    """
    Identificador da conta dentro do vinculo, por exemplo normal, sobreaviso ou feriado.
    """
    nome: str | None = None
    """
    Nome da conta.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Inicio do periodo de compensacao.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Fim do periodo. E a data que dispara quitacao ou expiracao.
    """
    status: Status30 | None = None
    """
    Situacao da conta.
    """
    saldo_atual_minutos: int | None = Field(None, alias="saldoAtualMinutos")
    """
    Saldo materializado para leitura rapida. A verdade e a soma dos lancamentos; divergencia e defeito.
    """
    ultima_sequencia: int | None = Field(None, alias="ultimaSequencia", ge=0)
    """
    Ultimo numero de sequencia usado no extrato.
    """
    encerrada_em: AwareDatetime | None = Field(None, alias="encerradaEm")
    """
    Instante do encerramento da conta.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class BhContaCriar(BaseModel):
    """
    Dados aceitos na criacao de BhConta.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    vinculo_id: UUID = Field(..., alias="vinculoId")
    """
    Vinculo dono da conta.
    """
    bh_politica_id: UUID = Field(..., alias="bhPoliticaId")
    """
    Politica aplicada a conta.
    """
    codigo: str
    """
    Identificador da conta dentro do vinculo, por exemplo normal, sobreaviso ou feriado.
    """
    nome: str | None = None
    """
    Nome da conta.
    """
    periodo_inicio: date = Field(..., alias="periodoInicio")
    """
    Inicio do periodo de compensacao.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Fim do periodo. E a data que dispara quitacao ou expiracao.
    """
    status: Status30 | None = None
    """
    Situacao da conta.
    """


class Tipo27(StrEnum):
    """
    Natureza do lancamento.
    """

    credito = "credito"
    debito = "debito"
    quitacao = "quitacao"
    expiracao = "expiracao"
    ajuste = "ajuste"
    transferencia = "transferencia"
    estorno = "estorno"


class Origem7(StrEnum):
    """
    Insumo que gerou o lancamento.
    """

    apuracao = "apuracao"
    tratamento = "tratamento"
    solicitacao = "solicitacao"
    quitacao = "quitacao"
    expiracao = "expiracao"
    ajuste_manual = "ajuste_manual"
    importacao = "importacao"
    fechamento = "fechamento"
    rescisao = "rescisao"


class BhLancamento(BaseModel):
    """
    Linha do EXTRATO IMUTAVEL do banco de horas, com cadeia de hash. Corrigir um lancamento significa emitir um estorno, nunca reescrever a linha.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do lancamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    bh_conta_id: UUID | None = Field(None, alias="bhContaId")
    """
    Conta a que o lancamento pertence.
    """
    sequencia: int | None = Field(None, ge=1)
    """
    Ordem do lancamento dentro da conta, sem lacunas.
    """
    data_competencia: date | None = Field(None, alias="dataCompetencia")
    """
    Dia a que o lancamento se refere.
    """
    tipo: Tipo27 | None = None
    """
    Natureza do lancamento.
    """
    origem: Origem7 | None = None
    """
    Insumo que gerou o lancamento.
    """
    apuracao_dia_id: UUID | None = Field(None, alias="apuracaoDiaId")
    """
    Apuracao que originou o lancamento.
    """
    tratamento_id: UUID | None = Field(None, alias="tratamentoId")
    """
    Tratamento que originou o lancamento.
    """
    quitacao_id: UUID | None = Field(None, alias="quitacaoId")
    """
    Quitacao que originou o lancamento.
    """
    estorna_lancamento_id: UUID | None = Field(None, alias="estornaLancamentoId")
    """
    Lancamento estornado por este. Presente somente quando o tipo e estorno.
    """
    minutos: int | None = None
    """
    Minutos brutos do evento. Positivo em credito, negativo em debito. Zero e proibido.
    """
    fator: float | None = Field(None, ge=0.0)
    """
    Fator aplicado ao lancamento.
    """
    minutos_equivalentes: int | None = Field(None, alias="minutosEquivalentes")
    """
    Minutos aplicado o fator. E este valor que altera o saldo.
    """
    saldo_apos_minutos: int | None = Field(None, alias="saldoAposMinutos")
    """
    Saldo da conta depois deste lancamento.
    """
    vence_em: date | None = Field(None, alias="venceEm")
    """
    Data em que este credito especifico vence. E o que permite FIFO e LIFO reais.
    """
    consumido_minutos: int | None = Field(None, alias="consumidoMinutos", ge=0)
    """
    Quanto deste credito ja foi consumido por debitos posteriores.
    """
    descricao: str | None = None
    """
    Descricao legivel do lancamento.
    """
    hash_anterior: str | None = Field(None, alias="hashAnterior", pattern="^[0-9a-f]{64}$")
    """
    Hash do lancamento anterior da mesma conta.
    """
    hash_registro: str | None = Field(None, alias="hashRegistro", pattern="^[0-9a-f]{64}$")
    """
    SHA-256 do conteudo canonico do lancamento concatenado com hashAnterior.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do lancamento.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario ou processo que gerou o lancamento.
    """


class Tipo28(StrEnum):
    """
    Forma de liquidacao. expiracao registra a perda de horas por vencimento, que precisa ficar rastreavel mesmo sem pagamento.
    """

    folha = "folha"
    folga = "folga"
    rescisao = "rescisao"
    expiracao = "expiracao"
    compensacao_programada = "compensacao_programada"


class Status32(StrEnum):
    """
    Situacao da quitacao.
    """

    planejada = "planejada"
    aprovada = "aprovada"
    efetivada = "efetivada"
    cancelada = "cancelada"


class BhQuitacao(BaseModel):
    """
    Liquidacao de saldo de banco de horas: pagamento em folha, folga programada, acerto na rescisao ou expiracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da quitacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    bh_conta_id: UUID | None = Field(None, alias="bhContaId")
    """
    Conta liquidada.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    tipo: Tipo28 | None = None
    """
    Forma de liquidacao. expiracao registra a perda de horas por vencimento, que precisa ficar rastreavel mesmo sem pagamento.
    """
    minutos: int | None = Field(None, ge=1)
    """
    Minutos liquidados.
    """
    fator: float | None = Field(None, ge=0.0)
    """
    Fator aplicado a liquidacao.
    """
    valor: float | None = Field(None, ge=0.0)
    """
    Valor monetario quando a quitacao e em dinheiro.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia AAAA-MM em que o pagamento entra na folha.
    """
    data_prevista: date | None = Field(None, alias="dataPrevista")
    """
    Data prevista da efetivacao.
    """
    data_efetivacao: date | None = Field(None, alias="dataEfetivacao")
    """
    Data em que a quitacao foi efetivada.
    """
    status: Status32 | None = None
    """
    Situacao da quitacao.
    """
    aprovado_por: UUID | None = Field(None, alias="aprovadoPor")
    """
    Usuario que aprovou.
    """
    aprovado_em: AwareDatetime | None = Field(None, alias="aprovadoEm")
    """
    Instante da aprovacao.
    """
    observacao: str | None = None
    """
    Observacao livre.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class BhQuitacaoCriar(BaseModel):
    """
    Dados aceitos na criacao de BhQuitacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    bh_conta_id: UUID = Field(..., alias="bhContaId")
    """
    Conta liquidada.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    tipo: Tipo28
    """
    Forma de liquidacao. expiracao registra a perda de horas por vencimento, que precisa ficar rastreavel mesmo sem pagamento.
    """
    minutos: int = Field(..., ge=1)
    """
    Minutos liquidados.
    """
    fator: float | None = Field(None, ge=0.0)
    """
    Fator aplicado a liquidacao.
    """
    valor: float | None = Field(None, ge=0.0)
    """
    Valor monetario quando a quitacao e em dinheiro.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia AAAA-MM em que o pagamento entra na folha.
    """
    data_prevista: date | None = Field(None, alias="dataPrevista")
    """
    Data prevista da efetivacao.
    """
    data_efetivacao: date | None = Field(None, alias="dataEfetivacao")
    """
    Data em que a quitacao foi efetivada.
    """
    status: Status32 | None = None
    """
    Situacao da quitacao.
    """
    observacao: str | None = None
    """
    Observacao livre.
    """


class Categoria7(StrEnum):
    """
    Categoria funcional do pedido.
    """

    ajuste_ponto = "ajuste_ponto"
    abono = "abono"
    justificativa = "justificativa"
    ferias = "ferias"
    folga = "folga"
    compensacao = "compensacao"
    afastamento = "afastamento"
    troca_escala = "troca_escala"
    hora_extra = "hora_extra"
    desbloqueio_dispositivo = "desbloqueio_dispositivo"
    outro = "outro"


class TipoSolicitacao(BaseModel):
    """
    Catalogo configuravel de pedidos que o colaborador ou o gestor podem abrir, com a cadeia de aprovacao de cada um.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do tipo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do tipo de solicitacao.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria7 | None = None
    """
    Categoria funcional do pedido.
    """
    etapas: dict[str, Any] | None = None
    """
    Cadeia de aprovacao em JSON, uma entrada por etapa com o papel responsavel.
    """
    prazo_resposta_horas: int | None = Field(None, alias="prazoRespostaHoras", ge=1)
    """
    Prazo de resposta de cada etapa, em horas.
    """
    escalonar_apos_horas: int | None = Field(None, alias="escalonarAposHoras", ge=1)
    """
    Prazo apos o qual a pendencia sobe de nivel automaticamente.
    """
    exige_anexo: bool | None = Field(None, alias="exigeAnexo")
    """
    Exige documento anexado.
    """
    exige_justificativa: bool | None = Field(None, alias="exigeJustificativa")
    """
    Exige justificativa textual.
    """
    permite_retroativo_dias: int | None = Field(None, alias="permiteRetroativoDias", ge=0)
    """
    Prazo maximo de retroatividade, em dias.
    """
    tipo_tratamento_id: UUID | None = Field(None, alias="tipoTratamentoId")
    """
    Tratamento gerado quando a solicitacao e aprovada. E o elo entre workflow e apuracao.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class TipoSolicitacaoCriar(BaseModel):
    """
    Dados aceitos na criacao de TipoSolicitacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str
    """
    Codigo unico por tenant.
    """
    nome: str
    """
    Nome do tipo de solicitacao.
    """
    descricao: str | None = None
    """
    Descricao livre.
    """
    categoria: Categoria7
    """
    Categoria funcional do pedido.
    """
    etapas: dict[str, Any] | None = None
    """
    Cadeia de aprovacao em JSON, uma entrada por etapa com o papel responsavel.
    """
    prazo_resposta_horas: int | None = Field(None, alias="prazoRespostaHoras", ge=1)
    """
    Prazo de resposta de cada etapa, em horas.
    """
    escalonar_apos_horas: int | None = Field(None, alias="escalonarAposHoras", ge=1)
    """
    Prazo apos o qual a pendencia sobe de nivel automaticamente.
    """
    exige_anexo: bool | None = Field(None, alias="exigeAnexo")
    """
    Exige documento anexado.
    """
    exige_justificativa: bool | None = Field(None, alias="exigeJustificativa")
    """
    Exige justificativa textual.
    """
    permite_retroativo_dias: int | None = Field(None, alias="permiteRetroativoDias", ge=0)
    """
    Prazo maximo de retroatividade, em dias.
    """
    tipo_tratamento_id: UUID | None = Field(None, alias="tipoTratamentoId")
    """
    Tratamento gerado quando a solicitacao e aprovada. E o elo entre workflow e apuracao.
    """
    ativo: bool | None = None
    """
    Tipo ativo.
    """


class Status34(StrEnum):
    """
    Situacao do pedido.
    """

    rascunho = "rascunho"
    pendente = "pendente"
    em_aprovacao = "em_aprovacao"
    aprovada = "aprovada"
    reprovada = "reprovada"
    cancelada = "cancelada"
    expirada = "expirada"


class SolicitacaoCriar(BaseModel):
    """
    Dados aceitos na criacao de Solicitacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    tipo_solicitacao_id: UUID = Field(..., alias="tipoSolicitacaoId")
    """
    Tipo de solicitacao.
    """
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Colaborador alvo.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    solicitante_usuario_id: UUID | None = Field(None, alias="solicitanteUsuarioId")
    """
    Usuario que abriu o pedido.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Dia de referencia do pedido.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Inicio do periodo pedido.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim do periodo pedido.
    """
    descricao: str
    """
    Justificativa do solicitante.
    """
    payload: dict[str, Any] | None = None
    """
    Conteudo especifico do tipo, por exemplo os horarios propostos em um ajuste de ponto.
    """
    status: Status34 | None = None
    """
    Situacao do pedido.
    """


class Papel2(StrEnum):
    """
    Papel responsavel pela etapa.
    """

    gestor = "gestor"
    rh = "rh"
    diretoria = "diretoria"
    sistema = "sistema"


class Decisao(StrEnum):
    """
    Decisao da etapa.
    """

    pendente = "pendente"
    aprovada = "aprovada"
    reprovada = "reprovada"
    delegada = "delegada"
    expirada = "expirada"
    cancelada = "cancelada"


class Aprovacao(BaseModel):
    """
    Uma etapa da cadeia de uma solicitacao. Guarda quem decidiu, quando, de onde e se decidiu por delegacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da etapa.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    solicitacao_id: UUID | None = Field(None, alias="solicitacaoId")
    """
    Solicitacao a que a etapa pertence.
    """
    etapa: int | None = Field(None, ge=1)
    """
    Indice da etapa na cadeia.
    """
    papel: Papel2 | None = None
    """
    Papel responsavel pela etapa.
    """
    aprovador_usuario_id: UUID | None = Field(None, alias="aprovadorUsuarioId")
    """
    Usuario que decidiu.
    """
    aprovador_delegacao_id: UUID | None = Field(None, alias="aprovadorDelegacaoId")
    """
    Delegacao que autorizou o aprovador a decidir no lugar do titular.
    """
    decisao: Decisao | None = None
    """
    Decisao da etapa.
    """
    comentario: str | None = None
    """
    Comentario do aprovador.
    """
    prazo_em: AwareDatetime | None = Field(None, alias="prazoEm")
    """
    Prazo da etapa.
    """
    notificado_em: AwareDatetime | None = Field(None, alias="notificadoEm")
    """
    Instante da notificacao ao aprovador.
    """
    escalonado_em: AwareDatetime | None = Field(None, alias="escalonadoEm")
    """
    Momento em que a pendencia subiu de nivel por estouro de prazo.
    """
    decidido_em: AwareDatetime | None = Field(None, alias="decididoEm")
    """
    Instante da decisao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Status36(StrEnum):
    """
    Situacao da delegacao.
    """

    agendada = "agendada"
    ativa = "ativa"
    encerrada = "encerrada"
    cancelada = "cancelada"


class Delegacao(BaseModel):
    """
    Delegacao temporaria de atribuicoes, tipicamente ferias do gestor. Toda acao exercida por delegacao e marcada como tal na auditoria.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da delegacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    delegante_usuario_id: UUID | None = Field(None, alias="deleganteUsuarioId")
    """
    Usuario titular que delega.
    """
    delegado_usuario_id: UUID | None = Field(None, alias="delegadoUsuarioId")
    """
    Usuario que recebe a delegacao.
    """
    perfil_id: UUID | None = Field(None, alias="perfilId")
    """
    Perfil delegado, quando a delegacao e restrita a um papel.
    """
    motivo: str | None = None
    """
    Justificativa obrigatoria da delegacao.
    """
    escopo: dict[str, Any] | None = None
    """
    Restricao opcional em JSON, por exemplo limitar a solicitacoes de ajuste de ponto.
    """
    inicio_em: AwareDatetime | None = Field(None, alias="inicioEm")
    """
    Inicio da vigencia.
    """
    fim_em: AwareDatetime | None = Field(None, alias="fimEm")
    """
    Fim da vigencia.
    """
    status: Status36 | None = None
    """
    Situacao da delegacao.
    """
    revogada_em: AwareDatetime | None = Field(None, alias="revogadaEm")
    """
    Instante da revogacao.
    """
    revogada_por: UUID | None = Field(None, alias="revogadaPor")
    """
    Usuario que revogou.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class DelegacaoCriar(BaseModel):
    """
    Dados aceitos na criacao de Delegacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    delegante_usuario_id: UUID | None = Field(None, alias="deleganteUsuarioId")
    """
    Usuario titular que delega.
    """
    delegado_usuario_id: UUID = Field(..., alias="delegadoUsuarioId")
    """
    Usuario que recebe a delegacao.
    """
    perfil_id: UUID | None = Field(None, alias="perfilId")
    """
    Perfil delegado, quando a delegacao e restrita a um papel.
    """
    motivo: str
    """
    Justificativa obrigatoria da delegacao.
    """
    escopo: dict[str, Any] | None = None
    """
    Restricao opcional em JSON, por exemplo limitar a solicitacoes de ajuste de ponto.
    """
    inicio_em: AwareDatetime = Field(..., alias="inicioEm")
    """
    Inicio da vigencia.
    """
    fim_em: AwareDatetime = Field(..., alias="fimEm")
    """
    Fim da vigencia.
    """
    status: Status36 | None = None
    """
    Situacao da delegacao.
    """


class Tipo30(StrEnum):
    """
    Natureza do periodo.
    """

    mensal = "mensal"
    quinzenal = "quinzenal"
    semanal = "semanal"
    personalizado = "personalizado"
    banco_horas = "banco_horas"


class Status38(StrEnum):
    """
    Situacao do periodo.
    """

    aberto = "aberto"
    em_conferencia = "em_conferencia"
    fechado = "fechado"
    reaberto = "reaberto"
    exportado = "exportado"


class Periodo(BaseModel):
    """
    Janela de apuracao da empresa. O periodo do ponto e independente do periodo do banco de horas.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do periodo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do periodo.
    """
    codigo: str | None = None
    """
    Rotulo do periodo, tipicamente AAAA-MM em periodos mensais.
    """
    tipo: Tipo30 | None = None
    """
    Natureza do periodo.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Primeiro dia do periodo.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do periodo.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia da folha que consome este periodo.
    """
    status: Status38 | None = None
    """
    Situacao do periodo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class PeriodoCriar(BaseModel):
    """
    Dados aceitos na criacao de Periodo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa do periodo.
    """
    codigo: str
    """
    Rotulo do periodo, tipicamente AAAA-MM em periodos mensais.
    """
    tipo: Tipo30 | None = None
    """
    Natureza do periodo.
    """
    data_inicio: date = Field(..., alias="dataInicio")
    """
    Primeiro dia do periodo.
    """
    data_fim: date = Field(..., alias="dataFim")
    """
    Ultimo dia do periodo.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia da folha que consome este periodo.
    """
    status: Status38 | None = None
    """
    Situacao do periodo.
    """


class Escopo(StrEnum):
    """
    Abrangencia da trava.
    """

    empresa = "empresa"
    unidade = "unidade"
    departamento = "departamento"
    equipe = "equipe"
    colaborador = "colaborador"


class Status40(StrEnum):
    """
    Situacao do fechamento.
    """

    em_andamento = "em_andamento"
    conferido = "conferido"
    fechado = "fechado"
    reaberto = "reaberto"
    cancelado = "cancelado"


class Fechamento(BaseModel):
    """
    Trava do periodo para um escopo. Fechado, o dia nao recalcula. A reabertura e sempre nominal e justificada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do fechamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo travado.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do fechamento.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade do escopo, quando aplicavel.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento do escopo, quando aplicavel.
    """
    escopo: Escopo | None = None
    """
    Abrangencia da trava.
    """
    status: Status40 | None = None
    """
    Situacao do fechamento.
    """
    total_colaboradores: int | None = Field(None, alias="totalColaboradores")
    """
    Colaboradores abrangidos.
    """
    total_ocorrencias: int | None = Field(None, alias="totalOcorrencias")
    """
    Ocorrencias registradas no periodo.
    """
    total_pendencias: int | None = Field(None, alias="totalPendencias")
    """
    Ocorrencias e solicitacoes ainda abertas no momento do fechamento. Fechar com pendencia e possivel, mas fica registrado.
    """
    hash_conteudo: str | None = Field(None, alias="hashConteudo", pattern="^[0-9a-f]{64}$")
    """
    Hash do conjunto de apuracoes travadas. Permite provar que nada mudou depois do fechamento.
    """
    conferido_em: AwareDatetime | None = Field(None, alias="conferidoEm")
    """
    Instante da conferencia.
    """
    conferido_por: UUID | None = Field(None, alias="conferidoPor")
    """
    Usuario que conferiu.
    """
    fechado_em: AwareDatetime | None = Field(None, alias="fechadoEm")
    """
    Instante do fechamento.
    """
    fechado_por: UUID | None = Field(None, alias="fechadoPor")
    """
    Usuario que fechou.
    """
    reaberto_em: AwareDatetime | None = Field(None, alias="reabertoEm")
    """
    Instante da reabertura.
    """
    reaberto_por: UUID | None = Field(None, alias="reabertoPor")
    """
    Usuario que reabriu.
    """
    motivo_reabertura: str | None = Field(None, alias="motivoReabertura")
    """
    Justificativa obrigatoria da reabertura.
    """
    exportado_em: AwareDatetime | None = Field(None, alias="exportadoEm")
    """
    Instante da exportacao para a folha.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Tipo32(StrEnum):
    """
    Natureza do espelho.
    """

    previo = "previo"
    oficial = "oficial"
    retificado = "retificado"


class SignatarioTipo(StrEnum):
    """
    Papel de quem assinou.
    """

    colaborador = "colaborador"
    gestor = "gestor"
    rh = "rh"
    empregador = "empregador"


class Metodo(StrEnum):
    """
    Meio de assinatura. aceite_eletronico com carimbo de tempo e hash e o padrao.
    """

    aceite_eletronico = "aceite_eletronico"
    icp_brasil = "icp_brasil"
    biometria = "biometria"
    senha = "senha"
    token_email = "token_email"


class Status41(StrEnum):
    """
    Situacao da assinatura.
    """

    pendente = "pendente"
    assinado = "assinado"
    recusado = "recusado"
    expirado = "expirado"


class AssinaturaEspelho(BaseModel):
    """
    Aceite eletronico do espelho de ponto. Append-only: recusar e depois assinar gera duas linhas, preservando o historico.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da assinatura.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    espelho_id: UUID | None = Field(None, alias="espelhoId")
    """
    Espelho assinado.
    """
    signatario_tipo: SignatarioTipo | None = Field(None, alias="signatarioTipo")
    """
    Papel de quem assinou.
    """
    signatario_usuario_id: UUID | None = Field(None, alias="signatarioUsuarioId")
    """
    Usuario signatario.
    """
    signatario_colaborador_id: UUID | None = Field(None, alias="signatarioColaboradorId")
    """
    Colaborador signatario.
    """
    metodo: Metodo | None = None
    """
    Meio de assinatura. aceite_eletronico com carimbo de tempo e hash e o padrao.
    """
    hash_assinado: str | None = Field(None, alias="hashAssinado", pattern="^[0-9a-f]{64}$")
    """
    Hash do espelho no momento do aceite. Se o espelho mudar depois, a assinatura deixa de conferir.
    """
    certificado_ref: str | None = Field(None, alias="certificadoRef")
    """
    Chave do certificado utilizado, quando o metodo e ICP-Brasil.
    """
    carimbo_tempo: AwareDatetime | None = Field(None, alias="carimboTempo")
    """
    Instante do aceite registrado pelo servidor.
    """
    status: Status41 | None = None
    """
    Situacao da assinatura.
    """
    recusa_motivo: str | None = Field(None, alias="recusaMotivo")
    """
    Motivo informado na recusa.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Status42(StrEnum):
    """
    Situacao da geracao.
    """

    gerando = "gerando"
    gerado = "gerado"
    assinado = "assinado"
    falhou = "falhou"
    cancelado = "cancelado"


class AfdArquivo(BaseModel):
    """
    Arquivo Fonte de Dados gerado EXCLUSIVAMENTE pelo REP-P: texto ASCII ISO 8859-1, campos separados por barra vertical, linhas terminadas em CR+LF, CRC-16 por registro e SHA-256 do arquivo. Nenhum tratamento entra aqui.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do arquivo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do arquivo.
    """
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P que originou os registros.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Primeiro dia contemplado.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Ultimo dia contemplado.
    """
    nsr_inicial: int | None = Field(None, alias="nsrInicial", ge=1)
    """
    Primeiro NSR contido no arquivo.
    """
    nsr_final: int | None = Field(None, alias="nsrFinal", ge=1)
    """
    Ultimo NSR contido no arquivo.
    """
    total_registros: int | None = Field(None, alias="totalRegistros", ge=0)
    """
    Quantidade de registros no arquivo.
    """
    nome_arquivo: str | None = Field(None, alias="nomeArquivo")
    """
    Nome do arquivo gerado.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do arquivo no armazenamento de objetos.
    """
    tamanho_bytes: int | None = Field(None, alias="tamanhoBytes", ge=0)
    """
    Tamanho do arquivo em bytes.
    """
    encoding: str | None = None
    """
    Codificacao do arquivo. ISO-8859-1 por exigencia do leiaute.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    SHA-256 do arquivo gerado.
    """
    versao_leiaute: str | None = Field(None, alias="versaoLeiaute")
    """
    Versao do leiaute aplicada.
    """
    fracionado: bool | None = None
    """
    Verdadeiro quando o arquivo e uma fracao do periodo.
    """
    fracao_numero: int | None = Field(None, alias="fracaoNumero", ge=1)
    """
    Numero da fracao.
    """
    fracao_total: int | None = Field(None, alias="fracaoTotal", ge=1)
    """
    Quantidade total de fracoes.
    """
    status: Status42 | None = None
    """
    Situacao da geracao.
    """
    assinatura_ref: str | None = Field(None, alias="assinaturaRef")
    """
    Chave do arquivo .p7s de assinatura CAdES destacada.
    """
    solicitado_por: UUID | None = Field(None, alias="solicitadoPor")
    """
    Usuario que solicitou a geracao.
    """
    gerado_em: AwareDatetime | None = Field(None, alias="geradoEm")
    """
    Instante da conclusao da geracao.
    """
    erro: str | None = None
    """
    Mensagem de erro quando a geracao falha.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class AejArquivo(BaseModel):
    """
    Arquivo Eletronico de Jornada, gerado pelo Programa de Tratamento de Registro de Ponto. Substitui AFDT e ACJEF e contem cabecalho, REPs utilizados, vinculos, horario contratual, marcacoes, matricula eSocial, ausencias, banco de horas, identificacao do PTRP e trailer.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do arquivo.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do arquivo.
    """
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo de apuracao correspondente.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Primeiro dia contemplado.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Ultimo dia contemplado.
    """
    nome_arquivo: str | None = Field(None, alias="nomeArquivo")
    """
    Nome do arquivo gerado.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do arquivo no armazenamento de objetos.
    """
    tamanho_bytes: int | None = Field(None, alias="tamanhoBytes", ge=0)
    """
    Tamanho do arquivo em bytes.
    """
    encoding: str | None = None
    """
    Codificacao do arquivo.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    SHA-256 do arquivo gerado.
    """
    versao_leiaute: str | None = Field(None, alias="versaoLeiaute")
    """
    Versao do leiaute aplicada.
    """
    total_vinculos: int | None = Field(None, alias="totalVinculos")
    """
    Vinculos exportados.
    """
    total_marcacoes: int | None = Field(None, alias="totalMarcacoes")
    """
    Marcacoes exportadas.
    """
    total_ausencias: int | None = Field(None, alias="totalAusencias")
    """
    Ausencias exportadas.
    """
    total_lancamentos_banco: int | None = Field(None, alias="totalLancamentosBanco")
    """
    Lancamentos de banco de horas exportados. Precisa fechar com o extrato do periodo.
    """
    ptrp_identificacao: str | None = Field(None, alias="ptrpIdentificacao")
    """
    Identificacao do Programa de Tratamento que gerou o arquivo.
    """
    ptrp_cnpj: str | None = Field(None, alias="ptrpCnpj", pattern="^[0-9]{14}$")
    """
    CNPJ do responsavel pelo Programa de Tratamento.
    """
    ptrp_versao: str | None = Field(None, alias="ptrpVersao")
    """
    Versao do Programa de Tratamento.
    """
    status: Status42 | None = None
    """
    Situacao da geracao.
    """
    assinatura_ref: str | None = Field(None, alias="assinaturaRef")
    """
    Chave do arquivo .p7s de assinatura CAdES destacada.
    """
    solicitado_por: UUID | None = Field(None, alias="solicitadoPor")
    """
    Usuario que solicitou a geracao.
    """
    gerado_em: AwareDatetime | None = Field(None, alias="geradoEm")
    """
    Instante da conclusao da geracao.
    """
    erro: str | None = None
    """
    Mensagem de erro quando a geracao falha.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class TipoArquivo(StrEnum):
    """
    Tipo do arquivo assinado.
    """

    afd = "afd"
    aej = "aej"
    espelho = "espelho"
    comprovante = "comprovante"
    relatorio = "relatorio"


class Padrao(StrEnum):
    """
    Padrao de assinatura.
    """

    c_ad_es = "CAdES"
    x_ad_es = "XAdES"
    p_ad_es = "PAdES"


class Formato(StrEnum):
    """
    detached significa .p7s separado do arquivo original, formato exigido para o AFD.
    """

    detached = "detached"
    attached = "attached"


class Status44(StrEnum):
    """
    Situacao da assinatura.
    """

    pendente = "pendente"
    assinado = "assinado"
    invalido = "invalido"
    revogado = "revogado"


class ArquivoAssinatura(BaseModel):
    """
    Assinatura digital de arquivo fiscal no padrao CAdES, em .p7s destacado, com certificado ICP-Brasil. Somente-acrescimo: reassinar gera linha nova.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da assinatura.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    tipo_arquivo: TipoArquivo | None = Field(None, alias="tipoArquivo")
    """
    Tipo do arquivo assinado.
    """
    arquivo_id: UUID | None = Field(None, alias="arquivoId")
    """
    Arquivo assinado.
    """
    padrao: Padrao | None = None
    """
    Padrao de assinatura.
    """
    formato: Formato | None = None
    """
    detached significa .p7s separado do arquivo original, formato exigido para o AFD.
    """
    assinatura_ref: str | None = Field(None, alias="assinaturaRef")
    """
    Chave do arquivo de assinatura no armazenamento de objetos.
    """
    certificado_titular: str | None = Field(None, alias="certificadoTitular")
    """
    Titular do certificado utilizado.
    """
    certificado_serial: str | None = Field(None, alias="certificadoSerial")
    """
    Numero de serie do certificado.
    """
    certificado_emissor: str | None = Field(None, alias="certificadoEmissor")
    """
    Autoridade certificadora emissora.
    """
    certificado_validade_inicio: AwareDatetime | None = Field(
        None, alias="certificadoValidadeInicio"
    )
    """
    Inicio da validade do certificado.
    """
    certificado_validade_fim: AwareDatetime | None = Field(None, alias="certificadoValidadeFim")
    """
    Fim da validade do certificado.
    """
    politica_assinatura: str | None = Field(None, alias="politicaAssinatura")
    """
    Politica de assinatura aplicada.
    """
    carimbo_tempo: AwareDatetime | None = Field(None, alias="carimboTempo")
    """
    Carimbo do tempo da assinatura.
    """
    hash_arquivo: str | None = Field(None, alias="hashArquivo", pattern="^[0-9a-f]{64}$")
    """
    Hash do arquivo no momento da assinatura. Divergencia posterior indica adulteracao.
    """
    algoritmo_hash: str | None = Field(None, alias="algoritmoHash")
    """
    Algoritmo de hash utilizado.
    """
    status: Status44 | None = None
    """
    Situacao da assinatura.
    """
    validado_em: AwareDatetime | None = Field(None, alias="validadoEm")
    """
    Instante da ultima validacao.
    """
    validacao_resultado: dict[str, Any] | None = Field(None, alias="validacaoResultado")
    """
    Saida da validacao contra verificador ICP-Brasil independente, guardada como evidencia de conformidade.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Status45(StrEnum):
    """
    Situacao. desabilitado_por_falha e aplicado automaticamente apos falhas consecutivas.
    """

    ativo = "ativo"
    suspenso = "suspenso"
    desabilitado_por_falha = "desabilitado_por_falha"


class Webhook(BaseModel):
    """
    Assinatura de eventos por HTTP. Somente HTTPS. O corpo e assinado em HMAC-SHA256 com segredo proprio de cada webhook.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do webhook.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    api_client_id: UUID | None = Field(None, alias="apiClientId")
    """
    Cliente de API dono da assinatura.
    """
    nome: str | None = None
    """
    Nome do webhook, unico por tenant.
    """
    url: AnyUrl | None = None
    """
    Destino HTTPS da entrega.
    """
    eventos: list[str] | None = None
    """
    Codigos do catalogo events.yaml. Somente eventos com webhookPublico verdadeiro podem ser assinados.
    """
    cabecalhos_extras: dict[str, Any] | None = Field(None, alias="cabecalhosExtras")
    """
    Cabecalhos adicionais enviados na entrega.
    """
    max_tentativas: int | None = Field(None, alias="maxTentativas", ge=1)
    """
    Maximo de tentativas antes da dead letter queue.
    """
    timeout_segundos: int | None = Field(None, alias="timeoutSegundos", ge=1)
    """
    Tempo limite de cada entrega.
    """
    status: Status45 | None = None
    """
    Situacao. desabilitado_por_falha e aplicado automaticamente apos falhas consecutivas.
    """
    falhas_consecutivas: int | None = Field(None, alias="falhasConsecutivas", ge=0)
    """
    Falhas consecutivas acumuladas.
    """
    ultima_entrega_em: AwareDatetime | None = Field(None, alias="ultimaEntregaEm")
    """
    Instante da ultima entrega.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class WebhookCriar(BaseModel):
    """
    Dados aceitos na criacao de Webhook.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    api_client_id: UUID | None = Field(None, alias="apiClientId")
    """
    Cliente de API dono da assinatura.
    """
    nome: str
    """
    Nome do webhook, unico por tenant.
    """
    url: AnyUrl
    """
    Destino HTTPS da entrega.
    """
    eventos: list[str]
    """
    Codigos do catalogo events.yaml. Somente eventos com webhookPublico verdadeiro podem ser assinados.
    """
    cabecalhos_extras: dict[str, Any] | None = Field(None, alias="cabecalhosExtras")
    """
    Cabecalhos adicionais enviados na entrega.
    """
    max_tentativas: int | None = Field(None, alias="maxTentativas", ge=1)
    """
    Maximo de tentativas antes da dead letter queue.
    """
    timeout_segundos: int | None = Field(None, alias="timeoutSegundos", ge=1)
    """
    Tempo limite de cada entrega.
    """
    status: Status45 | None = None
    """
    Situacao. desabilitado_por_falha e aplicado automaticamente apos falhas consecutivas.
    """


class WebhookAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Webhook. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    api_client_id: UUID | None = Field(None, alias="apiClientId")
    """
    Cliente de API dono da assinatura.
    """
    nome: str | None = None
    """
    Nome do webhook, unico por tenant.
    """
    url: AnyUrl | None = None
    """
    Destino HTTPS da entrega.
    """
    eventos: list[str] | None = None
    """
    Codigos do catalogo events.yaml. Somente eventos com webhookPublico verdadeiro podem ser assinados.
    """
    cabecalhos_extras: dict[str, Any] | None = Field(None, alias="cabecalhosExtras")
    """
    Cabecalhos adicionais enviados na entrega.
    """
    max_tentativas: int | None = Field(None, alias="maxTentativas", ge=1)
    """
    Maximo de tentativas antes da dead letter queue.
    """
    timeout_segundos: int | None = Field(None, alias="timeoutSegundos", ge=1)
    """
    Tempo limite de cada entrega.
    """
    status: Status45 | None = None
    """
    Situacao. desabilitado_por_falha e aplicado automaticamente apos falhas consecutivas.
    """


class Status48(StrEnum):
    """
    Situacao da entrega. dlq e a dead letter queue: entrega desistida apos esgotar as tentativas.
    """

    pendente = "pendente"
    enviando = "enviando"
    sucesso = "sucesso"
    falha = "falha"
    dlq = "dlq"
    cancelada = "cancelada"


class WebhookEntrega(BaseModel):
    """
    Tentativa de entrega de um evento. Retentativa exponencial ate o maximo configurado; esgotado, vai para a dead letter queue.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da entrega.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    webhook_id: UUID | None = Field(None, alias="webhookId")
    """
    Webhook de destino.
    """
    evento: str | None = None
    """
    Nome do evento entregue.
    """
    evento_id: UUID | None = Field(None, alias="eventoId")
    """
    Identificador do evento de dominio. Permite ao destinatario deduplicar.
    """
    payload: dict[str, Any] | None = None
    """
    Corpo enviado, no envelope padrao de eventos.
    """
    assinatura: str | None = None
    """
    Valor do cabecalho X-Ponto-Signature enviado.
    """
    tentativa: int | None = Field(None, ge=1)
    """
    Numero da tentativa.
    """
    status: Status48 | None = None
    """
    Situacao da entrega. dlq e a dead letter queue: entrega desistida apos esgotar as tentativas.
    """
    http_status: int | None = Field(None, alias="httpStatus")
    """
    Status HTTP devolvido pelo destino.
    """
    resposta: str | None = None
    """
    Trecho da resposta do destino, para diagnostico.
    """
    duracao_ms: int | None = Field(None, alias="duracaoMs", ge=0)
    """
    Duracao da chamada em milissegundos.
    """
    erro: str | None = None
    """
    Erro observado na entrega.
    """
    proxima_tentativa_em: AwareDatetime | None = Field(None, alias="proximaTentativaEm")
    """
    Instante da proxima tentativa.
    """
    enviado_em: AwareDatetime | None = Field(None, alias="enviadoEm")
    """
    Instante do envio.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Parceiro(StrEnum):
    """
    Sistema de folha de destino.
    """

    dominio = "dominio"
    alterdata = "alterdata"
    totvs_rm = "totvs_rm"
    totvs_protheus = "totvs_protheus"
    totvs_datasul = "totvs_datasul"
    senior = "senior"
    sankhya = "sankhya"
    questor = "questor"
    fortes = "fortes"
    contmatic = "contmatic"
    generico_csv = "generico_csv"


class Formato1(StrEnum):
    """
    Formato do arquivo gerado.
    """

    csv = "csv"
    txt = "txt"
    xml = "xml"
    json = "json"
    api = "api"


class IntegracaoFolha(BaseModel):
    """
    Configuracao de exportacao para um sistema de folha. O mapeamento de rubricas traduz nossos codigos de apuracao para os codigos do parceiro.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da integracao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa da integracao.
    """
    parceiro: Parceiro | None = None
    """
    Sistema de folha de destino.
    """
    nome: str | None = None
    """
    Nome da integracao, unico por empresa.
    """
    configuracao: dict[str, Any] | None = None
    """
    Parametros especificos do parceiro.
    """
    mapeamento_rubricas: dict[str, Any] | None = Field(None, alias="mapeamentoRubricas")
    """
    De-para entre codigos de componentes de apuracao e rubricas do parceiro.
    """
    formato: Formato1 | None = None
    """
    Formato do arquivo gerado.
    """
    ativo: bool | None = None
    """
    Integracao ativa.
    """
    ultima_exportacao_em: AwareDatetime | None = Field(None, alias="ultimaExportacaoEm")
    """
    Instante da ultima exportacao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class IntegracaoFolhaCriar(BaseModel):
    """
    Dados aceitos na criacao de IntegracaoFolha.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID = Field(..., alias="empresaId")
    """
    Empresa da integracao.
    """
    parceiro: Parceiro
    """
    Sistema de folha de destino.
    """
    nome: str
    """
    Nome da integracao, unico por empresa.
    """
    configuracao: dict[str, Any] | None = None
    """
    Parametros especificos do parceiro.
    """
    mapeamento_rubricas: dict[str, Any] | None = Field(None, alias="mapeamentoRubricas")
    """
    De-para entre codigos de componentes de apuracao e rubricas do parceiro.
    """
    formato: Formato1 | None = None
    """
    Formato do arquivo gerado.
    """
    ativo: bool | None = None
    """
    Integracao ativa.
    """
    ultima_exportacao_em: AwareDatetime | None = Field(None, alias="ultimaExportacaoEm")
    """
    Instante da ultima exportacao.
    """


class Tipo33(StrEnum):
    """
    Tipo de importacao. afd_terceiro importa AFD de outro fabricante para migracao; essas marcacoes usam namespace de NSR separado.
    """

    colaboradores = "colaboradores"
    estrutura = "estrutura"
    escalas = "escalas"
    feriados = "feriados"
    marcacoes = "marcacoes"
    afd_terceiro = "afd_terceiro"
    banco_horas = "banco_horas"
    biometria = "biometria"
    afastamentos = "afastamentos"


class Origem8(StrEnum):
    """
    Formato do arquivo de origem.
    """

    csv = "csv"
    xlsx = "xlsx"
    afd = "afd"
    api = "api"
    manual = "manual"


class Status49(StrEnum):
    """
    Situacao do processamento.
    """

    recebido = "recebido"
    validando = "validando"
    processando = "processando"
    concluido = "concluido"
    concluido_com_erros = "concluido_com_erros"
    falhou = "falhou"
    cancelado = "cancelado"


class Importacao(BaseModel):
    """
    Execucao de um importador. Guarda o arquivo de origem, o resultado linha a linha e o relatorio de erros, que e o que torna a carga de milhares de registros auditavel.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da importacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa alvo da carga.
    """
    tipo: Tipo33 | None = None
    """
    Tipo de importacao. afd_terceiro importa AFD de outro fabricante para migracao; essas marcacoes usam namespace de NSR separado.
    """
    origem: Origem8 | None = None
    """
    Formato do arquivo de origem.
    """
    nome_arquivo: str | None = Field(None, alias="nomeArquivo")
    """
    Nome do arquivo enviado.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do arquivo no armazenamento de objetos.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    Hash do arquivo enviado.
    """
    parametros: dict[str, Any] | None = None
    """
    Parametros da execucao, por exemplo delimitador e modo de atualizacao.
    """
    status: Status49 | None = None
    """
    Situacao do processamento.
    """
    total_linhas: int | None = Field(None, alias="totalLinhas")
    """
    Linhas lidas do arquivo.
    """
    linhas_processadas: int | None = Field(None, alias="linhasProcessadas")
    """
    Linhas ja processadas.
    """
    linhas_sucesso: int | None = Field(None, alias="linhasSucesso")
    """
    Linhas processadas com sucesso.
    """
    linhas_erro: int | None = Field(None, alias="linhasErro")
    """
    Linhas recusadas.
    """
    relatorio_ref: str | None = Field(None, alias="relatorioRef")
    """
    Chave do relatorio de erros no armazenamento de objetos.
    """
    erros: dict[str, Any] | None = None
    """
    Erros estruturados por linha, para a interface exibir sem baixar o relatorio.
    """
    iniciado_em: AwareDatetime | None = Field(None, alias="iniciadoEm")
    """
    Instante de inicio do processamento.
    """
    concluido_em: AwareDatetime | None = Field(None, alias="concluidoEm")
    """
    Instante de conclusao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class ImportacaoCriar(BaseModel):
    """
    Dados aceitos na criacao de Importacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa alvo da carga.
    """
    tipo: Tipo33
    """
    Tipo de importacao. afd_terceiro importa AFD de outro fabricante para migracao; essas marcacoes usam namespace de NSR separado.
    """
    origem: Origem8
    """
    Formato do arquivo de origem.
    """
    nome_arquivo: str | None = Field(None, alias="nomeArquivo")
    """
    Nome do arquivo enviado.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do arquivo no armazenamento de objetos, obtida por upload previo. Obrigatoria para origem csv/xlsx, que processam um arquivo ja enviado.
    """
    parametros: dict[str, Any] | None = None
    """
    Parametros da execucao, por exemplo delimitador e modo de atualizacao.
    """
    status: Status49 | None = None
    """
    Situacao do processamento.
    """
    erros: dict[str, Any] | None = None
    """
    Erros estruturados por linha, para a interface exibir sem baixar o relatorio.
    """


class Acao(StrEnum):
    """
    Acao registrada.
    """

    criar = "criar"
    ler = "ler"
    atualizar = "atualizar"
    excluir = "excluir"
    aprovar = "aprovar"
    reprovar = "reprovar"
    exportar = "exportar"
    login = "login"
    logout = "logout"
    falha_login = "falha_login"
    fechar = "fechar"
    reabrir = "reabrir"
    assinar = "assinar"
    revogar = "revogar"
    configurar = "configurar"
    recalcular = "recalcular"


class Origem10(StrEnum):
    """
    Canal de origem da acao.
    """

    web = "web"
    mobile = "mobile"
    api = "api"
    terminal = "terminal"
    worker = "worker"
    cli = "cli"
    sistema = "sistema"


class Resultado(StrEnum):
    """
    Desfecho da acao.
    """

    sucesso = "sucesso"
    falha = "falha"
    negado = "negado"


class RegistroAuditoria(BaseModel):
    """
    Linha da trilha de auditoria ENCADEADA. Cada linha carrega o hash da anterior: remover uma linha silenciosamente quebra a cadeia e e detectavel.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do registro.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    sequencia: int | None = Field(None, ge=1)
    """
    Posicao na cadeia, sem lacunas, por tenant.
    """
    evento: str | None = None
    """
    Codigo do evento no catalogo events.yaml.
    """
    entidade: str | None = None
    """
    Nome logico da entidade afetada.
    """
    entidade_id: UUID | None = Field(None, alias="entidadeId")
    """
    Identificador da entidade afetada.
    """
    acao: Acao | None = None
    """
    Acao registrada.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario responsavel.
    """
    usuario_email: str | None = Field(None, alias="usuarioEmail")
    """
    E-mail do usuario no momento da acao.
    """
    perfil: str | None = None
    """
    Perfil exercido na acao.
    """
    delegacao_id: UUID | None = Field(None, alias="delegacaoId")
    """
    Delegacao usada, quando a acao foi exercida em nome de outro.
    """
    ip: str | None = None
    """
    Endereco de origem.
    """
    origem: Origem10 | None = None
    """
    Canal de origem da acao.
    """
    requisicao_id: str | None = Field(None, alias="requisicaoId")
    """
    Correlaciona a linha com o trace distribuido.
    """
    valor_anterior: dict[str, Any] | None = Field(None, alias="valorAnterior")
    """
    Estado antes da mudanca. Ausente em criacao.
    """
    valor_novo: dict[str, Any] | None = Field(None, alias="valorNovo")
    """
    Estado depois da mudanca.
    """
    diferenca: dict[str, Any] | None = None
    """
    Diff calculado entre anterior e novo, para leitura humana rapida.
    """
    metadados: dict[str, Any] | None = None
    """
    Contexto adicional da acao.
    """
    resultado: Resultado | None = None
    """
    Desfecho da acao.
    """
    mensagem: str | None = None
    """
    Mensagem associada ao desfecho.
    """
    ocorrido_em: AwareDatetime | None = Field(None, alias="ocorridoEm")
    """
    Instante da acao.
    """
    hash_anterior: str | None = Field(None, alias="hashAnterior", pattern="^[0-9a-f]{64}$")
    """
    Hash do registro anterior da cadeia.
    """
    hash_registro: str | None = Field(None, alias="hashRegistro", pattern="^[0-9a-f]{64}$")
    """
    SHA-256 do conteudo canonico da linha concatenado com hashAnterior.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Categoria9(StrEnum):
    """
    Categoria do dado acessado.
    """

    biometria = "biometria"
    documento = "documento"
    saude = "saude"
    remuneracao = "remuneracao"
    geolocalizacao = "geolocalizacao"
    foto = "foto"
    cpf = "cpf"
    dados_pessoais = "dados_pessoais"


class BaseLegal(StrEnum):
    """
    Hipotese legal que autoriza o tratamento.
    """

    obrigacao_legal = "obrigacao_legal"
    consentimento = "consentimento"
    execucao_contrato = "execucao_contrato"
    legitimo_interesse = "legitimo_interesse"
    exercicio_direitos = "exercicio_direitos"
    protecao_vida = "protecao_vida"


class Acao1(StrEnum):
    """
    Operacao realizada.
    """

    leitura = "leitura"
    exportacao = "exportacao"
    impressao = "impressao"
    compartilhamento = "compartilhamento"
    eliminacao = "eliminacao"


class Origem11(StrEnum):
    """
    Canal de origem.
    """

    web = "web"
    mobile = "mobile"
    api = "api"
    terminal = "terminal"
    worker = "worker"
    cli = "cli"
    sistema = "sistema"


class AcessoDadoSensivel(BaseModel):
    """
    Registro de TODA leitura de dado pessoal sensivel. Append-only. E a evidencia que a LGPD exige, incluindo o acesso de suporte da SEEG.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do acesso.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario que acessou.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Titular do dado acessado.
    """
    categoria: Categoria9 | None = None
    """
    Categoria do dado acessado.
    """
    entidade: str | None = None
    """
    Entidade acessada.
    """
    entidade_id: UUID | None = Field(None, alias="entidadeId")
    """
    Identificador do registro acessado.
    """
    finalidade: str | None = None
    """
    Motivo declarado do acesso, exigido pelo principio da finalidade.
    """
    base_legal: BaseLegal | None = Field(None, alias="baseLegal")
    """
    Hipotese legal que autoriza o tratamento.
    """
    acao: Acao1 | None = None
    """
    Operacao realizada.
    """
    quantidade_registros: int | None = Field(None, alias="quantidadeRegistros")
    """
    Volume acessado. Exportacao em massa fica evidente no relatorio.
    """
    ip: str | None = None
    """
    Endereco de origem.
    """
    origem: Origem11 | None = None
    """
    Canal de origem.
    """
    ocorrido_em: AwareDatetime | None = Field(None, alias="ocorridoEm")
    """
    Instante do acesso.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao do registro.
    """


class Finalidade(StrEnum):
    """
    Finalidade especifica autorizada.
    """

    biometria_facial = "biometria_facial"
    biometria_digital = "biometria_digital"
    geolocalizacao = "geolocalizacao"
    foto_registro = "foto_registro"
    uso_imagem = "uso_imagem"
    comunicacao = "comunicacao"


class Status51(StrEnum):
    """
    Situacao do consentimento.
    """

    pendente = "pendente"
    concedido = "concedido"
    revogado = "revogado"
    expirado = "expirado"


class Canal3(StrEnum):
    """
    Canal em que o aceite foi coletado.
    """

    app = "app"
    web = "web"
    terminal = "terminal"
    papel = "papel"
    importacao = "importacao"


class Consentimento(BaseModel):
    """
    Consentimento LGPD versionado. O registro do ponto se apoia em obrigacao legal, mas a BIOMETRIA exige consentimento especifico.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do consentimento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Titular do consentimento.
    """
    finalidade: Finalidade | None = None
    """
    Finalidade especifica autorizada.
    """
    versao_termo: str | None = Field(None, alias="versaoTermo")
    """
    Versao do texto aceito. Mudar o termo exige novo consentimento.
    """
    texto_termo_ref: str | None = Field(None, alias="textoTermoRef")
    """
    Chave do texto do termo no armazenamento de objetos.
    """
    hash_termo: str | None = Field(None, alias="hashTermo", pattern="^[0-9a-f]{64}$")
    """
    Hash do texto exato que o titular leu. Prova o que foi consentido.
    """
    status: Status51 | None = None
    """
    Situacao do consentimento.
    """
    concedido_em: AwareDatetime | None = Field(None, alias="concedidoEm")
    """
    Instante da concessao.
    """
    revogado_em: AwareDatetime | None = Field(None, alias="revogadoEm")
    """
    Instante da revogacao.
    """
    expira_em: AwareDatetime | None = Field(None, alias="expiraEm")
    """
    Instante da expiracao.
    """
    canal: Canal3 | None = None
    """
    Canal em que o aceite foi coletado.
    """
    ip: str | None = None
    """
    Endereco de origem do aceite.
    """
    evidencia_ref: str | None = Field(None, alias="evidenciaRef")
    """
    Evidencia do aceite, por exemplo o PDF do termo em papel digitalizado.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class ConsentimentoCriar(BaseModel):
    """
    Dados aceitos na criacao de Consentimento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID = Field(..., alias="colaboradorId")
    """
    Titular do consentimento.
    """
    finalidade: Finalidade
    """
    Finalidade especifica autorizada.
    """
    versao_termo: str = Field(..., alias="versaoTermo")
    """
    Versao do texto aceito. Mudar o termo exige novo consentimento.
    """
    texto_termo_ref: str | None = Field(None, alias="textoTermoRef")
    """
    Chave do texto do termo no armazenamento de objetos.
    """
    hash_termo: str | None = Field(None, alias="hashTermo", pattern="^[0-9a-f]{64}$")
    """
    Hash do texto exato que o titular leu. Prova o que foi consentido.
    """
    status: Status51 | None = None
    """
    Situacao do consentimento.
    """
    canal: Canal3 | None = None
    """
    Canal em que o aceite foi coletado.
    """
    ip: str | None = None
    """
    Endereco de origem do aceite.
    """
    evidencia_ref: str | None = Field(None, alias="evidenciaRef")
    """
    Evidencia do aceite, por exemplo o PDF do termo em papel digitalizado.
    """


class Tipo35(StrEnum):
    """
    Direito exercido. eliminacao nao apaga marcacao: o dado de ponto tem guarda obrigatoria e a recusa parcial precisa ser fundamentada.
    """

    acesso = "acesso"
    correcao = "correcao"
    portabilidade = "portabilidade"
    eliminacao = "eliminacao"
    anonimizacao = "anonimizacao"
    revogacao_consentimento = "revogacao_consentimento"
    informacao_compartilhamento = "informacao_compartilhamento"
    oposicao = "oposicao"


class Status53(StrEnum):
    """
    Situacao do pedido.
    """

    recebida = "recebida"
    em_analise = "em_analise"
    atendida = "atendida"
    parcialmente_atendida = "parcialmente_atendida"
    recusada = "recusada"
    cancelada = "cancelada"


class SolicitacaoTitular(BaseModel):
    """
    Pedido de titular de dados previsto na LGPD. Guarda protocolo, prazo de resposta e o arquivo entregue, que e a evidencia de atendimento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da solicitacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular, quando identificado.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario titular, quando identificado.
    """
    protocolo: str | None = None
    """
    Numero de protocolo do pedido.
    """
    requerente_nome: str | None = Field(None, alias="requerenteNome")
    """
    Nome do requerente.
    """
    requerente_cpf: str | None = Field(None, alias="requerenteCpf", pattern="^[0-9]{11}$")
    """
    CPF do requerente.
    """
    requerente_email: EmailStr | None = Field(None, alias="requerenteEmail")
    """
    E-mail do requerente.
    """
    tipo: Tipo35 | None = None
    """
    Direito exercido. eliminacao nao apaga marcacao: o dado de ponto tem guarda obrigatoria e a recusa parcial precisa ser fundamentada.
    """
    descricao: str | None = None
    """
    Descricao do pedido.
    """
    status: Status53 | None = None
    """
    Situacao do pedido.
    """
    prazo_em: date | None = Field(None, alias="prazoEm")
    """
    Prazo legal de resposta.
    """
    resposta: str | None = None
    """
    Texto da resposta ao titular.
    """
    resposta_ref: str | None = Field(None, alias="respostaRef")
    """
    Chave do pacote de dados entregue, por exemplo o export de portabilidade.
    """
    respondido_em: AwareDatetime | None = Field(None, alias="respondidoEm")
    """
    Instante da resposta.
    """
    respondido_por: UUID | None = Field(None, alias="respondidoPor")
    """
    Usuario que respondeu.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class SolicitacaoTitularCriar(BaseModel):
    """
    Dados aceitos na criacao de SolicitacaoTitular.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular, quando identificado.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario titular, quando identificado.
    """
    requerente_nome: str = Field(..., alias="requerenteNome")
    """
    Nome do requerente.
    """
    requerente_cpf: str | None = Field(None, alias="requerenteCpf", pattern="^[0-9]{11}$")
    """
    CPF do requerente.
    """
    requerente_email: EmailStr | None = Field(None, alias="requerenteEmail")
    """
    E-mail do requerente.
    """
    tipo: Tipo35
    """
    Direito exercido. eliminacao nao apaga marcacao: o dado de ponto tem guarda obrigatoria e a recusa parcial precisa ser fundamentada.
    """
    descricao: str | None = None
    """
    Descricao do pedido.
    """
    status: Status53 | None = None
    """
    Situacao do pedido.
    """
    resposta: str | None = None
    """
    Texto da resposta ao titular.
    """
    resposta_ref: str | None = Field(None, alias="respostaRef")
    """
    Chave do pacote de dados entregue, por exemplo o export de portabilidade.
    """


class Categoria10(StrEnum):
    """
    Categoria do relatorio.
    """

    operacional = "operacional"
    gerencial = "gerencial"
    fiscal = "fiscal"
    financeiro = "financeiro"
    lgpd = "lgpd"


class RelatorioDefinicao(BaseModel):
    """
    Item do catalogo de relatorios. Os 24 relatorios do produto sao semeados por tenant; o cliente pode criar variantes proprias.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da definicao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo estavel do relatorio, usado na URL de execucao.
    """
    nome: str | None = None
    """
    Nome do relatorio.
    """
    descricao: str | None = None
    """
    Descricao do que o relatorio entrega.
    """
    categoria: Categoria10 | None = None
    """
    Categoria do relatorio.
    """
    sistema: bool | None = None
    """
    Relatorio de fabrica, semeado em todo tenant.
    """
    dataset: str | None = None
    """
    Identificador do conjunto de dados no backend. NUNCA SQL cru vindo do usuario: e o que impede injecao por configuracao.
    """
    colunas_disponiveis: dict[str, Any] | None = Field(None, alias="colunasDisponiveis")
    """
    Catalogo de colunas. O espelho de jornada expoe mais de 30 colunas configuraveis.
    """
    filtros_disponiveis: dict[str, Any] | None = Field(None, alias="filtrosDisponiveis")
    """
    Catalogo de filtros aceitos.
    """
    agrupamentos: dict[str, Any] | None = None
    """
    Agrupamentos aceitos.
    """
    formatos: list[str] | None = None
    """
    Formatos de exportacao disponiveis.
    """
    permissao_codigo: str | None = Field(None, alias="permissaoCodigo")
    """
    Permissao exigida para executar o relatorio.
    """
    assincrono: bool | None = None
    """
    Verdadeiro para relatorios pesados, executados por worker com progresso.
    """
    ativo: bool | None = None
    """
    Relatorio ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class Formato3(StrEnum):
    """
    Formato do artefato gerado.
    """

    csv = "csv"
    xlsx = "xlsx"
    pdf = "pdf"
    json = "json"


class Status55(StrEnum):
    """
    Situacao da execucao.
    """

    enfileirado = "enfileirado"
    processando = "processando"
    concluido = "concluido"
    falhou = "falhou"
    cancelado = "cancelado"
    expirado = "expirado"


class RelatorioExecucao(BaseModel):
    """
    Execucao de um relatorio, sincrona ou assincrona. Guarda parametros, progresso e o artefato gerado, com expiracao para nao acumular arquivo indefinidamente.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da execucao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    relatorio_definicao_id: UUID | None = Field(None, alias="relatorioDefinicaoId")
    """
    Relatorio executado.
    """
    relatorio_codigo: str | None = Field(None, alias="relatorioCodigo")
    """
    Codigo do relatorio executado.
    """
    agendamento_id: UUID | None = Field(None, alias="agendamentoId")
    """
    Agendamento que disparou a execucao.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario que solicitou.
    """
    parametros: dict[str, Any] | None = None
    """
    Parametros aplicados na execucao.
    """
    formato: Formato3 | None = None
    """
    Formato do artefato gerado.
    """
    status: Status55 | None = None
    """
    Situacao da execucao.
    """
    progresso: int | None = Field(None, ge=0, le=100)
    """
    Percentual concluido, exibido durante execucoes longas.
    """
    total_linhas: int | None = Field(None, alias="totalLinhas")
    """
    Linhas do resultado.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do artefato no armazenamento de objetos.
    """
    url_download: AnyUrl | None = Field(None, alias="urlDownload")
    """
    URL temporaria de download do artefato.
    """
    tamanho_bytes: int | None = Field(None, alias="tamanhoBytes", ge=0)
    """
    Tamanho do artefato em bytes.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    Hash do artefato gerado.
    """
    iniciado_em: AwareDatetime | None = Field(None, alias="iniciadoEm")
    """
    Instante de inicio.
    """
    concluido_em: AwareDatetime | None = Field(None, alias="concluidoEm")
    """
    Instante de conclusao.
    """
    duracao_ms: int | None = Field(None, alias="duracaoMs", ge=0)
    """
    Duracao da execucao em milissegundos.
    """
    expira_em: AwareDatetime | None = Field(None, alias="expiraEm")
    """
    Momento em que o artefato e removido pela politica de retencao.
    """
    erro: str | None = None
    """
    Mensagem de erro quando a execucao falha.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Canal5(StrEnum):
    """
    Canal de entrega.
    """

    email = "email"
    webhook = "webhook"
    minio = "minio"


class RelatorioAgendamento(BaseModel):
    """
    Envio recorrente de relatorio. A expressao cron e interpretada no fuso indicado, nao no fuso do servidor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do agendamento.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    relatorio_definicao_id: UUID | None = Field(None, alias="relatorioDefinicaoId")
    """
    Relatorio agendado.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario dono do agendamento.
    """
    nome: str | None = None
    """
    Nome do agendamento, unico por tenant.
    """
    parametros: dict[str, Any] | None = None
    """
    Parametros aplicados a cada execucao.
    """
    formato: Formato3 | None = None
    """
    Formato do artefato gerado.
    """
    cron: str | None = None
    """
    Expressao cron da recorrencia.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso em que a expressao cron e interpretada.
    """
    canal: Canal5 | None = None
    """
    Canal de entrega.
    """
    destinatarios: list[str] | None = None
    """
    Enderecos de e-mail ou URLs de webhook conforme o canal.
    """
    ativo: bool | None = None
    """
    Agendamento ativo.
    """
    ultima_execucao_em: AwareDatetime | None = Field(None, alias="ultimaExecucaoEm")
    """
    Instante da ultima execucao.
    """
    proxima_execucao_em: AwareDatetime | None = Field(None, alias="proximaExecucaoEm")
    """
    Instante da proxima execucao.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class RelatorioAgendamentoCriar(BaseModel):
    """
    Dados aceitos na criacao de RelatorioAgendamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    relatorio_definicao_id: UUID = Field(..., alias="relatorioDefinicaoId")
    """
    Relatorio agendado.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario dono do agendamento.
    """
    nome: str
    """
    Nome do agendamento, unico por tenant.
    """
    parametros: dict[str, Any] | None = None
    """
    Parametros aplicados a cada execucao.
    """
    formato: Formato3 | None = None
    """
    Formato do artefato gerado.
    """
    cron: str
    """
    Expressao cron da recorrencia.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso em que a expressao cron e interpretada.
    """
    canal: Canal5 | None = None
    """
    Canal de entrega.
    """
    destinatarios: list[str] | None = None
    """
    Enderecos de e-mail ou URLs de webhook conforme o canal.
    """
    ativo: bool | None = None
    """
    Agendamento ativo.
    """


class Tipo37(StrEnum):
    """
    humano: pessoa. servico: conta tecnica de integracao. suporte: operador da SEEG com acesso controlado.
    """

    humano = "humano"
    servico = "servico"
    suporte = "suporte"


class Status56(StrEnum):
    """
    convidado: criado e ainda sem primeiro acesso. bloqueado: barrado por seguranca. inativo: desligado.
    """

    convidado = "convidado"
    ativo = "ativo"
    bloqueado = "bloqueado"
    inativo = "inativo"


class EscopoTipo(StrEnum):
    """
    Define qual campo de escopo e obrigatorio. proprio restringe ao proprio colaborador do usuario.
    """

    tenant = "tenant"
    empresa = "empresa"
    unidade = "unidade"
    departamento = "departamento"
    equipe = "equipe"
    proprio = "proprio"


class UsuarioPerfil(BaseModel):
    """
    Atribuicao de perfil a usuario COM ESCOPO. O mesmo usuario pode ser gestor de uma unidade e colaborador comum no resto da empresa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da atribuicao.
    """
    perfil_id: UUID | None = Field(None, alias="perfilId")
    """
    Perfil atribuido.
    """
    perfil_codigo: str | None = Field(None, alias="perfilCodigo")
    """
    Codigo do perfil atribuido.
    """
    escopo_tipo: EscopoTipo | None = Field(None, alias="escopoTipo")
    """
    Define qual campo de escopo e obrigatorio. proprio restringe ao proprio colaborador do usuario.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do escopo.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade do escopo.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento do escopo.
    """
    equipe_id: UUID | None = Field(None, alias="equipeId")
    """
    Equipe do escopo.
    """
    incluir_subordinados: bool | None = Field(None, alias="incluirSubordinados")
    """
    Quando verdadeiro, o escopo desce pela arvore de departamentos e pela hierarquia de gestores.
    """
    vigencia_inicio: date | None = Field(None, alias="vigenciaInicio")
    """
    Inicio da vigencia.
    """
    vigencia_fim: date | None = Field(None, alias="vigenciaFim")
    """
    Fim da vigencia. Ausente significa vigencia aberta.
    """


class EscopoPadrao(StrEnum):
    """
    Alcance sugerido ao atribuir o perfil.
    """

    global_ = "global"
    tenant = "tenant"
    empresa = "empresa"
    unidade = "unidade"
    departamento = "departamento"
    equipe = "equipe"
    proprio = "proprio"


class Perfil(BaseModel):
    """
    Papel do RBAC. Os perfis de fabrica sao super_admin, admin_empresa, rh, gestor, colaborador, auditor e integracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do perfil.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    codigo: str | None = None
    """
    Codigo unico por tenant.
    """
    nome: str | None = None
    """
    Nome do perfil.
    """
    descricao: str | None = None
    """
    Descricao do papel.
    """
    sistema: bool | None = None
    """
    Perfil de fabrica, semeado em todo tenant. Nao pode ser excluido.
    """
    escopo_padrao: EscopoPadrao | None = Field(None, alias="escopoPadrao")
    """
    Alcance sugerido ao atribuir o perfil.
    """
    somente_leitura: bool | None = Field(None, alias="somenteLeitura")
    """
    Perfil que nunca recebe permissao de escrita, como auditor e fiscal.
    """
    permissoes: list[str] | None = None
    """
    Codigos de permissao concedidos ao perfil.
    """
    ativo: bool | None = None
    """
    Perfil ativo.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class PerfilCriar(BaseModel):
    """
    Dados aceitos na criacao de Perfil.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    codigo: str
    """
    Codigo unico por tenant.
    """
    nome: str
    """
    Nome do perfil.
    """
    descricao: str | None = None
    """
    Descricao do papel.
    """
    sistema: bool | None = None
    """
    Perfil de fabrica, semeado em todo tenant. Nao pode ser excluido.
    """
    escopo_padrao: EscopoPadrao | None = Field(None, alias="escopoPadrao")
    """
    Alcance sugerido ao atribuir o perfil.
    """
    somente_leitura: bool | None = Field(None, alias="somenteLeitura")
    """
    Perfil que nunca recebe permissao de escrita, como auditor e fiscal.
    """
    permissoes: list[str] | None = None
    """
    Codigos de permissao concedidos ao perfil.
    """
    ativo: bool | None = None
    """
    Perfil ativo.
    """


class Acao2(StrEnum):
    """
    Acao permitida.
    """

    ler = "ler"
    criar = "criar"
    editar = "editar"
    excluir = "excluir"
    aprovar = "aprovar"
    exportar = "exportar"
    executar = "executar"
    assinar = "assinar"
    administrar = "administrar"
    configurar = "configurar"
    reabrir = "reabrir"
    ler_sensivel = "ler_sensivel"


class Permissao(BaseModel):
    """
    Item do catalogo GLOBAL de permissoes do produto. Corresponde a um par recurso e acao e e identico em todos os tenants.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da permissao.
    """
    codigo: str | None = None
    """
    Identificador estavel usado no codigo e no OpenAPI, por exemplo marcacoes.ler.
    """
    recurso: str | None = None
    """
    Recurso alvo da permissao.
    """
    acao: Acao2 | None = None
    """
    Acao permitida.
    """
    descricao: str | None = None
    """
    Descricao da permissao.
    """
    sensivel: bool | None = None
    """
    Quando verdadeira, todo exercicio da permissao gera registro de acesso a dado sensivel.
    """
    modulo: str | None = None
    """
    Modulo funcional ao qual a permissao pertence.
    """


class Tipo40(StrEnum):
    """
    Natureza do cliente.
    """

    confidencial = "confidencial"
    publico = "publico"
    maquina = "maquina"


class Ambiente(StrEnum):
    """
    Ambiente do cliente. Credencial de sandbox nao vale em producao.
    """

    sandbox = "sandbox"
    producao = "producao"


class Status59(StrEnum):
    """
    Situacao do cliente.
    """

    ativo = "ativo"
    suspenso = "suspenso"
    revogado = "revogado"


class ApiClient(BaseModel):
    """
    Aplicacao integradora autorizada a consumir a API publica. Cada cliente vive em um ambiente e carrega seus proprios escopos e limite de taxa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do cliente.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do cliente.
    """
    nome: str | None = None
    """
    Nome do cliente, unico por tenant.
    """
    descricao: str | None = None
    """
    Descricao da integracao.
    """
    client_id: str | None = Field(None, alias="clientId")
    """
    Identificador publico do cliente OAuth.
    """
    tipo: Tipo40 | None = None
    """
    Natureza do cliente.
    """
    ambiente: Ambiente | None = None
    """
    Ambiente do cliente. Credencial de sandbox nao vale em producao.
    """
    escopos: list[str] | None = None
    """
    Escopos OAuth concedidos.
    """
    redirect_uris: list[str] | None = Field(None, alias="redirectUris")
    """
    URIs de redirecionamento autorizadas.
    """
    ips_permitidos: list[str] | None = Field(None, alias="ipsPermitidos")
    """
    Restricao opcional de origem por faixa CIDR.
    """
    rate_limit_por_minuto: int | None = Field(None, alias="rateLimitPorMinuto", ge=1)
    """
    Cota de requisicoes por minuto.
    """
    contato_email: EmailStr | None = Field(None, alias="contatoEmail")
    """
    E-mail de contato tecnico.
    """
    status: Status59 | None = None
    """
    Situacao do cliente.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class ApiClientCriar(BaseModel):
    """
    Dados aceitos na criacao de ApiClient.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    nome: str
    """
    Nome do cliente, unico por tenant.
    """
    descricao: str | None = None
    """
    Descricao da integracao.
    """
    tipo: Tipo40 | None = None
    """
    Natureza do cliente.
    """
    ambiente: Ambiente | None = None
    """
    Ambiente do cliente. Credencial de sandbox nao vale em producao.
    """
    escopos: list[str]
    """
    Escopos OAuth concedidos.
    """
    redirect_uris: list[str] | None = Field(None, alias="redirectUris")
    """
    URIs de redirecionamento autorizadas.
    """
    ips_permitidos: list[str] | None = Field(None, alias="ipsPermitidos")
    """
    Restricao opcional de origem por faixa CIDR.
    """
    rate_limit_por_minuto: int | None = Field(None, alias="rateLimitPorMinuto", ge=1)
    """
    Cota de requisicoes por minuto.
    """
    contato_email: EmailStr | None = Field(None, alias="contatoEmail")
    """
    E-mail de contato tecnico.
    """
    status: Status59 | None = None
    """
    Situacao do cliente.
    """


class LoginRequisicao(BaseModel):
    """
    Credenciais de acesso do usuario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    email: EmailStr | None = None
    """
    E-mail de acesso do usuario.
    """
    senha: SecretStr | None = Field(None, max_length=128, min_length=8)
    """
    Senha em claro. Trafega apenas sob TLS 1.3 e nunca e registrada em log.
    """
    tenant: str | None = None
    """
    Slug do tenant. Dispensavel quando o acesso e por subdominio do cliente.
    """
    dispositivo_identificador: str | None = Field(None, alias="dispositivoIdentificador")
    """
    Identificador do aparelho, para vincular a sessao ao dispositivo.
    """
    fingerprint: str | None = None
    """
    Impressao digital do navegador ou do aparelho, usada como sinal antifraude.
    """


class Metodo1(StrEnum):
    """
    Metodo utilizado.
    """

    totp = "totp"
    sms = "sms"
    email = "email"
    webauthn = "webauthn"
    codigos_backup = "codigos_backup"


class MfaVerificacaoRequisicao(BaseModel):
    """
    Resposta ao desafio de segundo fator.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    desafio_id: UUID | None = Field(None, alias="desafioId")
    """
    Desafio recebido no login.
    """
    codigo: str | None = Field(None, max_length=512, min_length=6)
    """
    Codigo TOTP, codigo de backup ou assercao WebAuthn.
    """
    metodo: Metodo1 | None = None
    """
    Metodo utilizado.
    """
    confiar_neste_dispositivo: bool | None = Field(None, alias="confiarNesteDispositivo")
    """
    Dispensa o segundo fator neste aparelho por 30 dias.
    """


class RefreshRequisicao(BaseModel):
    """
    Renovacao de sessao por rotacao de refresh token.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    refresh_token: str | None = Field(None, alias="refreshToken")
    """
    Refresh token vigente. E consumido nesta chamada e substituido por um novo.
    """


class LogoutRequisicao(BaseModel):
    """
    Encerramento de sessao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    refresh_token: str | None = Field(None, alias="refreshToken")
    """
    Refresh token da sessao a encerrar.
    """
    todas_as_sessoes: bool | None = Field(None, alias="todasAsSessoes")
    """
    Quando verdadeiro, revoga todas as sessoes do usuario.
    """


class ReautenticacaoRequisicao(BaseModel):
    """
    Reautenticacao exigida para registrar ponto pela web e para operacoes sensiveis, mesmo com sessao valida.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    senha: SecretStr | None = None
    """
    Senha do usuario.
    """
    codigo_mfa: str | None = Field(None, alias="codigoMfa")
    """
    Codigo de segundo fator, quando exigido pela politica.
    """


class ReautenticacaoResposta(BaseModel):
    """
    Comprovante de reautenticacao recente, exigido pelas operacoes sensiveis.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    reautenticado_em: AwareDatetime | None = Field(None, alias="reautenticadoEm")
    """
    Instante da reautenticacao.
    """
    valido_ate: AwareDatetime | None = Field(None, alias="validoAte")
    """
    Instante ate o qual a reautenticacao e aceita.
    """
    token_operacao: str | None = Field(None, alias="tokenOperacao")
    """
    Token de curta duracao a ser enviado na operacao sensivel subsequente.
    """


class RecuperacaoSenhaRequisicao(BaseModel):
    """
    Pedido de recuperacao de senha. A resposta e sempre 202, exista ou nao a conta, para nao permitir enumeracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    email: EmailStr | None = None
    """
    E-mail da conta.
    """
    tenant: str | None = None
    """
    Slug do tenant, quando o acesso nao e por subdominio.
    """


class RedefinicaoSenhaRequisicao(BaseModel):
    """
    Redefinicao de senha com token de uso unico recebido por e-mail.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    token: str | None = None
    """
    Token de recuperacao de uso unico.
    """
    nova_senha: SecretStr | None = Field(None, alias="novaSenha", max_length=128, min_length=12)
    """
    Nova senha. Sera armazenada com Argon2id.
    """


class GrantType(StrEnum):
    """
    Fluxo utilizado. Somente client_credentials e suportado.
    """

    client_credentials = "client_credentials"


class TokenOAuthRequisicao(BaseModel):
    """
    Emissao de token no fluxo OAuth 2.0 client credentials, para integracoes maquina a maquina.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    grant_type: GrantType | None = Field(None, alias="grantType")
    """
    Fluxo utilizado. Somente client_credentials e suportado.
    """
    client_id: str | None = Field(None, alias="clientId")
    """
    Identificador publico do cliente.
    """
    client_secret: SecretStr | None = Field(None, alias="clientSecret")
    """
    Segredo do cliente.
    """
    scope: str | None = None
    """
    Escopos pedidos, separados por espaco. Subconjunto dos escopos do cliente.
    """


class TokenOAuthResposta(BaseModel):
    """
    Token de acesso emitido para o cliente de integracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    access_token: str | None = Field(None, alias="accessToken")
    """
    Token de acesso.
    """
    token_type: str | None = Field(None, alias="tokenType")
    """
    Tipo do token. Sempre Bearer.
    """
    expires_in: int | None = Field(None, alias="expiresIn")
    """
    Validade em segundos.
    """
    scope: str | None = None
    """
    Escopos efetivamente concedidos.
    """


class Canal7(StrEnum):
    """
    Canal de acesso.
    """

    web = "web"
    mobile = "mobile"
    totem = "totem"
    api = "api"
    terminal = "terminal"


class MotivoEncerramento(StrEnum):
    """
    Motivo do encerramento.
    """

    logout = "logout"
    expiracao = "expiracao"
    inatividade = "inatividade"
    revogacao_admin = "revogacao_admin"
    troca_senha = "troca_senha"
    reuso_token = "reuso_token"
    dispositivo_revogado = "dispositivo_revogado"


class Sessao(BaseModel):
    """
    Sessao de acesso ativa ou encerrada. Agrupa a familia de refresh tokens e permite revogacao em massa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da sessao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant da sessao.
    """
    usuario_id: UUID | None = Field(None, alias="usuarioId")
    """
    Usuario autenticado.
    """
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo de origem.
    """
    canal: Canal7 | None = None
    """
    Canal de acesso.
    """
    ip: str | None = None
    """
    Endereco de origem.
    """
    user_agent: str | None = Field(None, alias="userAgent")
    """
    User agent do cliente.
    """
    fingerprint: str | None = None
    """
    Impressao digital do navegador ou aparelho.
    """
    iniciada_em: AwareDatetime | None = Field(None, alias="iniciadaEm")
    """
    Inicio da sessao.
    """
    ultima_atividade_em: AwareDatetime | None = Field(None, alias="ultimaAtividadeEm")
    """
    Ultima atividade registrada.
    """
    expira_em: AwareDatetime | None = Field(None, alias="expiraEm")
    """
    Expiracao da sessao.
    """
    encerrada_em: AwareDatetime | None = Field(None, alias="encerradaEm")
    """
    Instante do encerramento.
    """
    motivo_encerramento: MotivoEncerramento | None = Field(None, alias="motivoEncerramento")
    """
    Motivo do encerramento.
    """
    atual: bool | None = None
    """
    Verdadeiro quando e a sessao que fez a requisicao.
    """


class Canal8(StrEnum):
    """
    Canal de origem. importacao nao e aceito aqui: carga historica usa o importador.
    """

    terminal = "terminal"
    mobile = "mobile"
    web = "web"
    totem = "totem"
    api = "api"


class SentidoInformado1(StrEnum):
    """
    Sentido informado pelo coletor, quando ele informa. Nao substitui o pareamento feito na apuracao.
    """

    entrada = "entrada"
    saida = "saida"
    indefinido = "indefinido"


class MarcacaoCriar(BaseModel):
    """
    Requisicao de registro de ponto, identica em todos os canais. O servidor e quem carimba a hora, atribui o NSR e emite o comprovante.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador identificado. Alternativa a informar cpf ou matricula.
    """
    cpf: str | None = Field(None, pattern="^[0-9]{11}$")
    """
    CPF do colaborador, quando o identificador interno nao e conhecido pelo integrador.
    """
    matricula: str | None = None
    """
    Matricula interna, usada por terminal e quiosque.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do registro. Inferida do colaborador quando ausente.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade de origem do registro.
    """
    canal: Canal8 | None = None
    """
    Canal de origem. importacao nao e aceito aqui: carga historica usa o importador.
    """
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo que originou o registro.
    """
    terminal_id: UUID | None = Field(None, alias="terminalId")
    """
    Terminal coletor, quando o canal e terminal.
    """
    datahora_dispositivo: AwareDatetime | None = Field(None, alias="datahoraDispositivo")
    """
    Relogio do aparelho no momento da captura. Guardado como evidencia; NAO define o horario do fato.
    """
    datahora_coleta: AwareDatetime | None = Field(None, alias="datahoraColeta")
    """
    Momento real da captura, usado apenas em sincronizacao offline e em catch-up de terminal. Ignorado no registro online.
    """
    coletada_offline: bool | None = Field(None, alias="coletadaOffline")
    """
    Verdadeiro quando o registro vem de fila offline.
    """
    sentido_informado: SentidoInformado1 | None = Field(None, alias="sentidoInformado")
    """
    Sentido informado pelo coletor, quando ele informa. Nao substitui o pareamento feito na apuracao.
    """
    external_id: str | None = Field(None, alias="externalId")
    """
    Chave de idempotencia do integrador. Junto com o canal forma uma chave unica no tenant.
    """
    log_externo_id: int | None = Field(None, alias="logExternoId")
    """
    Identificador do registro de acesso no terminal, para idempotencia do catch-up.
    """
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    """
    Latitude da captura.
    """
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    """
    Longitude da captura.
    """
    precisao_metros: float | None = Field(None, alias="precisaoMetros", ge=0.0)
    """
    Precisao do sinal de localizacao, em metros.
    """
    wifi_bssid: str | None = Field(None, alias="wifiBssid")
    """
    BSSID do ponto de acesso, usado para corroborar o GPS.
    """
    foto_base64: str | None = Field(None, alias="fotoBase64")
    """
    Captura ao vivo em base64, quando a politica exige facial. NUNCA aceita upload de arquivo previamente salvo.
    """
    liveness_metodo: LivenessMetodo | None = Field(None, alias="livenessMetodo")
    """
    Metodo de prova de vida aplicado.
    """
    liveness_evidencia: dict[str, Any] | None = Field(None, alias="livenessEvidencia")
    """
    Evidencia do desafio de vivacidade executado.
    """
    flags_integridade: dict[str, Any] | None = Field(None, alias="flagsIntegridade")
    """
    Sinais de integridade do ambiente coletados pelo cliente (attestation, RASP, modo desenvolvedor, mock location).
    """
    attestation_token: str | None = Field(None, alias="attestationToken")
    """
    Token de Play Integrity ou App Attest. O veredito e SEMPRE verificado no servidor, nunca no cliente.
    """
    assinatura_payload: str | None = Field(None, alias="assinaturaPayload")
    """
    Assinatura do payload com a chave do keystore ou secure enclave do aparelho.
    """
    observacao: str | None = None
    """
    Observacao livre do integrador.
    """


class ClassificacaoConfianca1(StrEnum):
    """
    Faixa resultante da politica de registro.
    """

    alta = "alta"
    media = "media"
    baixa = "baixa"
    bloqueada = "bloqueada"


class MarcacaoCriada(BaseModel):
    """
    Resultado do registro de ponto: a marcacao gravada, o comprovante emitido e a avaliacao de risco do servidor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    marcacao: Marcacao | None = None
    """
    Marcacao gravada, ja com NSR e hash encadeado.
    """
    comprovante: Comprovante | None = None
    """
    Comprovante emitido na mesma transacao.
    """
    score_confianca: int | None = Field(None, alias="scoreConfianca", ge=0, le=100)
    """
    Score de confianca composto calculado no servidor.
    """
    classificacao_confianca: ClassificacaoConfianca1 | None = Field(
        None, alias="classificacaoConfianca"
    )
    """
    Faixa resultante da politica de registro.
    """
    revisao_requerida: bool | None = Field(None, alias="revisaoRequerida")
    """
    Verdadeiro quando a marcacao entrou na fila de revisao do gestor.
    """
    dentro_geocerca: bool | None = Field(None, alias="dentroGeocerca")
    """
    Resultado da avaliacao da geocerca, quando aplicavel.
    """
    avisos: list[str] | None = None
    """
    Avisos nao bloqueantes, por exemplo registro fora da geocerca aceito por politica de sinalizacao.
    """
    duplicada: bool | None = None
    """
    Verdadeiro quando a chave de idempotencia ja existia: a marcacao devolvida e a original, e nenhuma nova foi criada.
    """


class ItemFilaOffline(BaseModel):
    """
    Item capturado sem rede, cifrado e assinado no aparelho.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    contador_monotonico: int | None = Field(None, alias="contadorMonotonico", ge=0)
    """
    Contador que so cresce, por dispositivo. Reapresentar um valor ja usado caracteriza replay.
    """
    payload_cifrado: Base64Str | None = Field(None, alias="payloadCifrado")
    """
    Item cifrado em AES-256-GCM, codificado em base64.
    """
    iv: Base64Str | None = None
    """
    Vetor de inicializacao da cifra, em base64.
    """
    hmac: str | None = None
    """
    HMAC do item calculado no aparelho. Item com HMAC invalido e rejeitado.
    """
    datahora_dispositivo: AwareDatetime | None = Field(None, alias="datahoraDispositivo")
    """
    Relogio civil do aparelho no instante da captura.
    """
    tempo_monotonico_ms: int | None = Field(None, alias="tempoMonotonicoMs")
    """
    Relogio monotonico do aparelho no instante da captura. Permite classificar a confianca temporal mesmo com o relogio civil adulterado.
    """


class SincronizacaoOfflineRequisicao(BaseModel):
    """
    Lote de itens capturados sem rede. O servidor valida HMAC e contador antes de converter cada item em marcacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dispositivo_id: UUID | None = Field(None, alias="dispositivoId")
    """
    Dispositivo que originou as capturas.
    """
    itens: list[ItemFilaOffline] | None = None
    """
    Itens da fila, em ordem crescente de contador.
    """


class Status61(StrEnum):
    """
    Desfecho do item.
    """

    processado = "processado"
    duplicado = "duplicado"
    rejeitado = "rejeitado"
    expirado = "expirado"


class ResultadoItemOffline(BaseModel):
    """
    Desfecho do processamento de um item da fila offline.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    contador_monotonico: int | None = Field(None, alias="contadorMonotonico")
    """
    Contador do item processado.
    """
    status: Status61 | None = None
    """
    Desfecho do item.
    """
    marcacao_id: UUID | None = Field(None, alias="marcacaoId")
    """
    Marcacao criada, quando o item foi processado.
    """
    nsr: int | None = None
    """
    NSR atribuido, quando o item foi processado.
    """
    codigo_erro: str | None = Field(None, alias="codigoErro")
    """
    Codigo do catalogo de erros, quando o item foi rejeitado ou expirou.
    """
    mensagem: str | None = None
    """
    Explicacao do desfecho.
    """


class SincronizacaoOfflineResposta(BaseModel):
    """
    Resultado do processamento do lote offline, item a item. Itens vencidos viram ocorrencia, nunca marcacao silenciosa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    processados: int | None = None
    """
    Itens convertidos em marcacao.
    """
    duplicados: int | None = None
    """
    Itens ja conhecidos, ignorados por idempotencia.
    """
    rejeitados: int | None = None
    """
    Itens recusados por assinatura, replay ou regra.
    """
    expirados: int | None = None
    """
    Itens fora do prazo de sincronizacao, convertidos em ocorrencia.
    """
    resultados: list[ResultadoItemOffline] | None = None
    """
    Desfecho de cada item enviado.
    """


class VerificacaoNsr(BaseModel):
    """
    Resultado da verificacao de continuidade da sequencia de NSR de um REP-P.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P verificado.
    """
    nsr_inicial: int | None = Field(None, alias="nsrInicial")
    """
    Primeiro NSR verificado.
    """
    nsr_final: int | None = Field(None, alias="nsrFinal")
    """
    Ultimo NSR verificado.
    """
    total_esperado: int | None = Field(None, alias="totalEsperado")
    """
    Quantidade de registros esperada na faixa.
    """
    total_encontrado: int | None = Field(None, alias="totalEncontrado")
    """
    Quantidade de registros encontrada.
    """
    integro: bool | None = None
    """
    Verdadeiro quando nao ha lacuna nem repeticao.
    """
    lacunas: dict[str, Any] | None = None
    """
    Faixas de NSR ausentes, quando houver.
    """
    cadeia_hash_integra: bool | None = Field(None, alias="cadeiaHashIntegra")
    """
    Verdadeiro quando a cadeia de hash encadeado confere de ponta a ponta.
    """
    verificado_em: AwareDatetime | None = Field(None, alias="verificadoEm")
    """
    Instante da verificacao.
    """


class Decisao1(StrEnum):
    """
    Decisao tomada.
    """

    aprovar = "aprovar"
    reprovar = "reprovar"


class DecisaoRequisicao(BaseModel):
    """
    Decisao sobre um item pendente de aprovacao (tratamento, solicitacao ou etapa de aprovacao).
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    decisao: Decisao1 | None = None
    """
    Decisao tomada.
    """
    comentario: str | None = None
    """
    Comentario do decisor. Obrigatorio na reprovacao.
    """
    delegacao_id: UUID | None = Field(None, alias="delegacaoId")
    """
    Delegacao usada, quando a decisao e exercida em nome de outro.
    """


class Motivo(StrEnum):
    """
    Insumo que justifica o reprocessamento. Vai para a auditoria.
    """

    tratamento = "tratamento"
    afastamento = "afastamento"
    jornada = "jornada"
    escala = "escala"
    feriado = "feriado"
    marcacao_tardia = "marcacao_tardia"
    politica_banco = "politica_banco"
    manual = "manual"


class RecalculoRequisicao(BaseModel):
    """
    Pedido de reprocessamento determinístico de um intervalo. Recalcular duas vezes o mesmo periodo produz exatamente o mesmo resultado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa alvo. Obrigatorio quando nao ha vinculos informados.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Restringe o recalculo a uma unidade.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Restringe o recalculo a um departamento.
    """
    vinculo_ids: list[UUID] | None = Field(None, alias="vinculoIds")
    """
    Vinculos especificos a reprocessar.
    """
    colaborador_ids: list[UUID] | None = Field(None, alias="colaboradorIds")
    """
    Colaboradores especificos a reprocessar.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Primeiro dia do intervalo.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do intervalo.
    """
    motivo: Motivo | None = None
    """
    Insumo que justifica o reprocessamento. Vai para a auditoria.
    """
    forcar: bool | None = None
    """
    Ignora o hash de entrada e reprocessa mesmo sem mudanca de insumo. Use apenas em diagnostico.
    """


class Tipo42(StrEnum):
    """
    Natureza do trabalho.
    """

    recalculo = "recalculo"
    afd = "afd"
    aej = "aej"
    relatorio = "relatorio"
    importacao = "importacao"
    exportacao_folha = "exportacao_folha"
    espelho = "espelho"
    sincronizacao_terminal = "sincronizacao_terminal"


class Status62(StrEnum):
    """
    Situacao do processamento.
    """

    enfileirado = "enfileirado"
    processando = "processando"
    concluido = "concluido"
    falhou = "falhou"
    cancelado = "cancelado"


class ProcessamentoAssincrono(BaseModel):
    """
    Handle de um processamento em segundo plano. Consulte o mesmo identificador ate o status sair de enfileirado ou processando.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do processamento.
    """
    tipo: Tipo42 | None = None
    """
    Natureza do trabalho.
    """
    status: Status62 | None = None
    """
    Situacao do processamento.
    """
    progresso: int | None = Field(None, ge=0, le=100)
    """
    Percentual concluido.
    """
    total_itens: int | None = Field(None, alias="totalItens")
    """
    Total de itens a processar.
    """
    itens_processados: int | None = Field(None, alias="itensProcessados")
    """
    Itens ja processados.
    """
    resultado_ref: AnyUrl | None = Field(None, alias="resultadoRef")
    """
    URI do recurso produzido, quando concluido.
    """
    iniciado_em: AwareDatetime | None = Field(None, alias="iniciadoEm")
    """
    Instante de inicio.
    """
    concluido_em: AwareDatetime | None = Field(None, alias="concluidoEm")
    """
    Instante de conclusao.
    """
    erro: str | None = None
    """
    Mensagem de erro quando o processamento falha.
    """
    codigo_erro: str | None = Field(None, alias="codigoErro")
    """
    Codigo do catalogo de erros associado a falha.
    """


class AcaoVencimento2(StrEnum):
    """
    O que a politica fara no vencimento.
    """

    quitar_folha = "quitar_folha"
    expirar = "expirar"
    prorrogar = "prorrogar"
    manter = "manter"


class SaldoBancoHoras(BaseModel):
    """
    Saldo consolidado do banco de horas por conta, com projecao de vencimento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo dono das contas.
    """
    conta_id: UUID | None = Field(None, alias="contaId")
    """
    Conta consultada.
    """
    conta_codigo: str | None = Field(None, alias="contaCodigo")
    """
    Codigo da conta.
    """
    politica_codigo: str | None = Field(None, alias="politicaCodigo")
    """
    Politica de banco de horas aplicada.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Inicio do periodo de compensacao.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Fim do periodo de compensacao.
    """
    saldo_minutos: int | None = Field(None, alias="saldoMinutos")
    """
    Saldo atual. Positivo e saldo credor; negativo e saldo devedor.
    """
    a_vencer30_minutos: int | None = Field(None, alias="aVencer30Minutos")
    """
    Minutos que vencem nos proximos 30 dias.
    """
    a_vencer15_minutos: int | None = Field(None, alias="aVencer15Minutos")
    """
    Minutos que vencem nos proximos 15 dias.
    """
    a_vencer7_minutos: int | None = Field(None, alias="aVencer7Minutos")
    """
    Minutos que vencem nos proximos 7 dias.
    """
    projecao_vencimento_minutos: int | None = Field(None, alias="projecaoVencimentoMinutos")
    """
    Projecao do que vencera ate o fim do periodo mantido o ritmo atual.
    """
    teto_positivo_minutos: int | None = Field(None, alias="tetoPositivoMinutos")
    """
    Teto credor da politica.
    """
    teto_negativo_minutos: int | None = Field(None, alias="tetoNegativoMinutos")
    """
    Teto devedor da politica.
    """
    acao_vencimento: AcaoVencimento2 | None = Field(None, alias="acaoVencimento")
    """
    O que a politica fara no vencimento.
    """
    calculado_em: AwareDatetime | None = Field(None, alias="calculadoEm")
    """
    Instante do calculo.
    """


class SimulacaoBancoRequisicao(BaseModel):
    """
    Simulacao de impacto no saldo: o colaborador ve quanto sobra se sair mais cedo ou tirar folga.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador simulado.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo simulado.
    """
    conta_id: UUID | None = Field(None, alias="contaId")
    """
    Conta simulada. Ausente usa a conta normal.
    """
    data: date | None = None
    """
    Dia da simulacao.
    """
    saida_prevista: str | None = Field(
        None, alias="saidaPrevista", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    """
    Horario de saida hipotetico.
    """
    minutos_compensar: int | None = Field(None, alias="minutosCompensar")
    """
    Minutos de folga a consumir, como alternativa ao horario de saida.
    """


class SimulacaoBancoResposta(BaseModel):
    """
    Resultado da simulacao de saldo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    saldo_atual_minutos: int | None = Field(None, alias="saldoAtualMinutos")
    """
    Saldo antes da simulacao.
    """
    impacto_minutos: int | None = Field(None, alias="impactoMinutos")
    """
    Efeito da hipotese no saldo. Negativo consome saldo.
    """
    saldo_simulado_minutos: int | None = Field(None, alias="saldoSimuladoMinutos")
    """
    Saldo resultante.
    """
    dentro_dos_tetos: bool | None = Field(None, alias="dentroDosTetos")
    """
    Verdadeiro quando o saldo resultante respeita os tetos da politica.
    """
    avisos: list[str] | None = None
    """
    Avisos, por exemplo horas que venceriam antes da compensacao pretendida.
    """


class FechamentoCriar(BaseModel):
    """
    Pedido de fechamento de periodo para um escopo. Trava a apuracao dos dias cobertos e gera os espelhos oficiais.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo a fechar.
    """
    escopo: Escopo | None = None
    """
    Abrangencia da trava.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do fechamento.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade, quando o escopo e unidade.
    """
    departamento_id: UUID | None = Field(None, alias="departamentoId")
    """
    Departamento, quando o escopo e departamento.
    """
    equipe_id: UUID | None = Field(None, alias="equipeId")
    """
    Equipe, quando o escopo e equipe.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador, quando o escopo e colaborador.
    """
    gerar_espelhos: bool | None = Field(None, alias="gerarEspelhos")
    """
    Gera os espelhos oficiais do escopo no mesmo processamento.
    """
    forcar: bool | None = None
    """
    Permite fechar com pendencias abertas. O total pendente fica registrado no fechamento.
    """
    observacao: str | None = None
    """
    Observacao do responsavel pelo fechamento.
    """


class ReaberturaRequisicao(BaseModel):
    """
    Reabertura de periodo fechado. Justificativa e obrigatoria e a operacao e sempre nominal.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    motivo: str | None = Field(None, max_length=1000, min_length=10)
    """
    Justificativa da reabertura. Aparece no espelho retificado e na auditoria.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Restringe a reabertura a partir desta data.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Restringe a reabertura ate esta data.
    """


class ConferenciaResposta(BaseModel):
    """
    Resultado da conferencia previa ao fechamento: o que ainda impede fechar sem forcar.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    fechamento_id: UUID | None = Field(None, alias="fechamentoId")
    """
    Fechamento conferido.
    """
    total_colaboradores: int | None = Field(None, alias="totalColaboradores")
    """
    Colaboradores no escopo.
    """
    total_dias: int | None = Field(None, alias="totalDias")
    """
    Dias apurados no escopo.
    """
    ocorrencias_abertas: int | None = Field(None, alias="ocorrenciasAbertas")
    """
    Ocorrencias ainda abertas.
    """
    solicitacoes_pendentes: int | None = Field(None, alias="solicitacoesPendentes")
    """
    Solicitacoes ainda em aprovacao.
    """
    apuracoes_pendentes: int | None = Field(None, alias="apuracoesPendentes")
    """
    Dias ainda nao apurados.
    """
    bloqueantes: list[str] | None = None
    """
    Codigos das pendencias que impedem o fechamento sem forcar.
    """
    pode_fechar: bool | None = Field(None, alias="podeFechar")
    """
    Verdadeiro quando nao ha pendencia bloqueante.
    """
    conferido_em: AwareDatetime | None = Field(None, alias="conferidoEm")
    """
    Instante da conferencia.
    """


class Tipo43(StrEnum):
    """
    Natureza do espelho a gerar.
    """

    previo = "previo"
    oficial = "oficial"
    retificado = "retificado"


class EspelhoCriar(BaseModel):
    """
    Pedido de geracao de espelho de ponto.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo apurado.
    """
    tipo: Tipo43 | None = None
    """
    Natureza do espelho a gerar.
    """
    vinculo_ids: list[UUID] | None = Field(None, alias="vinculoIds")
    """
    Vinculos especificos. Ausente gera para todo o escopo.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do escopo.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Unidade do escopo.
    """
    gerar_pdf: bool | None = Field(None, alias="gerarPdf")
    """
    Gera tambem o PDF com o layout oficial.
    """


class Metodo2(StrEnum):
    """
    Meio de assinatura.
    """

    aceite_eletronico = "aceite_eletronico"
    icp_brasil = "icp_brasil"
    biometria = "biometria"
    senha = "senha"
    token_email = "token_email"


class SignatarioTipo1(StrEnum):
    """
    Papel do signatario.
    """

    colaborador = "colaborador"
    gestor = "gestor"
    rh = "rh"
    empregador = "empregador"


class AssinaturaEspelhoRequisicao(BaseModel):
    """
    Aceite eletronico do espelho. O hash assinado vincula a versao exata que o signatario leu.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    Hash do espelho exibido ao signatario. Divergencia recusa o aceite.
    """
    metodo: Metodo2 | None = None
    """
    Meio de assinatura.
    """
    signatario_tipo: SignatarioTipo1 | None = Field(None, alias="signatarioTipo")
    """
    Papel do signatario.
    """
    senha: SecretStr | None = None
    """
    Senha do signatario, quando o metodo e senha.
    """
    assinatura_base64: Base64Str | None = Field(None, alias="assinaturaBase64")
    """
    Assinatura CAdES em base64, quando o metodo e ICP-Brasil.
    """
    aceite: bool | None = None
    """
    Verdadeiro assina; falso registra recusa fundamentada.
    """
    recusa_motivo: str | None = Field(None, alias="recusaMotivo")
    """
    Motivo da recusa. Obrigatorio quando aceite e falso.
    """


class AfdCriar(BaseModel):
    """
    Pedido de geracao de AFD. A verificacao de continuidade de NSR roda antes: havendo lacuna, o arquivo NAO e gerado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    rep_p_id: UUID | None = Field(None, alias="repPId")
    """
    REP-P cuja sequencia de NSR sera exportada.
    """
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do arquivo.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Primeiro dia a contemplar.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Ultimo dia a contemplar.
    """
    nsr_inicial: int | None = Field(None, alias="nsrInicial", ge=1)
    """
    Primeiro NSR, como alternativa ao periodo.
    """
    nsr_final: int | None = Field(None, alias="nsrFinal", ge=1)
    """
    Ultimo NSR, como alternativa ao periodo.
    """
    fracionar: bool | None = None
    """
    Fraciona o arquivo por periodo, como o leiaute permite ao REP-P.
    """
    tamanho_fracao_registros: int | None = Field(None, alias="tamanhoFracaoRegistros", ge=1)
    """
    Registros por fracao, quando fracionar e verdadeiro.
    """
    assinar: bool | None = None
    """
    Assina em CAdES logo apos gerar. Sem certificado disponivel a geracao conclui e a assinatura fica pendente.
    """


class AejCriar(BaseModel):
    """
    Pedido de geracao de AEJ pelo Programa de Tratamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    empresa_id: UUID | None = Field(None, alias="empresaId")
    """
    Empresa do arquivo.
    """
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo de apuracao. Alternativa a informar o intervalo de datas.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Primeiro dia a contemplar.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Ultimo dia a contemplar.
    """
    incluir_banco_horas: bool | None = Field(None, alias="incluirBancoHoras")
    """
    Inclui o bloco de banco de horas, que precisa fechar com o extrato.
    """
    assinar: bool | None = None
    """
    Assina em CAdES logo apos gerar.
    """


class TipoArquivo1(StrEnum):
    """
    Tipo do arquivo a assinar.
    """

    afd = "afd"
    aej = "aej"
    espelho = "espelho"
    comprovante = "comprovante"
    relatorio = "relatorio"


class Padrao1(StrEnum):
    """
    Padrao de assinatura. CAdES e o exigido para AFD.
    """

    c_ad_es = "CAdES"
    x_ad_es = "XAdES"
    p_ad_es = "PAdES"


class Formato6(StrEnum):
    """
    Formato da assinatura. detached e o exigido para AFD.
    """

    detached = "detached"
    attached = "attached"


class AssinaturaArquivoRequisicao(BaseModel):
    """
    Pedido de assinatura CAdES de um arquivo fiscal ja gerado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    tipo_arquivo: TipoArquivo1 | None = Field(None, alias="tipoArquivo")
    """
    Tipo do arquivo a assinar.
    """
    certificado_id: str | None = Field(None, alias="certificadoId")
    """
    Identificador do certificado configurado no ambiente.
    """
    padrao: Padrao1 | None = None
    """
    Padrao de assinatura. CAdES e o exigido para AFD.
    """
    formato: Formato6 | None = None
    """
    Formato da assinatura. detached e o exigido para AFD.
    """
    carimbo_tempo: bool | None = Field(None, alias="carimboTempo")
    """
    Solicita carimbo do tempo de autoridade credenciada.
    """


class VerificacaoCadeiaResposta(BaseModel):
    """
    Resultado da verificacao da cadeia de hash da trilha de auditoria. Remocao silenciosa de linha quebra a cadeia e e detectada aqui.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    sequencia_inicial: int | None = Field(None, alias="sequenciaInicial")
    """
    Primeira sequencia verificada.
    """
    sequencia_final: int | None = Field(None, alias="sequenciaFinal")
    """
    Ultima sequencia verificada.
    """
    total_verificado: int | None = Field(None, alias="totalVerificado")
    """
    Quantidade de registros verificados.
    """
    integra: bool | None = None
    """
    Verdadeiro quando a cadeia confere de ponta a ponta.
    """
    primeira_divergencia_sequencia: int | None = Field(None, alias="primeiraDivergenciaSequencia")
    """
    Sequencia da primeira divergencia encontrada.
    """
    lacunas: dict[str, Any] | None = None
    """
    Faixas de sequencia ausentes, quando houver.
    """
    verificado_em: AwareDatetime | None = Field(None, alias="verificadoEm")
    """
    Instante da verificacao.
    """


class ExportacaoFolhaRequisicao(BaseModel):
    """
    Pedido de exportacao da apuracao para o sistema de folha configurado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo a exportar.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia de destino no formato AAAA-MM.
    """
    unidade_id: UUID | None = Field(None, alias="unidadeId")
    """
    Restringe a exportacao a uma unidade.
    """
    somente_fechados: bool | None = Field(None, alias="somenteFechados")
    """
    Exporta apenas periodos ja fechados. Recomendado.
    """


class ApiClientCriado(BaseModel):
    """
    Cliente de API recem-criado. O segredo aparece UMA UNICA VEZ nesta resposta e nao pode ser recuperado depois.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    cliente: ApiClient | None = None
    """
    Cliente criado.
    """
    client_secret: str | None = Field(None, alias="clientSecret")
    """
    Segredo do cliente em claro. Guarde-o agora: nao ha como consulta-lo novamente.
    """
    api_key: str | None = Field(None, alias="apiKey")
    """
    Chave de API em claro, quando solicitada na criacao.
    """
    api_key_prefixo: str | None = Field(None, alias="apiKeyPrefixo")
    """
    Prefixo da chave, exibido na interface para identifica-la sem expo-la.
    """


class Status63(StrEnum):
    """
    Estado agregado.
    """

    ok = "ok"
    degradado = "degradado"
    indisponivel = "indisponivel"


class Ambiente2(StrEnum):
    """
    Ambiente da instancia.
    """

    dev = "dev"
    hml = "hml"
    prd = "prd"


class Saude(BaseModel):
    """
    Estado operacional da API e de suas dependencias.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    status: Status63 | None = None
    """
    Estado agregado.
    """
    versao: str | None = None
    """
    Versao da aplicacao em execucao.
    """
    commit: str | None = None
    """
    Commit da build em execucao.
    """
    ambiente: Ambiente2 | None = None
    """
    Ambiente da instancia.
    """
    dependencias: dict[str, Any] | None = None
    """
    Estado de cada dependencia: banco, fila, objetos, facial e gateway de dispositivos.
    """
    verificado_em: AwareDatetime | None = Field(None, alias="verificadoEm")
    """
    Instante da verificacao.
    """


class EncerramentoVinculoRequisicao(BaseModel):
    """
    Dados do desligamento de um vinculo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Ultimo dia do vinculo.
    """
    motivo_desligamento: str | None = Field(None, alias="motivoDesligamento")
    """
    Motivo registrado no encerramento.
    """
    quitar_banco_horas: bool | None = Field(None, alias="quitarBancoHoras")
    """
    Gera a quitacao do saldo de banco de horas na rescisao. Saldo devedor e tratado conforme a politica.
    """
    competencia_folha: str | None = Field(
        None, alias="competenciaFolha", pattern="^[0-9]{4}-(0[1-9]|1[0-2])$"
    )
    """
    Competencia em que o acerto entra na folha.
    """


class VinculoDispositivoRequisicao(BaseModel):
    """
    Pedido de vinculo entre aparelho e colaborador.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador que passara a usar o aparelho.
    """
    aprovar_imediatamente: bool | None = Field(None, alias="aprovarImediatamente")
    """
    Cria o vinculo ja ativo. Restrito ao RH; o fluxo padrao do colaborador cria vinculo pendente.
    """
    revogar_anterior: bool | None = Field(None, alias="revogarAnterior")
    """
    Revoga o vinculo ativo anterior do colaborador, permitindo a troca de aparelho na mesma operacao.
    """
    motivo: str | None = None
    """
    Justificativa da troca de aparelho, exibida na auditoria.
    """


class SincronizacaoTerminalRequisicao(BaseModel):
    """
    Escopo da sincronizacao a enfileirar para o coletor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    enviar_cadastros: bool | None = Field(None, alias="enviarCadastros")
    """
    Envia usuarios, grupos, regras de acesso e faixas de horario.
    """
    enviar_faces: bool | None = Field(None, alias="enviarFaces")
    """
    Envia as imagens ou templates faciais dos colaboradores autorizados.
    """
    coletar_registros: bool | None = Field(None, alias="coletarRegistros")
    """
    Executa o catch-up dos registros de acesso pendentes a partir da marca dagua.
    """
    reiniciar_marca_dagua: bool | None = Field(None, alias="reiniciarMarcaDagua")
    """
    Recoleta a partir do inicio, ignorando a marca dagua. Uso excepcional em diagnostico: a idempotencia impede duplicacao, mas o volume pode ser alto.
    """
    colaborador_ids: list[UUID] | None = Field(None, alias="colaboradorIds")
    """
    Restringe o envio de cadastros a colaboradores especificos.
    """


class Origem12(StrEnum):
    """
    De onde veio a resolucao. sem_regra indica ausencia de jornada ou escala vigente e resulta em PONTO-APUR-002.
    """

    jornada = "jornada"
    escala = "escala"
    afastamento = "afastamento"
    feriado = "feriado"
    sem_regra = "sem_regra"


class ResolucaoJornada(BaseModel):
    """
    O que o motor entende como previsto para um vinculo em uma data. Resposta de diagnostico do resolvedor de jornada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo consultado.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador do vinculo.
    """
    data: date | None = None
    """
    Data consultada.
    """
    tipo_dia: TipoDia2 | None = Field(None, alias="tipoDia")
    """
    Classificacao do dia.
    """
    jornada_id: UUID | None = Field(None, alias="jornadaId")
    """
    Jornada vigente na data.
    """
    jornada_codigo: str | None = Field(None, alias="jornadaCodigo")
    """
    Codigo da jornada vigente.
    """
    escala_id: UUID | None = Field(None, alias="escalaId")
    """
    Escala vigente na data, quando o regime e por escala.
    """
    posicao_ciclo: int | None = Field(None, alias="posicaoCiclo", ge=1)
    """
    Posicao do ciclo da escala resolvida para a data.
    """
    turno_id: UUID | None = Field(None, alias="turnoId")
    """
    Turno resolvido para a data.
    """
    horario_id: UUID | None = Field(None, alias="horarioId")
    """
    Horario previsto para a data.
    """
    entrada_prevista: AwareDatetime | None = Field(None, alias="entradaPrevista")
    """
    Entrada prevista, ja no fuso da unidade.
    """
    saida_prevista: AwareDatetime | None = Field(None, alias="saidaPrevista")
    """
    Saida prevista. Pode cair no dia seguinte em jornada que vira o dia.
    """
    intervalos_previstos: dict[str, Any] | None = Field(None, alias="intervalosPrevistos")
    """
    Intervalos esperados no dia, incluindo pausas da NR-17.
    """
    carga_prevista_minutos: int | None = Field(None, alias="cargaPrevistaMinutos")
    """
    Carga prevista em minutos.
    """
    cruza_meia_noite: bool | None = Field(None, alias="cruzaMeiaNoite")
    """
    Verdadeiro quando a jornada do dia vira para o dia seguinte.
    """
    feriado_id: UUID | None = Field(None, alias="feriadoId")
    """
    Feriado aplicavel, quando houver.
    """
    feriado_nome: str | None = Field(None, alias="feriadoNome")
    """
    Nome do feriado aplicavel.
    """
    afastamento_id: UUID | None = Field(None, alias="afastamentoId")
    """
    Afastamento aplicavel, quando houver.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso efetivo usado na resolucao, herdado da unidade.
    """
    origem: Origem12 | None = None
    """
    De onde veio a resolucao. sem_regra indica ausencia de jornada ou escala vigente e resulta em PONTO-APUR-002.
    """


class CancelamentoRequisicao(BaseModel):
    """
    Cancelamento com justificativa registrada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    motivo: str | None = Field(None, max_length=1000, min_length=5)
    """
    Justificativa do cancelamento.
    """


class VerificacaoCadeiaRequisicao(BaseModel):
    """
    Escopo da verificacao da cadeia de hash da auditoria.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    sequencia_de: int | None = Field(None, alias="sequenciaDe", ge=1)
    """
    Sequencia inicial. Ausente comeca em 1.
    """
    sequencia_ate: int | None = Field(None, alias="sequenciaAte", ge=1)
    """
    Sequencia final. Ausente vai ate a ultima gravada.
    """
    de: AwareDatetime | None = None
    """
    Alternativa a faixa de sequencia: instante inicial.
    """
    ate: AwareDatetime | None = None
    """
    Alternativa a faixa de sequencia: instante final.
    """


class WebhookCriado(BaseModel):
    """
    Webhook recem-criado. O segredo HMAC aparece UMA UNICA VEZ nesta resposta e nao pode ser recuperado depois.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    webhook: Webhook | None = None
    """
    Webhook criado.
    """
    segredo_hmac: str | None = Field(None, alias="segredoHmac")
    """
    Segredo usado para assinar o corpo das entregas em HMAC-SHA256. Guarde-o agora: perdido, so resta criar outro webhook.
    """
    cabecalho_assinatura: str | None = Field(None, alias="cabecalhoAssinatura")
    """
    Nome do cabecalho que transporta a assinatura.
    """
    formato_assinatura: str | None = Field(None, alias="formatoAssinatura")
    """
    Formato do valor do cabecalho de assinatura.
    """


class Paginacao(BaseModel):
    """
    Metadados da paginacao por cursor. Cursor e opaco e carrega a ordenacao e os filtros da consulta: mudar qualquer um deles exige voltar a primeira pagina.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    proximo_cursor: str | None = Field(None, alias="proximoCursor")
    """
    Cursor da proxima pagina. Ausente na ultima pagina.
    """
    cursor_anterior: str | None = Field(None, alias="cursorAnterior")
    """
    Cursor da pagina anterior. Ausente na primeira pagina.
    """
    tem_mais: bool = Field(..., alias="temMais")
    """
    Indica se existe pagina seguinte.
    """
    limite: int
    """
    Quantidade de itens por pagina efetivamente aplicada.
    """
    total: int | None = None
    """
    Total de itens quando o calculo e barato. Ausente em conjuntos grandes.
    """
    total_estimado: bool | None = Field(None, alias="totalEstimado")
    """
    Verdadeiro quando total e uma estimativa, nao uma contagem exata.
    """


class ErroCampo(BaseModel):
    """
    Detalhe de um campo invalido.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    campo: str
    """
    Caminho do campo em notacao de ponto, por exemplo endereco.cep.
    """
    mensagem: str
    """
    Explicacao do problema no campo.
    """
    codigo: str | None = Field(None, pattern="^PONTO-[A-Z]{2,6}-[0-9]{3}$")
    """
    Codigo do catalogo associado ao campo, quando aplicavel.
    """
    valor_recebido: Any | None = Field(None, alias="valorRecebido")
    """
    Valor recebido, quando seguro exibi-lo. Nunca traz segredo.
    """


class Problema(BaseModel):
    """
    Corpo de erro no formato RFC 9457 (application/problem+json), estendido com o codigo estavel do catalogo. O campo codigo e o unico identificador estavel: title e detail sao texto e podem mudar sem aviso. Toda mensagem exibida ao usuario final deve ser derivada do codigo, nunca do texto. O catalogo completo, com causa provavel e acao sugerida por codigo, esta em packages/contracts/errors.yaml.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    type: AnyUrl
    """
    URI que identifica o tipo do problema e aponta para a documentacao do codigo.
    """
    title: str
    """
    Resumo legivel do problema, estavel por codigo.
    """
    status: int
    """
    Status HTTP repetido no corpo, como preve a RFC 9457.
    """
    detail: str | None = None
    """
    Explicacao especifica desta ocorrencia. Nunca expoe parametro interno de seguranca quando o erro e marcado como expoe_regra falso.
    """
    instance: str | None = None
    """
    Caminho da requisicao que produziu o erro.
    """
    codigo: str = Field(..., pattern="^PONTO-[A-Z]{2,6}-[0-9]{3}$")
    """
    Codigo estavel do catalogo, por exemplo PONTO-MARC-001.
    """
    request_id: str | None = Field(None, alias="requestId")
    """
    Identificador de correlacao. Informe ao suporte ao abrir chamado.
    """
    erros_campo: list[ErroCampo] | None = Field(None, alias="errosCampo")
    """
    Campos invalidos, presente nos erros de validacao.
    """
    documentacao: AnyUrl | None = None
    """
    Link para a pagina do codigo na documentacao publica.
    """
    tentar_novamente_em: int | None = Field(None, alias="tentarNovamenteEm")
    """
    Segundos sugeridos antes de nova tentativa, quando o erro e retentavel.
    """


class ListaSessao(BaseModel):
    """
    Pagina de resultados de Sessao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Sessao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTenant(BaseModel):
    """
    Pagina de resultados de Tenant.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Tenant]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTenantConfiguracao(BaseModel):
    """
    Pagina de resultados de TenantConfiguracao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[TenantConfiguracao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaEmpresa(BaseModel):
    """
    Pagina de resultados de Empresa.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Empresa]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaUnidade(BaseModel):
    """
    Pagina de resultados de Unidade.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Unidade]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaRedePermitida(BaseModel):
    """
    Pagina de resultados de RedePermitida.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[RedePermitida]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaDepartamento(BaseModel):
    """
    Pagina de resultados de Departamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Departamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaCentroCusto(BaseModel):
    """
    Pagina de resultados de CentroCusto.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[CentroCusto]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaCargo(BaseModel):
    """
    Pagina de resultados de Cargo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Cargo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaEquipe(BaseModel):
    """
    Pagina de resultados de Equipe.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Equipe]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaColaborador(BaseModel):
    """
    Pagina de resultados de Colaborador.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Colaborador]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaColaboradorGestor(BaseModel):
    """
    Pagina de resultados de ColaboradorGestor.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[ColaboradorGestor]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaContrato(BaseModel):
    """
    Pagina de resultados de Contrato.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Contrato]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaVinculo(BaseModel):
    """
    Pagina de resultados de Vinculo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Vinculo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaBiometria(BaseModel):
    """
    Pagina de resultados de Biometria.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Biometria]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaDispositivo(BaseModel):
    """
    Pagina de resultados de Dispositivo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Dispositivo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTerminal(BaseModel):
    """
    Pagina de resultados de Terminal.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Terminal]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTerminalSaude(BaseModel):
    """
    Pagina de resultados de TerminalSaude.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[TerminalSaude]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaHorario(BaseModel):
    """
    Pagina de resultados de Horario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Horario]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaJornada(BaseModel):
    """
    Pagina de resultados de Jornada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Jornada]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaVinculoJornada(BaseModel):
    """
    Pagina de resultados de VinculoJornada.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[VinculoJornada]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaEscala(BaseModel):
    """
    Pagina de resultados de Escala.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Escala]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTurno(BaseModel):
    """
    Pagina de resultados de Turno.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Turno]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaFeriadoConjunto(BaseModel):
    """
    Pagina de resultados de FeriadoConjunto.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[FeriadoConjunto]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaFeriado(BaseModel):
    """
    Pagina de resultados de Feriado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Feriado]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTipoAfastamento(BaseModel):
    """
    Pagina de resultados de TipoAfastamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[TipoAfastamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaAfastamento(BaseModel):
    """
    Pagina de resultados de Afastamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Afastamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaMarcacao(BaseModel):
    """
    Pagina de resultados de Marcacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Marcacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao
    metas: dict[str, MarcacaoMeta] | None = None
    """
    Presente apenas quando incluirMeta=true e o chamador tem marcacoes.ler_sensivel. Mapa do id de cada Marcacao de dados para o seu MarcacaoMeta correspondente.
    """


class ListaComprovante(BaseModel):
    """
    Pagina de resultados de Comprovante.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Comprovante]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTratamento(BaseModel):
    """
    Pagina de resultados de Tratamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Tratamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTipoTratamento(BaseModel):
    """
    Pagina de resultados de TipoTratamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[TipoTratamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaApuracaoDia(BaseModel):
    """
    Pagina de resultados de ApuracaoDia.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[ApuracaoDia]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaOcorrencia(BaseModel):
    """
    Pagina de resultados de Ocorrencia.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Ocorrencia]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaBhConta(BaseModel):
    """
    Pagina de resultados de BhConta.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[BhConta]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaBhPolitica(BaseModel):
    """
    Pagina de resultados de BhPolitica.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[BhPolitica]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaTipoSolicitacao(BaseModel):
    """
    Pagina de resultados de TipoSolicitacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[TipoSolicitacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaAprovacao(BaseModel):
    """
    Pagina de resultados de Aprovacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Aprovacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaDelegacao(BaseModel):
    """
    Pagina de resultados de Delegacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Delegacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaPeriodo(BaseModel):
    """
    Pagina de resultados de Periodo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Periodo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaFechamento(BaseModel):
    """
    Pagina de resultados de Fechamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Fechamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaRelatorioDefinicao(BaseModel):
    """
    Pagina de resultados de RelatorioDefinicao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[RelatorioDefinicao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaRelatorioAgendamento(BaseModel):
    """
    Pagina de resultados de RelatorioAgendamento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[RelatorioAgendamento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaAfdArquivo(BaseModel):
    """
    Pagina de resultados de AfdArquivo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[AfdArquivo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaAejArquivo(BaseModel):
    """
    Pagina de resultados de AejArquivo.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[AejArquivo]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaRepP(BaseModel):
    """
    Pagina de resultados de RepP.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[RepP]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaWebhook(BaseModel):
    """
    Pagina de resultados de Webhook.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Webhook]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaWebhookEntrega(BaseModel):
    """
    Pagina de resultados de WebhookEntrega.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[WebhookEntrega]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaIntegracaoFolha(BaseModel):
    """
    Pagina de resultados de IntegracaoFolha.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[IntegracaoFolha]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaImportacao(BaseModel):
    """
    Pagina de resultados de Importacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Importacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaRegistroAuditoria(BaseModel):
    """
    Pagina de resultados de RegistroAuditoria.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[RegistroAuditoria]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaConsentimento(BaseModel):
    """
    Pagina de resultados de Consentimento.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Consentimento]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaSolicitacaoTitular(BaseModel):
    """
    Pagina de resultados de SolicitacaoTitular.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[SolicitacaoTitular]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaAcessoDadoSensivel(BaseModel):
    """
    Pagina de resultados de AcessoDadoSensivel.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[AcessoDadoSensivel]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaPerfil(BaseModel):
    """
    Pagina de resultados de Perfil.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Perfil]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaPermissao(BaseModel):
    """
    Pagina de resultados de Permissao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Permissao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaApiClient(BaseModel):
    """
    Pagina de resultados de ApiClient.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[ApiClient]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class Solicitacao(BaseModel):
    """
    Pedido aberto no workflow. Percorre a cadeia definida no tipo e, quando aprovado, materializa um tratamento ou um afastamento. A solicitacao nunca altera marcacao diretamente.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador da solicitacao.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    tipo_solicitacao_id: UUID | None = Field(None, alias="tipoSolicitacaoId")
    """
    Tipo de solicitacao.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador alvo.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo alvo.
    """
    solicitante_usuario_id: UUID | None = Field(None, alias="solicitanteUsuarioId")
    """
    Usuario que abriu o pedido.
    """
    protocolo: str | None = None
    """
    Numero de protocolo legivel, informado ao colaborador para acompanhamento.
    """
    data_referencia: date | None = Field(None, alias="dataReferencia")
    """
    Dia de referencia do pedido.
    """
    data_inicio: date | None = Field(None, alias="dataInicio")
    """
    Inicio do periodo pedido.
    """
    data_fim: date | None = Field(None, alias="dataFim")
    """
    Fim do periodo pedido.
    """
    descricao: str | None = None
    """
    Justificativa do solicitante.
    """
    payload: dict[str, Any] | None = None
    """
    Conteudo especifico do tipo, por exemplo os horarios propostos em um ajuste de ponto.
    """
    status: Status34 | None = None
    """
    Situacao do pedido.
    """
    etapa_atual: int | None = Field(None, alias="etapaAtual", ge=1)
    """
    Indice da etapa em andamento na cadeia de aprovacao.
    """
    prazo_em: AwareDatetime | None = Field(None, alias="prazoEm")
    """
    Prazo de resposta da etapa corrente.
    """
    concluida_em: AwareDatetime | None = Field(None, alias="concluidaEm")
    """
    Instante da conclusao.
    """
    resultado: str | None = None
    """
    Desfecho registrado na conclusao.
    """
    aprovacoes: list[Aprovacao] | None = None
    """
    Historico das etapas da cadeia.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Espelho(BaseModel):
    """
    Espelho de ponto do periodo para um vinculo. O tipo oficial e emitido no fechamento e e o documento que o colaborador assina. Retificacao gera versao nova, jamais sobrescreve a anterior.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do espelho.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    periodo_id: UUID | None = Field(None, alias="periodoId")
    """
    Periodo apurado.
    """
    fechamento_id: UUID | None = Field(None, alias="fechamentoId")
    """
    Fechamento que originou o espelho oficial.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador dono do espelho.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo apurado.
    """
    versao: int | None = Field(None, ge=1)
    """
    Versao do espelho. Retificacao gera versao nova.
    """
    tipo: Tipo32 | None = None
    """
    Natureza do espelho.
    """
    conteudo: dict[str, Any] | None = None
    """
    Snapshot completo em JSON: dias, marcacoes, tratamentos, totais e observacoes, congelado na emissao.
    """
    conteudo_ref: str | None = Field(None, alias="conteudoRef")
    """
    Chave do PDF no armazenamento de objetos.
    """
    hash_sha256: str | None = Field(None, alias="hashSha256", pattern="^[0-9a-f]{64}$")
    """
    Hash do conteudo. E o valor efetivamente assinado pelo colaborador, o que torna a assinatura verificavel e nao repudiavel.
    """
    total_previsto_minutos: int | None = Field(None, alias="totalPrevistoMinutos")
    """
    Total previsto no periodo.
    """
    total_trabalhado_minutos: int | None = Field(None, alias="totalTrabalhadoMinutos")
    """
    Total trabalhado no periodo.
    """
    total_extras_minutos: int | None = Field(None, alias="totalExtrasMinutos")
    """
    Total de horas extras no periodo.
    """
    total_faltas_minutos: int | None = Field(None, alias="totalFaltasMinutos")
    """
    Total de faltas no periodo.
    """
    total_noturno_minutos: int | None = Field(None, alias="totalNoturnoMinutos")
    """
    Total de horas noturnas no periodo.
    """
    saldo_banco_minutos: int | None = Field(None, alias="saldoBancoMinutos")
    """
    Saldo de banco de horas no fim do periodo.
    """
    assinaturas: list[AssinaturaEspelho] | None = None
    """
    Assinaturas registradas para este espelho.
    """
    gerado_em: AwareDatetime | None = Field(None, alias="geradoEm")
    """
    Instante da geracao.
    """
    gerado_por: UUID | None = Field(None, alias="geradoPor")
    """
    Usuario ou processo que gerou.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """


class Usuario(BaseModel):
    """
    Identidade de acesso ao sistema. Distinta de colaborador: nem todo colaborador tem usuario e nem todo usuario e colaborador.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    id: UUID | None = None
    """
    Identificador do usuario.
    """
    tenant_id: UUID | None = Field(None, alias="tenantId")
    """
    Tenant dono do registro.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador correspondente, quando houver.
    """
    email: EmailStr | None = None
    """
    E-mail de acesso, unico por tenant.
    """
    email_verificado_em: AwareDatetime | None = Field(None, alias="emailVerificadoEm")
    """
    Instante da verificacao do e-mail.
    """
    nome_completo: str | None = Field(None, alias="nomeCompleto")
    """
    Nome do usuario.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    avatar_ref: str | None = Field(None, alias="avatarRef")
    """
    Chave do avatar no armazenamento de objetos.
    """
    tipo: Tipo37 | None = None
    """
    humano: pessoa. servico: conta tecnica de integracao. suporte: operador da SEEG com acesso controlado.
    """
    status: Status56 | None = None
    """
    convidado: criado e ainda sem primeiro acesso. bloqueado: barrado por seguranca. inativo: desligado.
    """
    idioma: str | None = None
    """
    Idioma da interface.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso de exibicao do usuario.
    """
    mfa_obrigatorio: bool | None = Field(None, alias="mfaObrigatorio")
    """
    Forca segundo fator neste usuario independentemente da politica do tenant.
    """
    perfis: list[UsuarioPerfil] | None = None
    """
    Perfis atribuidos com escopo.
    """
    ultimo_acesso_em: AwareDatetime | None = Field(None, alias="ultimoAcessoEm")
    """
    Instante do ultimo acesso.
    """
    aceite_termos_em: AwareDatetime | None = Field(None, alias="aceiteTermosEm")
    """
    Instante do aceite dos termos de uso.
    """
    criado_em: AwareDatetime | None = Field(None, alias="criadoEm")
    """
    Instante de criacao, atribuido pelo servidor.
    """
    criado_por: UUID | None = Field(None, alias="criadoPor")
    """
    Usuario que criou o registro.
    """
    atualizado_em: AwareDatetime | None = Field(None, alias="atualizadoEm")
    """
    Instante da ultima atualizacao.
    """
    atualizado_por: UUID | None = Field(None, alias="atualizadoPor")
    """
    Usuario responsavel pela ultima atualizacao.
    """
    excluido_em: AwareDatetime | None = Field(None, alias="excluidoEm")
    """
    Instante da exclusao logica. Ausente enquanto o registro esta ativo.
    """
    excluido_por: UUID | None = Field(None, alias="excluidoPor")
    """
    Usuario que fez a exclusao logica.
    """


class UsuarioCriar(BaseModel):
    """
    Dados aceitos na criacao de Usuario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador correspondente, quando houver.
    """
    email: EmailStr
    """
    E-mail de acesso, unico por tenant.
    """
    nome_completo: str = Field(..., alias="nomeCompleto")
    """
    Nome do usuario.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    avatar_ref: str | None = Field(None, alias="avatarRef")
    """
    Chave do avatar no armazenamento de objetos.
    """
    tipo: Tipo37 | None = None
    """
    humano: pessoa. servico: conta tecnica de integracao. suporte: operador da SEEG com acesso controlado.
    """
    status: Status56 | None = None
    """
    convidado: criado e ainda sem primeiro acesso. bloqueado: barrado por seguranca. inativo: desligado.
    """
    idioma: str | None = None
    """
    Idioma da interface.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso de exibicao do usuario.
    """
    mfa_obrigatorio: bool | None = Field(None, alias="mfaObrigatorio")
    """
    Forca segundo fator neste usuario independentemente da politica do tenant.
    """
    perfis: list[UsuarioPerfil] | None = None
    """
    Perfis atribuidos com escopo.
    """


class UsuarioAtualizar(BaseModel):
    """
    Campos aceitos na atualizacao parcial de Usuario. Apenas os campos enviados sao alterados.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador correspondente, quando houver.
    """
    email: EmailStr | None = None
    """
    E-mail de acesso, unico por tenant.
    """
    nome_completo: str | None = Field(None, alias="nomeCompleto")
    """
    Nome do usuario.
    """
    telefone: str | None = None
    """
    Telefone de contato.
    """
    avatar_ref: str | None = Field(None, alias="avatarRef")
    """
    Chave do avatar no armazenamento de objetos.
    """
    tipo: Tipo37 | None = None
    """
    humano: pessoa. servico: conta tecnica de integracao. suporte: operador da SEEG com acesso controlado.
    """
    status: Status56 | None = None
    """
    convidado: criado e ainda sem primeiro acesso. bloqueado: barrado por seguranca. inativo: desligado.
    """
    idioma: str | None = None
    """
    Idioma da interface.
    """
    fuso_horario: str | None = Field(None, alias="fusoHorario", examples=["America/Sao_Paulo"])
    """
    Fuso de exibicao do usuario.
    """
    mfa_obrigatorio: bool | None = Field(None, alias="mfaObrigatorio")
    """
    Forca segundo fator neste usuario independentemente da politica do tenant.
    """
    perfis: list[UsuarioPerfil] | None = None
    """
    Perfis atribuidos com escopo.
    """


class LoginResposta(BaseModel):
    """
    Resultado da autenticacao. Quando mfaRequerido e verdadeiro, os tokens ficam ausentes ate o segundo fator ser validado.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    mfa_requerido: bool | None = Field(None, alias="mfaRequerido")
    """
    Verdadeiro quando falta validar o segundo fator.
    """
    desafio_id: UUID | None = Field(None, alias="desafioId")
    """
    Identificador do desafio de MFA a ser respondido.
    """
    metodos_mfa: list[str] | None = Field(None, alias="metodosMfa")
    """
    Metodos de segundo fator disponiveis para o usuario.
    """
    access_token: str | None = Field(None, alias="accessToken")
    """
    JWT de acesso, assinado em RS256.
    """
    refresh_token: str | None = Field(None, alias="refreshToken")
    """
    Token de renovacao rotativo. Reapresentar um token ja usado revoga a familia.
    """
    token_type: str | None = Field(None, alias="tokenType")
    """
    Tipo do token. Sempre Bearer.
    """
    expires_in: int | None = Field(None, alias="expiresIn")
    """
    Validade do access token em segundos.
    """
    sessao_id: UUID | None = Field(None, alias="sessaoId")
    """
    Sessao criada.
    """
    usuario: Usuario | None = None
    """
    Usuario autenticado.
    """


class SessaoAtual(BaseModel):
    """
    Contexto da sessao corrente: quem e o usuario, em qual tenant, com quais perfis, permissoes e escopos efetivos.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    usuario: Usuario | None = None
    """
    Usuario autenticado.
    """
    tenant: Tenant | None = None
    """
    Tenant corrente.
    """
    sessao_id: UUID | None = Field(None, alias="sessaoId")
    """
    Sessao corrente.
    """
    perfis: list[str] | None = None
    """
    Codigos dos perfis vigentes.
    """
    permissoes: list[str] | None = None
    """
    Codigos de permissao efetivos, ja combinando perfis e negacoes.
    """
    escopos: list[str] | None = None
    """
    Escopos OAuth do token, quando a identidade e um cliente de integracao.
    """
    empresas_visiveis: list[UUID] | None = Field(None, alias="empresasVisiveis")
    """
    Empresas alcancadas pelo escopo do usuario.
    """
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador correspondente ao usuario, quando houver.
    """
    mfa_validado_em: AwareDatetime | None = Field(None, alias="mfaValidadoEm")
    """
    Instante da validacao do segundo fator nesta sessao.
    """
    reautenticado_em: AwareDatetime | None = Field(None, alias="reautenticadoEm")
    """
    Instante da ultima reautenticacao explicita.
    """
    expira_em: AwareDatetime | None = Field(None, alias="expiraEm")
    """
    Expiracao da sessao.
    """


class ExtratoBancoHoras(BaseModel):
    """
    Extrato conta-corrente do banco de horas: saldo inicial, lancamentos rastreaveis e saldo final. Nenhuma linha e sobrescrita.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    colaborador_id: UUID | None = Field(None, alias="colaboradorId")
    """
    Colaborador titular.
    """
    vinculo_id: UUID | None = Field(None, alias="vinculoId")
    """
    Vinculo dono das contas.
    """
    conta_id: UUID | None = Field(None, alias="contaId")
    """
    Conta consultada, quando a consulta e restrita a uma conta.
    """
    conta_codigo: str | None = Field(None, alias="contaCodigo")
    """
    Codigo da conta consultada.
    """
    periodo_inicio: date | None = Field(None, alias="periodoInicio")
    """
    Inicio do intervalo consultado.
    """
    periodo_fim: date | None = Field(None, alias="periodoFim")
    """
    Fim do intervalo consultado.
    """
    saldo_inicial_minutos: int | None = Field(None, alias="saldoInicialMinutos")
    """
    Saldo no inicio do intervalo.
    """
    creditos_minutos: int | None = Field(None, alias="creditosMinutos")
    """
    Total creditado no intervalo.
    """
    debitos_minutos: int | None = Field(None, alias="debitosMinutos")
    """
    Total debitado no intervalo.
    """
    quitacoes_minutos: int | None = Field(None, alias="quitacoesMinutos")
    """
    Total quitado no intervalo.
    """
    expiracoes_minutos: int | None = Field(None, alias="expiracoesMinutos")
    """
    Total expirado no intervalo.
    """
    saldo_final_minutos: int | None = Field(None, alias="saldoFinalMinutos")
    """
    Saldo no fim do intervalo.
    """
    lancamentos: list[BhLancamento] | None = None
    """
    Lancamentos do intervalo, em ordem de sequencia.
    """
    paginacao: Paginacao | None = None
    """
    Paginacao dos lancamentos.
    """


class ListaSolicitacao(BaseModel):
    """
    Pagina de resultados de Solicitacao.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Solicitacao]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaEspelho(BaseModel):
    """
    Pagina de resultados de Espelho.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Espelho]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao


class ListaUsuario(BaseModel):
    """
    Pagina de resultados de Usuario.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
    dados: list[Usuario]
    """
    Itens da pagina, na ordem pedida em ordenar.
    """
    paginacao: Paginacao
