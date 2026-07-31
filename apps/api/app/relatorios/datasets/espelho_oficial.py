"""Dataset do item 1 do catálogo -- espelho de ponto oficial (F11, T12, A4).

Segue o contrato fixado por `app.relatorios.catalogo`/`app.relatorios.motor`
(leia as duas docstrings antes de mexer aqui): recebe
`(sessao, tenant_id, contexto: ContextoConsulta)`, devolve um
`sqlalchemy.Select` **linha a linha** (nunca `GROUP BY` -- é responsabilidade
exclusiva do motor), com toda coluna de `RelatorioDefinicao.colunas_
disponiveis` exposta via `.label(chave)`, EXATAMENTE as chaves que
`apps/api/tests/f11/conftest.py::_CATALOGO_RELATORIOS` já semeia para
`codigo="espelho-oficial"` (`dataset="espelho_oficial"`, formato coordenado
entre A1/A4, ver aquele módulo): `colaboradorNome`, `vinculoId`,
`periodoCodigo`, `versao`, `tipo`, `assinado`, `assinadoEm`.

**Só lê `espelhos`/`assinaturas_espelho` (F10) -- nunca gera nem assina um
espelho novo.** Este módulo não importa `app.workflow.fechamento.espelho`
nem `app.workflow.fechamento.servico` (proibição 3, PCF §9 -- "não reabra
nem reescreva um período fechado, nem gere um novo espelho de ponto
oficial"); a prova estática dessa restrição está em
`apps/api/tests/f11/espelho_oficial/test_espelho_oficial.py`.

**Por que o filtro de `tipo` é sempre restrito a `oficial`/`retificado`,
mesmo sem o cliente pedir:** o item 1 do catálogo (PROJETO.md §9) É
literalmente "Espelho de ponto oficial" -- um espelho `previo` (rascunho,
antes do fechamento) nunca é "oficial" e não pertence a este relatório,
mesmo que a tabela `espelhos` guarde as três variantes na mesma linha (T12,
PCF §6: "filtrados por período/escopo/tipo='oficial' ou 'retificado'").
O filtro adicional `filtros.tipo` (`RelatorioDefinicao.filtros_disponiveis`,
já semeado por A1) só ESTREITA esse conjunto-base (ex.: só `oficial`, sem
retificações) -- nunca o alarga; pedir `filtros={"tipo":"previo"}` combina
com a restrição de base via `AND` e devolve zero linhas, não erro (mesmo
padrão de "zero linhas é reflexo do escopo pedido, não falha" que o resto do
PCF já estabelece, §2.3).

**`assinado`/`assinadoEm` vêm de uma subconsulta agregada sobre
`assinaturas_espelho`** (`MAX(carimbo_tempo)` por `espelho_id`, filtrado a
`status='assinado'`): um espelho pode ter mais de uma linha de assinatura
(`signatario_tipo` diferente -- colaborador, gestor, rh, empregador,
`schema.sql`), e "assinado" aqui significa "existe pelo menos um aceite
registrado", com `assinadoEm` sendo o mais recente. Não confundir com
`Espelho.tipo`: um espelho pode estar assinado e ainda ser `tipo='previo'`
(o aceite é sobre o CONTEÚDO gerado, independente do tipo) -- mas como este
dataset já restringe a `oficial`/`retificado` na base, só espelhos
realmente oficiais aparecem aqui de qualquer forma.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import AssinaturaEspelho, Colaborador, Espelho, Periodo

from app.core.erros import ErroDeAplicacao
from app.relatorios.catalogo import registrar_dataset

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.relatorios.motor import ContextoConsulta

#: Mesmo código que `motor.py::CODIGO_CONSULTA_INVALIDA` -- reaproveitado
#: aqui (não redeclarado com outro nome) para um `filtros.vinculoId`/
#: `filtros.tipo` malformado responder exatamente o mesmo `PONTO-VAL-005`
#: que o resto do motor já usa para "parametro de query fora do dominio"
#: (PCF §2.8 item 5, proibição 5 -- nenhum código de erro novo).
_CODIGO_CONSULTA_INVALIDA = "PONTO-VAL-005"

#: Conjunto-base de `Espelho.tipo` aceito por este dataset -- ver docstring
#: do módulo. `previo` nunca aparece aqui, mesmo que `espelhos` guarde as
#: três variantes na mesma tabela.
_TIPOS_OFICIAIS = ("oficial", "retificado")


def _uuid_do_filtro(contexto: ContextoConsulta, chave: str) -> UUID | None:
    """Lê `contexto.filtros[chave]` (JSON decodificado por `motor.py::
    montar_contexto_consulta`) como `UUID`, ou `None` se ausente.
    `PONTO-VAL-005` se o valor existir mas não for um UUID válido -- mesmo
    tratamento que `motor.py` já dá a parâmetro de consulta fora do
    domínio."""
    bruto = contexto.filtros.get(chave)
    if bruto is None:
        return None
    try:
        return UUID(str(bruto))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ErroDeAplicacao(
            _CODIGO_CONSULTA_INVALIDA, detalhe=f"filtros.{chave} deve ser um UUID valido."
        ) from exc


def espelho_oficial(
    sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta
) -> Select[Any]:
    """Lista espelhos oficiais/retificados já gerados por F10 -- nunca gera
    nenhum novo (ver docstring do módulo). Zero linhas quando o escopo
    pedido ainda não tem espelho oficial emitido é o comportamento esperado,
    não um erro."""
    ultima_assinatura = (
        sa.select(
            AssinaturaEspelho.espelho_id.label("espelho_id"),
            sa.func.max(AssinaturaEspelho.carimbo_tempo).label("assinado_em"),
        )
        .where(
            AssinaturaEspelho.tenant_id == tenant_id,
            AssinaturaEspelho.status == "assinado",
        )
        .group_by(AssinaturaEspelho.espelho_id)
        .subquery()
    )

    consulta = (
        sa.select(
            Colaborador.nome_completo.label("colaboradorNome"),
            Espelho.vinculo_id.label("vinculoId"),
            Periodo.codigo.label("periodoCodigo"),
            Espelho.versao.label("versao"),
            Espelho.tipo.label("tipo"),
            ultima_assinatura.c.assinado_em.is_not(None).label("assinado"),
            ultima_assinatura.c.assinado_em.label("assinadoEm"),
        )
        .select_from(Espelho)
        .join(Colaborador, Colaborador.id == Espelho.colaborador_id)
        .join(Periodo, Periodo.id == Espelho.periodo_id)
        .outerjoin(ultima_assinatura, ultima_assinatura.c.espelho_id == Espelho.id)
        .where(
            Espelho.tenant_id == tenant_id,
            Colaborador.tenant_id == tenant_id,
            Periodo.tenant_id == tenant_id,
            Espelho.tipo.in_(_TIPOS_OFICIAIS),
        )
    )

    if contexto.periodo_id is not None:
        consulta = consulta.where(Espelho.periodo_id == contexto.periodo_id)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(Espelho.colaborador_id == contexto.colaborador_id)

    vinculo_id = _uuid_do_filtro(contexto, "vinculoId")
    if vinculo_id is not None:
        consulta = consulta.where(Espelho.vinculo_id == vinculo_id)

    tipo_pedido = contexto.filtros.get("tipo")
    if tipo_pedido is not None:
        consulta = consulta.where(Espelho.tipo == str(tipo_pedido))

    return consulta


registrar_dataset("espelho_oficial", espelho_oficial)
