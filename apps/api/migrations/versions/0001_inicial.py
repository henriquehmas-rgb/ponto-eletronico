"""Schema inicial do Ponto Eletronico (REP-P multiempresa).

Revisao: 0001_inicial
Revisao anterior: nenhuma
Alvo: PostgreSQL 16

Esta migration materializa `packages/contracts/schema.sql` inteiro:

  1.  extensoes (pgcrypto, uuid-ossp, btree_gist, pg_trgm)
  2.  funcoes auxiliares e barreiras de imutabilidade
  3.  dominios de formato (CPF, CNPJ, PIS, CEP, UF, IBGE, CBO, e-mail,
      SHA-256, fuso e competencia)
  4.  as 92 tabelas do contrato, com CHECK, UNIQUE, EXCLUDE, comentarios e os
      182 indices (parciais, por expressao e GIN inclusos)
  5.  as 12 chaves estrangeiras adiadas, que fecham os ciclos de referencia
  6.  `fn_resolve_tenant()`, porta de entrada do login antes de existir
      `app.tenant_id`
  7.  particionamento mensal de `marcacoes` (2026-01 a 2027-12) mais a particao
      padrao, cada uma ja com RLS, policy e barreira de TRUNCATE
  8.  gatilhos de imutabilidade das tabelas append-only
  9.  gatilhos de `atualizado_em`
  10. Row Level Security em toda tabela com `tenant_id`
  11. roles `ponto_app`, `ponto_leitura` e `ponto_suporte` com os privilegios
      corretos (defesa em profundidade: a role da aplicacao nao recebe UPDATE
      nem DELETE nas tabelas append-only)
  12. bloco de verificacao que FALHA a migration se alguma invariante do
      contrato estiver quebrada

O bloco de tabelas e indices e a traducao direta dos models declarativos de
`packages/contracts/models`; foi gerado a partir de `Base.metadata` e conferido
contra `schema.sql` (92 tabelas, 182 indices, 103 constraints nomeadas).

`downgrade()` reverte tudo: solta as chaves estrangeiras adiadas, derruba as
tabelas na ordem topologica inversa (o que leva junto particoes, indices,
gatilhos e policies), remove as funcoes e remove os dominios.

Duas coisas NAO sao removidas no downgrade, deliberadamente:

* **Extensoes** - sao objetos do banco inteiro, criados com
  `IF NOT EXISTS`. Nao ha como saber se foram criadas por esta migration ou se
  ja existiam para outro schema; derruba-las poderia quebrar terceiros.
* **Roles** - sao objetos do cluster, compartilhados entre bancos. Os
  privilegios concedidos morrem junto com as tabelas; a role em si permanece.

Ambas sao idempotentes na reaplicacao, entao
`upgrade -> downgrade -> upgrade` continua funcionando (e o CI executa
exatamente essa sequencia).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_inicial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ===========================================================================
# 1. EXTENSOES
# ===========================================================================
SQL_EXTENSOES: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    (
        "COMMENT ON EXTENSION btree_gist IS "
        "'Necessaria para as constraints EXCLUDE de vigencia "
        "(tenant_id WITH = combinado com daterange WITH &&).'"
    ),
)


# ===========================================================================
# 2. FUNCOES AUXILIARES
# ===========================================================================
SQL_FUNCOES: tuple[str, ...] = (
    r"""
CREATE OR REPLACE FUNCTION app_tenant_atual() RETURNS UUID
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$
""",
    (
        "COMMENT ON FUNCTION app_tenant_atual() IS "
        "'Retorna o tenant corrente lido de current_setting(''app.tenant_id''). "
        "Retorna NULL quando nao definido, o que faz as policies de RLS negarem tudo.'"
    ),
    r"""
CREATE OR REPLACE FUNCTION app_usuario_atual() RETURNS UUID
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.usuario_id', true), '')::uuid;
$$
""",
    (
        "COMMENT ON FUNCTION app_usuario_atual() IS "
        "'Retorna o usuario corrente lido de current_setting(''app.usuario_id''). "
        "Usado por gatilhos e por rotinas de auditoria.'"
    ),
    r"""
CREATE OR REPLACE FUNCTION fn_atualiza_timestamp() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em := now();
    RETURN NEW;
END;
$$
""",
    (
        "COMMENT ON FUNCTION fn_atualiza_timestamp() IS "
        "'Gatilho BEFORE UPDATE aplicado automaticamente a toda tabela que possui "
        "a coluna atualizado_em.'"
    ),
    r"""
CREATE OR REPLACE FUNCTION fn_registro_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
      'registro_imutavel: operacao % vedada na tabela %. Registros desta tabela sao append-only por exigencia legal e de auditoria; use a camada de tratamento.',
      TG_OP, TG_TABLE_NAME
      USING ERRCODE = '42501',
            HINT = 'Portaria MTP 671/2021 e ADR-002 (imutabilidade de marcacao).';
END;
$$
""",
    (
        "COMMENT ON FUNCTION fn_registro_imutavel() IS "
        "'Gatilho que aborta UPDATE, DELETE e TRUNCATE em tabelas append-only. "
        "Exigencia legal, nao configuravel.'"
    ),
    r"""
CREATE OR REPLACE FUNCTION fn_bh_lancamento_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Todas as colunas, exceto consumido_minutos, precisam estar intactas.
    IF ROW(NEW.id, NEW.tenant_id, NEW.bh_conta_id, NEW.sequencia, NEW.data_competencia,
           NEW.tipo, NEW.origem, NEW.apuracao_dia_id, NEW.tratamento_id, NEW.quitacao_id,
           NEW.estorna_lancamento_id, NEW.minutos, NEW.fator, NEW.minutos_equivalentes,
           NEW.saldo_apos_minutos, NEW.vence_em, NEW.descricao, NEW.hash_anterior,
           NEW.hash_registro, NEW.criado_em, NEW.criado_por)
       IS NOT DISTINCT FROM
       ROW(OLD.id, OLD.tenant_id, OLD.bh_conta_id, OLD.sequencia, OLD.data_competencia,
           OLD.tipo, OLD.origem, OLD.apuracao_dia_id, OLD.tratamento_id, OLD.quitacao_id,
           OLD.estorna_lancamento_id, OLD.minutos, OLD.fator, OLD.minutos_equivalentes,
           OLD.saldo_apos_minutos, OLD.vence_em, OLD.descricao, OLD.hash_anterior,
           OLD.hash_registro, OLD.criado_em, OLD.criado_por)
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
      'registro_imutavel: o extrato de banco de horas so admite atualizacao de consumido_minutos. Para corrigir um lancamento, emita um estorno.'
      USING ERRCODE = '42501';
END;
$$
""",
    (
        "COMMENT ON FUNCTION fn_bh_lancamento_imutavel() IS "
        "'Permite exclusivamente a atualizacao de consumido_minutos em bh_lancamentos. "
        "Qualquer outra alteracao e abortada; correcao se faz por estorno.'"
    ),
)

#: Funcoes na ordem inversa de criacao, para o downgrade.
FUNCOES_PARA_REMOVER: tuple[str, ...] = (
    "fn_bh_lancamento_imutavel()",
    "fn_cria_particao_marcacoes(DATE)",
    "fn_resolve_terminal(TEXT)",
    "fn_resolve_tenant(TEXT)",
    "fn_registro_imutavel()",
    "fn_atualiza_timestamp()",
    "app_usuario_atual()",
    "app_tenant_atual()",
)


# ===========================================================================
# 3. DOMINIOS DE FORMATO
#
# A validacao de digito verificador (CPF, CNPJ, PIS) e responsabilidade da
# aplicacao (Fase 2). O dominio valida o formato.
# ===========================================================================
DOMINIOS: tuple[tuple[str, str, str], ...] = (
    (
        "dom_cpf",
        r"VALUE ~ '^[0-9]{11}$'",
        "CPF em 11 digitos, sem pontuacao. Digito verificador validado na aplicacao.",
    ),
    ("dom_cnpj", r"VALUE ~ '^[0-9]{14}$'", "CNPJ em 14 digitos, sem pontuacao."),
    ("dom_pis", r"VALUE ~ '^[0-9]{11}$'", "PIS, PASEP ou NIT em 11 digitos, sem pontuacao."),
    ("dom_cep", r"VALUE ~ '^[0-9]{8}$'", "CEP em 8 digitos, sem pontuacao."),
    ("dom_uf", r"VALUE ~ '^[A-Z]{2}$'", "Sigla da unidade federativa em 2 letras maiusculas."),
    (
        "dom_ibge",
        r"VALUE ~ '^[0-9]{7}$'",
        "Codigo IBGE do municipio em 7 digitos. Base dos feriados municipais.",
    ),
    ("dom_cbo", r"VALUE ~ '^[0-9]{6}$'", "Classificacao Brasileira de Ocupacoes, 6 digitos."),
    (
        "dom_email",
        r"VALUE ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'",
        "Endereco de e-mail em formato minimo verificavel.",
    ),
    (
        "dom_sha256",
        r"VALUE ~ '^[0-9a-fA-F]{64}$'",
        "Hash SHA-256 em hexadecimal (64 caracteres).",
    ),
    (
        "dom_fuso",
        r"VALUE ~ '^[A-Za-z]+/[A-Za-z_+-]+$'",
        "Fuso horario IANA, por exemplo America/Sao_Paulo.",
    ),
    (
        "dom_competencia",
        r"VALUE ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
        "Competencia de folha no formato AAAA-MM.",
    ),
)


# ===========================================================================
# 6. RESOLUCAO DE TENANT POR SUBDOMINIO
#
# SECURITY DEFINER porque `tenants` esta sob RLS e, no momento do login, ainda
# nao existe `app.tenant_id`. Expoe apenas quatro colunas: nao ha como enumerar
# a base de clientes por aqui.
# ===========================================================================
SQL_RESOLVE_TENANT: tuple[str, ...] = (
    # RFC-009: a versao original (RFC-004) decidia slug-vs-UUID com um guard
    # de AND/OR, assumindo curto-circuito estrito -- o PostgreSQL nao garante
    # ordem de avaliacao de AND/OR (manual, 4.2.14), e o planejador podia
    # tentar `p_slug::uuid` mesmo com o regex falso, quebrando a resolucao por
    # slug de forma intermitente conforme o plano escolhido. CASE/WHEN e a
    # unica construcao com ordem de avaliacao garantida pelo padrao SQL.
    r"""
CREATE OR REPLACE FUNCTION fn_resolve_tenant(p_slug TEXT)
RETURNS TABLE (id UUID, slug TEXT, nome_exibicao TEXT, status TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.slug, t.nome_exibicao, t.status
    FROM tenants t
   WHERE t.excluido_em IS NULL
     AND CASE
           WHEN p_slug ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
             THEN t.id = p_slug::uuid
           ELSE t.slug = p_slug
         END;
$$
""",
    (
        "COMMENT ON FUNCTION fn_resolve_tenant(TEXT) IS "
        "'Unica porta de entrada para descobrir o tenant a partir do subdominio ou "
        "do cabecalho X-Tenant (slug ou UUID, RFC-004) antes de app.tenant_id "
        "existir.'"
    ),
)

# RFC-010: mesma classe de problema que SQL_RESOLVE_TENANT, agora para
# `terminais` -- resolver tenant_id/id de um terminal pelo numero de serie
# antes de existir app.tenant_id (chegada de evento Push/Monitor do iDFace,
# F6). `numero_serie` e unico POR TENANT (uq_terminais_serie), nao
# globalmente: LIMIT 2 e a aplicacao trata 2 linhas como ambiguidade (erro),
# nunca escolhe a primeira em silencio.
SQL_RESOLVE_TERMINAL: tuple[str, ...] = (
    r"""
CREATE OR REPLACE FUNCTION fn_resolve_terminal(p_numero_serie TEXT)
RETURNS TABLE (id UUID, tenant_id UUID, status TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.tenant_id, t.status
    FROM terminais t
   WHERE t.numero_serie = p_numero_serie
     AND t.excluido_em IS NULL
   LIMIT 2;
$$
""",
    (
        "COMMENT ON FUNCTION fn_resolve_terminal(TEXT) IS "
        "'Unica porta de entrada para descobrir tenant_id e id de um terminal "
        "a partir do numero de serie (RFC-010), antes de app.tenant_id "
        "existir. Devolve ate 2 linhas de proposito: a aplicacao deve tratar "
        "mais de uma linha como ambiguidade (erro), nunca escolher a "
        "primeira.'"
    ),
)


# ===========================================================================
# 7. PARTICIONAMENTO DE `marcacoes`
#
# Os limites usam o offset fixo do Brasil (-03), que nao tem horario de verao
# desde 2019, tornando as fronteiras deterministas e alinhadas ao mes civil.
# ===========================================================================
SQL_PARTICIONAMENTO: tuple[str, ...] = (
    r"""
CREATE OR REPLACE FUNCTION fn_cria_particao_marcacoes(p_mes DATE)
RETURNS TEXT
LANGUAGE plpgsql AS $$
DECLARE
    v_inicio DATE := date_trunc('month', p_mes)::date;
    v_fim    DATE := (date_trunc('month', p_mes) + INTERVAL '1 month')::date;
    v_nome   TEXT := format('marcacoes_%s', to_char(v_inicio, 'YYYY_MM'));
BEGIN
    IF to_regclass('public.' || quote_ident(v_nome)) IS NOT NULL THEN
        RETURN v_nome;
    END IF;

    EXECUTE format(
        'CREATE TABLE %I PARTITION OF marcacoes FOR VALUES FROM (%L) TO (%L)',
        v_nome,
        to_char(v_inicio, 'YYYY-MM-DD') || ' 00:00:00-03',
        to_char(v_fim,    'YYYY-MM-DD') || ' 00:00:00-03'
    );
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_nome);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', v_nome);
    EXECUTE format(
        'CREATE POLICY pol_isolamento_tenant ON %I '
        'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
        'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)',
        v_nome
    );
    EXECUTE format(
        'CREATE TRIGGER trg_%s_bloqueia_truncate BEFORE TRUNCATE ON %I '
        'FOR EACH STATEMENT EXECUTE FUNCTION fn_registro_imutavel()',
        v_nome, v_nome
    );

    -- Privilegios da nova particao: inserir e ler sim, alterar e apagar nunca.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_app') THEN
        EXECUTE format('GRANT SELECT, INSERT ON %I TO ponto_app', v_nome);
        EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM ponto_app', v_nome);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_leitura') THEN
        EXECUTE format('GRANT SELECT ON %I TO ponto_leitura', v_nome);
    END IF;

    RETURN v_nome;
END;
$$
""",
    (
        "COMMENT ON FUNCTION fn_cria_particao_marcacoes(DATE) IS "
        "'Cria a particao mensal de marcacoes ja com RLS, policy de tenant e barreira "
        "de TRUNCATE. Idempotente. O gatilho de TRUNCATE fica na particao porque o "
        "PostgreSQL nao aceita gatilho de TRUNCATE em tabela particionada.'"
    ),
    r"""
DO $$
DECLARE v_mes DATE := DATE '2026-01-01';
BEGIN
    WHILE v_mes < DATE '2028-01-01' LOOP
        PERFORM fn_cria_particao_marcacoes(v_mes);
        v_mes := (v_mes + INTERVAL '1 month')::date;
    END LOOP;
END $$
""",
    "CREATE TABLE marcacoes_default PARTITION OF marcacoes DEFAULT",
    (
        "COMMENT ON TABLE marcacoes_default IS "
        "'Particao padrao. Existe para que a ausencia de particao nunca recuse uma "
        "marcacao legitima. Monitorada: linha aqui e alarme operacional, nao normalidade.'"
    ),
    "ALTER TABLE marcacoes_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE marcacoes_default FORCE ROW LEVEL SECURITY",
    r"""
CREATE POLICY pol_isolamento_tenant ON marcacoes_default
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
""",
    r"""
CREATE TRIGGER trg_marcacoes_default_bloqueia_truncate
    BEFORE TRUNCATE ON marcacoes_default
    FOR EACH STATEMENT EXECUTE FUNCTION fn_registro_imutavel()
""",
)


# ===========================================================================
# 8. GATILHOS DE IMUTABILIDADE
#
# Exigencia legal, nao configuracao: a Portaria MTP 671/2021 veda ao REP
# alterar ou apagar marcacoes. `bh_lancamentos` tem tratamento proprio - o
# UPDATE passa por `fn_bh_lancamento_imutavel()`, que aceita apenas
# `consumido_minutos`.
# ===========================================================================
GATILHOS_IMUTABILIDADE: tuple[tuple[str, str, str, str, str], ...] = (
    # (nome, momento_evento, tabela, granularidade, funcao)
    (
        "trg_marcacoes_bloqueia_update",
        "BEFORE UPDATE",
        "marcacoes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_marcacoes_bloqueia_delete",
        "BEFORE DELETE",
        "marcacoes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_nsr_emissoes_bloqueia_update",
        "BEFORE UPDATE",
        "nsr_emissoes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_nsr_emissoes_bloqueia_delete",
        "BEFORE DELETE",
        "nsr_emissoes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_marcacao_idempotencia_bloqueia_update",
        "BEFORE UPDATE",
        "marcacao_idempotencia",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_marcacao_idempotencia_bloqueia_delete",
        "BEFORE DELETE",
        "marcacao_idempotencia",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_comprovantes_bloqueia_update",
        "BEFORE UPDATE",
        "comprovantes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_comprovantes_bloqueia_delete",
        "BEFORE DELETE",
        "comprovantes",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_bh_lancamentos_bloqueia_delete",
        "BEFORE DELETE",
        "bh_lancamentos",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_bh_lancamentos_imutavel",
        "BEFORE UPDATE",
        "bh_lancamentos",
        "FOR EACH ROW",
        "fn_bh_lancamento_imutavel",
    ),
    (
        "trg_bh_lancamentos_bloqueia_truncate",
        "BEFORE TRUNCATE",
        "bh_lancamentos",
        "FOR EACH STATEMENT",
        "fn_registro_imutavel",
    ),
    (
        "trg_assinaturas_espelho_bloqueia_update",
        "BEFORE UPDATE",
        "assinaturas_espelho",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_assinaturas_espelho_bloqueia_delete",
        "BEFORE DELETE",
        "assinaturas_espelho",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_arquivo_assinaturas_bloqueia_delete",
        "BEFORE DELETE",
        "arquivo_assinaturas",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_auditoria_bloqueia_update",
        "BEFORE UPDATE",
        "auditoria",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_auditoria_bloqueia_delete",
        "BEFORE DELETE",
        "auditoria",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_auditoria_bloqueia_truncate",
        "BEFORE TRUNCATE",
        "auditoria",
        "FOR EACH STATEMENT",
        "fn_registro_imutavel",
    ),
    (
        "trg_acessos_sensiveis_bloqueia_update",
        "BEFORE UPDATE",
        "acessos_dados_sensiveis",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
    (
        "trg_acessos_sensiveis_bloqueia_delete",
        "BEFORE DELETE",
        "acessos_dados_sensiveis",
        "FOR EACH ROW",
        "fn_registro_imutavel",
    ),
)


# ===========================================================================
# 9. GATILHOS DE `atualizado_em`
#
# Aplicados por laco a toda tabela que possui a coluna. O laco garante
# cobertura de 100 por cento; fazer a mao seria esquecer alguma.
# ===========================================================================
SQL_GATILHOS_TIMESTAMP = r"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r','p')
           AND EXISTS (
                 SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = c.oid
                    AND a.attname = 'atualizado_em'
                    AND NOT a.attisdropped
               )
         ORDER BY c.relname
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_atualiza_timestamp BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION fn_atualiza_timestamp()',
            r.relname, r.relname
        );
    END LOOP;
END $$
"""


# ===========================================================================
# 10. ROW LEVEL SECURITY
#
# Excecoes conscientes (documentadas no glossario):
#   tenants    - a coluna de isolamento e `id`; policy declarada a parte.
#   permissoes - catalogo global do produto, identico em todos os tenants.
# ===========================================================================
SQL_RLS: tuple[str, ...] = (
    r"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r','p')
           AND EXISTS (
                 SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = c.oid
                    AND a.attname = 'tenant_id'
                    AND NOT a.attisdropped
               )
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', r.relname);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', r.relname);
        EXECUTE format('DROP POLICY IF EXISTS pol_isolamento_tenant ON %I', r.relname);
        EXECUTE format(
            'CREATE POLICY pol_isolamento_tenant ON %I '
            'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
            'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)',
            r.relname
        );
    END LOOP;
END $$
""",
    "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
    r"""
CREATE POLICY pol_isolamento_tenant ON tenants
    USING      (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
""",
)


# ===========================================================================
# 11. ROLES E PRIVILEGIOS
#
# Defesa em profundidade: alem do gatilho de imutabilidade, a role da aplicacao
# simplesmente NAO recebe UPDATE nem DELETE nas tabelas append-only. Os blocos
# toleram falta de privilegio para que a migration rode com usuario sem
# CREATEROLE (o log avisa e a operacao segue).
# ===========================================================================
SQL_ROLES: tuple[str, ...] = (
    r"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_app') THEN
        EXECUTE 'CREATE ROLE ponto_app NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_leitura') THEN
        EXECUTE 'CREATE ROLE ponto_leitura NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_suporte') THEN
        EXECUTE 'CREATE ROLE ponto_suporte NOLOGIN BYPASSRLS';
    END IF;
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE NOTICE 'Sem privilegio para criar roles. Crie ponto_app, ponto_leitura e ponto_suporte manualmente (ver infra/).';
END $$
""",
    r"""
DO $$
DECLARE
    -- Append-only integral: nem UPDATE, nem DELETE, nem TRUNCATE.
    v_append_only TEXT[] := ARRAY[
        'marcacoes','nsr_emissoes','marcacao_idempotencia','comprovantes',
        'bh_lancamentos','auditoria','acessos_dados_sensiveis',
        'assinaturas_espelho','terminal_saude'
    ];
    -- Somente-acrescimo: aceitam UPDATE de campos operacionais, nunca DELETE.
    v_sem_delete  TEXT[] := ARRAY['arquivo_assinaturas'];
    r        RECORD;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_app') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO ponto_app';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ponto_app';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ponto_app';
        EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ponto_app';
        EXECUTE 'REVOKE INSERT, UPDATE, DELETE ON permissoes FROM ponto_app';

        -- Revoga tambem em cada particao de marcacoes: revogar so no pai nao
        -- alcanca as particoes, e o privilegio e verificado na relacao acessada.
        FOR r IN
            SELECT c.relname
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
               AND c.relkind IN ('r','p')
               AND (c.relname = ANY (v_append_only)
                    OR c.oid IN (SELECT inhrelid FROM pg_inherits
                                  WHERE inhparent = 'marcacoes'::regclass))
        LOOP
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM ponto_app', r.relname);
        END LOOP;

        FOR r IN SELECT unnest(v_sem_delete) AS relname LOOP
            EXECUTE format('REVOKE DELETE, TRUNCATE ON %I FROM ponto_app', r.relname);
        END LOOP;

        -- Excecao unica em todo o modelo: a rotina de consumo FIFO/LIFO precisa
        -- atualizar consumido_minutos.
        EXECUTE 'GRANT UPDATE (consumido_minutos) ON bh_lancamentos TO ponto_app';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_leitura') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO ponto_leitura';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO ponto_leitura';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_suporte') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO ponto_suporte';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO ponto_suporte';
        EXECUTE 'REVOKE SELECT ON biometria_templates FROM ponto_suporte';
    END IF;
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE NOTICE 'Sem privilegio para conceder permissoes. Aplique os GRANTs manualmente (ver infra/).';
END $$
""",
)


