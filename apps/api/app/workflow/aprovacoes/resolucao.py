"""Resolução do aprovador responsável por uma etapa da cadeia (F10, T2/T3,
agente A1) -- quem, especificamente, deve decidir uma etapa de `papel`
`gestor`/`rh` para um dado colaborador.

**Fonte, não invenção:** `colaborador_gestores` (F2, seção 5 do
`schema.sql`) já existe com exatamente este propósito -- o comentário da
própria tabela diz "Define a árvore de subordinados que o perfil gestor
enxerga e A CADEIA DE APROVAÇÃO DAS SOLICITAÇÕES" (`schema.sql` linha
1027-1028), e a coluna `tipo` já aceita o valor `'rh'` com o comentário
"analista responsável" (linha 1029) -- ou seja, o mesmo mecanismo cobre
tanto o gestor imediato quanto o analista de RH responsável por um
colaborador especifico, sem precisar de uma segunda tabela nem de acoplar
este modulo ao RBAC (`app.identidade.rbac`, fora do "Consome" do PCF desta
fase).

`resolver_aprovador_papel` devolve o `usuarios.id` do responsável quando
`colaborador_gestores` tem uma linha vigente do `tipo` correspondente
(`'imediato'` para papel `gestor`, `'rh'` para papel `rh`) E essa pessoa tem
uma conta de usuário (`usuarios.colaborador_id`) -- senão devolve `None`.
Para os papéis `diretoria`/`sistema` (sem `tipo` correspondente em
`colaborador_gestores`), sempre devolve `None`: não há um "titular" único
para pré-atribuir, a etapa fica com `aprovacoes.aprovador_usuario_id=NULL` e
`listarAprovacoesPendentes` (T3) enxerga essas etapas pelo casamento de
`papel` contra os perfis RBAC do próprio sujeito (`Sujeito.perfis`, já
resolvido por F1 -- este módulo não lê RBAC, só devolve `None` e deixa quem
lista decidir a visibilidade).

`aprovador_usuario_id=None` não impede a etapa de ser decidida: é só a
pré-atribuição da fila que fica ausente; qualquer usuário com a permissão
`aprovacoes.aprovar` e o `papel` certo ainda consegue decidir via
`decidirAprovacao` (T3) -- a autorização de QUEM PODE decidir não depende
deste módulo.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ColaboradorGestor, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

#: `aprovacoes.papel` -> `colaborador_gestores.tipo` correspondente. Só os
#: dois papéis com um "titular" único e resolvível por hierarquia/atribuição
#: (schema.sql, `colaborador_gestores.tipo` CHECK).
_TIPO_GESTOR_POR_PAPEL: dict[str, str] = {
    "gestor": "imediato",
    "rh": "rh",
}


async def resolver_aprovador_papel(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID,
    papel: str,
    data_referencia: dt.date,
) -> UUID | None:
    tipo = _TIPO_GESTOR_POR_PAPEL.get(papel)
    if tipo is None:
        return None

    gestor_colaborador_id = (
        await sessao.execute(
            sa.select(ColaboradorGestor.gestor_colaborador_id)
            .where(
                ColaboradorGestor.tenant_id == tenant_id,
                ColaboradorGestor.colaborador_id == colaborador_id,
                ColaboradorGestor.tipo == tipo,
                ColaboradorGestor.vigencia_inicio <= data_referencia,
                sa.or_(
                    ColaboradorGestor.vigencia_fim.is_(None),
                    ColaboradorGestor.vigencia_fim >= data_referencia,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if gestor_colaborador_id is None:
        return None

    return (
        await sessao.execute(
            sa.select(Usuario.id)
            .where(
                Usuario.tenant_id == tenant_id,
                Usuario.colaborador_id == gestor_colaborador_id,
                Usuario.excluido_em.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
