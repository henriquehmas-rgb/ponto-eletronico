-- =============================================================================
-- Ponto Eletronico (REP-P multiempresa) - MODELO DE DADOS CANONICO
-- Arquivo: packages/contracts/schema.sql
-- Alvo: PostgreSQL 16
-- Fase 0 - Fundacao e Contratos - Agente A1a
--
-- Este arquivo e a FONTE DA VERDADE do modelo de dados. Toda fase posterior
-- consome este contrato; nenhuma fase o altera sem RFC aprovada.
--
-- Convencoes adotadas (ver packages/contracts/glossario.md, secao "Convencoes"):
--   1. Nomes de tabela e coluna em portugues do Brasil, snake_case, plural nas
--      tabelas de entidade e singular nos qualificadores.
--   2. Chave primaria UUID v4 (gen_random_uuid) em todas as tabelas.
--   3. Enums de dominio sao TEXT + CHECK (padrao unico, sem tipos ENUM nativos).
--   4. Auditoria: criado_em / criado_por / atualizado_em / atualizado_por.
--      Tabelas append-only nao possuem atualizado_em / atualizado_por.
--   5. Soft delete (excluido_em / excluido_por) SOMENTE em cadastros.
--      NUNCA em marcacoes, lancamentos, auditoria ou qualquer trilha legal.
--   6. Todas as colunas de tempo sao TIMESTAMPTZ. Datas civis sao DATE.
--   7. Duracoes sao INTEGER em MINUTOS (nunca float, nunca interval).
--   8. Todo dado de dominio carrega tenant_id e esta sob Row Level Security.
--
-- Execucao: banco limpo. `psql -v ON_ERROR_STOP=1 -f schema.sql`.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. EXTENSOES
-- -----------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid(), digest(), crypt()
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid_generate_v4() (compatibilidade)
CREATE EXTENSION IF NOT EXISTS btree_gist;    -- EXCLUDE de vigencias combinando uuid + range
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- busca por nome de colaborador

COMMENT ON EXTENSION btree_gist IS
  'Necessaria para as constraints EXCLUDE de vigencia (tenant_id WITH = combinado com daterange WITH &&).';


-- -----------------------------------------------------------------------------
-- 1. FUNCOES AUXILIARES E DOMINIOS
-- -----------------------------------------------------------------------------

-- Tenant corrente da sessao. A aplicacao executa
--   SET LOCAL app.tenant_id = '<uuid>';
-- no inicio de cada transacao. Sem isso, nenhuma linha e visivel.
CREATE OR REPLACE FUNCTION app_tenant_atual() RETURNS UUID
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$;

COMMENT ON FUNCTION app_tenant_atual() IS
  'Retorna o tenant corrente lido de current_setting(''app.tenant_id''). Retorna NULL quando nao definido, o que faz as policies de RLS negarem tudo.';

-- Usuario corrente da sessao (para gatilhos de auditoria da aplicacao).
CREATE OR REPLACE FUNCTION app_usuario_atual() RETURNS UUID
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.usuario_id', true), '')::uuid;
$$;

COMMENT ON FUNCTION app_usuario_atual() IS
  'Retorna o usuario corrente lido de current_setting(''app.usuario_id''). Usado por gatilhos e por rotinas de auditoria.';

-- Mantem atualizado_em coerente sem depender da aplicacao.
CREATE OR REPLACE FUNCTION fn_atualiza_timestamp() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_atualiza_timestamp() IS
  'Gatilho BEFORE UPDATE aplicado automaticamente a toda tabela que possui a coluna atualizado_em.';

-- Barreira de imutabilidade. Usada em marcacoes, extrato de banco de horas,
-- auditoria, comprovantes e trilhas legais. Nao e preferencia de engenharia:
-- a Portaria MTP 671/2021 veda ao REP alterar ou apagar marcacoes.
CREATE OR REPLACE FUNCTION fn_registro_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    'registro_imutavel: operacao % vedada na tabela %. Registros desta tabela sao append-only por exigencia legal e de auditoria; use a camada de tratamento.',
    TG_OP, TG_TABLE_NAME
    USING ERRCODE = '42501',
          HINT = 'Portaria MTP 671/2021 e ADR-002 (imutabilidade de marcacao).';
END;
$$;

COMMENT ON FUNCTION fn_registro_imutavel() IS
  'Gatilho que aborta UPDATE, DELETE e TRUNCATE em tabelas append-only. Exigencia legal, nao configuravel.';

-- Nota: fn_resolve_tenant fica na secao 2, logo apos a tabela tenants, porque
-- corpos de funcao em LANGUAGE sql sao validados no momento da criacao.

-- Dominios de formato. Validam o formato; a validacao de digito verificador
-- (CPF, CNPJ, PIS) e responsabilidade da aplicacao (Fase 2).
CREATE DOMAIN dom_cpf         AS TEXT CHECK (VALUE ~ '^[0-9]{11}$');
CREATE DOMAIN dom_cnpj        AS TEXT CHECK (VALUE ~ '^[0-9]{14}$');
CREATE DOMAIN dom_pis         AS TEXT CHECK (VALUE ~ '^[0-9]{11}$');
CREATE DOMAIN dom_cep         AS TEXT CHECK (VALUE ~ '^[0-9]{8}$');
CREATE DOMAIN dom_uf          AS TEXT CHECK (VALUE ~ '^[A-Z]{2}$');
CREATE DOMAIN dom_ibge        AS TEXT CHECK (VALUE ~ '^[0-9]{7}$');
CREATE DOMAIN dom_cbo         AS TEXT CHECK (VALUE ~ '^[0-9]{6}$');
CREATE DOMAIN dom_email       AS TEXT CHECK (VALUE ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$');
CREATE DOMAIN dom_sha256      AS TEXT CHECK (VALUE ~ '^[0-9a-fA-F]{64}$');
CREATE DOMAIN dom_fuso        AS TEXT CHECK (VALUE ~ '^[A-Za-z]+/[A-Za-z_+-]+$');
CREATE DOMAIN dom_competencia AS TEXT CHECK (VALUE ~ '^[0-9]{4}-(0[1-9]|1[0-2])$');

COMMENT ON DOMAIN dom_cpf IS 'CPF em 11 digitos, sem pontuacao. Digito verificador validado na aplicacao.';
COMMENT ON DOMAIN dom_cnpj IS 'CNPJ em 14 digitos, sem pontuacao.';
COMMENT ON DOMAIN dom_pis IS 'PIS/PASEP/NIT em 11 digitos, sem pontuacao.';
COMMENT ON DOMAIN dom_ibge IS 'Codigo IBGE do municipio em 7 digitos. Base dos feriados municipais.';
COMMENT ON DOMAIN dom_sha256 IS 'Hash SHA-256 em hexadecimal (64 caracteres).';
COMMENT ON DOMAIN dom_competencia IS 'Competencia de folha no formato AAAA-MM.';


-- =============================================================================
-- 2. TENANCY
-- =============================================================================

CREATE TABLE tenants (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              TEXT NOT NULL,
    razao_social      TEXT NOT NULL,
    nome_exibicao     TEXT NOT NULL,
    documento         dom_cnpj,
    plano             TEXT NOT NULL DEFAULT 'padrao'
                      CHECK (plano IN ('trial','padrao','avancado','enterprise')),
    status            TEXT NOT NULL DEFAULT 'trial'
                      CHECK (status IN ('trial','ativo','suspenso','cancelado')),
    fuso_horario      dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    locale            TEXT NOT NULL DEFAULT 'pt-BR',
    dominio_proprio   TEXT,
    limite_colaboradores INTEGER,
    data_contratacao  DATE,
    data_cancelamento DATE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID,
    excluido_em       TIMESTAMPTZ,
    excluido_por      UUID,
    CONSTRAINT uq_tenants_slug UNIQUE (slug),
    CONSTRAINT ck_tenants_slug_formato CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$')
);

COMMENT ON TABLE tenants IS
  'Raiz da multi-tenancy. Cada tenant e um cliente do SaaS e pode conter varias empresas (CNPJs). Unica tabela de dominio sem coluna tenant_id: ela e o proprio tenant.';
COMMENT ON COLUMN tenants.slug IS 'Identificador usado no subdominio (empresa.ponto.<dominio>). Imutavel na pratica.';
COMMENT ON COLUMN tenants.documento IS 'CNPJ do contratante do SaaS, que pode nao coincidir com nenhuma das empresas operacionais.';
COMMENT ON COLUMN tenants.dominio_proprio IS 'Dominio proprio para white label. Reservado para fase futura.';
COMMENT ON COLUMN tenants.limite_colaboradores IS 'Teto contratual de colaboradores ativos. NULL significa ilimitado.';
COMMENT ON COLUMN tenants.fuso_horario IS 'Fuso padrao do tenant. Unidades podem sobrescrever.';
COMMENT ON COLUMN tenants.excluido_em IS 'Soft delete. Tenant excluido nao e removido fisicamente por causa da retencao legal de 5 anos das marcacoes.';

CREATE UNIQUE INDEX ix_tenants_dominio_proprio ON tenants (dominio_proprio) WHERE dominio_proprio IS NOT NULL;
CREATE INDEX ix_tenants_status ON tenants (status) WHERE excluido_em IS NULL;

-- RLS da raiz e explicita porque a coluna de isolamento e "id", nao "tenant_id".
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_isolamento_tenant ON tenants
    USING      (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Resolucao de tenant por subdominio ANTES de existir contexto de tenant.
-- SECURITY DEFINER porque tenants esta sob RLS e, no momento do login, ainda
-- nao ha app.tenant_id definido. Expoe apenas quatro colunas: nao ha como
-- enumerar a base de clientes por aqui.
--
-- Aceita slug OU UUID em p_slug (RFC-004, corrigida pela RFC-009): o cabecalho
-- X-Tenant do contrato documenta os dois formatos. RFC-009: a primeira versao
-- desta funcao decidia qual comparacao usar com um guard de AND/OR
-- (`(regex AND t.id = p_slug::uuid) OR (NOT regex AND t.slug = p_slug)`),
-- assumindo que o PostgreSQL avalia os operandos de AND estritamente da
-- esquerda para a direita com curto-circuito -- o proprio manual do
-- PostgreSQL desmente isso (secao 4.2.14, "Expression Evaluation Rules"): a
-- ordem de avaliacao de sub-expressoes de AND/OR NAO e garantida, e o
-- planejador pode tentar o cast `p_slug::uuid` mesmo quando o regex e falso.
-- Isso quebrava a resolucao por slug (o caso comum) de forma intermitente,
-- dependente do plano escolhido -- reproduzido de forma deterministica contra
-- o Postgres 16 real assim que a tabela `tenants` tinha linhas suficientes
-- para o planejador preferir outro plano. A unica construcao com ordem de
-- avaliacao garantida pelo padrao SQL (e documentada como tal pelo proprio
-- manual do PostgreSQL, mesma secao) e CASE/WHEN: o cast so roda dentro do
-- ramo que o regex ja confirmou.
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
$$;

COMMENT ON FUNCTION fn_resolve_tenant(TEXT) IS
  'Unica porta de entrada para descobrir o tenant a partir do subdominio ou do cabecalho X-Tenant (slug ou UUID, RFC-004) antes de app.tenant_id existir.';


CREATE TABLE tenant_configuracoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    categoria      TEXT NOT NULL DEFAULT 'geral'
                   CHECK (categoria IN ('geral','seguranca','jornada','banco_horas','fiscal',
                                        'notificacao','integracao','lgpd','aparencia')),
    chave          TEXT NOT NULL,
    valor          JSONB NOT NULL,
    descricao      TEXT,
    somente_leitura BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_tenant_configuracoes UNIQUE (tenant_id, chave)
);

COMMENT ON TABLE tenant_configuracoes IS
  'Configuracoes chave/valor por tenant. Usada para parametros que nao merecem coluna propria (limiares, textos, feature flags).';
COMMENT ON COLUMN tenant_configuracoes.chave IS 'Chave hierarquica com ponto, por exemplo seguranca.mfa.obrigatorio.';
COMMENT ON COLUMN tenant_configuracoes.valor IS 'Valor em JSON. O tipo esperado por chave e documentado no catalogo de configuracoes da aplicacao.';
COMMENT ON COLUMN tenant_configuracoes.somente_leitura IS 'Quando verdadeiro, so o super admin da SEEG altera.';

CREATE INDEX ix_tenant_configuracoes_categoria ON tenant_configuracoes (tenant_id, categoria);


-- =============================================================================
-- 3. ORGANIZACAO
-- =============================================================================

CREATE TABLE empresas (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    matriz_id             UUID REFERENCES empresas (id) ON DELETE RESTRICT,
    tipo                  TEXT NOT NULL DEFAULT 'matriz' CHECK (tipo IN ('matriz','filial')),
    cnpj                  dom_cnpj NOT NULL,
    razao_social          TEXT NOT NULL,
    nome_fantasia         TEXT,
    inscricao_estadual    TEXT,
    inscricao_municipal   TEXT,
    cnae_principal        TEXT,
    cei_caepf             TEXT,
    natureza_juridica     TEXT,
    logradouro            TEXT,
    numero                TEXT,
    complemento           TEXT,
    bairro                TEXT,
    municipio             TEXT,
    uf                    dom_uf,
    cep                   dom_cep,
    codigo_ibge_municipio dom_ibge,
    telefone              TEXT,
    email                 dom_email,
    fuso_horario          dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    logo_ref              TEXT,
    ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID,
    CONSTRAINT ck_empresas_matriz CHECK (
        (tipo = 'matriz' AND matriz_id IS NULL) OR (tipo = 'filial' AND matriz_id IS NOT NULL)
    )
);

COMMENT ON TABLE empresas IS
  'Pessoa juridica empregadora dentro do tenant. Matriz e filiais sao linhas distintas ligadas por matriz_id, cada uma com seu proprio CNPJ e seus proprios arquivos fiscais.';
COMMENT ON COLUMN empresas.matriz_id IS 'Auto-referencia. NULL quando a empresa e matriz.';
COMMENT ON COLUMN empresas.cei_caepf IS 'CEI ou CAEPF quando aplicavel. Vai para o cabecalho do AFD de obras e produtores rurais.';
COMMENT ON COLUMN empresas.codigo_ibge_municipio IS 'Codigo IBGE do municipio sede. Usado para resolver feriados municipais.';
COMMENT ON COLUMN empresas.logo_ref IS 'Chave do objeto no MinIO. Nunca o binario no banco.';
COMMENT ON COLUMN empresas.ativo IS 'Desativa a empresa sem excluir. Empresa inativa nao aceita novas marcacoes.';

CREATE UNIQUE INDEX uq_empresas_cnpj ON empresas (tenant_id, cnpj) WHERE excluido_em IS NULL;
CREATE INDEX ix_empresas_tenant ON empresas (tenant_id) WHERE excluido_em IS NULL;
CREATE INDEX ix_empresas_matriz ON empresas (tenant_id, matriz_id);


CREATE TABLE unidades (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo                    TEXT NOT NULL,
    nome                      TEXT NOT NULL,
    tipo                      TEXT NOT NULL DEFAULT 'filial'
                              CHECK (tipo IN ('sede','filial','obra','cliente','home_office','movel','deposito')),
    logradouro                TEXT,
    numero                    TEXT,
    complemento               TEXT,
    bairro                    TEXT,
    municipio                 TEXT,
    uf                        dom_uf,
    cep                       dom_cep,
    codigo_ibge_municipio     dom_ibge,
    fuso_horario              dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    geocerca_latitude         NUMERIC(10,7),
    geocerca_longitude        NUMERIC(10,7),
    geocerca_raio_metros      INTEGER CHECK (geocerca_raio_metros > 0 AND geocerca_raio_metros <= 100000),
    geocerca_poligono         JSONB,
    geocerca_obrigatoria      BOOLEAN NOT NULL DEFAULT TRUE,
    geocerca_tolerancia_metros INTEGER NOT NULL DEFAULT 50 CHECK (geocerca_tolerancia_metros >= 0),
    ativo                     BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    excluido_em               TIMESTAMPTZ,
    excluido_por              UUID,
    CONSTRAINT ck_unidades_geocerca_ponto CHECK (
        (geocerca_latitude IS NULL AND geocerca_longitude IS NULL AND geocerca_raio_metros IS NULL)
        OR (geocerca_latitude IS NOT NULL AND geocerca_longitude IS NOT NULL AND geocerca_raio_metros IS NOT NULL)
    ),
    CONSTRAINT ck_unidades_latitude CHECK (geocerca_latitude IS NULL OR geocerca_latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_unidades_longitude CHECK (geocerca_longitude IS NULL OR geocerca_longitude BETWEEN -180 AND 180),
    CONSTRAINT ck_unidades_poligono CHECK (
        geocerca_poligono IS NULL OR jsonb_typeof(geocerca_poligono) = 'object'
    )
);

COMMENT ON TABLE unidades IS
  'Local fisico de trabalho de uma empresa. Carrega o fuso horario efetivo do calculo de jornada, a geocerca do registro por app e o conjunto de feriados aplicavel.';
COMMENT ON COLUMN unidades.codigo IS 'Codigo curto usado nas importacoes e nos relatorios. Unico por empresa.';
COMMENT ON COLUMN unidades.fuso_horario IS 'Fuso efetivo da apuracao. Sobrescreve o fuso da empresa e do tenant.';
COMMENT ON COLUMN unidades.geocerca_latitude IS 'Centro da geocerca circular, em graus decimais WGS84.';
COMMENT ON COLUMN unidades.geocerca_raio_metros IS 'Raio da geocerca circular em metros. Preenchido em conjunto com latitude e longitude.';
COMMENT ON COLUMN unidades.geocerca_poligono IS 'Geocerca poligonal em GeoJSON (objeto Polygon ou MultiPolygon). Quando presente, tem precedencia sobre a geocerca circular.';
COMMENT ON COLUMN unidades.geocerca_obrigatoria IS 'Quando falso, marcacao fora da cerca e aceita e sinalizada para tratamento do gestor (caso do trabalhador externo).';
COMMENT ON COLUMN unidades.geocerca_tolerancia_metros IS 'Folga somada ao raio para absorver imprecisao do GPS.';

CREATE UNIQUE INDEX uq_unidades_codigo ON unidades (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;
CREATE INDEX ix_unidades_empresa ON unidades (tenant_id, empresa_id) WHERE excluido_em IS NULL;
CREATE INDEX ix_unidades_municipio ON unidades (tenant_id, codigo_ibge_municipio);


CREATE TABLE redes_permitidas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id     UUID NOT NULL REFERENCES empresas (id) ON DELETE CASCADE,
    unidade_id     UUID REFERENCES unidades (id) ON DELETE CASCADE,
    cidr           CIDR NOT NULL,
    descricao      TEXT,
    canal          TEXT CHECK (canal IN ('web','mobile','totem','api','terminal')),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID
);

COMMENT ON TABLE redes_permitidas IS
  'Allowlist de faixas CIDR (IPv4 e IPv6) autorizadas a registrar ponto. Escopo por empresa e, opcionalmente, por unidade e por canal. Multiplas linhas por escopo cobrem multiplos links.';
COMMENT ON COLUMN redes_permitidas.unidade_id IS 'NULL aplica a faixa a toda a empresa.';
COMMENT ON COLUMN redes_permitidas.canal IS 'NULL aplica a faixa a todos os canais. Na pratica a restricao interessa ao canal web.';
COMMENT ON COLUMN redes_permitidas.cidr IS 'Faixa em notacao CIDR. O tipo CIDR do PostgreSQL aceita IPv4 e IPv6 e permite o operador de contencao >>=.';

CREATE UNIQUE INDEX uq_redes_permitidas ON redes_permitidas (
    tenant_id, empresa_id,
    COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(canal, '*'),
    cidr
);
CREATE INDEX ix_redes_permitidas_lookup ON redes_permitidas (tenant_id, empresa_id, unidade_id) WHERE ativo;


CREATE TABLE departamentos (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    departamento_pai_id       UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    responsavel_colaborador_id UUID,
    codigo                    TEXT NOT NULL,
    nome                      TEXT NOT NULL,
    descricao                 TEXT,
    ativo                     BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    excluido_em               TIMESTAMPTZ,
    excluido_por              UUID
);

COMMENT ON TABLE departamentos IS
  'Estrutura departamental hierarquica da empresa. Usada para escopo de perfil, agrupamento de relatorio e roteamento de aprovacao.';
COMMENT ON COLUMN departamentos.departamento_pai_id IS 'Auto-referencia que forma a arvore. NULL na raiz.';
COMMENT ON COLUMN departamentos.responsavel_colaborador_id IS 'Colaborador responsavel. FK criada apos a tabela colaboradores (secao 5).';

CREATE UNIQUE INDEX uq_departamentos_codigo ON departamentos (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;
CREATE INDEX ix_departamentos_pai ON departamentos (tenant_id, departamento_pai_id);


CREATE TABLE centros_custo (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id     UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    centro_custo_pai_id UUID REFERENCES centros_custo (id) ON DELETE RESTRICT,
    codigo         TEXT NOT NULL,
    nome           TEXT NOT NULL,
    descricao      TEXT,
    codigo_externo TEXT,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID
);

COMMENT ON TABLE centros_custo IS
  'Centro de custo, projeto ou cliente ao qual as horas sao apropriadas. Base do relatorio de horas por centro de custo e do rateio para a folha.';
COMMENT ON COLUMN centros_custo.codigo_externo IS 'Codigo correspondente no ERP ou no sistema de folha do cliente.';

CREATE UNIQUE INDEX uq_centros_custo_codigo ON centros_custo (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;
CREATE INDEX ix_centros_custo_pai ON centros_custo (tenant_id, centro_custo_pai_id);


CREATE TABLE cargos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id     UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo         TEXT NOT NULL,
    nome           TEXT NOT NULL,
    cbo            dom_cbo,
    descricao      TEXT,
    nivel          TEXT CHECK (nivel IN ('estagio','aprendiz','junior','pleno','senior','especialista',
                                         'coordenacao','gerencia','diretoria')),
    salario_base   NUMERIC(14,2) CHECK (salario_base IS NULL OR salario_base >= 0),
    cargo_confianca BOOLEAN NOT NULL DEFAULT FALSE,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID
);

COMMENT ON TABLE cargos IS 'Cargo ocupado pelo colaborador, com CBO para o eSocial.';
COMMENT ON COLUMN cargos.cbo IS 'Classificacao Brasileira de Ocupacoes, 6 digitos.';
COMMENT ON COLUMN cargos.cargo_confianca IS 'Indica cargo de gestao do art. 62, II da CLT. Sugere dispensa de controle de jornada, que ainda assim e decidida no contrato.';
COMMENT ON COLUMN cargos.salario_base IS 'Referencia salarial usada apenas no relatorio de custo de horas extras.';

CREATE UNIQUE INDEX uq_cargos_codigo ON cargos (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;
CREATE INDEX ix_cargos_empresa ON cargos (tenant_id, empresa_id) WHERE excluido_em IS NULL;


-- =============================================================================
-- 4. IDENTIDADE, ACESSO E RBAC
-- =============================================================================

CREATE TABLE usuarios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id      UUID,
    email               dom_email NOT NULL,
    email_verificado_em TIMESTAMPTZ,
    nome_completo       TEXT NOT NULL,
    telefone            TEXT,
    avatar_ref          TEXT,
    tipo                TEXT NOT NULL DEFAULT 'humano'
                        CHECK (tipo IN ('humano','servico','suporte')),
    status              TEXT NOT NULL DEFAULT 'convidado'
                        CHECK (status IN ('convidado','ativo','bloqueado','inativo')),
    idioma              TEXT NOT NULL DEFAULT 'pt-BR',
    fuso_horario        dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    mfa_obrigatorio     BOOLEAN NOT NULL DEFAULT FALSE,
    ultimo_acesso_em    TIMESTAMPTZ,
    ultimo_acesso_ip    INET,
    aceite_termos_em    TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID,
    excluido_em         TIMESTAMPTZ,
    excluido_por        UUID
);

COMMENT ON TABLE usuarios IS
  'Identidade de acesso ao sistema. Distinta de colaborador: nem todo colaborador tem usuario (quem so bate ponto no terminal nao precisa) e nem todo usuario e colaborador (suporte SEEG, integracoes).';
COMMENT ON COLUMN usuarios.colaborador_id IS 'Vinculo opcional com a pessoa. FK criada apos a tabela colaboradores (secao 5).';
COMMENT ON COLUMN usuarios.tipo IS 'humano: pessoa. servico: conta tecnica de integracao. suporte: operador da SEEG com acesso cross-tenant controlado por role de banco.';
COMMENT ON COLUMN usuarios.status IS 'convidado: criado e ainda sem primeiro acesso. bloqueado: barrado por seguranca. inativo: desligado.';
COMMENT ON COLUMN usuarios.mfa_obrigatorio IS 'Forca segundo fator neste usuario independentemente da politica do tenant.';

CREATE UNIQUE INDEX uq_usuarios_email ON usuarios (tenant_id, lower(email)) WHERE excluido_em IS NULL;
CREATE UNIQUE INDEX uq_usuarios_colaborador ON usuarios (tenant_id, colaborador_id) WHERE colaborador_id IS NOT NULL AND excluido_em IS NULL;
CREATE INDEX ix_usuarios_status ON usuarios (tenant_id, status) WHERE excluido_em IS NULL;


CREATE TABLE credenciais (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id                UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo                      TEXT NOT NULL
                              CHECK (tipo IN ('senha','pin','certificado','sso','recuperacao')),
    hash                      TEXT NOT NULL,
    algoritmo                 TEXT NOT NULL DEFAULT 'argon2id'
                              CHECK (algoritmo IN ('argon2id','bcrypt','scrypt','pbkdf2','nenhum')),
    provedor_sso              TEXT CHECK (provedor_sso IN ('google','entra_id','saml','okta')),
    identificador_externo     TEXT,
    trocar_no_proximo_acesso  BOOLEAN NOT NULL DEFAULT FALSE,
    expira_em                 TIMESTAMPTZ,
    tentativas_falhas         INTEGER NOT NULL DEFAULT 0 CHECK (tentativas_falhas >= 0),
    bloqueado_ate             TIMESTAMPTZ,
    ultima_troca_em           TIMESTAMPTZ,
    ativo                     BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID
);

COMMENT ON TABLE credenciais IS
  'Segredos de autenticacao do usuario. Uma linha ativa por tipo. Senhas em Argon2id; a coluna hash nunca guarda o segredo em claro.';
COMMENT ON COLUMN credenciais.tipo IS 'senha: acesso web e app. pin: quiosque e fallback do terminal. certificado: mTLS. sso: identidade federada. recuperacao: token de reset de uso unico.';
COMMENT ON COLUMN credenciais.identificador_externo IS 'Subject ou e-mail retornado pelo provedor de SSO.';
COMMENT ON COLUMN credenciais.tentativas_falhas IS 'Contador de falhas consecutivas. Base do bloqueio progressivo.';
COMMENT ON COLUMN credenciais.bloqueado_ate IS 'Instante ate o qual a credencial nao aceita tentativa. NULL quando liberada.';

CREATE UNIQUE INDEX uq_credenciais_ativa ON credenciais (tenant_id, usuario_id, tipo) WHERE ativo;
CREATE INDEX ix_credenciais_usuario ON credenciais (tenant_id, usuario_id);
CREATE INDEX ix_credenciais_sso ON credenciais (tenant_id, provedor_sso, identificador_externo) WHERE provedor_sso IS NOT NULL;


CREATE TABLE sessoes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id            UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    dispositivo_id        UUID,
    canal                 TEXT NOT NULL
                          CHECK (canal IN ('web','mobile','totem','api','terminal')),
    ip                    INET,
    user_agent            TEXT,
    fingerprint           TEXT,
    geolocalizacao        JSONB,
    iniciada_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultima_atividade_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em             TIMESTAMPTZ NOT NULL,
    encerrada_em          TIMESTAMPTZ,
    motivo_encerramento   TEXT CHECK (motivo_encerramento IN
                          ('logout','expiracao','inatividade','revogacao_admin','troca_senha',
                           'reuso_token','dispositivo_revogado')),
    mfa_validado_em       TIMESTAMPTZ,
    reautenticado_em      TIMESTAMPTZ,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT ck_sessoes_expiracao CHECK (expira_em > iniciada_em)
);

COMMENT ON TABLE sessoes IS
  'Sessao de acesso ativa ou encerrada. Uma sessao agrupa a familia de refresh tokens e permite revogacao em massa por usuario ou por dispositivo.';
COMMENT ON COLUMN sessoes.dispositivo_id IS 'Dispositivo de origem. FK criada apos a tabela dispositivos (secao 6).';
COMMENT ON COLUMN sessoes.fingerprint IS 'Impressao digital do navegador ou do aparelho, usada como sinal antifraude.';
COMMENT ON COLUMN sessoes.reautenticado_em IS 'Ultima reautenticacao explicita. O registro de ponto pela web exige reautenticacao recente mesmo com sessao valida.';

CREATE INDEX ix_sessoes_usuario ON sessoes (tenant_id, usuario_id, iniciada_em DESC);
CREATE INDEX ix_sessoes_ativas ON sessoes (tenant_id, expira_em) WHERE encerrada_em IS NULL;
CREATE INDEX ix_sessoes_dispositivo ON sessoes (tenant_id, dispositivo_id) WHERE dispositivo_id IS NOT NULL;


CREATE TABLE refresh_tokens (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id         UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    sessao_id          UUID NOT NULL REFERENCES sessoes (id) ON DELETE CASCADE,
    familia_id         UUID NOT NULL,
    antecessor_id      UUID REFERENCES refresh_tokens (id) ON DELETE SET NULL,
    token_hash         dom_sha256 NOT NULL,
    emitido_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em          TIMESTAMPTZ NOT NULL,
    usado_em           TIMESTAMPTZ,
    revogado_em        TIMESTAMPTZ,
    motivo_revogacao   TEXT CHECK (motivo_revogacao IN
                       ('rotacao','logout','reuso_detectado','expiracao','revogacao_admin','troca_senha')),
    ip                 INET,
    user_agent         TEXT,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por         UUID,
    atualizado_em      TIMESTAMPTZ,
    atualizado_por     UUID,
    CONSTRAINT uq_refresh_tokens_hash UNIQUE (tenant_id, token_hash)
);

COMMENT ON TABLE refresh_tokens IS
  'Refresh tokens com rotacao. Cada uso emite um novo token e marca o anterior como usado. Reapresentar um token ja usado invalida a familia inteira (deteccao de reuso).';
COMMENT ON COLUMN refresh_tokens.familia_id IS 'Identificador da cadeia de rotacao. Revogar a familia derruba todos os descendentes de um mesmo login.';
COMMENT ON COLUMN refresh_tokens.antecessor_id IS 'Token que originou este por rotacao. Permite reconstruir a cadeia na investigacao de incidente.';
COMMENT ON COLUMN refresh_tokens.token_hash IS 'SHA-256 do token. O valor em claro so existe no cliente.';
COMMENT ON COLUMN refresh_tokens.usado_em IS 'Marcado na primeira troca. Segunda apresentacao com este campo preenchido caracteriza reuso.';

CREATE INDEX ix_refresh_tokens_familia ON refresh_tokens (tenant_id, familia_id);
CREATE INDEX ix_refresh_tokens_usuario ON refresh_tokens (tenant_id, usuario_id, emitido_em DESC);
CREATE INDEX ix_refresh_tokens_validos ON refresh_tokens (tenant_id, expira_em) WHERE revogado_em IS NULL AND usado_em IS NULL;


CREATE TABLE mfa_dispositivos (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id        UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo              TEXT NOT NULL
                      CHECK (tipo IN ('totp','sms','email','webauthn','codigos_backup')),
    rotulo            TEXT NOT NULL,
    segredo_cifrado   BYTEA,
    iv                BYTEA,
    chave_id          TEXT,
    credencial_publica BYTEA,
    contador          BIGINT NOT NULL DEFAULT 0,
    confirmado_em     TIMESTAMPTZ,
    ultimo_uso_em     TIMESTAMPTZ,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID
);

COMMENT ON TABLE mfa_dispositivos IS
  'Segundo fator registrado pelo usuario. O segredo TOTP e guardado cifrado com chave externa ao banco.';
COMMENT ON COLUMN mfa_dispositivos.segredo_cifrado IS 'Segredo TOTP ou lista de codigos de backup, cifrado em AES-256-GCM.';
COMMENT ON COLUMN mfa_dispositivos.chave_id IS 'Identificador da chave de cifra no cofre externo. O banco nunca guarda a chave.';
COMMENT ON COLUMN mfa_dispositivos.credencial_publica IS 'Chave publica da credencial WebAuthn.';
COMMENT ON COLUMN mfa_dispositivos.contador IS 'Contador anti-replay do autenticador WebAuthn.';
COMMENT ON COLUMN mfa_dispositivos.confirmado_em IS 'Preenchido apos o usuario provar posse do fator. Fator nao confirmado nao autentica.';

CREATE INDEX ix_mfa_dispositivos_usuario ON mfa_dispositivos (tenant_id, usuario_id) WHERE ativo;


CREATE TABLE perfis (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo         TEXT NOT NULL,
    nome           TEXT NOT NULL,
    descricao      TEXT,
    sistema        BOOLEAN NOT NULL DEFAULT FALSE,
    escopo_padrao  TEXT NOT NULL DEFAULT 'tenant'
                   CHECK (escopo_padrao IN ('global','tenant','empresa','unidade','departamento','equipe','proprio')),
    somente_leitura BOOLEAN NOT NULL DEFAULT FALSE,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID
);

COMMENT ON TABLE perfis IS
  'Papel do RBAC. Os perfis de fabrica sao super_admin, admin_empresa, rh, gestor, colaborador, auditor e integracao; o tenant pode criar os seus.';
COMMENT ON COLUMN perfis.sistema IS 'Perfil de fabrica, semeado em todo tenant. Nao pode ser excluido.';
COMMENT ON COLUMN perfis.escopo_padrao IS 'Alcance sugerido ao atribuir o perfil. proprio significa que o usuario so enxerga o proprio dado.';
COMMENT ON COLUMN perfis.somente_leitura IS 'Perfil que nunca recebe permissao de escrita, como auditor e fiscal.';

CREATE UNIQUE INDEX uq_perfis_codigo ON perfis (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE permissoes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo        TEXT NOT NULL,
    recurso       TEXT NOT NULL,
    acao          TEXT NOT NULL
                  CHECK (acao IN ('ler','criar','editar','excluir','aprovar','exportar',
                                  'executar','assinar','administrar',
                                  'configurar','reabrir','ler_sensivel')),
    descricao     TEXT NOT NULL,
    sensivel      BOOLEAN NOT NULL DEFAULT FALSE,
    modulo        TEXT NOT NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por    UUID,
    atualizado_em TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_permissoes_codigo UNIQUE (codigo),
    CONSTRAINT uq_permissoes_recurso_acao UNIQUE (recurso, acao)
);

COMMENT ON TABLE permissoes IS
  'Catalogo GLOBAL de permissoes do produto (recurso mais acao). Unica tabela sem tenant_id alem de tenants: as permissoes correspondem a endpoints do codigo, sao identicas em todos os tenants e sao somente leitura para a aplicacao. Divergencia documentada no glossario.';
COMMENT ON COLUMN permissoes.codigo IS 'Identificador estavel usado no codigo e no OpenAPI, por exemplo marcacoes.ler.';
COMMENT ON COLUMN permissoes.sensivel IS 'Quando verdadeira, todo exercicio da permissao gera linha em acessos_dados_sensiveis (LGPD).';
COMMENT ON COLUMN permissoes.modulo IS 'Modulo funcional ao qual a permissao pertence, para agrupar a tela de perfis.';

CREATE INDEX ix_permissoes_modulo ON permissoes (modulo, recurso);


CREATE TABLE perfil_permissoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    perfil_id      UUID NOT NULL REFERENCES perfis (id) ON DELETE CASCADE,
    permissao_id   UUID NOT NULL REFERENCES permissoes (id) ON DELETE CASCADE,
    concedida      BOOLEAN NOT NULL DEFAULT TRUE,
    condicao       JSONB,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_perfil_permissoes UNIQUE (tenant_id, perfil_id, permissao_id)
);

COMMENT ON TABLE perfil_permissoes IS
  'Associacao entre perfil e permissao. A linha com concedida = false serve para negar explicitamente uma permissao herdada de um perfil de fabrica.';
COMMENT ON COLUMN perfil_permissoes.condicao IS 'Restricao adicional em JSON, por exemplo limitar a exportacao a periodos ja fechados.';

CREATE INDEX ix_perfil_permissoes_perfil ON perfil_permissoes (tenant_id, perfil_id);


CREATE TABLE usuario_perfis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id      UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    perfil_id       UUID NOT NULL REFERENCES perfis (id) ON DELETE RESTRICT,
    escopo_tipo     TEXT NOT NULL DEFAULT 'tenant'
                    CHECK (escopo_tipo IN ('tenant','empresa','unidade','departamento','equipe','proprio')),
    empresa_id      UUID REFERENCES empresas (id) ON DELETE CASCADE,
    unidade_id      UUID REFERENCES unidades (id) ON DELETE CASCADE,
    departamento_id UUID REFERENCES departamentos (id) ON DELETE CASCADE,
    equipe_id       UUID,
    incluir_subordinados BOOLEAN NOT NULL DEFAULT TRUE,
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim    DATE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID,
    CONSTRAINT ck_usuario_perfis_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ck_usuario_perfis_escopo CHECK (
        (escopo_tipo = 'empresa'      AND empresa_id      IS NOT NULL) OR
        (escopo_tipo = 'unidade'      AND unidade_id      IS NOT NULL) OR
        (escopo_tipo = 'departamento' AND departamento_id IS NOT NULL) OR
        (escopo_tipo = 'equipe'       AND equipe_id       IS NOT NULL) OR
        (escopo_tipo IN ('tenant','proprio'))
    )
);

