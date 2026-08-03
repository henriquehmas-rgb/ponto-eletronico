"""Exportador de folha para TOTVS Protheus (rotina GPEA200, T17, agente A6).

**Debito tecnico de fidelidade -- leia antes de declarar este exportador
"validado".** A pesquisa de mercado feita para a revisao deste PCF
(`docs/fases/F13-api-publica-webhooks-integracoes.md` §2, T17) confirma que
GPEA200 (rotina de importacao de eventos de ponto do modulo de Folha de
Pagamento do Protheus) e uma ferramenta de mapeamento configuravel pelo
proprio cliente/consultor dentro do sistema -- **nao existe posicao de campo
fixa nem layout de arquivo publicado** pela TOTVS para esta rotina, ao
contrario do AFD/AEJ (regulacao federal publica) ou do Alterdata (unico
parceiro desta fase com posicao de campo publica e verificavel, T16). Isto
significa que:

- As colunas abaixo (nome, ordem, formato) sao uma **convencao plausivel**
  construida sobre o motor generico de A5 (`app.integracoes.folha.comum`,
  T15 -- mesmo grao vinculo x dia x componente, mesmo delimitador `;` de
  mercado que `generico_csv` usa) -- nao uma transcricao de especificacao
  oficial, porque essa especificacao nao existe publicamente. A coluna
  `Filial` e incluida porque GPEA200 e uma rotina multi-filial por desenho
  do Protheus (empresas/filiais distintas no mesmo ambiente) -- decisao de
  convencao, nao de norma.
- **Nunca descreva este exportador como "validado contra layout de
  referencia do parceiro"** (PCF, Proibicao 4; criterio de aceite 3). O
  arquivo gerado e plausivel e consistente internamente, nao verificado
  campo a campo contra nenhuma fonte primaria do fabricante.
- Mesmo padrao de honestidade que ADR-011/ADR-012 (e `app.integracoes.
  folha.dominio`, T16/A5, mesmo debito) ja estabeleceram neste projeto: a
  lacuna fica documentada aqui, no proprio modulo, nao escondida nem
  disfarcada de "atendido com ressalva".

**Nota alternativa considerada e descartada por esta implementacao:** a
pesquisa tambem confirma que o Protheus aceita AFD como entrada direta. O
PCF sugere isto como oportunidade ("nao e obrigatorio"), mas gerar um AFD
aqui contrariaria a Proibicao 8 do PCF ("Nao implemente... geracao de
AFD/AEJ. Esta fase so exporta o que F4/F12 ja calculam e geram") --
`apps/api/app/fiscal/afd/**` e ownership exclusivo de F12/A1, e um segundo
gerador de AFD fora dali arriscaria produzir um arquivo divergente do unico
gerador ja auditado do sistema. Por isso este exportador so produz o layout
CSV proprio abaixo, nao AFD.
"""

from __future__ import annotations

from typing import Final

from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha
from app.integracoes.folha.comum.rubricas import resolver_rubrica
from app.integracoes.folha.totvs_rm._formatacao import formatar_horas_decimais, montar_csv

#: Codigo do parceiro, identico ao enum `integracoes_folha.parceiro`
#: (`packages/contracts/schema.sql`) e ao enum `parceiro` de `IntegracaoFolha`
#: (`packages/contracts/openapi.yaml`).
PARCEIRO: Final[str] = "totvs_protheus"

NOME_EXIBICAO: Final[str] = "TOTVS Protheus (GPEA200)"

#: Ordem/nome de coluna plausivel para importacao via GPEA200 -- convencao,
#: nao especificacao oficial (ver debito tecnico no docstring do modulo).
_CABECALHO: Final[tuple[str, ...]] = (
    "Filial",
    "Matricula",
    "CPF",
    "Nome",
    "Data",
    "Verba",
    "Quantidade",
)


def _nome_arquivo(contexto: ContextoExportacaoFolha) -> str:
    """Mesma convencao de chave de objeto que `app.integracoes.folha.comum.
    generico_csv._nome_arquivo` usa, so trocando o prefixo para identificar
    este parceiro -- consistencia entre todos os exportadores da fase."""
    return (
        f"integracoes-folha/{contexto.tenant_id}/{contexto.integracao_id}/"
        f"totvs_protheus-{contexto.competencia_folha}-{contexto.processamento_id}.csv"
    )


def gerar(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    """Implementa `app.integracoes.folha.comum.protocolo.GeradorFolha` para
    o TOTVS Protheus (GPEA200). `contexto.linhas` ja vem materializado por
    `app.integracoes.folha.comum.dados.coletar_linhas_apuracao` -- este
    modulo nao consulta o banco. `Filial` vem de
    `contexto.configuracao["filial"]` (`integracoes_folha.configuracao`,
    parametro especifico do parceiro); sem essa chave, a coluna sai vazia
    -- decisao explicita de nao inventar um codigo de filial sem fonte."""
    filial = ""
    valor_filial = contexto.configuracao.get("filial")
    if isinstance(valor_filial, str):
        filial = valor_filial
    linhas_csv: list[tuple[str, ...]] = []
    for linha in contexto.linhas:
        rubrica = linha.rubrica
        if rubrica is None:
            rubrica = resolver_rubrica(linha.componente_codigo, contexto.mapeamento_rubricas)
        linhas_csv.append(
            (
                filial,
                linha.matricula,
                linha.cpf,
                linha.nome_completo,
                linha.data.strftime("%d/%m/%Y"),
                rubrica or linha.componente_codigo,
                formatar_horas_decimais(linha.minutos_equivalentes),
            )
        )
    conteudo = montar_csv(_CABECALHO, linhas_csv)
    return ArquivoFolhaGerado(
        conteudo=conteudo,
        nome_arquivo=_nome_arquivo(contexto),
        content_type="text/csv; charset=utf-8",
    )


__all__ = ["NOME_EXIBICAO", "PARCEIRO", "gerar"]
