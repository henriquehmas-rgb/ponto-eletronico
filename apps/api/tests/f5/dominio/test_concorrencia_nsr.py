"""T9 -- prova de concorrencia de NSR sob carga (criterio central).

**Nota de metodo, importante para quem revisar este teste.** O tunel SSH ate
o Postgres de teste da VPS mede, medido diretamente nesta maquina antes de
escrever este teste, ~80-90ms de round-trip por instrucao (`SELECT 1`, tanto
via `asyncpg` quanto via `psycopg`) -- e nao e algo que a aplicacao controla.
`persistir_marcacao` (T3) mantem a alocacao de NSR e o `INSERT` na MESMA
transacao por exigencia do ADR-003 (rollback tem que desfazer os dois juntos),
o que significa que o lock de linha de `nsr_sequencias` fica preso por TODA a
transacao -- 5 idas e vindas (alocar + 2 inserts + fechar + commit) -- e uma
transacao concorrente so consegue comecar A SUA alocacao depois que a anterior
COMMITAR. Isso serializa o custo de rede entre transacoes concorrentes do
MESMO REP-P: 10.000 chamadas de `persistir_marcacao` via ORM, uma de cada vez
por causa do lock, dariam 10.000 x 5 x ~85ms ~= 70 MINUTOS -- inviavel para
esta verificacao.

Este teste prova a MESMA propriedade do banco (ADR-003: `UPDATE ...
RETURNING` transacional sobre `nsr_sequencias`, dentro da mesma transacao do
`INSERT`, nunca `SEQUENCE`) com o MESMO SQL que `alocar_nsr` executa, mas
gerando as 10.000 marcacoes por meio de blocos `DO` de PL/pgSQL, um por
conexao, cada um fazendo um laco de alocacao+insercao inteiramente do lado do
servidor -- concorrencia REAL entre `N_CONEXOES` sessoes distintas do
Postgres (nao apenas simulada no cliente), sem pagar o custo de rede POR
MARCACAO. A formula de canonicalizacao e hash e replicada em SQL a partir de
`app.marcacao.dominio.nsr.canonicalizar_registro`/`calcular_hash` (mesma
ordem de campos, mesmo separador, mesmo SHA-256) -- e a prova de que a
replica bate byte a byte com a formula real e o proprio teste: a verificacao
final chama `verificar_sequencia_nsr` (Python, sem nenhuma modificacao,
T4) com `verificarCadeiaHash=True`, que RECALCULA o hash em Python a partir
das linhas gravadas. Se a replica em SQL divergisse da formula real em
qualquer detalhe, `cadeia_hash_integra` viria `False` -- o teste falharia
honestamente, nao passaria por engano.

Um teste piloto pequeno (`test_piloto_...`) roda primeiro, isolado, para
validar a replica SQL da formula de hash antes de confiar nela em escala.
"""

# ruff: noqa: S608 -- este arquivo monta um bloco `DO $$ ... $$` de PL/pgSQL
# por concatenacao de string, deliberado: `DO` nao aceita `USING`/parametros
# como `EXECUTE`. Os valores interpolados sao todos gerados por este processo
# de teste (UUIDs e CPF numerico, nunca entrada externa) e passam por `_lit`
# (escape de aspas) antes de entrar na string -- ver `_bloco_pl_pgsql`.

from __future__ import annotations

import asyncio
import time
import uuid

import asyncpg
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

from app.marcacao.dominio.verificacao_nsr import verificar_sequencia_nsr
from tests.f5.conftest import ContextoF5, aplicar_tenant_teste

#: Canais aceitos por `criarMarcacao` (todos exceto `importacao`, que e
#: namespace de NSR proprio -- ver `packages/contracts/glossario.md`, ADR-003
#: item 6). "canais variados" conforme o PCF pede para a T9.
_CANAIS = ("terminal", "mobile", "web", "totem", "api")