COMMENT ON TABLE usuario_perfis IS
  'Atribuicao de perfil a usuario COM ESCOPO. O mesmo usuario pode ser gestor de uma unidade e colaborador comum no resto da empresa.';
COMMENT ON COLUMN usuario_perfis.escopo_tipo IS 'Define qual coluna de escopo e obrigatoria. proprio restringe ao proprio colaborador do usuario.';
COMMENT ON COLUMN usuario_perfis.equipe_id IS 'Equipe do escopo. FK criada apos a tabela equipes (secao 5).';
COMMENT ON COLUMN usuario_perfis.incluir_subordinados IS 'Quando verdadeiro, o escopo desce pela arvore de departamentos e pela hierarquia de gestores.';
COMMENT ON COLUMN usuario_perfis.vigencia_fim IS 'NULL significa vigencia aberta. Usado tambem para atribuicao temporaria sem delegacao formal.';

CREATE UNIQUE INDEX uq_usuario_perfis ON usuario_perfis (
    tenant_id, usuario_id, perfil_id, escopo_tipo,
    COALESCE(empresa_id,      '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(unidade_id,      '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(departamento_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(equipe_id,       '00000000-0000-0000-0000-000000000000'::uuid),
    vigencia_inicio
);
CREATE INDEX ix_usuario_perfis_usuario ON usuario_perfis (tenant_id, usuario_id);
CREATE INDEX ix_usuario_perfis_vigentes ON usuario_perfis (tenant_id, usuario_id, vigencia_inicio, vigencia_fim);


CREATE TABLE delegacoes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    delegante_usuario_id  UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    delegado_usuario_id   UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    perfil_id             UUID REFERENCES perfis (id) ON DELETE RESTRICT,
    motivo                TEXT NOT NULL,
    escopo                JSONB,
    inicio_em             TIMESTAMPTZ NOT NULL,
    fim_em                TIMESTAMPTZ NOT NULL,
    status                TEXT NOT NULL DEFAULT 'agendada'
                          CHECK (status IN ('agendada','ativa','encerrada','cancelada')),
    revogada_em           TIMESTAMPTZ,
    revogada_por          UUID,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT ck_delegacoes_periodo CHECK (fim_em > inicio_em),
    CONSTRAINT ck_delegacoes_pessoas CHECK (delegante_usuario_id <> delegado_usuario_id),
    CONSTRAINT ex_delegacoes_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        delegante_usuario_id WITH =,
        delegado_usuario_id WITH =,
        tstzrange(inicio_em, fim_em) WITH &&
    ) WHERE (status IN ('agendada','ativa'))
);

COMMENT ON TABLE delegacoes IS
  'Delegacao temporaria de atribuicoes, tipicamente ferias do gestor. Enquanto vigente, o delegado herda o escopo do delegante para aprovacoes. Toda acao exercida por delegacao e marcada como tal na auditoria.';
COMMENT ON COLUMN delegacoes.escopo IS 'Restricao opcional em JSON, por exemplo limitar a delegacao a solicitacoes de ajuste de ponto.';
COMMENT ON CONSTRAINT ex_delegacoes_sobreposicao ON delegacoes IS
  'Impede duas delegacoes vigentes sobrepostas entre o mesmo par de usuarios.';

CREATE INDEX ix_delegacoes_delegado ON delegacoes (tenant_id, delegado_usuario_id, status);
CREATE INDEX ix_delegacoes_periodo ON delegacoes (tenant_id, inicio_em, fim_em) WHERE status IN ('agendada','ativa');


-- =============================================================================
-- 5. PESSOAS
-- =============================================================================

CREATE TABLE colaboradores (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id            UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    matricula             TEXT NOT NULL,
    cpf                   dom_cpf NOT NULL,
    pis_nit               dom_pis,
    nome_completo         TEXT NOT NULL,
    nome_social           TEXT,
    data_nascimento       DATE,
    sexo                  TEXT CHECK (sexo IN ('feminino','masculino','outro','nao_informado')),
    estado_civil          TEXT CHECK (estado_civil IN ('solteiro','casado','divorciado','viuvo','uniao_estavel','separado')),
    nacionalidade         TEXT,
    naturalidade          TEXT,
    nome_mae              TEXT,
    rg_numero             TEXT,
    rg_orgao_emissor      TEXT,
    rg_uf                 dom_uf,
    ctps_numero           TEXT,
    ctps_serie            TEXT,
    ctps_uf               dom_uf,
    titulo_eleitor        TEXT,
    email                 dom_email,
    telefone              TEXT,
    telefone_alternativo  TEXT,
    foto_ref              TEXT,
    logradouro            TEXT,
    numero                TEXT,
    complemento           TEXT,
    bairro                TEXT,
    municipio             TEXT,
    uf                    dom_uf,
    cep                   dom_cep,
    codigo_ibge_municipio dom_ibge,
    status                TEXT NOT NULL DEFAULT 'ativo'
                          CHECK (status IN ('pre_admissao','ativo','afastado','ferias','suspenso','desligado')),
    data_admissao         DATE,
    data_desligamento     DATE,
    pcd                   BOOLEAN NOT NULL DEFAULT FALSE,
    observacoes           TEXT,
    codigo_externo        TEXT,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID,
    CONSTRAINT ck_colaboradores_desligamento CHECK (
        data_desligamento IS NULL OR data_admissao IS NULL OR data_desligamento >= data_admissao
    )
);

COMMENT ON TABLE colaboradores IS
  'A PESSOA que trabalha. Guarda os dados cadastrais e pessoais. As condicoes de trabalho vivem em contratos e vinculos; um colaborador pode ter mais de um vinculo simultaneo.';
COMMENT ON COLUMN colaboradores.matricula IS 'Matricula interna da empresa, usada no terminal, no quiosque e nos relatorios. Unica por empresa.';
COMMENT ON COLUMN colaboradores.cpf IS 'CPF sem pontuacao. Vai literalmente para o registro tipo 7 do AFD.';
COMMENT ON COLUMN colaboradores.pis_nit IS 'PIS, PASEP ou NIT. Exigido pelos leiautes fiscais e pela folha.';
COMMENT ON COLUMN colaboradores.nome_social IS 'Nome social. Quando preenchido, e o nome exibido em toda a interface.';
COMMENT ON COLUMN colaboradores.foto_ref IS 'Chave da foto cadastral no MinIO. NAO e template biometrico.';
COMMENT ON COLUMN colaboradores.status IS 'Situacao consolidada da pessoa, derivada dos vinculos e afastamentos vigentes.';
COMMENT ON COLUMN colaboradores.pcd IS 'Pessoa com deficiencia. Influencia cota legal e relatorios, nao o calculo de jornada.';
COMMENT ON COLUMN colaboradores.codigo_externo IS 'Chave correspondente no ERP ou na folha, preenchida pelos importadores.';

CREATE UNIQUE INDEX uq_colaboradores_matricula ON colaboradores (tenant_id, empresa_id, matricula) WHERE excluido_em IS NULL;
CREATE UNIQUE INDEX uq_colaboradores_cpf ON colaboradores (tenant_id, empresa_id, cpf) WHERE excluido_em IS NULL;
CREATE INDEX ix_colaboradores_empresa_status ON colaboradores (tenant_id, empresa_id, status) WHERE excluido_em IS NULL;
CREATE INDEX ix_colaboradores_cpf ON colaboradores (tenant_id, cpf);
CREATE INDEX ix_colaboradores_nome_trgm ON colaboradores USING gin (nome_completo gin_trgm_ops);


CREATE TABLE contratos (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id           UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    empresa_id               UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    numero                   TEXT,
    tipo                     TEXT NOT NULL
                             CHECK (tipo IN ('clt','aprendiz','estagio','temporario','intermitente',
                                             'avulso','autonomo','pj','socio','servidor')),
    regime_jornada           TEXT NOT NULL DEFAULT 'fixa'
                             CHECK (regime_jornada IN ('fixa','flexivel','livre','escala','12x36',
                                                       'parcial','teletrabalho','externo','sobreaviso')),
    cargo_id                 UUID REFERENCES cargos (id) ON DELETE RESTRICT,
    departamento_id          UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    centro_custo_id          UUID REFERENCES centros_custo (id) ON DELETE RESTRICT,
    unidade_id               UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    data_inicio              DATE NOT NULL,
    data_fim                 DATE,
    experiencia_dias         INTEGER CHECK (experiencia_dias IS NULL OR experiencia_dias BETWEEN 0 AND 90),
    salario                  NUMERIC(14,2) CHECK (salario IS NULL OR salario >= 0),
    tipo_salario             TEXT CHECK (tipo_salario IN ('mensal','horista','diarista','semanal','comissionado','tarefa')),
    carga_horaria_semanal_minutos INTEGER CHECK (carga_horaria_semanal_minutos IS NULL OR carga_horaria_semanal_minutos BETWEEN 0 AND 4200),
    carga_horaria_mensal_minutos  INTEGER CHECK (carga_horaria_mensal_minutos IS NULL OR carga_horaria_mensal_minutos >= 0),
    controle_jornada         BOOLEAN NOT NULL DEFAULT TRUE,
    dispensa_controle_motivo TEXT CHECK (dispensa_controle_motivo IN
                             ('art62_i_externo','art62_ii_gestao','art62_iii_teletrabalho')),
    status                   TEXT NOT NULL DEFAULT 'ativo'
                             CHECK (status IN ('rascunho','ativo','suspenso','encerrado')),
    motivo_encerramento      TEXT,
    documento_id             UUID,
    criado_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por               UUID,
    atualizado_em            TIMESTAMPTZ,
    atualizado_por           UUID,
    excluido_em              TIMESTAMPTZ,
    excluido_por             UUID,
    CONSTRAINT ck_contratos_periodo CHECK (data_fim IS NULL OR data_fim >= data_inicio),
    CONSTRAINT ck_contratos_dispensa CHECK (
        (controle_jornada = TRUE  AND dispensa_controle_motivo IS NULL) OR
        (controle_jornada = FALSE AND dispensa_controle_motivo IS NOT NULL)
    )
);

COMMENT ON TABLE contratos IS
  'Instrumento juridico entre colaborador e empresa: tipo de contratacao, cargo, remuneracao, carga contratada e vigencia. Um contrato origina um vinculo, que e o objeto usado pelo motor de jornada.';
COMMENT ON COLUMN contratos.regime_jornada IS 'Regime contratado. Determina qual estrategia o resolvedor de jornada aplica.';
COMMENT ON COLUMN contratos.controle_jornada IS 'FALSE dispensa o controle de ponto (art. 62 da CLT). Nesse caso nao ha apuracao nem ocorrencia de falta.';
COMMENT ON COLUMN contratos.dispensa_controle_motivo IS 'Fundamento legal da dispensa. Obrigatorio quando controle_jornada e falso.';
COMMENT ON COLUMN contratos.carga_horaria_semanal_minutos IS 'Carga contratada por semana em minutos. 44 horas equivalem a 2640.';
COMMENT ON COLUMN contratos.documento_id IS 'Documento digitalizado do contrato. FK criada apos a tabela documentos.';

CREATE INDEX ix_contratos_colaborador ON contratos (tenant_id, colaborador_id) WHERE excluido_em IS NULL;
CREATE INDEX ix_contratos_vigentes ON contratos (tenant_id, empresa_id, data_inicio, data_fim) WHERE status = 'ativo';


CREATE TABLE vinculos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id      UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    empresa_id          UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    contrato_id         UUID REFERENCES contratos (id) ON DELETE RESTRICT,
    matricula_esocial   TEXT NOT NULL,
    categoria_esocial   SMALLINT,
    tipo_vinculo        TEXT NOT NULL DEFAULT 'empregado'
                        CHECK (tipo_vinculo IN ('empregado','estagiario','aprendiz','temporario',
                                                'avulso','autonomo','cooperado','diretor','servidor')),
    unidade_id          UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    departamento_id     UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    centro_custo_id     UUID REFERENCES centros_custo (id) ON DELETE RESTRICT,
    cargo_id            UUID REFERENCES cargos (id) ON DELETE RESTRICT,
    data_inicio         DATE NOT NULL,
    data_fim            DATE,
    motivo_desligamento TEXT,
    principal           BOOLEAN NOT NULL DEFAULT TRUE,
    apura_ponto         BOOLEAN NOT NULL DEFAULT TRUE,
    status              TEXT NOT NULL DEFAULT 'ativo'
                        CHECK (status IN ('ativo','suspenso','encerrado')),
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID,
    excluido_em         TIMESTAMPTZ,
    excluido_por        UUID,
    CONSTRAINT ck_vinculos_periodo CHECK (data_fim IS NULL OR data_fim >= data_inicio),
    CONSTRAINT ex_vinculos_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        colaborador_id WITH =,
        empresa_id WITH =,
        daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]') WITH &&
    ) WHERE (excluido_em IS NULL AND status <> 'encerrado')
);

COMMENT ON TABLE vinculos IS
  'A RELACAO DE TRABALHO efetiva, na granularidade que o AEJ e o eSocial exigem. E a chave de apuracao: toda apuracao de dia, escala, jornada vigente e conta de banco de horas pendura em um vinculo, nao no colaborador.';
COMMENT ON COLUMN vinculos.matricula_esocial IS 'Matricula do vinculo no eSocial. Vai para o registro de vinculo do AEJ. Unica por empresa.';
COMMENT ON COLUMN vinculos.categoria_esocial IS 'Codigo de categoria do trabalhador na tabela 01 do eSocial, por exemplo 101 para empregado geral.';
COMMENT ON COLUMN vinculos.principal IS 'Marca o vinculo principal quando o colaborador tem mais de um simultaneo.';
COMMENT ON COLUMN vinculos.apura_ponto IS 'Quando falso, o vinculo existe para folha mas nao entra no motor de apuracao.';
COMMENT ON CONSTRAINT ex_vinculos_sobreposicao ON vinculos IS
  'Impede dois vinculos ativos sobrepostos do mesmo colaborador na mesma empresa. Vinculos em empresas diferentes do mesmo tenant sao permitidos.';

CREATE UNIQUE INDEX uq_vinculos_matricula_esocial ON vinculos (tenant_id, empresa_id, matricula_esocial) WHERE excluido_em IS NULL;
CREATE INDEX ix_vinculos_colaborador ON vinculos (tenant_id, colaborador_id) WHERE excluido_em IS NULL;
CREATE INDEX ix_vinculos_apuracao ON vinculos (tenant_id, empresa_id, status, data_inicio, data_fim) WHERE apura_ponto;
CREATE INDEX ix_vinculos_unidade ON vinculos (tenant_id, unidade_id) WHERE status = 'ativo';


CREATE TABLE colaborador_gestores (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id        UUID NOT NULL REFERENCES colaboradores (id) ON DELETE CASCADE,
    gestor_colaborador_id UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    tipo                  TEXT NOT NULL DEFAULT 'imediato'
                          CHECK (tipo IN ('imediato','substituto','matricial','rh')),
    vigencia_inicio       DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim          DATE,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT ck_colaborador_gestores_distintos CHECK (colaborador_id <> gestor_colaborador_id),
    CONSTRAINT ck_colaborador_gestores_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ex_colaborador_gestores_imediato EXCLUDE USING gist (
        tenant_id WITH =,
        colaborador_id WITH =,
        daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]') WITH &&
    ) WHERE (tipo = 'imediato')
);

COMMENT ON TABLE colaborador_gestores IS
  'Hierarquia de gestao com historico. Define a arvore de subordinados que o perfil gestor enxerga e a cadeia de aprovacao das solicitacoes.';
COMMENT ON COLUMN colaborador_gestores.tipo IS 'imediato: um so por periodo. substituto: assume nas ausencias. matricial: gestor de projeto sem exclusividade. rh: analista responsavel.';
COMMENT ON CONSTRAINT ex_colaborador_gestores_imediato ON colaborador_gestores IS
  'Garante um unico gestor imediato vigente por colaborador em qualquer data.';

CREATE INDEX ix_colaborador_gestores_gestor ON colaborador_gestores (tenant_id, gestor_colaborador_id, vigencia_inicio, vigencia_fim);
CREATE INDEX ix_colaborador_gestores_colaborador ON colaborador_gestores (tenant_id, colaborador_id);


CREATE TABLE equipes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id            UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id            UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    departamento_id       UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    gestor_colaborador_id UUID REFERENCES colaboradores (id) ON DELETE SET NULL,
    codigo                TEXT NOT NULL,
    nome                  TEXT NOT NULL,
    descricao             TEXT,
    cor                   TEXT CHECK (cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'),
    ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID
);

COMMENT ON TABLE equipes IS
  'Agrupamento operacional de colaboradores para escala, cobertura de turno e visao do gestor. Ortogonal ao departamento: uma equipe pode cruzar departamentos.';
COMMENT ON COLUMN equipes.cor IS 'Cor em hexadecimal usada na grade de escala do painel.';

CREATE UNIQUE INDEX uq_equipes_codigo ON equipes (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;
CREATE INDEX ix_equipes_gestor ON equipes (tenant_id, gestor_colaborador_id);


CREATE TABLE equipe_membros (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    equipe_id       UUID NOT NULL REFERENCES equipes (id) ON DELETE CASCADE,
    colaborador_id  UUID NOT NULL REFERENCES colaboradores (id) ON DELETE CASCADE,
    papel           TEXT NOT NULL DEFAULT 'membro'
                    CHECK (papel IN ('membro','lider','substituto')),
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim    DATE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID,
    CONSTRAINT ck_equipe_membros_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ex_equipe_membros_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        equipe_id WITH =,
        colaborador_id WITH =,
        daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]') WITH &&
    )
);

