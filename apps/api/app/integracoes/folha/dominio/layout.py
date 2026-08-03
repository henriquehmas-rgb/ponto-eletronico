"""Geracao do arquivo `dominio` (F13/A5, T16). Ver docstring de `app.
integracoes.folha.dominio` para o debito tecnico completo antes de ler
este modulo.

Formato: identico ao `generico_csv` (mesmas colunas, mesmo delimitador `;`,
mesma codificacao UTF-8 com BOM -- ver `app.integracoes.folha.comum.
generico_csv` para a tabela de colunas completa), **so o nome do arquivo
muda** para deixar explicito, no proprio artefato entregue, que o pedido
foi para o parceiro Domínio. Nenhuma posicao fixa de campo e aplicada
porque nenhuma foi confirmada por fonte oficial (ver docstring do
pacote) -- transformar isto em largura fixa sem fonte primaria seria
inventar uma especificacao, exatamente o que a proibicao 4 do PCF F13
(secao 9) veda.
"""

from __future__ import annotations

from app.integracoes.folha.comum.generico_csv import gerar as gerar_generico_csv
from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha


def gerar(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    """Delega ao `generico_csv` para o conteudo (ver docstring do modulo)
    e so troca a convencao de nome do arquivo."""
    base = gerar_generico_csv(contexto)
    nome_arquivo = (
        f"integracoes-folha/{contexto.tenant_id}/{contexto.integracao_id}/"
        f"dominio-{contexto.competencia_folha}-{contexto.processamento_id}.csv"
    )
    return ArquivoFolhaGerado(
        conteudo=base.conteudo,
        nome_arquivo=nome_arquivo,
        content_type=base.content_type,
    )