# ===========================================================================
# 12. VERIFICACAO DO CONTRATO
#
# Se qualquer invariante do modelo estiver quebrada, a migration FALHA aqui em
# vez de subir um banco silenciosamente inseguro.
# ===========================================================================
SQL_VERIFICACAO = r"""
DO $$
DECLARE
    v_faltando       TEXT;
    v_sem_comentario TEXT;
    v_total_tabelas  INTEGER;
    v_total_dominio  INTEGER;
BEGIN
    -- 1. RLS habilitada e forcada em toda tabela com tenant_id.
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_faltando
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r','p')
       AND EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
       AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity);
    IF v_faltando IS NOT NULL THEN
        RAISE EXCEPTION 'RLS ausente ou nao forcada nas tabelas: %', v_faltando;
    END IF;

    -- 2. Policy de isolamento presente em toda tabela com tenant_id.
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_faltando
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r','p')
       AND EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
       AND NOT EXISTS (SELECT 1 FROM pg_policies p
                        WHERE p.schemaname = 'public'
                          AND p.tablename = c.relname
                          AND p.policyname = 'pol_isolamento_tenant');
    IF v_faltando IS NOT NULL THEN
        RAISE EXCEPTION 'Policy pol_isolamento_tenant ausente nas tabelas: %', v_faltando;
    END IF;

    -- 3. Marcacoes protegidas por gatilho de imutabilidade.
    IF (SELECT count(*) FROM pg_trigger t
         WHERE t.tgrelid = 'marcacoes'::regclass AND NOT t.tgisinternal) < 2 THEN
        RAISE EXCEPTION 'marcacoes sem os gatilhos de bloqueio de UPDATE e DELETE';
    END IF;

    -- 4. Toda tabela de dominio comentada (documentacao viva).
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_sem_comentario
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r','p')
       AND c.relispartition = FALSE
       AND c.relname <> 'alembic_version'
       AND obj_description(c.oid, 'pg_class') IS NULL;
    IF v_sem_comentario IS NOT NULL THEN
        RAISE EXCEPTION 'Tabelas sem COMMENT ON TABLE: %', v_sem_comentario;
    END IF;

    SELECT count(*) INTO v_total_tabelas
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND c.relispartition = FALSE;

    SELECT count(*) INTO v_total_dominio
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND c.relispartition = FALSE
       AND EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped);

    RAISE NOTICE 'Migration 0001_inicial aplicada. Tabelas: % (sendo % com tenant_id sob RLS).',
                 v_total_tabelas, v_total_dominio;
END $$
"""


# ===========================================================================
#  U P G R A D E
# ===========================================================================
def upgrade() -> None:
    # --- 1. extensoes -------------------------------------------------------
    for instrucao in SQL_EXTENSOES:
        op.execute(instrucao)

    # --- 2. funcoes auxiliares ---------------------------------------------
    for instrucao in SQL_FUNCOES:
        op.execute(instrucao)

    # --- 3. dominios de formato --------------------------------------------
    for nome, restricao, comentario in DOMINIOS:
        op.execute(f"CREATE DOMAIN {nome} AS TEXT CHECK ({restricao})")
        op.execute(f"COMMENT ON DOMAIN {nome} IS '{comentario}'")

    # --- 4. tabelas e indices ----------------------------------------------
    _criar_tabelas()

    # --- 5. chaves estrangeiras adiadas ------------------------------------
    _criar_fks_adiadas()

    # --- 6. resolucao de tenant e de terminal -------------------------------
    for instrucao in SQL_RESOLVE_TENANT:
        op.execute(instrucao)
    for instrucao in SQL_RESOLVE_TERMINAL:
        op.execute(instrucao)

    # --- 7. particionamento de marcacoes -----------------------------------
    for instrucao in SQL_PARTICIONAMENTO:
        op.execute(instrucao)

    # --- 8. gatilhos de imutabilidade --------------------------------------
    for nome, evento, tabela, granularidade, funcao in GATILHOS_IMUTABILIDADE:
        op.execute(
            f"CREATE TRIGGER {nome} {evento} ON {tabela} "
            f"{granularidade} EXECUTE FUNCTION {funcao}()"
        )

    # --- 9. gatilhos de atualizado_em --------------------------------------
    op.execute(SQL_GATILHOS_TIMESTAMP)

    # --- 10. Row Level Security --------------------------------------------
    for instrucao in SQL_RLS:
        op.execute(instrucao)

    # --- 11. roles e privilegios -------------------------------------------
    for instrucao in SQL_ROLES:
        op.execute(instrucao)

    # --- 12. verificacao do contrato ---------------------------------------
    op.execute(SQL_VERIFICACAO)


# ===========================================================================
#  D O W N G R A D E
# ===========================================================================
def downgrade() -> None:
    # As chaves estrangeiras adiadas saem primeiro: sao elas que fecham os
    # ciclos e impediriam o DROP TABLE em ordem topologica inversa.
    _remover_fks_adiadas()

    # DROP TABLE leva junto indices, gatilhos, policies e - no caso de
    # `marcacoes` - todas as particoes mensais e a particao padrao.
    _remover_tabelas()

    for assinatura in FUNCOES_PARA_REMOVER:
        op.execute(f"DROP FUNCTION IF EXISTS {assinatura}")

    for nome, _restricao, _comentario in reversed(DOMINIOS):
        op.execute(f"DROP DOMAIN IF EXISTS {nome}")

    # Extensoes e roles permanecem de proposito - ver docstring do modulo.


