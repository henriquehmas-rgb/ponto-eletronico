"""Models SQLAlchemy 2 do contrato de dados do Ponto Eletronico.

Este pacote e a traducao fiel de `packages/contracts/schema.sql`, que continua
sendo a FONTE DA VERDADE. Uma tabela do schema, um model aqui; nenhuma tabela
extra, nenhuma faltando.

Instalado como `ponto-contracts`, o pacote e importavel como `ponto_contracts`:

    from ponto_contracts import Base, Marcacao, Vinculo

`Base.metadata` e o `target_metadata` do Alembic (`apps/api/migrations/env.py`)
e cobre as 92 tabelas do contrato. As 24 particoes mensais de `marcacoes`, a
particao `marcacoes_default`, as funcoes PL/pgSQL, os gatilhos de imutabilidade,
as policies de RLS e as roles nao sao expressaveis em model declarativo e vivem
na migration inicial `0001_inicial`.

Organizacao por dominio, na mesma ordem de `schema.sql`:

| Modulo         | Grupo                          | Tabelas |
|----------------|--------------------------------|---------|
| `tenancy`      | 1 - Tenancy                    | 2  |
| `organizacao`  | 2 - Organizacao                | 6  |
| `identidade`   | 3 - Identidade e RBAC          | 10 |
| `pessoas`      | 4 - Pessoas                    | 7  |
| `biometria`    | 5 - Biometria e dispositivos   | 6  |
| `jornada`      | 6 - Jornada e calendario       | 13 |
| `marcacao`     | 7 - Marcacao (nucleo legal)    | 9  |
| `apuracao`     | 8 - Tratamento e apuracao      | 5  |
| `banco_horas`  | 9 - Banco de horas             | 5  |
| `workflow`     | 10 - Workflow                  | 6  |
| `fechamento`   | 11 - Fechamento e espelho      | 4  |
| `fiscal`       | 12 - Arquivos fiscais          | 3  |
| `integracao`   | 13 - Integracao e API publica  | 7  |
| `auditoria`    | 14 - Auditoria e LGPD          | 5  |
| `relatorio`    | 15 - Relatorios                | 4  |
|                | **Total**                      | **92** |
"""

from __future__ import annotations

from .apuracao import (
    ApuracaoComponente,
    ApuracaoDia,
    Ocorrencia,
    TipoTratamento,
    Tratamento,
)
from .auditoria import (
    AcessoDadoSensivel,
    Auditoria,
    Consentimento,
    PoliticaRetencao,
    SolicitacaoTitular,
)
from .banco_horas import BhConta, BhLancamento, BhPolitica, BhQuitacao, BhSaldo
from .base import (
    CONVENCAO_NOMES,
    Base,
    agora_no_banco,
    metadata_contrato,
    uuid_v4_no_banco,
)
from .biometria import (
    Biometria,
    BiometriaTemplate,
    Dispositivo,
    DispositivoVinculo,
    Terminal,
    TerminalSaude,
)
from .fechamento import AssinaturaEspelho, Espelho, Fechamento, Periodo
from .fiscal import AejArquivo, AfdArquivo, ArquivoAssinatura
from .identidade import (
    Credencial,
    Delegacao,
    MfaDispositivo,
    Perfil,
    PerfilPermissao,
    Permissao,
    RefreshToken,
    Sessao,
    Usuario,
    UsuarioPerfil,
)
from .integracao import (
    ApiClient,
    ApiKey,
    Importacao,
    IntegracaoFolha,
    OauthToken,
    Webhook,
    WebhookEntrega,
)
from .jornada import (
    Afastamento,
    Escala,
    EscalaAtribuicao,
    EscalaCiclo,
    Feriado,
    FeriadoConjunto,
    Horario,
    Jornada,
    JornadaDia,
    TipoAfastamento,
    Turno,
    UnidadeFeriadoConjunto,
    VinculoJornada,
)
from .marcacao import (
    PARTICIONAMENTO_MARCACOES,
    Comprovante,
    FilaOffline,
    Marcacao,
    MarcacaoIdempotencia,
    MarcacaoMeta,
    NsrEmissao,
    NsrSequencia,
    PoliticaRegistro,
    RepP,
)
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .organizacao import (
    Cargo,
    CentroCusto,
    Departamento,
    Empresa,
    RedePermitida,
    Unidade,
)
from .pessoas import (
    Colaborador,
    ColaboradorGestor,
    Contrato,
    Documento,
    Equipe,
    EquipeMembro,
    Vinculo,
)
from .relatorio import (
    PreferenciaColunas,
    RelatorioAgendamento,
    RelatorioDefinicao,
    RelatorioExecucao,
)
from .tenancy import Tenant, TenantConfiguracao
from .tipos import (
    DDL_DOMINIOS,
    DOM_CBO,
    DOM_CEP,
    DOM_CNPJ,
    DOM_COMPETENCIA,
    DOM_CPF,
    DOM_EMAIL,
    DOM_FUSO,
    DOM_IBGE,
    DOM_PIS,
    DOM_SHA256,
    DOM_UF,
    EXTENSOES,
    NOMES_DOMINIOS,
)
from .workflow import (
    Anexo,
    Aprovacao,
    Notificacao,
    NotificacaoPreferencia,
    Solicitacao,
    TipoSolicitacao,
)