COMMENT ON TABLE equipe_membros IS 'Participacao datada de um colaborador em uma equipe.';
COMMENT ON COLUMN equipe_membros.papel IS 'lider e substituto participam da cadeia de aprovacao da equipe.';

CREATE INDEX ix_equipe_membros_colaborador ON equipe_membros (tenant_id, colaborador_id);
CREATE INDEX ix_equipe_membros_equipe ON equipe_membros (tenant_id, equipe_id, vigencia_inicio);


CREATE TABLE documentos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id UUID REFERENCES colaboradores (id) ON DELETE CASCADE,
    vinculo_id     UUID REFERENCES vinculos (id) ON DELETE CASCADE,
    empresa_id     UUID REFERENCES empresas (id) ON DELETE CASCADE,
    tipo           TEXT NOT NULL
                   CHECK (tipo IN ('rg','cpf','ctps','comprovante_residencia','atestado','contrato',
                                   'acordo_banco_horas','acordo_compensacao','termo_consentimento',
                                   'certificado','aso','advertencia','rescisao','outro')),
    nome_arquivo   TEXT NOT NULL,
    conteudo_ref   TEXT NOT NULL,
    mime_type      TEXT,
    tamanho_bytes  BIGINT CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    hash_sha256    dom_sha256,
    data_emissao   DATE,
    data_validade  DATE,
    confidencial   BOOLEAN NOT NULL DEFAULT FALSE,
    descricao      TEXT,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID,
    CONSTRAINT ck_documentos_alvo CHECK (
        colaborador_id IS NOT NULL OR vinculo_id IS NOT NULL OR empresa_id IS NOT NULL
    )
);

COMMENT ON TABLE documentos IS
  'Documentos digitalizados de pessoas, vinculos e empresas. O binario fica no MinIO; aqui ficam metadados, hash e classificacao de confidencialidade.';
COMMENT ON COLUMN documentos.conteudo_ref IS 'Chave do objeto no MinIO. O banco nunca guarda o binario.';
COMMENT ON COLUMN documentos.hash_sha256 IS 'Hash do arquivo, para provar integridade em fiscalizacao ou litigio.';
COMMENT ON COLUMN documentos.confidencial IS 'Quando verdadeiro, a leitura gera registro em acessos_dados_sensiveis (atestado tem dado de saude).';
COMMENT ON COLUMN documentos.data_validade IS 'Vencimento do documento, por exemplo ASO. Alimenta alertas do RH.';

CREATE INDEX ix_documentos_colaborador ON documentos (tenant_id, colaborador_id, tipo) WHERE excluido_em IS NULL;
CREATE INDEX ix_documentos_validade ON documentos (tenant_id, data_validade) WHERE data_validade IS NOT NULL AND excluido_em IS NULL;


-- Chaves estrangeiras adiadas do bloco de identidade e organizacao,
-- criadas aqui porque as tabelas de destino so existem a partir desta secao.
ALTER TABLE usuarios
    ADD CONSTRAINT fk_usuarios_colaborador
    FOREIGN KEY (colaborador_id) REFERENCES colaboradores (id) ON DELETE SET NULL;

ALTER TABLE departamentos
    ADD CONSTRAINT fk_departamentos_responsavel
    FOREIGN KEY (responsavel_colaborador_id) REFERENCES colaboradores (id) ON DELETE SET NULL;

ALTER TABLE usuario_perfis
    ADD CONSTRAINT fk_usuario_perfis_equipe
    FOREIGN KEY (equipe_id) REFERENCES equipes (id) ON DELETE CASCADE;

ALTER TABLE contratos
    ADD CONSTRAINT fk_contratos_documento
    FOREIGN KEY (documento_id) REFERENCES documentos (id) ON DELETE SET NULL;


-- =============================================================================
-- 6. BIOMETRIA E DISPOSITIVOS
-- =============================================================================

CREATE TABLE biometrias (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id     UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    modalidade         TEXT NOT NULL DEFAULT 'facial'
                       CHECK (modalidade IN ('facial','digital','cartao','pin','qrcode')),
    status             TEXT NOT NULL DEFAULT 'pendente'
                       CHECK (status IN ('pendente','ativa','reprovada','revogada','expirada')),
    origem_cadastro    TEXT NOT NULL
                       CHECK (origem_cadastro IN ('terminal','app','web','importacao','rh')),
    qualidade          NUMERIC(5,2) CHECK (qualidade IS NULL OR qualidade BETWEEN 0 AND 100),
    consentimento_id   UUID,
    identificador_cartao TEXT,
    cadastrada_em      TIMESTAMPTZ,
    cadastrada_por     UUID,
    validada_em        TIMESTAMPTZ,
    validada_por       UUID,
    revogada_em        TIMESTAMPTZ,
    motivo_revogacao   TEXT,
    expira_em          TIMESTAMPTZ,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por         UUID,
    atualizado_em      TIMESTAMPTZ,
    atualizado_por     UUID
);

COMMENT ON TABLE biometrias IS
  'Credencial biometrica ou equivalente de um colaborador. Guarda o ciclo de vida (cadastro, validacao pelo RH, revogacao, expurgo); o vetor em si fica em biometria_templates.';
COMMENT ON COLUMN biometrias.modalidade IS 'facial e a modalidade principal. cartao, pin e qrcode existem como fallback obrigatorio quando o motor facial falha.';
COMMENT ON COLUMN biometrias.consentimento_id IS 'Consentimento LGPD que autoriza o tratamento. FK criada na secao de LGPD. Biometria facial sem consentimento vigente nao pode ser usada.';
COMMENT ON COLUMN biometrias.qualidade IS 'Qualidade da captura no cadastro, de 0 a 100. Abaixo do limiar o RH deve solicitar recadastro.';
COMMENT ON COLUMN biometrias.expira_em IS 'Data de expurgo programado, alimentada pela politica de retencao.';

CREATE UNIQUE INDEX uq_biometrias_ativa ON biometrias (tenant_id, colaborador_id, modalidade) WHERE status = 'ativa';
CREATE INDEX ix_biometrias_colaborador ON biometrias (tenant_id, colaborador_id);
CREATE INDEX ix_biometrias_expurgo ON biometrias (tenant_id, expira_em) WHERE expira_em IS NOT NULL;


CREATE TABLE biometria_templates (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    biometria_id      UUID NOT NULL REFERENCES biometrias (id) ON DELETE CASCADE,
    versao_modelo     TEXT NOT NULL,
    provedor          TEXT NOT NULL DEFAULT 'facial-svc',
    dimensao          INTEGER CHECK (dimensao IS NULL OR dimensao > 0),
    template_cifrado  BYTEA NOT NULL,
    iv                BYTEA NOT NULL,
    tag_autenticacao  BYTEA,
    algoritmo_cifra   TEXT NOT NULL DEFAULT 'AES-256-GCM'
                      CHECK (algoritmo_cifra IN ('AES-256-GCM','AES-256-CBC','ChaCha20-Poly1305')),
    chave_id          TEXT NOT NULL,
    hash_template     dom_sha256,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    gerado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID,
    CONSTRAINT uq_biometria_templates_versao UNIQUE (tenant_id, biometria_id, versao_modelo)
);

COMMENT ON TABLE biometria_templates IS
  'Vetor biometrico CIFRADO. Dado pessoal sensivel (LGPD art. 5, II). Versionado por modelo para permitir trocar o motor facial sem perder rastreabilidade nem forcar recadastro geral.';
COMMENT ON COLUMN biometria_templates.versao_modelo IS 'Identificador do modelo que gerou o vetor, por exemplo arcface-r100-v1. Templates de versoes diferentes nao sao comparaveis entre si.';
COMMENT ON COLUMN biometria_templates.template_cifrado IS 'Vetor de caracteristicas cifrado. NUNCA a imagem original. Ilegivel sem a chave referenciada em chave_id.';
COMMENT ON COLUMN biometria_templates.iv IS 'Vetor de inicializacao da cifra, unico por registro.';
COMMENT ON COLUMN biometria_templates.chave_id IS 'Identificador da chave no cofre externo. A chave NAO fica no banco: e o que impede que um dump vaze biometria.';
COMMENT ON COLUMN biometria_templates.hash_template IS 'Hash do vetor em claro, apenas para deduplicacao e deteccao de cadastro repetido sem expor o vetor.';

CREATE INDEX ix_biometria_templates_biometria ON biometria_templates (tenant_id, biometria_id) WHERE ativo;
CREATE INDEX ix_biometria_templates_modelo ON biometria_templates (tenant_id, versao_modelo);


CREATE TABLE dispositivos (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                UUID REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id                UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    tipo                      TEXT NOT NULL
                              CHECK (tipo IN ('terminal','celular','tablet','navegador','totem','integracao')),
    plataforma                TEXT CHECK (plataforma IN ('android','ios','web','linux','windows','macos','embarcado')),
    identificador             TEXT NOT NULL,
    nome                      TEXT,
    fabricante                TEXT,
    modelo                    TEXT,
    versao_so                 TEXT,
    versao_app                TEXT,
    chave_publica             TEXT,
    status                    TEXT NOT NULL DEFAULT 'pendente'
                              CHECK (status IN ('pendente','ativo','bloqueado','revogado','substituido')),
    attestation_status        TEXT NOT NULL DEFAULT 'nao_verificado'
                              CHECK (attestation_status IN ('nao_verificado','aprovado','reprovado','indisponivel')),
    attestation_verificado_em TIMESTAMPTZ,
    root_detectado            BOOLEAN NOT NULL DEFAULT FALSE,
    emulador_detectado        BOOLEAN NOT NULL DEFAULT FALSE,
    modo_desenvolvedor        BOOLEAN NOT NULL DEFAULT FALSE,
    depuracao_usb             BOOLEAN NOT NULL DEFAULT FALSE,
    ultimo_acesso_em          TIMESTAMPTZ,
    ultimo_ip                 INET,
    observacoes               TEXT,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    excluido_em               TIMESTAMPTZ,
    excluido_por              UUID
);

COMMENT ON TABLE dispositivos IS
  'Qualquer aparelho capaz de originar uma marcacao: terminal facial, celular, tablet de quiosque, navegador ou cliente de API. Guarda o estado antifraude conhecido do aparelho.';
COMMENT ON COLUMN dispositivos.identificador IS 'Identificador estavel do aparelho: android_id, identifierForVendor, fingerprint do navegador ou numero de serie do terminal.';
COMMENT ON COLUMN dispositivos.chave_publica IS 'Chave publica gerada no keystore ou secure enclave do aparelho, usada para verificar a assinatura do payload.';
COMMENT ON COLUMN dispositivos.attestation_status IS 'Ultimo veredito de Play Integrity ou App Attest, sempre verificado no servidor.';
COMMENT ON COLUMN dispositivos.modo_desenvolvedor IS 'Ultimo estado conhecido de DEVELOPMENT_SETTINGS_ENABLED. A politica que decide bloquear, sinalizar ou permitir esta em politicas_registro.';
COMMENT ON COLUMN dispositivos.status IS 'substituido indica troca de aparelho aprovada pelo RH, preservando o historico do anterior.';

CREATE UNIQUE INDEX uq_dispositivos_identificador ON dispositivos (tenant_id, identificador) WHERE excluido_em IS NULL;
CREATE INDEX ix_dispositivos_empresa ON dispositivos (tenant_id, empresa_id, tipo) WHERE excluido_em IS NULL;
CREATE INDEX ix_dispositivos_status ON dispositivos (tenant_id, status);


CREATE TABLE dispositivo_vinculos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    dispositivo_id   UUID NOT NULL REFERENCES dispositivos (id) ON DELETE CASCADE,
    colaborador_id   UUID NOT NULL REFERENCES colaboradores (id) ON DELETE CASCADE,
    status           TEXT NOT NULL DEFAULT 'pendente'
                     CHECK (status IN ('pendente','ativo','revogado','recusado')),
    vinculado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    aprovado_por     UUID,
    aprovado_em      TIMESTAMPTZ,
    revogado_em      TIMESTAMPTZ,
    motivo_revogacao TEXT,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por       UUID,
    atualizado_em    TIMESTAMPTZ,
    atualizado_por   UUID
);

COMMENT ON TABLE dispositivo_vinculos IS
  'Vinculo entre aparelho pessoal e colaborador. Regra de negocio: um unico dispositivo ativo por colaborador; a troca exige aprovacao do RH e fica registrada.';
COMMENT ON COLUMN dispositivo_vinculos.status IS 'pendente aguarda aprovacao do RH. Somente ativo autoriza registro de ponto pelo aparelho.';

CREATE UNIQUE INDEX uq_dispositivo_vinculos_ativo ON dispositivo_vinculos (tenant_id, colaborador_id) WHERE status = 'ativo';
CREATE INDEX ix_dispositivo_vinculos_dispositivo ON dispositivo_vinculos (tenant_id, dispositivo_id);


CREATE TABLE terminais (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    dispositivo_id         UUID NOT NULL REFERENCES dispositivos (id) ON DELETE RESTRICT,
    empresa_id             UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id             UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    rep_p_id               UUID,
    fabricante             TEXT NOT NULL DEFAULT 'control_id'
                           CHECK (fabricante IN ('control_id','henry','topdata','madis','dimep','inner','outro')),
    modelo                 TEXT,
    numero_serie           TEXT NOT NULL,
    endereco_ip            INET,
    porta                  INTEGER CHECK (porta IS NULL OR porta BETWEEN 1 AND 65535),
    mac                    TEXT,
    modo_comunicacao       TEXT NOT NULL DEFAULT 'push'
                           CHECK (modo_comunicacao IN ('push','monitor','polling','direto')),
    usuario_api            TEXT,
    senha_api_cifrada      BYTEA,
    chave_id               TEXT,
    token_push             TEXT,
    capacidade_faces       INTEGER,
    ultimo_log_externo_id  BIGINT NOT NULL DEFAULT 0,
    ultima_sincronizacao_em TIMESTAMPTZ,
    ultimo_contato_em      TIMESTAMPTZ,
    intervalo_push_segundos INTEGER NOT NULL DEFAULT 30 CHECK (intervalo_push_segundos > 0),
    status                 TEXT NOT NULL DEFAULT 'ativo'
                           CHECK (status IN ('ativo','inativo','manutencao','desativado')),
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID,
    excluido_em            TIMESTAMPTZ,
    excluido_por           UUID
);

COMMENT ON TABLE terminais IS
  'Coletor fisico de marcacao, tipicamente um Control iD iDFace. IMPORTANTE: o terminal NAO e o REP-P; ele identifica a pessoa e produz um access_log. O REP-P e o nosso software, que atribui o NSR e grava no AFD.';
COMMENT ON COLUMN terminais.rep_p_id IS 'REP-P sob o qual as marcacoes deste coletor recebem NSR. FK criada na secao de marcacao.';
COMMENT ON COLUMN terminais.modo_comunicacao IS 'push: o equipamento consulta o servidor buscando comandos (obrigatorio em LAN sem IP publico). monitor: o equipamento envia eventos assincronos. polling: o servidor consulta o equipamento.';
COMMENT ON COLUMN terminais.senha_api_cifrada IS 'Senha da API do equipamento, cifrada com chave externa referenciada em chave_id.';
COMMENT ON COLUMN terminais.ultimo_log_externo_id IS 'Marca dagua do catch-up: maior access_log id ja coletado. Garante que a religacao da rede recupere tudo sem duplicar.';
COMMENT ON COLUMN terminais.ultimo_contato_em IS 'Ultimo contato do equipamento em qualquer modo. Base do alerta de terminal offline.';

CREATE UNIQUE INDEX uq_terminais_serie ON terminais (tenant_id, numero_serie) WHERE excluido_em IS NULL;
CREATE UNIQUE INDEX uq_terminais_dispositivo ON terminais (tenant_id, dispositivo_id) WHERE excluido_em IS NULL;
CREATE INDEX ix_terminais_unidade ON terminais (tenant_id, unidade_id) WHERE status = 'ativo';
CREATE INDEX ix_terminais_contato ON terminais (tenant_id, ultimo_contato_em) WHERE status = 'ativo';


CREATE TABLE terminal_saude (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    terminal_id        UUID NOT NULL REFERENCES terminais (id) ON DELETE CASCADE,
    verificado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    online             BOOLEAN NOT NULL,
    latencia_ms        INTEGER CHECK (latencia_ms IS NULL OR latencia_ms >= 0),
    firmware           TEXT,
    faces_cadastradas  INTEGER,
    logs_pendentes     INTEGER,
    memoria_livre_pct  NUMERIC(5,2),
    temperatura        NUMERIC(5,2),
    alarme             TEXT,
    mensagem           TEXT,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por         UUID
);

COMMENT ON TABLE terminal_saude IS
  'Serie temporal de saude dos coletores. Append-only: cada verificacao gera uma linha nova, nunca atualiza a anterior. Alimenta o alerta de terminal offline e o relatorio de dispositivos.';
COMMENT ON COLUMN terminal_saude.logs_pendentes IS 'Quantidade de access_logs ainda nao coletados pelo gateway. Valor alto indica atraso no catch-up.';
COMMENT ON COLUMN terminal_saude.alarme IS 'Alarme reportado pelo equipamento, por exemplo violacao de gabinete.';

CREATE INDEX ix_terminal_saude_terminal ON terminal_saude (tenant_id, terminal_id, verificado_em DESC);
CREATE INDEX ix_terminal_saude_offline ON terminal_saude (tenant_id, verificado_em DESC) WHERE NOT online;

ALTER TABLE sessoes
    ADD CONSTRAINT fk_sessoes_dispositivo
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id) ON DELETE SET NULL;


-- =============================================================================
-- 7. JORNADA, ESCALA E CALENDARIO
-- =============================================================================

CREATE TABLE horarios (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo                    TEXT NOT NULL,
    nome                      TEXT NOT NULL,
    entrada                   TIME,
    saida                     TIME,
    intervalo_inicio          TIME,
    intervalo_fim             TIME,
    duracao_intervalo_minutos INTEGER CHECK (duracao_intervalo_minutos IS NULL OR duracao_intervalo_minutos >= 0),
    intervalos_extras         JSONB,
    cruza_meia_noite          BOOLEAN NOT NULL DEFAULT FALSE,
    carga_minutos             INTEGER NOT NULL CHECK (carga_minutos BETWEEN 0 AND 1440),
    ativo                     BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    excluido_em               TIMESTAMPTZ,
    excluido_por              UUID
);

COMMENT ON TABLE horarios IS
  'Gabarito de horario reutilizavel: entrada, saida e intervalos previstos de um dia de trabalho. E o bloco de montagem de jornadas e turnos.';
COMMENT ON COLUMN horarios.cruza_meia_noite IS 'Verdadeiro quando a saida e menor que a entrada, caso da jornada noturna e do 12x36 que vira o dia.';
COMMENT ON COLUMN horarios.carga_minutos IS 'Carga liquida prevista em minutos, ja descontado o intervalo.';
COMMENT ON COLUMN horarios.intervalos_extras IS 'Pausas adicionais em JSON, por exemplo as pausas obrigatorias da NR-17 para digitacao e teleatendimento.';

CREATE UNIQUE INDEX uq_horarios_codigo ON horarios (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE jornadas (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                  UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo                      TEXT NOT NULL,
    nome                        TEXT NOT NULL,
    descricao                   TEXT,
    tipo                        TEXT NOT NULL
                                CHECK (tipo IN ('fixa','flexivel','livre','escala','12x36','parcial',
                                                'intermitente','teletrabalho','motorista')),
    carga_diaria_minutos        INTEGER CHECK (carga_diaria_minutos IS NULL OR carga_diaria_minutos BETWEEN 0 AND 1440),
    carga_semanal_minutos       INTEGER CHECK (carga_semanal_minutos IS NULL OR carga_semanal_minutos BETWEEN 0 AND 4200),
    carga_mensal_minutos        INTEGER CHECK (carga_mensal_minutos IS NULL OR carga_mensal_minutos >= 0),
    tolerancia_marcacao_minutos INTEGER NOT NULL DEFAULT 5  CHECK (tolerancia_marcacao_minutos BETWEEN 0 AND 60),
    tolerancia_diaria_minutos   INTEGER NOT NULL DEFAULT 10 CHECK (tolerancia_diaria_minutos BETWEEN 0 AND 120),
    descontar_tudo_se_exceder   BOOLEAN NOT NULL DEFAULT FALSE,
    janela_flexivel_minutos     INTEGER CHECK (janela_flexivel_minutos IS NULL OR janela_flexivel_minutos >= 0),
    intervalo_automatico        BOOLEAN NOT NULL DEFAULT FALSE,
    intervalo_minimo_minutos    INTEGER CHECK (intervalo_minimo_minutos IS NULL OR intervalo_minimo_minutos >= 0),
    intervalo_flexivel          BOOLEAN NOT NULL DEFAULT FALSE,
    interjornada_minima_minutos INTEGER NOT NULL DEFAULT 660 CHECK (interjornada_minima_minutos >= 0),
    noturno_inicio              TIME NOT NULL DEFAULT '22:00',
    noturno_fim                 TIME NOT NULL DEFAULT '05:00',
    hora_ficta_noturna          BOOLEAN NOT NULL DEFAULT TRUE,
    prorrogacao_noturna         BOOLEAN NOT NULL DEFAULT TRUE,
    limite_extra_diario_minutos INTEGER NOT NULL DEFAULT 120 CHECK (limite_extra_diario_minutos >= 0),
    limite_jornada_diaria_minutos INTEGER NOT NULL DEFAULT 600 CHECK (limite_jornada_diaria_minutos > 0),
    bloqueia_extra_acima_limite BOOLEAN NOT NULL DEFAULT FALSE,
    compensa_sabado             BOOLEAN NOT NULL DEFAULT FALSE,
    fatores_extra               JSONB,
    vigencia_inicio             DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim                DATE,
    ativo                       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                  UUID,
    atualizado_em               TIMESTAMPTZ,
    atualizado_por              UUID,
    excluido_em                 TIMESTAMPTZ,
    excluido_por                UUID,
    CONSTRAINT ck_jornadas_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);

COMMENT ON TABLE jornadas IS
  'Conjunto de regras de trabalho e de calculo aplicado a um vinculo: carga, tolerancias, tratamento do noturno, limites de extra e politica de intervalo. E o parametro central do motor de apuracao.';
COMMENT ON COLUMN jornadas.tipo IS 'fixa: horario definido por dia da semana. flexivel: carga com janela. livre: so carga total. escala: dirigida por escala ciclica. motorista: regras da Lei 13.103.';
COMMENT ON COLUMN jornadas.tolerancia_marcacao_minutos IS 'Tolerancia por marcacao. Padrao legal de 5 minutos (art. 58, par. 1 da CLT).';
COMMENT ON COLUMN jornadas.tolerancia_diaria_minutos IS 'Tolerancia acumulada no dia. Padrao legal de 10 minutos.';
COMMENT ON COLUMN jornadas.descontar_tudo_se_exceder IS 'Quando verdadeiro e a tolerancia diaria estoura, todo o excedente e computado, nao apenas a diferenca.';
COMMENT ON COLUMN jornadas.intervalo_automatico IS 'Pre-assinalacao do intervalo: o sistema assume o intervalo previsto quando nao ha marcacao correspondente.';
COMMENT ON COLUMN jornadas.interjornada_minima_minutos IS 'Descanso minimo entre jornadas. Padrao de 660 minutos (11 horas).';
COMMENT ON COLUMN jornadas.hora_ficta_noturna IS 'Aplica a hora ficta urbana de 52 minutos e 30 segundos no periodo noturno.';
COMMENT ON COLUMN jornadas.prorrogacao_noturna IS 'Mantem o adicional noturno na prorrogacao da jornada iniciada em periodo noturno (Sumula 60, II do TST).';
COMMENT ON COLUMN jornadas.fatores_extra IS 'Faixas e percentuais de hora extra em JSON, por exemplo primeira e segunda hora a 50 por cento e o excedente a 100 por cento.';
COMMENT ON COLUMN jornadas.vigencia_inicio IS 'A jornada e versionada por vigencia: trocar a regra no meio do mes nao reescreve o passado.';

CREATE UNIQUE INDEX uq_jornadas_codigo ON jornadas (tenant_id, empresa_id, codigo, vigencia_inicio) WHERE excluido_em IS NULL;
CREATE INDEX ix_jornadas_empresa ON jornadas (tenant_id, empresa_id) WHERE excluido_em IS NULL;


CREATE TABLE jornada_dias (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    jornada_id     UUID NOT NULL REFERENCES jornadas (id) ON DELETE CASCADE,
    dia_semana     SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    tipo_dia       TEXT NOT NULL DEFAULT 'util'
                   CHECK (tipo_dia IN ('util','dsr','folga','compensado','facultativo')),
    horario_id     UUID REFERENCES horarios (id) ON DELETE RESTRICT,
    carga_minutos  INTEGER NOT NULL DEFAULT 0 CHECK (carga_minutos BETWEEN 0 AND 1440),
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_jornada_dias UNIQUE (tenant_id, jornada_id, dia_semana)
);

COMMENT ON TABLE jornada_dias IS
  'Desdobramento da jornada por dia da semana. Define o horario previsto e o tipo do dia em jornadas fixas e flexiveis.';
COMMENT ON COLUMN jornada_dias.dia_semana IS 'ISO adaptado: 0 domingo, 1 segunda, ..., 6 sabado.';
COMMENT ON COLUMN jornada_dias.tipo_dia IS 'dsr identifica o dia de repouso semanal remunerado, o que muda o fator da hora extra.';


CREATE TABLE turnos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id     UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    horario_id     UUID REFERENCES horarios (id) ON DELETE RESTRICT,
    codigo         TEXT NOT NULL,
    nome           TEXT NOT NULL,
    tipo           TEXT NOT NULL DEFAULT 'diurno'
                   CHECK (tipo IN ('diurno','noturno','misto','folga','dsr','sobreaviso','prontidao')),
    sequencia      INTEGER,
    cor            TEXT CHECK (cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID
);

COMMENT ON TABLE turnos IS
  'Turno nomeado, com o horario que o materializa. Em regime de revezamento, a sequencia define a ordem de rodizio (manha, tarde, noite).';
COMMENT ON COLUMN turnos.sequencia IS 'Posicao do turno no revezamento. NULL em turnos fixos.';
COMMENT ON COLUMN turnos.cor IS 'Cor usada na grade de escala do painel do gestor.';

CREATE UNIQUE INDEX uq_turnos_codigo ON turnos (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE escalas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id       UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    jornada_id       UUID REFERENCES jornadas (id) ON DELETE RESTRICT,
    codigo           TEXT NOT NULL,
    nome             TEXT NOT NULL,
    descricao        TEXT,
    tipo             TEXT NOT NULL
                     CHECK (tipo IN ('5x2','6x1','4x2','12x36','espanhola','rotativa','personalizada')),
    dias_ciclo       INTEGER NOT NULL CHECK (dias_ciclo BETWEEN 1 AND 366),
    data_referencia  DATE NOT NULL,
    ativo            BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por       UUID,
    atualizado_em    TIMESTAMPTZ,
    atualizado_por   UUID,
    excluido_em      TIMESTAMPTZ,
    excluido_por     UUID
);

COMMENT ON TABLE escalas IS
  'Padrao ciclico de trabalho e folga. O ciclo se repete indefinidamente a partir de data_referencia; qualquer data e resolvida por aritmetica modular, sem materializar o calendario.';
COMMENT ON COLUMN escalas.dias_ciclo IS 'Tamanho do ciclo em dias. 7 para 5x2 e 6x1, 2 para 12x36, 6 para 4x2.';
COMMENT ON COLUMN escalas.data_referencia IS 'Ancora do ciclo: a data em que a escala esta na posicao 1. E o que permite calcular a posicao de qualquer data.';

CREATE UNIQUE INDEX uq_escalas_codigo ON escalas (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE escala_ciclos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    escala_id      UUID NOT NULL REFERENCES escalas (id) ON DELETE CASCADE,
    posicao        INTEGER NOT NULL CHECK (posicao >= 1),
    turno_id       UUID REFERENCES turnos (id) ON DELETE RESTRICT,
    tipo_dia       TEXT NOT NULL DEFAULT 'trabalho'
                   CHECK (tipo_dia IN ('trabalho','folga','dsr','compensado')),
    carga_minutos  INTEGER NOT NULL DEFAULT 0 CHECK (carga_minutos BETWEEN 0 AND 1440),
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_escala_ciclos UNIQUE (tenant_id, escala_id, posicao)
);

COMMENT ON TABLE escala_ciclos IS
  'Uma linha por posicao do ciclo da escala. Em 12x36 sao duas linhas: posicao 1 trabalho de 12 horas, posicao 2 folga.';
COMMENT ON COLUMN escala_ciclos.posicao IS 'Posicao dentro do ciclo, de 1 ate escalas.dias_ciclo.';


CREATE TABLE escala_atribuicoes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    vinculo_id       UUID NOT NULL REFERENCES vinculos (id) ON DELETE CASCADE,
    escala_id        UUID NOT NULL REFERENCES escalas (id) ON DELETE RESTRICT,
    posicao_inicial  INTEGER NOT NULL DEFAULT 1 CHECK (posicao_inicial >= 1),
    vigencia_inicio  DATE NOT NULL,
    vigencia_fim     DATE,
    motivo           TEXT,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por       UUID,
    atualizado_em    TIMESTAMPTZ,
    atualizado_por   UUID,
    CONSTRAINT ck_escala_atribuicoes_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ex_escala_atribuicoes_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        vinculo_id WITH =,
        daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]') WITH &&
    )
);

