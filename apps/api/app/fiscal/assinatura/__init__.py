"""Assinatura eletronica CAdES de arquivos fiscais (F12/A3).

Modulos:

* `certificado.py` -- le a configuracao do certificado ICP-Brasil do
  ambiente (`app.core.config.Configuracao`) e carrega o par certificado/
  chave privada de um arquivo `.pfx`/`.p12`.
* `cades.py` -- assina (`assinar_cades`) e verifica de forma independente
  (`validar_cades`) uma assinatura CMS/PKCS#7 destacada, perfil CAdES-BES.
  Funcoes puras sobre bytes: nao tocam banco nem MinIO.
* `servico.py` -- orquestra `assinarArquivoFiscal`: resolve o arquivo de
  origem (AFD/AEJ/comprovante), grava o `.p7s` no armazenamento de objetos,
  grava `arquivo_assinaturas` e a trilha de auditoria.

Esta e a UNICA assinatura eletronica desta fase que usa certificado
ICP-Brasil. Nao confundir com `assinaturas_espelho` (aceite eletronico do
colaborador, F10) -- ver PCF F12 secao 2.14.
"""

from __future__ import annotations
