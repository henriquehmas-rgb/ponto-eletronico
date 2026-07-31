"""Orquestrador de `assinarArquivoFiscal` (F12/A3, T12).

Resolve o arquivo de origem (AFD, AEJ ou comprovante -- `espelho`/`relatorio`
sao de F10/F11 e nao tem implementacao aqui, ver `_TIPOS_NAO_IMPLEMENTADOS`
abaixo), busca o conteudo real no armazenamento de objetos, assina em CAdES
(`app.fiscal.assinatura.cades`), grava `.p7s` no MinIO, grava
`arquivo_assinaturas` (com o resultado da autoverificacao ja embutido no
INSERT -- ver nota abaixo) e a trilha de auditoria.

**Ordem deliberada: verifica ANTES de gravar.** `cades.validar_cades` roda
sobre a assinatura recem-produzida ANTES de qualquer `INSERT` em
`arquivo_assinaturas` -- nao depois. Isto evita o problema de "e se a
autoverificacao falhar depois que a linha ja existe": `arquivo_assinaturas`
bloqueia `DELETE` por gatilho (`fn_registro_imutavel`, ver
`docs/leiaute-afd-aej.md`/glossario secao 1.2), entao desfazer uma linha
gravada exigiria um `UPDATE` de status em vez de removê-la -- mais frágil e
mais dificil de auditar do que simplesmente nao gravar nada quando a
autoverificacao (que deveria SEMPRE bater, ja que assina e verifica o MESMO
conteudo com o MESMO certificado) falhar. Uma falha aqui e tratada como bug
interno (`PONTO-FISC-006`), nao como um estado "assinatura invalida" que o
cliente precisaria interpretar.

**Nunca `UPDATE` em `arquivo_assinaturas`.** Ao contrário do padrão de F10
para `assinaturas_espelho` (que bloqueia UPDATE E DELETE por gatilho),
`arquivo_assinaturas` bloqueia só `DELETE` por gatilho -- o `UPDATE` fica
tecnicamente permitido para a role de aplicação (`glossario.md` secao 1.2:
"UPDATE só para o resultado da validação", que é convenção de aplicação, não
imposta por gatilho igual `assinaturas_espelho`). Este módulo nunca exerce
esse UPDATE: como a autoverificação roda ANTES do INSERT (ver acima), o
`validacao_resultado`/`validado_em` já entram populados na ÚNICA escrita que
este módulo faz em `arquivo_assinaturas`, um INSERT só. Reassinar sempre
cria uma linha NOVA -- nunca sobrescreve a anterior. Isto é provado por
teste dedicado (`tests/f12/assinatura/test_imutabilidade.py`).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.serialization import Encoding
from ponto_contracts import AejArquivo, AfdArquivo, ArquivoAssinatura, Comprovante
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import obter_objeto, salvar_objeto
from app.core.erros import ErroDeAplicacao
from app.fiscal.assinatura import cades
from app.fiscal.assinatura.certificado import obter_certificado_configurado
from app.identidade.auditoria.hash_chain import gravar_auditoria
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_ESTADO_INVALIDO = "PONTO-CONF-003"
CODIGO_CERTIFICADO_INDISPONIVEL = "PONTO-FISC-004"
CODIGO_CERTIFICADO_EXPIRADO = "PONTO-FISC-005"
CODIGO_FALHA_GERACAO = "PONTO-FISC-006"
CODIGO_NAO_IMPLEMENTADO = "PONTO-INT-005"

#: `AssinaturaArquivoRequisicao.tipoArquivo` que este módulo sabe assinar.
#: `espelho`/`relatorio` são valores válidos do enum do contrato (a mesma
#: tabela `arquivo_assinaturas` deveria acomodá-los no futuro), mas o PCF
#: F12 §6/T12 descopa explicitamente os dois desta fase -- já têm (ou terão,
#: em F11) endpoint próprio no domínio de origem, e não devem passar por
#: aqui.
_TIPOS_IMPLEMENTADOS = frozenset({"afd", "aej", "comprovante"})

#: Tabela (nome de auditoria) por tipo de arquivo assinável nesta fase.
_ENTIDADE_POR_TIPO: dict[str, str] = {
    "afd": "afd_arquivos",
    "aej": "aej_arquivos",
    "comprovante": "comprovantes",
}

#: Estados de `afd_arquivos.status`/`aej_arquivos.status` que ainda não têm
#: conteúdo final para assinar -- CONF-003 (transição de estado inválida).
_ESTADOS_NAO_ASSINAVEIS = frozenset({"gerando", "falhou", "cancelado"})


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


def _nao_encontrado(tipo_arquivo: str, arquivo_id: UUID) -> ErroDeAplicacao:
    return ErroDeAplicacao(
        CODIGO_RECURSO_NAO_ENCONTRADO,
        detalhe=f"Arquivo '{tipo_arquivo}' com id {arquivo_id} nao encontrado.",
    )


async def _resolver_alvo(
    sessao: AsyncSession, tenant_id: UUID, tipo_arquivo: str, arquivo_id: UUID
) -> AfdArquivo | AejArquivo | Comprovante:
    # Três `sessao.get` tipados separadamente (em vez de um `modelo:
    # type[...]` genérico) de propósito: `AsyncSession.get(type[X], id)`
    # devolve `X | None` só quando `X` é um tipo concreto conhecido em tempo
    # de checagem estática -- com uma variável `type[A] | type[B] | type[C]`
    # o mypy alarga o retorno para `Base | None` (a superclasse comum do
    # ORM), perdendo a informação de qual subtipo é. Três ramos concretos
    # mantêm o tipo de retorno preciso sem `cast`.
    if tipo_arquivo == "afd":
        afd = await sessao.get(AfdArquivo, arquivo_id)
        if afd is None or afd.tenant_id != tenant_id:
            raise _nao_encontrado(tipo_arquivo, arquivo_id)
        return afd
    if tipo_arquivo == "aej":
        aej = await sessao.get(AejArquivo, arquivo_id)
        if aej is None or aej.tenant_id != tenant_id:
            raise _nao_encontrado(tipo_arquivo, arquivo_id)
        return aej
    comprovante = await sessao.get(Comprovante, arquivo_id)
    if comprovante is None or comprovante.tenant_id != tenant_id:
        raise _nao_encontrado(tipo_arquivo, arquivo_id)
    return comprovante


def _validar_estado_assinavel(
    tipo_arquivo: str, alvo: AfdArquivo | AejArquivo | Comprovante
) -> None:
    # `comprovantes` nao tem maquina de estado (emitido = pronto sempre) --
    # so afd_arquivos/aej_arquivos precisam da checagem de status.
    if tipo_arquivo not in ("afd", "aej"):
        return
    status = getattr(alvo, "status", None)
    if status in _ESTADOS_NAO_ASSINAVEIS:
        raise ErroDeAplicacao(
            CODIGO_ESTADO_INVALIDO,
            detalhe=(
                f"Arquivo '{tipo_arquivo}' esta com status='{status}': so arquivos "
                "'gerado' ou ja 'assinado' (reassinatura) podem ser assinados."
            ),
        )


async def _obter_conteudo(tipo_arquivo: str, alvo: AfdArquivo | AejArquivo | Comprovante) -> bytes:
    if tipo_arquivo == "comprovante":
        if not isinstance(alvo, Comprovante):  # pragma: no cover - defensivo, ver _resolver_alvo
            raise TypeError("tipo_arquivo='comprovante' mas alvo nao e Comprovante")
        return alvo.conteudo_texto.encode("utf-8")

    conteudo_ref = getattr(alvo, "conteudo_ref", None)
    if not conteudo_ref:
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO,
            detalhe=f"Arquivo '{tipo_arquivo}' nao tem conteudo gravado no armazenamento ainda.",
        )
    return await obter_objeto(conteudo_ref)


async def assinar_arquivo_fiscal(
    sessao: AsyncSession,
    tenant_id: UUID,
    arquivo_id: UUID,
    dados: esquemas.AssinaturaArquivoRequisicao,
    *,
    usuario_id: UUID | None,
) -> ArquivoAssinatura:
    tipo_arquivo = _valor(dados.tipo_arquivo)
    if not tipo_arquivo:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="tipoArquivo e obrigatorio.")
    if tipo_arquivo not in _TIPOS_IMPLEMENTADOS:
        raise ErroDeAplicacao(
            CODIGO_NAO_IMPLEMENTADO,
            detalhe=(
                f"tipoArquivo='{tipo_arquivo}' ainda nao implementado nesta fase (F12): "
                "apenas afd/aej/comprovante. 'espelho' e assinado por POST "
                "/v1/espelhos/{espelhoId}/assinar (F10, mecanismo diferente: aceite "
                "eletronico, nao CAdES); 'relatorio' e de F11."
            ),
        )

    padrao = _valor(dados.padrao) or "CAdES"
    formato = _valor(dados.formato) or "detached"
    if padrao != "CAdES" or formato != "detached":
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Este produto so implementa padrao=CAdES e formato=detached nesta fase.",
        )

    alvo = await _resolver_alvo(sessao, tenant_id, tipo_arquivo, arquivo_id)
    _validar_estado_assinavel(tipo_arquivo, alvo)

    certificado = obter_certificado_configurado()
    if certificado is None:
        raise ErroDeAplicacao(
            CODIGO_CERTIFICADO_INDISPONIVEL,
            detalhe="Certificado ICP-Brasil nao configurado no ambiente.",
        )
    if certificado.expirado:
        raise ErroDeAplicacao(
            CODIGO_CERTIFICADO_EXPIRADO,
            detalhe="O certificado configurado esta fora da janela de validade.",
        )

    conteudo = await _obter_conteudo(tipo_arquivo, alvo)

    assinatura_bytes = cades.assinar_cades(conteudo, certificado)

    # Autoverificacao independente ANTES de gravar qualquer coisa -- ver
    # docstring do modulo. `certificado_esperado` fecha o loop contra o
    # PROPRIO certificado que acabou de assinar (defesa contra um bug de
    # `assinar_cades` que embutisse um certificado errado no CMS).
    certificado_der = certificado.certificado.public_bytes(Encoding.DER)
    resultado = cades.validar_cades(
        conteudo, assinatura_bytes, certificado_esperado=certificado_der
    )
    if not resultado.valido:
        raise ErroDeAplicacao(
            CODIGO_FALHA_GERACAO,
            detalhe=(
                "A assinatura CAdES recem-produzida nao passou na autoverificacao "
                f"independente (motivo: {resultado.motivo_falha}). Nada foi gravado."
            ),
            contexto_log={"tipoArquivo": tipo_arquivo, "arquivoId": str(arquivo_id)},
        )

    chave_assinatura = f"fiscal/assinaturas/{tipo_arquivo}/{arquivo_id}/{uuid4()}.p7s"
    await salvar_objeto(
        chave_assinatura, assinatura_bytes, content_type="application/pkcs7-signature"
    )

    agora = _dt.datetime.now(_dt.UTC)
    carimbo_tempo = agora if dados.carimbo_tempo else None
    politica_assinatura = "CAdES-BES"
    if certificado.rotulo_teste:
        politica_assinatura = (
            f"{politica_assinatura} (certificado de teste: {certificado.rotulo_teste})"
        )

    nova_assinatura = ArquivoAssinatura(
        tenant_id=tenant_id,
        tipo_arquivo=tipo_arquivo,
        arquivo_id=arquivo_id,
        padrao=padrao,
        formato=formato,
        assinatura_ref=chave_assinatura,
        certificado_titular=certificado.titular,
        certificado_serial=certificado.serial,
        certificado_emissor=certificado.emissor,
        certificado_validade_inicio=certificado.validade_inicio,
        certificado_validade_fim=certificado.validade_fim,
        politica_assinatura=politica_assinatura,
        carimbo_tempo=carimbo_tempo,
        hash_arquivo=hashlib.sha256(conteudo).hexdigest(),
        algoritmo_hash="SHA-256",
        status="assinado",
        validado_em=agora,
        validacao_resultado={"valido": resultado.valido, **dataclasses.asdict(resultado)},
        criado_por=usuario_id,
    )
    sessao.add(nova_assinatura)
    await sessao.flush()

    # `afd_arquivos`/`aej_arquivos` refletem a assinatura mais recente no
    # proprio registro (o schema tem `status`/`assinaturaRef` para isso).
    # `comprovantes` NUNCA recebe UPDATE -- e 100% imutavel (UPDATE e DELETE
    # bloqueados por gatilho, `schema.sql` linhas 2289-2292): a assinatura
    # de um comprovante fica registrada SO em `arquivo_assinaturas`, nunca
    # refletida de volta em `comprovantes.assinatura_ref` (achado de
    # contrato documentado no relatorio da fase -- aquela coluna so poderia
    # ser preenchida no INSERT original de F5, que nunca tem certificado
    # disponivel na pratica).
    if tipo_arquivo in ("afd", "aej"):
        alvo.status = "assinado"  # type: ignore[union-attr]
        alvo.assinatura_ref = chave_assinatura  # type: ignore[union-attr]
        await sessao.flush()

    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="arquivo_fiscal.assinado",
        entidade=_ENTIDADE_POR_TIPO[tipo_arquivo],
        acao="assinar",
        entidade_id=arquivo_id,
        usuario_id=usuario_id,
        valor_novo={
            "assinaturaId": str(nova_assinatura.id),
            "tipoArquivo": tipo_arquivo,
            "status": nova_assinatura.status,
            "assinaturaRef": chave_assinatura,
        },
    )

    return nova_assinatura