COMMENT ON TABLE escala_atribuicoes IS
  'Atribuicao datada de uma escala a um vinculo. Um vinculo tem no maximo uma escala vigente por data, garantido por constraint de exclusao.';
COMMENT ON COLUMN escala_atribuicoes.posicao_inicial IS 'Posicao do ciclo em que este vinculo entra na vigencia. E o que permite equipes desencontradas na mesma escala.';


CREATE TABLE vinculo_jornadas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    vinculo_id      UUID NOT NULL REFERENCES vinculos (id) ON DELETE CASCADE,
    jornada_id      UUID NOT NULL REFERENCES jornadas (id) ON DELETE RESTRICT,
    vigencia_inicio DATE NOT NULL,
    vigencia_fim    DATE,
    motivo          TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID,
    CONSTRAINT ck_vinculo_jornadas_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ex_vinculo_jornadas_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        vinculo_id WITH =,
        daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]') WITH &&
    )
);

COMMENT ON TABLE vinculo_jornadas IS
  'Historico de jornada vigente por vinculo. Tabela acrescentada ao modelo sugerido (divergencia documentada no glossario) porque sem ela nao ha como trocar a jornada no meio do mes preservando a apuracao anterior.';
COMMENT ON COLUMN vinculo_jornadas.motivo IS 'Justificativa da troca de jornada, exibida no espelho e na auditoria.';

CREATE INDEX ix_vinculo_jornadas_resolucao ON vinculo_jornadas (tenant_id, vinculo_id, vigencia_inicio DESC);


CREATE TABLE feriado_conjuntos (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo                TEXT NOT NULL,
    nome                  TEXT NOT NULL,
    abrangencia           TEXT NOT NULL
                          CHECK (abrangencia IN ('nacional','estadual','municipal','empresa','unidade')),
    uf                    dom_uf,
    codigo_ibge_municipio dom_ibge,
    ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID,
    CONSTRAINT ck_feriado_conjuntos_abrangencia CHECK (
        (abrangencia = 'estadual'  AND uf IS NOT NULL) OR
        (abrangencia = 'municipal' AND codigo_ibge_municipio IS NOT NULL) OR
        (abrangencia IN ('nacional','empresa','unidade'))
    )
);

COMMENT ON TABLE feriado_conjuntos IS
  'Agrupamento de feriados por abrangencia. A unidade combina varios conjuntos (nacional mais estadual mais municipal), o que faz o feriado municipal valer so onde deve valer.';

CREATE UNIQUE INDEX uq_feriado_conjuntos_codigo ON feriado_conjuntos (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE feriados (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    feriado_conjunto_id    UUID NOT NULL REFERENCES feriado_conjuntos (id) ON DELETE CASCADE,
    nome                   TEXT NOT NULL,
    data                   DATE,
    ano                    INTEGER CHECK (ano IS NULL OR ano BETWEEN 1900 AND 2200),
    tipo                   TEXT NOT NULL DEFAULT 'feriado'
                           CHECK (tipo IN ('feriado','ponto_facultativo','data_comemorativa','compensado')),
    movel                  BOOLEAN NOT NULL DEFAULT FALSE,
    regra_movel            TEXT CHECK (regra_movel IN ('pascoa','carnaval','sexta_santa','corpus_christi',
                                                       'quarta_cinzas','custom')),
    offset_dias            INTEGER,
    integral               BOOLEAN NOT NULL DEFAULT TRUE,
    carga_reduzida_minutos INTEGER CHECK (carga_reduzida_minutos IS NULL OR carga_reduzida_minutos >= 0),
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID,
    CONSTRAINT ck_feriados_definicao CHECK (
        (movel = TRUE  AND regra_movel IS NOT NULL) OR
        (movel = FALSE AND data IS NOT NULL)
    ),
    CONSTRAINT ck_feriados_parcial CHECK (
        integral = TRUE OR carga_reduzida_minutos IS NOT NULL
    )
);

COMMENT ON TABLE feriados IS
  'Feriado, ponto facultativo ou expediente reduzido. Feriados moveis nao guardam data: sao calculados por regra a partir da Pascoa no ano de referencia.';
COMMENT ON COLUMN feriados.movel IS 'Verdadeiro para feriados que mudam de data a cada ano (Carnaval, Sexta-Feira Santa, Corpus Christi).';
COMMENT ON COLUMN feriados.regra_movel IS 'Ancora do calculo. offset_dias e somado a ela para chegar na data efetiva.';
COMMENT ON COLUMN feriados.integral IS 'Falso indica expediente reduzido; a carga do dia passa a ser carga_reduzida_minutos.';
COMMENT ON COLUMN feriados.ano IS 'Ano de aplicacao para feriados fixos pontuais. NULL significa que a data se repete todo ano.';

CREATE UNIQUE INDEX uq_feriados_fixos ON feriados (tenant_id, feriado_conjunto_id, data, nome) WHERE data IS NOT NULL;
CREATE INDEX ix_feriados_conjunto ON feriados (tenant_id, feriado_conjunto_id);
CREATE INDEX ix_feriados_data ON feriados (tenant_id, data) WHERE data IS NOT NULL;


CREATE TABLE unidade_feriado_conjuntos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    unidade_id          UUID NOT NULL REFERENCES unidades (id) ON DELETE CASCADE,
    feriado_conjunto_id UUID NOT NULL REFERENCES feriado_conjuntos (id) ON DELETE CASCADE,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID,
    CONSTRAINT uq_unidade_feriado_conjuntos UNIQUE (tenant_id, unidade_id, feriado_conjunto_id)
);

COMMENT ON TABLE unidade_feriado_conjuntos IS
  'Associacao N para N entre unidade e conjuntos de feriados. Tabela acrescentada ao modelo sugerido porque uma unidade precisa somar o calendario nacional, o estadual e o municipal.';


CREATE TABLE tipos_afastamento (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo            TEXT NOT NULL,
    nome              TEXT NOT NULL,
    descricao         TEXT,
    categoria         TEXT NOT NULL
                      CHECK (categoria IN ('ferias','atestado','licenca_maternidade','licenca_paternidade',
                                           'inss','acidente_trabalho','suspensao','falta_justificada',
                                           'falta_injustificada','servico_militar','doacao_sangue','casamento',
                                           'obito','treinamento','licenca_nao_remunerada','outro')),
    codigo_esocial    TEXT,
    abona_dia         BOOLEAN NOT NULL DEFAULT TRUE,
    remunerado        BOOLEAN NOT NULL DEFAULT TRUE,
    computa_carga     BOOLEAN NOT NULL DEFAULT FALSE,
    computa_dsr       BOOLEAN NOT NULL DEFAULT TRUE,
    suspende_contrato BOOLEAN NOT NULL DEFAULT FALSE,
    exige_documento   BOOLEAN NOT NULL DEFAULT FALSE,
    limite_dias       INTEGER CHECK (limite_dias IS NULL OR limite_dias > 0),
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID,
    excluido_em       TIMESTAMPTZ,
    excluido_por      UUID
);

COMMENT ON TABLE tipos_afastamento IS
  'Catalogo configuravel de motivos de ausencia e o efeito de cada um no calculo. Os codigos de fabrica sao semeados por tenant.';
COMMENT ON COLUMN tipos_afastamento.abona_dia IS 'Quando verdadeiro, o dia nao gera falta nem debito de carga.';
COMMENT ON COLUMN tipos_afastamento.computa_carga IS 'Quando verdadeiro, o afastamento gera horas na apuracao como se trabalhadas (caso de treinamento externo).';
COMMENT ON COLUMN tipos_afastamento.computa_dsr IS 'Falso faz o afastamento derrubar o DSR da semana, como na falta injustificada.';
COMMENT ON COLUMN tipos_afastamento.codigo_esocial IS 'Codigo do motivo de afastamento na tabela do eSocial, exportado no AEJ.';

CREATE UNIQUE INDEX uq_tipos_afastamento_codigo ON tipos_afastamento (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE afastamentos (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id       UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id           UUID REFERENCES vinculos (id) ON DELETE RESTRICT,
    tipo_afastamento_id  UUID NOT NULL REFERENCES tipos_afastamento (id) ON DELETE RESTRICT,
    data_inicio          DATE NOT NULL,
    data_fim             DATE,
    periodo_parcial      BOOLEAN NOT NULL DEFAULT FALSE,
    hora_inicio          TIME,
    hora_fim             TIME,
    motivo               TEXT,
    cid                  TEXT,
    dias_previstos       INTEGER,
    documento_id         UUID REFERENCES documentos (id) ON DELETE SET NULL,
    solicitacao_id       UUID,
    origem               TEXT NOT NULL DEFAULT 'manual'
                         CHECK (origem IN ('manual','solicitacao','integracao','importacao')),
    status               TEXT NOT NULL DEFAULT 'aprovado'
                         CHECK (status IN ('solicitado','aprovado','reprovado','cancelado','encerrado')),
    aprovado_por         UUID,
    aprovado_em          TIMESTAMPTZ,
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por           UUID,
    atualizado_em        TIMESTAMPTZ,
    atualizado_por       UUID,
    excluido_em          TIMESTAMPTZ,
    excluido_por         UUID,
    CONSTRAINT ck_afastamentos_periodo CHECK (data_fim IS NULL OR data_fim >= data_inicio),
    CONSTRAINT ck_afastamentos_parcial CHECK (
        periodo_parcial = FALSE OR (hora_inicio IS NOT NULL AND hora_fim IS NOT NULL)
    ),
    CONSTRAINT ex_afastamentos_sobreposicao EXCLUDE USING gist (
        tenant_id WITH =,
        colaborador_id WITH =,
        daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]') WITH &&
    ) WHERE (status = 'aprovado' AND periodo_parcial = FALSE AND excluido_em IS NULL)
);

COMMENT ON TABLE afastamentos IS
  'Periodo de ausencia legitima do colaborador. Entra na apuracao como insumo (nao como marcacao) e e exportado no bloco de ausencias do AEJ.';
COMMENT ON COLUMN afastamentos.periodo_parcial IS 'Verdadeiro para ausencia de algumas horas do dia, caso de consulta medica com atestado de horas.';
COMMENT ON COLUMN afastamentos.cid IS 'Codigo CID do atestado. Dado de saude: leitura sempre registrada em acessos_dados_sensiveis.';
COMMENT ON COLUMN afastamentos.solicitacao_id IS 'Solicitacao de workflow que originou o afastamento. FK criada na secao de workflow.';
COMMENT ON CONSTRAINT ex_afastamentos_sobreposicao ON afastamentos IS
  'Impede dois afastamentos integrais aprovados sobrepostos para o mesmo colaborador. Afastamentos parciais ficam de fora da regra por natureza.';

CREATE INDEX ix_afastamentos_colaborador ON afastamentos (tenant_id, colaborador_id, data_inicio, data_fim) WHERE excluido_em IS NULL;
CREATE INDEX ix_afastamentos_vinculo ON afastamentos (tenant_id, vinculo_id, data_inicio) WHERE status = 'aprovado';
CREATE INDEX ix_afastamentos_tipo ON afastamentos (tenant_id, tipo_afastamento_id, data_inicio);


-- =============================================================================
-- 8. MARCACAO (NUCLEO LEGAL)
--
-- Principio inegociavel: marcacao e IMUTAVEL. Nenhum endpoint, tela ou rotina
-- altera ou apaga um registro desta secao. Correcao vive na secao 9
-- (tratamento). A Portaria MTP 671/2021 veda ao REP alterar ou apagar
-- marcacoes e veda inserir marcacao que nao corresponda ao fato real.
-- =============================================================================

CREATE TABLE rep_ps (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                  UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                 UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    identificador              TEXT NOT NULL,
    tipo                       TEXT NOT NULL DEFAULT 'rep_p'
                               CHECK (tipo IN ('rep_p','rep_c','rep_a')),
    numero_inpi                TEXT NOT NULL CHECK (numero_inpi ~ '^[0-9]+$'),
    cnpj_desenvolvedor         dom_cnpj NOT NULL,
    razao_social_desenvolvedor TEXT NOT NULL,
    cnpj_empregador            dom_cnpj NOT NULL,
    razao_social_empregador    TEXT NOT NULL,
    cei_caepf                  TEXT,
    versao_programa            TEXT NOT NULL,
    data_inicio_operacao       DATE NOT NULL,
    data_fim_operacao          DATE,
    status                     TEXT NOT NULL DEFAULT 'ativo'
                               CHECK (status IN ('ativo','inativo','substituido')),
    criado_em                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                 UUID,
    atualizado_em              TIMESTAMPTZ,
    atualizado_por             UUID,
    excluido_em                TIMESTAMPTZ,
    excluido_por               UUID,
    CONSTRAINT ck_rep_ps_periodo CHECK (data_fim_operacao IS NULL OR data_fim_operacao >= data_inicio_operacao)
);

COMMENT ON TABLE rep_ps IS
  'Identificacao de cada instancia de REP-P em operacao. O REP-P e o nosso software, nao o terminal. Um REP-P por empresa e o caso normal; cada um tem sua propria sequencia de NSR e seus proprios arquivos AFD.';
COMMENT ON COLUMN rep_ps.identificador IS 'Codigo interno do REP-P, usado para separar sequencias de NSR quando a empresa opera mais de um.';
COMMENT ON COLUMN rep_ps.numero_inpi IS 'Numero do registro do programa no INPI, SOMENTE DIGITOS. Vai impresso no cabecalho do AFD.';
COMMENT ON COLUMN rep_ps.cnpj_desenvolvedor IS 'CNPJ do desenvolvedor do programa (SEEG). Diferente do CNPJ do empregador.';
COMMENT ON COLUMN rep_ps.cnpj_empregador IS 'CNPJ da empresa empregadora que opera este REP-P. Vai para o cabecalho do AFD.';
COMMENT ON COLUMN rep_ps.versao_programa IS 'Versao do programa em operacao. Trocar de versao nao reinicia o NSR.';

CREATE UNIQUE INDEX uq_rep_ps_identificador ON rep_ps (tenant_id, empresa_id, identificador) WHERE excluido_em IS NULL;
CREATE INDEX ix_rep_ps_empresa ON rep_ps (tenant_id, empresa_id) WHERE status = 'ativo';


CREATE TABLE nsr_sequencias (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    rep_p_id           UUID NOT NULL REFERENCES rep_ps (id) ON DELETE RESTRICT,
    proximo_nsr        BIGINT NOT NULL DEFAULT 1 CHECK (proximo_nsr >= 1),
    ultimo_nsr_emitido BIGINT NOT NULL DEFAULT 0 CHECK (ultimo_nsr_emitido >= 0),
    ultimo_hash        dom_sha256,
    ultima_emissao_em  TIMESTAMPTZ,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por         UUID,
    atualizado_em      TIMESTAMPTZ,
    atualizado_por     UUID,
    CONSTRAINT uq_nsr_sequencias UNIQUE (tenant_id, rep_p_id),
    CONSTRAINT ck_nsr_sequencias_coerencia CHECK (proximo_nsr = ultimo_nsr_emitido + 1)
);

COMMENT ON TABLE nsr_sequencias IS
  'Alocador transacional do Numero Sequencial de Registro, um por REP-P. Deliberadamente NAO usa SEQUENCE do PostgreSQL: sequence nao volta atras em rollback e produziria lacunas, o que a Portaria proibe. A alocacao e feita com SELECT ... FOR UPDATE nesta linha dentro da mesma transacao da marcacao.';
COMMENT ON COLUMN nsr_sequencias.proximo_nsr IS 'Proximo NSR a ser entregue. Comeca em 1 e nunca e reiniciado, nem na virada de ano, nem na troca de versao.';
COMMENT ON COLUMN nsr_sequencias.ultimo_hash IS 'Hash do ultimo registro gravado. E o elo anterior da cadeia de hash das marcacoes.';


CREATE TABLE marcacoes (
    id                  UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    rep_p_id            UUID NOT NULL REFERENCES rep_ps (id) ON DELETE RESTRICT,
    empresa_id          UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id          UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    colaborador_id      UUID REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id          UUID REFERENCES vinculos (id) ON DELETE RESTRICT,
    nsr                 BIGINT NOT NULL CHECK (nsr >= 1),
    tipo_registro       TEXT NOT NULL DEFAULT '7'
                        CHECK (tipo_registro IN ('2','3','4','5','6','7','9')),
    sentido_informado   TEXT CHECK (sentido_informado IN ('entrada','saida','indefinido')),
    cpf                 dom_cpf NOT NULL,
    pis_nit             dom_pis,
    datahora_marcacao   TIMESTAMPTZ NOT NULL,
    datahora_gravacao   TIMESTAMPTZ NOT NULL DEFAULT now(),
    datahora_dispositivo TIMESTAMPTZ,
    fuso_horario        dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    canal               TEXT NOT NULL
                        CHECK (canal IN ('terminal','mobile','web','totem','api','importacao')),
    dispositivo_id      UUID REFERENCES dispositivos (id) ON DELETE RESTRICT,
    terminal_id         UUID REFERENCES terminais (id) ON DELETE RESTRICT,
    external_id         TEXT,
    log_externo_id      BIGINT,
    idempotency_key     TEXT,
    origem_importacao_id UUID,
    crc16               INTEGER NOT NULL CHECK (crc16 BETWEEN 0 AND 65535),
    hash_anterior       dom_sha256,
    hash_registro       dom_sha256 NOT NULL,
    linha_afd           TEXT,
    coletada_offline    BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    PRIMARY KEY (id, datahora_marcacao),
    CONSTRAINT uq_marcacoes_nsr UNIQUE (tenant_id, rep_p_id, nsr, datahora_marcacao)
) PARTITION BY RANGE (datahora_marcacao);

COMMENT ON TABLE marcacoes IS
  'Registro de ponto. APPEND-ONLY e PARTICIONADA POR MES em datahora_marcacao. Nunca sofre UPDATE nem DELETE: gatilhos abortam ambos. Nao possui soft delete nem colunas atualizado_em/atualizado_por por definicao. Toda correcao acontece em tratamentos, sem tocar aqui.';
COMMENT ON COLUMN marcacoes.nsr IS 'Numero Sequencial de Registro atribuido pelo servidor, por REP-P, comecando em 1 e sem lacunas. Alocado em nsr_sequencias na mesma transacao.';
COMMENT ON COLUMN marcacoes.tipo_registro IS 'Tipo do registro no leiaute do AFD. 7 e a marcacao de ponto do REP-P. Os demais tipos existem para importacao de AFD de terceiros.';
COMMENT ON COLUMN marcacoes.sentido_informado IS 'Entrada ou saida QUANDO o coletor informa (o iDFace informa). O REP-P nao registra sentido legalmente: o pareamento definitivo e feito na apuracao. Nunca preencher por inferencia no momento da gravacao.';
COMMENT ON COLUMN marcacoes.cpf IS 'CPF do trabalhador congelado no momento do registro. Vai literalmente para o registro tipo 7 do AFD, por isso nao e resolvido por join na hora de gerar o arquivo.';
COMMENT ON COLUMN marcacoes.datahora_marcacao IS 'Momento do FATO, no relogio do servidor. Chave de particionamento. E o horario que aparece no AFD e no espelho.';
COMMENT ON COLUMN marcacoes.datahora_gravacao IS 'Momento em que o servidor persistiu o registro. Difere de datahora_marcacao em coleta offline e em catch-up de terminal.';
COMMENT ON COLUMN marcacoes.datahora_dispositivo IS 'Relogio do aparelho no momento da captura. Guardado apenas como evidencia: o relogio do servidor e a fonte de verdade.';
COMMENT ON COLUMN marcacoes.canal IS 'Canal de origem. importacao identifica marcacao vinda de AFD de terceiro, que usa namespace de NSR proprio.';
COMMENT ON COLUMN marcacoes.external_id IS 'Chave de idempotencia informada pelo integrador no canal api.';
COMMENT ON COLUMN marcacoes.log_externo_id IS 'Identificador do access_log no terminal Control iD. Junto com dispositivo_id forma a chave de idempotencia do catch-up.';
COMMENT ON COLUMN marcacoes.crc16 IS 'CRC-16 do registro conforme o leiaute do AFD, calculado na gravacao e congelado.';
COMMENT ON COLUMN marcacoes.hash_anterior IS 'Hash do registro anterior do mesmo REP-P. Forma a cadeia que torna remocao silenciosa detectavel.';
COMMENT ON COLUMN marcacoes.hash_registro IS 'SHA-256 do conteudo canonico do registro concatenado com hash_anterior.';
COMMENT ON COLUMN marcacoes.linha_afd IS 'Linha exatamente como sera escrita no AFD, congelada na gravacao. Garante que o arquivo gerado hoje seja byte a byte igual ao gerado daqui a cinco anos.';
COMMENT ON COLUMN marcacoes.coletada_offline IS 'Verdadeiro quando o registro chegou por fila offline. O sistema NUNCA finge que foi online: o espelho exibe a marca.';
COMMENT ON COLUMN marcacoes.origem_importacao_id IS 'Importacao que trouxe o registro. FK criada na secao de integracao.';
COMMENT ON CONSTRAINT uq_marcacoes_nsr ON marcacoes IS
  'Unicidade de NSR dentro da particao. A unicidade GLOBAL do par REP-P mais NSR e garantida pela tabela nsr_emissoes, porque o PostgreSQL exige a chave de particao em qualquer constraint unica de tabela particionada.';

