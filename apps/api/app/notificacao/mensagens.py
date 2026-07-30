"""Textos das notificações do motor de regras (T10, A3).

Um template por evento, em português, montando título e corpo a partir do
`dados` do envelope (mesmo formato de `packages/contracts/events.yaml`).
Nunca carrega dado pessoal sensível além do que o próprio evento já expõe
(`events.yaml`, convenção 4 do cabeçalho) -- nada de CPF, biometria,
template facial ou detalhe de atestado nos textos abaixo.

Nomes de evento como constantes (não string solta) porque `app.notificacao.
motor` e `worker.notificacoes_verificacao` precisam do MESMO literal em três
lugares (roteamento, resolução de destinatário e reconstrução do envelope
sintético) -- divergir um caractere entre eles quebraria o roteamento em
silêncio.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Os seis eventos que a própria F10 publica (PCF §2.7/§4), reaproveitados
#: literalmente de `events.yaml` -- nunca reinventados aqui.
NOME_AJUSTE_SOLICITADO = "ajuste.solicitado"
NOME_AJUSTE_APROVADO = "ajuste.aprovado"
NOME_AJUSTE_REPROVADO = "ajuste.reprovado"
NOME_PERIODO_FECHADO = "periodo.fechado"
NOME_PERIODO_REABERTO = "periodo.reaberto"
NOME_ESPELHO_ASSINADO = "espelho.assinado"

#: `ocorrencia.aberta` já existe em `events.yaml` (origem `worker`,
#: `webhook_publico: false`) -- reaproveitado aqui como o `tipo` do envelope
#: SINTÉTICO que `worker.notificacoes_verificacao` reconstrói a partir de
#: uma linha de `ocorrencias` já gravada (o evento original, publicado em
#: processo por F4 no momento da apuração, não está mais em memória quando
#: o cron roda -- PCF §2.7).
NOME_OCORRENCIA_ABERTA = "ocorrencia.aberta"

#: Este NÃO é um evento de `events.yaml` -- não existe produtor nenhum do
#: catálogo para "solicitação pendente há N dias" (PCF §2.10, tabela de
#: rotinas de cron: "nenhum evento de events.yaml corresponde 1:1 a esta
#: rotina"). É um identificador interno, só para rotear a mensagem e marcar
#: `notificacoes.evento`/`notificacoes.entidade` -- nunca publicado em
#: nenhum `BARRAMENTO_INTERNO` de domínio, nunca assinável por webhook.
NOME_SOLICITACAO_PENDENTE = "solicitacao.pendente_prazo"


@dataclass(frozen=True, slots=True)
class Mensagem:
    """Título e corpo já resolvidos para uma notificação concreta."""

    titulo: str
    corpo: str


MontadorMensagem = Callable[[dict[str, Any]], Mensagem]


def _texto(valor: Any, alternativa: str = "-") -> str:
    """Formata um valor do payload para texto, sem levantar por campo
    ausente -- o envelope é `additionalProperties: true` e nem todo campo
    `required` do schema chega preenchido em todo caminho de teste."""
    return alternativa if valor in (None, "") else str(valor)


def _ajuste_solicitado(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Nova solicitação aguardando sua aprovação",
        corpo=(
            f"Protocolo {_texto(dados.get('protocolo'))}: solicitação de "
            f"{_texto(dados.get('tipoSolicitacaoCodigo'), 'ajuste')} referente ao dia "
            f"{_texto(dados.get('dataReferencia'))} está aguardando sua decisão."
        ),
    )


def _ajuste_aprovado(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Solicitação aprovada",
        corpo=(
            f"Sua solicitação {_texto(dados.get('protocolo'))}, referente ao dia "
            f"{_texto(dados.get('dataReferencia'))}, foi aprovada."
        ),
    )


def _ajuste_reprovado(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Solicitação reprovada",
        corpo=(
            f"Sua solicitação {_texto(dados.get('protocolo'))}, referente ao dia "
            f"{_texto(dados.get('dataReferencia'))}, foi reprovada. Motivo: "
            f"{_texto(dados.get('motivo'), 'não informado')}"
        ),
    )


def _periodo_fechado(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Período de apuração fechado",
        corpo=(
            f"O período de {_texto(dados.get('dataInicio'))} a "
            f"{_texto(dados.get('dataFim'))} foi fechado "
            f"({_texto(dados.get('totalColaboradores'), '0')} colaboradores abrangidos)."
        ),
    )


def _periodo_reaberto(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Período de apuração reaberto",
        corpo=(
            f"O período de {_texto(dados.get('dataInicio'))} a "
            f"{_texto(dados.get('dataFim'))} foi reaberto. Motivo: "
            f"{_texto(dados.get('motivo'), 'não informado')}"
        ),
    )


def _espelho_assinado(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Espelho de ponto assinado",
        corpo=(
            f"O espelho de ponto (versão {_texto(dados.get('versaoEspelho'), '1')}) foi "
            f"assinado eletronicamente em {_texto(dados.get('carimboTempo'))}."
        ),
    )


def _ocorrencia_aberta(dados: dict[str, Any]) -> Mensagem:
    codigo = _texto(dados.get("codigo"), "ocorrência")
    descricao = _texto(dados.get("descricao"), "")
    corpo = f"Ocorrência '{codigo}' aberta em {_texto(dados.get('data'))}."
    if descricao and descricao != "-":
        corpo = f"{corpo} {descricao}"
    return Mensagem(titulo="Nova ocorrência aberta", corpo=corpo)


def _solicitacao_pendente(dados: dict[str, Any]) -> Mensagem:
    return Mensagem(
        titulo="Solicitação aguardando sua decisão há vários dias",
        corpo=(
            f"O protocolo {_texto(dados.get('protocolo'))}, sob sua responsabilidade, está "
            f"com o prazo de resposta vencido desde {_texto(dados.get('prazoEm'))} e ainda "
            "não foi decidido."
        ),
    )


#: Único ponto de despacho por `tipo` de evento -- `app.notificacao.motor`
#: nunca faz `if tipo == "..."` fora daqui.
TEMPLATES: dict[str, MontadorMensagem] = {
    NOME_AJUSTE_SOLICITADO: _ajuste_solicitado,
    NOME_AJUSTE_APROVADO: _ajuste_aprovado,
    NOME_AJUSTE_REPROVADO: _ajuste_reprovado,
    NOME_PERIODO_FECHADO: _periodo_fechado,
    NOME_PERIODO_REABERTO: _periodo_reaberto,
    NOME_ESPELHO_ASSINADO: _espelho_assinado,
    NOME_OCORRENCIA_ABERTA: _ocorrencia_aberta,
    NOME_SOLICITACAO_PENDENTE: _solicitacao_pendente,
}


def montar_mensagem(tipo_evento: str, dados: dict[str, Any]) -> Mensagem | None:
    """Título/corpo do evento, ou `None` quando não há template (o evento
    não é um dos que este motor conhece -- não é erro, é "nada a notificar
    aqui")."""
    montador = TEMPLATES.get(tipo_evento)
    return montador(dados) if montador is not None else None


__all__ = [
    "NOME_AJUSTE_APROVADO",
    "NOME_AJUSTE_REPROVADO",
    "NOME_AJUSTE_SOLICITADO",
    "NOME_ESPELHO_ASSINADO",
    "NOME_OCORRENCIA_ABERTA",
    "NOME_PERIODO_FECHADO",
    "NOME_PERIODO_REABERTO",
    "NOME_SOLICITACAO_PENDENTE",
    "TEMPLATES",
    "Mensagem",
    "montar_mensagem",
]
