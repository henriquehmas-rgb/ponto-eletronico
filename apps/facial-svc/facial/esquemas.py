"""Contrato de entrada e saida das tres operacoes biometricas.

Ate a implementacao do motor, o corpo destas rotas era `dict[str, Any]` e o
contrato vivia so na docstring. Agora que ha trabalho de verdade acontecendo,
ele e Pydantic: corpo malformado passa a virar `400 PONTO-VAL-001` com
`errosCampo` pelo tratador de `RequestValidationError` que `facial/erros.py` ja
instala, em vez de estourar dentro do motor.

O que os modelos deste arquivo **nao** fazem, e e proposital: nao carregam CPF,
nome, matricula nem identificador de colaborador. Este servico recebe imagem e
devolve vetor; `referencia` e um identificador **opaco**, escolhido pelo
chamador, que serve para amarrar a chamada ao registro em
`acessos_dados_sensiveis` sem que o facial-svc precise saber quem e o titular.

`imagemBase64` e os itens de `quadrosBase64` sao **biometria**. Eles nao tem
`examples`, nao aparecem em `repr` e nao entram em log — inclusive porque um
`example` no OpenAPI acaba copiado para tutorial e dai para um `curl` no
historico do shell de alguem.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

#: Teto do comprimento da string base64. E folgado de proposito: o teto que vale
#: e `FACIAL_TAMANHO_MAXIMO_BYTES`, conferido em `facial.motor.imagem` contra a
#: configuracao. Este aqui so evita que uma string absurda chegue ao validador.
MAX_BASE64 = 32 * 1024 * 1024


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CorpoEnroll(_Base):
    """Entrada de `POST /enroll`."""

    imagem_base64: Annotated[str, Field(alias="imagemBase64", min_length=16, max_length=MAX_BASE64)]
    mime_type: Annotated[str, Field(alias="mimeType")] = "image/jpeg"
    referencia: Annotated[
        str | None,
        Field(
            max_length=128,
            description="Identificador opaco da operacao, escolhido pelo chamador.",
        ),
    ] = None


class CorpoVerificar(_Base):
    """Entrada de `POST /verificar`."""

    imagem_base64: Annotated[str, Field(alias="imagemBase64", min_length=16, max_length=MAX_BASE64)]
    mime_type: Annotated[str, Field(alias="mimeType")] = "image/jpeg"
    templates: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=32,
            description=(
                "Templates de referencia do titular. Mais de um e o caso normal: "
                "recadastro apos mudanca de aparencia, cadastro pelo app e pelo terminal."
            ),
        ),
    ]
    modelo_versao: Annotated[
        str,
        Field(
            alias="modeloVersao",
            min_length=1,
            max_length=64,
            description=(
                "Versao do modelo que gerou os templates. Conferida, nao assumida: "
                "comparar vetores de motores diferentes nao devolve 'menos parecido', "
                "devolve numero sem significado."
            ),
        ),
    ]
    referencia: Annotated[str | None, Field(max_length=128)] = None
    exigir_aprovacao: Annotated[
        bool,
        Field(
            alias="exigirAprovacao",
            description=(
                "Quando verdadeiro, reprovacao vira `403 PONTO-SCORE-003` sem detalhe, "
                "que e a resposta correta num fluxo de registro de ponto. Falso (padrao) "
                "devolve 200 com `aprovado`, para o uso interno de comparacao em lote."
            ),
        ),
    ] = False


class Desafio(_Base):
    """Desafio ativo emitido pelo servidor (piscar, virar a cabeca)."""

    tipo: Annotated[str, Field(max_length=32)]
    emitido_em: Annotated[str | None, Field(alias="emitidoEm", max_length=64)] = None


class CorpoLiveness(_Base):
    """Entrada de `POST /liveness`. **Quadros no plural**, e nao uma foto."""

    quadros_base64: Annotated[
        list[str],
        Field(
            alias="quadrosBase64",
            min_length=1,
            max_length=16,
            description="Sequencia de quadros da mesma captura, em ordem temporal.",
        ),
    ]
    mime_type: Annotated[str, Field(alias="mimeType")] = "image/jpeg"
    desafio: Desafio | None = None
    referencia: Annotated[str | None, Field(max_length=128)] = None
    exigir_aprovacao: Annotated[bool, Field(alias="exigirAprovacao")] = False


class RespostaEnroll(_Base):
    """Saida de `POST /enroll`."""

    template: str
    dimensao: int
    modelo_versao: Annotated[str, Field(serialization_alias="modeloVersao")]
    qualidade: dict[str, Any]
    duracao_ms: Annotated[int, Field(serialization_alias="duracaoMs")]


class RespostaVerificar(_Base):
    """Saida de `POST /verificar`.

    Repare no que **nao** esta aqui: a similaridade e o limiar.
    `PONTO-SCORE-003` tem `expoe_regra: false` — quem esta testando mascara
    impressa nao pode receber o placar da tentativa e iterar ate acertar.
    """

    aprovado: bool
    indice: int
    modelo_versao: Annotated[str, Field(serialization_alias="modeloVersao")]
    duracao_ms: Annotated[int, Field(serialization_alias="duracaoMs")]


class RespostaLiveness(_Base):
    """Saida de `POST /liveness`. `sinais` sao booleanos — nunca escores."""

    aprovado: bool
    sinais: dict[str, bool]
    quadros_analisados: Annotated[int, Field(serialization_alias="quadrosAnalisados")]
    duracao_ms: Annotated[int, Field(serialization_alias="duracaoMs")]