CREATE INDEX ix_marcacoes_colaborador_data ON marcacoes (tenant_id, colaborador_id, datahora_marcacao DESC);
CREATE INDEX ix_marcacoes_vinculo_data ON marcacoes (tenant_id, vinculo_id, datahora_marcacao);
CREATE INDEX ix_marcacoes_rep_nsr ON marcacoes (tenant_id, rep_p_id, nsr);
CREATE INDEX ix_marcacoes_empresa_data ON marcacoes (tenant_id, empresa_id, datahora_marcacao);
CREATE INDEX ix_marcacoes_cpf ON marcacoes (tenant_id, cpf, datahora_marcacao);
CREATE INDEX ix_marcacoes_gravacao ON marcacoes (tenant_id, datahora_gravacao);
CREATE INDEX ix_marcacoes_idem_external ON marcacoes (tenant_id, canal, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX ix_marcacoes_idem_dispositivo ON marcacoes (tenant_id, dispositivo_id, log_externo_id) WHERE log_externo_id IS NOT NULL;
CREATE INDEX ix_marcacoes_offline ON marcacoes (tenant_id, datahora_marcacao) WHERE coletada_offline;

-- Gatilhos de imutabilidade. Exigencia legal, nao configuracao.
CREATE TRIGGER trg_marcacoes_bloqueia_update
    BEFORE UPDATE ON marcacoes
    FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();

CREATE TRIGGER trg_marcacoes_bloqueia_delete
    BEFORE DELETE ON marcacoes
    FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();

-- Criacao de particao mensal. O scheduler chama esta funcao com antecedencia.
-- Os limites usam o offset fixo do Brasil (-03), que nao tem horario de verao
-- desde 2019, tornando as fronteiras deterministas e alinhadas ao mes civil.
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
$$;

COMMENT ON FUNCTION fn_cria_particao_marcacoes(DATE) IS
  'Cria a particao mensal de marcacoes ja com RLS, policy de tenant e barreira de TRUNCATE. Idempotente. O gatilho de TRUNCATE fica na particao porque o PostgreSQL nao aceita gatilho de TRUNCATE em tabela particionada.';

-- Particoes iniciais: 2026 e 2027. O scheduler estende a janela mensalmente.
DO $$
DECLARE v_mes DATE := DATE '2026-01-01';
BEGIN
    WHILE v_mes < DATE '2028-01-01' LOOP
        PERFORM fn_cria_particao_marcacoes(v_mes);
        v_mes := (v_mes + INTERVAL '1 month')::date;
    END LOOP;
END $$;

-- Rede de seguranca: nenhuma marcacao pode ser recusada por falta de particao.
CREATE TABLE marcacoes_default PARTITION OF marcacoes DEFAULT;
COMMENT ON TABLE marcacoes_default IS
  'Particao padrao. Existe para que a ausencia de particao nunca recuse uma marcacao legitima. Monitorada: linha aqui e alarme operacional, nao normalidade.';

ALTER TABLE marcacoes_default ENABLE ROW LEVEL SECURITY;
ALTER TABLE marcacoes_default FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_isolamento_tenant ON marcacoes_default
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE TRIGGER trg_marcacoes_default_bloqueia_truncate
    BEFORE TRUNCATE ON marcacoes_default
    FOR EACH STATEMENT EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE nsr_emissoes (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    rep_p_id          UUID NOT NULL REFERENCES rep_ps (id) ON DELETE RESTRICT,
    nsr               BIGINT NOT NULL CHECK (nsr >= 1),
    marcacao_id       UUID NOT NULL,
    datahora_marcacao TIMESTAMPTZ NOT NULL,
    hash_registro     dom_sha256 NOT NULL,
    hash_anterior     dom_sha256,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    CONSTRAINT uq_nsr_emissoes UNIQUE (tenant_id, rep_p_id, nsr),
    CONSTRAINT fk_nsr_emissoes_marcacao FOREIGN KEY (marcacao_id, datahora_marcacao)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT
);

COMMENT ON TABLE nsr_emissoes IS
  'Indice global de NSR emitidos. Tabela ACRESCENTADA ao modelo sugerido (divergencia documentada no glossario): o PostgreSQL exige a chave de particao em constraints unicas de tabela particionada, logo UNIQUE (tenant_id, rep_p_id, nsr) nao pode ser imposta em marcacoes. Esta tabela nao e particionada e impoe a unicidade globalmente, alem de tornar a deteccao de lacuna uma consulta trivial.';
COMMENT ON COLUMN nsr_emissoes.hash_registro IS 'Copia do hash da marcacao. Permite verificar a cadeia sem varrer todas as particoes.';

CREATE INDEX ix_nsr_emissoes_sequencia ON nsr_emissoes (tenant_id, rep_p_id, nsr);

CREATE TRIGGER trg_nsr_emissoes_bloqueia_update
    BEFORE UPDATE ON nsr_emissoes FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_nsr_emissoes_bloqueia_delete
    BEFORE DELETE ON nsr_emissoes FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE marcacao_idempotencia (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    escopo            TEXT NOT NULL
                      CHECK (escopo IN ('external_id','dispositivo_log','idempotency_key','offline_hmac')),
    chave             TEXT NOT NULL,
    marcacao_id       UUID NOT NULL,
    datahora_marcacao TIMESTAMPTZ NOT NULL,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    CONSTRAINT uq_marcacao_idempotencia UNIQUE (tenant_id, escopo, chave),
    CONSTRAINT fk_marcacao_idempotencia_marcacao FOREIGN KEY (marcacao_id, datahora_marcacao)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT
);

COMMENT ON TABLE marcacao_idempotencia IS
  'Guarda global de idempotencia. Tabela ACRESCENTADA ao modelo sugerido pelo mesmo motivo de nsr_emissoes: os indices de idempotencia em marcacoes servem para consulta, mas so uma tabela nao particionada consegue IMPOR unicidade entre meses distintos. Reenvio do mesmo registro offline colide aqui e nao duplica marcacao.';
COMMENT ON COLUMN marcacao_idempotencia.escopo IS 'external_id: canal api. dispositivo_log: par dispositivo mais access_log do terminal. idempotency_key: cabecalho Idempotency-Key. offline_hmac: HMAC do item da fila offline.';

CREATE INDEX ix_marcacao_idempotencia_marcacao ON marcacao_idempotencia (tenant_id, marcacao_id);

CREATE TRIGGER trg_marcacao_idempotencia_bloqueia_update
    BEFORE UPDATE ON marcacao_idempotencia FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_marcacao_idempotencia_bloqueia_delete
    BEFORE DELETE ON marcacao_idempotencia FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE marcacoes_meta (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    marcacao_id               UUID NOT NULL,
    marcacao_datahora         TIMESTAMPTZ NOT NULL,
    latitude                  NUMERIC(10,7) CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    longitude                 NUMERIC(10,7) CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    precisao_metros           NUMERIC(8,2) CHECK (precisao_metros IS NULL OR precisao_metros >= 0),
    altitude                  NUMERIC(8,2),
    endereco_aproximado       TEXT,
    unidade_geocerca_id       UUID REFERENCES unidades (id) ON DELETE SET NULL,
    dentro_geocerca           BOOLEAN,
    distancia_geocerca_metros NUMERIC(10,2),
    foto_ref                  TEXT,
    foto_hash                 dom_sha256,
    score_facial              NUMERIC(5,2) CHECK (score_facial IS NULL OR score_facial BETWEEN 0 AND 100),
    limiar_facial             NUMERIC(5,2) CHECK (limiar_facial IS NULL OR limiar_facial BETWEEN 0 AND 100),
    versao_modelo_facial      TEXT,
    liveness_aprovado         BOOLEAN,
    liveness_metodo           TEXT CHECK (liveness_metodo IN ('desafio_ativo','passivo','hibrido','nao_aplicavel')),
    score_confianca           SMALLINT CHECK (score_confianca IS NULL OR score_confianca BETWEEN 0 AND 100),
    classificacao_confianca   TEXT CHECK (classificacao_confianca IN ('alta','media','baixa','bloqueada')),
    flags_integridade         JSONB NOT NULL DEFAULT '{}'::jsonb,
    attestation_veredito      TEXT CHECK (attestation_veredito IN ('aprovado','reprovado','indisponivel','nao_aplicavel')),
    root_detectado            BOOLEAN,
    emulador_detectado        BOOLEAN,
    modo_desenvolvedor        BOOLEAN,
    mock_location             BOOLEAN,
    camera_virtual            BOOLEAN,
    velocidade_desde_ultima_kmh NUMERIC(8,2),
    wifi_bssid                TEXT,
    celula_id                 TEXT,
    ip                        INET,
    asn                       TEXT,
    pais                      TEXT,
    user_agent                TEXT,
    fingerprint               TEXT,
    revisao_status            TEXT NOT NULL DEFAULT 'nao_requer'
                              CHECK (revisao_status IN ('nao_requer','pendente','aprovada','rejeitada')),
    revisado_por              UUID,
    revisado_em               TIMESTAMPTZ,
    revisao_observacao        TEXT,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    CONSTRAINT uq_marcacoes_meta UNIQUE (tenant_id, marcacao_id),
    CONSTRAINT fk_marcacoes_meta_marcacao FOREIGN KEY (marcacao_id, marcacao_datahora)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT
);

COMMENT ON TABLE marcacoes_meta IS
  'Contexto e evidencia antifraude da marcacao. Separada de marcacoes por dois motivos: manter o nucleo legal enxuto e imutavel, e permitir que o gestor revise o risco (campos de revisao mudam) sem jamais tocar no registro legal.';
COMMENT ON COLUMN marcacoes_meta.marcacao_datahora IS 'Copia de datahora_marcacao. Obrigatoria porque a chave estrangeira precisa referenciar a chave primaria composta da tabela particionada.';
COMMENT ON COLUMN marcacoes_meta.dentro_geocerca IS 'Resultado da avaliacao da geocerca no momento do registro. NULL quando a unidade nao tem geocerca configurada.';
COMMENT ON COLUMN marcacoes_meta.foto_ref IS 'Chave da foto de captura no MinIO. Sujeita a politica de retencao curta, diferente da marcacao, que retem por 5 anos.';
COMMENT ON COLUMN marcacoes_meta.score_facial IS 'Similaridade retornada pelo facial-svc, de 0 a 100. Comparada com limiar_facial vigente na empresa.';
COMMENT ON COLUMN marcacoes_meta.score_confianca IS 'Score de confianca composto (0 a 100) calculado no servidor a partir de attestation, RASP, modo desenvolvedor, mock location, coerencia geografica e reputacao do dispositivo.';
COMMENT ON COLUMN marcacoes_meta.classificacao_confianca IS 'Faixa resultante da comparacao do score com os limiares de politicas_registro. bloqueada significa que o registro foi recusado.';
COMMENT ON COLUMN marcacoes_meta.flags_integridade IS 'Mapa completo dos sinais brutos coletados pelo cliente, em JSON. As colunas booleanas ao lado sao a projecao dos sinais mais consultados.';
COMMENT ON COLUMN marcacoes_meta.velocidade_desde_ultima_kmh IS 'Velocidade implicita entre esta marcacao e a anterior do mesmo colaborador. Valor absurdo denuncia deslocamento impossivel.';
COMMENT ON COLUMN marcacoes_meta.wifi_bssid IS 'BSSID do ponto de acesso, usado para corroborar o GPS.';
COMMENT ON COLUMN marcacoes_meta.revisao_status IS 'Fila de revisao do gestor para marcacoes de confianca media. A revisao NAO altera a marcacao: no maximo gera um tratamento.';

CREATE INDEX ix_marcacoes_meta_revisao ON marcacoes_meta (tenant_id, revisao_status) WHERE revisao_status = 'pendente';
CREATE INDEX ix_marcacoes_meta_score ON marcacoes_meta (tenant_id, score_confianca);
CREATE INDEX ix_marcacoes_meta_fora_cerca ON marcacoes_meta (tenant_id, marcacao_datahora) WHERE dentro_geocerca = FALSE;
CREATE INDEX ix_marcacoes_meta_flags ON marcacoes_meta USING gin (flags_integridade);


CREATE TABLE fila_offline (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id        UUID REFERENCES colaboradores (id) ON DELETE RESTRICT,
    dispositivo_id        UUID NOT NULL REFERENCES dispositivos (id) ON DELETE RESTRICT,
    payload_cifrado       BYTEA NOT NULL,
    iv                    BYTEA NOT NULL,
    hmac                  TEXT NOT NULL,
    contador_monotonico   BIGINT NOT NULL CHECK (contador_monotonico >= 0),
    datahora_dispositivo  TIMESTAMPTZ NOT NULL,
    tempo_monotonico_ms   BIGINT,
    capturado_em_offline  BOOLEAN NOT NULL DEFAULT TRUE,
    recebido_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    processado_em         TIMESTAMPTZ,
    status                TEXT NOT NULL DEFAULT 'pendente'
                          CHECK (status IN ('pendente','processado','duplicado','rejeitado','expirado')),
    tentativas            INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    erro                  TEXT,
    marcacao_id           UUID,
    marcacao_datahora     TIMESTAMPTZ,
    expira_em             TIMESTAMPTZ,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT uq_fila_offline_contador UNIQUE (tenant_id, dispositivo_id, contador_monotonico),
    CONSTRAINT fk_fila_offline_marcacao FOREIGN KEY (marcacao_id, marcacao_datahora)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT,
    CONSTRAINT ck_fila_offline_marcacao CHECK (
        (marcacao_id IS NULL AND marcacao_datahora IS NULL) OR
        (marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)
    )
);

COMMENT ON TABLE fila_offline IS
  'Itens capturados sem rede e enviados depois. Chegam cifrados e assinados; o servidor valida HMAC e contador antes de converter em marcacao. Esta tabela e mutavel de proposito: e o estagio ANTES de virar registro legal.';
COMMENT ON COLUMN fila_offline.payload_cifrado IS 'Item da fila cifrado em AES-GCM com chave derivada no keystore ou secure enclave do aparelho.';
COMMENT ON COLUMN fila_offline.hmac IS 'HMAC do item calculado no aparelho. Payload com HMAC invalido e rejeitado sem virar marcacao.';
COMMENT ON COLUMN fila_offline.contador_monotonico IS 'Contador que so cresce, por dispositivo. Reapresentar um valor ja usado caracteriza replay e colide na constraint unica.';
COMMENT ON COLUMN fila_offline.tempo_monotonico_ms IS 'Relogio monotonico do aparelho no instante da captura. Permite ao servidor classificar a confianca temporal mesmo com o relogio civil adulterado.';
COMMENT ON COLUMN fila_offline.expira_em IS 'Fim do TTL de sincronizacao (padrao 72 horas). Item vencido vira ocorrencia para tratamento, nao marcacao silenciosa.';

CREATE INDEX ix_fila_offline_pendentes ON fila_offline (tenant_id, status, recebido_em) WHERE status = 'pendente';
CREATE INDEX ix_fila_offline_dispositivo ON fila_offline (tenant_id, dispositivo_id, contador_monotonico DESC);


CREATE TABLE comprovantes (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    marcacao_id       UUID NOT NULL,
    marcacao_datahora TIMESTAMPTZ NOT NULL,
    colaborador_id    UUID REFERENCES colaboradores (id) ON DELETE RESTRICT,
    cpf               dom_cpf NOT NULL,
    numero            TEXT NOT NULL,
    nsr               BIGINT NOT NULL,
    conteudo_texto    TEXT NOT NULL,
    conteudo_ref      TEXT,
    hash_sha256       dom_sha256 NOT NULL,
    assinatura_ref    TEXT,
    emitido_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    disponivel_ate    TIMESTAMPTZ,
    canal_entrega     TEXT NOT NULL DEFAULT 'app'
                      CHECK (canal_entrega IN ('app','web','email','impresso','api','terminal')),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    CONSTRAINT uq_comprovantes_marcacao UNIQUE (tenant_id, marcacao_id),
    CONSTRAINT uq_comprovantes_numero UNIQUE (tenant_id, numero),
    CONSTRAINT fk_comprovantes_marcacao FOREIGN KEY (marcacao_id, marcacao_datahora)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT
);

COMMENT ON TABLE comprovantes IS
  'Comprovante de registro emitido a cada marcacao. Append-only. A impressao no momento da marcacao e dispensada porque garantimos acesso eletronico permanente, com as ultimas 48 horas sempre disponiveis em app e web.';
COMMENT ON COLUMN comprovantes.conteudo_texto IS 'Corpo textual do comprovante conforme o leiaute da Portaria, congelado na emissao.';
COMMENT ON COLUMN comprovantes.assinatura_ref IS 'Chave do arquivo .p7s de assinatura CAdES do comprovante, quando ja emitido com certificado.';
COMMENT ON COLUMN comprovantes.disponivel_ate IS 'Limite do acesso garantido. NULL significa disponibilidade permanente, que e o padrao do produto; a exigencia legal minima e de 48 horas.';

CREATE INDEX ix_comprovantes_colaborador ON comprovantes (tenant_id, colaborador_id, emitido_em DESC);
CREATE INDEX ix_comprovantes_48h ON comprovantes (tenant_id, emitido_em DESC);

CREATE TRIGGER trg_comprovantes_bloqueia_update
    BEFORE UPDATE ON comprovantes FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_comprovantes_bloqueia_delete
    BEFORE DELETE ON comprovantes FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE politicas_registro (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                     UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                    UUID NOT NULL REFERENCES empresas (id) ON DELETE CASCADE,
    unidade_id                    UUID REFERENCES unidades (id) ON DELETE CASCADE,
    canal                         TEXT CHECK (canal IN ('terminal','mobile','web','totem','api')),
    exige_geocerca                BOOLEAN NOT NULL DEFAULT TRUE,
    exige_facial                  BOOLEAN NOT NULL DEFAULT TRUE,
    exige_liveness                BOOLEAN NOT NULL DEFAULT TRUE,
    exige_attestation             BOOLEAN NOT NULL DEFAULT TRUE,
    exige_rede_permitida          BOOLEAN NOT NULL DEFAULT FALSE,
    limiar_facial                 NUMERIC(5,2) NOT NULL DEFAULT 75 CHECK (limiar_facial BETWEEN 0 AND 100),
    limiar_bloqueio               SMALLINT NOT NULL DEFAULT 40 CHECK (limiar_bloqueio BETWEEN 0 AND 100),
    limiar_revisao                SMALLINT NOT NULL DEFAULT 70 CHECK (limiar_revisao BETWEEN 0 AND 100),
    politica_modo_desenvolvedor   TEXT NOT NULL DEFAULT 'bloquear'
                                  CHECK (politica_modo_desenvolvedor IN ('bloquear','sinalizar','permitir')),
    politica_root                 TEXT NOT NULL DEFAULT 'bloquear'
                                  CHECK (politica_root IN ('bloquear','sinalizar','permitir')),
    politica_mock_location        TEXT NOT NULL DEFAULT 'bloquear'
                                  CHECK (politica_mock_location IN ('bloquear','sinalizar','permitir')),
    politica_fora_geocerca        TEXT NOT NULL DEFAULT 'sinalizar'
                                  CHECK (politica_fora_geocerca IN ('bloquear','sinalizar','permitir')),
    bloquear_vpn_proxy            BOOLEAN NOT NULL DEFAULT FALSE,
    exige_reautenticacao          BOOLEAN NOT NULL DEFAULT TRUE,
    ttl_offline_horas             INTEGER NOT NULL DEFAULT 72 CHECK (ttl_offline_horas > 0),
    ativo                         BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                    UUID,
    atualizado_em                 TIMESTAMPTZ,
    atualizado_por                UUID,
    CONSTRAINT ck_politicas_registro_limiares CHECK (limiar_revisao >= limiar_bloqueio)
);

COMMENT ON TABLE politicas_registro IS
  'Politica antifraude aplicada ao registro de ponto, por empresa, unidade e canal. Tabela ACRESCENTADA ao modelo sugerido: sem ela nao ha onde guardar a decisao configuravel entre bloquear, sinalizar e permitir, que e o que evita o falso dilema entre bloquear tudo e aceitar tudo.';
COMMENT ON COLUMN politicas_registro.limiar_bloqueio IS 'Score de confianca abaixo do qual o registro e recusado.';
COMMENT ON COLUMN politicas_registro.limiar_revisao IS 'Score entre limiar_bloqueio e este valor grava a marcacao e a envia para revisao do gestor. Acima grava direto.';
COMMENT ON COLUMN politicas_registro.politica_modo_desenvolvedor IS 'Comportamento diante de modo desenvolvedor ou depuracao USB ativos. Recomendacao: bloquear na sede, sinalizar em campo.';
COMMENT ON COLUMN politicas_registro.exige_rede_permitida IS 'Quando verdadeiro, o IP de origem precisa estar em redes_permitidas. Uso tipico no canal web.';
COMMENT ON COLUMN politicas_registro.ttl_offline_horas IS 'Prazo maximo para sincronizar um item da fila offline antes de ele virar ocorrencia.';

CREATE UNIQUE INDEX uq_politicas_registro ON politicas_registro (
    tenant_id, empresa_id,
    COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(canal, '*')
);

ALTER TABLE terminais
    ADD CONSTRAINT fk_terminais_rep_p
    FOREIGN KEY (rep_p_id) REFERENCES rep_ps (id) ON DELETE RESTRICT;


-- =============================================================================
-- 9. TRATAMENTO E APURACAO
--
-- Sequencia canonica do motor:
--   marcacoes imutaveis -> regras da jornada do dia -> tratamentos aplicaveis
--   -> apuracao do dia -> lancamentos de banco de horas -> fechamento
-- =============================================================================

CREATE TABLE tipos_tratamento (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo          TEXT NOT NULL,
    nome            TEXT NOT NULL,
    descricao       TEXT,
    categoria       TEXT NOT NULL
                    CHECK (categoria IN ('inclusao_marcacao','desconsideracao_marcacao','ajuste_intervalo',
                                         'abono','justificativa','afastamento','compensacao','ajuste_saldo')),
    exige_aprovacao BOOLEAN NOT NULL DEFAULT TRUE,
    exige_anexo     BOOLEAN NOT NULL DEFAULT FALSE,
    exige_motivo    BOOLEAN NOT NULL DEFAULT TRUE,
    afeta_afd       BOOLEAN NOT NULL DEFAULT FALSE,
    afeta_aej       BOOLEAN NOT NULL DEFAULT TRUE,
    permite_retroativo_dias INTEGER CHECK (permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0),
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID,
    excluido_em     TIMESTAMPTZ,
    excluido_por    UUID,
    CONSTRAINT ck_tipos_tratamento_afd CHECK (afeta_afd = FALSE)
);

COMMENT ON TABLE tipos_tratamento IS
  'Catalogo configuravel de tipos de tratamento. Tratamento e a UNICA forma de corrigir a jornada, e ele nunca altera a marcacao: ele se soma a ela na apuracao.';
COMMENT ON COLUMN tipos_tratamento.categoria IS 'inclusao_marcacao e o lancamento manual do RH ou gestor: aparece no espelho identificado como manual e vai para o AEJ, jamais para o AFD.';
COMMENT ON COLUMN tipos_tratamento.afeta_afd IS 'Sempre falso, garantido por CHECK. A coluna existe para tornar a regra explicita e auditavel, nao para ser configurada.';
COMMENT ON COLUMN tipos_tratamento.afeta_aej IS 'Verdadeiro faz o tratamento aparecer no Arquivo Eletronico de Jornada, que e onde a correcao legitimamente aparece.';

CREATE UNIQUE INDEX uq_tipos_tratamento_codigo ON tipos_tratamento (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE tratamentos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id      UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id          UUID NOT NULL REFERENCES vinculos (id) ON DELETE RESTRICT,
    tipo_tratamento_id  UUID NOT NULL REFERENCES tipos_tratamento (id) ON DELETE RESTRICT,
    data_referencia     DATE NOT NULL,
    marcacao_id         UUID,
    marcacao_datahora   TIMESTAMPTZ,
    datahora_proposta   TIMESTAMPTZ,
    sentido             TEXT CHECK (sentido IN ('entrada','saida','indefinido')),
    minutos_ajuste      INTEGER,
    tipo_afastamento_id UUID REFERENCES tipos_afastamento (id) ON DELETE RESTRICT,
    motivo              TEXT NOT NULL,
    observacao          TEXT,
    origem              TEXT NOT NULL DEFAULT 'gestor'
                        CHECK (origem IN ('colaborador','gestor','rh','sistema','integracao','importacao')),
    solicitacao_id      UUID,
    documento_id        UUID REFERENCES documentos (id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('rascunho','pendente','aprovado','reprovado','cancelado','aplicado')),
    aprovado_por        UUID,
    aprovado_em         TIMESTAMPTZ,
    reprovado_motivo    TEXT,
    aplicado_em         TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID,
    CONSTRAINT fk_tratamentos_marcacao FOREIGN KEY (marcacao_id, marcacao_datahora)
        REFERENCES marcacoes (id, datahora_marcacao) ON DELETE RESTRICT,
    CONSTRAINT ck_tratamentos_marcacao CHECK (
        (marcacao_id IS NULL AND marcacao_datahora IS NULL) OR
        (marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)
    )
);

COMMENT ON TABLE tratamentos IS
  'CAMADA DE CORRECAO. Um tratamento se refere a um dia e, opcionalmente, a uma marcacao existente, mas NUNCA a modifica. E aqui que vivem inclusao manual, desconsideracao, abono e justificativa, sempre com autor, data, motivo e anexo.';
COMMENT ON COLUMN tratamentos.marcacao_id IS 'Marcacao alvo, quando o tratamento se refere a uma existente (por exemplo desconsiderar uma batida duplicada). A marcacao permanece intacta no AFD.';
COMMENT ON COLUMN tratamentos.datahora_proposta IS 'Horario proposto em uma inclusao manual. Entra na apuracao e no AEJ; nunca gera registro no AFD.';
COMMENT ON COLUMN tratamentos.minutos_ajuste IS 'Ajuste em minutos para tratamentos de saldo ou de intervalo. Positivo credita, negativo debita.';
COMMENT ON COLUMN tratamentos.status IS 'aplicado marca que a apuracao ja consumiu o tratamento. Reprocessar o dia reavalia tudo do zero, de forma deterministica.';
COMMENT ON COLUMN tratamentos.solicitacao_id IS 'Solicitacao de workflow que originou o tratamento. FK criada na secao de workflow.';

CREATE INDEX ix_tratamentos_vinculo_data ON tratamentos (tenant_id, vinculo_id, data_referencia);
CREATE INDEX ix_tratamentos_pendentes ON tratamentos (tenant_id, status, data_referencia) WHERE status = 'pendente';
CREATE INDEX ix_tratamentos_marcacao ON tratamentos (tenant_id, marcacao_id) WHERE marcacao_id IS NOT NULL;


CREATE TABLE apuracoes_dia (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    vinculo_id                  UUID NOT NULL REFERENCES vinculos (id) ON DELETE CASCADE,
    colaborador_id              UUID NOT NULL REFERENCES colaboradores (id) ON DELETE CASCADE,
    data                        DATE NOT NULL,
    empresa_id                  UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id                  UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    departamento_id             UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    centro_custo_id             UUID REFERENCES centros_custo (id) ON DELETE RESTRICT,
    jornada_id                  UUID REFERENCES jornadas (id) ON DELETE RESTRICT,
    escala_id                   UUID REFERENCES escalas (id) ON DELETE RESTRICT,
    turno_id                    UUID REFERENCES turnos (id) ON DELETE RESTRICT,
    horario_id                  UUID REFERENCES horarios (id) ON DELETE RESTRICT,
    feriado_id                  UUID REFERENCES feriados (id) ON DELETE RESTRICT,
    afastamento_id              UUID REFERENCES afastamentos (id) ON DELETE RESTRICT,
    tipo_dia                    TEXT NOT NULL DEFAULT 'util'
                                CHECK (tipo_dia IN ('util','dsr','folga','feriado','ponto_facultativo',
                                                    'afastamento','compensado','nao_apurado')),
    previsto_minutos            INTEGER NOT NULL DEFAULT 0,
    trabalhado_minutos          INTEGER NOT NULL DEFAULT 0,
    normais_minutos             INTEGER NOT NULL DEFAULT 0,
    extras_minutos              INTEGER NOT NULL DEFAULT 0,
    extras_noturnas_minutos     INTEGER NOT NULL DEFAULT 0,
    noturno_minutos             INTEGER NOT NULL DEFAULT 0,
    noturno_ficta_minutos       INTEGER NOT NULL DEFAULT 0,
    intervalo_minutos           INTEGER NOT NULL DEFAULT 0,
    intervalo_previsto_minutos  INTEGER NOT NULL DEFAULT 0,
    intrajornada_suprimida_minutos INTEGER NOT NULL DEFAULT 0,
    interjornada_minutos        INTEGER,
    interjornada_violada        BOOLEAN NOT NULL DEFAULT FALSE,
    atraso_minutos              INTEGER NOT NULL DEFAULT 0,
    saida_antecipada_minutos    INTEGER NOT NULL DEFAULT 0,
    falta_minutos               INTEGER NOT NULL DEFAULT 0,
    abono_minutos               INTEGER NOT NULL DEFAULT 0,
    sobreaviso_minutos          INTEGER NOT NULL DEFAULT 0,
    prontidao_minutos           INTEGER NOT NULL DEFAULT 0,
    pausas_nr17_minutos         INTEGER NOT NULL DEFAULT 0,
    dsr_credito_minutos         INTEGER NOT NULL DEFAULT 0,
    dsr_debito_minutos          INTEGER NOT NULL DEFAULT 0,
    banco_credito_minutos       INTEGER NOT NULL DEFAULT 0,
    banco_debito_minutos        INTEGER NOT NULL DEFAULT 0,
    tolerancia_aplicada_minutos INTEGER NOT NULL DEFAULT 0,
    saldo_minutos               INTEGER NOT NULL DEFAULT 0,
    quantidade_marcacoes        SMALLINT NOT NULL DEFAULT 0 CHECK (quantidade_marcacoes >= 0),
    marcacoes_impares           BOOLEAN NOT NULL DEFAULT FALSE,
    tem_tratamento              BOOLEAN NOT NULL DEFAULT FALSE,
    status                      TEXT NOT NULL DEFAULT 'pendente'
                                CHECK (status IN ('pendente','apurado','com_ocorrencia','fechado','reaberto')),
    versao                      INTEGER NOT NULL DEFAULT 1 CHECK (versao >= 1),
    hash_entrada                dom_sha256,
    fechamento_id               UUID,
    apurado_em                  TIMESTAMPTZ,
    apurado_por                 UUID,
    criado_em                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                  UUID,
    atualizado_em               TIMESTAMPTZ,
    atualizado_por              UUID,
    CONSTRAINT uq_apuracoes_dia UNIQUE (tenant_id, vinculo_id, data)
);

COMMENT ON TABLE apuracoes_dia IS
  'Resultado consolidado do calculo de um dia para um vinculo. E derivada e recalculavel: apagar e recalcular a partir de marcacoes, tratamentos e regras precisa produzir exatamente o mesmo resultado.';
COMMENT ON COLUMN apuracoes_dia.previsto_minutos IS 'Carga prevista pelo horario ou pela escala do dia.';
COMMENT ON COLUMN apuracoes_dia.trabalhado_minutos IS 'Tempo efetivamente apurado, ja considerando tratamentos aprovados e tolerancias.';
COMMENT ON COLUMN apuracoes_dia.noturno_ficta_minutos IS 'Acrescimo decorrente da hora ficta de 52 minutos e 30 segundos aplicada ao periodo noturno.';
COMMENT ON COLUMN apuracoes_dia.intrajornada_suprimida_minutos IS 'Minutos de intervalo nao usufruidos. Geram a indenizacao de 50 por cento do art. 71, par. 4 da CLT.';
COMMENT ON COLUMN apuracoes_dia.interjornada_minutos IS 'Intervalo entre o fim da jornada anterior e o inicio desta. Abaixo do minimo gera ocorrencia.';
COMMENT ON COLUMN apuracoes_dia.marcacoes_impares IS 'Verdadeiro quando o dia tem numero impar de marcacoes. O sistema SINALIZA a inconsistencia e nao a corrige silenciosamente.';
COMMENT ON COLUMN apuracoes_dia.saldo_minutos IS 'Saldo liquido do dia. Positivo credita banco de horas, negativo debita, conforme a politica vigente.';
COMMENT ON COLUMN apuracoes_dia.hash_entrada IS 'Hash dos insumos (marcacoes, tratamentos, regras vigentes). Se nao mudou, o recalculo pode ser dispensado: e o que torna o reprocessamento barato e idempotente.';
COMMENT ON COLUMN apuracoes_dia.versao IS 'Incrementada a cada recalculo efetivo. O diff entre versoes vai para a auditoria.';
COMMENT ON COLUMN apuracoes_dia.fechamento_id IS 'Fechamento que travou o dia. FK criada na secao de fechamento. Dia travado so recalcula com reabertura autorizada.';

CREATE INDEX ix_apuracoes_dia_periodo ON apuracoes_dia (tenant_id, empresa_id, data);
CREATE INDEX ix_apuracoes_dia_colaborador ON apuracoes_dia (tenant_id, colaborador_id, data DESC);
CREATE INDEX ix_apuracoes_dia_status ON apuracoes_dia (tenant_id, status, data) WHERE status IN ('pendente','com_ocorrencia');
CREATE INDEX ix_apuracoes_dia_fechamento ON apuracoes_dia (tenant_id, fechamento_id) WHERE fechamento_id IS NOT NULL;
CREATE INDEX ix_apuracoes_dia_unidade ON apuracoes_dia (tenant_id, unidade_id, data);


CREATE TABLE apuracao_componentes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    apuracao_dia_id      UUID NOT NULL REFERENCES apuracoes_dia (id) ON DELETE CASCADE,
    codigo               TEXT NOT NULL,
    descricao            TEXT,
    categoria            TEXT NOT NULL
                         CHECK (categoria IN ('normal','extra','noturno','falta','abono','intervalo',
                                              'sobreaviso','prontidao','dsr','banco','indenizacao','pausa')),
    minutos              INTEGER NOT NULL,
    fator                NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK (fator >= 0),
    minutos_equivalentes INTEGER NOT NULL DEFAULT 0,
    origem               TEXT NOT NULL DEFAULT 'marcacao'
                         CHECK (origem IN ('marcacao','tratamento','afastamento','regra','banco','feriado')),
    inicio               TIMESTAMPTZ,
    fim                  TIMESTAMPTZ,
    detalhes             JSONB,
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por           UUID,
    atualizado_em        TIMESTAMPTZ,
    atualizado_por       UUID
);

