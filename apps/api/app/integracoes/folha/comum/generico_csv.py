"""Layout `generico_csv` (F13/A5, T15): parceiro `generico_csv`, ja no enum
`IntegracaoFolha.parceiro`/`IntegracaoFolhaCriar.parceiro` do contrato.

**Por que este e o formato de entrega real para a maioria dos parceiros.**
A pesquisa de mercado desta revisao (PCF F13 secao 2, ADR-011/ADR-012 mesmo
padrao de honestidade) confirma que layout de exportacao de folha comercial
brasileira e majoritariamente proprietario: so a Alterdata (`app.
integracoes.folha.alterdata`, T16) tem posicao de campo publica e
verificavel. Este modulo e a base documentada que Domínio, a familia TOTVS
(A6) e Senior/Sankhya/Questor/Fortes/Contmatic (A7) usam quando a
especificacao publica do parceiro nao alcanca fidelidade de posicao de
campo -- nunca finge ser o layout oficial de nenhum parceiro.

**Formato (documentado aqui porque e o proprio contrato do arquivo, ver PCF
T15 "confere campo a campo contra a documentacao que voce mesmo escreve no
modulo"):**

- Um arquivo CSV, delimitador `;` (convencao de mercado brasileira -- Excel
  PT-BR abre `;` como separador de coluna sem configuracao adicional,
  diferente de `,`).
- Quebra de linha `\r\n` (CRLF), mesma convencao dos leiautes fiscais deste
  projeto (AFD/AEJ, `docs/leiaute-afd-aej.md`).
- Codificacao UTF-8 com BOM (`utf-8-sig`): abre corretamente em Excel PT-BR
  sem prompt de codificacao, mesmo com nome com acento -- diferente do AFD/
  AEJ (ISO-8859-1, exigencia normativa fixa da Portaria MTP 671/2021), este
  formato e nosso, sem norma externa a seguir, e UTF-8 e a escolha correta
  para um arquivo novo em 2026.
- Cabecalho com nome de coluna (primeira linha), nunca omitido.
- **Um registro por combinacao vinculo x dia x componente de apuracao**
  (PCF T15, literal) -- um colaborador com 3 componentes em um dia gera 3
  linhas, nao 1. Quem quiser consolidar por dia/colaborador faz isso do
  lado do parceiro; este formato prioriza auditabilidade (cada linha
  rastreia exatamente 1 `apuracao_componentes.id` de origem) sobre
  compacidade.

Colunas, na ordem exata do cabecalho:

| Coluna | Origem | Observacao |
|---|---|---|
| matricula | `colaboradores.matricula` | |
| cpf | `colaboradores.cpf` | 11 digitos, sem pontuacao (`dom_cpf`) |
| pis | `colaboradores.pis_nit` | vazio quando nao cadastrado |
| nomeCompleto | `colaboradores.nome_completo` | |
| cnpjEmpresa | `empresas.cnpj` | 14 digitos, sem pontuacao (`dom_cnpj`) |
| data | `apuracoes_dia.data` | `AAAA-MM-DD` (ISO 8601) |
| componenteCodigo | `apuracao_componentes.codigo` | codigo interno, por exemplo `he_50` |
| componenteDescricao | `apuracao_componentes.descricao` | vazio quando a linha de origem nao |
|   |   | tem descricao |
| categoria | `apuracao_componentes.categoria` | enum do schema (`normal`,`extra`,`noturno`,...) |
| minutos | `apuracao_componentes.minutos` | inteiro |
| fator | `apuracao_componentes.fator` | decimal, 4 casas, ponto como separador |
| minutosEquivalentes | `apuracao_componentes.minutos_equivalentes` | `minutos * fator`, |
|   |   | arredondado -- e o valor que a folha consome |
| origem | `apuracao_componentes.origem` | enum do schema (`marcacao`,`tratamento`, |
|   |   | `afastamento`,`regra`,`banco`,`feriado`) |
| rubrica | `integracoes_folha.mapeamento_rubricas[componenteCodigo]` | vazio quando o de-para |
|   |   | nao tem entrada para este codigo (a propria descricao de `criarIntegracaoFolha` avisa) |
"""

from __future__ import annotations

import csv
import io

from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha
from app.integracoes.folha.comum.rubricas import resolver_rubrica

#: Ordem exata das colunas -- qualquer mudanca aqui e mudanca de contrato do
#: arquivo, documente na tabela acima no mesmo commit.
CABECALHO: tuple[str, ...] = (
    "matricula",
    "cpf",
    "pis",
    "nomeCompleto",
    "cnpjEmpresa",
    "data",
    "componenteCodigo",
    "componenteDescricao",
    "categoria",
    "minutos",
    "fator",
    "minutosEquivalentes",
    "origem",
    "rubrica",
)

DELIMITADOR: str = ";"


def gerar(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    """Gera o CSV generico bem documentado (ver docstring do modulo)."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=DELIMITADOR, lineterminator="\r\n")
    escritor.writerow(CABECALHO)
    for linha in contexto.linhas:
        rubrica = linha.rubrica
        if rubrica is None:
            rubrica = resolver_rubrica(linha.componente_codigo, contexto.mapeamento_rubricas)
        escritor.writerow(
            [
                linha.matricula,
                linha.cpf,
                linha.pis_nit or "",
                linha.nome_completo,
                linha.empresa_cnpj,
                linha.data.isoformat(),
                linha.componente_codigo,
                linha.componente_descricao or "",
                linha.categoria,
                str(linha.minutos),
                format(linha.fator, ".4f"),
                str(linha.minutos_equivalentes),
                linha.origem,
                rubrica or "",
            ]
        )
    conteudo = buffer.getvalue().encode("utf-8-sig")
    nome_arquivo = (
        f"integracoes-folha/{contexto.tenant_id}/{contexto.integracao_id}/"
        f"generico_csv-{contexto.competencia_folha}-{contexto.processamento_id}.csv"
    )
    return ArquivoFolhaGerado(
        conteudo=conteudo,
        nome_arquivo=nome_arquivo,
        content_type="text/csv; charset=utf-8",
    )
