"""Tipos do contrato interno entre o motor generico e cada exportador de
parceiro (F13/A5, T15). Protocolo Python, nao OpenAPI -- nao confundir com
`packages/contracts/openapi.yaml`.

Nenhum destes tipos e exposto na API publica; `LinhaApuracaoFolha` e o
formato NEUTRO que `dados.coletar_linhas_apuracao` produz a partir de
`apuracoes_dia`/`apuracao_componentes`/`colaboradores`/`empresas`, e que
todo exportador (o `generico_csv` deste pacote, `dominio`/`alterdata` de
A5, `totvs_*` de A6, os cinco de A7) recebe pronto -- nenhum parceiro
consulta o banco por conta propria.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LinhaApuracaoFolha:
    """Uma linha vinculo x dia x componente de apuracao (PCF T15), com os
    dados cadastrais do colaborador/empresa ja embutidos para que nenhum
    exportador precise de uma segunda consulta."""

    vinculo_id: UUID
    colaborador_id: UUID
    empresa_id: UUID
    unidade_id: UUID | None
    departamento_id: UUID | None
    departamento_codigo: str | None
    matricula: str
    cpf: str
    pis_nit: str | None
    nome_completo: str
    empresa_cnpj: str
    data: dt.date
    componente_codigo: str
    componente_descricao: str | None
    categoria: str
    minutos: int
    fator: Decimal
    minutos_equivalentes: int
    origem: str
    rubrica: str | None
    """Codigo do parceiro para este componente, resolvido via
    `mapeamento_rubricas` (de-para de `integracoes_folha`). `None` quando o
    componente nao tem correspondencia mapeada -- o exportador decide como
    tratar a ausencia (o `generico_csv` grava a coluna vazia; a descricao
    da operacao `criarIntegracaoFolha` ja avisa: "sem mapeamento, a
    exportacao sai com os codigos internos e o parceiro nao consome")."""


@dataclass(frozen=True, slots=True)
class ContextoExportacaoFolha:
    """Tudo que um exportador de parceiro recebe para gerar o arquivo de um
    pedido de `exportarFolha`. Imutavel: nenhum exportador deve mutar o
    contexto recebido (linhas e um `tuple`, nao uma lista)."""

    tenant_id: UUID
    integracao_id: UUID
    processamento_id: UUID
    empresa_id: UUID
    empresa_cnpj: str
    parceiro: str
    competencia_folha: str
    periodo_id: UUID | None
    unidade_id: UUID | None
    somente_fechados: bool
    periodo_inicio: dt.date
    periodo_fim: dt.date
    configuracao: Mapping[str, Any]
    mapeamento_rubricas: Mapping[str, Any]
    linhas: Sequence[LinhaApuracaoFolha]
    gerado_em: dt.datetime


@dataclass(frozen=True, slots=True)
class ArquivoFolhaGerado:
    """Resultado de um exportador: bytes prontos para `app.comum.
    armazenamento.salvar_objeto`, nome de arquivo (convencao do parceiro) e
    content-type."""

    conteudo: bytes
    nome_arquivo: str
    content_type: str = "application/octet-stream"


#: Assinatura que todo exportador de parceiro implementa. Sincrona de
#: proposito -- gerar um arquivo de folha e transformacao pura de dados ja
#: em memoria (nenhum I/O de rede/banco dentro do gerador), entao nao ha
#: necessidade de `async def` aqui; quem chama (`servico.py`) e que roda em
#: contexto assincrono e faz I/O (banco, armazenamento) antes/depois.
GeradorFolha = Callable[[ContextoExportacaoFolha], ArquivoFolhaGerado]