COMMENT ON TABLE apuracao_componentes IS
  'Decomposicao auditavel da apuracao do dia. Cada linha explica de onde saiu cada bloco de minutos, o que torna o espelho defensavel numa fiscalizacao e o motor depuravel.';
COMMENT ON COLUMN apuracao_componentes.codigo IS 'Identificador da rubrica, por exemplo he_50, he_100, adicional_noturno, intrajornada_indenizada.';
COMMENT ON COLUMN apuracao_componentes.fator IS 'Multiplicador aplicado, por exemplo 1.5 para hora extra a 50 por cento.';
COMMENT ON COLUMN apuracao_componentes.minutos_equivalentes IS 'minutos multiplicados por fator, arredondado. E o valor que a folha consome.';

CREATE INDEX ix_apuracao_componentes_apuracao ON apuracao_componentes (tenant_id, apuracao_dia_id);
CREATE INDEX ix_apuracao_componentes_codigo ON apuracao_componentes (tenant_id, codigo, categoria);


CREATE TABLE ocorrencias (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id  UUID NOT NULL REFERENCES colaboradores (id) ON DELETE CASCADE,
    vinculo_id      UUID REFERENCES vinculos (id) ON DELETE CASCADE,
    apuracao_dia_id UUID REFERENCES apuracoes_dia (id) ON DELETE CASCADE,
    data            DATE NOT NULL,
    codigo          TEXT NOT NULL
                    CHECK (codigo IN ('marcacao_impar','sem_marcacao','falta','atraso','saida_antecipada',
                                      'extra_excedida','jornada_excedida','intrajornada_suprimida',
                                      'interjornada_violada','dsr_violado','pausa_nr17','fora_geocerca',
                                      'score_baixo','marcacao_duplicada','offline_tardio','banco_teto',
                                      'banco_vencendo','terminal_offline')),
    severidade      TEXT NOT NULL DEFAULT 'atencao'
                    CHECK (severidade IN ('info','atencao','alta','critica')),
    descricao       TEXT NOT NULL,
    detalhes        JSONB,
    status          TEXT NOT NULL DEFAULT 'aberta'
                    CHECK (status IN ('aberta','em_tratamento','resolvida','ignorada')),
    tratamento_id   UUID REFERENCES tratamentos (id) ON DELETE SET NULL,
    resolucao       TEXT,
    resolvida_em    TIMESTAMPTZ,
    resolvida_por   UUID,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID
);

COMMENT ON TABLE ocorrencias IS
  'Inconsistencia ou desvio detectado pelo motor. Ocorrencia nao corrige nada: ela chama o humano. E a fila de trabalho do gestor e do RH e a base do relatorio de ocorrencias.';
COMMENT ON COLUMN ocorrencias.codigo IS 'Tipo da ocorrencia. Os codigos sao fechados porque relatorios, notificacoes e webhooks dependem deles.';
COMMENT ON COLUMN ocorrencias.tratamento_id IS 'Tratamento que resolveu a ocorrencia, quando houve.';

CREATE INDEX ix_ocorrencias_abertas ON ocorrencias (tenant_id, status, data DESC) WHERE status IN ('aberta','em_tratamento');
CREATE INDEX ix_ocorrencias_colaborador ON ocorrencias (tenant_id, colaborador_id, data DESC);
CREATE INDEX ix_ocorrencias_codigo ON ocorrencias (tenant_id, codigo, data);


-- =============================================================================
-- 10. BANCO DE HORAS
-- =============================================================================

CREATE TABLE bh_politicas (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id                  UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo                      TEXT NOT NULL,
    nome                        TEXT NOT NULL,
    descricao                   TEXT,
    regime                      TEXT NOT NULL
                                CHECK (regime IN ('individual','coletivo','convencao','especial')),
    periodo_meses               INTEGER NOT NULL CHECK (periodo_meses BETWEEN 1 AND 12),
    metodo_consumo              TEXT NOT NULL DEFAULT 'fifo'
                                CHECK (metodo_consumo IN ('fifo','lifo')),
    fator_credito_padrao        NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK (fator_credito_padrao > 0),
    fator_debito_padrao         NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK (fator_debito_padrao > 0),
    fatores_por_faixa           JSONB,
    teto_positivo_minutos       INTEGER CHECK (teto_positivo_minutos IS NULL OR teto_positivo_minutos >= 0),
    teto_negativo_minutos       INTEGER CHECK (teto_negativo_minutos IS NULL OR teto_negativo_minutos >= 0),
    limite_diario_minutos       INTEGER NOT NULL DEFAULT 120 CHECK (limite_diario_minutos >= 0),
    limite_jornada_diaria_minutos INTEGER NOT NULL DEFAULT 600 CHECK (limite_jornada_diaria_minutos > 0),
    acao_vencimento             TEXT NOT NULL DEFAULT 'quitar_folha'
                                CHECK (acao_vencimento IN ('quitar_folha','expirar','prorrogar','manter')),
    dias_pre_aviso              INTEGER[] NOT NULL DEFAULT '{30,15,7}',
    bloqueia_extra_no_teto      BOOLEAN NOT NULL DEFAULT FALSE,
    permite_saldo_negativo      BOOLEAN NOT NULL DEFAULT TRUE,
    documento_acordo_id         UUID REFERENCES documentos (id) ON DELETE SET NULL,
    vigencia_inicio             DATE NOT NULL,
    vigencia_fim                DATE,
    ativo                       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                  UUID,
    atualizado_em               TIMESTAMPTZ,
    atualizado_por              UUID,
    excluido_em                 TIMESTAMPTZ,
    excluido_por                UUID,
    CONSTRAINT ck_bh_politicas_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio),
    CONSTRAINT ck_bh_politicas_periodo_legal CHECK (
        (regime = 'individual' AND periodo_meses <= 6) OR
        (regime IN ('coletivo','convencao') AND periodo_meses <= 12) OR
        (regime = 'especial')
    )
);

COMMENT ON TABLE bh_politicas IS
  'Regras do banco de horas por empresa. O limite legal esta no CHECK: acordo individual escrito compensa em ate 6 meses; acordo ou convencao coletiva, em ate 12. O teto de 10 horas diarias e respeitado em limite_jornada_diaria_minutos.';
COMMENT ON COLUMN bh_politicas.regime IS 'individual: acordo escrito com o empregado. coletivo e convencao: instrumento sindical. especial: regime autorizado por norma propria, sem teto padrao.';
COMMENT ON COLUMN bh_politicas.metodo_consumo IS 'Ordem de consumo do saldo: fifo consome primeiro as horas mais antigas (protege o empregado do vencimento); lifo consome as mais recentes.';
COMMENT ON COLUMN bh_politicas.fatores_por_faixa IS 'Fatores diferenciados de credito por faixa em JSON, por exemplo primeira e segunda hora a 1.5 e dominical a 2.0.';
COMMENT ON COLUMN bh_politicas.teto_positivo_minutos IS 'Saldo credor maximo. Ao atingir, gera alerta e, se configurado, bloqueia novas extras.';
COMMENT ON COLUMN bh_politicas.acao_vencimento IS 'O que acontece com as horas ao fim do periodo: quitar em folha, expirar, prorrogar para o proximo periodo ou manter em aberto.';
COMMENT ON COLUMN bh_politicas.dias_pre_aviso IS 'Antecedencias em dias para avisar gestor e colaborador sobre horas a vencer.';
COMMENT ON COLUMN bh_politicas.documento_acordo_id IS 'Acordo assinado que da validade juridica ao regime. Sem ele, o banco de horas e questionavel em juizo.';

CREATE UNIQUE INDEX uq_bh_politicas_codigo ON bh_politicas (tenant_id, empresa_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE bh_contas (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id       UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id           UUID NOT NULL REFERENCES vinculos (id) ON DELETE RESTRICT,
    bh_politica_id       UUID NOT NULL REFERENCES bh_politicas (id) ON DELETE RESTRICT,
    codigo               TEXT NOT NULL DEFAULT 'normal',
    nome                 TEXT NOT NULL,
    periodo_inicio       DATE NOT NULL,
    periodo_fim          DATE NOT NULL,
    status               TEXT NOT NULL DEFAULT 'aberta'
                         CHECK (status IN ('aberta','encerrada','quitada','expirada','suspensa')),
    saldo_atual_minutos  INTEGER NOT NULL DEFAULT 0,
    ultima_sequencia     BIGINT NOT NULL DEFAULT 0 CHECK (ultima_sequencia >= 0),
    ultimo_hash          dom_sha256,
    encerrada_em         TIMESTAMPTZ,
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por           UUID,
    atualizado_em        TIMESTAMPTZ,
    atualizado_por       UUID,
    CONSTRAINT uq_bh_contas UNIQUE (tenant_id, vinculo_id, codigo, periodo_inicio),
    CONSTRAINT ck_bh_contas_periodo CHECK (periodo_fim > periodo_inicio)
);

COMMENT ON TABLE bh_contas IS
  'Conta-corrente de horas de um vinculo dentro de um periodo de apuracao do banco. Um mesmo vinculo pode ter varias contas simultaneas com fatores diferentes (banco normal, banco de sobreaviso, banco de feriado).';
COMMENT ON COLUMN bh_contas.codigo IS 'Identificador da conta dentro do vinculo, por exemplo normal, sobreaviso, feriado.';
COMMENT ON COLUMN bh_contas.periodo_fim IS 'Fim do periodo de compensacao, derivado de bh_politicas.periodo_meses. E a data que dispara quitacao ou expiracao.';
COMMENT ON COLUMN bh_contas.saldo_atual_minutos IS 'Saldo materializado para leitura rapida. A verdade e a soma de bh_lancamentos; divergencia entre os dois e defeito e deve falhar em teste.';
COMMENT ON COLUMN bh_contas.ultima_sequencia IS 'Ultimo numero de sequencia usado no extrato. Alocado com FOR UPDATE nesta linha para nao haver buraco.';
COMMENT ON COLUMN bh_contas.ultimo_hash IS 'Hash do ultimo lancamento, elo anterior da cadeia do extrato.';

CREATE INDEX ix_bh_contas_vinculo ON bh_contas (tenant_id, vinculo_id, status);
CREATE INDEX ix_bh_contas_vencimento ON bh_contas (tenant_id, periodo_fim) WHERE status = 'aberta';


CREATE TABLE bh_lancamentos (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    bh_conta_id           UUID NOT NULL REFERENCES bh_contas (id) ON DELETE RESTRICT,
    sequencia             BIGINT NOT NULL CHECK (sequencia >= 1),
    data_competencia      DATE NOT NULL,
    tipo                  TEXT NOT NULL
                          CHECK (tipo IN ('credito','debito','quitacao','expiracao','ajuste','transferencia','estorno')),
    origem                TEXT NOT NULL
                          CHECK (origem IN ('apuracao','tratamento','solicitacao','quitacao','expiracao',
                                            'ajuste_manual','importacao','fechamento','rescisao')),
    apuracao_dia_id       UUID REFERENCES apuracoes_dia (id) ON DELETE RESTRICT,
    tratamento_id         UUID REFERENCES tratamentos (id) ON DELETE RESTRICT,
    quitacao_id           UUID,
    estorna_lancamento_id UUID REFERENCES bh_lancamentos (id) ON DELETE RESTRICT,
    minutos               INTEGER NOT NULL CHECK (minutos <> 0),
    fator                 NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK (fator > 0),
    minutos_equivalentes  INTEGER NOT NULL,
    saldo_apos_minutos    INTEGER NOT NULL,
    vence_em              DATE,
    consumido_minutos     INTEGER NOT NULL DEFAULT 0 CHECK (consumido_minutos >= 0),
    descricao             TEXT NOT NULL,
    hash_anterior         dom_sha256,
    hash_registro         dom_sha256 NOT NULL,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    CONSTRAINT uq_bh_lancamentos_sequencia UNIQUE (tenant_id, bh_conta_id, sequencia)
);

COMMENT ON TABLE bh_lancamentos IS
  'EXTRATO IMUTAVEL do banco de horas, com cadeia de hash. Gatilhos barram DELETE, TRUNCATE e qualquer UPDATE que nao seja exclusivamente em consumido_minutos (unica excecao, exigida pela rotina de consumo FIFO/LIFO). Corrigir um lancamento significa emitir um estorno, nunca reescrever a linha.';
COMMENT ON COLUMN bh_lancamentos.sequencia IS 'Ordem do lancamento dentro da conta, sem lacunas. Alocada em bh_contas.ultima_sequencia na mesma transacao.';
COMMENT ON COLUMN bh_lancamentos.minutos IS 'Minutos brutos do evento. Positivo em credito, negativo em debito. Zero e proibido.';
COMMENT ON COLUMN bh_lancamentos.minutos_equivalentes IS 'minutos aplicado o fator. E este valor que altera o saldo.';
COMMENT ON COLUMN bh_lancamentos.saldo_apos_minutos IS 'Saldo da conta depois deste lancamento. Torna o extrato legivel sem recalcular a soma corrida.';
COMMENT ON COLUMN bh_lancamentos.vence_em IS 'Data em que este credito especifico vence. E o que permite FIFO e LIFO reais em vez de saldo unico indistinto.';
COMMENT ON COLUMN bh_lancamentos.consumido_minutos IS 'Quanto deste credito ja foi consumido por debitos posteriores. Atualizado apenas pela rotina de consumo, que emite lancamentos proprios.';
COMMENT ON COLUMN bh_lancamentos.estorna_lancamento_id IS 'Lancamento estornado por este. Presente somente quando tipo e estorno.';
COMMENT ON COLUMN bh_lancamentos.quitacao_id IS 'Quitacao que originou o lancamento. FK criada logo apos a tabela bh_quitacoes.';

CREATE INDEX ix_bh_lancamentos_conta ON bh_lancamentos (tenant_id, bh_conta_id, sequencia);
CREATE INDEX ix_bh_lancamentos_competencia ON bh_lancamentos (tenant_id, data_competencia);
CREATE INDEX ix_bh_lancamentos_vencimento ON bh_lancamentos (tenant_id, vence_em) WHERE vence_em IS NOT NULL AND tipo = 'credito';
CREATE INDEX ix_bh_lancamentos_apuracao ON bh_lancamentos (tenant_id, apuracao_dia_id) WHERE apuracao_dia_id IS NOT NULL;

CREATE TRIGGER trg_bh_lancamentos_bloqueia_delete
    BEFORE DELETE ON bh_lancamentos FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE bh_saldos (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    bh_conta_id              UUID NOT NULL REFERENCES bh_contas (id) ON DELETE CASCADE,
    data_referencia          DATE NOT NULL,
    saldo_minutos            INTEGER NOT NULL,
    credito_periodo_minutos  INTEGER NOT NULL DEFAULT 0,
    debito_periodo_minutos   INTEGER NOT NULL DEFAULT 0,
    a_vencer_30_minutos      INTEGER NOT NULL DEFAULT 0,
    a_vencer_15_minutos      INTEGER NOT NULL DEFAULT 0,
    a_vencer_7_minutos       INTEGER NOT NULL DEFAULT 0,
    projecao_vencimento_minutos INTEGER NOT NULL DEFAULT 0,
    calculado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por               UUID,
    atualizado_em            TIMESTAMPTZ,
    atualizado_por           UUID,
    CONSTRAINT uq_bh_saldos UNIQUE (tenant_id, bh_conta_id, data_referencia)
);

COMMENT ON TABLE bh_saldos IS
  'Fotografia diaria do saldo de cada conta. Existe para relatorio, dashboard e simulador responderem rapido sem varrer o extrato inteiro. Sempre reconstrutivel a partir de bh_lancamentos.';
COMMENT ON COLUMN bh_saldos.a_vencer_30_minutos IS 'Minutos que vencem nos proximos 30 dias. Alimenta o pre-aviso ao gestor e ao colaborador.';
COMMENT ON COLUMN bh_saldos.projecao_vencimento_minutos IS 'Projecao de quanto vencera ate o fim do periodo mantido o ritmo atual.';

CREATE INDEX ix_bh_saldos_data ON bh_saldos (tenant_id, data_referencia DESC);


CREATE TABLE bh_quitacoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    bh_conta_id         UUID NOT NULL REFERENCES bh_contas (id) ON DELETE RESTRICT,
    colaborador_id      UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    tipo                TEXT NOT NULL
                        CHECK (tipo IN ('folha','folga','rescisao','expiracao','compensacao_programada')),
    minutos             INTEGER NOT NULL CHECK (minutos > 0),
    fator               NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK (fator > 0),
    valor               NUMERIC(14,2) CHECK (valor IS NULL OR valor >= 0),
    competencia_folha   dom_competencia,
    data_prevista       DATE,
    data_efetivacao     DATE,
    status              TEXT NOT NULL DEFAULT 'planejada'
                        CHECK (status IN ('planejada','aprovada','efetivada','cancelada')),
    aprovado_por        UUID,
    aprovado_em         TIMESTAMPTZ,
    observacao          TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID
);

COMMENT ON TABLE bh_quitacoes IS
  'Liquidacao de saldo de banco de horas: pagamento em folha, folga programada, acerto na rescisao ou expiracao. Cada quitacao efetivada gera lancamento correspondente no extrato.';
COMMENT ON COLUMN bh_quitacoes.tipo IS 'expiracao registra a perda de horas por vencimento, que precisa ficar rastreavel mesmo sem pagamento.';
COMMENT ON COLUMN bh_quitacoes.competencia_folha IS 'Competencia AAAA-MM em que o pagamento entra na folha.';
COMMENT ON COLUMN bh_quitacoes.valor IS 'Valor monetario quando a quitacao e em dinheiro. Calculado a partir do valor-hora do contrato.';

CREATE INDEX ix_bh_quitacoes_conta ON bh_quitacoes (tenant_id, bh_conta_id, status);
CREATE INDEX ix_bh_quitacoes_competencia ON bh_quitacoes (tenant_id, competencia_folha) WHERE tipo = 'folha';

ALTER TABLE bh_lancamentos
    ADD CONSTRAINT fk_bh_lancamentos_quitacao
    FOREIGN KEY (quitacao_id) REFERENCES bh_quitacoes (id) ON DELETE RESTRICT;


-- =============================================================================
-- 11. WORKFLOW, APROVACOES E NOTIFICACOES
-- =============================================================================

CREATE TABLE tipos_solicitacao (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo                  TEXT NOT NULL,
    nome                    TEXT NOT NULL,
    descricao               TEXT,
    categoria               TEXT NOT NULL
                            CHECK (categoria IN ('ajuste_ponto','abono','justificativa','ferias','folga',
                                                 'compensacao','afastamento','troca_escala','hora_extra',
                                                 'desbloqueio_dispositivo','outro')),
    etapas                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    prazo_resposta_horas    INTEGER CHECK (prazo_resposta_horas IS NULL OR prazo_resposta_horas > 0),
    escalonar_apos_horas    INTEGER CHECK (escalonar_apos_horas IS NULL OR escalonar_apos_horas > 0),
    exige_anexo             BOOLEAN NOT NULL DEFAULT FALSE,
    exige_justificativa     BOOLEAN NOT NULL DEFAULT TRUE,
    permite_retroativo_dias INTEGER CHECK (permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0),
    tipo_tratamento_id      UUID REFERENCES tipos_tratamento (id) ON DELETE RESTRICT,
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por              UUID,
    atualizado_em           TIMESTAMPTZ,
    atualizado_por          UUID,
    excluido_em             TIMESTAMPTZ,
    excluido_por            UUID
);

COMMENT ON TABLE tipos_solicitacao IS
  'Catalogo configuravel de pedidos que o colaborador ou o gestor podem abrir, com a cadeia de aprovacao de cada um.';
COMMENT ON COLUMN tipos_solicitacao.etapas IS 'Cadeia de aprovacao em JSON, uma entrada por etapa com o papel responsavel, por exemplo gestor e depois rh.';
COMMENT ON COLUMN tipos_solicitacao.escalonar_apos_horas IS 'Prazo apos o qual a pendencia sobe automaticamente para o proximo nivel.';
COMMENT ON COLUMN tipos_solicitacao.tipo_tratamento_id IS 'Tratamento gerado quando a solicitacao e aprovada. E o elo entre workflow e apuracao.';

CREATE UNIQUE INDEX uq_tipos_solicitacao_codigo ON tipos_solicitacao (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE solicitacoes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    tipo_solicitacao_id   UUID NOT NULL REFERENCES tipos_solicitacao (id) ON DELETE RESTRICT,
    colaborador_id        UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id            UUID REFERENCES vinculos (id) ON DELETE RESTRICT,
    solicitante_usuario_id UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    protocolo             TEXT NOT NULL,
    data_referencia       DATE,
    data_inicio           DATE,
    data_fim              DATE,
    descricao             TEXT NOT NULL,
    payload               JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                TEXT NOT NULL DEFAULT 'pendente'
                          CHECK (status IN ('rascunho','pendente','em_aprovacao','aprovada','reprovada',
                                            'cancelada','expirada')),
    etapa_atual           INTEGER NOT NULL DEFAULT 1 CHECK (etapa_atual >= 1),
    prazo_em              TIMESTAMPTZ,
    concluida_em          TIMESTAMPTZ,
    resultado             TEXT,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT uq_solicitacoes_protocolo UNIQUE (tenant_id, protocolo),
    CONSTRAINT ck_solicitacoes_periodo CHECK (data_fim IS NULL OR data_inicio IS NULL OR data_fim >= data_inicio)
);

COMMENT ON TABLE solicitacoes IS
  'Pedido aberto no workflow. Percorre a cadeia definida no tipo e, quando aprovado, materializa um tratamento ou um afastamento. A solicitacao nunca altera marcacao diretamente.';
COMMENT ON COLUMN solicitacoes.protocolo IS 'Numero de protocolo legivel, informado ao colaborador para acompanhamento.';
COMMENT ON COLUMN solicitacoes.payload IS 'Conteudo especifico do tipo em JSON, por exemplo os horarios propostos em um ajuste de ponto.';
COMMENT ON COLUMN solicitacoes.etapa_atual IS 'Indice da etapa em andamento na cadeia definida em tipos_solicitacao.etapas.';

CREATE INDEX ix_solicitacoes_colaborador ON solicitacoes (tenant_id, colaborador_id, criado_em DESC);
CREATE INDEX ix_solicitacoes_pendentes ON solicitacoes (tenant_id, status, prazo_em) WHERE status IN ('pendente','em_aprovacao');
CREATE INDEX ix_solicitacoes_data ON solicitacoes (tenant_id, data_referencia);


CREATE TABLE aprovacoes (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    solicitacao_id         UUID NOT NULL REFERENCES solicitacoes (id) ON DELETE CASCADE,
    etapa                  INTEGER NOT NULL CHECK (etapa >= 1),
    papel                  TEXT NOT NULL DEFAULT 'gestor'
                           CHECK (papel IN ('gestor','rh','diretoria','sistema')),
    aprovador_usuario_id   UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    aprovador_delegacao_id UUID REFERENCES delegacoes (id) ON DELETE SET NULL,
    decisao                TEXT NOT NULL DEFAULT 'pendente'
                           CHECK (decisao IN ('pendente','aprovada','reprovada','delegada','expirada','cancelada')),
    comentario             TEXT,
    prazo_em               TIMESTAMPTZ,
    notificado_em          TIMESTAMPTZ,
    escalonado_em          TIMESTAMPTZ,
    decidido_em            TIMESTAMPTZ,
    ip                     INET,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID
);

COMMENT ON TABLE aprovacoes IS
  'Uma linha por etapa da cadeia de uma solicitacao. Guarda quem decidiu, quando, de onde e se decidiu por delegacao. E a prova de quem autorizou cada correcao de jornada.';
COMMENT ON COLUMN aprovacoes.aprovador_delegacao_id IS 'Delegacao vigente que autorizou o aprovador a decidir no lugar do titular.';
COMMENT ON COLUMN aprovacoes.escalonado_em IS 'Momento em que a pendencia subiu de nivel por estouro de prazo.';

CREATE UNIQUE INDEX uq_aprovacoes_etapa ON aprovacoes (tenant_id, solicitacao_id, etapa);
CREATE INDEX ix_aprovacoes_pendentes ON aprovacoes (tenant_id, aprovador_usuario_id, decisao) WHERE decisao = 'pendente';


CREATE TABLE anexos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    entidade       TEXT NOT NULL
                   CHECK (entidade IN ('solicitacao','tratamento','afastamento','colaborador',
                                       'fechamento','ocorrencia','marcacao','importacao')),
    entidade_id    UUID NOT NULL,
    nome_arquivo   TEXT NOT NULL,
    conteudo_ref   TEXT NOT NULL,
    mime_type      TEXT,
    tamanho_bytes  BIGINT CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    hash_sha256    dom_sha256,
    descricao      TEXT,
    confidencial   BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    excluido_em    TIMESTAMPTZ,
    excluido_por   UUID
);

COMMENT ON TABLE anexos IS
  'Arquivos anexados a qualquer entidade do workflow. A referencia e polimorfica (entidade mais entidade_id) e por isso NAO tem chave estrangeira: a integridade e garantida na aplicacao. Divergencia consciente, documentada no glossario.';
COMMENT ON COLUMN anexos.entidade IS 'Nome logico da tabela alvo. O conjunto e fechado por CHECK para evitar referencia orfa a tabelas inexistentes.';
COMMENT ON COLUMN anexos.confidencial IS 'Anexo com dado sensivel, como atestado medico. Leitura gera registro em acessos_dados_sensiveis.';