# ===========================================================================
#  Blocos gerados a partir de `ponto_contracts.Base.metadata`
# ===========================================================================
def _criar_tabelas() -> None:
    op.create_table(
        "permissoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("recurso", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("sensivel", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("modulo", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "acao IN ('ler','criar','editar','excluir','aprovar','exportar','executar','assinar','administrar','configurar','reabrir','ler_sensivel')",
            name="permissoes_acao_check",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("permissoes_pkey")),
        sa.UniqueConstraint("codigo", name="uq_permissoes_codigo"),
        sa.UniqueConstraint("recurso", "acao", name="uq_permissoes_recurso_acao"),
        comment="Catalogo GLOBAL de permissoes do produto (recurso mais acao). Unica tabela sem tenant_id alem de tenants: as permissoes correspondem a endpoints do codigo e sao somente leitura para a aplicacao.",
    )
    op.create_index("ix_permissoes_modulo", "permissoes", ["modulo", "recurso"], unique=False)
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("razao_social", sa.Text(), nullable=False),
        sa.Column("nome_exibicao", sa.Text(), nullable=False),
        sa.Column(
            "documento", postgresql.DOMAIN("dom_cnpj", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("plano", sa.Text(), server_default=sa.text("'padrao'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'trial'"), nullable=False),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("locale", sa.Text(), server_default=sa.text("'pt-BR'"), nullable=False),
        sa.Column("dominio_proprio", sa.Text(), nullable=True),
        sa.Column("limite_colaboradores", sa.Integer(), nullable=True),
        sa.Column("data_contratacao", sa.Date(), nullable=True),
        sa.Column("data_cancelamento", sa.Date(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "plano IN ('trial','padrao','avancado','enterprise')", name="tenants_plano_check"
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$'", name="ck_tenants_slug_formato"
        ),
        sa.CheckConstraint(
            "status IN ('trial','ativo','suspenso','cancelado')", name="tenants_status_check"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tenants_pkey")),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        comment="Raiz da multi-tenancy. Cada tenant e um cliente do SaaS e pode conter varias empresas (CNPJs). Unica tabela de dominio sem coluna tenant_id: ela e o proprio tenant.",
    )
    op.create_index(
        "ix_tenants_dominio_proprio",
        "tenants",
        ["dominio_proprio"],
        unique=True,
        postgresql_where=sa.text("dominio_proprio IS NOT NULL"),
    )
    op.create_index(
        "ix_tenants_status",
        "tenants",
        ["status"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "anexos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=False),
        sa.Column("entidade_id", sa.Uuid(), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("confidencial", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "entidade IN ('solicitacao','tratamento','afastamento','colaborador','fechamento','ocorrencia','marcacao','importacao')",
            name="anexos_entidade_check",
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0", name="anexos_tamanho_bytes_check"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("anexos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("anexos_pkey")),
        comment="Arquivos anexados a qualquer entidade do workflow. A referencia e polimorfica e por isso NAO tem chave estrangeira; a integridade e garantida na aplicacao.",
    )
    op.create_index(
        "ix_anexos_entidade",
        "anexos",
        ["tenant_id", "entidade", "entidade_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "api_clients",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret_hash", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'confidencial'"), nullable=False),
        sa.Column("ambiente", sa.Text(), server_default=sa.text("'sandbox'"), nullable=False),
        sa.Column(
            "escopos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("ips_permitidos", postgresql.ARRAY(postgresql.CIDR()), nullable=True),
        sa.Column(
            "rate_limit_por_minuto", sa.Integer(), server_default=sa.text("600"), nullable=False
        ),
        sa.Column(
            "contato_email",
            postgresql.DOMAIN("dom_email", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("ambiente IN ('sandbox','producao')", name="api_clients_ambiente_check"),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','revogado')", name="api_clients_status_check"
        ),
        sa.CheckConstraint(
            "tipo IN ('confidencial','publico','maquina')", name="api_clients_tipo_check"
        ),
        sa.CheckConstraint(
            "rate_limit_por_minuto > 0", name="api_clients_rate_limit_por_minuto_check"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("api_clients_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("api_clients_pkey")),
        sa.UniqueConstraint("client_id", name="uq_api_clients_client_id"),
        comment="Aplicacao integradora autorizada a consumir a API publica. Cada cliente vive em um ambiente (sandbox ou producao).",
    )
    op.create_index("ix_api_clients_tenant", "api_clients", ["tenant_id", "status"], unique=False)
    op.create_index(
        "uq_api_clients_nome",
        "api_clients",
        ["tenant_id", "nome"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "arquivo_assinaturas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_arquivo", sa.Text(), nullable=False),
        sa.Column("arquivo_id", sa.Uuid(), nullable=False),
        sa.Column("padrao", sa.Text(), server_default=sa.text("'CAdES'"), nullable=False),
        sa.Column("formato", sa.Text(), server_default=sa.text("'detached'"), nullable=False),
        sa.Column("assinatura_ref", sa.Text(), nullable=False),
        sa.Column("certificado_titular", sa.Text(), nullable=True),
        sa.Column("certificado_serial", sa.Text(), nullable=True),
        sa.Column("certificado_emissor", sa.Text(), nullable=True),
        sa.Column("certificado_validade_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificado_validade_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("politica_assinatura", sa.Text(), nullable=True),
        sa.Column("carimbo_tempo", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "hash_arquivo",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("algoritmo_hash", sa.Text(), server_default=sa.text("'SHA-256'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'assinado'"), nullable=False),
        sa.Column("validado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validacao_resultado", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "formato IN ('detached','attached')", name="arquivo_assinaturas_formato_check"
        ),
        sa.CheckConstraint(
            "padrao IN ('CAdES','XAdES','PAdES')", name="arquivo_assinaturas_padrao_check"
        ),
        sa.CheckConstraint(
            "status IN ('pendente','assinado','invalido','revogado')",
            name="arquivo_assinaturas_status_check",
        ),
        sa.CheckConstraint(
            "tipo_arquivo IN ('afd','aej','espelho','comprovante','relatorio')",
            name="arquivo_assinaturas_tipo_arquivo_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("arquivo_assinaturas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("arquivo_assinaturas_pkey")),
        comment="Assinatura digital de arquivos fiscais no padrao CAdES, em .p7s destacado, com certificado ICP-Brasil. Referencia polimorfica sem chave estrangeira. Somente-acrescimo: DELETE e barrado por gatilho.",
    )
    op.create_index(
        "ix_arquivo_assinaturas_alvo",
        "arquivo_assinaturas",
        ["tenant_id", "tipo_arquivo", "arquivo_id"],
        unique=False,
    )
    op.create_table(
        "auditoria",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sequencia", sa.BigInteger(), nullable=False),
        sa.Column("evento", sa.Text(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=False),
        sa.Column("entidade_id", sa.Uuid(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("usuario_email", sa.Text(), nullable=True),
        sa.Column("perfil", sa.Text(), nullable=True),
        sa.Column("delegacao_id", sa.Uuid(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), server_default=sa.text("'api'"), nullable=False),
        sa.Column("requisicao_id", sa.Text(), nullable=True),
        sa.Column("valor_anterior", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valor_novo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diferenca", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadados", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resultado", sa.Text(), server_default=sa.text("'sucesso'"), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column(
            "ocorrido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "hash_anterior",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "hash_registro",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "acao IN ('criar','ler','atualizar','excluir','aprovar','reprovar','exportar','login','logout','falha_login','fechar','reabrir','assinar','revogar','configurar','recalcular')",
            name="auditoria_acao_check",
        ),
        sa.CheckConstraint(
            "origem IN ('web','mobile','api','terminal','worker','cli','sistema')",
            name="auditoria_origem_check",
        ),
        sa.CheckConstraint(
            "resultado IN ('sucesso','falha','negado')", name="auditoria_resultado_check"
        ),
        sa.CheckConstraint("sequencia >= 1", name="auditoria_sequencia_check"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("auditoria_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("auditoria_pkey")),
        sa.UniqueConstraint("tenant_id", "hash_registro", name="uq_auditoria_hash"),
        sa.UniqueConstraint("tenant_id", "sequencia", name="uq_auditoria_sequencia"),
        comment="Trilha de auditoria ENCADEADA. Cada linha carrega o hash da anterior, formando uma cadeia por tenant: remover uma linha silenciosamente quebra a cadeia e e detectavel.",
    )
    op.create_index(
        "ix_auditoria_acao",
        "auditoria",
        ["tenant_id", "acao", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_auditoria_entidade",
        "auditoria",
        ["tenant_id", "entidade", "entidade_id", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_auditoria_ocorrido",
        "auditoria",
        ["tenant_id", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_auditoria_usuario",
        "auditoria",
        ["tenant_id", "usuario_id", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_table(
        "empresas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("matriz_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'matriz'"), nullable=False),
        sa.Column(
            "cnpj", postgresql.DOMAIN("dom_cnpj", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column("razao_social", sa.Text(), nullable=False),
        sa.Column("nome_fantasia", sa.Text(), nullable=True),
        sa.Column("inscricao_estadual", sa.Text(), nullable=True),
        sa.Column("inscricao_municipal", sa.Text(), nullable=True),
        sa.Column("cnae_principal", sa.Text(), nullable=True),
        sa.Column("cei_caepf", sa.Text(), nullable=True),
        sa.Column("natureza_juridica", sa.Text(), nullable=True),
        sa.Column("logradouro", sa.Text(), nullable=True),
        sa.Column("numero", sa.Text(), nullable=True),
        sa.Column("complemento", sa.Text(), nullable=True),
        sa.Column("bairro", sa.Text(), nullable=True),
        sa.Column("municipio", sa.Text(), nullable=True),
        sa.Column("uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True),
        sa.Column("cep", postgresql.DOMAIN("dom_cep", sa.TEXT(), create_type=False), nullable=True),
        sa.Column(
            "codigo_ibge_municipio",
            postgresql.DOMAIN("dom_ibge", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("telefone", sa.Text(), nullable=True),
        sa.Column(
            "email", postgresql.DOMAIN("dom_email", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("logo_ref", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(tipo = 'matriz' AND matriz_id IS NULL) OR (tipo = 'filial' AND matriz_id IS NOT NULL)",
            name="ck_empresas_matriz",
        ),
        sa.CheckConstraint("tipo IN ('matriz','filial')", name="empresas_tipo_check"),
        sa.ForeignKeyConstraint(
            ["matriz_id"],
            ["empresas.id"],
            name=op.f("empresas_matriz_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("empresas_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("empresas_pkey")),
        comment="Pessoa juridica empregadora dentro do tenant. Matriz e filiais sao linhas distintas ligadas por matriz_id, cada uma com seu proprio CNPJ e seus proprios arquivos fiscais.",
    )
    op.create_index("ix_empresas_matriz", "empresas", ["tenant_id", "matriz_id"], unique=False)
    op.create_index(
        "ix_empresas_tenant",
        "empresas",
        ["tenant_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_empresas_cnpj",
        "empresas",
        ["tenant_id", "cnpj"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "feriado_conjuntos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("abrangencia", sa.Text(), nullable=False),
        sa.Column("uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True),
        sa.Column(
            "codigo_ibge_municipio",
            postgresql.DOMAIN("dom_ibge", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(abrangencia = 'estadual'  AND uf IS NOT NULL) OR (abrangencia = 'municipal' AND codigo_ibge_municipio IS NOT NULL) OR (abrangencia IN ('nacional','empresa','unidade'))",
            name="ck_feriado_conjuntos_abrangencia",
        ),
        sa.CheckConstraint(
            "abrangencia IN ('nacional','estadual','municipal','empresa','unidade')",
            name="feriado_conjuntos_abrangencia_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("feriado_conjuntos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("feriado_conjuntos_pkey")),
        comment="Agrupamento de feriados por abrangencia. A unidade combina varios conjuntos (nacional mais estadual mais municipal).",
    )
    op.create_index(
        "uq_feriado_conjuntos_codigo",
        "feriado_conjuntos",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "perfis",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("sistema", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("escopo_padrao", sa.Text(), server_default=sa.text("'tenant'"), nullable=False),
        sa.Column("somente_leitura", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "escopo_padrao IN ('global','tenant','empresa','unidade','departamento','equipe','proprio')",
            name="perfis_escopo_padrao_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("perfis_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("perfis_pkey")),
        comment="Papel do RBAC. Os perfis de fabrica sao super_admin, admin_empresa, rh, gestor, colaborador, auditor e integracao; o tenant pode criar os seus.",
    )
    op.create_index(
        "uq_perfis_codigo",
        "perfis",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "politicas_retencao",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=False),
        sa.Column("prazo_dias", sa.Integer(), nullable=False),
        sa.Column("base_legal", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("ultima_execucao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proxima_execucao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registros_ultima_execucao", sa.BigInteger(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "acao IN ('anonimizar','eliminar','arquivar')", name="politicas_retencao_acao_check"
        ),
        sa.CheckConstraint(
            "entidade IN ('marcacao','foto_registro','biometria','documento','auditoria','notificacao','espelho','afd','aej','log_acesso','fila_offline','relatorio_execucao','sessao')",
            name="politicas_retencao_entidade_check",
        ),
        sa.CheckConstraint("prazo_dias > 0", name="politicas_retencao_prazo_dias_check"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("politicas_retencao_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("politicas_retencao_pkey")),
        sa.UniqueConstraint("tenant_id", "entidade", name="uq_politicas_retencao"),
        comment="Prazo de guarda por tipo de dado e o que fazer no vencimento. Marcacao retem 5 anos por obrigacao legal; foto de captura retem prazo curto.",
    )
    op.create_table(
        "relatorio_definicoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("sistema", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column(
            "colunas_disponiveis",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "filtros_disponiveis",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "agrupamentos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "formatos",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{csv,xlsx,pdf}'"),
            nullable=False,
        ),
        sa.Column("permissao_codigo", sa.Text(), nullable=True),
        sa.Column("assincrono", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('operacional','gerencial','fiscal','financeiro','lgpd')",
            name="relatorio_definicoes_categoria_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("relatorio_definicoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("relatorio_definicoes_pkey")),
        comment="Catalogo dos relatorios disponiveis. Os 24 relatorios do produto sao semeados por tenant com sistema = true.",
    )
    op.create_index(
        "uq_relatorio_definicoes_codigo",
        "relatorio_definicoes",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "tenant_configuracoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("categoria", sa.Text(), server_default=sa.text("'geral'"), nullable=False),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("valor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("somente_leitura", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('geral','seguranca','jornada','banco_horas','fiscal','notificacao','integracao','lgpd','aparencia')",
            name="tenant_configuracoes_categoria_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("tenant_configuracoes_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tenant_configuracoes_pkey")),
        sa.UniqueConstraint("tenant_id", "chave", name="uq_tenant_configuracoes"),
        comment="Configuracoes chave/valor por tenant. Usada para parametros que nao merecem coluna propria (limiares, textos, feature flags).",
    )
    op.create_index(
        "ix_tenant_configuracoes_categoria",
        "tenant_configuracoes",
        ["tenant_id", "categoria"],
        unique=False,
    )
    op.create_table(
        "tipos_afastamento",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("codigo_esocial", sa.Text(), nullable=True),
        sa.Column("abona_dia", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("remunerado", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("computa_carga", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("computa_dsr", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "suspende_contrato", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("exige_documento", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("limite_dias", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('ferias','atestado','licenca_maternidade','licenca_paternidade','inss','acidente_trabalho','suspensao','falta_justificada','falta_injustificada','servico_militar','doacao_sangue','casamento','obito','treinamento','licenca_nao_remunerada','outro')",
            name="tipos_afastamento_categoria_check",
        ),
        sa.CheckConstraint(
            "limite_dias IS NULL OR limite_dias > 0", name="tipos_afastamento_limite_dias_check"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("tipos_afastamento_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tipos_afastamento_pkey")),
        comment="Catalogo configuravel de motivos de ausencia e o efeito de cada um no calculo. Os codigos de fabrica sao semeados por tenant.",
    )
    op.create_index(
        "uq_tipos_afastamento_codigo",
        "tipos_afastamento",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "tipos_tratamento",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("exige_aprovacao", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("exige_anexo", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("exige_motivo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("afeta_afd", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("afeta_aej", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("permite_retroativo_dias", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('inclusao_marcacao','desconsideracao_marcacao','ajuste_intervalo','abono','justificativa','afastamento','compensacao','ajuste_saldo')",
            name="tipos_tratamento_categoria_check",
        ),
        sa.CheckConstraint("afeta_afd = FALSE", name="ck_tipos_tratamento_afd"),
        sa.CheckConstraint(
            "permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0",
            name="tipos_tratamento_permite_retroativo_dias_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("tipos_tratamento_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tipos_tratamento_pkey")),
        comment="Catalogo configuravel de tipos de tratamento. Tratamento e a UNICA forma de corrigir a jornada, e ele nunca altera a marcacao.",
    )
    op.create_index(
        "uq_tipos_tratamento_codigo",
        "tipos_tratamento",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column(
            "email", postgresql.DOMAIN("dom_email", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column("email_verificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nome_completo", sa.Text(), nullable=False),
        sa.Column("telefone", sa.Text(), nullable=True),
        sa.Column("avatar_ref", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'humano'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'convidado'"), nullable=False),
        sa.Column("idioma", sa.Text(), server_default=sa.text("'pt-BR'"), nullable=False),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("mfa_obrigatorio", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("ultimo_acesso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_acesso_ip", postgresql.INET(), nullable=True),
        sa.Column("aceite_termos_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('convidado','ativo','bloqueado','inativo')", name="usuarios_status_check"
        ),
        sa.CheckConstraint("tipo IN ('humano','servico','suporte')", name="usuarios_tipo_check"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("usuarios_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("usuarios_pkey")),
        comment="Identidade de acesso ao sistema. Distinta de colaborador: nem todo colaborador tem usuario e nem todo usuario e colaborador.",
    )
    op.create_index(
        "ix_usuarios_status",
        "usuarios",
        ["tenant_id", "status"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_usuarios_colaborador",
        "usuarios",
        ["tenant_id", "colaborador_id"],
        unique=True,
        postgresql_where=sa.text("colaborador_id IS NOT NULL AND excluido_em IS NULL"),
    )
    op.create_index(
        "uq_usuarios_email",
        "usuarios",
        ["tenant_id", sa.literal_column("lower(email)")],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("api_client_id", sa.Uuid(), nullable=False),
        sa.Column("prefixo", sa.Text(), nullable=False),
        sa.Column(
            "hash", postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column("rotulo", sa.Text(), nullable=True),
        sa.Column("ambiente", sa.Text(), server_default=sa.text("'sandbox'"), nullable=False),
        sa.Column(
            "escopos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_uso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_ip", postgresql.INET(), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revogacao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("ambiente IN ('sandbox','producao')", name="api_keys_ambiente_check"),
        sa.ForeignKeyConstraint(
            ["api_client_id"],
            ["api_clients.id"],
            name=op.f("api_keys_api_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("api_keys_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("api_keys_pkey")),
        sa.UniqueConstraint("tenant_id", "prefixo", name="uq_api_keys_prefixo"),
        comment="Chave de API para integracoes simples que nao justificam o fluxo OAuth completo. Guardada por hash; o prefixo serve para identificar a chave.",
    )
    op.create_index(
        "ix_api_keys_client",
        "api_keys",
        ["tenant_id", "api_client_id"],
        unique=False,
        postgresql_where=sa.text("revogada_em IS NULL"),
    )
    op.create_table(
        "cargos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("cbo", postgresql.DOMAIN("dom_cbo", sa.TEXT(), create_type=False), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("nivel", sa.Text(), nullable=True),
        sa.Column("salario_base", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("cargo_confianca", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "nivel IN ('estagio','aprendiz','junior','pleno','senior','especialista','coordenacao','gerencia','diretoria')",
            name="cargos_nivel_check",
        ),
        sa.CheckConstraint(
            "salario_base IS NULL OR salario_base >= 0", name="cargos_salario_base_check"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("cargos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("cargos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("cargos_pkey")),
        comment="Cargo ocupado pelo colaborador, com CBO para o eSocial.",
    )
    op.create_index(
        "ix_cargos_empresa",
        "cargos",
        ["tenant_id", "empresa_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_cargos_codigo",
        "cargos",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "centros_custo",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("centro_custo_pai_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("codigo_externo", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["centro_custo_pai_id"],
            ["centros_custo.id"],
            name=op.f("centros_custo_centro_custo_pai_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("centros_custo_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("centros_custo_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("centros_custo_pkey")),
        comment="Centro de custo, projeto ou cliente ao qual as horas sao apropriadas. Base do relatorio de horas por centro de custo e do rateio para a folha.",
    )
    op.create_index(
        "ix_centros_custo_pai", "centros_custo", ["tenant_id", "centro_custo_pai_id"], unique=False
    )
    op.create_index(
        "uq_centros_custo_codigo",
        "centros_custo",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "colaboradores",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("matricula", sa.Text(), nullable=False),
        sa.Column(
            "cpf", postgresql.DOMAIN("dom_cpf", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column(
            "pis_nit", postgresql.DOMAIN("dom_pis", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("nome_completo", sa.Text(), nullable=False),
        sa.Column("nome_social", sa.Text(), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=True),
        sa.Column("sexo", sa.Text(), nullable=True),
        sa.Column("estado_civil", sa.Text(), nullable=True),
        sa.Column("nacionalidade", sa.Text(), nullable=True),
        sa.Column("naturalidade", sa.Text(), nullable=True),
        sa.Column("nome_mae", sa.Text(), nullable=True),
        sa.Column("rg_numero", sa.Text(), nullable=True),
        sa.Column("rg_orgao_emissor", sa.Text(), nullable=True),
        sa.Column(
            "rg_uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("ctps_numero", sa.Text(), nullable=True),
        sa.Column("ctps_serie", sa.Text(), nullable=True),
        sa.Column(
            "ctps_uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("titulo_eleitor", sa.Text(), nullable=True),
        sa.Column(
            "email", postgresql.DOMAIN("dom_email", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("telefone", sa.Text(), nullable=True),
        sa.Column("telefone_alternativo", sa.Text(), nullable=True),
        sa.Column("foto_ref", sa.Text(), nullable=True),
        sa.Column("logradouro", sa.Text(), nullable=True),
        sa.Column("numero", sa.Text(), nullable=True),
        sa.Column("complemento", sa.Text(), nullable=True),
        sa.Column("bairro", sa.Text(), nullable=True),
        sa.Column("municipio", sa.Text(), nullable=True),
        sa.Column("uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True),
        sa.Column("cep", postgresql.DOMAIN("dom_cep", sa.TEXT(), create_type=False), nullable=True),
        sa.Column(
            "codigo_ibge_municipio",
            postgresql.DOMAIN("dom_ibge", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column("data_admissao", sa.Date(), nullable=True),
        sa.Column("data_desligamento", sa.Date(), nullable=True),
        sa.Column("pcd", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("codigo_externo", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado_civil IN ('solteiro','casado','divorciado','viuvo','uniao_estavel','separado')",
            name="colaboradores_estado_civil_check",
        ),
        sa.CheckConstraint(
            "sexo IN ('feminino','masculino','outro','nao_informado')",
            name="colaboradores_sexo_check",
        ),
        sa.CheckConstraint(
            "status IN ('pre_admissao','ativo','afastado','ferias','suspenso','desligado')",
            name="colaboradores_status_check",
        ),
        sa.CheckConstraint(
            "data_desligamento IS NULL OR data_admissao IS NULL OR data_desligamento >= data_admissao",
            name="ck_colaboradores_desligamento",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("colaboradores_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("colaboradores_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("colaboradores_pkey")),
        comment="A PESSOA que trabalha. Guarda os dados cadastrais e pessoais. As condicoes de trabalho vivem em contratos e vinculos.",
    )
    op.create_index("ix_colaboradores_cpf", "colaboradores", ["tenant_id", "cpf"], unique=False)
    op.create_index(
        "ix_colaboradores_empresa_status",
        "colaboradores",
        ["tenant_id", "empresa_id", "status"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_colaboradores_nome_trgm",
        "colaboradores",
        ["nome_completo"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"nome_completo": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_colaboradores_cpf",
        "colaboradores",
        ["tenant_id", "empresa_id", "cpf"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_colaboradores_matricula",
        "colaboradores",
        ["tenant_id", "empresa_id", "matricula"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "credenciais",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("algoritmo", sa.Text(), server_default=sa.text("'argon2id'"), nullable=False),
        sa.Column("provedor_sso", sa.Text(), nullable=True),
        sa.Column("identificador_externo", sa.Text(), nullable=True),
        sa.Column(
            "trocar_no_proximo_acesso",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tentativas_falhas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("bloqueado_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_troca_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "algoritmo IN ('argon2id','bcrypt','scrypt','pbkdf2','nenhum')",
            name="credenciais_algoritmo_check",
        ),
        sa.CheckConstraint(
            "provedor_sso IN ('google','entra_id','saml','okta')",
            name="credenciais_provedor_sso_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('senha','pin','certificado','sso','recuperacao')",
            name="credenciais_tipo_check",
        ),
        sa.CheckConstraint("tentativas_falhas >= 0", name="credenciais_tentativas_falhas_check"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("credenciais_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("credenciais_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("credenciais_pkey")),
        comment="Segredos de autenticacao do usuario. Uma linha ativa por tipo. Senhas em Argon2id; a coluna hash nunca guarda o segredo em claro.",
    )
    op.create_index(
        "ix_credenciais_sso",
        "credenciais",
        ["tenant_id", "provedor_sso", "identificador_externo"],
        unique=False,
        postgresql_where=sa.text("provedor_sso IS NOT NULL"),
    )
    op.create_index(
        "ix_credenciais_usuario", "credenciais", ["tenant_id", "usuario_id"], unique=False
    )
    op.create_index(
        "uq_credenciais_ativa",
        "credenciais",
        ["tenant_id", "usuario_id", "tipo"],
        unique=True,
        postgresql_where=sa.text("ativo"),
    )
    op.create_table(
        "delegacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("delegante_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("delegado_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("escopo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("inicio_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fim_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'agendada'"), nullable=False),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_por", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("delegante_usuario_id"), "="),
            (sa.column("delegado_usuario_id"), "="),
            (sa.text("tstzrange(inicio_em, fim_em)"), "&&"),
            where=sa.text("status IN ('agendada','ativa')"),
            using="gist",
            name="ex_delegacoes_sobreposicao",
        ),
        sa.CheckConstraint(
            "status IN ('agendada','ativa','encerrada','cancelada')", name="delegacoes_status_check"
        ),
        sa.CheckConstraint(
            "delegante_usuario_id <> delegado_usuario_id", name="ck_delegacoes_pessoas"
        ),
        sa.CheckConstraint("fim_em > inicio_em", name="ck_delegacoes_periodo"),
        sa.ForeignKeyConstraint(
            ["delegado_usuario_id"],
            ["usuarios.id"],
            name=op.f("delegacoes_delegado_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["delegante_usuario_id"],
            ["usuarios.id"],
            name=op.f("delegacoes_delegante_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["perfil_id"],
            ["perfis.id"],
            name=op.f("delegacoes_perfil_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("delegacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("delegacoes_pkey")),
        comment="Delegacao temporaria de atribuicoes, tipicamente ferias do gestor. Toda acao exercida por delegacao e marcada como tal na auditoria.",
    )
    op.create_index(
        "ix_delegacoes_delegado",
        "delegacoes",
        ["tenant_id", "delegado_usuario_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_delegacoes_periodo",
        "delegacoes",
        ["tenant_id", "inicio_em", "fim_em"],
        unique=False,
        postgresql_where=sa.text("status IN ('agendada','ativa')"),
    )
    op.create_table(
        "departamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("departamento_pai_id", sa.Uuid(), nullable=True),
        sa.Column("responsavel_colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["departamento_pai_id"],
            ["departamentos.id"],
            name=op.f("departamentos_departamento_pai_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("departamentos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("departamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("departamentos_pkey")),
        comment="Estrutura departamental hierarquica da empresa. Usada para escopo de perfil, agrupamento de relatorio e roteamento de aprovacao.",
    )
    op.create_index(
        "ix_departamentos_pai", "departamentos", ["tenant_id", "departamento_pai_id"], unique=False
    )
    op.create_index(
        "uq_departamentos_codigo",
        "departamentos",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "feriados",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("feriado_conjunto_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'feriado'"), nullable=False),
        sa.Column("movel", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("regra_movel", sa.Text(), nullable=True),
        sa.Column("offset_dias", sa.Integer(), nullable=True),
        sa.Column("integral", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("carga_reduzida_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "regra_movel IN ('pascoa','carnaval','sexta_santa','corpus_christi','quarta_cinzas','custom')",
            name="feriados_regra_movel_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('feriado','ponto_facultativo','data_comemorativa','compensado')",
            name="feriados_tipo_check",
        ),
        sa.CheckConstraint(
            "(movel = TRUE  AND regra_movel IS NOT NULL) OR (movel = FALSE AND data IS NOT NULL)",
            name="ck_feriados_definicao",
        ),
        sa.CheckConstraint("ano IS NULL OR ano BETWEEN 1900 AND 2200", name="feriados_ano_check"),
        sa.CheckConstraint(
            "carga_reduzida_minutos IS NULL OR carga_reduzida_minutos >= 0",
            name="feriados_carga_reduzida_minutos_check",
        ),
        sa.CheckConstraint(
            "integral = TRUE OR carga_reduzida_minutos IS NOT NULL", name="ck_feriados_parcial"
        ),
        sa.ForeignKeyConstraint(
            ["feriado_conjunto_id"],
            ["feriado_conjuntos.id"],
            name=op.f("feriados_feriado_conjunto_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("feriados_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("feriados_pkey")),
        comment="Feriado, ponto facultativo ou expediente reduzido. Feriados moveis nao guardam data: sao calculados por regra a partir da Pascoa.",
    )
    op.create_index(
        "ix_feriados_conjunto", "feriados", ["tenant_id", "feriado_conjunto_id"], unique=False
    )
    op.create_index(
        "ix_feriados_data",
        "feriados",
        ["tenant_id", "data"],
        unique=False,
        postgresql_where=sa.text("data IS NOT NULL"),
    )
    op.create_index(
        "uq_feriados_fixos",
        "feriados",
        ["tenant_id", "feriado_conjunto_id", "data", "nome"],
        unique=True,
        postgresql_where=sa.text("data IS NOT NULL"),
    )
    op.create_table(
        "horarios",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("entrada", sa.Time(), nullable=True),
        sa.Column("saida", sa.Time(), nullable=True),
        sa.Column("intervalo_inicio", sa.Time(), nullable=True),
        sa.Column("intervalo_fim", sa.Time(), nullable=True),
        sa.Column("duracao_intervalo_minutos", sa.Integer(), nullable=True),
        sa.Column("intervalos_extras", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "cruza_meia_noite", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("carga_minutos", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("carga_minutos BETWEEN 0 AND 1440", name="horarios_carga_minutos_check"),
        sa.CheckConstraint(
            "duracao_intervalo_minutos IS NULL OR duracao_intervalo_minutos >= 0",
            name="horarios_duracao_intervalo_minutos_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("horarios_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("horarios_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("horarios_pkey")),
        comment="Gabarito de horario reutilizavel: entrada, saida e intervalos previstos de um dia de trabalho. E o bloco de montagem de jornadas e turnos.",
    )
    op.create_index(
        "uq_horarios_codigo",
        "horarios",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "importacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), server_default=sa.text("'csv'"), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=True),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("parametros", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'recebido'"), nullable=False),
        sa.Column("total_linhas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("linhas_processadas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("linhas_sucesso", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("linhas_erro", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("relatorio_ref", sa.Text(), nullable=True),
        sa.Column("erros", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "origem IN ('csv','xlsx','afd','api','manual')", name="importacoes_origem_check"
        ),
        sa.CheckConstraint(
            "status IN ('recebido','validando','processando','concluido','concluido_com_erros','falhou','cancelado')",
            name="importacoes_status_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('colaboradores','estrutura','escalas','feriados','marcacoes','afd_terceiro','banco_horas','biometria','afastamentos')",
            name="importacoes_tipo_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("importacoes_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("importacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("importacoes_pkey")),
        comment="Execucao de um importador. Guarda o arquivo de origem, o resultado linha a linha e o relatorio de erros.",
    )
    op.create_index(
        "ix_importacoes_status",
        "importacoes",
        ["tenant_id", "status"],
        unique=False,
        postgresql_where=sa.text("status IN ('recebido','validando','processando')"),
    )
    op.create_index(
        "ix_importacoes_tenant",
        "importacoes",
        ["tenant_id", "tipo", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_table(
        "integracoes_folha",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("parceiro", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "configuracao",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("mapeamento_rubricas", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("formato", sa.Text(), server_default=sa.text("'csv'"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("ultima_exportacao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "formato IN ('csv','txt','xml','json','api')", name="integracoes_folha_formato_check"
        ),
        sa.CheckConstraint(
            "parceiro IN ('dominio','alterdata','totvs_rm','totvs_protheus','totvs_datasul','senior','sankhya','questor','fortes','contmatic','generico_csv')",
            name="integracoes_folha_parceiro_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("integracoes_folha_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("integracoes_folha_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("integracoes_folha_pkey")),
        comment="Configuracao de exportacao para um sistema de folha. O mapeamento de rubricas traduz nossos codigos de apuracao para os do parceiro.",
    )
    op.create_index(
        "uq_integracoes_folha_nome",
        "integracoes_folha",
        ["tenant_id", "empresa_id", "nome"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "jornadas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("carga_diaria_minutos", sa.Integer(), nullable=True),
        sa.Column("carga_semanal_minutos", sa.Integer(), nullable=True),
        sa.Column("carga_mensal_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "tolerancia_marcacao_minutos", sa.Integer(), server_default=sa.text("5"), nullable=False
        ),
        sa.Column(
            "tolerancia_diaria_minutos", sa.Integer(), server_default=sa.text("10"), nullable=False
        ),
        sa.Column(
            "descontar_tudo_se_exceder",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("janela_flexivel_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "intervalo_automatico", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("intervalo_minimo_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "intervalo_flexivel", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "interjornada_minima_minutos",
            sa.Integer(),
            server_default=sa.text("660"),
            nullable=False,
        ),
        sa.Column("noturno_inicio", sa.Time(), server_default=sa.text("'22:00'"), nullable=False),
        sa.Column("noturno_fim", sa.Time(), server_default=sa.text("'05:00'"), nullable=False),
        sa.Column(
            "hora_ficta_noturna", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "prorrogacao_noturna", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "limite_extra_diario_minutos",
            sa.Integer(),
            server_default=sa.text("120"),
            nullable=False,
        ),
        sa.Column(
            "limite_jornada_diaria_minutos",
            sa.Integer(),
            server_default=sa.text("600"),
            nullable=False,
        ),
        sa.Column(
            "bloqueia_extra_acima_limite",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("compensa_sabado", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("fatores_extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "vigencia_inicio", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('fixa','flexivel','livre','escala','12x36','parcial','intermitente','teletrabalho','motorista')",
            name="jornadas_tipo_check",
        ),
        sa.CheckConstraint(
            "carga_diaria_minutos IS NULL OR carga_diaria_minutos BETWEEN 0 AND 1440",
            name="jornadas_carga_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_mensal_minutos IS NULL OR carga_mensal_minutos >= 0",
            name="jornadas_carga_mensal_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_semanal_minutos IS NULL OR carga_semanal_minutos BETWEEN 0 AND 4200",
            name="jornadas_carga_semanal_minutos_check",
        ),
        sa.CheckConstraint(
            "interjornada_minima_minutos >= 0", name="jornadas_interjornada_minima_minutos_check"
        ),
        sa.CheckConstraint(
            "intervalo_minimo_minutos IS NULL OR intervalo_minimo_minutos >= 0",
            name="jornadas_intervalo_minimo_minutos_check",
        ),
        sa.CheckConstraint(
            "janela_flexivel_minutos IS NULL OR janela_flexivel_minutos >= 0",
            name="jornadas_janela_flexivel_minutos_check",
        ),
        sa.CheckConstraint(
            "limite_extra_diario_minutos >= 0", name="jornadas_limite_extra_diario_minutos_check"
        ),
        sa.CheckConstraint(
            "limite_jornada_diaria_minutos > 0", name="jornadas_limite_jornada_diaria_minutos_check"
        ),
        sa.CheckConstraint(
            "tolerancia_diaria_minutos BETWEEN 0 AND 120",
            name="jornadas_tolerancia_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "tolerancia_marcacao_minutos BETWEEN 0 AND 60",
            name="jornadas_tolerancia_marcacao_minutos_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio", name="ck_jornadas_vigencia"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("jornadas_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("jornadas_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("jornadas_pkey")),
        comment="Conjunto de regras de trabalho e de calculo aplicado a um vinculo: carga, tolerancias, tratamento do noturno, limites de extra e politica de intervalo.",
    )
    op.create_index(
        "ix_jornadas_empresa",
        "jornadas",
        ["tenant_id", "empresa_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_jornadas_codigo",
        "jornadas",
        ["tenant_id", "empresa_id", "codigo", "vigencia_inicio"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "mfa_dispositivos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("rotulo", sa.Text(), nullable=False),
        sa.Column("segredo_cifrado", postgresql.BYTEA(), nullable=True),
        sa.Column("iv", postgresql.BYTEA(), nullable=True),
        sa.Column("chave_id", sa.Text(), nullable=True),
        sa.Column("credencial_publica", postgresql.BYTEA(), nullable=True),
        sa.Column("contador", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("confirmado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_uso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('totp','sms','email','webauthn','codigos_backup')",
            name="mfa_dispositivos_tipo_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("mfa_dispositivos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("mfa_dispositivos_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("mfa_dispositivos_pkey")),
        comment="Segundo fator registrado pelo usuario. O segredo TOTP e guardado cifrado com chave externa ao banco.",
    )
    op.create_index(
        "ix_mfa_dispositivos_usuario",
        "mfa_dispositivos",
        ["tenant_id", "usuario_id"],
        unique=False,
        postgresql_where=sa.text("ativo"),
    )
    op.create_table(
        "notificacao_preferencias",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("evento", sa.Text(), nullable=False),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("habilitado", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("janela_inicio", sa.Time(), nullable=True),
        sa.Column("janela_fim", sa.Time(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('push','email','whatsapp','in_app','sms')",
            name="notificacao_preferencias_canal_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("notificacao_preferencias_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("notificacao_preferencias_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("notificacao_preferencias_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "usuario_id", "evento", "canal", name="uq_notificacao_preferencias"
        ),
        comment="Preferencia do usuario por evento e canal. Ausencia de linha significa usar o padrao do tenant.",
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("api_client_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column(
            "token_hash",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "escopos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "emitido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("tipo IN ('access','refresh')", name="oauth_tokens_tipo_check"),
        sa.ForeignKeyConstraint(
            ["api_client_id"],
            ["api_clients.id"],
            name=op.f("oauth_tokens_api_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("oauth_tokens_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("oauth_tokens_pkey")),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_oauth_tokens_hash"),
        comment="Tokens emitidos no fluxo client credentials. Guardados por hash e revogaveis individualmente ou por cliente.",
    )
    op.create_index(
        "ix_oauth_tokens_client",
        "oauth_tokens",
        ["tenant_id", "api_client_id", "expira_em"],
        unique=False,
    )
    op.create_table(
        "perfil_permissoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("permissao_id", sa.Uuid(), nullable=False),
        sa.Column("concedida", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("condicao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["perfil_id"],
            ["perfis.id"],
            name=op.f("perfil_permissoes_perfil_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permissao_id"],
            ["permissoes.id"],
            name=op.f("perfil_permissoes_permissao_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("perfil_permissoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("perfil_permissoes_pkey")),
        sa.UniqueConstraint("tenant_id", "perfil_id", "permissao_id", name="uq_perfil_permissoes"),
        comment="Associacao entre perfil e permissao. A linha com concedida = false nega explicitamente uma permissao herdada de um perfil de fabrica.",
    )
    op.create_index(
        "ix_perfil_permissoes_perfil", "perfil_permissoes", ["tenant_id", "perfil_id"], unique=False
    )
    op.create_table(
        "periodos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'mensal'"), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column(
            "competencia_folha",
            postgresql.DOMAIN("dom_competencia", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'aberto'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('aberto','em_conferencia','fechado','reaberto','exportado')",
            name="periodos_status_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('mensal','quinzenal','semanal','personalizado','banco_horas')",
            name="periodos_tipo_check",
        ),
        sa.CheckConstraint("data_fim >= data_inicio", name="ck_periodos_intervalo"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("periodos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("periodos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("periodos_pkey")),
        sa.UniqueConstraint("tenant_id", "empresa_id", "tipo", "codigo", name="uq_periodos_codigo"),
        comment="Janela de apuracao da empresa. O periodo do ponto e independente do periodo do banco de horas.",
    )
    op.create_index(
        "ix_periodos_empresa",
        "periodos",
        ["tenant_id", "empresa_id", sa.literal_column("data_inicio DESC")],
        unique=False,
    )
    op.create_table(
        "preferencias_colunas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("relatorio_definicao_id", sa.Uuid(), nullable=True),
        sa.Column("tela", sa.Text(), nullable=True),
        sa.Column("nome", sa.Text(), server_default=sa.text("'padrao'"), nullable=False),
        sa.Column("colunas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ordenacao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("filtros", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("larguras", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("padrao", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "relatorio_definicao_id IS NOT NULL OR tela IS NOT NULL",
            name="ck_preferencias_colunas_alvo",
        ),
        sa.ForeignKeyConstraint(
            ["relatorio_definicao_id"],
            ["relatorio_definicoes.id"],
            name=op.f("preferencias_colunas_relatorio_definicao_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("preferencias_colunas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("preferencias_colunas_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("preferencias_colunas_pkey")),
        comment="Layout de colunas salvo por usuario, tanto para relatorios quanto para grades da interface.",
    )
    op.create_index(
        "uq_preferencias_colunas",
        "preferencias_colunas",
        [
            "tenant_id",
            "usuario_id",
            sa.literal_column(
                "COALESCE(relatorio_definicao_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.literal_column("COALESCE(tela, '')"),
            "nome",
        ],
        unique=True,
    )
    op.create_table(
        "relatorio_agendamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("relatorio_definicao_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "parametros",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("formato", sa.Text(), server_default=sa.text("'pdf'"), nullable=False),
        sa.Column("cron", sa.Text(), nullable=False),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("canal", sa.Text(), server_default=sa.text("'email'"), nullable=False),
        sa.Column(
            "destinatarios",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("ultima_execucao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proxima_execucao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('email','webhook','minio')", name="relatorio_agendamentos_canal_check"
        ),
        sa.CheckConstraint(
            "formato IN ('csv','xlsx','pdf','json')", name="relatorio_agendamentos_formato_check"
        ),
        sa.ForeignKeyConstraint(
            ["relatorio_definicao_id"],
            ["relatorio_definicoes.id"],
            name=op.f("relatorio_agendamentos_relatorio_definicao_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("relatorio_agendamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("relatorio_agendamentos_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("relatorio_agendamentos_pkey")),
        comment="Envio recorrente de relatorio. A expressao cron e interpretada no fuso indicado, nao no fuso do servidor.",
    )
    op.create_index(
        "ix_relatorio_agendamentos_proxima",
        "relatorio_agendamentos",
        ["tenant_id", "proxima_execucao_em"],
        unique=False,
        postgresql_where=sa.text("ativo"),
    )
    op.create_index(
        "uq_relatorio_agendamentos_nome",
        "relatorio_agendamentos",
        ["tenant_id", "nome"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "rep_ps",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("identificador", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'rep_p'"), nullable=False),
        sa.Column("numero_inpi", sa.Text(), nullable=False),
        sa.Column(
            "cnpj_desenvolvedor",
            postgresql.DOMAIN("dom_cnpj", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("razao_social_desenvolvedor", sa.Text(), nullable=False),
        sa.Column(
            "cnpj_empregador",
            postgresql.DOMAIN("dom_cnpj", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("razao_social_empregador", sa.Text(), nullable=False),
        sa.Column("cei_caepf", sa.Text(), nullable=True),
        sa.Column("versao_programa", sa.Text(), nullable=False),
        sa.Column("data_inicio_operacao", sa.Date(), nullable=False),
        sa.Column("data_fim_operacao", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("numero_inpi ~ '^[0-9]+$'", name="rep_ps_numero_inpi_check"),
        sa.CheckConstraint(
            "status IN ('ativo','inativo','substituido')", name="rep_ps_status_check"
        ),
        sa.CheckConstraint("tipo IN ('rep_p','rep_c','rep_a')", name="rep_ps_tipo_check"),
        sa.CheckConstraint(
            "data_fim_operacao IS NULL OR data_fim_operacao >= data_inicio_operacao",
            name="ck_rep_ps_periodo",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("rep_ps_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("rep_ps_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("rep_ps_pkey")),
        comment="Identificacao de cada instancia de REP-P em operacao. Cada um tem sua propria sequencia de NSR e seus proprios arquivos AFD.",
    )
    op.create_index(
        "ix_rep_ps_empresa",
        "rep_ps",
        ["tenant_id", "empresa_id"],
        unique=False,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_index(
        "uq_rep_ps_identificador",
        "rep_ps",
        ["tenant_id", "empresa_id", "identificador"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "sessoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=True),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("geolocalizacao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ultima_atividade_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_encerramento", sa.Text(), nullable=True),
        sa.Column("mfa_validado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reautenticado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('web','mobile','totem','api','terminal')", name="sessoes_canal_check"
        ),
        sa.CheckConstraint(
            "motivo_encerramento IN ('logout','expiracao','inatividade','revogacao_admin','troca_senha','reuso_token','dispositivo_revogado')",
            name="sessoes_motivo_encerramento_check",
        ),
        sa.CheckConstraint("expira_em > iniciada_em", name="ck_sessoes_expiracao"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("sessoes_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("sessoes_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("sessoes_pkey")),
        comment="Sessao de acesso ativa ou encerrada. Uma sessao agrupa a familia de refresh tokens e permite revogacao em massa por usuario ou dispositivo.",
    )
    op.create_index(
        "ix_sessoes_ativas",
        "sessoes",
        ["tenant_id", "expira_em"],
        unique=False,
        postgresql_where=sa.text("encerrada_em IS NULL"),
    )
    op.create_index(
        "ix_sessoes_dispositivo",
        "sessoes",
        ["tenant_id", "dispositivo_id"],
        unique=False,
        postgresql_where=sa.text("dispositivo_id IS NOT NULL"),
    )
    op.create_index(
        "ix_sessoes_usuario",
        "sessoes",
        ["tenant_id", "usuario_id", sa.literal_column("iniciada_em DESC")],
        unique=False,
    )
    op.create_table(
        "tipos_solicitacao",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column(
            "etapas",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("prazo_resposta_horas", sa.Integer(), nullable=True),
        sa.Column("escalonar_apos_horas", sa.Integer(), nullable=True),
        sa.Column("exige_anexo", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column(
            "exige_justificativa", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column("permite_retroativo_dias", sa.Integer(), nullable=True),
        sa.Column("tipo_tratamento_id", sa.Uuid(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('ajuste_ponto','abono','justificativa','ferias','folga','compensacao','afastamento','troca_escala','hora_extra','desbloqueio_dispositivo','outro')",
            name="tipos_solicitacao_categoria_check",
        ),
        sa.CheckConstraint(
            "escalonar_apos_horas IS NULL OR escalonar_apos_horas > 0",
            name="tipos_solicitacao_escalonar_apos_horas_check",
        ),
        sa.CheckConstraint(
            "permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0",
            name="tipos_solicitacao_permite_retroativo_dias_check",
        ),
        sa.CheckConstraint(
            "prazo_resposta_horas IS NULL OR prazo_resposta_horas > 0",
            name="tipos_solicitacao_prazo_resposta_horas_check",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("tipos_solicitacao_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_tratamento_id"],
            ["tipos_tratamento.id"],
            name=op.f("tipos_solicitacao_tipo_tratamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tipos_solicitacao_pkey")),
        comment="Catalogo configuravel de pedidos que o colaborador ou o gestor podem abrir, com a cadeia de aprovacao de cada um.",
    )
    op.create_index(
        "uq_tipos_solicitacao_codigo",
        "tipos_solicitacao",
        ["tenant_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "unidades",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'filial'"), nullable=False),
        sa.Column("logradouro", sa.Text(), nullable=True),
        sa.Column("numero", sa.Text(), nullable=True),
        sa.Column("complemento", sa.Text(), nullable=True),
        sa.Column("bairro", sa.Text(), nullable=True),
        sa.Column("municipio", sa.Text(), nullable=True),
        sa.Column("uf", postgresql.DOMAIN("dom_uf", sa.TEXT(), create_type=False), nullable=True),
        sa.Column("cep", postgresql.DOMAIN("dom_cep", sa.TEXT(), create_type=False), nullable=True),
        sa.Column(
            "codigo_ibge_municipio",
            postgresql.DOMAIN("dom_ibge", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("geocerca_latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("geocerca_longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("geocerca_raio_metros", sa.Integer(), nullable=True),
        sa.Column("geocerca_poligono", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "geocerca_obrigatoria", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "geocerca_tolerancia_metros", sa.Integer(), server_default=sa.text("50"), nullable=False
        ),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "geocerca_poligono IS NULL OR jsonb_typeof(geocerca_poligono) = 'object'",
            name="ck_unidades_poligono",
        ),
        sa.CheckConstraint(
            "tipo IN ('sede','filial','obra','cliente','home_office','movel','deposito')",
            name="unidades_tipo_check",
        ),
        sa.CheckConstraint(
            "(geocerca_latitude IS NULL AND geocerca_longitude IS NULL AND geocerca_raio_metros IS NULL) OR (geocerca_latitude IS NOT NULL AND geocerca_longitude IS NOT NULL AND geocerca_raio_metros IS NOT NULL)",
            name="ck_unidades_geocerca_ponto",
        ),
        sa.CheckConstraint(
            "geocerca_latitude IS NULL OR geocerca_latitude BETWEEN -90 AND 90",
            name="ck_unidades_latitude",
        ),
        sa.CheckConstraint(
            "geocerca_longitude IS NULL OR geocerca_longitude BETWEEN -180 AND 180",
            name="ck_unidades_longitude",
        ),
        sa.CheckConstraint(
            "geocerca_raio_metros > 0 AND geocerca_raio_metros <= 100000",
            name="unidades_geocerca_raio_metros_check",
        ),
        sa.CheckConstraint(
            "geocerca_tolerancia_metros >= 0", name="unidades_geocerca_tolerancia_metros_check"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("unidades_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("unidades_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("unidades_pkey")),
        comment="Local fisico de trabalho de uma empresa. Carrega o fuso horario efetivo do calculo de jornada, a geocerca do registro por app e o conjunto de feriados aplicavel.",
    )
    op.create_index(
        "ix_unidades_empresa",
        "unidades",
        ["tenant_id", "empresa_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_unidades_municipio", "unidades", ["tenant_id", "codigo_ibge_municipio"], unique=False
    )
    op.create_index(
        "uq_unidades_codigo",
        "unidades",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("api_client_id", sa.Uuid(), nullable=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("eventos", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("segredo_hmac_cifrado", postgresql.BYTEA(), nullable=False),
        sa.Column("chave_id", sa.Text(), nullable=True),
        sa.Column("cabecalhos_extras", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("max_tentativas", sa.Integer(), server_default=sa.text("8"), nullable=False),
        sa.Column("timeout_segundos", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column("falhas_consecutivas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ultima_entrega_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','desabilitado_por_falha')", name="webhooks_status_check"
        ),
        sa.CheckConstraint("url ~ '^https://'", name="webhooks_url_check"),
        sa.CheckConstraint("falhas_consecutivas >= 0", name="webhooks_falhas_consecutivas_check"),
        sa.CheckConstraint("max_tentativas > 0", name="webhooks_max_tentativas_check"),
        sa.CheckConstraint("timeout_segundos > 0", name="webhooks_timeout_segundos_check"),
        sa.ForeignKeyConstraint(
            ["api_client_id"],
            ["api_clients.id"],
            name=op.f("webhooks_api_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("webhooks_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("webhooks_pkey")),
        comment="Assinatura de eventos por HTTP. Somente HTTPS, garantido por CHECK. O corpo e assinado em HMAC com segredo proprio de cada webhook.",
    )
    op.create_index(
        "ix_webhooks_eventos", "webhooks", ["eventos"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "uq_webhooks_nome",
        "webhooks",
        ["tenant_id", "nome"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "acessos_dados_sensiveis",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=True),
        sa.Column("entidade_id", sa.Uuid(), nullable=True),
        sa.Column("finalidade", sa.Text(), nullable=False),
        sa.Column("base_legal", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("quantidade_registros", sa.Integer(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), nullable=True),
        sa.Column(
            "ocorrido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "acao IN ('leitura','exportacao','impressao','compartilhamento','eliminacao')",
            name="acessos_dados_sensiveis_acao_check",
        ),
        sa.CheckConstraint(
            "base_legal IN ('obrigacao_legal','consentimento','execucao_contrato','legitimo_interesse','exercicio_direitos','protecao_vida')",
            name="acessos_dados_sensiveis_base_legal_check",
        ),
        sa.CheckConstraint(
            "categoria IN ('biometria','documento','saude','remuneracao','geolocalizacao','foto','cpf','dados_pessoais')",
            name="acessos_dados_sensiveis_categoria_check",
        ),
        sa.CheckConstraint(
            "origem IN ('web','mobile','api','terminal','worker','cli','sistema')",
            name="acessos_dados_sensiveis_origem_check",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("acessos_dados_sensiveis_colaborador_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("acessos_dados_sensiveis_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("acessos_dados_sensiveis_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("acessos_dados_sensiveis_pkey")),
        comment="Registro de TODA leitura de dado pessoal sensivel. Append-only. E a evidencia que a LGPD exige, incluindo o acesso de suporte da SEEG.",
    )
    op.create_index(
        "ix_acessos_sensiveis_categoria",
        "acessos_dados_sensiveis",
        ["tenant_id", "categoria", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_acessos_sensiveis_colaborador",
        "acessos_dados_sensiveis",
        ["tenant_id", "colaborador_id", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_acessos_sensiveis_usuario",
        "acessos_dados_sensiveis",
        ["tenant_id", "usuario_id", sa.literal_column("ocorrido_em DESC")],
        unique=False,
    )
    op.create_table(
        "aej_arquivos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("periodo_id", sa.Uuid(), nullable=True),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("encoding", sa.Text(), server_default=sa.text("'ISO-8859-1'"), nullable=False),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "versao_leiaute", sa.Text(), server_default=sa.text("'671/2021'"), nullable=False
        ),
        sa.Column("total_vinculos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_marcacoes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_ausencias", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "total_lancamentos_banco", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("ptrp_identificacao", sa.Text(), nullable=False),
        sa.Column(
            "ptrp_cnpj", postgresql.DOMAIN("dom_cnpj", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("ptrp_versao", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'gerando'"), nullable=False),
        sa.Column("solicitado_por", sa.Uuid(), nullable=True),
        sa.Column("gerado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('gerando','gerado','assinado','falhou','cancelado')",
            name="aej_arquivos_status_check",
        ),
        sa.CheckConstraint("periodo_fim >= periodo_inicio", name="ck_aej_arquivos_periodo"),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0", name="aej_arquivos_tamanho_bytes_check"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("aej_arquivos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
            name=op.f("aej_arquivos_periodo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("aej_arquivos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("aej_arquivos_pkey")),
        comment="Arquivo Eletronico de Jornada, gerado pelo Programa de Tratamento de Registro de Ponto. Substitui AFDT e ACJEF.",
    )
    op.create_index(
        "ix_aej_arquivos_empresa",
        "aej_arquivos",
        ["tenant_id", "empresa_id", sa.literal_column("periodo_inicio DESC")],
        unique=False,
    )
    op.create_table(
        "afd_arquivos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("rep_p_id", sa.Uuid(), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("nsr_inicial", sa.BigInteger(), nullable=False),
        sa.Column("nsr_final", sa.BigInteger(), nullable=False),
        sa.Column("total_registros", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("encoding", sa.Text(), server_default=sa.text("'ISO-8859-1'"), nullable=False),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "versao_leiaute", sa.Text(), server_default=sa.text("'671/2021'"), nullable=False
        ),
        sa.Column("fracionado", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("fracao_numero", sa.Integer(), nullable=True),
        sa.Column("fracao_total", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'gerando'"), nullable=False),
        sa.Column("solicitado_por", sa.Uuid(), nullable=True),
        sa.Column("gerado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('gerando','gerado','assinado','falhou','cancelado')",
            name="afd_arquivos_status_check",
        ),
        sa.CheckConstraint(
            "(fracionado = FALSE AND fracao_numero IS NULL AND fracao_total IS NULL) OR (fracionado = TRUE  AND fracao_numero IS NOT NULL AND fracao_total IS NOT NULL AND fracao_numero <= fracao_total)",
            name="ck_afd_arquivos_fracao",
        ),
        sa.CheckConstraint(
            "fracao_numero IS NULL OR fracao_numero >= 1", name="afd_arquivos_fracao_numero_check"
        ),
        sa.CheckConstraint(
            "fracao_total IS NULL OR fracao_total >= 1", name="afd_arquivos_fracao_total_check"
        ),
        sa.CheckConstraint("nsr_final >= 1", name="afd_arquivos_nsr_final_check"),
        sa.CheckConstraint("nsr_final >= nsr_inicial", name="ck_afd_arquivos_nsr"),
        sa.CheckConstraint("nsr_inicial >= 1", name="afd_arquivos_nsr_inicial_check"),
        sa.CheckConstraint("periodo_fim >= periodo_inicio", name="ck_afd_arquivos_periodo"),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0", name="afd_arquivos_tamanho_bytes_check"
        ),
        sa.CheckConstraint("total_registros >= 0", name="afd_arquivos_total_registros_check"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("afd_arquivos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rep_p_id"],
            ["rep_ps.id"],
            name=op.f("afd_arquivos_rep_p_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("afd_arquivos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("afd_arquivos_pkey")),
        comment="Arquivo Fonte de Dados gerado EXCLUSIVAMENTE pelo REP-P. Texto ASCII ISO 8859-1, separador barra vertical, CR+LF, CRC-16 por registro e SHA-256 do arquivo. Nenhum tratamento entra aqui.",
    )
    op.create_index(
        "ix_afd_arquivos_empresa",
        "afd_arquivos",
        ["tenant_id", "empresa_id", sa.literal_column("periodo_inicio DESC")],
        unique=False,
    )
    op.create_index(
        "ix_afd_arquivos_rep",
        "afd_arquivos",
        ["tenant_id", "rep_p_id", "nsr_inicial"],
        unique=False,
    )
    op.create_table(
        "biometrias",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("modalidade", sa.Text(), server_default=sa.text("'facial'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("origem_cadastro", sa.Text(), nullable=False),
        sa.Column("qualidade", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("consentimento_id", sa.Uuid(), nullable=True),
        sa.Column("identificador_cartao", sa.Text(), nullable=True),
        sa.Column("cadastrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cadastrada_por", sa.Uuid(), nullable=True),
        sa.Column("validada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validada_por", sa.Uuid(), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revogacao", sa.Text(), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "modalidade IN ('facial','digital','cartao','pin','qrcode')",
            name="biometrias_modalidade_check",
        ),
        sa.CheckConstraint(
            "origem_cadastro IN ('terminal','app','web','importacao','rh')",
            name="biometrias_origem_cadastro_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','ativa','reprovada','revogada','expirada')",
            name="biometrias_status_check",
        ),
        sa.CheckConstraint(
            "qualidade IS NULL OR qualidade BETWEEN 0 AND 100", name="biometrias_qualidade_check"
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("biometrias_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("biometrias_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("biometrias_pkey")),
        comment="Credencial biometrica ou equivalente de um colaborador. Guarda o ciclo de vida; o vetor em si fica em biometria_templates.",
    )
    op.create_index(
        "ix_biometrias_colaborador", "biometrias", ["tenant_id", "colaborador_id"], unique=False
    )
    op.create_index(
        "ix_biometrias_expurgo",
        "biometrias",
        ["tenant_id", "expira_em"],
        unique=False,
        postgresql_where=sa.text("expira_em IS NOT NULL"),
    )
    op.create_index(
        "uq_biometrias_ativa",
        "biometrias",
        ["tenant_id", "colaborador_id", "modalidade"],
        unique=True,
        postgresql_where=sa.text("status = 'ativa'"),
    )
    op.create_table(
        "colaborador_gestores",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("gestor_colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'imediato'"), nullable=False),
        sa.Column(
            "vigencia_inicio", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("colaborador_id"), "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            where=sa.text("tipo = 'imediato'"),
            using="gist",
            name="ex_colaborador_gestores_imediato",
        ),
        sa.CheckConstraint(
            "tipo IN ('imediato','substituto','matricial','rh')",
            name="colaborador_gestores_tipo_check",
        ),
        sa.CheckConstraint(
            "colaborador_id <> gestor_colaborador_id", name="ck_colaborador_gestores_distintos"
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_colaborador_gestores_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("colaborador_gestores_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gestor_colaborador_id"],
            ["colaboradores.id"],
            name=op.f("colaborador_gestores_gestor_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("colaborador_gestores_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("colaborador_gestores_pkey")),
        comment="Hierarquia de gestao com historico. Define a arvore de subordinados que o perfil gestor enxerga e a cadeia de aprovacao das solicitacoes.",
    )
    op.create_index(
        "ix_colaborador_gestores_colaborador",
        "colaborador_gestores",
        ["tenant_id", "colaborador_id"],
        unique=False,
    )
    op.create_index(
        "ix_colaborador_gestores_gestor",
        "colaborador_gestores",
        ["tenant_id", "gestor_colaborador_id", "vigencia_inicio", "vigencia_fim"],
        unique=False,
    )
    op.create_table(
        "consentimentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("finalidade", sa.Text(), nullable=False),
        sa.Column("versao_termo", sa.Text(), nullable=False),
        sa.Column("texto_termo_ref", sa.Text(), nullable=False),
        sa.Column(
            "hash_termo",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'concedido'"), nullable=False),
        sa.Column("concedido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canal", sa.Text(), server_default=sa.text("'app'"), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("evidencia_ref", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('app','web','terminal','papel','importacao')",
            name="consentimentos_canal_check",
        ),
        sa.CheckConstraint(
            "finalidade IN ('biometria_facial','biometria_digital','geolocalizacao','foto_registro','uso_imagem','comunicacao')",
            name="consentimentos_finalidade_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','concedido','revogado','expirado')",
            name="consentimentos_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("consentimentos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("consentimentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("consentimentos_pkey")),
        comment="Consentimento LGPD versionado. A BIOMETRIA exige consentimento especifico: sem linha concedida vigente aqui, o template nao pode ser usado.",
    )
    op.create_index(
        "ix_consentimentos_colaborador",
        "consentimentos",
        ["tenant_id", "colaborador_id"],
        unique=False,
    )
    op.create_index(
        "uq_consentimentos_vigente",
        "consentimentos",
        ["tenant_id", "colaborador_id", "finalidade"],
        unique=True,
        postgresql_where=sa.text("status = 'concedido'"),
    )
    op.create_table(
        "contratos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("numero", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("regime_jornada", sa.Text(), server_default=sa.text("'fixa'"), nullable=False),
        sa.Column("cargo_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("centro_custo_id", sa.Uuid(), nullable=True),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("experiencia_dias", sa.Integer(), nullable=True),
        sa.Column("salario", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("tipo_salario", sa.Text(), nullable=True),
        sa.Column("carga_horaria_semanal_minutos", sa.Integer(), nullable=True),
        sa.Column("carga_horaria_mensal_minutos", sa.Integer(), nullable=True),
        sa.Column("controle_jornada", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("dispensa_controle_motivo", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column("motivo_encerramento", sa.Text(), nullable=True),
        sa.Column("documento_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "dispensa_controle_motivo IN ('art62_i_externo','art62_ii_gestao','art62_iii_teletrabalho')",
            name="contratos_dispensa_controle_motivo_check",
        ),
        sa.CheckConstraint(
            "regime_jornada IN ('fixa','flexivel','livre','escala','12x36','parcial','teletrabalho','externo','sobreaviso')",
            name="contratos_regime_jornada_check",
        ),
        sa.CheckConstraint(
            "status IN ('rascunho','ativo','suspenso','encerrado')", name="contratos_status_check"
        ),
        sa.CheckConstraint(
            "tipo IN ('clt','aprendiz','estagio','temporario','intermitente','avulso','autonomo','pj','socio','servidor')",
            name="contratos_tipo_check",
        ),
        sa.CheckConstraint(
            "tipo_salario IN ('mensal','horista','diarista','semanal','comissionado','tarefa')",
            name="contratos_tipo_salario_check",
        ),
        sa.CheckConstraint(
            "(controle_jornada = TRUE  AND dispensa_controle_motivo IS NULL) OR (controle_jornada = FALSE AND dispensa_controle_motivo IS NOT NULL)",
            name="ck_contratos_dispensa",
        ),
        sa.CheckConstraint(
            "carga_horaria_mensal_minutos IS NULL OR carga_horaria_mensal_minutos >= 0",
            name="contratos_carga_horaria_mensal_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_horaria_semanal_minutos IS NULL OR carga_horaria_semanal_minutos BETWEEN 0 AND 4200",
            name="contratos_carga_horaria_semanal_minutos_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_contratos_periodo"
        ),
        sa.CheckConstraint(
            "experiencia_dias IS NULL OR experiencia_dias BETWEEN 0 AND 90",
            name="contratos_experiencia_dias_check",
        ),
        sa.CheckConstraint("salario IS NULL OR salario >= 0", name="contratos_salario_check"),
        sa.ForeignKeyConstraint(
            ["cargo_id"], ["cargos.id"], name=op.f("contratos_cargo_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["centro_custo_id"],
            ["centros_custo.id"],
            name=op.f("contratos_centro_custo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("contratos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("contratos_departamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("contratos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("contratos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("contratos_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("contratos_pkey")),
        comment="Instrumento juridico entre colaborador e empresa: tipo de contratacao, cargo, remuneracao, carga contratada e vigencia.",
    )
    op.create_index(
        "ix_contratos_colaborador",
        "contratos",
        ["tenant_id", "colaborador_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_contratos_vigentes",
        "contratos",
        ["tenant_id", "empresa_id", "data_inicio", "data_fim"],
        unique=False,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_table(
        "dispositivos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=True),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("plataforma", sa.Text(), nullable=True),
        sa.Column("identificador", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=True),
        sa.Column("fabricante", sa.Text(), nullable=True),
        sa.Column("modelo", sa.Text(), nullable=True),
        sa.Column("versao_so", sa.Text(), nullable=True),
        sa.Column("versao_app", sa.Text(), nullable=True),
        sa.Column("chave_publica", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column(
            "attestation_status",
            sa.Text(),
            server_default=sa.text("'nao_verificado'"),
            nullable=False,
        ),
        sa.Column("attestation_verificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("root_detectado", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column(
            "emulador_detectado", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "modo_desenvolvedor", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("depuracao_usb", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("ultimo_acesso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_ip", postgresql.INET(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "attestation_status IN ('nao_verificado','aprovado','reprovado','indisponivel')",
            name="dispositivos_attestation_status_check",
        ),
        sa.CheckConstraint(
            "plataforma IN ('android','ios','web','linux','windows','macos','embarcado')",
            name="dispositivos_plataforma_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','ativo','bloqueado','revogado','substituido')",
            name="dispositivos_status_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('terminal','celular','tablet','navegador','totem','integracao')",
            name="dispositivos_tipo_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("dispositivos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("dispositivos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("dispositivos_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("dispositivos_pkey")),
        comment="Qualquer aparelho capaz de originar uma marcacao: terminal facial, celular, tablet de quiosque, navegador ou cliente de API.",
    )
    op.create_index(
        "ix_dispositivos_empresa",
        "dispositivos",
        ["tenant_id", "empresa_id", "tipo"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index("ix_dispositivos_status", "dispositivos", ["tenant_id", "status"], unique=False)
    op.create_index(
        "uq_dispositivos_identificador",
        "dispositivos",
        ["tenant_id", "identificador"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "equipes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("gestor_colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("cor", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'", name="equipes_cor_check"),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("equipes_departamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("equipes_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gestor_colaborador_id"],
            ["colaboradores.id"],
            name=op.f("equipes_gestor_colaborador_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("equipes_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("equipes_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("equipes_pkey")),
        comment="Agrupamento operacional de colaboradores para escala, cobertura de turno e visao do gestor. Ortogonal ao departamento.",
    )
    op.create_index(
        "ix_equipes_gestor", "equipes", ["tenant_id", "gestor_colaborador_id"], unique=False
    )
    op.create_index(
        "uq_equipes_codigo",
        "equipes",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "escalas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("dias_ciclo", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('5x2','6x1','4x2','12x36','espanhola','rotativa','personalizada')",
            name="escalas_tipo_check",
        ),
        sa.CheckConstraint("dias_ciclo BETWEEN 1 AND 366", name="escalas_dias_ciclo_check"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("escalas_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["jornada_id"],
            ["jornadas.id"],
            name=op.f("escalas_jornada_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("escalas_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("escalas_pkey")),
        comment="Padrao ciclico de trabalho e folga. O ciclo se repete indefinidamente a partir de data_referencia; qualquer data e resolvida por aritmetica modular, sem materializar o calendario.",
    )
    op.create_index(
        "uq_escalas_codigo",
        "escalas",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "fechamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("periodo_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("escopo", sa.Text(), server_default=sa.text("'empresa'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'em_andamento'"), nullable=False),
        sa.Column("total_colaboradores", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_ocorrencias", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_pendencias", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "hash_conteudo",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("conferido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conferido_por", sa.Uuid(), nullable=True),
        sa.Column("fechado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fechado_por", sa.Uuid(), nullable=True),
        sa.Column("reaberto_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reaberto_por", sa.Uuid(), nullable=True),
        sa.Column("motivo_reabertura", sa.Text(), nullable=True),
        sa.Column("exportado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "escopo IN ('empresa','unidade','departamento','equipe','colaborador')",
            name="fechamentos_escopo_check",
        ),
        sa.CheckConstraint(
            "status IN ('em_andamento','conferido','fechado','reaberto','cancelado')",
            name="fechamentos_status_check",
        ),
        sa.CheckConstraint(
            "reaberto_em IS NULL OR (motivo_reabertura IS NOT NULL AND reaberto_por IS NOT NULL)",
            name="ck_fechamentos_reabertura",
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("fechamentos_departamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("fechamentos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
            name=op.f("fechamentos_periodo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fechamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("fechamentos_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("fechamentos_pkey")),
        comment="Trava do periodo para um escopo. Fechado, o dia nao recalcula. A reabertura e sempre nominal e justificada, garantido por CHECK.",
    )
    op.create_index(
        "ix_fechamentos_empresa",
        "fechamentos",
        ["tenant_id", "empresa_id", sa.literal_column("fechado_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_fechamentos_periodo", "fechamentos", ["tenant_id", "periodo_id", "status"], unique=False
    )
    op.create_table(
        "jornada_dias",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=False),
        sa.Column("dia_semana", sa.SmallInteger(), nullable=False),
        sa.Column("tipo_dia", sa.Text(), server_default=sa.text("'util'"), nullable=False),
        sa.Column("horario_id", sa.Uuid(), nullable=True),
        sa.Column("carga_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo_dia IN ('util','dsr','folga','compensado','facultativo')",
            name="jornada_dias_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "carga_minutos BETWEEN 0 AND 1440", name="jornada_dias_carga_minutos_check"
        ),
        sa.CheckConstraint("dia_semana BETWEEN 0 AND 6", name="jornada_dias_dia_semana_check"),
        sa.ForeignKeyConstraint(
            ["horario_id"],
            ["horarios.id"],
            name=op.f("jornada_dias_horario_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["jornada_id"],
            ["jornadas.id"],
            name=op.f("jornada_dias_jornada_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("jornada_dias_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("jornada_dias_pkey")),
        sa.UniqueConstraint("tenant_id", "jornada_id", "dia_semana", name="uq_jornada_dias"),
        comment="Desdobramento da jornada por dia da semana. Define o horario previsto e o tipo do dia em jornadas fixas e flexiveis.",
    )
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("evento", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prioridade", sa.Text(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("agendada_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enviada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entregue_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tentativas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("provedor", sa.Text(), nullable=True),
        sa.Column("provedor_mensagem_id", sa.Text(), nullable=True),
        sa.Column("entidade", sa.Text(), nullable=True),
        sa.Column("entidade_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('push','email','whatsapp','in_app','sms')", name="notificacoes_canal_check"
        ),
        sa.CheckConstraint(
            "prioridade IN ('baixa','normal','alta','critica')",
            name="notificacoes_prioridade_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','enviada','entregue','lida','falhou','descartada')",
            name="notificacoes_status_check",
        ),
        sa.CheckConstraint("tentativas >= 0", name="notificacoes_tentativas_check"),
        sa.CheckConstraint(
            "usuario_id IS NOT NULL OR colaborador_id IS NOT NULL",
            name="ck_notificacoes_destinatario",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("notificacoes_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("notificacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("notificacoes_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("notificacoes_pkey")),
        comment="Mensagem enviada ao usuario em qualquer canal. Uma linha por canal: o mesmo evento notificado por push e e-mail gera duas linhas.",
    )
    op.create_index(
        "ix_notificacoes_nao_lidas",
        "notificacoes",
        ["tenant_id", "usuario_id"],
        unique=False,
        postgresql_where=sa.text("canal = 'in_app' AND lida_em IS NULL"),
    )
    op.create_index(
        "ix_notificacoes_pendentes",
        "notificacoes",
        ["tenant_id", "status", "agendada_para"],
        unique=False,
        postgresql_where=sa.text("status = 'pendente'"),
    )
    op.create_index(
        "ix_notificacoes_usuario",
        "notificacoes",
        ["tenant_id", "usuario_id", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_table(
        "nsr_sequencias",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rep_p_id", sa.Uuid(), nullable=False),
        sa.Column("proximo_nsr", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "ultimo_nsr_emitido", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "ultimo_hash",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("ultima_emissao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "proximo_nsr = ultimo_nsr_emitido + 1", name="ck_nsr_sequencias_coerencia"
        ),
        sa.CheckConstraint("proximo_nsr >= 1", name="nsr_sequencias_proximo_nsr_check"),
        sa.CheckConstraint(
            "ultimo_nsr_emitido >= 0", name="nsr_sequencias_ultimo_nsr_emitido_check"
        ),
        sa.ForeignKeyConstraint(
            ["rep_p_id"],
            ["rep_ps.id"],
            name=op.f("nsr_sequencias_rep_p_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("nsr_sequencias_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("nsr_sequencias_pkey")),
        sa.UniqueConstraint("tenant_id", "rep_p_id", name="uq_nsr_sequencias"),
        comment="Alocador transacional do Numero Sequencial de Registro, um por REP-P. Nao usa SEQUENCE porque sequence nao volta atras em rollback e produziria lacunas, o que a Portaria proibe.",
    )
    op.create_table(
        "politicas_registro",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("canal", sa.Text(), nullable=True),
        sa.Column("exige_geocerca", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("exige_facial", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("exige_liveness", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "exige_attestation", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "exige_rede_permitida", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "limiar_facial",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("75"),
            nullable=False,
        ),
        sa.Column(
            "limiar_bloqueio", sa.SmallInteger(), server_default=sa.text("40"), nullable=False
        ),
        sa.Column(
            "limiar_revisao", sa.SmallInteger(), server_default=sa.text("70"), nullable=False
        ),
        sa.Column(
            "politica_modo_desenvolvedor",
            sa.Text(),
            server_default=sa.text("'bloquear'"),
            nullable=False,
        ),
        sa.Column("politica_root", sa.Text(), server_default=sa.text("'bloquear'"), nullable=False),
        sa.Column(
            "politica_mock_location",
            sa.Text(),
            server_default=sa.text("'bloquear'"),
            nullable=False,
        ),
        sa.Column(
            "politica_fora_geocerca",
            sa.Text(),
            server_default=sa.text("'sinalizar'"),
            nullable=False,
        ),
        sa.Column(
            "bloquear_vpn_proxy", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "exige_reautenticacao", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column("ttl_offline_horas", sa.Integer(), server_default=sa.text("72"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('terminal','mobile','web','totem','api')",
            name="politicas_registro_canal_check",
        ),
        sa.CheckConstraint(
            "politica_fora_geocerca IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_fora_geocerca_check",
        ),
        sa.CheckConstraint(
            "politica_mock_location IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_mock_location_check",
        ),
        sa.CheckConstraint(
            "politica_modo_desenvolvedor IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_modo_desenvolvedor_check",
        ),
        sa.CheckConstraint(
            "politica_root IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_root_check",
        ),
        sa.CheckConstraint(
            "limiar_bloqueio BETWEEN 0 AND 100", name="politicas_registro_limiar_bloqueio_check"
        ),
        sa.CheckConstraint(
            "limiar_facial BETWEEN 0 AND 100", name="politicas_registro_limiar_facial_check"
        ),
        sa.CheckConstraint(
            "limiar_revisao >= limiar_bloqueio", name="ck_politicas_registro_limiares"
        ),
        sa.CheckConstraint(
            "limiar_revisao BETWEEN 0 AND 100", name="politicas_registro_limiar_revisao_check"
        ),
        sa.CheckConstraint(
            "ttl_offline_horas > 0", name="politicas_registro_ttl_offline_horas_check"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("politicas_registro_empresa_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("politicas_registro_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("politicas_registro_unidade_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("politicas_registro_pkey")),
        comment="Politica antifraude aplicada ao registro de ponto, por empresa, unidade e canal. Guarda a decisao configuravel entre bloquear, sinalizar e permitir.",
    )
    op.create_index(
        "uq_politicas_registro",
        "politicas_registro",
        [
            "tenant_id",
            "empresa_id",
            sa.literal_column("COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.literal_column("COALESCE(canal, '*')"),
        ],
        unique=True,
    )
    op.create_table(
        "redes_permitidas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("cidr", postgresql.CIDR(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("canal", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('web','mobile','totem','api','terminal')",
            name="redes_permitidas_canal_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("redes_permitidas_empresa_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("redes_permitidas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("redes_permitidas_unidade_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("redes_permitidas_pkey")),
        comment="Allowlist de faixas CIDR (IPv4 e IPv6) autorizadas a registrar ponto. Escopo por empresa e, opcionalmente, por unidade e por canal.",
    )
    op.create_index(
        "ix_redes_permitidas_lookup",
        "redes_permitidas",
        ["tenant_id", "empresa_id", "unidade_id"],
        unique=False,
        postgresql_where=sa.text("ativo"),
    )
    op.create_index(
        "uq_redes_permitidas",
        "redes_permitidas",
        [
            "tenant_id",
            "empresa_id",
            sa.literal_column("COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.literal_column("COALESCE(canal, '*')"),
            "cidr",
        ],
        unique=True,
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("sessao_id", sa.Uuid(), nullable=False),
        sa.Column("familia_id", sa.Uuid(), nullable=False),
        sa.Column("antecessor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "token_hash",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "emitido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revogacao", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "motivo_revogacao IN ('rotacao','logout','reuso_detectado','expiracao','revogacao_admin','troca_senha')",
            name="refresh_tokens_motivo_revogacao_check",
        ),
        sa.ForeignKeyConstraint(
            ["antecessor_id"],
            ["refresh_tokens.id"],
            name=op.f("refresh_tokens_antecessor_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sessao_id"],
            ["sessoes.id"],
            name=op.f("refresh_tokens_sessao_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("refresh_tokens_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("refresh_tokens_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("refresh_tokens_pkey")),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_refresh_tokens_hash"),
        comment="Refresh tokens com rotacao. Reapresentar um token ja usado invalida a familia inteira (deteccao de reuso).",
    )
    op.create_index(
        "ix_refresh_tokens_familia", "refresh_tokens", ["tenant_id", "familia_id"], unique=False
    )
    op.create_index(
        "ix_refresh_tokens_usuario",
        "refresh_tokens",
        ["tenant_id", "usuario_id", sa.literal_column("emitido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_validos",
        "refresh_tokens",
        ["tenant_id", "expira_em"],
        unique=False,
        postgresql_where=sa.text("revogado_em IS NULL AND usado_em IS NULL"),
    )
    op.create_table(
        "relatorio_execucoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("relatorio_definicao_id", sa.Uuid(), nullable=False),
        sa.Column("agendamento_id", sa.Uuid(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column(
            "parametros",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("formato", sa.Text(), server_default=sa.text("'csv'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'enfileirado'"), nullable=False),
        sa.Column("progresso", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_linhas", sa.BigInteger(), nullable=True),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "formato IN ('csv','xlsx','pdf','json')", name="relatorio_execucoes_formato_check"
        ),
        sa.CheckConstraint(
            "status IN ('enfileirado','processando','concluido','falhou','cancelado','expirado')",
            name="relatorio_execucoes_status_check",
        ),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0", name="relatorio_execucoes_duracao_ms_check"
        ),
        sa.CheckConstraint(
            "progresso BETWEEN 0 AND 100", name="relatorio_execucoes_progresso_check"
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0",
            name="relatorio_execucoes_tamanho_bytes_check",
        ),
        sa.ForeignKeyConstraint(
            ["agendamento_id"],
            ["relatorio_agendamentos.id"],
            name=op.f("relatorio_execucoes_agendamento_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["relatorio_definicao_id"],
            ["relatorio_definicoes.id"],
            name=op.f("relatorio_execucoes_relatorio_definicao_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("relatorio_execucoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("relatorio_execucoes_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("relatorio_execucoes_pkey")),
        comment="Execucao de um relatorio, sincrona ou assincrona. Guarda parametros, progresso e o artefato gerado, com expiracao.",
    )
    op.create_index(
        "ix_relatorio_execucoes_fila",
        "relatorio_execucoes",
        ["tenant_id", "status", "criado_em"],
        unique=False,
        postgresql_where=sa.text("status IN ('enfileirado','processando')"),
    )
    op.create_index(
        "ix_relatorio_execucoes_usuario",
        "relatorio_execucoes",
        ["tenant_id", "usuario_id", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_table(
        "solicitacoes_titular",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("protocolo", sa.Text(), nullable=False),
        sa.Column("requerente_nome", sa.Text(), nullable=False),
        sa.Column(
            "requerente_cpf",
            postgresql.DOMAIN("dom_cpf", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "requerente_email",
            postgresql.DOMAIN("dom_email", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'recebida'"), nullable=False),
        sa.Column("prazo_em", sa.Date(), nullable=True),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("resposta_ref", sa.Text(), nullable=True),
        sa.Column("respondido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respondido_por", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('recebida','em_analise','atendida','parcialmente_atendida','recusada','cancelada')",
            name="solicitacoes_titular_status_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('acesso','correcao','portabilidade','eliminacao','anonimizacao','revogacao_consentimento','informacao_compartilhamento','oposicao')",
            name="solicitacoes_titular_tipo_check",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("solicitacoes_titular_colaborador_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("solicitacoes_titular_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("solicitacoes_titular_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("solicitacoes_titular_pkey")),
        sa.UniqueConstraint("tenant_id", "protocolo", name="uq_solicitacoes_titular_protocolo"),
        comment="Pedido de titular de dados previsto na LGPD. Guarda protocolo, prazo de resposta e o arquivo entregue.",
    )
    op.create_index(
        "ix_solicitacoes_titular_status",
        "solicitacoes_titular",
        ["tenant_id", "status", "prazo_em"],
        unique=False,
    )
    op.create_table(
        "turnos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("horario_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'diurno'"), nullable=False),
        sa.Column("sequencia", sa.Integer(), nullable=True),
        sa.Column("cor", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'", name="turnos_cor_check"),
        sa.CheckConstraint(
            "tipo IN ('diurno','noturno','misto','folga','dsr','sobreaviso','prontidao')",
            name="turnos_tipo_check",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("turnos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["horario_id"],
            ["horarios.id"],
            name=op.f("turnos_horario_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("turnos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("turnos_pkey")),
        comment="Turno nomeado, com o horario que o materializa. Em regime de revezamento, a sequencia define a ordem de rodizio.",
    )
    op.create_index(
        "uq_turnos_codigo",
        "turnos",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "unidade_feriado_conjuntos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("feriado_conjunto_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["feriado_conjunto_id"],
            ["feriado_conjuntos.id"],
            name=op.f("unidade_feriado_conjuntos_feriado_conjunto_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("unidade_feriado_conjuntos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("unidade_feriado_conjuntos_unidade_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("unidade_feriado_conjuntos_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "unidade_id", "feriado_conjunto_id", name="uq_unidade_feriado_conjuntos"
        ),
        comment="Associacao N para N entre unidade e conjuntos de feriados. Uma unidade precisa somar o calendario nacional, o estadual e o municipal.",
    )
    op.create_table(
        "usuario_perfis",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("escopo_tipo", sa.Text(), server_default=sa.text("'tenant'"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=True),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("equipe_id", sa.Uuid(), nullable=True),
        sa.Column(
            "incluir_subordinados", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "vigencia_inicio", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(escopo_tipo = 'empresa'      AND empresa_id      IS NOT NULL) OR (escopo_tipo = 'unidade'      AND unidade_id      IS NOT NULL) OR (escopo_tipo = 'departamento' AND departamento_id IS NOT NULL) OR (escopo_tipo = 'equipe'       AND equipe_id       IS NOT NULL) OR (escopo_tipo IN ('tenant','proprio'))",
            name="ck_usuario_perfis_escopo",
        ),
        sa.CheckConstraint(
            "escopo_tipo IN ('tenant','empresa','unidade','departamento','equipe','proprio')",
            name="usuario_perfis_escopo_tipo_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_usuario_perfis_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("usuario_perfis_departamento_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("usuario_perfis_empresa_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["perfil_id"],
            ["perfis.id"],
            name=op.f("usuario_perfis_perfil_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("usuario_perfis_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("usuario_perfis_unidade_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("usuario_perfis_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("usuario_perfis_pkey")),
        comment="Atribuicao de perfil a usuario COM ESCOPO. O mesmo usuario pode ser gestor de uma unidade e colaborador comum no resto da empresa.",
    )
    op.create_index(
        "ix_usuario_perfis_usuario", "usuario_perfis", ["tenant_id", "usuario_id"], unique=False
    )
    op.create_index(
        "ix_usuario_perfis_vigentes",
        "usuario_perfis",
        ["tenant_id", "usuario_id", "vigencia_inicio", "vigencia_fim"],
        unique=False,
    )
    op.create_index(
        "uq_usuario_perfis",
        "usuario_perfis",
        [
            "tenant_id",
            "usuario_id",
            "perfil_id",
            "escopo_tipo",
            sa.literal_column(
                "COALESCE(empresa_id,      '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.literal_column(
                "COALESCE(unidade_id,      '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.literal_column(
                "COALESCE(departamento_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.literal_column(
                "COALESCE(equipe_id,       '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            "vigencia_inicio",
        ],
        unique=True,
    )
    op.create_table(
        "webhook_entregas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("webhook_id", sa.Uuid(), nullable=False),
        sa.Column("evento", sa.Text(), nullable=False),
        sa.Column("evento_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assinatura", sa.Text(), nullable=True),
        sa.Column("tentativa", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente','enviando','sucesso','falha','dlq','cancelada')",
            name="webhook_entregas_status_check",
        ),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0", name="webhook_entregas_duracao_ms_check"
        ),
        sa.CheckConstraint("tentativa >= 1", name="webhook_entregas_tentativa_check"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("webhook_entregas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["webhooks.id"],
            name=op.f("webhook_entregas_webhook_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("webhook_entregas_pkey")),
        comment="Tentativa de entrega de um evento. Retentativa exponencial ate max_tentativas; esgotado, vai para dlq e pode ser reenviada manualmente.",
    )
    op.create_index(
        "ix_webhook_entregas_dlq",
        "webhook_entregas",
        ["tenant_id", sa.literal_column("criado_em DESC")],
        unique=False,
        postgresql_where=sa.text("status = 'dlq'"),
    )
    op.create_index(
        "ix_webhook_entregas_pendentes",
        "webhook_entregas",
        ["tenant_id", "proxima_tentativa_em"],
        unique=False,
        postgresql_where=sa.text("status IN ('pendente','falha')"),
    )
    op.create_index(
        "ix_webhook_entregas_webhook",
        "webhook_entregas",
        ["tenant_id", "webhook_id", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_table(
        "biometria_templates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("biometria_id", sa.Uuid(), nullable=False),
        sa.Column("versao_modelo", sa.Text(), nullable=False),
        sa.Column("provedor", sa.Text(), server_default=sa.text("'facial-svc'"), nullable=False),
        sa.Column("dimensao", sa.Integer(), nullable=True),
        sa.Column("template_cifrado", postgresql.BYTEA(), nullable=False),
        sa.Column("iv", postgresql.BYTEA(), nullable=False),
        sa.Column("tag_autenticacao", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "algoritmo_cifra", sa.Text(), server_default=sa.text("'AES-256-GCM'"), nullable=False
        ),
        sa.Column("chave_id", sa.Text(), nullable=False),
        sa.Column(
            "hash_template",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "gerado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "algoritmo_cifra IN ('AES-256-GCM','AES-256-CBC','ChaCha20-Poly1305')",
            name="biometria_templates_algoritmo_cifra_check",
        ),
        sa.CheckConstraint(
            "dimensao IS NULL OR dimensao > 0", name="biometria_templates_dimensao_check"
        ),
        sa.ForeignKeyConstraint(
            ["biometria_id"],
            ["biometrias.id"],
            name=op.f("biometria_templates_biometria_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("biometria_templates_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("biometria_templates_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "biometria_id", "versao_modelo", name="uq_biometria_templates_versao"
        ),
        comment="Vetor biometrico CIFRADO. Dado pessoal sensivel (LGPD art. 5, II). Versionado por modelo. A role ponto_suporte NAO tem SELECT nesta tabela.",
    )
    op.create_index(
        "ix_biometria_templates_biometria",
        "biometria_templates",
        ["tenant_id", "biometria_id"],
        unique=False,
        postgresql_where=sa.text("ativo"),
    )
    op.create_index(
        "ix_biometria_templates_modelo",
        "biometria_templates",
        ["tenant_id", "versao_modelo"],
        unique=False,
    )
    op.create_table(
        "dispositivo_vinculos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column(
            "vinculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("aprovado_por", sa.Uuid(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revogacao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente','ativo','revogado','recusado')",
            name="dispositivo_vinculos_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("dispositivo_vinculos_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dispositivo_id"],
            ["dispositivos.id"],
            name=op.f("dispositivo_vinculos_dispositivo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("dispositivo_vinculos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("dispositivo_vinculos_pkey")),
        comment="Vinculo entre aparelho pessoal e colaborador. Um unico dispositivo ativo por colaborador; a troca exige aprovacao do RH e fica registrada.",
    )
    op.create_index(
        "ix_dispositivo_vinculos_dispositivo",
        "dispositivo_vinculos",
        ["tenant_id", "dispositivo_id"],
        unique=False,
    )
    op.create_index(
        "uq_dispositivo_vinculos_ativo",
        "dispositivo_vinculos",
        ["tenant_id", "colaborador_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_table(
        "equipe_membros",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("equipe_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("papel", sa.Text(), server_default=sa.text("'membro'"), nullable=False),
        sa.Column(
            "vigencia_inicio", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("equipe_id"), "="),
            (sa.column("colaborador_id"), "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            using="gist",
            name="ex_equipe_membros_sobreposicao",
        ),
        sa.CheckConstraint(
            "papel IN ('membro','lider','substituto')", name="equipe_membros_papel_check"
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_equipe_membros_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("equipe_membros_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["equipe_id"],
            ["equipes.id"],
            name=op.f("equipe_membros_equipe_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("equipe_membros_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("equipe_membros_pkey")),
        comment="Participacao datada de um colaborador em uma equipe.",
    )
    op.create_index(
        "ix_equipe_membros_colaborador",
        "equipe_membros",
        ["tenant_id", "colaborador_id"],
        unique=False,
    )
    op.create_index(
        "ix_equipe_membros_equipe",
        "equipe_membros",
        ["tenant_id", "equipe_id", "vigencia_inicio"],
        unique=False,
    )
    op.create_table(
        "escala_ciclos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("escala_id", sa.Uuid(), nullable=False),
        sa.Column("posicao", sa.Integer(), nullable=False),
        sa.Column("turno_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_dia", sa.Text(), server_default=sa.text("'trabalho'"), nullable=False),
        sa.Column("carga_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo_dia IN ('trabalho','folga','dsr','compensado')",
            name="escala_ciclos_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "carga_minutos BETWEEN 0 AND 1440", name="escala_ciclos_carga_minutos_check"
        ),
        sa.CheckConstraint("posicao >= 1", name="escala_ciclos_posicao_check"),
        sa.ForeignKeyConstraint(
            ["escala_id"],
            ["escalas.id"],
            name=op.f("escala_ciclos_escala_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("escala_ciclos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turno_id"],
            ["turnos.id"],
            name=op.f("escala_ciclos_turno_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("escala_ciclos_pkey")),
        sa.UniqueConstraint("tenant_id", "escala_id", "posicao", name="uq_escala_ciclos"),
        comment="Uma linha por posicao do ciclo da escala. Em 12x36 sao duas linhas: posicao 1 trabalho de 12 horas, posicao 2 folga.",
    )
    op.create_table(
        "terminais",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("rep_p_id", sa.Uuid(), nullable=True),
        sa.Column("fabricante", sa.Text(), server_default=sa.text("'control_id'"), nullable=False),
        sa.Column("modelo", sa.Text(), nullable=True),
        sa.Column("numero_serie", sa.Text(), nullable=False),
        sa.Column("endereco_ip", postgresql.INET(), nullable=True),
        sa.Column("porta", sa.Integer(), nullable=True),
        sa.Column("mac", sa.Text(), nullable=True),
        sa.Column("modo_comunicacao", sa.Text(), server_default=sa.text("'push'"), nullable=False),
        sa.Column("usuario_api", sa.Text(), nullable=True),
        sa.Column("senha_api_cifrada", postgresql.BYTEA(), nullable=True),
        sa.Column("chave_id", sa.Text(), nullable=True),
        sa.Column("token_push", sa.Text(), nullable=True),
        sa.Column("capacidade_faces", sa.Integer(), nullable=True),
        sa.Column(
            "ultimo_log_externo_id", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("ultima_sincronizacao_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_contato_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "intervalo_push_segundos", sa.Integer(), server_default=sa.text("30"), nullable=False
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "fabricante IN ('control_id','henry','topdata','madis','dimep','inner','outro')",
            name="terminais_fabricante_check",
        ),
        sa.CheckConstraint(
            "modo_comunicacao IN ('push','monitor','polling','direto')",
            name="terminais_modo_comunicacao_check",
        ),
        sa.CheckConstraint(
            "status IN ('ativo','inativo','manutencao','desativado')", name="terminais_status_check"
        ),
        sa.CheckConstraint(
            "intervalo_push_segundos > 0", name="terminais_intervalo_push_segundos_check"
        ),
        sa.CheckConstraint(
            "porta IS NULL OR porta BETWEEN 1 AND 65535", name="terminais_porta_check"
        ),
        sa.ForeignKeyConstraint(
            ["dispositivo_id"],
            ["dispositivos.id"],
            name=op.f("terminais_dispositivo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("terminais_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("terminais_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("terminais_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("terminais_pkey")),
        comment="Coletor fisico de marcacao, tipicamente um Control iD iDFace. O terminal NAO e o REP-P: ele identifica a pessoa e produz um access_log.",
    )
    op.create_index(
        "ix_terminais_contato",
        "terminais",
        ["tenant_id", "ultimo_contato_em"],
        unique=False,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_index(
        "ix_terminais_unidade",
        "terminais",
        ["tenant_id", "unidade_id"],
        unique=False,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_index(
        "uq_terminais_dispositivo",
        "terminais",
        ["tenant_id", "dispositivo_id"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "uq_terminais_serie",
        "terminais",
        ["tenant_id", "numero_serie"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "vinculos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("contrato_id", sa.Uuid(), nullable=True),
        sa.Column("matricula_esocial", sa.Text(), nullable=False),
        sa.Column("categoria_esocial", sa.SmallInteger(), nullable=True),
        sa.Column("tipo_vinculo", sa.Text(), server_default=sa.text("'empregado'"), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("centro_custo_id", sa.Uuid(), nullable=True),
        sa.Column("cargo_id", sa.Uuid(), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("motivo_desligamento", sa.Text(), nullable=True),
        sa.Column("principal", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("apura_ponto", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ativo'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("colaborador_id"), "="),
            (sa.column("empresa_id"), "="),
            (sa.text("daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]')"), "&&"),
            where=sa.text("excluido_em IS NULL AND status <> 'encerrado'"),
            using="gist",
            name="ex_vinculos_sobreposicao",
        ),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','encerrado')", name="vinculos_status_check"
        ),
        sa.CheckConstraint(
            "tipo_vinculo IN ('empregado','estagiario','aprendiz','temporario','avulso','autonomo','cooperado','diretor','servidor')",
            name="vinculos_tipo_vinculo_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_vinculos_periodo"
        ),
        sa.ForeignKeyConstraint(
            ["cargo_id"], ["cargos.id"], name=op.f("vinculos_cargo_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["centro_custo_id"],
            ["centros_custo.id"],
            name=op.f("vinculos_centro_custo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("vinculos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contrato_id"],
            ["contratos.id"],
            name=op.f("vinculos_contrato_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("vinculos_departamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("vinculos_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("vinculos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("vinculos_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("vinculos_pkey")),
        comment="A RELACAO DE TRABALHO efetiva, na granularidade que o AEJ e o eSocial exigem. Toda apuracao pendura em um vinculo, nao no colaborador.",
    )
    op.create_index(
        "ix_vinculos_apuracao",
        "vinculos",
        ["tenant_id", "empresa_id", "status", "data_inicio", "data_fim"],
        unique=False,
        postgresql_where=sa.text("apura_ponto"),
    )
    op.create_index(
        "ix_vinculos_colaborador",
        "vinculos",
        ["tenant_id", "colaborador_id"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_vinculos_unidade",
        "vinculos",
        ["tenant_id", "unidade_id"],
        unique=False,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_index(
        "uq_vinculos_matricula_esocial",
        "vinculos",
        ["tenant_id", "empresa_id", "matricula_esocial"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "documentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.Column("empresa_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("data_emissao", sa.Date(), nullable=True),
        sa.Column("data_validade", sa.Date(), nullable=True),
        sa.Column("confidencial", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('rg','cpf','ctps','comprovante_residencia','atestado','contrato','acordo_banco_horas','acordo_compensacao','termo_consentimento','certificado','aso','advertencia','rescisao','outro')",
            name="documentos_tipo_check",
        ),
        sa.CheckConstraint(
            "colaborador_id IS NOT NULL OR vinculo_id IS NOT NULL OR empresa_id IS NOT NULL",
            name="ck_documentos_alvo",
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0", name="documentos_tamanho_bytes_check"
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("documentos_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("documentos_empresa_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("documentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("documentos_vinculo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("documentos_pkey")),
        comment="Documentos digitalizados de pessoas, vinculos e empresas. O binario fica no MinIO; aqui ficam metadados, hash e classificacao de confidencialidade.",
    )
    op.create_index(
        "ix_documentos_colaborador",
        "documentos",
        ["tenant_id", "colaborador_id", "tipo"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_documentos_validade",
        "documentos",
        ["tenant_id", "data_validade"],
        unique=False,
        postgresql_where=sa.text("data_validade IS NOT NULL AND excluido_em IS NULL"),
    )
    op.create_table(
        "escala_atribuicoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("escala_id", sa.Uuid(), nullable=False),
        sa.Column("posicao_inicial", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("vigencia_inicio", sa.Date(), nullable=False),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("vinculo_id"), "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            using="gist",
            name="ex_escala_atribuicoes_sobreposicao",
        ),
        sa.CheckConstraint("posicao_inicial >= 1", name="escala_atribuicoes_posicao_inicial_check"),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_escala_atribuicoes_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["escala_id"],
            ["escalas.id"],
            name=op.f("escala_atribuicoes_escala_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("escala_atribuicoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("escala_atribuicoes_vinculo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("escala_atribuicoes_pkey")),
        comment="Atribuicao datada de uma escala a um vinculo. Um vinculo tem no maximo uma escala vigente por data, garantido por constraint de exclusao.",
    )
    op.create_table(
        "espelhos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("periodo_id", sa.Uuid(), nullable=False),
        sa.Column("fechamento_id", sa.Uuid(), nullable=True),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("versao", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tipo", sa.Text(), server_default=sa.text("'previo'"), nullable=False),
        sa.Column("conteudo", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "total_previsto_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_trabalhado_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_extras_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_faltas_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_noturno_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("saldo_banco_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "gerado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("gerado_por", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("tipo IN ('previo','oficial','retificado')", name="espelhos_tipo_check"),
        sa.CheckConstraint("versao >= 1", name="espelhos_versao_check"),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("espelhos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fechamento_id"],
            ["fechamentos.id"],
            name=op.f("espelhos_fechamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
            name=op.f("espelhos_periodo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("espelhos_tenant_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("espelhos_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("espelhos_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "periodo_id", "vinculo_id", "versao", name="uq_espelhos_versao"
        ),
        comment="Espelho de ponto do periodo para um vinculo. O tipo oficial e emitido no fechamento e e o documento que o colaborador assina.",
    )
    op.create_index(
        "ix_espelhos_colaborador",
        "espelhos",
        ["tenant_id", "colaborador_id", sa.literal_column("gerado_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_espelhos_fechamento",
        "espelhos",
        ["tenant_id", "fechamento_id"],
        unique=False,
        postgresql_where=sa.text("fechamento_id IS NOT NULL"),
    )
    op.create_table(
        "marcacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rep_p_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.Column("nsr", sa.BigInteger(), nullable=False),
        sa.Column("tipo_registro", sa.Text(), server_default=sa.text("'7'"), nullable=False),
        sa.Column("sentido_informado", sa.Text(), nullable=True),
        sa.Column(
            "cpf", postgresql.DOMAIN("dom_cpf", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column(
            "pis_nit", postgresql.DOMAIN("dom_pis", sa.TEXT(), create_type=False), nullable=True
        ),
        sa.Column("datahora_marcacao", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "datahora_gravacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("datahora_dispositivo", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fuso_horario",
            postgresql.DOMAIN("dom_fuso", sa.TEXT(), create_type=False),
            server_default=sa.text("'America/Sao_Paulo'"),
            nullable=False,
        ),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=True),
        sa.Column("terminal_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("log_externo_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("origem_importacao_id", sa.Uuid(), nullable=True),
        sa.Column("crc16", sa.Integer(), nullable=False),
        sa.Column(
            "hash_anterior",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "hash_registro",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("linha_afd", sa.Text(), nullable=True),
        sa.Column(
            "coletada_offline", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('terminal','mobile','web','totem','api','importacao')",
            name="marcacoes_canal_check",
        ),
        sa.CheckConstraint(
            "sentido_informado IN ('entrada','saida','indefinido')",
            name="marcacoes_sentido_informado_check",
        ),
        sa.CheckConstraint(
            "tipo_registro IN ('2','3','4','5','6','7','9')", name="marcacoes_tipo_registro_check"
        ),
        sa.CheckConstraint("crc16 BETWEEN 0 AND 65535", name="marcacoes_crc16_check"),
        sa.CheckConstraint("nsr >= 1", name="marcacoes_nsr_check"),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("marcacoes_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispositivo_id"],
            ["dispositivos.id"],
            name=op.f("marcacoes_dispositivo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("marcacoes_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rep_p_id"], ["rep_ps.id"], name=op.f("marcacoes_rep_p_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("marcacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["terminal_id"],
            ["terminais.id"],
            name=op.f("marcacoes_terminal_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("marcacoes_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("marcacoes_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", "datahora_marcacao", name=op.f("marcacoes_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "rep_p_id", "nsr", "datahora_marcacao", name="uq_marcacoes_nsr"
        ),
        comment="Registro de ponto. APPEND-ONLY e PARTICIONADA POR MES em datahora_marcacao. Nunca sofre UPDATE nem DELETE: gatilhos abortam ambos. Toda correcao acontece em tratamentos, sem tocar aqui.",
        postgresql_partition_by="RANGE (datahora_marcacao)",
    )
    op.create_index(
        "ix_marcacoes_colaborador_data",
        "marcacoes",
        ["tenant_id", "colaborador_id", sa.literal_column("datahora_marcacao DESC")],
        unique=False,
    )
    op.create_index(
        "ix_marcacoes_cpf", "marcacoes", ["tenant_id", "cpf", "datahora_marcacao"], unique=False
    )
    op.create_index(
        "ix_marcacoes_empresa_data",
        "marcacoes",
        ["tenant_id", "empresa_id", "datahora_marcacao"],
        unique=False,
    )
    op.create_index(
        "ix_marcacoes_gravacao", "marcacoes", ["tenant_id", "datahora_gravacao"], unique=False
    )
    op.create_index(
        "ix_marcacoes_idem_dispositivo",
        "marcacoes",
        ["tenant_id", "dispositivo_id", "log_externo_id"],
        unique=False,
        postgresql_where=sa.text("log_externo_id IS NOT NULL"),
    )
    op.create_index(
        "ix_marcacoes_idem_external",
        "marcacoes",
        ["tenant_id", "canal", "external_id"],
        unique=False,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "ix_marcacoes_offline",
        "marcacoes",
        ["tenant_id", "datahora_marcacao"],
        unique=False,
        postgresql_where=sa.text("coletada_offline"),
    )
    op.create_index(
        "ix_marcacoes_rep_nsr", "marcacoes", ["tenant_id", "rep_p_id", "nsr"], unique=False
    )
    op.create_index(
        "ix_marcacoes_vinculo_data",
        "marcacoes",
        ["tenant_id", "vinculo_id", "datahora_marcacao"],
        unique=False,
    )
    op.create_table(
        "solicitacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_solicitacao_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.Column("solicitante_usuario_id", sa.Uuid(), nullable=True),
        sa.Column("protocolo", sa.Text(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("etapa_atual", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("prazo_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('rascunho','pendente','em_aprovacao','aprovada','reprovada','cancelada','expirada')",
            name="solicitacoes_status_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_inicio IS NULL OR data_fim >= data_inicio",
            name="ck_solicitacoes_periodo",
        ),
        sa.CheckConstraint("etapa_atual >= 1", name="solicitacoes_etapa_atual_check"),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("solicitacoes_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["solicitante_usuario_id"],
            ["usuarios.id"],
            name=op.f("solicitacoes_solicitante_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("solicitacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_solicitacao_id"],
            ["tipos_solicitacao.id"],
            name=op.f("solicitacoes_tipo_solicitacao_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("solicitacoes_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("solicitacoes_pkey")),
        sa.UniqueConstraint("tenant_id", "protocolo", name="uq_solicitacoes_protocolo"),
        comment="Pedido aberto no workflow. Percorre a cadeia definida no tipo e, quando aprovado, materializa um tratamento ou um afastamento.",
    )
    op.create_index(
        "ix_solicitacoes_colaborador",
        "solicitacoes",
        ["tenant_id", "colaborador_id", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_solicitacoes_data", "solicitacoes", ["tenant_id", "data_referencia"], unique=False
    )
    op.create_index(
        "ix_solicitacoes_pendentes",
        "solicitacoes",
        ["tenant_id", "status", "prazo_em"],
        unique=False,
        postgresql_where=sa.text("status IN ('pendente','em_aprovacao')"),
    )
    op.create_table(
        "terminal_saude",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("terminal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "verificado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("latencia_ms", sa.Integer(), nullable=True),
        sa.Column("firmware", sa.Text(), nullable=True),
        sa.Column("faces_cadastradas", sa.Integer(), nullable=True),
        sa.Column("logs_pendentes", sa.Integer(), nullable=True),
        sa.Column("memoria_livre_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("temperatura", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("alarme", sa.Text(), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "latencia_ms IS NULL OR latencia_ms >= 0", name="terminal_saude_latencia_ms_check"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("terminal_saude_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["terminal_id"],
            ["terminais.id"],
            name=op.f("terminal_saude_terminal_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("terminal_saude_pkey")),
        comment="Serie temporal de saude dos coletores. Append-only: cada verificacao gera uma linha nova, nunca atualiza a anterior.",
    )
    op.create_index(
        "ix_terminal_saude_offline",
        "terminal_saude",
        ["tenant_id", sa.literal_column("verificado_em DESC")],
        unique=False,
        postgresql_where=sa.text("NOT online"),
    )
    op.create_index(
        "ix_terminal_saude_terminal",
        "terminal_saude",
        ["tenant_id", "terminal_id", sa.literal_column("verificado_em DESC")],
        unique=False,
    )
    op.create_table(
        "vinculo_jornadas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=False),
        sa.Column("vigencia_inicio", sa.Date(), nullable=False),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("vinculo_id"), "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            using="gist",
            name="ex_vinculo_jornadas_sobreposicao",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_vinculo_jornadas_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["jornada_id"],
            ["jornadas.id"],
            name=op.f("vinculo_jornadas_jornada_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("vinculo_jornadas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("vinculo_jornadas_vinculo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("vinculo_jornadas_pkey")),
        comment="Historico de jornada vigente por vinculo. Sem ela nao ha como trocar a jornada no meio do mes preservando a apuracao anterior.",
    )
    op.create_index(
        "ix_vinculo_jornadas_resolucao",
        "vinculo_jornadas",
        ["tenant_id", "vinculo_id", sa.literal_column("vigencia_inicio DESC")],
        unique=False,
    )
    op.create_table(
        "afastamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_afastamento_id", sa.Uuid(), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("periodo_parcial", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=True),
        sa.Column("hora_fim", sa.Time(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("cid", sa.Text(), nullable=True),
        sa.Column("dias_previstos", sa.Integer(), nullable=True),
        sa.Column("documento_id", sa.Uuid(), nullable=True),
        sa.Column("solicitacao_id", sa.Uuid(), nullable=True),
        sa.Column("origem", sa.Text(), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'aprovado'"), nullable=False),
        sa.Column("aprovado_por", sa.Uuid(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("colaborador_id"), "="),
            (sa.text("daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]')"), "&&"),
            where=sa.text(
                "status = 'aprovado' AND periodo_parcial = FALSE AND excluido_em IS NULL"
            ),
            using="gist",
            name="ex_afastamentos_sobreposicao",
        ),
        sa.CheckConstraint(
            "origem IN ('manual','solicitacao','integracao','importacao')",
            name="afastamentos_origem_check",
        ),
        sa.CheckConstraint(
            "status IN ('solicitado','aprovado','reprovado','cancelado','encerrado')",
            name="afastamentos_status_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_afastamentos_periodo"
        ),
        sa.CheckConstraint(
            "periodo_parcial = FALSE OR (hora_inicio IS NOT NULL AND hora_fim IS NOT NULL)",
            name="ck_afastamentos_parcial",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("afastamentos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos.id"],
            name=op.f("afastamentos_documento_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("afastamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_afastamento_id"],
            ["tipos_afastamento.id"],
            name=op.f("afastamentos_tipo_afastamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("afastamentos_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("afastamentos_pkey")),
        comment="Periodo de ausencia legitima do colaborador. Entra na apuracao como insumo (nao como marcacao) e e exportado no bloco de ausencias do AEJ.",
    )
    op.create_index(
        "ix_afastamentos_colaborador",
        "afastamentos",
        ["tenant_id", "colaborador_id", "data_inicio", "data_fim"],
        unique=False,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_index(
        "ix_afastamentos_tipo",
        "afastamentos",
        ["tenant_id", "tipo_afastamento_id", "data_inicio"],
        unique=False,
    )
    op.create_index(
        "ix_afastamentos_vinculo",
        "afastamentos",
        ["tenant_id", "vinculo_id", "data_inicio"],
        unique=False,
        postgresql_where=sa.text("status = 'aprovado'"),
    )
    op.create_table(
        "aprovacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("solicitacao_id", sa.Uuid(), nullable=False),
        sa.Column("etapa", sa.Integer(), nullable=False),
        sa.Column("papel", sa.Text(), server_default=sa.text("'gestor'"), nullable=False),
        sa.Column("aprovador_usuario_id", sa.Uuid(), nullable=True),
        sa.Column("aprovador_delegacao_id", sa.Uuid(), nullable=True),
        sa.Column("decisao", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("prazo_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalonado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "decisao IN ('pendente','aprovada','reprovada','delegada','expirada','cancelada')",
            name="aprovacoes_decisao_check",
        ),
        sa.CheckConstraint(
            "papel IN ('gestor','rh','diretoria','sistema')", name="aprovacoes_papel_check"
        ),
        sa.CheckConstraint("etapa >= 1", name="aprovacoes_etapa_check"),
        sa.ForeignKeyConstraint(
            ["aprovador_delegacao_id"],
            ["delegacoes.id"],
            name=op.f("aprovacoes_aprovador_delegacao_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["aprovador_usuario_id"],
            ["usuarios.id"],
            name=op.f("aprovacoes_aprovador_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacoes.id"],
            name=op.f("aprovacoes_solicitacao_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("aprovacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("aprovacoes_pkey")),
        comment="Uma linha por etapa da cadeia de uma solicitacao. E a prova de quem autorizou cada correcao de jornada.",
    )
    op.create_index(
        "ix_aprovacoes_pendentes",
        "aprovacoes",
        ["tenant_id", "aprovador_usuario_id", "decisao"],
        unique=False,
        postgresql_where=sa.text("decisao = 'pendente'"),
    )
    op.create_index(
        "uq_aprovacoes_etapa", "aprovacoes", ["tenant_id", "solicitacao_id", "etapa"], unique=True
    )
    op.create_table(
        "assinaturas_espelho",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("espelho_id", sa.Uuid(), nullable=False),
        sa.Column("signatario_tipo", sa.Text(), nullable=False),
        sa.Column("signatario_usuario_id", sa.Uuid(), nullable=True),
        sa.Column("signatario_colaborador_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metodo", sa.Text(), server_default=sa.text("'aceite_eletronico'"), nullable=False
        ),
        sa.Column(
            "hash_assinado",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("assinatura", postgresql.BYTEA(), nullable=True),
        sa.Column("certificado_ref", sa.Text(), nullable=True),
        sa.Column(
            "carimbo_tempo",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("geolocalizacao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("recusa_motivo", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "metodo IN ('aceite_eletronico','icp_brasil','biometria','senha','token_email')",
            name="assinaturas_espelho_metodo_check",
        ),
        sa.CheckConstraint(
            "signatario_tipo IN ('colaborador','gestor','rh','empregador')",
            name="assinaturas_espelho_signatario_tipo_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','assinado','recusado','expirado')",
            name="assinaturas_espelho_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["espelho_id"],
            ["espelhos.id"],
            name=op.f("assinaturas_espelho_espelho_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["signatario_colaborador_id"],
            ["colaboradores.id"],
            name=op.f("assinaturas_espelho_signatario_colaborador_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["signatario_usuario_id"],
            ["usuarios.id"],
            name=op.f("assinaturas_espelho_signatario_usuario_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("assinaturas_espelho_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("assinaturas_espelho_pkey")),
        comment="Aceite eletronico do espelho de ponto. Append-only: recusar e depois assinar gera duas linhas, preservando o historico.",
    )
    op.create_index(
        "ix_assinaturas_espelho_espelho",
        "assinaturas_espelho",
        ["tenant_id", "espelho_id"],
        unique=False,
    )
    op.create_index(
        "uq_assinaturas_espelho",
        "assinaturas_espelho",
        [
            "tenant_id",
            "espelho_id",
            "signatario_tipo",
            sa.literal_column(
                "COALESCE(signatario_colaborador_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
        ],
        unique=True,
        postgresql_where=sa.text("status = 'assinado'"),
    )
    op.create_table(
        "bh_politicas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("periodo_meses", sa.Integer(), nullable=False),
        sa.Column("metodo_consumo", sa.Text(), server_default=sa.text("'fifo'"), nullable=False),
        sa.Column(
            "fator_credito_padrao",
            sa.Numeric(precision=6, scale=4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "fator_debito_padrao",
            sa.Numeric(precision=6, scale=4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column("fatores_por_faixa", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("teto_positivo_minutos", sa.Integer(), nullable=True),
        sa.Column("teto_negativo_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "limite_diario_minutos", sa.Integer(), server_default=sa.text("120"), nullable=False
        ),
        sa.Column(
            "limite_jornada_diaria_minutos",
            sa.Integer(),
            server_default=sa.text("600"),
            nullable=False,
        ),
        sa.Column(
            "acao_vencimento", sa.Text(), server_default=sa.text("'quitar_folha'"), nullable=False
        ),
        sa.Column(
            "dias_pre_aviso",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{30,15,7}'"),
            nullable=False,
        ),
        sa.Column(
            "bloqueia_extra_no_teto", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "permite_saldo_negativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column("documento_acordo_id", sa.Uuid(), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=False),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluido_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(regime = 'individual' AND periodo_meses <= 6) OR (regime IN ('coletivo','convencao') AND periodo_meses <= 12) OR (regime = 'especial')",
            name="ck_bh_politicas_periodo_legal",
        ),
        sa.CheckConstraint(
            "acao_vencimento IN ('quitar_folha','expirar','prorrogar','manter')",
            name="bh_politicas_acao_vencimento_check",
        ),
        sa.CheckConstraint(
            "metodo_consumo IN ('fifo','lifo')", name="bh_politicas_metodo_consumo_check"
        ),
        sa.CheckConstraint(
            "regime IN ('individual','coletivo','convencao','especial')",
            name="bh_politicas_regime_check",
        ),
        sa.CheckConstraint(
            "fator_credito_padrao > 0", name="bh_politicas_fator_credito_padrao_check"
        ),
        sa.CheckConstraint(
            "fator_debito_padrao > 0", name="bh_politicas_fator_debito_padrao_check"
        ),
        sa.CheckConstraint(
            "limite_diario_minutos >= 0", name="bh_politicas_limite_diario_minutos_check"
        ),
        sa.CheckConstraint(
            "limite_jornada_diaria_minutos > 0",
            name="bh_politicas_limite_jornada_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "periodo_meses BETWEEN 1 AND 12", name="bh_politicas_periodo_meses_check"
        ),
        sa.CheckConstraint(
            "teto_negativo_minutos IS NULL OR teto_negativo_minutos >= 0",
            name="bh_politicas_teto_negativo_minutos_check",
        ),
        sa.CheckConstraint(
            "teto_positivo_minutos IS NULL OR teto_positivo_minutos >= 0",
            name="bh_politicas_teto_positivo_minutos_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_bh_politicas_vigencia",
        ),
        sa.ForeignKeyConstraint(
            ["documento_acordo_id"],
            ["documentos.id"],
            name=op.f("bh_politicas_documento_acordo_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("bh_politicas_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("bh_politicas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bh_politicas_pkey")),
        comment="Regras do banco de horas por empresa. O limite legal esta no CHECK: acordo individual escrito compensa em ate 6 meses; acordo ou convencao coletiva, em ate 12.",
    )
    op.create_index(
        "uq_bh_politicas_codigo",
        "bh_politicas",
        ["tenant_id", "empresa_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("excluido_em IS NULL"),
    )
    op.create_table(
        "comprovantes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("marcacao_id", sa.Uuid(), nullable=False),
        sa.Column("marcacao_datahora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column(
            "cpf", postgresql.DOMAIN("dom_cpf", sa.TEXT(), create_type=False), nullable=False
        ),
        sa.Column("numero", sa.Text(), nullable=False),
        sa.Column("nsr", sa.BigInteger(), nullable=False),
        sa.Column("conteudo_texto", sa.Text(), nullable=False),
        sa.Column("conteudo_ref", sa.Text(), nullable=True),
        sa.Column(
            "hash_sha256",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column("assinatura_ref", sa.Text(), nullable=True),
        sa.Column(
            "emitido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("disponivel_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canal_entrega", sa.Text(), server_default=sa.text("'app'"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal_entrega IN ('app','web','email','impresso','api','terminal')",
            name="comprovantes_canal_entrega_check",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("comprovantes_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_comprovantes_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("comprovantes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("comprovantes_pkey")),
        sa.UniqueConstraint("tenant_id", "marcacao_id", name="uq_comprovantes_marcacao"),
        sa.UniqueConstraint("tenant_id", "numero", name="uq_comprovantes_numero"),
        comment="Comprovante de registro emitido a cada marcacao. Append-only. A impressao no momento da marcacao e dispensada porque garantimos acesso eletronico permanente, com as ultimas 48 horas sempre disponiveis.",
    )
    op.create_index(
        "ix_comprovantes_48h",
        "comprovantes",
        ["tenant_id", sa.literal_column("emitido_em DESC")],
        unique=False,
    )
    op.create_index(
        "ix_comprovantes_colaborador",
        "comprovantes",
        ["tenant_id", "colaborador_id", sa.literal_column("emitido_em DESC")],
        unique=False,
    )
    op.create_table(
        "fila_offline",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=True),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("payload_cifrado", postgresql.BYTEA(), nullable=False),
        sa.Column("iv", postgresql.BYTEA(), nullable=False),
        sa.Column("hmac", sa.Text(), nullable=False),
        sa.Column("contador_monotonico", sa.BigInteger(), nullable=False),
        sa.Column("datahora_dispositivo", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tempo_monotonico_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "capturado_em_offline", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "recebido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("tentativas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("marcacao_id", sa.Uuid(), nullable=True),
        sa.Column("marcacao_datahora", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente','processado','duplicado','rejeitado','expirado')",
            name="fila_offline_status_check",
        ),
        sa.CheckConstraint(
            "(marcacao_id IS NULL AND marcacao_datahora IS NULL) OR (marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)",
            name="ck_fila_offline_marcacao",
        ),
        sa.CheckConstraint(
            "contador_monotonico >= 0", name="fila_offline_contador_monotonico_check"
        ),
        sa.CheckConstraint("tentativas >= 0", name="fila_offline_tentativas_check"),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("fila_offline_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispositivo_id"],
            ["dispositivos.id"],
            name=op.f("fila_offline_dispositivo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_fila_offline_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fila_offline_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("fila_offline_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "dispositivo_id", "contador_monotonico", name="uq_fila_offline_contador"
        ),
        comment="Itens capturados sem rede e enviados depois. Chegam cifrados e assinados; o servidor valida HMAC e contador antes de converter em marcacao. Esta tabela e mutavel de proposito.",
    )
    op.create_index(
        "ix_fila_offline_dispositivo",
        "fila_offline",
        ["tenant_id", "dispositivo_id", sa.literal_column("contador_monotonico DESC")],
        unique=False,
    )
    op.create_index(
        "ix_fila_offline_pendentes",
        "fila_offline",
        ["tenant_id", "status", "recebido_em"],
        unique=False,
        postgresql_where=sa.text("status = 'pendente'"),
    )
    op.create_table(
        "marcacao_idempotencia",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("escopo", sa.Text(), nullable=False),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("marcacao_id", sa.Uuid(), nullable=False),
        sa.Column("datahora_marcacao", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "escopo IN ('external_id','dispositivo_log','idempotency_key','offline_hmac')",
            name="marcacao_idempotencia_escopo_check",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "datahora_marcacao"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_marcacao_idempotencia_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("marcacao_idempotencia_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("marcacao_idempotencia_pkey")),
        sa.UniqueConstraint("tenant_id", "escopo", "chave", name="uq_marcacao_idempotencia"),
        comment="Guarda global de idempotencia. Reenvio do mesmo registro offline colide aqui e nao duplica marcacao.",
    )
    op.create_index(
        "ix_marcacao_idempotencia_marcacao",
        "marcacao_idempotencia",
        ["tenant_id", "marcacao_id"],
        unique=False,
    )
    op.create_table(
        "marcacoes_meta",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("marcacao_id", sa.Uuid(), nullable=False),
        sa.Column("marcacao_datahora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("precisao_metros", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("altitude", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("endereco_aproximado", sa.Text(), nullable=True),
        sa.Column("unidade_geocerca_id", sa.Uuid(), nullable=True),
        sa.Column("dentro_geocerca", sa.Boolean(), nullable=True),
        sa.Column("distancia_geocerca_metros", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("foto_ref", sa.Text(), nullable=True),
        sa.Column(
            "foto_hash",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("score_facial", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("limiar_facial", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("versao_modelo_facial", sa.Text(), nullable=True),
        sa.Column("liveness_aprovado", sa.Boolean(), nullable=True),
        sa.Column("liveness_metodo", sa.Text(), nullable=True),
        sa.Column("score_confianca", sa.SmallInteger(), nullable=True),
        sa.Column("classificacao_confianca", sa.Text(), nullable=True),
        sa.Column(
            "flags_integridade",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attestation_veredito", sa.Text(), nullable=True),
        sa.Column("root_detectado", sa.Boolean(), nullable=True),
        sa.Column("emulador_detectado", sa.Boolean(), nullable=True),
        sa.Column("modo_desenvolvedor", sa.Boolean(), nullable=True),
        sa.Column("mock_location", sa.Boolean(), nullable=True),
        sa.Column("camera_virtual", sa.Boolean(), nullable=True),
        sa.Column("velocidade_desde_ultima_kmh", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("wifi_bssid", sa.Text(), nullable=True),
        sa.Column("celula_id", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("asn", sa.Text(), nullable=True),
        sa.Column("pais", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column(
            "revisao_status", sa.Text(), server_default=sa.text("'nao_requer'"), nullable=False
        ),
        sa.Column("revisado_por", sa.Uuid(), nullable=True),
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revisao_observacao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "attestation_veredito IN ('aprovado','reprovado','indisponivel','nao_aplicavel')",
            name="marcacoes_meta_attestation_veredito_check",
        ),
        sa.CheckConstraint(
            "classificacao_confianca IN ('alta','media','baixa','bloqueada')",
            name="marcacoes_meta_classificacao_confianca_check",
        ),
        sa.CheckConstraint(
            "liveness_metodo IN ('desafio_ativo','passivo','hibrido','nao_aplicavel')",
            name="marcacoes_meta_liveness_metodo_check",
        ),
        sa.CheckConstraint(
            "revisao_status IN ('nao_requer','pendente','aprovada','rejeitada')",
            name="marcacoes_meta_revisao_status_check",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="marcacoes_meta_latitude_check"
        ),
        sa.CheckConstraint(
            "limiar_facial IS NULL OR limiar_facial BETWEEN 0 AND 100",
            name="marcacoes_meta_limiar_facial_check",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="marcacoes_meta_longitude_check",
        ),
        sa.CheckConstraint(
            "precisao_metros IS NULL OR precisao_metros >= 0",
            name="marcacoes_meta_precisao_metros_check",
        ),
        sa.CheckConstraint(
            "score_confianca IS NULL OR score_confianca BETWEEN 0 AND 100",
            name="marcacoes_meta_score_confianca_check",
        ),
        sa.CheckConstraint(
            "score_facial IS NULL OR score_facial BETWEEN 0 AND 100",
            name="marcacoes_meta_score_facial_check",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_marcacoes_meta_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("marcacoes_meta_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_geocerca_id"],
            ["unidades.id"],
            name=op.f("marcacoes_meta_unidade_geocerca_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("marcacoes_meta_pkey")),
        sa.UniqueConstraint("tenant_id", "marcacao_id", name="uq_marcacoes_meta"),
        comment="Contexto e evidencia antifraude da marcacao. Separada de marcacoes para manter o nucleo legal enxuto e imutavel e permitir que o gestor revise o risco sem jamais tocar no registro legal.",
    )
    op.create_index(
        "ix_marcacoes_meta_flags",
        "marcacoes_meta",
        ["flags_integridade"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_marcacoes_meta_fora_cerca",
        "marcacoes_meta",
        ["tenant_id", "marcacao_datahora"],
        unique=False,
        postgresql_where=sa.text("dentro_geocerca = FALSE"),
    )
    op.create_index(
        "ix_marcacoes_meta_revisao",
        "marcacoes_meta",
        ["tenant_id", "revisao_status"],
        unique=False,
        postgresql_where=sa.text("revisao_status = 'pendente'"),
    )
    op.create_index(
        "ix_marcacoes_meta_score", "marcacoes_meta", ["tenant_id", "score_confianca"], unique=False
    )
    op.create_table(
        "nsr_emissoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rep_p_id", sa.Uuid(), nullable=False),
        sa.Column("nsr", sa.BigInteger(), nullable=False),
        sa.Column("marcacao_id", sa.Uuid(), nullable=False),
        sa.Column("datahora_marcacao", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "hash_registro",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "hash_anterior",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint("nsr >= 1", name="nsr_emissoes_nsr_check"),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "datahora_marcacao"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_nsr_emissoes_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rep_p_id"],
            ["rep_ps.id"],
            name=op.f("nsr_emissoes_rep_p_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("nsr_emissoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("nsr_emissoes_pkey")),
        sa.UniqueConstraint("tenant_id", "rep_p_id", "nsr", name="uq_nsr_emissoes"),
        comment="Indice global de NSR emitidos. Nao e particionada e impoe a unicidade de (tenant_id, rep_p_id, nsr) globalmente, tornando a deteccao de lacuna uma consulta trivial.",
    )
    op.create_index(
        "ix_nsr_emissoes_sequencia", "nsr_emissoes", ["tenant_id", "rep_p_id", "nsr"], unique=False
    )
    op.create_table(
        "tratamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_tratamento_id", sa.Uuid(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("marcacao_id", sa.Uuid(), nullable=True),
        sa.Column("marcacao_datahora", sa.DateTime(timezone=True), nullable=True),
        sa.Column("datahora_proposta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sentido", sa.Text(), nullable=True),
        sa.Column("minutos_ajuste", sa.Integer(), nullable=True),
        sa.Column("tipo_afastamento_id", sa.Uuid(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), server_default=sa.text("'gestor'"), nullable=False),
        sa.Column("solicitacao_id", sa.Uuid(), nullable=True),
        sa.Column("documento_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("aprovado_por", sa.Uuid(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reprovado_motivo", sa.Text(), nullable=True),
        sa.Column("aplicado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "origem IN ('colaborador','gestor','rh','sistema','integracao','importacao')",
            name="tratamentos_origem_check",
        ),
        sa.CheckConstraint(
            "sentido IN ('entrada','saida','indefinido')", name="tratamentos_sentido_check"
        ),
        sa.CheckConstraint(
            "status IN ('rascunho','pendente','aprovado','reprovado','cancelado','aplicado')",
            name="tratamentos_status_check",
        ),
        sa.CheckConstraint(
            "(marcacao_id IS NULL AND marcacao_datahora IS NULL) OR (marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)",
            name="ck_tratamentos_marcacao",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("tratamentos_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos.id"],
            name=op.f("tratamentos_documento_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_tratamentos_marcacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("tratamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_afastamento_id"],
            ["tipos_afastamento.id"],
            name=op.f("tratamentos_tipo_afastamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_tratamento_id"],
            ["tipos_tratamento.id"],
            name=op.f("tratamentos_tipo_tratamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("tratamentos_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tratamentos_pkey")),
        comment="CAMADA DE CORRECAO. Um tratamento se refere a um dia e, opcionalmente, a uma marcacao existente, mas NUNCA a modifica.",
    )
    op.create_index(
        "ix_tratamentos_marcacao",
        "tratamentos",
        ["tenant_id", "marcacao_id"],
        unique=False,
        postgresql_where=sa.text("marcacao_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tratamentos_pendentes",
        "tratamentos",
        ["tenant_id", "status", "data_referencia"],
        unique=False,
        postgresql_where=sa.text("status = 'pendente'"),
    )
    op.create_index(
        "ix_tratamentos_vinculo_data",
        "tratamentos",
        ["tenant_id", "vinculo_id", "data_referencia"],
        unique=False,
    )
    op.create_table(
        "apuracoes_dia",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("departamento_id", sa.Uuid(), nullable=True),
        sa.Column("centro_custo_id", sa.Uuid(), nullable=True),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("escala_id", sa.Uuid(), nullable=True),
        sa.Column("turno_id", sa.Uuid(), nullable=True),
        sa.Column("horario_id", sa.Uuid(), nullable=True),
        sa.Column("feriado_id", sa.Uuid(), nullable=True),
        sa.Column("afastamento_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_dia", sa.Text(), server_default=sa.text("'util'"), nullable=False),
        sa.Column("previsto_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("trabalhado_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("normais_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("extras_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "extras_noturnas_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("noturno_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "noturno_ficta_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("intervalo_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "intervalo_previsto_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "intrajornada_suprimida_minutos",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("interjornada_minutos", sa.Integer(), nullable=True),
        sa.Column(
            "interjornada_violada", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("atraso_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "saida_antecipada_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("falta_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("abono_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sobreaviso_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("prontidao_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pausas_nr17_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("dsr_credito_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("dsr_debito_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "banco_credito_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "banco_debito_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "tolerancia_aplicada_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("saldo_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "quantidade_marcacoes", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "marcacoes_impares", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column("tem_tratamento", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pendente'"), nullable=False),
        sa.Column("versao", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "hash_entrada",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("fechamento_id", sa.Uuid(), nullable=True),
        sa.Column("apurado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apurado_por", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente','apurado','com_ocorrencia','fechado','reaberto')",
            name="apuracoes_dia_status_check",
        ),
        sa.CheckConstraint(
            "tipo_dia IN ('util','dsr','folga','feriado','ponto_facultativo','afastamento','compensado','nao_apurado')",
            name="apuracoes_dia_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "quantidade_marcacoes >= 0", name="apuracoes_dia_quantidade_marcacoes_check"
        ),
        sa.CheckConstraint("versao >= 1", name="apuracoes_dia_versao_check"),
        sa.ForeignKeyConstraint(
            ["afastamento_id"],
            ["afastamentos.id"],
            name=op.f("apuracoes_dia_afastamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["centro_custo_id"],
            ["centros_custo.id"],
            name=op.f("apuracoes_dia_centro_custo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("apuracoes_dia_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["departamentos.id"],
            name=op.f("apuracoes_dia_departamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["empresas.id"],
            name=op.f("apuracoes_dia_empresa_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["escala_id"],
            ["escalas.id"],
            name=op.f("apuracoes_dia_escala_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feriado_id"],
            ["feriados.id"],
            name=op.f("apuracoes_dia_feriado_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["horario_id"],
            ["horarios.id"],
            name=op.f("apuracoes_dia_horario_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["jornada_id"],
            ["jornadas.id"],
            name=op.f("apuracoes_dia_jornada_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("apuracoes_dia_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turno_id"],
            ["turnos.id"],
            name=op.f("apuracoes_dia_turno_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id"],
            ["unidades.id"],
            name=op.f("apuracoes_dia_unidade_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("apuracoes_dia_vinculo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("apuracoes_dia_pkey")),
        sa.UniqueConstraint("tenant_id", "vinculo_id", "data", name="uq_apuracoes_dia"),
        comment="Resultado consolidado do calculo de um dia para um vinculo. E derivada e recalculavel: apagar e recalcular precisa produzir exatamente o mesmo resultado.",
    )
    op.create_index(
        "ix_apuracoes_dia_colaborador",
        "apuracoes_dia",
        ["tenant_id", "colaborador_id", sa.literal_column("data DESC")],
        unique=False,
    )
    op.create_index(
        "ix_apuracoes_dia_fechamento",
        "apuracoes_dia",
        ["tenant_id", "fechamento_id"],
        unique=False,
        postgresql_where=sa.text("fechamento_id IS NOT NULL"),
    )
    op.create_index(
        "ix_apuracoes_dia_periodo",
        "apuracoes_dia",
        ["tenant_id", "empresa_id", "data"],
        unique=False,
    )
    op.create_index(
        "ix_apuracoes_dia_status",
        "apuracoes_dia",
        ["tenant_id", "status", "data"],
        unique=False,
        postgresql_where=sa.text("status IN ('pendente','com_ocorrencia')"),
    )
    op.create_index(
        "ix_apuracoes_dia_unidade",
        "apuracoes_dia",
        ["tenant_id", "unidade_id", "data"],
        unique=False,
    )
    op.create_table(
        "bh_contas",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=False),
        sa.Column("bh_politica_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'aberta'"), nullable=False),
        sa.Column("saldo_atual_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ultima_sequencia", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "ultimo_hash",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('aberta','encerrada','quitada','expirada','suspensa')",
            name="bh_contas_status_check",
        ),
        sa.CheckConstraint("periodo_fim > periodo_inicio", name="ck_bh_contas_periodo"),
        sa.CheckConstraint("ultima_sequencia >= 0", name="bh_contas_ultima_sequencia_check"),
        sa.ForeignKeyConstraint(
            ["bh_politica_id"],
            ["bh_politicas.id"],
            name=op.f("bh_contas_bh_politica_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("bh_contas_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("bh_contas_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("bh_contas_vinculo_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bh_contas_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "vinculo_id", "codigo", "periodo_inicio", name="uq_bh_contas"
        ),
        comment="Conta-corrente de horas de um vinculo dentro de um periodo de apuracao do banco. Um vinculo pode ter varias contas simultaneas com fatores diferentes.",
    )
    op.create_index(
        "ix_bh_contas_vencimento",
        "bh_contas",
        ["tenant_id", "periodo_fim"],
        unique=False,
        postgresql_where=sa.text("status = 'aberta'"),
    )
    op.create_index(
        "ix_bh_contas_vinculo", "bh_contas", ["tenant_id", "vinculo_id", "status"], unique=False
    )
    op.create_table(
        "apuracao_componentes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("apuracao_dia_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("minutos", sa.Integer(), nullable=False),
        sa.Column(
            "fator", sa.Numeric(precision=6, scale=4), server_default=sa.text("1.0"), nullable=False
        ),
        sa.Column(
            "minutos_equivalentes", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("origem", sa.Text(), server_default=sa.text("'marcacao'"), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detalhes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('normal','extra','noturno','falta','abono','intervalo','sobreaviso','prontidao','dsr','banco','indenizacao','pausa')",
            name="apuracao_componentes_categoria_check",
        ),
        sa.CheckConstraint(
            "origem IN ('marcacao','tratamento','afastamento','regra','banco','feriado')",
            name="apuracao_componentes_origem_check",
        ),
        sa.CheckConstraint("fator >= 0", name="apuracao_componentes_fator_check"),
        sa.ForeignKeyConstraint(
            ["apuracao_dia_id"],
            ["apuracoes_dia.id"],
            name=op.f("apuracao_componentes_apuracao_dia_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("apuracao_componentes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("apuracao_componentes_pkey")),
        comment="Decomposicao auditavel da apuracao do dia. Cada linha explica de onde saiu cada bloco de minutos.",
    )
    op.create_index(
        "ix_apuracao_componentes_apuracao",
        "apuracao_componentes",
        ["tenant_id", "apuracao_dia_id"],
        unique=False,
    )
    op.create_index(
        "ix_apuracao_componentes_codigo",
        "apuracao_componentes",
        ["tenant_id", "codigo", "categoria"],
        unique=False,
    )
    op.create_table(
        "bh_lancamentos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bh_conta_id", sa.Uuid(), nullable=False),
        sa.Column("sequencia", sa.BigInteger(), nullable=False),
        sa.Column("data_competencia", sa.Date(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("apuracao_dia_id", sa.Uuid(), nullable=True),
        sa.Column("tratamento_id", sa.Uuid(), nullable=True),
        sa.Column("quitacao_id", sa.Uuid(), nullable=True),
        sa.Column("estorna_lancamento_id", sa.Uuid(), nullable=True),
        sa.Column("minutos", sa.Integer(), nullable=False),
        sa.Column(
            "fator", sa.Numeric(precision=6, scale=4), server_default=sa.text("1.0"), nullable=False
        ),
        sa.Column("minutos_equivalentes", sa.Integer(), nullable=False),
        sa.Column("saldo_apos_minutos", sa.Integer(), nullable=False),
        sa.Column("vence_em", sa.Date(), nullable=True),
        sa.Column("consumido_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column(
            "hash_anterior",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column(
            "hash_registro",
            postgresql.DOMAIN("dom_sha256", sa.TEXT(), create_type=False),
            nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "origem IN ('apuracao','tratamento','solicitacao','quitacao','expiracao','ajuste_manual','importacao','fechamento','rescisao')",
            name="bh_lancamentos_origem_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('credito','debito','quitacao','expiracao','ajuste','transferencia','estorno')",
            name="bh_lancamentos_tipo_check",
        ),
        sa.CheckConstraint("consumido_minutos >= 0", name="bh_lancamentos_consumido_minutos_check"),
        sa.CheckConstraint("fator > 0", name="bh_lancamentos_fator_check"),
        sa.CheckConstraint("minutos <> 0", name="bh_lancamentos_minutos_check"),
        sa.CheckConstraint("sequencia >= 1", name="bh_lancamentos_sequencia_check"),
        sa.ForeignKeyConstraint(
            ["apuracao_dia_id"],
            ["apuracoes_dia.id"],
            name=op.f("bh_lancamentos_apuracao_dia_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bh_conta_id"],
            ["bh_contas.id"],
            name=op.f("bh_lancamentos_bh_conta_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["estorna_lancamento_id"],
            ["bh_lancamentos.id"],
            name=op.f("bh_lancamentos_estorna_lancamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("bh_lancamentos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tratamento_id"],
            ["tratamentos.id"],
            name=op.f("bh_lancamentos_tratamento_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bh_lancamentos_pkey")),
        sa.UniqueConstraint(
            "tenant_id", "bh_conta_id", "sequencia", name="uq_bh_lancamentos_sequencia"
        ),
        comment="EXTRATO IMUTAVEL do banco de horas, com cadeia de hash. Gatilhos barram DELETE, TRUNCATE e qualquer UPDATE que nao seja exclusivamente em consumido_minutos. Corrigir significa emitir um estorno.",
    )
    op.create_index(
        "ix_bh_lancamentos_apuracao",
        "bh_lancamentos",
        ["tenant_id", "apuracao_dia_id"],
        unique=False,
        postgresql_where=sa.text("apuracao_dia_id IS NOT NULL"),
    )
    op.create_index(
        "ix_bh_lancamentos_competencia",
        "bh_lancamentos",
        ["tenant_id", "data_competencia"],
        unique=False,
    )
    op.create_index(
        "ix_bh_lancamentos_conta",
        "bh_lancamentos",
        ["tenant_id", "bh_conta_id", "sequencia"],
        unique=False,
    )
    op.create_index(
        "ix_bh_lancamentos_vencimento",
        "bh_lancamentos",
        ["tenant_id", "vence_em"],
        unique=False,
        postgresql_where=sa.text("vence_em IS NOT NULL AND tipo = 'credito'"),
    )
    op.create_table(
        "bh_quitacoes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bh_conta_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("minutos", sa.Integer(), nullable=False),
        sa.Column(
            "fator", sa.Numeric(precision=6, scale=4), server_default=sa.text("1.0"), nullable=False
        ),
        sa.Column("valor", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "competencia_folha",
            postgresql.DOMAIN("dom_competencia", sa.TEXT(), create_type=False),
            nullable=True,
        ),
        sa.Column("data_prevista", sa.Date(), nullable=True),
        sa.Column("data_efetivacao", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'planejada'"), nullable=False),
        sa.Column("aprovado_por", sa.Uuid(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('planejada','aprovada','efetivada','cancelada')",
            name="bh_quitacoes_status_check",
        ),
        sa.CheckConstraint(
            "tipo IN ('folha','folga','rescisao','expiracao','compensacao_programada')",
            name="bh_quitacoes_tipo_check",
        ),
        sa.CheckConstraint("fator > 0", name="bh_quitacoes_fator_check"),
        sa.CheckConstraint("minutos > 0", name="bh_quitacoes_minutos_check"),
        sa.CheckConstraint("valor IS NULL OR valor >= 0", name="bh_quitacoes_valor_check"),
        sa.ForeignKeyConstraint(
            ["bh_conta_id"],
            ["bh_contas.id"],
            name=op.f("bh_quitacoes_bh_conta_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("bh_quitacoes_colaborador_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("bh_quitacoes_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bh_quitacoes_pkey")),
        comment="Liquidacao de saldo de banco de horas: pagamento em folha, folga programada, acerto na rescisao ou expiracao.",
    )
    op.create_index(
        "ix_bh_quitacoes_competencia",
        "bh_quitacoes",
        ["tenant_id", "competencia_folha"],
        unique=False,
        postgresql_where=sa.text("tipo = 'folha'"),
    )
    op.create_index(
        "ix_bh_quitacoes_conta",
        "bh_quitacoes",
        ["tenant_id", "bh_conta_id", "status"],
        unique=False,
    )
    op.create_table(
        "bh_saldos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bh_conta_id", sa.Uuid(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("saldo_minutos", sa.Integer(), nullable=False),
        sa.Column(
            "credito_periodo_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "debito_periodo_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("a_vencer_30_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("a_vencer_15_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("a_vencer_7_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "projecao_vencimento_minutos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "calculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["bh_conta_id"],
            ["bh_contas.id"],
            name=op.f("bh_saldos_bh_conta_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("bh_saldos_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bh_saldos_pkey")),
        sa.UniqueConstraint("tenant_id", "bh_conta_id", "data_referencia", name="uq_bh_saldos"),
        comment="Fotografia diaria do saldo de cada conta. Existe para relatorio, dashboard e simulador responderem rapido sem varrer o extrato inteiro.",
    )
    op.create_index(
        "ix_bh_saldos_data",
        "bh_saldos",
        ["tenant_id", sa.literal_column("data_referencia DESC")],
        unique=False,
    )
    op.create_table(
        "ocorrencias",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("colaborador_id", sa.Uuid(), nullable=False),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.Column("apuracao_dia_id", sa.Uuid(), nullable=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("severidade", sa.Text(), server_default=sa.text("'atencao'"), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("detalhes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'aberta'"), nullable=False),
        sa.Column("tratamento_id", sa.Uuid(), nullable=True),
        sa.Column("resolucao", sa.Text(), nullable=True),
        sa.Column("resolvida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolvida_por", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "codigo IN ('marcacao_impar','sem_marcacao','falta','atraso','saida_antecipada','extra_excedida','jornada_excedida','intrajornada_suprimida','interjornada_violada','dsr_violado','pausa_nr17','fora_geocerca','score_baixo','marcacao_duplicada','offline_tardio','banco_teto','banco_vencendo','terminal_offline')",
            name="ocorrencias_codigo_check",
        ),
        sa.CheckConstraint(
            "severidade IN ('info','atencao','alta','critica')", name="ocorrencias_severidade_check"
        ),
        sa.CheckConstraint(
            "status IN ('aberta','em_tratamento','resolvida','ignorada')",
            name="ocorrencias_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["apuracao_dia_id"],
            ["apuracoes_dia.id"],
            name=op.f("ocorrencias_apuracao_dia_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["colaboradores.id"],
            name=op.f("ocorrencias_colaborador_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("ocorrencias_tenant_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tratamento_id"],
            ["tratamentos.id"],
            name=op.f("ocorrencias_tratamento_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vinculo_id"],
            ["vinculos.id"],
            name=op.f("ocorrencias_vinculo_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("ocorrencias_pkey")),
        comment="Inconsistencia ou desvio detectado pelo motor. E a fila de trabalho do gestor e do RH e a base do relatorio de ocorrencias.",
    )
    op.create_index(
        "ix_ocorrencias_abertas",
        "ocorrencias",
        ["tenant_id", "status", sa.literal_column("data DESC")],
        unique=False,
        postgresql_where=sa.text("status IN ('aberta','em_tratamento')"),
    )
    op.create_index(
        "ix_ocorrencias_codigo", "ocorrencias", ["tenant_id", "codigo", "data"], unique=False
    )
    op.create_index(
        "ix_ocorrencias_colaborador",
        "ocorrencias",
        ["tenant_id", "colaborador_id", sa.literal_column("data DESC")],
        unique=False,
    )


def _criar_fks_adiadas() -> None:
    op.create_foreign_key(
        "fk_afastamentos_solicitacao",
        "afastamentos",
        "solicitacoes",
        ["solicitacao_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_apuracoes_dia_fechamento",
        "apuracoes_dia",
        "fechamentos",
        ["fechamento_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_bh_lancamentos_quitacao",
        "bh_lancamentos",
        "bh_quitacoes",
        ["quitacao_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_biometrias_consentimento",
        "biometrias",
        "consentimentos",
        ["consentimento_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_contratos_documento",
        "contratos",
        "documentos",
        ["documento_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_departamentos_responsavel",
        "departamentos",
        "colaboradores",
        ["responsavel_colaborador_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_marcacoes_importacao",
        "marcacoes",
        "importacoes",
        ["origem_importacao_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_sessoes_dispositivo",
        "sessoes",
        "dispositivos",
        ["dispositivo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_terminais_rep_p",
        "terminais",
        "rep_ps",
        ["rep_p_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tratamentos_solicitacao",
        "tratamentos",
        "solicitacoes",
        ["solicitacao_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usuario_perfis_equipe",
        "usuario_perfis",
        "equipes",
        ["equipe_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_usuarios_colaborador",
        "usuarios",
        "colaboradores",
        ["colaborador_id"],
        ["id"],
        ondelete="SET NULL",
    )


def _remover_fks_adiadas() -> None:
    op.drop_constraint("fk_afastamentos_solicitacao", "afastamentos", type_="foreignkey")
    op.drop_constraint("fk_apuracoes_dia_fechamento", "apuracoes_dia", type_="foreignkey")
    op.drop_constraint("fk_bh_lancamentos_quitacao", "bh_lancamentos", type_="foreignkey")
    op.drop_constraint("fk_biometrias_consentimento", "biometrias", type_="foreignkey")
    op.drop_constraint("fk_contratos_documento", "contratos", type_="foreignkey")
    op.drop_constraint("fk_departamentos_responsavel", "departamentos", type_="foreignkey")
    op.drop_constraint("fk_marcacoes_importacao", "marcacoes", type_="foreignkey")
    op.drop_constraint("fk_sessoes_dispositivo", "sessoes", type_="foreignkey")
    op.drop_constraint("fk_terminais_rep_p", "terminais", type_="foreignkey")
    op.drop_constraint("fk_tratamentos_solicitacao", "tratamentos", type_="foreignkey")
    op.drop_constraint("fk_usuario_perfis_equipe", "usuario_perfis", type_="foreignkey")
    op.drop_constraint("fk_usuarios_colaborador", "usuarios", type_="foreignkey")


def _remover_tabelas() -> None:
    op.drop_table("ocorrencias")
    op.drop_table("bh_saldos")
    op.drop_table("bh_quitacoes")
    op.drop_table("bh_lancamentos")
    op.drop_table("apuracao_componentes")
    op.drop_table("bh_contas")
    op.drop_table("apuracoes_dia")
    op.drop_table("tratamentos")
    op.drop_table("nsr_emissoes")
    op.drop_table("marcacoes_meta")
    op.drop_table("marcacao_idempotencia")
    op.drop_table("fila_offline")
    op.drop_table("comprovantes")
    op.drop_table("bh_politicas")
    op.drop_table("assinaturas_espelho")
    op.drop_table("aprovacoes")
    op.drop_table("afastamentos")
    op.drop_table("vinculo_jornadas")
    op.drop_table("terminal_saude")
    op.drop_table("solicitacoes")
    op.drop_table("marcacoes")
    op.drop_table("espelhos")
    op.drop_table("escala_atribuicoes")
    op.drop_table("documentos")
    op.drop_table("vinculos")
    op.drop_table("terminais")
    op.drop_table("escala_ciclos")
    op.drop_table("equipe_membros")
    op.drop_table("dispositivo_vinculos")
    op.drop_table("biometria_templates")
    op.drop_table("webhook_entregas")
    op.drop_table("usuario_perfis")
    op.drop_table("unidade_feriado_conjuntos")
    op.drop_table("turnos")
    op.drop_table("solicitacoes_titular")
    op.drop_table("relatorio_execucoes")
    op.drop_table("refresh_tokens")
    op.drop_table("redes_permitidas")
    op.drop_table("politicas_registro")
    op.drop_table("nsr_sequencias")
    op.drop_table("notificacoes")
    op.drop_table("jornada_dias")
    op.drop_table("fechamentos")
    op.drop_table("escalas")
    op.drop_table("equipes")
    op.drop_table("dispositivos")
    op.drop_table("contratos")
    op.drop_table("consentimentos")
    op.drop_table("colaborador_gestores")
    op.drop_table("biometrias")
    op.drop_table("afd_arquivos")
    op.drop_table("aej_arquivos")
    op.drop_table("acessos_dados_sensiveis")
    op.drop_table("webhooks")
    op.drop_table("unidades")
    op.drop_table("tipos_solicitacao")
    op.drop_table("sessoes")
    op.drop_table("rep_ps")
    op.drop_table("relatorio_agendamentos")
    op.drop_table("preferencias_colunas")
    op.drop_table("periodos")
    op.drop_table("perfil_permissoes")
    op.drop_table("oauth_tokens")
    op.drop_table("notificacao_preferencias")
    op.drop_table("mfa_dispositivos")
    op.drop_table("jornadas")
    op.drop_table("integracoes_folha")
    op.drop_table("importacoes")
    op.drop_table("horarios")
    op.drop_table("feriados")
    op.drop_table("departamentos")
    op.drop_table("delegacoes")
    op.drop_table("credenciais")
    op.drop_table("colaboradores")
    op.drop_table("centros_custo")
    op.drop_table("cargos")
    op.drop_table("api_keys")
    op.drop_table("usuarios")
    op.drop_table("tipos_tratamento")
    op.drop_table("tipos_afastamento")
    op.drop_table("tenant_configuracoes")
    op.drop_table("relatorio_definicoes")
    op.drop_table("politicas_retencao")
    op.drop_table("perfis")
    op.drop_table("feriado_conjuntos")
    op.drop_table("empresas")
    op.drop_table("auditoria")
    op.drop_table("arquivo_assinaturas")
    op.drop_table("api_clients")
    op.drop_table("anexos")
    op.drop_table("tenants")
    op.drop_table("permissoes")
