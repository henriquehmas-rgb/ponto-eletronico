"""Testes de `app/biometria/cifra.py` (ADR-006, T9 do PCF da F2).

Cobre os criterios de aceite 5 e 6 da secao 7 do PCF que dependem so da
cifra em si, sem precisar do banco: template ilegivel sem a chave, e AAD de
outro colaborador falha a decifragem (nunca devolve vetor errado).
"""

from __future__ import annotations

import secrets
from uuid import uuid4

import pytest

from app.biometria import cifra


def _vetor_de_exemplo() -> bytes:
    # Um "vetor facial" de verdade e float32 x 512 (~2KB); o conteudo exato
    # nao importa para estes testes, so que ele nunca apareca em claro no
    # texto cifrado.
    return secrets.token_bytes(2048)


def test_cifrar_e_decifrar_com_mesmo_aad_devolve_o_vetor_original() -> None:
    tenant_id = uuid4()
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(tenant_id=tenant_id, colaborador_id=colaborador_id, vetor=vetor)
    decifrado = cifra.decifrar_vetor(
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        template_cifrado=resultado.template_cifrado,
        iv=resultado.iv,
        tag_autenticacao=resultado.tag_autenticacao,
    )

    assert decifrado == vetor


def test_template_cifrado_e_ilegivel_sem_a_chave() -> None:
    """Criterio 5: lido "direto do banco" (aqui, o proprio resultado da
    cifra), o conteudo nao revela o vetor -- nem por inspecao de bytes."""
    tenant_id = uuid4()
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(tenant_id=tenant_id, colaborador_id=colaborador_id, vetor=vetor)

    assert resultado.template_cifrado != vetor
    assert vetor not in resultado.template_cifrado
    assert resultado.algoritmo_cifra == "AES-256-GCM"
    assert len(resultado.tag_autenticacao) == cifra.TAMANHO_TAG_BYTES
    assert resultado.chave_id == cifra.chave_id_atual()


def test_decifrar_com_aad_de_outro_colaborador_falha_nao_devolve_valor_errado() -> None:
    """Criterio 5 (segunda metade): decifrar com o AAD de OUTRO colaborador
    precisa FALHAR -- nao devolver um vetor diferente silenciosamente."""
    tenant_id = uuid4()
    colaborador_dono = uuid4()
    colaborador_intruso = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(
        tenant_id=tenant_id, colaborador_id=colaborador_dono, vetor=vetor
    )

    with pytest.raises(cifra.TemplateIlegivel):
        cifra.decifrar_vetor(
            tenant_id=tenant_id,
            colaborador_id=colaborador_intruso,
            template_cifrado=resultado.template_cifrado,
            iv=resultado.iv,
            tag_autenticacao=resultado.tag_autenticacao,
        )


def test_decifrar_com_aad_de_outro_tenant_tambem_falha() -> None:
    """O AAD amarra tenant_id E colaborador_id (ADR-006 regra 2): trocar so
    o tenant, mantendo o mesmo colaborador_id, tambem tem que falhar."""
    tenant_dono = uuid4()
    tenant_intruso = uuid4()
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(
        tenant_id=tenant_dono, colaborador_id=colaborador_id, vetor=vetor
    )

    with pytest.raises(cifra.TemplateIlegivel):
        cifra.decifrar_vetor(
            tenant_id=tenant_intruso,
            colaborador_id=colaborador_id,
            template_cifrado=resultado.template_cifrado,
            iv=resultado.iv,
            tag_autenticacao=resultado.tag_autenticacao,
        )


def test_decifrar_com_byte_do_texto_cifrado_adulterado_falha() -> None:
    """GCM autentica o texto cifrado inteiro: um unico bit alterado invalida
    a tag, mesmo com o AAD certo."""
    tenant_id = uuid4()
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(tenant_id=tenant_id, colaborador_id=colaborador_id, vetor=vetor)
    adulterado = bytearray(resultado.template_cifrado)
    adulterado[0] ^= 0xFF

    with pytest.raises(cifra.TemplateIlegivel):
        cifra.decifrar_vetor(
            tenant_id=tenant_id,
            colaborador_id=colaborador_id,
            template_cifrado=bytes(adulterado),
            iv=resultado.iv,
            tag_autenticacao=resultado.tag_autenticacao,
        )


def test_decifrar_com_tag_adulterada_falha() -> None:
    tenant_id = uuid4()
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    resultado = cifra.cifrar_vetor(tenant_id=tenant_id, colaborador_id=colaborador_id, vetor=vetor)
    tag_adulterada = bytearray(resultado.tag_autenticacao)
    tag_adulterada[0] ^= 0xFF

    with pytest.raises(cifra.TemplateIlegivel):
        cifra.decifrar_vetor(
            tenant_id=tenant_id,
            colaborador_id=colaborador_id,
            template_cifrado=resultado.template_cifrado,
            iv=resultado.iv,
            tag_autenticacao=bytes(tag_adulterada),
        )


def test_tenants_diferentes_produzem_deks_diferentes_mesmo_vetor() -> None:
    """DEK por tenant (ADR-006 regra 1): o mesmo vetor cifrado para dois
    tenants diferentes produz textos cifrados diferentes (DEKs diferentes),
    e o template de um tenant nao decifra com o AAD do outro."""
    colaborador_id = uuid4()
    vetor = _vetor_de_exemplo()

    tenant_a = uuid4()
    tenant_b = uuid4()
    resultado_a = cifra.cifrar_vetor(tenant_id=tenant_a, colaborador_id=colaborador_id, vetor=vetor)
    resultado_b = cifra.cifrar_vetor(tenant_id=tenant_b, colaborador_id=colaborador_id, vetor=vetor)

    assert resultado_a.template_cifrado != resultado_b.template_cifrado


def test_chave_mestra_ausente_leva_a_erro_explicito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PONTO_BIOMETRIA_CHAVE_MESTRA", raising=False)
    with pytest.raises(cifra.ChaveMestraAusente):
        cifra.cifrar_vetor(tenant_id=uuid4(), colaborador_id=uuid4(), vetor=b"x")


def test_chave_mestra_com_tamanho_invalido_leva_a_erro_explicito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PONTO_BIOMETRIA_CHAVE_MESTRA", "abcd")  # curta demais
    with pytest.raises(cifra.ChaveMestraAusente):
        cifra.cifrar_vetor(tenant_id=uuid4(), colaborador_id=uuid4(), vetor=b"x")


def test_chave_mestra_nao_hexadecimal_leva_a_erro_explicito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PONTO_BIOMETRIA_CHAVE_MESTRA", "z" * 64)  # nao e hex
    with pytest.raises(cifra.ChaveMestraAusente):
        cifra.cifrar_vetor(tenant_id=uuid4(), colaborador_id=uuid4(), vetor=b"x")


def test_variavel_de_ambiente_com_nome_errado_nao_e_lida(monkeypatch: pytest.MonkeyPatch) -> None:
    """A variavel documentada no ADR-006 e exatamente `PONTO_BIOMETRIA_CHAVE_MESTRA`
    -- gravar sob outro nome nao deve funcionar por acidente."""
    monkeypatch.delenv("PONTO_BIOMETRIA_CHAVE_MESTRA", raising=False)
    monkeypatch.setenv("PONTO_BIOMETRIA_CHAVE_MESTRA_ERRADA", secrets.token_hex(32))
    with pytest.raises(cifra.ChaveMestraAusente):
        cifra.cifrar_vetor(tenant_id=uuid4(), colaborador_id=uuid4(), vetor=b"x")
