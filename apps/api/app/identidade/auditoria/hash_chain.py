"""Trilha de auditoria encadeada por hash: formula, gravacao e verificacao.

FORMULA DO HASH (fixada -- mudar invalida a cadeia historica, ver PCF secao
6/T10). `hash_registro` de uma linha e:

    SHA-256(
        hash_anterior_ou_GENESIS
        + US + tenant_id
        + US + sequencia
        + US + evento
        + US + entidade
        + US + entidade_id_ou_vazio
        + US + acao
        + US + usuario_id_ou_vazio
        + US + resultado
        + US + ocorrido_em_iso_utc_microssegundos
        + US + valor_anterior_json_canonico
        + US + valor_novo_json_canonico
    )

onde:

* `US` e o caractere ASCII "unit separator" (`\\x1f`, `chr(31)`), escolhido
  por nao aparecer em texto humano nem em JSON serializado -- delimita os
  campos sem ambiguidade de concatenacao.
* `hash_anterior_ou_GENESIS` e o `hash_registro` hexadecimal da linha
  anterior da cadeia NAQUELE tenant, ou a string literal `"GENESIS"` para a
  primeira linha (`sequencia = 1`). Nunca string vazia, para que o genesis
  produza um hash diferente de uma linha com `hash_anterior` realmente vazio
  (impossivel no schema, mas a formula fica inambigua de qualquer forma).
* `tenant_id`, `entidade_id`, `usuario_id` entram como `str(uuid)` (minusculo,
  com hifens); ausentes entram como string vazia.
* `sequencia` entra como `str(int)`, decimal, sem separador de milhar.
* `ocorrido_em` entra em UTC, ISO 8601 com microssegundos
  (`datetime.isoformat(timespec="microseconds")`), sempre com o sufixo de
  fuso (`+00:00`).
* `valor_anterior`/`valor_novo` entram como JSON canonico:
  `json.dumps(valor, sort_keys=True, separators=(",", ":"), default=str)`
  quando o valor nao e `None`; caso contrario, string vazia. `default=str`
  cobre `UUID`/`datetime` dentro do JSONB sem exigir serializador customizado.

O verificador (`verificar_cadeia`) recalcula esta MESMA formula para cada
linha e compara com `hash_registro` gravado, alem de conferir que
`hash_anterior` da linha bate com o `hash_registro` da linha de `sequencia`
imediatamente anterior e que a sequencia dos ids diverso repetido nao existe
lacuna (a quebra da cadeia por remocao silenciosa aparece como um "buraco" na
sequencia OU como um `hash_anterior` que nao bate com nada).

ALOCACAO DE `sequencia` SEM LACUNA SOB CONCORRENCIA. `gravar_auditoria` toma
um `pg_advisory_xact_lock` cuja chave e derivada do `tenant_id` ANTES de ler
`MAX(sequencia)`: o lock e escopado a transacao (liberado automaticamente no
commit/rollback) e serializa, por tenant, a secao critica
"ler o ultimo estado da cadeia, calcular o proximo e inserir". Duas
transacoes concorrentes no MESMO tenant nunca leem o mesmo `MAX(sequencia)`:
a segunda so adquire o lock depois que a primeira libera (ao commitar), e
nesse momento ja enxerga a linha que a primeira gravou (READ COMMITTED le o
que foi commitado). Tenants DIFERENTES nao se bloqueiam entre si (chaves de
lock diferentes).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.identidade.rbac._contrato import contrato

_US = "\x1f"
_GENESIS = "GENESIS"

#: Mapa de `permissoes.acao` para `acessos_dados_sensiveis.acao` (T10, ultimo
#: paragrafo do texto da tarefa). Acoes de escrita fora deste mapa (criar,
#: editar, excluir, administrar, configurar...) nao produzem um acesso
#: sensivel automatico "generico": o exercicio de uma permissao sensivel de
#: ESCRITA so faz sentido registrado com o `entidade_id` e a `finalidade`
#: reais da operacao, que so quem escreve o dado conhece -- por isso
#: `registrar_acesso_sensivel_generico` (chamada automaticamente por
#: `exigir_permissao`) cobre apenas leitura/exportacao, e operacoes futuras
#: com semantica mais rica chamam `gravar_acesso_sensivel` diretamente.
_ACAO_PERMISSAO_PARA_ACESSO_SENSIVEL: dict[str, str] = {
    "ler": "leitura",
    "ler_sensivel": "leitura",
    "exportar": "exportacao",
}


def _json_canonico(valor: Any | None) -> str:
    if valor is None:
        return ""
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), default=str)


def _para_jsonb(valor: Any | None) -> Any | None:
    """Normaliza um valor para algo que o driver JSONB sabe serializar.

    `valor_anterior`/`valor_novo`/`diferenca`/`metadados` chegam como
    instantaneos de modelos ORM (via `getattr`) e podem carregar `date`,
    `datetime`, `UUID` ou `Decimal` -- tipos que `_json_canonico` ja sabe
    achatar (`default=str`) para calcular o hash, mas que o serializador JSON
    padrao do SQLAlchemy/asyncpg NAO sabe codificar ao gravar a coluna JSONB
    (`TypeError: Object of type date is not JSON serializable`, achado ao
    rodar `atualizarTenant` contra `tenants.data_contratacao`). Aplicar a
    MESMA normalizacao (`json.dumps(..., default=str)` seguido de
    `json.loads`) antes de gravar garante que o valor persistido seja
    exatamente o que foi hasheado -- o verificador (`verificar_cadeia`) relê
    esta forma ja normalizada e recalcula o mesmo hash.
    """
    if valor is None:
        return None
    return json.loads(json.dumps(valor, default=str))


def calcular_hash(
    *,
    hash_anterior: str | None,
    tenant_id: UUID,
    sequencia: int,
    evento: str,
    entidade: str,
    entidade_id: UUID | None,
    acao: str,
    usuario_id: UUID | None,
    resultado: str,
    ocorrido_em: _dt.datetime,
    valor_anterior: Any | None,
    valor_novo: Any | None,
) -> str:
    """Formula fixa do hash da linha. Ver docstring do modulo."""
    instante_utc = ocorrido_em.astimezone(_dt.UTC)
    campos = (
        hash_anterior or _GENESIS,
        str(tenant_id),
        str(sequencia),
        evento,
        entidade,
        str(entidade_id) if entidade_id else "",
        acao,
        str(usuario_id) if usuario_id else "",
        resultado,
        instante_utc.isoformat(timespec="microseconds"),
        _json_canonico(valor_anterior),
        _json_canonico(valor_novo),
    )
    return hashlib.sha256(_US.join(campos).encode("utf-8")).hexdigest()


async def _travar_e_ler_estado_cadeia(
    sessao: AsyncSession, *, tenant_id: UUID
) -> tuple[int, str | None]:
    """Adquire o advisory lock do tenant e devolve `(proxima_sequencia, ultimo_hash)`."""
    await sessao.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"),
        {"tenant": str(tenant_id)},
    )
    linha = (
        await sessao.execute(
            sa.select(
                sa.func.coalesce(sa.func.max(contrato.Auditoria.sequencia), 0),
            ).where(contrato.Auditoria.tenant_id == tenant_id)
        )
    ).scalar_one()
    ultima_sequencia = int(linha)
    ultimo_hash: str | None = None
    if ultima_sequencia > 0:
        ultimo_hash = (
            await sessao.execute(
                sa.select(contrato.Auditoria.hash_registro).where(
                    contrato.Auditoria.tenant_id == tenant_id,
                    contrato.Auditoria.sequencia == ultima_sequencia,
                )
            )
        ).scalar_one()
    return ultima_sequencia + 1, ultimo_hash


async def gravar_auditoria(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    evento: str,
    entidade: str,
    acao: str,
    entidade_id: UUID | None = None,
    usuario_id: UUID | None = None,
    usuario_email: str | None = None,
    perfil: str | None = None,
    delegacao_id: UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    origem: str = "api",
    requisicao_id: str | None = None,
    valor_anterior: Any | None = None,
    valor_novo: Any | None = None,
    diferenca: Any | None = None,
    metadados: Any | None = None,
    resultado: str = "sucesso",
    mensagem: str | None = None,
) -> Any:
    """Grava uma linha na trilha de auditoria, encadeada por hash.

    Deve ser chamada DENTRO da mesma transacao/`sessao` da escrita de negocio
    que ela documenta -- o advisory lock e escopado a transacao
    (`pg_advisory_xact_lock`), e a trilha so faz sentido atomica com o dado
    que descreve. Nao comita: quem chama decide quando.
    """
    ocorrido_em = _dt.datetime.now(_dt.UTC)
    # Normaliza ANTES de hashear e de gravar: mesma forma nos dois, e livre de
    # tipo que o driver JSONB nao serializa (ver docstring de `_para_jsonb`).
    valor_anterior = _para_jsonb(valor_anterior)
    valor_novo = _para_jsonb(valor_novo)
    diferenca = _para_jsonb(diferenca)
    metadados = _para_jsonb(metadados)
    sequencia, hash_anterior = await _travar_e_ler_estado_cadeia(sessao, tenant_id=tenant_id)
    hash_registro = calcular_hash(
        hash_anterior=hash_anterior,
        tenant_id=tenant_id,
        sequencia=sequencia,
        evento=evento,
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        usuario_id=usuario_id,
        resultado=resultado,
        ocorrido_em=ocorrido_em,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
    )
    registro = contrato.Auditoria(
        tenant_id=tenant_id,
        sequencia=sequencia,
        evento=evento,
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        usuario_id=usuario_id,
        usuario_email=usuario_email,
        perfil=perfil,
        delegacao_id=delegacao_id,
        ip=ip,
        user_agent=user_agent,
        origem=origem,
        requisicao_id=requisicao_id,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
        diferenca=diferenca,
        metadados=metadados,
        resultado=resultado,
        mensagem=mensagem,
        ocorrido_em=ocorrido_em,
        hash_anterior=hash_anterior,
        hash_registro=hash_registro,
        criado_por=usuario_id,
    )
    sessao.add(registro)
    await sessao.flush()
    return registro


async def registrar_auditoria_de_sujeito(
    sessao: AsyncSession,
    sujeito: Sujeito,
    *,
    evento: str,
    entidade: str,
    acao: str,
    entidade_id: UUID | None = None,
    resultado: str = "sucesso",
    valor_anterior: Any | None = None,
    valor_novo: Any | None = None,
    diferenca: Any | None = None,
    metadados: Any | None = None,
    mensagem: str | None = None,
    origem: str = "api",
) -> Any:
    """Atalho de `gravar_auditoria` a partir de um `Sujeito` ja resolvido.

    Preenche `usuario_id`, `usuario_email`, `perfil` (primeiro perfil, para
    leitura humana) e `delegacao_id` a partir do sujeito -- e assim que a
    acao exercida POR DELEGACAO fica marcada como tal na trilha (T9).
    """
    if sujeito.tenant_id is None:
        raise ValueError("sujeito sem tenant_id nao pode gravar auditoria")
    return await gravar_auditoria(
        sessao,
        tenant_id=sujeito.tenant_id,
        evento=evento,
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        usuario_id=sujeito.usuario_id,
        usuario_email=sujeito.email or None,
        perfil=sujeito.perfis[0] if sujeito.perfis else None,
        delegacao_id=sujeito.delegacao_id,
        origem=origem,
        resultado=resultado,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
        diferenca=diferenca,
        metadados=metadados,
        mensagem=mensagem,
    )


async def registrar_acesso_sensivel_generico(sujeito: Sujeito, codigo_permissao: str) -> None:
    """Grava `acessos_dados_sensiveis` de forma GENERICA, a partir so do codigo.

    Chamada automaticamente por `app.core.seguranca.exigir_permissao` quando
    `codigo_permissao` esta em `sujeito.permissoes_sensiveis`. Como
    `exigir_permissao` nao tem acesso a sessao de banco da requisicao (a
    assinatura de `_verificar` esta fixada e nao recebe `SessaoDb`), esta
    funcao abre a SUA PROPRIA sessao curta -- limitacao conhecida, registrada
    no relatorio da fase (custo de uma conexao extra por permissao sensivel
    exercida). So cobre `ler`/`ler_sensivel`/`exportar` (ver
    `_ACAO_PERMISSAO_PARA_ACESSO_SENSIVEL`); operacoes de escrita sensiveis
    chamam `gravar_acesso_sensivel` diretamente, com `finalidade` e
    `entidade_id` reais.
    """
    if sujeito.tenant_id is None:
        return
    acao_permissao = codigo_permissao.rpartition(".")[2]
    acao_acesso = _ACAO_PERMISSAO_PARA_ACESSO_SENSIVEL.get(acao_permissao)
    if acao_acesso is None:
        return

    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, str(sujeito.tenant_id))
        recurso = codigo_permissao.rpartition(".")[0]
        sessao.add(
            contrato.AcessoDadoSensivel(
                tenant_id=sujeito.tenant_id,
                usuario_id=sujeito.usuario_id,
                categoria="dados_pessoais",
                entidade=recurso,
                finalidade=f"Exercicio da permissao {codigo_permissao}",
                base_legal="obrigacao_legal",
                acao=acao_acesso,
                origem="api",
            )
        )
        await sessao.commit()


async def gravar_acesso_sensivel(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    categoria: str,
    finalidade: str,
    base_legal: str,
    acao: str,
    usuario_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    entidade: str | None = None,
    entidade_id: UUID | None = None,
    quantidade_registros: int | None = None,
    origem: str = "api",
) -> Any:
    """Grava `acessos_dados_sensiveis` com semantica completa (uso direto)."""
    registro = contrato.AcessoDadoSensivel(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        colaborador_id=colaborador_id,
        categoria=categoria,
        entidade=entidade,
        entidade_id=entidade_id,
        finalidade=finalidade,
        base_legal=base_legal,
        acao=acao,
        quantidade_registros=quantidade_registros,
        origem=origem,
    )
    sessao.add(registro)
    await sessao.flush()
    return registro


class ResultadoVerificacaoCadeia:
    """Resultado de `verificar_cadeia`. Espelha `VerificacaoCadeiaResposta` do contrato."""

    __slots__ = (
        "sequencia_inicial",
        "sequencia_final",
        "total_verificado",
        "integra",
        "primeira_divergencia_sequencia",
        "lacunas",
    )

    def __init__(
        self,
        *,
        sequencia_inicial: int | None,
        sequencia_final: int | None,
        total_verificado: int,
        integra: bool,
        primeira_divergencia_sequencia: int | None,
        lacunas: list[dict[str, int]],
    ) -> None:
        self.sequencia_inicial = sequencia_inicial
        self.sequencia_final = sequencia_final
        self.total_verificado = total_verificado
        self.integra = integra
        self.primeira_divergencia_sequencia = primeira_divergencia_sequencia
        self.lacunas = {"faixas": lacunas} if lacunas else None


async def verificar_cadeia(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    sequencia_de: int | None = None,
    sequencia_ate: int | None = None,
) -> ResultadoVerificacaoCadeia:
    """Recalcula a cadeia de hash do tenant e confere contra o gravado.

    Detecta tres formas de adulteracao: (1) conteudo de uma linha alterado
    (o hash recalculado da linha diverge do gravado); (2) linha removida no
    MEIO da cadeia (aparece como lacuna na sequencia); (3) linha removida na
    PONTA (a ultima sequencia lida e menor do que deveria ser -- indetectavel
    so por esta consulta, mas coberto pelo gatilho de imutabilidade que
    impede a remocao pela role da aplicacao, ver `fn_registro_imutavel`).
    """
    consulta = sa.select(contrato.Auditoria).where(contrato.Auditoria.tenant_id == tenant_id)
    if sequencia_de is not None:
        consulta = consulta.where(contrato.Auditoria.sequencia >= sequencia_de)
    if sequencia_ate is not None:
        consulta = consulta.where(contrato.Auditoria.sequencia <= sequencia_ate)
    consulta = consulta.order_by(contrato.Auditoria.sequencia.asc())

    linhas = list((await sessao.scalars(consulta)).all())
    if not linhas:
        return ResultadoVerificacaoCadeia(
            sequencia_inicial=None,
            sequencia_final=None,
            total_verificado=0,
            integra=True,
            primeira_divergencia_sequencia=None,
            lacunas=[],
        )

    lacunas: list[dict[str, int]] = []
    primeira_divergencia: int | None = None
    esperado_hash_anterior = linhas[0].hash_anterior
    sequencia_anterior = linhas[0].sequencia - 1

    for linha in linhas:
        if linha.sequencia != sequencia_anterior + 1:
            lacunas.append({"de": sequencia_anterior + 1, "ate": linha.sequencia - 1})
        recalculado = calcular_hash(
            hash_anterior=linha.hash_anterior,
            tenant_id=linha.tenant_id,
            sequencia=linha.sequencia,
            evento=linha.evento,
            entidade=linha.entidade,
            entidade_id=linha.entidade_id,
            acao=linha.acao,
            usuario_id=linha.usuario_id,
            resultado=linha.resultado,
            ocorrido_em=linha.ocorrido_em,
            valor_anterior=linha.valor_anterior,
            valor_novo=linha.valor_novo,
        )
        quebrou = recalculado != linha.hash_registro or (
            linha.sequencia != linhas[0].sequencia and linha.hash_anterior != esperado_hash_anterior
        )
        if quebrou and primeira_divergencia is None:
            primeira_divergencia = linha.sequencia
        esperado_hash_anterior = linha.hash_registro
        sequencia_anterior = linha.sequencia

    return ResultadoVerificacaoCadeia(
        sequencia_inicial=linhas[0].sequencia,
        sequencia_final=linhas[-1].sequencia,
        total_verificado=len(linhas),
        integra=primeira_divergencia is None and not lacunas,
        primeira_divergencia_sequencia=primeira_divergencia,
        lacunas=lacunas,
    )
