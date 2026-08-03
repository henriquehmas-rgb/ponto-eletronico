"""T19 (A8) -- teste ADVERSARIAL do critério de aceite 4/8 do PCF F13:
"importar um AFD de outro fabricante, mesmo com NSR colidindo numericamente
com o nosso, nunca produz duas marcações com o mesmo (rep_p_id, nsr) na
sequência própria -- a marcação importada nunca aparece em `nsr_emissoes`".

ADR-003 item 6: "Marcações importadas de AFD de outro fabricante (F13) vivem
em namespace de NSR separado e nunca tocam a sequência do nosso REP-P."

A prova, ponto a ponto:

1. Uma marcação REAL é gravada pelo pipeline real de F5
   (`persistir_marcacao`), alocando NSR=1 de verdade em `nsr_sequencias`
   e criando a linha correspondente em `nsr_emissoes`.
2. Um AFD de terceiro é importado para o MESMO REP-P com um registro tipo 7
   cujo NSR também é 1 (colisão numérica deliberada).
3. A importação TERMINA COM SUCESSO (não é rejeitada por colisão -- é
   exatamente o cenário que o namespace separado precisa suportar).
4. `nsr_emissoes` continua com EXATAMENTE UMA linha para
   `(tenant_id, rep_p_id, nsr=1)` -- a real, nunca duas.
5. A marcação importada existe em `marcacoes` (mesmo NSR numérico,
   `canal='importacao'`) mas NÃO tem entrada correspondente em
   `nsr_emissoes`.
6. `nsr_sequencias` (o alocador transacional) não foi tocado pela
   importação: `proximo_nsr`/`ultimo_nsr_emitido`/`ultimo_hash` continuam
   exatamente o que a alocação real produziu.
7. `app.marcacao.dominio.verificacao_nsr.verificar_sequencia_nsr` -- o
   verificador OFICIAL de continuidade que `GET /v1/marcacoes/nsr/verificar`
   expõe -- continua reportando a sequência do REP-P como íntegra
   (`integro=True`, sem lacunas), inteiramente alheio à existência da
   marcação importada.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from ponto_contracts import Importacao, Marcacao, NsrEmissao, NsrSequencia
from sqlalchemy.ext.asyncio import AsyncSession

from app.integracoes.importadores.afd_terceiro.servico import processar_arquivo
from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from app.marcacao.dominio.verificacao_nsr import verificar_sequencia_nsr
from tests.f13.conftest import ContextoF13, aplicar_tenant_teste
from tests.f13.importadores.afd_terceiro.conftest import montar_arquivo_afd


async def test_nsr_colidindo_nao_produz_segunda_emissao_nem_corrompe_sequencia(
    sessao_f13: AsyncSession,
    contexto_f13: ContextoF13,
    criar_rep_p,
    criar_colaborador_ativo,
) -> None:
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    # `nsr_sequencias` só é criada quando o cadastro do REP-P (F12) faz o
    # `INSERT` correspondente -- esta fixture (F13/A8) segue o mesmo padrão
    # que `tests/f12/conftest.py` já estabelece: semear diretamente.
    await sessao_f13.execute(
        sa.text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (gen_random_uuid(), :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"tenant_id": str(contexto_f13.tenant_id), "rep_p_id": str(rep_p.id)},
    )
    colaborador = await criar_colaborador_ativo(
        tenant_id=contexto_f13.tenant_id, empresa_id=contexto_f13.empresa_id, cpf="12345678909"
    )

    # 1. Marcacao REAL via o pipeline de verdade de F5 -- aloca NSR=1.
    momento_real = dt.datetime(2026, 1, 1, 8, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3)))
    dados = DadosMarcacao(
        rep_p_id=rep_p.id,
        empresa_id=contexto_f13.empresa_id,
        cpf=colaborador.cpf,
        canal="terminal",
        datahora_marcacao=momento_real,
        colaborador_id=colaborador.id,
        vinculo_id=colaborador.vinculo_id,
        tipo_registro="7",
    )
    marcacao_real = await persistir_marcacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, dados=dados
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    assert marcacao_real.nsr == 1

    # 2. Importa um AFD de terceiro com um registro tipo 7 de NSR=1 TAMBEM,
    # deliberadamente colidindo com o NSR real recem-alocado, para o MESMO
    # REP-P (decisao documentada em servico.py: rep_p_id real, nao marcador
    # dedicado).
    importacao = Importacao(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        tipo="afd_terceiro",
        origem="afd",
        nome_arquivo="afd_terceiro_colidindo.txt",
        status="recebido",
    )
    sessao_f13.add(importacao)
    await sessao_f13.flush()

    # NSR=1 colide de proposito com o NSR real acima; data distinta evita
    # colidir com a PK/UNIQUE de particao (tenant_id, rep_p_id, nsr,
    # datahora_marcacao).
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {
                "nsr": 1,
                "datahora_marc": "2025-06-15T10:00:00-0300",
                "cpf": colaborador.cpf,
            }
        ]
    )

    # 3. A importacao TERMINA COM SUCESSO -- nao ha rejeicao por colisao,
    # porque colidir numericamente e exatamente o cenario que o namespace
    # separado precisa suportar sem quebrar nada.
    resultado = await processar_arquivo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id=rep_p.id,
        importacao=importacao,
        conteudo=conteudo,
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    assert resultado.linhas_sucesso == 1
    assert resultado.linhas_erro == 0

    # 4. `nsr_emissoes` continua com EXATAMENTE UMA linha para
    # (tenant_id, rep_p_id, nsr=1) -- a REAL. Nunca duas.
    emissoes_nsr1 = (
        (
            await sessao_f13.execute(
                sa.select(NsrEmissao).where(
                    NsrEmissao.tenant_id == contexto_f13.tenant_id,
                    NsrEmissao.rep_p_id == rep_p.id,
                    NsrEmissao.nsr == 1,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(emissoes_nsr1) == 1, (
        f"esperava exatamente 1 linha em nsr_emissoes para nsr=1, achou {len(emissoes_nsr1)} "
        "-- a marcacao importada NUNCA pode ganhar entrada em nsr_emissoes"
    )
    assert emissoes_nsr1[0].marcacao_id == marcacao_real.id

    # 5. As DUAS marcacoes (real + importada) existem em `marcacoes`, com o
    # MESMO nsr numerico, distinguidas por canal/origem_importacao_id.
    marcacoes_nsr1 = (
        (
            await sessao_f13.execute(
                sa.select(Marcacao)
                .where(
                    Marcacao.tenant_id == contexto_f13.tenant_id,
                    Marcacao.rep_p_id == rep_p.id,
                    Marcacao.nsr == 1,
                )
                .order_by(Marcacao.canal)
            )
        )
        .scalars()
        .all()
    )
    # As duas marcacoes (real + importada) devem coexistir com nsr=1.
    assert len(marcacoes_nsr1) == 2
    canais = {linha.canal for linha in marcacoes_nsr1}
    assert canais == {"terminal", "importacao"}

    marcacao_importada = next(m for m in marcacoes_nsr1 if m.canal == "importacao")
    assert marcacao_importada.origem_importacao_id == importacao.id
    assert marcacao_importada.id != marcacao_real.id

    # 6. `nsr_sequencias` (o alocador transacional) NAO foi tocado pela
    # importacao -- continua exatamente o que a alocacao REAL produziu.
    sequencia = (
        await sessao_f13.execute(
            sa.select(NsrSequencia).where(
                NsrSequencia.tenant_id == contexto_f13.tenant_id,
                NsrSequencia.rep_p_id == rep_p.id,
            )
        )
    ).scalar_one()
    assert sequencia.proximo_nsr == 2
    assert sequencia.ultimo_nsr_emitido == 1

    # 7. O verificador OFICIAL de continuidade (o mesmo que
    # `GET /v1/marcacoes/nsr/verificar` expoe) continua vendo a sequencia do
    # REP-P como INTEGRA -- inteiramente alheio a marcacao importada.
    verificacao = await verificar_sequencia_nsr(
        sessao_f13, tenant_id=contexto_f13.tenant_id, rep_p_id=rep_p.id
    )
    assert verificacao.integro is True
    assert verificacao.lacunas is None
    assert verificacao.total_esperado == 1
    assert verificacao.total_encontrado == 1
    assert verificacao.nsr_inicial == 1
    assert verificacao.nsr_final == 1


async def test_importacao_nunca_escreve_em_nsr_sequencias_nem_nsr_emissoes_diretamente(
    sessao_f13: AsyncSession,
    contexto_f13: ContextoF13,
    criar_rep_p,
) -> None:
    """Prova complementar por análise estática indireta: roda uma importação
    de várias linhas (sem nenhuma marcação real concorrente) e confirma que
    `nsr_emissoes` continua VAZIA e `nsr_sequencias` continua no estado
    inicial (`proximo_nsr=1`), mesmo a importação tendo processado NSRs
    "altos" que, se fossem alocados de verdade, teriam avançado o contador."""
    rep_p = await criar_rep_p(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        empresa_cnpj=contexto_f13.empresa_cnpj,
    )
    await sessao_f13.execute(
        sa.text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (gen_random_uuid(), :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"tenant_id": str(contexto_f13.tenant_id), "rep_p_id": str(rep_p.id)},
    )

    importacao = Importacao(
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        tipo="afd_terceiro",
        origem="afd",
        nome_arquivo="afd_terceiro_alto_volume.txt",
        status="recebido",
    )
    sessao_f13.add(importacao)
    await sessao_f13.flush()

    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {
                "nsr": nsr,
                "datahora_marc": f"2026-01-{(nsr % 27) + 1:02d}T08:00:00-0300",
                "cpf": "12345678909",
            }
            for nsr in range(999_990, 1_000_000)
        ]
    )

    resultado = await processar_arquivo(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        empresa_id=contexto_f13.empresa_id,
        rep_p_id=rep_p.id,
        importacao=importacao,
        conteudo=conteudo,
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    assert resultado.linhas_sucesso == 10

    total_emissoes = (
        await sessao_f13.execute(
            sa.select(sa.func.count())
            .select_from(NsrEmissao)
            .where(NsrEmissao.rep_p_id == rep_p.id)
        )
    ).scalar_one()
    assert total_emissoes == 0, "importacao NUNCA escreve em nsr_emissoes"

    sequencia = (
        await sessao_f13.execute(
            sa.select(NsrSequencia).where(
                NsrSequencia.tenant_id == contexto_f13.tenant_id,
                NsrSequencia.rep_p_id == rep_p.id,
            )
        )
    ).scalar_one()
    # importacao NUNCA avanca nsr_sequencias, mesmo com NSR de arquivo altos.
    assert sequencia.proximo_nsr == 1
    assert sequencia.ultimo_nsr_emitido == 0