CREATE INDEX ix_anexos_entidade ON anexos (tenant_id, entidade, entidade_id) WHERE excluido_em IS NULL;


CREATE TABLE notificacoes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id            UUID REFERENCES usuarios (id) ON DELETE CASCADE,
    colaborador_id        UUID REFERENCES colaboradores (id) ON DELETE CASCADE,
    canal                 TEXT NOT NULL
                          CHECK (canal IN ('push','email','whatsapp','in_app','sms')),
    evento                TEXT NOT NULL,
    titulo                TEXT NOT NULL,
    corpo                 TEXT NOT NULL,
    payload               JSONB,
    prioridade            TEXT NOT NULL DEFAULT 'normal'
                          CHECK (prioridade IN ('baixa','normal','alta','critica')),
    status                TEXT NOT NULL DEFAULT 'pendente'
                          CHECK (status IN ('pendente','enviada','entregue','lida','falhou','descartada')),
    agendada_para         TIMESTAMPTZ,
    enviada_em            TIMESTAMPTZ,
    entregue_em           TIMESTAMPTZ,
    lida_em               TIMESTAMPTZ,
    tentativas            INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    erro                  TEXT,
    provedor              TEXT,
    provedor_mensagem_id  TEXT,
    entidade              TEXT,
    entidade_id           UUID,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT ck_notificacoes_destinatario CHECK (usuario_id IS NOT NULL OR colaborador_id IS NOT NULL)
);

COMMENT ON TABLE notificacoes IS
  'Mensagem enviada ao usuario em qualquer canal. Uma linha por canal: o mesmo evento notificado por push e e-mail gera duas linhas, cada uma com seu proprio ciclo de entrega.';
COMMENT ON COLUMN notificacoes.evento IS 'Codigo do evento no catalogo events.yaml, por exemplo banco_horas.vencendo.';
COMMENT ON COLUMN notificacoes.provedor IS 'Servico usado no envio, por exemplo opasuite no canal whatsapp ou fcm no push.';
COMMENT ON COLUMN notificacoes.agendada_para IS 'Envio programado, respeitando a janela de silencio configurada pelo usuario.';

CREATE INDEX ix_notificacoes_usuario ON notificacoes (tenant_id, usuario_id, criado_em DESC);
CREATE INDEX ix_notificacoes_pendentes ON notificacoes (tenant_id, status, agendada_para) WHERE status = 'pendente';
CREATE INDEX ix_notificacoes_nao_lidas ON notificacoes (tenant_id, usuario_id) WHERE canal = 'in_app' AND lida_em IS NULL;


CREATE TABLE notificacao_preferencias (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id     UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    evento         TEXT NOT NULL,
    canal          TEXT NOT NULL
                   CHECK (canal IN ('push','email','whatsapp','in_app','sms')),
    habilitado     BOOLEAN NOT NULL DEFAULT TRUE,
    janela_inicio  TIME,
    janela_fim     TIME,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por     UUID,
    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_notificacao_preferencias UNIQUE (tenant_id, usuario_id, evento, canal)
);

COMMENT ON TABLE notificacao_preferencias IS
  'Preferencia do usuario por evento e canal. Ausencia de linha significa usar o padrao do tenant.';
COMMENT ON COLUMN notificacao_preferencias.evento IS 'Codigo do evento ou o coringa * para valer em todos.';
COMMENT ON COLUMN notificacao_preferencias.janela_inicio IS 'Inicio da janela em que o usuario aceita ser notificado. Fora dela a mensagem e agendada.';


-- =============================================================================
-- 12. FECHAMENTO E ESPELHO
-- =============================================================================

CREATE TABLE periodos (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id        UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    codigo            TEXT NOT NULL,
    tipo              TEXT NOT NULL DEFAULT 'mensal'
                      CHECK (tipo IN ('mensal','quinzenal','semanal','personalizado','banco_horas')),
    data_inicio       DATE NOT NULL,
    data_fim          DATE NOT NULL,
    competencia_folha dom_competencia,
    status            TEXT NOT NULL DEFAULT 'aberto'
                      CHECK (status IN ('aberto','em_conferencia','fechado','reaberto','exportado')),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por        UUID,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID,
    CONSTRAINT uq_periodos_codigo UNIQUE (tenant_id, empresa_id, tipo, codigo),
    CONSTRAINT ck_periodos_intervalo CHECK (data_fim >= data_inicio)
);

COMMENT ON TABLE periodos IS
  'Janela de apuracao da empresa. O periodo do ponto e independente do periodo do banco de horas: por isso o tipo banco_horas existe como valor proprio.';
COMMENT ON COLUMN periodos.codigo IS 'Rotulo do periodo, tipicamente AAAA-MM em periodos mensais.';
COMMENT ON COLUMN periodos.competencia_folha IS 'Competencia da folha que consome este periodo. Pode diferir do mes civil quando o corte nao e no ultimo dia.';

CREATE INDEX ix_periodos_empresa ON periodos (tenant_id, empresa_id, data_inicio DESC);


CREATE TABLE fechamentos (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    periodo_id           UUID NOT NULL REFERENCES periodos (id) ON DELETE RESTRICT,
    empresa_id           UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    unidade_id           UUID REFERENCES unidades (id) ON DELETE RESTRICT,
    departamento_id      UUID REFERENCES departamentos (id) ON DELETE RESTRICT,
    escopo               TEXT NOT NULL DEFAULT 'empresa'
                         CHECK (escopo IN ('empresa','unidade','departamento','equipe','colaborador')),
    status               TEXT NOT NULL DEFAULT 'em_andamento'
                         CHECK (status IN ('em_andamento','conferido','fechado','reaberto','cancelado')),
    total_colaboradores  INTEGER NOT NULL DEFAULT 0,
    total_ocorrencias    INTEGER NOT NULL DEFAULT 0,
    total_pendencias     INTEGER NOT NULL DEFAULT 0,
    hash_conteudo        dom_sha256,
    conferido_em         TIMESTAMPTZ,
    conferido_por        UUID,
    fechado_em           TIMESTAMPTZ,
    fechado_por          UUID,
    reaberto_em          TIMESTAMPTZ,
    reaberto_por         UUID,
    motivo_reabertura    TEXT,
    exportado_em         TIMESTAMPTZ,
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por           UUID,
    atualizado_em        TIMESTAMPTZ,
    atualizado_por       UUID,
    CONSTRAINT ck_fechamentos_reabertura CHECK (
        reaberto_em IS NULL OR (motivo_reabertura IS NOT NULL AND reaberto_por IS NOT NULL)
    )
);

COMMENT ON TABLE fechamentos IS
  'Trava do periodo para um escopo. Fechado, o dia nao recalcula. A reabertura e sempre nominal e justificada, garantido por CHECK, e fica na auditoria.';
COMMENT ON COLUMN fechamentos.hash_conteudo IS 'Hash do conjunto de apuracoes travadas. Permite provar que nada mudou depois do fechamento.';
COMMENT ON COLUMN fechamentos.motivo_reabertura IS 'Justificativa obrigatoria da reabertura. Sem ela o CHECK impede a operacao.';
COMMENT ON COLUMN fechamentos.total_pendencias IS 'Ocorrencias e solicitacoes ainda abertas no momento do fechamento. Fechar com pendencia e possivel, mas fica registrado.';

CREATE INDEX ix_fechamentos_periodo ON fechamentos (tenant_id, periodo_id, status);
CREATE INDEX ix_fechamentos_empresa ON fechamentos (tenant_id, empresa_id, fechado_em DESC);


CREATE TABLE espelhos (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    periodo_id                UUID NOT NULL REFERENCES periodos (id) ON DELETE RESTRICT,
    fechamento_id             UUID REFERENCES fechamentos (id) ON DELETE RESTRICT,
    colaborador_id            UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    vinculo_id                UUID NOT NULL REFERENCES vinculos (id) ON DELETE RESTRICT,
    versao                    INTEGER NOT NULL DEFAULT 1 CHECK (versao >= 1),
    tipo                      TEXT NOT NULL DEFAULT 'previo'
                              CHECK (tipo IN ('previo','oficial','retificado')),
    conteudo                  JSONB NOT NULL,
    conteudo_ref              TEXT,
    hash_sha256               dom_sha256 NOT NULL,
    total_previsto_minutos    INTEGER NOT NULL DEFAULT 0,
    total_trabalhado_minutos  INTEGER NOT NULL DEFAULT 0,
    total_extras_minutos      INTEGER NOT NULL DEFAULT 0,
    total_faltas_minutos      INTEGER NOT NULL DEFAULT 0,
    total_noturno_minutos     INTEGER NOT NULL DEFAULT 0,
    saldo_banco_minutos       INTEGER NOT NULL DEFAULT 0,
    gerado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    gerado_por                UUID,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID,
    atualizado_em             TIMESTAMPTZ,
    atualizado_por            UUID,
    CONSTRAINT uq_espelhos_versao UNIQUE (tenant_id, periodo_id, vinculo_id, versao)
);

COMMENT ON TABLE espelhos IS
  'Espelho de ponto do periodo para um vinculo. O tipo oficial e emitido no fechamento e e o documento que o colaborador assina. Retificacao gera versao nova, jamais sobrescreve a anterior.';
COMMENT ON COLUMN espelhos.conteudo IS 'Snapshot completo do espelho em JSON: dias, marcacoes, tratamentos, totais e observacoes, congelado na emissao.';
COMMENT ON COLUMN espelhos.conteudo_ref IS 'Chave do PDF no MinIO.';
COMMENT ON COLUMN espelhos.hash_sha256 IS 'Hash do conteudo. E o valor efetivamente assinado pelo colaborador, o que torna a assinatura verificavel e nao repudiavel.';

CREATE INDEX ix_espelhos_colaborador ON espelhos (tenant_id, colaborador_id, gerado_em DESC);
CREATE INDEX ix_espelhos_fechamento ON espelhos (tenant_id, fechamento_id) WHERE fechamento_id IS NOT NULL;


CREATE TABLE assinaturas_espelho (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    espelho_id               UUID NOT NULL REFERENCES espelhos (id) ON DELETE RESTRICT,
    signatario_tipo          TEXT NOT NULL
                             CHECK (signatario_tipo IN ('colaborador','gestor','rh','empregador')),
    signatario_usuario_id    UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    signatario_colaborador_id UUID REFERENCES colaboradores (id) ON DELETE SET NULL,
    metodo                   TEXT NOT NULL DEFAULT 'aceite_eletronico'
                             CHECK (metodo IN ('aceite_eletronico','icp_brasil','biometria','senha','token_email')),
    hash_assinado            dom_sha256 NOT NULL,
    assinatura               BYTEA,
    certificado_ref          TEXT,
    carimbo_tempo            TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip                       INET,
    user_agent               TEXT,
    geolocalizacao           JSONB,
    status                   TEXT NOT NULL DEFAULT 'pendente'
                             CHECK (status IN ('pendente','assinado','recusado','expirado')),
    recusa_motivo            TEXT,
    criado_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por               UUID
);

COMMENT ON TABLE assinaturas_espelho IS
  'Aceite eletronico do espelho de ponto. Append-only: recusar e depois assinar gera duas linhas, preservando o historico. E a prova de ciencia do colaborador sobre a jornada apurada.';
COMMENT ON COLUMN assinaturas_espelho.hash_assinado IS 'Hash do espelho no momento do aceite. Se o espelho mudar depois, a assinatura deixa de conferir, que e exatamente o comportamento desejado.';
COMMENT ON COLUMN assinaturas_espelho.metodo IS 'aceite_eletronico com carimbo de tempo e hash e o padrao. icp_brasil e usado quando o cliente exige certificado.';
COMMENT ON COLUMN assinaturas_espelho.carimbo_tempo IS 'Instante do aceite registrado pelo servidor.';

CREATE UNIQUE INDEX uq_assinaturas_espelho ON assinaturas_espelho (
    tenant_id, espelho_id, signatario_tipo,
    COALESCE(signatario_colaborador_id, '00000000-0000-0000-0000-000000000000'::uuid)
) WHERE status = 'assinado';
CREATE INDEX ix_assinaturas_espelho_espelho ON assinaturas_espelho (tenant_id, espelho_id);

CREATE TRIGGER trg_assinaturas_espelho_bloqueia_update
    BEFORE UPDATE ON assinaturas_espelho FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_assinaturas_espelho_bloqueia_delete
    BEFORE DELETE ON assinaturas_espelho FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();

ALTER TABLE apuracoes_dia
    ADD CONSTRAINT fk_apuracoes_dia_fechamento
    FOREIGN KEY (fechamento_id) REFERENCES fechamentos (id) ON DELETE SET NULL;

ALTER TABLE tratamentos
    ADD CONSTRAINT fk_tratamentos_solicitacao
    FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes (id) ON DELETE SET NULL;

ALTER TABLE afastamentos
    ADD CONSTRAINT fk_afastamentos_solicitacao
    FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes (id) ON DELETE SET NULL;


-- =============================================================================
-- 13. ARQUIVOS FISCAIS (AFD, AEJ E ASSINATURA)
-- =============================================================================

CREATE TABLE afd_arquivos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id      UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    rep_p_id        UUID NOT NULL REFERENCES rep_ps (id) ON DELETE RESTRICT,
    periodo_inicio  DATE NOT NULL,
    periodo_fim     DATE NOT NULL,
    nsr_inicial     BIGINT NOT NULL CHECK (nsr_inicial >= 1),
    nsr_final       BIGINT NOT NULL CHECK (nsr_final >= 1),
    total_registros BIGINT NOT NULL DEFAULT 0 CHECK (total_registros >= 0),
    nome_arquivo    TEXT NOT NULL,
    conteudo_ref    TEXT,
    tamanho_bytes   BIGINT CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    encoding        TEXT NOT NULL DEFAULT 'ISO-8859-1',
    hash_sha256     dom_sha256,
    versao_leiaute  TEXT NOT NULL DEFAULT '671/2021',
    fracionado      BOOLEAN NOT NULL DEFAULT FALSE,
    fracao_numero   INTEGER CHECK (fracao_numero IS NULL OR fracao_numero >= 1),
    fracao_total    INTEGER CHECK (fracao_total IS NULL OR fracao_total >= 1),
    status          TEXT NOT NULL DEFAULT 'gerando'
                    CHECK (status IN ('gerando','gerado','assinado','falhou','cancelado')),
    solicitado_por  UUID,
    gerado_em       TIMESTAMPTZ,
    erro            TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID,
    CONSTRAINT ck_afd_arquivos_periodo CHECK (periodo_fim >= periodo_inicio),
    CONSTRAINT ck_afd_arquivos_nsr CHECK (nsr_final >= nsr_inicial),
    CONSTRAINT ck_afd_arquivos_fracao CHECK (
        (fracionado = FALSE AND fracao_numero IS NULL AND fracao_total IS NULL) OR
        (fracionado = TRUE  AND fracao_numero IS NOT NULL AND fracao_total IS NOT NULL
         AND fracao_numero <= fracao_total)
    )
);

COMMENT ON TABLE afd_arquivos IS
  'Arquivo Fonte de Dados gerado EXCLUSIVAMENTE pelo REP-P. Texto ASCII ISO 8859-1, campos separados por barra vertical, linhas terminadas em CR+LF, CRC-16 por registro e SHA-256 do arquivo. Nenhum tratamento entra aqui.';
COMMENT ON COLUMN afd_arquivos.nsr_inicial IS 'Primeiro NSR contido no arquivo. Junto com nsr_final documenta a faixa e permite provar ausencia de lacuna.';
COMMENT ON COLUMN afd_arquivos.encoding IS 'ISO-8859-1 por exigencia do leiaute. Nao alterar sem RFC.';
COMMENT ON COLUMN afd_arquivos.versao_leiaute IS 'Versao do leiaute aplicada. A conferencia campo a campo contra os anexos da Portaria e tarefa bloqueante da Fase 12.';
COMMENT ON COLUMN afd_arquivos.fracionado IS 'O REP-P pode fracionar o AFD por periodo. As fracoes juntas cobrem a faixa completa sem sobreposicao.';
COMMENT ON COLUMN afd_arquivos.hash_sha256 IS 'SHA-256 do arquivo gerado, exigido pelo leiaute e usado na verificacao de integridade.';

CREATE INDEX ix_afd_arquivos_empresa ON afd_arquivos (tenant_id, empresa_id, periodo_inicio DESC);
CREATE INDEX ix_afd_arquivos_rep ON afd_arquivos (tenant_id, rep_p_id, nsr_inicial);


CREATE TABLE aej_arquivos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id              UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    periodo_id              UUID REFERENCES periodos (id) ON DELETE RESTRICT,
    periodo_inicio          DATE NOT NULL,
    periodo_fim             DATE NOT NULL,
    nome_arquivo            TEXT NOT NULL,
    conteudo_ref            TEXT,
    tamanho_bytes           BIGINT CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    encoding                TEXT NOT NULL DEFAULT 'ISO-8859-1',
    hash_sha256             dom_sha256,
    versao_leiaute          TEXT NOT NULL DEFAULT '671/2021',
    total_vinculos          INTEGER NOT NULL DEFAULT 0,
    total_marcacoes         BIGINT NOT NULL DEFAULT 0,
    total_ausencias         INTEGER NOT NULL DEFAULT 0,
    total_lancamentos_banco INTEGER NOT NULL DEFAULT 0,
    ptrp_identificacao      TEXT NOT NULL,
    ptrp_cnpj               dom_cnpj,
    ptrp_versao             TEXT,
    status                  TEXT NOT NULL DEFAULT 'gerando'
                            CHECK (status IN ('gerando','gerado','assinado','falhou','cancelado')),
    solicitado_por          UUID,
    gerado_em               TIMESTAMPTZ,
    erro                    TEXT,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por              UUID,
    atualizado_em           TIMESTAMPTZ,
    atualizado_por          UUID,
    CONSTRAINT ck_aej_arquivos_periodo CHECK (periodo_fim >= periodo_inicio)
);

COMMENT ON TABLE aej_arquivos IS
  'Arquivo Eletronico de Jornada, gerado pelo Programa de Tratamento de Registro de Ponto. Substitui AFDT e ACJEF. Contem cabecalho, REPs utilizados, vinculos, horario contratual, marcacoes, matricula eSocial, ausencias, banco de horas, identificacao do PTRP e trailer.';
COMMENT ON COLUMN aej_arquivos.ptrp_identificacao IS 'Identificacao do Programa de Tratamento de Registro de Ponto que gerou o arquivo. Exigida pelo leiaute.';
COMMENT ON COLUMN aej_arquivos.total_lancamentos_banco IS 'Quantidade de lancamentos de banco de horas exportados. Precisa fechar com o extrato do periodo.';

CREATE INDEX ix_aej_arquivos_empresa ON aej_arquivos (tenant_id, empresa_id, periodo_inicio DESC);


CREATE TABLE arquivo_assinaturas (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    tipo_arquivo              TEXT NOT NULL
                              CHECK (tipo_arquivo IN ('afd','aej','espelho','comprovante','relatorio')),
    arquivo_id                UUID NOT NULL,
    padrao                    TEXT NOT NULL DEFAULT 'CAdES'
                              CHECK (padrao IN ('CAdES','XAdES','PAdES')),
    formato                   TEXT NOT NULL DEFAULT 'detached'
                              CHECK (formato IN ('detached','attached')),
    assinatura_ref            TEXT NOT NULL,
    certificado_titular       TEXT,
    certificado_serial        TEXT,
    certificado_emissor       TEXT,
    certificado_validade_inicio TIMESTAMPTZ,
    certificado_validade_fim  TIMESTAMPTZ,
    politica_assinatura       TEXT,
    carimbo_tempo             TIMESTAMPTZ,
    hash_arquivo              dom_sha256 NOT NULL,
    algoritmo_hash            TEXT NOT NULL DEFAULT 'SHA-256',
    status                    TEXT NOT NULL DEFAULT 'assinado'
                              CHECK (status IN ('pendente','assinado','invalido','revogado')),
    validado_em               TIMESTAMPTZ,
    validacao_resultado       JSONB,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por                UUID
);

COMMENT ON TABLE arquivo_assinaturas IS
  'Assinatura digital de arquivos fiscais no padrao CAdES, em .p7s destacado, com certificado ICP-Brasil. Referencia polimorfica por tipo_arquivo mais arquivo_id, sem chave estrangeira; divergencia documentada no glossario. Somente-acrescimo: DELETE e barrado por gatilho e reassinar gera linha nova; o UPDATE existe apenas para registrar o resultado da validacao posterior.';
COMMENT ON COLUMN arquivo_assinaturas.formato IS 'detached significa .p7s separado do arquivo original, que e o formato exigido para AFD.';
COMMENT ON COLUMN arquivo_assinaturas.hash_arquivo IS 'Hash do arquivo no momento da assinatura. Divergencia posterior indica adulteracao.';
COMMENT ON COLUMN arquivo_assinaturas.validacao_resultado IS 'Saida da validacao contra verificador ICP-Brasil independente, guardada como evidencia de conformidade.';

CREATE INDEX ix_arquivo_assinaturas_alvo ON arquivo_assinaturas (tenant_id, tipo_arquivo, arquivo_id);

CREATE TRIGGER trg_arquivo_assinaturas_bloqueia_delete
    BEFORE DELETE ON arquivo_assinaturas FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


-- =============================================================================
-- 14. INTEGRACAO E API PUBLICA
-- =============================================================================

CREATE TABLE api_clients (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    nome                  TEXT NOT NULL,
    descricao             TEXT,
    client_id             TEXT NOT NULL,
    client_secret_hash    TEXT,
    tipo                  TEXT NOT NULL DEFAULT 'confidencial'
                          CHECK (tipo IN ('confidencial','publico','maquina')),
    ambiente              TEXT NOT NULL DEFAULT 'sandbox'
                          CHECK (ambiente IN ('sandbox','producao')),
    escopos               TEXT[] NOT NULL DEFAULT '{}',
    redirect_uris         TEXT[],
    ips_permitidos        CIDR[],
    rate_limit_por_minuto INTEGER NOT NULL DEFAULT 600 CHECK (rate_limit_por_minuto > 0),
    contato_email         dom_email,
    status                TEXT NOT NULL DEFAULT 'ativo'
                          CHECK (status IN ('ativo','suspenso','revogado')),
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID,
    CONSTRAINT uq_api_clients_client_id UNIQUE (client_id)
);

COMMENT ON TABLE api_clients IS
  'Aplicacao integradora autorizada a consumir a API publica. Cada cliente vive em um ambiente (sandbox ou producao) e carrega seus proprios escopos e limite de taxa.';
COMMENT ON COLUMN api_clients.client_id IS 'Identificador publico do cliente OAuth. Unico em toda a instalacao, nao apenas no tenant.';
COMMENT ON COLUMN api_clients.client_secret_hash IS 'Hash do segredo. O valor em claro e mostrado uma unica vez, na criacao.';
COMMENT ON COLUMN api_clients.escopos IS 'Escopos OAuth concedidos, por exemplo marcacoes:ler e colaboradores:escrever.';
COMMENT ON COLUMN api_clients.ips_permitidos IS 'Restricao opcional de origem por faixa CIDR.';

CREATE UNIQUE INDEX uq_api_clients_nome ON api_clients (tenant_id, nome) WHERE excluido_em IS NULL;
CREATE INDEX ix_api_clients_tenant ON api_clients (tenant_id, status);


CREATE TABLE api_keys (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    api_client_id    UUID NOT NULL REFERENCES api_clients (id) ON DELETE CASCADE,
    prefixo          TEXT NOT NULL,
    hash             dom_sha256 NOT NULL,
    rotulo           TEXT,
    ambiente         TEXT NOT NULL DEFAULT 'sandbox'
                     CHECK (ambiente IN ('sandbox','producao')),
    escopos          TEXT[] NOT NULL DEFAULT '{}',
    expira_em        TIMESTAMPTZ,
    ultimo_uso_em    TIMESTAMPTZ,
    ultimo_ip        INET,
    revogada_em      TIMESTAMPTZ,
    motivo_revogacao TEXT,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por       UUID,
    atualizado_em    TIMESTAMPTZ,
    atualizado_por   UUID,
    CONSTRAINT uq_api_keys_prefixo UNIQUE (tenant_id, prefixo)
);

COMMENT ON TABLE api_keys IS
  'Chave de API para integracoes simples que nao justificam o fluxo OAuth completo. Guardada por hash; o prefixo serve para o usuario identificar a chave sem expo-la.';
COMMENT ON COLUMN api_keys.prefixo IS 'Primeiros caracteres da chave, exibidos na interface, por exemplo pk_prd_a1b2.';

CREATE INDEX ix_api_keys_client ON api_keys (tenant_id, api_client_id) WHERE revogada_em IS NULL;


CREATE TABLE oauth_tokens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    api_client_id UUID NOT NULL REFERENCES api_clients (id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('access','refresh')),
    token_hash    dom_sha256 NOT NULL,
    escopos       TEXT[] NOT NULL DEFAULT '{}',
    emitido_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em     TIMESTAMPTZ NOT NULL,
    revogado_em   TIMESTAMPTZ,
    ip            INET,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por    UUID,
    atualizado_em TIMESTAMPTZ,
    atualizado_por UUID,
    CONSTRAINT uq_oauth_tokens_hash UNIQUE (tenant_id, token_hash)
);

COMMENT ON TABLE oauth_tokens IS
  'Tokens emitidos no fluxo client credentials. Guardados por hash e revogaveis individualmente ou por cliente.';

CREATE INDEX ix_oauth_tokens_client ON oauth_tokens (tenant_id, api_client_id, expira_em);


CREATE TABLE webhooks (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    api_client_id         UUID REFERENCES api_clients (id) ON DELETE CASCADE,
    nome                  TEXT NOT NULL,
    url                   TEXT NOT NULL CHECK (url ~ '^https://'),
    eventos               TEXT[] NOT NULL,
    segredo_hmac_cifrado  BYTEA NOT NULL,
    chave_id              TEXT,
    cabecalhos_extras     JSONB,
    max_tentativas        INTEGER NOT NULL DEFAULT 8 CHECK (max_tentativas > 0),
    timeout_segundos      INTEGER NOT NULL DEFAULT 10 CHECK (timeout_segundos > 0),
    status                TEXT NOT NULL DEFAULT 'ativo'
                          CHECK (status IN ('ativo','suspenso','desabilitado_por_falha')),
    falhas_consecutivas   INTEGER NOT NULL DEFAULT 0 CHECK (falhas_consecutivas >= 0),
    ultima_entrega_em     TIMESTAMPTZ,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID
);

COMMENT ON TABLE webhooks IS
  'Assinatura de eventos por HTTP. Somente HTTPS, garantido por CHECK. O corpo e assinado em HMAC com segredo proprio de cada webhook.';
COMMENT ON COLUMN webhooks.eventos IS 'Lista de codigos do catalogo events.yaml, por exemplo marcacao.criada e periodo.fechado.';
COMMENT ON COLUMN webhooks.segredo_hmac_cifrado IS 'Segredo de assinatura, cifrado com chave externa referenciada em chave_id.';
COMMENT ON COLUMN webhooks.status IS 'desabilitado_por_falha e aplicado automaticamente apos falhas consecutivas, para nao inundar um endpoint morto.';

CREATE UNIQUE INDEX uq_webhooks_nome ON webhooks (tenant_id, nome) WHERE excluido_em IS NULL;
CREATE INDEX ix_webhooks_eventos ON webhooks USING gin (eventos);


