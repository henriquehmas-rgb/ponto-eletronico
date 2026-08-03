"""Exportador de folha para o Sankhya (Sankhya Om, ERP com modulo de RH),
parceiro `sankhya` do enum `IntegracaoFolha.parceiro` (F13/A7, T18).

**Debito tecnico registrado explicitamente (PCF F13 secao 2/6/9, mesmo
padrao de honestidade de ADR-011/ADR-012) -- leia antes de usar este modulo
para qualquer alegacao de conformidade ou fidelidade de layout.** A pesquisa
de mercado feita para a revisao do PCF (`docs/fases/
F13-api-publica-webhooks-integracoes.md`, secao 2 e T18) confirma que o
Sankhya **nao publica layout fixo** de exportacao de folha: o mapeamento de
campos e configurado pelo proprio cliente/consultor dentro da ferramenta
Sankhya -- mesmo achado de mercado que a familia TOTVS (T17/A6; ver `app.
integracoes.folha.totvs_rm` para o mesmo padrao de decisao tomado
independentemente pelo agente daquele grupo). Diferente de `app.integracoes.
folha.alterdata` (T16/A5, o unico parceiro desta fase com posicao de campo
publica e verificavel), este exportador **nao pode ser descrito como
"validado contra layout de referencia do parceiro"** em nenhuma
circunstancia (PCF F13 secao 7, criterio de aceite 3; secao 9, proibicao 4).
Ver `VALIDADO_CONTRA_LAYOUT_REFERENCIA` em `layout.py`.

**Nota alternativa considerada e descartada (mesma decisao que A6 tomou para
a familia TOTVS -- ver `app.integracoes.folha.totvs_rm.exportador`, mesma
nota).** A pesquisa tambem confirma que o Sankhya aceita AFD como entrada
direta para migracao de dados de ponto. O PCF sugere isto como oportunidade
NAO obrigatoria para T17/T18 ("considere expor 'exportar como AFD' ... se
fizer sentido dentro do tempo da fase"). Esta implementacao NAO expõe essa
opcao, por duas razoes independentes, cada uma suficiente sozinha: (1)
gerar um AFD aqui contrariaria a Proibicao 8 do PCF ("Nao implemente...
geracao de AFD/AEJ. Esta fase so exporta o que F4/F12 ja calculam e geram")
-- `apps/api/app/fiscal/afd/**` e ownership exclusivo de F12/A1, e um segundo
gerador de AFD fora dali arriscaria produzir um arquivo divergente do unico
gerador ja auditado do sistema; (2) o enum `integracoes_folha.formato`
(`packages/contracts/schema.sql`) e `IntegracaoFolha.formato`
(`packages/contracts/openapi.yaml`) so aceitam `csv`/`txt`/`xml`/`json`/
`api` -- `afd` nao e um valor representavel sem uma RFC que estenda esse
enum, decisao de contrato que nao me cabe tomar sozinho (nunca "Decidida"
por conta propria, `docs/rfc/README.md` secao 4). Registrado aqui como
candidato a RFC futura, nao decidido nem implementado nesta entrega.

**Decisao de implementacao:** gera sobre o motor generico (`app.
integracoes.folha.comum`), reaproveitando `generico_csv.gerar` (mesmo padrao
que T16/A5 usou para Domínio) com um nome de arquivo proprio do parceiro --
convencao plausivel, nao confirmada por fonte oficial.
"""

from __future__ import annotations

from app.integracoes.folha.comum import registro
from app.integracoes.folha.sankhya.layout import gerar

registro.registrar("sankhya", gerar)

__all__ = ["gerar"]