__version__ = "0.1.0"

#: Metadata alvo do Alembic. Atalho estavel para `Base.metadata`.
metadata = Base.metadata

# A lista abaixo segue a ordem dos GRUPOS de schema.sql, nao a ordem alfabetica:
# e ela que deixa visivel, de relance, que os 15 grupos do contrato estao todos
# cobertos. Ordenar alfabeticamente destruiria essa leitura.
__all__ = [  # noqa: RUF022
    # --- infraestrutura ---
    "Base",
    "CONVENCAO_NOMES",
    "metadata",
    "metadata_contrato",
    "agora_no_banco",
    "uuid_v4_no_banco",
    "__version__",
    # --- mixins ---
    "AuditoriaMixin",
    "ChavePrimariaUUIDMixin",
    "CriacaoMixin",
    "SoftDeleteMixin",
    "TenantMixin",
    "TimestampMixin",
    # --- dominios e extensoes ---
    "DDL_DOMINIOS",
    "DOM_CBO",
    "DOM_CEP",
    "DOM_CNPJ",
    "DOM_COMPETENCIA",
    "DOM_CPF",
    "DOM_EMAIL",
    "DOM_FUSO",
    "DOM_IBGE",
    "DOM_PIS",
    "DOM_SHA256",
    "DOM_UF",
    "EXTENSOES",
    "NOMES_DOMINIOS",
    "PARTICIONAMENTO_MARCACOES",
    # --- 1. tenancy ---
    "Tenant",
    "TenantConfiguracao",
    # --- 2. organizacao ---
    "Cargo",
    "CentroCusto",
    "Departamento",
    "Empresa",
    "RedePermitida",
    "Unidade",
    # --- 3. identidade e RBAC ---
    "Credencial",
    "Delegacao",
    "MfaDispositivo",
    "Perfil",
    "PerfilPermissao",
    "Permissao",
    "RefreshToken",
    "Sessao",
    "Usuario",
    "UsuarioPerfil",
    # --- 4. pessoas ---
    "Colaborador",
    "ColaboradorGestor",
    "Contrato",
    "Documento",
    "Equipe",
    "EquipeMembro",
    "Vinculo",
    # --- 5. biometria e dispositivos ---
    "Biometria",
    "BiometriaTemplate",
    "Dispositivo",
    "DispositivoVinculo",
    "Terminal",
    "TerminalSaude",
    # --- 6. jornada e calendario ---
    "Afastamento",
    "Escala",
    "EscalaAtribuicao",
    "EscalaCiclo",
    "Feriado",
    "FeriadoConjunto",
    "Horario",
    "Jornada",
    "JornadaDia",
    "TipoAfastamento",
    "Turno",
    "UnidadeFeriadoConjunto",
    "VinculoJornada",
    # --- 7. marcacao ---
    "Comprovante",
    "FilaOffline",
    "Marcacao",
    "MarcacaoIdempotencia",
    "MarcacaoMeta",
    "NsrEmissao",
    "NsrSequencia",
    "PoliticaRegistro",
    "RepP",
    # --- 8. tratamento e apuracao ---
    "ApuracaoComponente",
    "ApuracaoDia",
    "Ocorrencia",
    "TipoTratamento",
    "Tratamento",
    # --- 9. banco de horas ---
    "BhConta",
    "BhLancamento",
    "BhPolitica",
    "BhQuitacao",
    "BhSaldo",
    # --- 10. workflow ---
    "Anexo",
    "Aprovacao",
    "Notificacao",
    "NotificacaoPreferencia",
    "Solicitacao",
    "TipoSolicitacao",
    # --- 11. fechamento ---
    "AssinaturaEspelho",
    "Espelho",
    "Fechamento",
    "Periodo",
    # --- 12. fiscal ---
    "AejArquivo",
    "AfdArquivo",
    "ArquivoAssinatura",
    # --- 13. integracao ---
    "ApiClient",
    "ApiKey",
    "Importacao",
    "IntegracaoFolha",
    "OauthToken",
    "Webhook",
    "WebhookEntrega",
    # --- 14. auditoria e LGPD ---
    "AcessoDadoSensivel",
    "Auditoria",
    "Consentimento",
    "PoliticaRetencao",
    "SolicitacaoTitular",
    # --- 15. relatorios ---
    "PreferenciaColunas",
    "RelatorioAgendamento",
    "RelatorioDefinicao",
    "RelatorioExecucao",
]