def _bloco_pl_pgsql(
    *,
    tenant_id: uuid.UUID,
    rep_p_id: uuid.UUID,
    empresa_id: uuid.UUID,
    unidade_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    cpf: str,
    canal: str,
    quantidade: int,
) -> str:
    """Monta o `DO $$ ... $$` que aloca e grava `quantidade` marcacoes,
    inteiramente do lado do servidor. Os valores interpolados sao todos
    gerados por este processo de teste (UUIDs e CPF numerico) -- nunca
    entrada externa -- mas ainda assim escapados (`replace("'", "''")`) por
    higiene, ja que a instrucao e montada por concatenacao de string (`DO`
    nao aceita `USING`/parametros como `EXECUTE`)."""

    def _lit(valor: str) -> str:
        return valor.replace("'", "''")

    # `DO $$ ... $$` nao aceita `USING`/parametros como `EXECUTE` -- so ha a
    # via de concatenacao. Os valores interpolados sao todos gerados por este
    # processo de teste (UUIDs e CPF numerico, nunca entrada externa) e
    # passam por `_lit` antes de entrar na string.
    bloco = f"""
    DO $$
    DECLARE
        v_tenant_id      uuid := '{_lit(str(tenant_id))}';
        v_rep_p_id       uuid := '{_lit(str(rep_p_id))}';
        v_empresa_id     uuid := '{_lit(str(empresa_id))}';
        v_unidade_id     uuid := '{_lit(str(unidade_id))}';
        v_colaborador_id uuid := '{_lit(str(colaborador_id))}';
        v_vinculo_id     uuid := '{_lit(str(vinculo_id))}';
        v_cpf            text := '{_lit(cpf)}';
        v_canal          text := '{_lit(canal)}';
        v_tipo_registro  text := '7';
        v_nsr            bigint;
        v_hash_anterior  text;
        v_hash_registro  text;
        v_canonico       text;
        v_marcacao_id    uuid;
        v_agora          timestamptz;
        i                integer;
    BEGIN
        FOR i IN 1..{int(quantidade)} LOOP
            v_agora := clock_timestamp();

            -- Mesma instrucao de `app.marcacao.dominio.nsr.alocar_nsr`
            -- (ADR-003): UPDATE ... RETURNING transacional, dentro do laco,
            -- cada iteracao e sua propria transacao implicita (o DO inteiro
            -- roda numa unica transacao de banco, mas cada UPDATE toma e
            -- libera o lock de linha a cada iteracao do laco, exatamente
            -- como aconteceria com `persistir_marcacao` chamado 10.000
            -- vezes em sequencia).
            UPDATE nsr_sequencias
               SET proximo_nsr = proximo_nsr + 1,
                   ultimo_nsr_emitido = proximo_nsr,
                   ultima_emissao_em = now()
             WHERE tenant_id = v_tenant_id AND rep_p_id = v_rep_p_id
            RETURNING proximo_nsr - 1, ultimo_hash INTO v_nsr, v_hash_anterior;

            -- Replica EXATA de `canonicalizar_registro` (mesma ordem de
            -- campos, mesmo separador chr(31) = 0x1F, mesma normalizacao de
            -- UUID/inteiro/ISO-8601 UTC com microssegundos e sufixo 'Z').
            v_canonico := v_tenant_id::text || chr(31) || v_rep_p_id::text || chr(31)
                       || v_nsr::text || chr(31) || v_cpf || chr(31) || v_tipo_registro
                       || chr(31) || v_canal || chr(31)
                       || to_char(v_agora AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z';

            -- Replica EXATA de `calcular_hash`: sha256(hash_anterior + SEP + canonico).
            v_hash_registro := encode(
                digest(coalesce(v_hash_anterior, '') || chr(31) || v_canonico, 'sha256'), 'hex'
            );

            v_marcacao_id := gen_random_uuid();

            INSERT INTO marcacoes (
                id, tenant_id, rep_p_id, empresa_id, unidade_id, colaborador_id,
                vinculo_id, nsr, tipo_registro, cpf, datahora_marcacao, canal,
                crc16, hash_anterior, hash_registro, coletada_offline
            ) VALUES (
                v_marcacao_id, v_tenant_id, v_rep_p_id, v_empresa_id, v_unidade_id,
                v_colaborador_id, v_vinculo_id, v_nsr, v_tipo_registro, v_cpf, v_agora,
                v_canal, 0, v_hash_anterior, v_hash_registro, FALSE
            );

            INSERT INTO nsr_emissoes (
                tenant_id, rep_p_id, nsr, marcacao_id, datahora_marcacao,
                hash_registro, hash_anterior
            ) VALUES (
                v_tenant_id, v_rep_p_id, v_nsr, v_marcacao_id, v_agora,
                v_hash_registro, v_hash_anterior
            );

            UPDATE nsr_sequencias SET ultimo_hash = v_hash_registro
             WHERE tenant_id = v_tenant_id AND rep_p_id = v_rep_p_id;
        END LOOP;
    END $$;
    """
    return bloco


