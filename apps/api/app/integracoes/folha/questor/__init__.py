"""Exportador de folha para o Questor (Questor Sistemas, ERP contabil/folha),
parceiro `questor` do enum `IntegracaoFolha.parceiro` (F13/A7, T18).

**Debito tecnico registrado explicitamente (PCF F13 secao 2/6/9, mesmo
padrao de honestidade de ADR-011/ADR-012) -- leia antes de usar este modulo
para qualquer alegacao de conformidade ou fidelidade de layout.** A pesquisa
de mercado feita para a revisao do PCF (`docs/fases/
F13-api-publica-webhooks-integracoes.md`, secao 2 e T18) encontrou, para o
Questor, apenas documentacao PUBLICA de fluxo/tela do modulo de folha --
descricao de processo, **sem** posicao de campo, ordem de coluna ou nome de
arquivo publicados campo a campo (fica atras de login da propria plataforma
-- mesmo achado que Senior e Contmatic, os outros dois parceiros desta
tarefa com "fluxo documentado, campo a campo atras de login"). Diferente de
`app.integracoes.folha.alterdata` (T16/A5, o unico parceiro desta fase com
posicao de campo publica e verificavel), este exportador **nao pode ser
descrito como "validado contra layout de referencia do parceiro"** em
nenhuma circunstancia (PCF F13 secao 7, criterio de aceite 3; secao 9,
proibicao 4). Ver `VALIDADO_CONTRA_LAYOUT_REFERENCIA` em `layout.py`.

**Decisao de implementacao:** gera sobre o motor generico (`app.
integracoes.folha.comum`), reaproveitando `generico_csv.gerar` (mesmo padrao
que T16/A5 usou para Domínio) com um nome de arquivo proprio do parceiro --
convencao plausivel, nao confirmada por fonte oficial -- para que o arquivo
pelo menos seja identificavel como destinado ao Questor, sem fingir qualquer
fidelidade de posicao de campo que a pesquisa nao confirmou.
"""

from __future__ import annotations

from app.integracoes.folha.comum import registro
from app.integracoes.folha.questor.layout import gerar

registro.registrar("questor", gerar)

__all__ = ["gerar"]
