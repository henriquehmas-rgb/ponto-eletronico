"""Exportador de folha para a Fortes (Fortes Informatica, folha/RH),
parceiro `fortes` do enum `IntegracaoFolha.parceiro` (F13/A7, T18).

**Debito tecnico registrado explicitamente -- o mais severo dos cinco
parceiros desta tarefa, leia com atencao (PCF F13 secao 2/6/9, mesmo padrao
de honestidade de ADR-011/ADR-012).** A pesquisa de mercado feita para a
revisao do PCF (`docs/fases/F13-api-publica-webhooks-integracoes.md`, secao
2 e T18) **nao encontrou nenhuma especificacao de campo publica** para a
Fortes: a documentacao inteira fica atras de suporte pago contratado -- nem
sequer o FLUXO/tela esta publicamente descrito (diferente de Senior, Questor
e Contmatic, que ao menos tem o fluxo documentado). O UNICO dado publico
confirmado pela pesquisa sao os NOMES de dois formatos historicamente
aceitos: `.ps` (layout legado) e `.csv` -- nenhuma posicao de campo, nenhum
delimitador, nenhuma convencao de nome de arquivo documentada. Este
exportador **nao pode ser descrito como "validado contra layout de
referencia do parceiro"** em nenhuma circunstancia (PCF F13 secao 7,
criterio de aceite 3; secao 9, proibicao 4). Ver `VALIDADO_CONTRA_LAYOUT_
REFERENCIA` em `layout.py`.

**Por que este modulo produz so `.csv`, nunca `.ps`.** O enum `integracoes_
folha.formato` (`packages/contracts/schema.sql`) e `IntegracaoFolha.formato`
(`packages/contracts/openapi.yaml`) so aceitam `csv`/`txt`/`xml`/`json`/
`api` -- `.ps` nao e um valor representavel sem uma RFC que estenda esse
enum, decisao de contrato fora do meu ownership (nunca "Decidida" por conta
propria, `docs/rfc/README.md` secao 4). Mesmo que uma RFC futura adicionasse
`.ps` ao enum, nao haveria como implementar com fidelidade: a especificacao
inteira do formato fica atras de um contrato de suporte pago que esta
pesquisa nao teve acesso -- adicionar o valor ao enum sem uma fonte real
so trocaria uma lacuna de contrato por uma promessa vazia. Por isso este
exportador produz apenas o formato generico csv (ja no enum), nunca tenta
aproximar `.ps`.

**Decisao de implementacao:** gera sobre o motor generico (`app.
integracoes.folha.comum`), reaproveitando `generico_csv.gerar` (mesmo padrao
que T16/A5 usou para Domínio) com um nome de arquivo proprio do parceiro --
convencao plausivel, nao confirmada por fonte oficial.
"""

from __future__ import annotations

from app.integracoes.folha.comum import registro
from app.integracoes.folha.fortes.layout import gerar

registro.registrar("fortes", gerar)

__all__ = ["gerar"]
