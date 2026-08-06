"""`PoliticaAntifraude`/`PesosScore`: forma da politica pronta para o motor.

`app.marcacao.pipeline.ingestao._politica_efetiva` (territorio de A1 dentro de
`marcacao/pipeline/**`) resolve a linha de `politicas_registro` e monta esta
estrutura; `app.antifraude.motor.compor_score` so consome, nunca consulta o
banco. Separar a leitura (pipeline) da decisao (motor) e o que permite testar
o motor com sinais 100% sinteticos, sem banco (ver `tests/f14/antifraude/
test_motor_composicao.py`).

Os quatro pesos (`PesosScore`) nao precisam somar 100: o motor renormaliza
pelas categorias efetivamente disponiveis no momento do registro (ADR-014 --
"nunca inventar valor" tambem vale para peso de categoria sem sinal).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: `DEFAULT` de cada peso na ausencia de qualquer linha em `politicas_registro`
#: (mesmo espirito de `_POLITICA_PADRAO` em `marcacao/pipeline/ingestao.py`,
#: copiado literalmente do `DEFAULT` da coluna em schema.sql/migration
#: 0003_antifraude_pesos_score) -- perfil "equilibrado", os quatro pesos
#: iguais.
PESO_PADRAO = 25


@dataclass(frozen=True, slots=True)
class PesosScore:
    """Peso (0-100) de cada categoria de sinal na composicao ponderada."""

    dispositivo: int = PESO_PADRAO
    biometria: int = PESO_PADRAO
    geolocalizacao: int = PESO_PADRAO
    comportamento: int = PESO_PADRAO

    def total(self) -> int:
        return self.dispositivo + self.biometria + self.geolocalizacao + self.comportamento


@dataclass(frozen=True, slots=True)
class PoliticaAntifraude:
    """Politica efetiva (linha de `politicas_registro` ou o `DEFAULT` da
    coluna) num formato que o motor de composicao consome diretamente.

    Os tres campos `politica_*` (bloquear/sinalizar/permitir) e
    `exige_attestation` governam os SINAIS DECISIVOS (ADR-008 regra 7): valem
    tanto para os que ja existem hoje (mock_location, root, modo
    desenvolvedor via web/terminal) quanto para os que so existirao quando F7
    existir (attestation) -- ver `app.antifraude.motor` para a logica exata.
    """

    pesos: PesosScore = field(default_factory=PesosScore)
    perfil_confianca: str = "equilibrado"
    politica_root: str = "bloquear"
    politica_modo_desenvolvedor: str = "bloquear"
    politica_mock_location: str = "bloquear"
    exige_attestation: bool = True
    exige_facial: bool = True
    exige_liveness: bool = True
    limiar_facial: float = 75.0


#: Politica neutra usada quando o chamador nao informa nenhuma (compatibilidade
#: retroativa de `app.marcacao.confianca.motor.avaliar_confianca`, cujo unico
#: parametro de politica -- `pesos` -- e opcional por desenho: ver docstring
#: daquele modulo). NUNCA usada pelo pipeline real (`marcacao/pipeline/
#: ingestao.py` sempre monta uma `PoliticaAntifraude` a partir do banco).
POLITICA_NEUTRA = PoliticaAntifraude()
