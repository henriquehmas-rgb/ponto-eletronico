"""Registro de exportadores de folha por `parceiro` (F13/A5, T15).

Efeito colateral deliberado: cada pacote de parceiro (`app.integracoes.
folha.dominio`, `.alterdata`, e futuramente `.totvs_rm`/`.totvs_protheus`/
`.totvs_datasul` de A6, `.senior`/`.sankhya`/`.questor`/`.fortes`/
`.contmatic` de A7) chama `registrar(...)` no PRÓPRIO `__init__.py`, no
momento do import -- nenhum consumidor deste modulo edita este arquivo
para "adicionar" um parceiro novo. `app.integracoes.folha.
carregar_exportadores()` e quem garante que todos os pacotes conhecidos
foram importados pelo menos uma vez antes de qualquer `obter_gerador`.
"""

from __future__ import annotations

from app.integracoes.folha.comum.protocolo import GeradorFolha

_REGISTRO: dict[str, GeradorFolha] = {}


class ParceiroNaoRegistrado(LookupError):
    """`parceiro` valido no enum do contrato mas sem exportador registrado
    ainda (pacote de A6/A7 nao escrito/importado nesta execucao)."""

    def __init__(self, parceiro: str) -> None:
        self.parceiro = parceiro
        super().__init__(f"Nenhum exportador registrado para o parceiro {parceiro!r}.")


def registrar(parceiro: str, gerador: GeradorFolha, *, sobrescrever: bool = False) -> None:
    """Associa `parceiro` (valor do enum `IntegracaoFolha.parceiro`) ao
    `gerador`. Chamar duas vezes para o mesmo `parceiro` com um `gerador`
    DIFERENTE sem `sobrescrever=True` e erro de programacao (dois modulos
    disputando o mesmo nome de parceiro) -- levanta `ValueError` cedo, em
    vez de deixar o ultimo import vencer silenciosamente."""
    existente = _REGISTRO.get(parceiro)
    if existente is not None and existente is not gerador and not sobrescrever:
        raise ValueError(
            f"Parceiro {parceiro!r} ja registrado por outro gerador "
            f"({existente!r}); use sobrescrever=True se isso for intencional."
        )
    _REGISTRO[parceiro] = gerador


def obter_gerador(parceiro: str) -> GeradorFolha:
    """Devolve o gerador do parceiro. Levanta `ParceiroNaoRegistrado`
    (nunca `KeyError` cru) quando o pacote correspondente ainda nao foi
    importado/escrito."""
    try:
        return _REGISTRO[parceiro]
    except KeyError as exc:
        raise ParceiroNaoRegistrado(parceiro) from exc


def parceiros_disponiveis() -> frozenset[str]:
    """Parceiros com exportador registrado nesta execucao. Usado pelo
    router para decidir `PONTO-VAL-001` (parceiro do enum mas ainda sem
    implementacao) em vez de um `KeyError`/`500` cru."""
    return frozenset(_REGISTRO)


def _resetar_para_teste() -> None:
    """Uso exclusivo de teste: limpa o registro entre casos que testam o
    proprio mecanismo de registro (nunca chamado pelo codigo de producao)."""
    _REGISTRO.clear()
