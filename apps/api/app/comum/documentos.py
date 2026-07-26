"""Validacao de digito verificador de documentos brasileiros.

`packages/contracts/schema.sql` cria os dominios `dom_cpf`, `dom_cnpj` e
`dom_pis`, mas eles validam **so o formato** (quantidade de digitos): o
comentario no proprio schema e explicito -- "a validacao de digito
verificador (CPF, CNPJ, PIS) e responsabilidade da aplicacao (Fase 2)". Este
modulo e essa responsabilidade.

Contrato fixado no PCF da F2 (secao 5, "Compartilhado dentro da fase"): as
quatro assinaturas abaixo nao mudam sem RFC. Ownership do arquivo e do agente
A2 (pessoas); A1 e A3 apenas importam.

Todas as funcoes recebem o valor como o usuario digitou (com ou sem mascara) e
devolvem/consomem sempre **so digitos** -- a mascara e responsabilidade da
interface, nunca do banco.
"""

from __future__ import annotations

__all__ = ["cnpj_valido", "cpf_valido", "pis_valido", "somente_digitos"]


def somente_digitos(valor: str) -> str:
    """Remove tudo que nao for digito decimal."""
    return "".join(caractere for caractere in valor if caractere.isdigit())


def _sequencia_repetida(digitos: str) -> bool:
    """`00000000000`, `11111111111` etc. passam no digito verificador e ainda
    assim nao sao documentos validos -- precisam ser recusados a parte."""
    return len(set(digitos)) == 1


def _digito_modulo_11(digitos: str, pesos: list[int]) -> int:
    """Digito verificador padrao do modulo 11 usado por CPF, CNPJ e PIS.

    Soma o produto digito x peso, tira o resto da divisao por 11: resto menor
    que 2 vira 0, senao o digito e `11 - resto`.
    """
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(valor: str) -> bool:
    """CPF: 11 digitos, dois digitos verificadores em modulo 11."""
    digitos = somente_digitos(valor)
    if len(digitos) != 11 or _sequencia_repetida(digitos):
        return False
    dv1 = _digito_modulo_11(digitos[:9], list(range(10, 1, -1)))
    dv2 = _digito_modulo_11(digitos[:9] + str(dv1), list(range(11, 1, -1)))
    return digitos[-2:] == f"{dv1}{dv2}"


def cnpj_valido(valor: str) -> bool:
    """CNPJ: 14 digitos, dois digitos verificadores em modulo 11 com peso
    ciclico 2..9 (o CNPJ alfanumerico da Receita ainda nao esta em vigor no
    dominio deste sistema; `dom_cnpj` so aceita digitos)."""
    digitos = somente_digitos(valor)
    if len(digitos) != 14 or _sequencia_repetida(digitos):
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _digito_modulo_11(digitos[:12], pesos1)
    dv2 = _digito_modulo_11(digitos[:12] + str(dv1), pesos2)
    return digitos[-2:] == f"{dv1}{dv2}"


def pis_valido(valor: str) -> bool:
    """PIS/PASEP/NIT: 11 digitos, um digito verificador em modulo 11 com peso
    ciclico 3,2,9,8,7,6,5,4,3,2."""
    digitos = somente_digitos(valor)
    if len(digitos) != 11 or _sequencia_repetida(digitos):
        return False
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digito) * peso for digito, peso in zip(digitos[:10], pesos, strict=True))
    resto = soma % 11
    dv = 11 - resto
    if dv >= 10:
        dv = 0
    return digitos[-1] == str(dv)
