"""Emissao do comprovante de registro de ponto.

`emitir_comprovante` roda na MESMA transacao da marcacao -- e chamado pela
pipeline de ingestao (`app.marcacao.pipeline.ingestao`, A2/T6) logo apos
`app.marcacao.dominio.registro.persistir_marcacao` (A1/T3), antes do commit.
A Portaria dispensa a impressao no momento da marcacao porque o produto
garante acesso eletronico permanente ao comprovante, e um comprovante sem
NSR nao cumpre essa promessa -- por isso a emissao nao pode esperar um job
separado. Esta funcao so grava a linha em `comprovantes`; publicar o evento
`comprovante.emitido` e responsabilidade de quem chama (ver
`app/marcacao/comprovantes/eventos_comprovante.py`), para o dia em que um
segundo caminho de emissao existir sem publicar duas vezes.

**Formato de `numero`** (unico por tenant -- `uq_comprovantes_numero` nao e
por empresa, ver `packages/contracts/schema.sql`): `AAAAMMDD` (data local da
marcacao, no fuso do proprio registro, `marcacoes.fuso_horario`) seguido do
NSR com 8 digitos, por exemplo `2026072500001842` para o NSR 1842 emitido em
25/07/2026 -- identico ao exemplo de `packages/contracts/events.yaml`. Essa
base sozinha e unica DENTRO de um REP-P (o NSR de um REP-P nunca se repete,
`nsr_emissoes`), mas pode colidir ENTRE REP-Ps distintos do mesmo tenant que,
por coincidencia, emitam o mesmo NSR no mesmo dia civil (cada REP-P comeca
sua propria sequencia em 1 -- ADR-003). Por isso: quando o tenant ja teve
mais de um REP-P cadastrado (`rep_ps`, contagem SEM filtro de status -- um
REP-P substituido pode ter emitido comprovantes cuja base "nua" ainda
precisamos continuar distinguindo), o numero recebe o prefixo
`<identificador do REP-P>-` na frente da base. Tenant com um unico REP-P (o
caso normal, ver `packages/contracts/schema.sql`, comentario de `rep_ps`)
mantem exatamente o formato do exemplo do contrato, sem prefixo.

`conteudo_texto` traz os campos legalmente relevantes (NSR, CPF, data/hora,
canal, hash) o bastante para dispensar a impressao no ato -- o leiaute
oficial completo e conferido pela F12; aqui a exigencia e "completo o
bastante", nao conformidade certificada. `assinatura_ref` fica `NULL` ate a
F12 assinar em CAdES. `disponivel_ate` fica `NULL` de proposito: o padrao do
produto e disponibilidade permanente (a exigencia legal minima e so as
ultimas 48h, ver T11/`listarComprovantesRecentes`).
"""

from __future__ import annotations

import hashlib
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from ponto_contracts import Comprovante as ComprovanteOrm
from ponto_contracts import Marcacao as MarcacaoOrm
from ponto_contracts import RepP
from sqlalchemy.ext.asyncio import AsyncSession

#: Canal de entrega padrao quando a marcacao nao diz de outro jeito. O
#: contrato (`Comprovante.canalEntrega`) nao amarra o canal do comprovante ao
#: canal da marcacao -- `app` e o destino universal (app e web leem o mesmo
#: recurso), entao mante-lo fixo aqui e correto para as 5 origens de
#: `MarcacaoCriar.canal`.
CANAL_ENTREGA_PADRAO = "app"


async def _quantidade_rep_ps_do_tenant(sessao: AsyncSession, tenant_id: object) -> int:
    """Quantos REP-P (qualquer status) o tenant ja teve. Mais de um implica
    risco de colisao de `numero` entre sequencias de NSR independentes (ver
    docstring do modulo)."""
    resultado = await sessao.execute(
        sa.select(sa.func.count()).select_from(RepP).where(RepP.tenant_id == tenant_id)
    )
    return int(resultado.scalar_one())


async def _montar_numero(sessao: AsyncSession, marcacao: MarcacaoOrm) -> str:
    fuso = ZoneInfo(marcacao.fuso_horario)
    data_local = marcacao.datahora_marcacao.astimezone(fuso).date()
    base = f"{data_local:%Y%m%d}{marcacao.nsr:08d}"
    if await _quantidade_rep_ps_do_tenant(sessao, marcacao.tenant_id) > 1:
        rep_p = await sessao.get(RepP, marcacao.rep_p_id)
        identificador = rep_p.identificador if rep_p is not None else str(marcacao.rep_p_id)
        return f"{identificador}-{base}"
    return base


def _montar_conteudo_texto(marcacao: MarcacaoOrm, numero: str) -> str:
    """Corpo textual minimo para dispensar a impressao no ato (Portaria MTP
    671/2021). O leiaute oficial completo e conferido pela F12; aqui a
    exigencia e conteudo completo o bastante, nao conformidade certificada."""
    linhas = [
        "COMPROVANTE DE REGISTRO DE PONTO",
        f"Numero: {numero}",
        f"NSR: {marcacao.nsr}",
        f"CPF: {marcacao.cpf}",
        f"Data e hora do registro: {marcacao.datahora_marcacao.isoformat()}",
        f"Canal: {marcacao.canal}",
        f"Hash do registro: {marcacao.hash_registro}",
    ]
    return "\n".join(linhas)


async def emitir_comprovante(sessao: AsyncSession, marcacao: MarcacaoOrm) -> ComprovanteOrm:
    """Emite o comprovante da marcacao recem-gravada, na MESMA transacao.

    Nao commita: quem chama (a pipeline de ingestao, T6/A2) controla a
    transacao inteira -- marcacao, meta e comprovante sobem ou caem juntos.
    Nao publica o evento `comprovante.emitido`: ver docstring do modulo.
    """
    numero = await _montar_numero(sessao, marcacao)
    conteudo_texto = _montar_conteudo_texto(marcacao, numero)
    hash_sha256 = hashlib.sha256(conteudo_texto.encode("utf-8")).hexdigest()

    comprovante = ComprovanteOrm(
        tenant_id=marcacao.tenant_id,
        marcacao_id=marcacao.id,
        marcacao_datahora=marcacao.datahora_marcacao,
        colaborador_id=marcacao.colaborador_id,
        cpf=marcacao.cpf,
        numero=numero,
        nsr=marcacao.nsr,
        conteudo_texto=conteudo_texto,
        hash_sha256=hash_sha256,
        canal_entrega=CANAL_ENTREGA_PADRAO,
        criado_por=marcacao.criado_por,
    )
    sessao.add(comprovante)
    await sessao.flush()
    return comprovante
