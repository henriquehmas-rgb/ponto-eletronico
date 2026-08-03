"""Geracao do arquivo `sankhya` (F13/A7, T18). Ver docstring de `app.
integracoes.folha.sankhya` para o debito tecnico completo (inclusive a nota
sobre AFD como alternativa nao implementada) antes de ler este modulo.

Formato: identico ao `generico_csv` (mesmas colunas, mesmo delimitador `;`,
mesma codificacao UTF-8 com BOM -- ver `app.integracoes.folha.comum.
generico_csv` para a tabela de colunas completa), **so o nome do arquivo
muda** para deixar explicito, no proprio artefato entregue, que o pedido foi
para o parceiro Sankhya. Nenhuma posicao fixa de campo e aplicada porque
nenhuma foi confirmada por fonte oficial (ver docstring do pacote) --
transformar isto em largura fixa sem fonte primaria seria inventar uma
especificacao, exatamente o que a proibicao 4 do PCF F13 (secao 9) veda.
"""

from __future__ import annotations

from typing import Final

from app.integracoes.folha.comum.generico_csv import gerar as gerar_generico_csv
from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha

#: Codigo do parceiro, identico ao enum `integracoes_folha.parceiro`
#: (`packages/contracts/schema.sql`) e ao enum `IntegracaoFolha.parceiro`
#: (`packages/contracts/openapi.yaml`).
PARCEIRO: Final[str] = "sankhya"

#: Nunca mude para `True` sem uma fonte primaria (documentacao oficial do
#: fabricante com posicao de campo verificavel) que justifique -- ver
#: docstring do pacote. `False` e o estado honesto para os cinco parceiros
#: de T18 (Senior, Sankhya, Questor, Fortes, Contmatic).
VALIDADO_CONTRA_LAYOUT_REFERENCIA: Final[bool] = False


def gerar(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    """Delega ao `generico_csv` para o conteudo (ver docstring do modulo) e
    so troca a convencao de nome do arquivo."""
    base = gerar_generico_csv(contexto)
    nome_arquivo = (
        f"integracoes-folha/{contexto.tenant_id}/{contexto.integracao_id}/"
        f"sankhya-{contexto.competencia_folha}-{contexto.processamento_id}.csv"
    )
    return ArquivoFolhaGerado(
        conteudo=base.conteudo,
        nome_arquivo=nome_arquivo,
        content_type=base.content_type,
    )


__all__ = ["PARCEIRO", "VALIDADO_CONTRA_LAYOUT_REFERENCIA", "gerar"]