CREATE TABLE webhook_entregas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    webhook_id          UUID NOT NULL REFERENCES webhooks (id) ON DELETE CASCADE,
    evento              TEXT NOT NULL,
    evento_id           UUID NOT NULL,
    payload             JSONB NOT NULL,
    assinatura          TEXT,
    tentativa           INTEGER NOT NULL DEFAULT 1 CHECK (tentativa >= 1),
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente','enviando','sucesso','falha','dlq','cancelada')),
    http_status         INTEGER,
    resposta            TEXT,
    duracao_ms          INTEGER CHECK (duracao_ms IS NULL OR duracao_ms >= 0),
    erro                TEXT,
    proxima_tentativa_em TIMESTAMPTZ,
    enviado_em          TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID
);

COMMENT ON TABLE webhook_entregas IS
  'Tentativa de entrega de um evento. Retentativa exponencial ate max_tentativas; esgotado, vai para dlq e pode ser reenviada manualmente pelo painel.';
COMMENT ON COLUMN webhook_entregas.evento_id IS 'Identificador do evento de dominio. Permite ao destinatario deduplicar entregas repetidas.';
COMMENT ON COLUMN webhook_entregas.status IS 'dlq e a dead letter queue: entrega desistida apos esgotar as tentativas.';

CREATE INDEX ix_webhook_entregas_webhook ON webhook_entregas (tenant_id, webhook_id, criado_em DESC);
CREATE INDEX ix_webhook_entregas_pendentes ON webhook_entregas (tenant_id, proxima_tentativa_em) WHERE status IN ('pendente','falha');
CREATE INDEX ix_webhook_entregas_dlq ON webhook_entregas (tenant_id, criado_em DESC) WHERE status = 'dlq';


CREATE TABLE integracoes_folha (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id            UUID NOT NULL REFERENCES empresas (id) ON DELETE RESTRICT,
    parceiro              TEXT NOT NULL
                          CHECK (parceiro IN ('dominio','alterdata','totvs_rm','totvs_protheus','totvs_datasul',
                                              'senior','sankhya','questor','fortes','contmatic','generico_csv')),
    nome                  TEXT NOT NULL,
    configuracao          JSONB NOT NULL DEFAULT '{}'::jsonb,
    mapeamento_rubricas   JSONB,
    formato               TEXT NOT NULL DEFAULT 'csv'
                          CHECK (formato IN ('csv','txt','xml','json','api')),
    ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
    ultima_exportacao_em  TIMESTAMPTZ,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    excluido_em           TIMESTAMPTZ,
    excluido_por          UUID
);

COMMENT ON TABLE integracoes_folha IS
  'Configuracao de exportacao para um sistema de folha. O mapeamento de rubricas traduz nossos codigos de apuracao para os codigos do parceiro.';
COMMENT ON COLUMN integracoes_folha.mapeamento_rubricas IS 'De-para em JSON entre codigos de apuracao_componentes e rubricas do parceiro.';

CREATE UNIQUE INDEX uq_integracoes_folha_nome ON integracoes_folha (tenant_id, empresa_id, nome) WHERE excluido_em IS NULL;


CREATE TABLE importacoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    empresa_id          UUID REFERENCES empresas (id) ON DELETE RESTRICT,
    tipo                TEXT NOT NULL
                        CHECK (tipo IN ('colaboradores','estrutura','escalas','feriados','marcacoes',
                                        'afd_terceiro','banco_horas','biometria','afastamentos')),
    origem              TEXT NOT NULL DEFAULT 'csv'
                        CHECK (origem IN ('csv','xlsx','afd','api','manual')),
    nome_arquivo        TEXT,
    conteudo_ref        TEXT,
    hash_sha256         dom_sha256,
    parametros          JSONB,
    status              TEXT NOT NULL DEFAULT 'recebido'
                        CHECK (status IN ('recebido','validando','processando','concluido',
                                          'concluido_com_erros','falhou','cancelado')),
    total_linhas        INTEGER NOT NULL DEFAULT 0,
    linhas_processadas  INTEGER NOT NULL DEFAULT 0,
    linhas_sucesso      INTEGER NOT NULL DEFAULT 0,
    linhas_erro         INTEGER NOT NULL DEFAULT 0,
    relatorio_ref       TEXT,
    erros               JSONB,
    iniciado_em         TIMESTAMPTZ,
    concluido_em        TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por          UUID,
    atualizado_em       TIMESTAMPTZ,
    atualizado_por      UUID
);

COMMENT ON TABLE importacoes IS
  'Execucao de um importador. Guarda o arquivo de origem, o resultado linha a linha e o relatorio de erros, que e o que torna a carga de 5.000 colaboradores auditavel.';
COMMENT ON COLUMN importacoes.tipo IS 'afd_terceiro importa AFD de outro fabricante para migracao; essas marcacoes usam namespace de NSR separado do nosso REP-P.';
COMMENT ON COLUMN importacoes.erros IS 'Erros estruturados por linha em JSON, para a interface exibir sem baixar o relatorio.';

CREATE INDEX ix_importacoes_tenant ON importacoes (tenant_id, tipo, criado_em DESC);
CREATE INDEX ix_importacoes_status ON importacoes (tenant_id, status) WHERE status IN ('recebido','validando','processando');

ALTER TABLE marcacoes
    ADD CONSTRAINT fk_marcacoes_importacao
    FOREIGN KEY (origem_importacao_id) REFERENCES importacoes (id) ON DELETE RESTRICT;


-- =============================================================================
-- 15. AUDITORIA E LGPD
-- =============================================================================

CREATE TABLE auditoria (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    sequencia       BIGINT NOT NULL CHECK (sequencia >= 1),
    evento          TEXT NOT NULL,
    entidade        TEXT NOT NULL,
    entidade_id     UUID,
    acao            TEXT NOT NULL
                    CHECK (acao IN ('criar','ler','atualizar','excluir','aprovar','reprovar','exportar',
                                    'login','logout','falha_login','fechar','reabrir','assinar','revogar',
                                    'configurar','recalcular')),
    usuario_id      UUID,
    usuario_email   TEXT,
    perfil          TEXT,
    delegacao_id    UUID,
    ip              INET,
    user_agent      TEXT,
    origem          TEXT NOT NULL DEFAULT 'api'
                    CHECK (origem IN ('web','mobile','api','terminal','worker','cli','sistema')),
    requisicao_id   TEXT,
    valor_anterior  JSONB,
    valor_novo      JSONB,
    diferenca       JSONB,
    metadados       JSONB,
    resultado       TEXT NOT NULL DEFAULT 'sucesso'
                    CHECK (resultado IN ('sucesso','falha','negado')),
    mensagem        TEXT,
    ocorrido_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    hash_anterior   dom_sha256,
    hash_registro   dom_sha256 NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    CONSTRAINT uq_auditoria_sequencia UNIQUE (tenant_id, sequencia),
    CONSTRAINT uq_auditoria_hash UNIQUE (tenant_id, hash_registro)
);

COMMENT ON TABLE auditoria IS
  'Trilha de auditoria ENCADEADA. Cada linha carrega o hash da anterior, formando uma cadeia por tenant: remover uma linha silenciosamente quebra a cadeia e e detectavel. Append-only, com gatilho que barra UPDATE e DELETE.';
COMMENT ON COLUMN auditoria.sequencia IS 'Posicao na cadeia, sem lacunas, por tenant. Alocada transacionalmente junto com o hash.';
COMMENT ON COLUMN auditoria.evento IS 'Codigo do evento no catalogo events.yaml.';
COMMENT ON COLUMN auditoria.delegacao_id IS 'Preenchido quando a acao foi exercida por delegacao, o que precisa ficar visivel na trilha.';
COMMENT ON COLUMN auditoria.valor_anterior IS 'Estado antes da mudanca, em JSON. NULL em criacao.';
COMMENT ON COLUMN auditoria.diferenca IS 'Diff calculado entre anterior e novo, para leitura humana rapida.';
COMMENT ON COLUMN auditoria.requisicao_id IS 'Correlaciona a linha com o trace distribuido do OpenTelemetry.';
COMMENT ON COLUMN auditoria.hash_registro IS 'SHA-256 do conteudo canonico da linha concatenado com hash_anterior.';

CREATE INDEX ix_auditoria_entidade ON auditoria (tenant_id, entidade, entidade_id, ocorrido_em DESC);
CREATE INDEX ix_auditoria_usuario ON auditoria (tenant_id, usuario_id, ocorrido_em DESC);
CREATE INDEX ix_auditoria_ocorrido ON auditoria (tenant_id, ocorrido_em DESC);
CREATE INDEX ix_auditoria_acao ON auditoria (tenant_id, acao, ocorrido_em DESC);

CREATE TRIGGER trg_auditoria_bloqueia_update
    BEFORE UPDATE ON auditoria FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_auditoria_bloqueia_delete
    BEFORE DELETE ON auditoria FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_auditoria_bloqueia_truncate
    BEFORE TRUNCATE ON auditoria FOR EACH STATEMENT EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE acessos_dados_sensiveis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id      UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    colaborador_id  UUID REFERENCES colaboradores (id) ON DELETE SET NULL,
    categoria       TEXT NOT NULL
                    CHECK (categoria IN ('biometria','documento','saude','remuneracao','geolocalizacao',
                                         'foto','cpf','dados_pessoais')),
    entidade        TEXT,
    entidade_id     UUID,
    finalidade      TEXT NOT NULL,
    base_legal      TEXT NOT NULL
                    CHECK (base_legal IN ('obrigacao_legal','consentimento','execucao_contrato',
                                          'legitimo_interesse','exercicio_direitos','protecao_vida')),
    acao            TEXT NOT NULL
                    CHECK (acao IN ('leitura','exportacao','impressao','compartilhamento','eliminacao')),
    quantidade_registros INTEGER,
    ip              INET,
    user_agent      TEXT,
    origem          TEXT CHECK (origem IN ('web','mobile','api','terminal','worker','cli','sistema')),
    ocorrido_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID
);

COMMENT ON TABLE acessos_dados_sensiveis IS
  'Registro de TODA leitura de dado pessoal sensivel. Append-only. E a evidencia que a LGPD exige e a base do relatorio de acessos, incluindo o acesso de suporte da SEEG.';
COMMENT ON COLUMN acessos_dados_sensiveis.finalidade IS 'Motivo declarado do acesso, exigido pelo principio da finalidade.';
COMMENT ON COLUMN acessos_dados_sensiveis.base_legal IS 'Hipotese legal que autoriza o tratamento. Ponto usa obrigacao legal; biometria exige consentimento especifico.';
COMMENT ON COLUMN acessos_dados_sensiveis.quantidade_registros IS 'Volume acessado. Exportacao em massa fica evidente no relatorio.';

CREATE INDEX ix_acessos_sensiveis_usuario ON acessos_dados_sensiveis (tenant_id, usuario_id, ocorrido_em DESC);
CREATE INDEX ix_acessos_sensiveis_colaborador ON acessos_dados_sensiveis (tenant_id, colaborador_id, ocorrido_em DESC);
CREATE INDEX ix_acessos_sensiveis_categoria ON acessos_dados_sensiveis (tenant_id, categoria, ocorrido_em DESC);

CREATE TRIGGER trg_acessos_sensiveis_bloqueia_update
    BEFORE UPDATE ON acessos_dados_sensiveis FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();
CREATE TRIGGER trg_acessos_sensiveis_bloqueia_delete
    BEFORE DELETE ON acessos_dados_sensiveis FOR EACH ROW EXECUTE FUNCTION fn_registro_imutavel();


CREATE TABLE consentimentos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id  UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    finalidade      TEXT NOT NULL
                    CHECK (finalidade IN ('biometria_facial','biometria_digital','geolocalizacao',
                                          'foto_registro','uso_imagem','comunicacao')),
    versao_termo    TEXT NOT NULL,
    texto_termo_ref TEXT NOT NULL,
    hash_termo      dom_sha256 NOT NULL,
    status          TEXT NOT NULL DEFAULT 'concedido'
                    CHECK (status IN ('pendente','concedido','revogado','expirado')),
    concedido_em    TIMESTAMPTZ,
    revogado_em     TIMESTAMPTZ,
    expira_em       TIMESTAMPTZ,
    canal           TEXT NOT NULL DEFAULT 'app'
                    CHECK (canal IN ('app','web','terminal','papel','importacao')),
    ip              INET,
    user_agent      TEXT,
    evidencia_ref   TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por      UUID,
    atualizado_em   TIMESTAMPTZ,
    atualizado_por  UUID
);

COMMENT ON TABLE consentimentos IS
  'Consentimento LGPD versionado. O registro do ponto se apoia em obrigacao legal, mas a BIOMETRIA exige consentimento especifico: sem linha concedida vigente aqui, o template nao pode ser usado.';
COMMENT ON COLUMN consentimentos.versao_termo IS 'Versao do texto aceito. Mudar o termo exige novo consentimento, nao reaproveita o antigo.';
COMMENT ON COLUMN consentimentos.hash_termo IS 'Hash do texto exato que o titular leu. Prova o que foi consentido.';
COMMENT ON COLUMN consentimentos.evidencia_ref IS 'Evidencia do aceite, por exemplo captura de tela assinada ou PDF do termo em papel digitalizado.';

CREATE UNIQUE INDEX uq_consentimentos_vigente ON consentimentos (tenant_id, colaborador_id, finalidade) WHERE status = 'concedido';
CREATE INDEX ix_consentimentos_colaborador ON consentimentos (tenant_id, colaborador_id);

ALTER TABLE biometrias
    ADD CONSTRAINT fk_biometrias_consentimento
    FOREIGN KEY (consentimento_id) REFERENCES consentimentos (id) ON DELETE RESTRICT;


CREATE TABLE politicas_retencao (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    entidade              TEXT NOT NULL
                          CHECK (entidade IN ('marcacao','foto_registro','biometria','documento','auditoria',
                                              'notificacao','espelho','afd','aej','log_acesso','fila_offline',
                                              'relatorio_execucao','sessao')),
    prazo_dias            INTEGER NOT NULL CHECK (prazo_dias > 0),
    base_legal            TEXT NOT NULL,
    acao                  TEXT NOT NULL
                          CHECK (acao IN ('anonimizar','eliminar','arquivar')),
    ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
    ultima_execucao_em    TIMESTAMPTZ,
    proxima_execucao_em   TIMESTAMPTZ,
    registros_ultima_execucao BIGINT,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por            UUID,
    atualizado_em         TIMESTAMPTZ,
    atualizado_por        UUID,
    CONSTRAINT uq_politicas_retencao UNIQUE (tenant_id, entidade)
);

COMMENT ON TABLE politicas_retencao IS
  'Prazo de guarda por tipo de dado e o que fazer no vencimento. Marcacao retem 5 anos por obrigacao legal; foto de captura retem prazo curto por minimizacao.';
COMMENT ON COLUMN politicas_retencao.acao IS 'anonimizar preserva estatistica sem identificar. eliminar apaga. arquivar move para armazenamento frio.';
COMMENT ON COLUMN politicas_retencao.base_legal IS 'Fundamento do prazo, por exemplo art. 74 da CLT ou politica interna de minimizacao.';


CREATE TABLE solicitacoes_titular (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    colaborador_id   UUID REFERENCES colaboradores (id) ON DELETE SET NULL,
    usuario_id       UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    protocolo        TEXT NOT NULL,
    requerente_nome  TEXT NOT NULL,
    requerente_cpf   dom_cpf,
    requerente_email dom_email,
    tipo             TEXT NOT NULL
                     CHECK (tipo IN ('acesso','correcao','portabilidade','eliminacao','anonimizacao',
                                     'revogacao_consentimento','informacao_compartilhamento','oposicao')),
    descricao        TEXT,
    status           TEXT NOT NULL DEFAULT 'recebida'
                     CHECK (status IN ('recebida','em_analise','atendida','parcialmente_atendida',
                                       'recusada','cancelada')),
    prazo_em         DATE,
    resposta         TEXT,
    resposta_ref     TEXT,
    respondido_em    TIMESTAMPTZ,
    respondido_por   UUID,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por       UUID,
    atualizado_em    TIMESTAMPTZ,
    atualizado_por   UUID,
    CONSTRAINT uq_solicitacoes_titular_protocolo UNIQUE (tenant_id, protocolo)
);

COMMENT ON TABLE solicitacoes_titular IS
  'Pedido de titular de dados previsto na LGPD. Guarda protocolo, prazo de resposta e o arquivo entregue, que e a evidencia de atendimento.';
COMMENT ON COLUMN solicitacoes_titular.tipo IS 'eliminacao nao apaga marcacao: o dado de ponto tem guarda obrigatoria e a recusa parcial precisa ser fundamentada na resposta.';
COMMENT ON COLUMN solicitacoes_titular.resposta_ref IS 'Chave do pacote de dados entregue ao titular, por exemplo o export de portabilidade.';

CREATE INDEX ix_solicitacoes_titular_status ON solicitacoes_titular (tenant_id, status, prazo_em);


-- =============================================================================
-- 16. RELATORIOS
-- =============================================================================

CREATE TABLE relatorio_definicoes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    codigo               TEXT NOT NULL,
    nome                 TEXT NOT NULL,
    descricao            TEXT,
    categoria            TEXT NOT NULL
                         CHECK (categoria IN ('operacional','gerencial','fiscal','financeiro','lgpd')),
    sistema              BOOLEAN NOT NULL DEFAULT FALSE,
    dataset              TEXT NOT NULL,
    colunas_disponiveis  JSONB NOT NULL DEFAULT '[]'::jsonb,
    filtros_disponiveis  JSONB NOT NULL DEFAULT '[]'::jsonb,
    agrupamentos         JSONB NOT NULL DEFAULT '[]'::jsonb,
    formatos             TEXT[] NOT NULL DEFAULT '{csv,xlsx,pdf}',
    permissao_codigo     TEXT,
    assincrono           BOOLEAN NOT NULL DEFAULT FALSE,
    ativo                BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por           UUID,
    atualizado_em        TIMESTAMPTZ,
    atualizado_por       UUID,
    excluido_em          TIMESTAMPTZ,
    excluido_por         UUID
);

COMMENT ON TABLE relatorio_definicoes IS
  'Catalogo dos relatorios disponiveis. Os 24 relatorios do produto sao semeados por tenant com sistema = true; o cliente pode criar variantes proprias.';
COMMENT ON COLUMN relatorio_definicoes.dataset IS 'Identificador do conjunto de dados no backend. NUNCA SQL cru vindo do usuario: e o que impede injecao por configuracao.';
COMMENT ON COLUMN relatorio_definicoes.colunas_disponiveis IS 'Catalogo de colunas em JSON. O espelho de jornada expoe mais de 30 colunas configuraveis.';
COMMENT ON COLUMN relatorio_definicoes.assincrono IS 'Verdadeiro para relatorios pesados, que sao executados por worker com progresso.';

CREATE UNIQUE INDEX uq_relatorio_definicoes_codigo ON relatorio_definicoes (tenant_id, codigo) WHERE excluido_em IS NULL;


CREATE TABLE relatorio_agendamentos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    relatorio_definicao_id UUID NOT NULL REFERENCES relatorio_definicoes (id) ON DELETE CASCADE,
    usuario_id             UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    nome                   TEXT NOT NULL,
    parametros             JSONB NOT NULL DEFAULT '{}'::jsonb,
    formato                TEXT NOT NULL DEFAULT 'pdf'
                           CHECK (formato IN ('csv','xlsx','pdf','json')),
    cron                   TEXT NOT NULL,
    fuso_horario           dom_fuso NOT NULL DEFAULT 'America/Sao_Paulo',
    canal                  TEXT NOT NULL DEFAULT 'email'
                           CHECK (canal IN ('email','webhook','minio')),
    destinatarios          TEXT[] NOT NULL DEFAULT '{}',
    ativo                  BOOLEAN NOT NULL DEFAULT TRUE,
    ultima_execucao_em     TIMESTAMPTZ,
    proxima_execucao_em    TIMESTAMPTZ,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID,
    excluido_em            TIMESTAMPTZ,
    excluido_por           UUID
);

COMMENT ON TABLE relatorio_agendamentos IS
  'Envio recorrente de relatorio. A expressao cron e interpretada no fuso indicado, nao no fuso do servidor.';
COMMENT ON COLUMN relatorio_agendamentos.destinatarios IS 'Enderecos de e-mail ou URLs de webhook conforme o canal.';

CREATE UNIQUE INDEX uq_relatorio_agendamentos_nome ON relatorio_agendamentos (tenant_id, nome) WHERE excluido_em IS NULL;
CREATE INDEX ix_relatorio_agendamentos_proxima ON relatorio_agendamentos (tenant_id, proxima_execucao_em) WHERE ativo;


CREATE TABLE relatorio_execucoes (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    relatorio_definicao_id UUID NOT NULL REFERENCES relatorio_definicoes (id) ON DELETE RESTRICT,
    agendamento_id         UUID REFERENCES relatorio_agendamentos (id) ON DELETE SET NULL,
    usuario_id             UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    parametros             JSONB NOT NULL DEFAULT '{}'::jsonb,
    formato                TEXT NOT NULL DEFAULT 'csv'
                           CHECK (formato IN ('csv','xlsx','pdf','json')),
    status                 TEXT NOT NULL DEFAULT 'enfileirado'
                           CHECK (status IN ('enfileirado','processando','concluido','falhou','cancelado','expirado')),
    progresso              SMALLINT NOT NULL DEFAULT 0 CHECK (progresso BETWEEN 0 AND 100),
    total_linhas           BIGINT,
    conteudo_ref           TEXT,
    tamanho_bytes          BIGINT CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    hash_sha256            dom_sha256,
    iniciado_em            TIMESTAMPTZ,
    concluido_em           TIMESTAMPTZ,
    duracao_ms             INTEGER CHECK (duracao_ms IS NULL OR duracao_ms >= 0),
    expira_em              TIMESTAMPTZ,
    erro                   TEXT,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID
);

COMMENT ON TABLE relatorio_execucoes IS
  'Execucao de um relatorio, sincrona ou assincrona. Guarda parametros, progresso e o artefato gerado, com expiracao para nao acumular arquivo indefinidamente.';
COMMENT ON COLUMN relatorio_execucoes.progresso IS 'Percentual concluido, exibido na interface durante execucoes longas.';
COMMENT ON COLUMN relatorio_execucoes.expira_em IS 'Momento em que o artefato e removido do MinIO pela politica de retencao.';

CREATE INDEX ix_relatorio_execucoes_usuario ON relatorio_execucoes (tenant_id, usuario_id, criado_em DESC);
CREATE INDEX ix_relatorio_execucoes_fila ON relatorio_execucoes (tenant_id, status, criado_em) WHERE status IN ('enfileirado','processando');


CREATE TABLE preferencias_colunas (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id             UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    relatorio_definicao_id UUID REFERENCES relatorio_definicoes (id) ON DELETE CASCADE,
    tela                   TEXT,
    nome                   TEXT NOT NULL DEFAULT 'padrao',
    colunas                JSONB NOT NULL,
    ordenacao              JSONB,
    filtros                JSONB,
    larguras               JSONB,
    padrao                 BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID,
    CONSTRAINT ck_preferencias_colunas_alvo CHECK (relatorio_definicao_id IS NOT NULL OR tela IS NOT NULL)
);

COMMENT ON TABLE preferencias_colunas IS
  'Layout de colunas salvo por usuario, tanto para relatorios quanto para grades da interface. E o que faz a configuracao do espelho de jornada persistir entre sessoes.';
COMMENT ON COLUMN preferencias_colunas.tela IS 'Identificador de uma grade da interface quando a preferencia nao pertence a um relatorio, por exemplo grade_apuracao.';
COMMENT ON COLUMN preferencias_colunas.padrao IS 'Layout aplicado automaticamente ao abrir a tela ou o relatorio.';

CREATE UNIQUE INDEX uq_preferencias_colunas ON preferencias_colunas (
    tenant_id, usuario_id,
    COALESCE(relatorio_definicao_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(tela, ''),
    nome
);


-- =============================================================================
-- 17. IMUTABILIDADE PARCIAL DO EXTRATO DE BANCO DE HORAS
-- =============================================================================

-- O extrato e imutavel em tudo, com uma unica excecao operacional: a rotina de
-- consumo FIFO/LIFO precisa marcar quanto de cada credito ja foi consumido.
-- Qualquer outra alteracao e abortada.
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
$$;

COMMENT ON FUNCTION fn_bh_lancamento_imutavel() IS
  'Permite exclusivamente a atualizacao de consumido_minutos em bh_lancamentos. Qualquer outra alteracao e abortada; correcao se faz por estorno.';

CREATE TRIGGER trg_bh_lancamentos_imutavel
    BEFORE UPDATE ON bh_lancamentos
    FOR EACH ROW EXECUTE FUNCTION fn_bh_lancamento_imutavel();

CREATE TRIGGER trg_bh_lancamentos_bloqueia_truncate
    BEFORE TRUNCATE ON bh_lancamentos
    FOR EACH STATEMENT EXECUTE FUNCTION fn_registro_imutavel();


-- =============================================================================
-- 18. GATILHOS DE atualizado_em
--
-- Aplicados automaticamente a toda tabela que possui a coluna atualizado_em.
-- Tabelas append-only nao possuem a coluna e por isso ficam de fora.
-- =============================================================================

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
END $$;


-- =============================================================================
-- 19. ROW LEVEL SECURITY
--
-- Regra: toda tabela de dominio que possui tenant_id recebe, sem excecao,
--     ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
--     ALTER TABLE <t> FORCE  ROW LEVEL SECURITY;
--     CREATE POLICY pol_isolamento_tenant ON <t>
--         USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
--         WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
--
-- A aplicacao das tres instrucoes e feita pelo laco abaixo, e nao a mao, porque
-- o laco garante cobertura de 100 por cento e o bloco de verificacao da secao
-- 21 falha a migracao se alguma tabela escapar. FORCE faz a politica valer ate
-- para o dono da tabela. O acesso cross-tenant do suporte da SEEG e feito por
-- role com BYPASSRLS, nunca por brecha na policy.
--
-- Excecoes conscientes (documentadas no glossario):
--   tenants     - a coluna de isolamento e "id"; RLS declarada explicitamente
--                 na secao 2.
--   permissoes  - catalogo global do produto, identico em todos os tenants,
--                 somente leitura para a aplicacao.
-- =============================================================================

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
END $$;


-- =============================================================================
-- 20. ROLES E PRIVILEGIOS
--
-- Defesa em profundidade: alem do gatilho de imutabilidade, a role da aplicacao
-- simplesmente NAO recebe UPDATE nem DELETE nas tabelas append-only.
-- Os blocos toleram falta de privilegio para que schema.sql permaneca
-- executavel por um usuario sem CREATEROLE.
-- =============================================================================

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
END $$;

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
        -- atualizar consumido_minutos. A revisao do gestor vive em
        -- marcacoes_meta, nunca em marcacoes.
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
END $$;

COMMENT ON TABLE biometria_templates IS
  'Vetor biometrico CIFRADO. Dado pessoal sensivel (LGPD art. 5, II). Versionado por modelo para permitir trocar o motor facial sem perder rastreabilidade nem forcar recadastro geral. A role ponto_suporte (super admin da SEEG) NAO tem SELECT nesta tabela.';


-- =============================================================================
-- 21. VERIFICACAO DO CONTRATO
--
-- Executada no fim da migracao. Se qualquer invariante do modelo estiver
-- quebrada, a migracao FALHA aqui em vez de subir um banco silenciosamente
-- inseguro.
-- =============================================================================

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

    RAISE NOTICE 'schema.sql aplicado. Tabelas: % (sendo % com tenant_id sob RLS).',
                 v_total_tabelas, v_total_dominio;
END $$;

-- =============================================================================
-- FIM DO CONTRATO DE DADOS
-- Alteracoes exigem RFC conforme FASES-E-AGENTES.md, secao 1.3.
-- =============================================================================

