"""Motor generico de exportacao de folha (F13/A5, T15).

**Publicado cedo de proposito** (A5 e T1-first do subgrupo "integracoes de
folha", PCF F13 secao 5.1): A6 (familia TOTVS) e A7 (Senior/Sankhya/Questor/
Fortes/Contmatic) importam este pacote para gerar o arquivo de cada
parceiro sem duplicar consulta a apuracao nem o mecanismo de registro.

Contrato interno (protocolo Python, nao OpenAPI) que qualquer exportador de
parceiro implementa:

1. Uma funcao com a assinatura `protocolo.GeradorFolha` -- recebe um
   `protocolo.ContextoExportacaoFolha` (apuracao fechada de um periodo, ja
   materializada em `LinhaApuracaoFolha`, mais `mapeamento_rubricas`/
   `configuracao`) e devolve um `protocolo.ArquivoFolhaGerado` (bytes +
   nome + content-type). Nenhum exportador de parceiro consulta o banco por
   conta propria -- `dados.coletar_linhas_apuracao` (aqui) e o UNICO ponto
   que fala com `apuracoes_dia`/`apuracao_componentes`, para que o
   "registro por combinacao vinculo x dia x componente" (PCF T15) seja
   identico para todos os oito parceiros mais o layout generico.
2. `registro.registrar(parceiro, gerador)`, chamado no import do proprio
   pacote do parceiro (`app.integracoes.folha.dominio`, `.alterdata`,
   `.totvs_rm`, ...) -- efeito colateral deliberado, mesmo padrao de
   auto-registro usado por bibliotecas de plugin em Python. Nenhum parceiro
   precisa editar este pacote (`comum`) nem `__init__.py` deste pacote para
   se registrar.

`carregar_exportadores()` (`app.integracoes.folha`, pacote pai) importa
todos os once nomes de parceiro conhecidos (RFC-016/017 fixam o enum) com
`try/except ModuleNotFoundError` -- os que A6/A7 ainda nao escreveram nesta
fase simplesmente nao se registram ainda, sem quebrar o carregamento dos
que ja existem (`generico_csv` aqui mesmo, `dominio`/`alterdata`, ambos de
A5).
"""

from __future__ import annotations

from app.integracoes.folha.comum import generico_csv, registro

# `generico_csv` e o unico exportador que vive dentro do proprio `comum`
# (PCF T15: "Implementa tambem o layout generico_csv" dentro de
# `app/integracoes/folha/comum/**`) -- os demais parceiros (dominio,
# alterdata, totvs_*, senior, sankhya, questor, fortes, contmatic) vivem em
# pacotes irmaos e se registram no PROPRIO import, nunca aqui.
registro.registrar("generico_csv", generico_csv.gerar)

__all__ = ["generico_csv", "registro"]
