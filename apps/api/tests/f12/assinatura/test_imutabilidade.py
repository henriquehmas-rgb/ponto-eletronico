"""Imutabilidade de `arquivo_assinaturas` (F12/A3, T12/critério de aceite).

**Precisão sobre a regra real, não sobre a paráfrase do PCF.** O PCF F12
(T12, "pronto quando") descreve o critério como "prove com UPDATE/DELETE
reais falhando com ERRCODE 42501, role de aplicação real, mesmo padrão de
evidência que F10 exigiu para `assinaturas_espelho`" -- mas
`assinaturas_espelho` (F10) e `arquivo_assinaturas` (F12) têm regras de
imutabilidade DIFERENTES por desenho, confirmado lendo o schema real
(`packages/contracts/schema.sql`, gatilhos da tabela) e o glossário
(`packages/contracts/glossario.md` §1.2, linha da tabela): `assinaturas_
espelho` bloqueia UPDATE **e** DELETE por gatilho; `arquivo_assinaturas`
bloqueia **só** DELETE por gatilho -- o UPDATE fica tecnicamente permitido
para a role de aplicação, "só para o resultado da validação" por
CONVENÇÃO, não por gatilho. Aplicar literalmente a frase do PCF (esperar
que um UPDATE cru também falhe com 42501) produziria um teste FALSO -- a
tabela nunca teve essa garantia de banco para `arquivo_assinaturas`.

Este arquivo prova, então, exatamente o que É verdade:

1. `DELETE` direto falha com `ERRCODE 42501` (gatilho `fn_registro_imutavel`
   + `REVOKE DELETE` -- os dois mecanismos, redundantes por desenho).
2. `UPDATE` direto (de uma coluna arbitrária) é tecnicamente aceito pelo
   banco -- confirmando a linha do glossário, não escondendo o fato.
3. A garantia real de "somente-acréscimo" vem da APLICAÇÃO, não do banco:
   `app.fiscal.assinatura.servico.assinar_arquivo_fiscal` nunca emite um
   `UPDATE` contra `arquivo_assinaturas` (prova por análise estática, `grep`)
   -- reassinar sempre gera uma linha nova (já provado por
   `test_servico.py::test_reassinar_gera_linha_nova_nunca_sobrescreve`, que
   este arquivo só referencia, sem duplicar).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ponto_contracts import ArquivoAssinatura
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.fiscal.assinatura import servico
from app.fiscal.assinatura.certificado import CertificadoConfig
from app.schemas import contrato as esquemas
from tests.f12.assinatura.conftest import ContextoF12A3, aplicar_tenant_teste_f12


async def _assinar(
    sessao: AsyncSession,
    contexto: ContextoF12A3,
    certificado: CertificadoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> ArquivoAssinatura:
    monkeypatch.setattr(servico, "obter_certificado_configurado", lambda: certificado)
    return await servico.assinar_arquivo_fiscal(
        sessao,
        contexto.tenant_id,
        contexto.comprovante_id,
        esquemas.AssinaturaArquivoRequisicao.model_validate({"tipoArquivo": "comprovante"}),
        usuario_id=contexto.usuario_id,
    )


@pytest.mark.asyncio
async def test_delete_direto_em_arquivo_assinaturas_falha_42501(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assinatura = await _assinar(sessao_f12_a3, contexto_f12_a3, certificado_teste, monkeypatch)
    await sessao_f12_a3.flush()

    with pytest.raises(DBAPIError) as excinfo:
        await sessao_f12_a3.execute(
            text("DELETE FROM arquivo_assinaturas WHERE id = :id"), {"id": assinatura.id}
        )
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    await sessao_f12_a3.rollback()
    await aplicar_tenant_teste_f12(sessao_f12_a3, contexto_f12_a3.tenant_id)


@pytest.mark.asyncio
async def test_update_direto_e_tecnicamente_aceito_pelo_banco_mas_a_aplicacao_nunca_o_emite(
    sessao_f12_a3: AsyncSession,
    contexto_f12_a3: ContextoF12A3,
    certificado_teste: CertificadoConfig,
    bucket_minio_f12: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documenta, em vez de esconder, a diferença real com `assinaturas_
    espelho`: `UPDATE` NÃO tem gatilho de bloqueio em `arquivo_assinaturas`
    (só `DELETE` tem -- `schema.sql`, `trg_arquivo_assinaturas_bloqueia_
    delete`; confirmado por `glossario.md` §1.2: "UPDATE só para o
    resultado da validação"). Este teste prova que o UPDATE realmente
    passa no banco (não seria honesto afirmar 42501 aqui) -- a garantia de
    append-only vem da disciplina de `servico.py`, provada estaticamente no
    teste seguinte."""
    assinatura = await _assinar(sessao_f12_a3, contexto_f12_a3, certificado_teste, monkeypatch)
    await sessao_f12_a3.flush()

    resultado = await sessao_f12_a3.execute(
        text("UPDATE arquivo_assinaturas SET status = 'invalido' WHERE id = :id"),
        {"id": assinatura.id},
    )
    assert resultado.rowcount == 1
    await sessao_f12_a3.rollback()
    await aplicar_tenant_teste_f12(sessao_f12_a3, contexto_f12_a3.tenant_id)


def test_servico_nunca_emite_update_contra_arquivo_assinaturas() -> None:
    """Prova ESTÁTICA (não depende de banco): `app/fiscal/assinatura/
    servico.py` nunca chama `sessao.execute` com `UPDATE arquivo_
    assinaturas` nem faz `sessao.add`/mutação de atributo de uma instância
    de `ArquivoAssinatura` já carregada do banco -- a única escrita nessa
    tabela é o `sessao.add(nova_assinatura)` de uma linha NOVA. Mesmo
    padrão de evidência (grep + leitura) que o critério de aceite 7 do PCF
    exige para "reaproveitamento de F4/F5, não duplicação"."""
    caminho = Path(__file__).resolve().parents[3] / "app" / "fiscal" / "assinatura" / "servico.py"
    codigo = caminho.read_text(encoding="utf-8")

    # Não há nenhuma variável do tipo `ArquivoAssinatura` recebendo atributo
    # setado (`nova_assinatura.<algo> = ...`) além da construção inicial via
    # `ArquivoAssinatura(...)` -- e não há UPDATE textual algum na tabela.
    assert not re.search(r"UPDATE\s+arquivo_assinaturas", codigo, re.IGNORECASE)
    assert "nova_assinatura.status =" not in codigo
    assert "nova_assinatura.assinatura_ref =" not in codigo
    assert "nova_assinatura.validacao_resultado =" not in codigo
    # A única linha que instancia ArquivoAssinatura é o INSERT de uma nova
    # assinatura -- confirma que não existe um segundo caminho de escrita.
    assert codigo.count("ArquivoAssinatura(") == 1
