"""Importador de AFD de outro fabricante (F13/A8, T19).

Lê um AFD (Arquivo Fonte de Dados) de outro REP-P -- largura fixa, ISO-8859-1,
mesma estrutura posicional que `docs/leiaute-afd-aej.md` documenta para o
NOSSO AFD, porque a norma (Portaria MTP 671/2021, Anexo V) é a mesma para
qualquer REP-P, não uma convenção nossa. Este pacote só LÊ; nunca reaproveita
nem chama o gerador de AFD da F12 (`app.fiscal.afd.**`, fora do ownership
desta fase) -- a leitura reaproveita conhecimento do leiaute, nunca código.

**Namespace de NSR separado (ADR-003 item 6, critério de aceite 4/8 do PCF
F13).** As marcações produzidas por este pacote nunca alocam NSR da
sequência própria (`nsr_sequencias`/`nsr_emissoes`, F5): o `nsr` gravado é o
valor **do arquivo de origem** (histórico, não alocado por nós), e a linha
importada **nunca** ganha entrada correspondente em `nsr_emissoes` -- é essa
ausência, não o valor numérico em si, que impede a marcação importada de
participar da prova de sequência sem lacunas do nosso REP-P. Ver
`servico.py` para a decisão documentada sobre `rep_p_id`.

Módulos:

- `leiaute.py`: posições de campo do AFD (Anexo V), CRC-16/KERMIT (o
  algoritmo OFICIAL do leiaute, distinto do CRC-16/ARC que
  `app.marcacao.dominio.nsr` usa para as NOSSAS marcações) e parsing de
  campos `DH`.
- `parser.py`: leitura estrutural do arquivo (cabeçalho, registros tipo "7",
  trailer, validações que rejeitam o arquivo inteiro).
- `cadeia.py`: fórmula de hash/CRC PRÓPRIA para a marcação importada,
  deliberadamente distinta da fórmula de `app.marcacao.dominio.nsr` (critério
  de aceite 8 do PCF: não pode ser confundida com o que F5 calcularia).
- `servico.py`: orquestração (resolve REP-P/colaborador, monta e insere as
  marcações, atualiza `importacoes`, nunca commita -- quem abre a sessão
  decide).
"""

from __future__ import annotations
