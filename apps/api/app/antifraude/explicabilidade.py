"""Serializacao da explicabilidade do score para `marcacoes_meta.flags_integridade`.

**Decisao de design registrada (nao estava explicita no PCF).** ADR-008 regra
4 exige que `marcacoes_meta` guarde quais sinais contribuiram e com que peso.
O schema (`packages/contracts/schema.sql`) nao tem uma coluna dedicada para
isso, e o PCF F14 (secao 3, "Fora do alcance de todos") so autoriza DDL nova
em `politicas_registro` (A1) e na rotina de expurgo do scheduler (A3) --
nenhuma excecao para `marcacoes_meta`. `flags_integridade` (JSONB,
`additionalProperties: true` no contrato, ja devolvido por `GET /v1/marcacoes/
{id}/meta` e por `GET /v1/marcacoes?incluirMeta=true`) e a unica estrutura
existente, ja exposta pela API, capaz de guardar dado estruturado adicional
sem mudar DDL nem contrato. Usada aqui sob uma chave reservada (`_antifraude`)
para nao colidir com os sinais brutos que o CLIENTE reporta (o resto do
dicionario, exatamente como antes desta fase) -- a mistura e proposital e
documentada: `_antifraude` e sempre computado pelo SERVIDOR, nunca aceito do
corpo da requisicao (`app.schemas.contrato.MarcacaoCriar` nao tem esse campo,
entao um cliente que tentar mandar `flagsIntegridade["_antifraude"]` so
polui o proprio dicionario de entrada, que e sobrescrito por
`app.marcacao.pipeline.ingestao` ao gravar `marcacoes_meta` -- ver aquele
modulo).
"""

from __future__ import annotations

from typing import Any

from app.antifraude.motor import ResultadoScore

CHAVE_EXPLICABILIDADE = "_antifraude"


def montar_bloco_explicabilidade(
    resultado: ResultadoScore,
    *,
    limiar_bloqueio: int,
    limiar_revisao: int,
    perfil_confianca: str,
) -> dict[str, Any]:
    """Bloco gravado sob `flags_integridade["_antifraude"]`.

    Os proprios limiares/pesos efetivos aparecem aqui -- isto NAO viola
    `expoe_regra: false` (ADR-008 regra 5): aquela regra e sobre a RESPOSTA
    HTTP de erro (`app/core/erros.py::montar_problema`), nunca sobre o
    registro de auditoria. `marcacoes_meta` so e legivel por quem tem
    `marcacoes.ler_sensivel` (permissao propria, acesso registrado em
    `acessos_dados_sensiveis`) -- exatamente o publico que ADR-008 regra 4
    diz que PRECISA enxergar o peso para poder decidir/contestar.
    """
    return {
        CHAVE_EXPLICABILIDADE: {
            "versaoMotor": 1,
            "perfilConfianca": perfil_confianca,
            "limiarBloqueio": limiar_bloqueio,
            "limiarRevisao": limiar_revisao,
            "scoreExplicabilidade": [c.para_dict() for c in resultado.explicabilidade],
        }
    }


def mesclar_flags_com_explicabilidade(
    flags_do_cliente: dict[str, Any],
    resultado: ResultadoScore,
    *,
    limiar_bloqueio: int,
    limiar_revisao: int,
    perfil_confianca: str,
) -> dict[str, Any]:
    """`flags_do_cliente` tal como reportado (nunca alterado) + o bloco
    `_antifraude` computado pelo servidor, sobrescrevendo qualquer chave de
    mesmo nome que o cliente tenha tentado mandar."""
    mesclado = dict(flags_do_cliente)
    mesclado.pop(CHAVE_EXPLICABILIDADE, None)
    mesclado.update(
        montar_bloco_explicabilidade(
            resultado,
            limiar_bloqueio=limiar_bloqueio,
            limiar_revisao=limiar_revisao,
            perfil_confianca=perfil_confianca,
        )
    )
    return mesclado
