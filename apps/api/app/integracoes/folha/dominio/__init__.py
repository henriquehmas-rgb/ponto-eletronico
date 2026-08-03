"""Exportador para o sistema Domínio (Thomson Reuters/Domínio Sistemas),
parceiro `dominio` do enum `IntegracaoFolha.parceiro` (F13/A5, T16).

**Débito tecnico registrado explicitamente (PCF F13 secao 2/6/9.4, mesmo
padrao de honestidade de ADR-011/ADR-012) -- leia antes de usar este
modulo para qualquer alegacao de conformidade.** A pesquisa de mercado
feita para a revisao deste PCF encontrou apenas documentacao PARCIAL e
publica sobre o formato de importacao de ponto do Domínio -- material de
terceiro (forum/documento de integrador), nao a especificacao oficial do
fabricante publicada com posicao de campo verificavel. Esta sessao de
build (A5, sem acesso a busca na web neste ambiente de execucao) NAO
encontrou nem confirmou nenhuma posicao de campo adicional alem do que o
proprio PCF ja registra -- ou seja, **nenhum campo abaixo esta confirmado
contra fonte oficial**. Diferente de `app.integracoes.folha.alterdata`
(T16, posicao de campo publica e verificavel em `ajuda.alterdata.com.br`),
este exportador **nao pode ser descrito como "validado contra layout de
referencia do parceiro"** em nenhuma circunstancia (PCF F13 secao 7,
criterio de aceite 3; secao 9, proibicao 4).

**Decisao de implementacao:** gera sobre o motor generico (`app.
integracoes.folha.comum`), reaproveitando `generico_csv.gerar` com um
cabecalho e nome de arquivo proprios do parceiro (convencao de nome
plausivel, nao confirmada), para que o arquivo pelo menos seja
identificavel como destinado ao Domínio -- sem fingir qualquer fidelidade
de posicao de campo que a pesquisa nao confirmou. Nenhum campo e omitido
nem inventado alem do que o motor generico ja produz.
"""

from __future__ import annotations

from app.integracoes.folha.comum import registro
from app.integracoes.folha.dominio.layout import gerar

registro.registrar("dominio", gerar)

__all__ = ["gerar"]