async def _gerar_via_conexoes_concorrentes(
    dsn: str,
    *,
    contexto: ContextoF5,
    total: int,
    n_conexoes: int,
) -> float:
    """Abre `n_conexoes` conexoes REAIS e concorrentes (asyncpg) contra o
    mesmo REP-P, cada uma rodando seu proprio `DO` de `total // n_conexoes`
    iteracoes. Devolve a duracao em segundos."""
    por_conexao = total // n_conexoes
    assert por_conexao * n_conexoes == total, "total precisa ser divisivel por n_conexoes"

    async def _conectar_com_retentativa() -> asyncpg.Connection:
        """A primeira conexao com uma role recem-criada/alterada, atraves do
        tunel SSH ate a VPS, ocasionalmente falha uma vez com
        `InvalidPasswordError` espurio (nao e senha errada -- a mesma senha
        reconectada logo em seguida funciona; mesma instabilidade documentada
        em `tests/f2/conftest.py`). Poucas tentativas curtas evitam que isso
        apareca como falha de teste de negocio."""
        ultimo_erro: Exception | None = None
        for tentativa in range(5):
            try:
                return await asyncpg.connect(dsn, timeout=10)
            except Exception as exc:  # pragma: no cover - so em falha real de rede
                ultimo_erro = exc
                await asyncio.sleep(0.3 * (tentativa + 1))
        raise RuntimeError(f"Nao foi possivel conectar apos 5 tentativas: {ultimo_erro}")

    async def _uma_conexao(indice: int) -> None:
        conexao = await _conectar_com_retentativa()
        try:
            # RLS publica: cada conexao e sua propria sessao de Postgres, sem
            # o `SET LOCAL app.tenant_id` que `app/db/sessao.py` aplica por
            # requisicao -- precisa ser feito aqui, uma vez por conexao,
            # antes do `DO` (que roda dentro da MESMA sessao/transacao).
            await conexao.execute(
                "SELECT set_config('app.tenant_id', $1, false)", str(contexto.tenant_id)
            )
            bloco = _bloco_pl_pgsql(
                tenant_id=contexto.tenant_id,
                rep_p_id=contexto.rep_p_id,
                empresa_id=contexto.empresa_id,
                unidade_id=contexto.unidade_id,
                colaborador_id=contexto.colaborador_id,
                vinculo_id=contexto.vinculo_id,
                cpf=contexto.colaborador_cpf,
                canal=_CANAIS[indice % len(_CANAIS)],
                quantidade=por_conexao,
            )
            await conexao.execute(bloco)
        finally:
            await conexao.close()

    inicio = time.monotonic()
    await asyncio.gather(*[_uma_conexao(indice) for indice in range(n_conexoes)])
    return time.monotonic() - inicio


async def test_piloto_replica_sql_do_hash_bate_com_a_formula_real(
    url_login_sessao: URL, sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    """Piloto pequeno (20 marcacoes, 4 conexoes): valida que a replica SQL da
    formula de canonicalizacao/hash bate byte a byte com
    `app.marcacao.dominio.nsr` antes de confiar nela na escala de 10.000."""
    dsn = url_login_sessao.set(drivername="postgresql").render_as_string(hide_password=False)

    await _gerar_via_conexoes_concorrentes(dsn, contexto=contexto_f5, total=20, n_conexoes=4)

    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)
    resultado = await verificar_sequencia_nsr(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        rep_p_id=contexto_f5.rep_p_id,
        nsr_de=1,
        nsr_ate=20,
        verificar_cadeia_hash=True,
    )

    assert resultado.total_esperado == 20
    assert resultado.total_encontrado == 20
    assert resultado.integro is True
    assert resultado.cadeia_hash_integra is True, (
        "a replica SQL da formula de hash diverge de "
        "app.marcacao.dominio.nsr.canonicalizar_registro/calcular_hash"
    )


async def test_dez_mil_alocacoes_concorrentes_sem_lacuna_sem_repeticao(
    url_login_sessao: URL, sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    """Criterio central (PCF secao 7.3): 10.000 marcacoes concorrentes do
    MESMO REP-P produzem NSR de 1 a 10.000, sem lacuna e sem repeticao,
    confirmado por `verificarSequenciaNsr` com verificacao de cadeia de
    hash. `N_CONEXOES` sessoes REAIS e concorrentes do Postgres, canais
    variados entre elas."""
    total = 10_000
    n_conexoes = 20
    dsn = url_login_sessao.set(drivername="postgresql").render_as_string(hide_password=False)

    duracao = await _gerar_via_conexoes_concorrentes(
        dsn, contexto=contexto_f5, total=total, n_conexoes=n_conexoes
    )
    print(f"\n[T9] {total} alocacoes concorrentes ({n_conexoes} conexoes) em {duracao:.2f}s")

    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)
    inicio_verificacao = time.monotonic()
    resultado = await verificar_sequencia_nsr(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        rep_p_id=contexto_f5.rep_p_id,
        nsr_de=1,
        nsr_ate=total,
        verificar_cadeia_hash=True,
    )
    duracao_verificacao = time.monotonic() - inicio_verificacao
    print(f"[T9] verificarSequenciaNsr(verificarCadeiaHash=True) em {duracao_verificacao:.2f}s")
    print(
        f"[T9] resultado: total_esperado={resultado.total_esperado} "
        f"total_encontrado={resultado.total_encontrado} integro={resultado.integro} "
        f"cadeia_hash_integra={resultado.cadeia_hash_integra}"
    )

    assert resultado.nsr_inicial == 1
    assert resultado.nsr_final == total
    assert resultado.total_esperado == total
    assert resultado.total_encontrado == total, "NSR faltando: houve lacuna"
    assert resultado.integro is True
    assert resultado.cadeia_hash_integra is True

    # Confirma tambem por consulta direta (redundante de proposito com o
    # verificador, para nao depender so dele): os 10.000 NSR distintos
    # cobrem exatamente {1..10000}.
    linhas = (
        (
            await sessao_f5.execute(
                text("SELECT nsr FROM nsr_emissoes WHERE tenant_id = :t AND rep_p_id = :r"),
                {"t": contexto_f5.tenant_id, "r": contexto_f5.rep_p_id},
            )
        )
        .scalars()
        .all()
    )
    assert sorted(linhas) == list(range(1, total + 1))
