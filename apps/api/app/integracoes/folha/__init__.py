"""Integracoes de folha de pagamento (F13, PCF secao 5.2/6, Grupo
"integracoes de folha"). Pacote unico criador: A5.

Sub-pacotes:

- `comum` (A5, T15): motor generico -- protocolo `GeradorFolha`, registro
  de parceiros, coleta de apuracao fechada e o layout `generico_csv`.
- `dominio`, `alterdata` (A5, T16): Domínio (melhor esforco, debito tecnico
  documentado) e Alterdata (unico com posicao de campo publica verificada).
- `totvs_rm`, `totvs_protheus`, `totvs_datasul` (A6, T17): familia TOTVS.
- `senior`, `sankhya`, `questor`, `fortes`, `contmatic` (A7, T18).

`carregar_exportadores()` importa todos os pacotes de parceiro conhecidos
pelo enum do contrato (`IntegracaoFolha.parceiro`); cada um se auto-
registra no proprio `__init__.py` (efeito colateral do import, ver `app.
integracoes.folha.comum.registro`). Pacotes que A6/A7 ainda nao escreveram
nesta fase sao pulados silenciosamente (`ModuleNotFoundError`) -- nenhuma
falha de um agente derruba o carregamento dos demais. Chamada de forma
idempotente (repetir nao duplica registro: `registro.registrar` recebe
sempre a MESMA funcao para o mesmo parceiro a cada import, Python cacheia
modulo por `sys.modules`).
"""

from __future__ import annotations

import importlib
import logging

_logger = logging.getLogger("app.integracoes.folha")

#: Todo o enum `IntegracaoFolha.parceiro`/`IntegracaoFolhaCriar.parceiro`
#: do contrato, MENOS `generico_csv` (que vive dentro de `comum`, nao e um
#: pacote de parceiro proprio -- ver `comum/__init__.py`).
_PACOTES_DE_PARCEIRO: tuple[str, ...] = (
    "dominio",
    "alterdata",
    "totvs_rm",
    "totvs_protheus",
    "totvs_datasul",
    "senior",
    "sankhya",
    "questor",
    "fortes",
    "contmatic",
)


def carregar_exportadores() -> None:
    """Importa `comum` (registra `generico_csv`) e todo pacote de parceiro
    ja escrito nesta arvore. Chame antes de `comum.registro.obter_gerador`
    sempre que o processo puder ainda nao ter importado nenhum parceiro
    (por exemplo, no inicio do handler do router)."""
    importlib.import_module("app.integracoes.folha.comum")
    for nome in _PACOTES_DE_PARCEIRO:
        try:
            importlib.import_module(f"app.integracoes.folha.{nome}")
        except ModuleNotFoundError:
            _logger.debug("pacote de parceiro de folha ainda nao escrito: %s", nome)
            continue


__all__ = ["carregar_exportadores"]
