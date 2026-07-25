#!/usr/bin/env python
"""Semeia os dados MINIMOS de desenvolvimento do Ponto Eletronico.

O que entra:

* 1 tenant (SEEG, cliente numero 1 e cliente de homologacao)
* 1 empresa (matriz) e 1 unidade (sede, com geocerca e fuso)
* o catalogo GLOBAL de permissoes (recurso + acao)
* os 7 perfis de fabrica, com a matriz perfil x permissao de desenvolvimento
* 1 usuario administrador, com senha vinda de variavel de ambiente
* os tipos de tratamento de fabrica
* os tipos de solicitacao de fabrica
* o conjunto de feriados nacionais (fixos e moveis), ligado a unidade

O que NAO entra: colaborador, vinculo, jornada, escala, marcacao, apuracao. Isso
e massa de teste, e massa de teste pertence as fases que implementam cada
modulo - nao ao andaime da Fase 0.

------------------------------------------------------------------------------
SEGURANCA
------------------------------------------------------------------------------
* A senha do administrador vem EXCLUSIVAMENTE de `PONTO_SEED_ADMIN_SENHA`. Nao
  ha valor padrao, nao ha valor no codigo e nao ha valor em arquivo versionado.
  Sem a variavel, o script recusa rodar.
* O script recusa rodar quando `AMBIENTE` indica producao, a menos que receba
  `--forcar` explicitamente.
* O hash usa Argon2id quando `argon2-cffi` estiver instalado; caso contrario cai
  para `hashlib.scrypt` da biblioteca padrao. Os dois valores estao previstos no
  CHECK de `credenciais.algoritmo`. A credencial nasce com
  `trocar_no_proximo_acesso = TRUE`.

------------------------------------------------------------------------------
USO
------------------------------------------------------------------------------
    # a partir de apps/api
    set PONTO_SEED_ADMIN_SENHA=...            # Windows (PowerShell: $env:...)
    export PONTO_SEED_ADMIN_SENHA=...         # Linux/macOS
    python migrations/seed_dev.py

    # opcoes
    python migrations/seed_dev.py --url postgresql+psycopg://ponto:...@localhost/ponto
    python migrations/seed_dev.py --tenant-slug seeg --admin-email rh@exemplo.com.br

O script e IDEMPOTENTE: rodar duas vezes nao duplica nada. Ele localiza o que ja
existe pelas chaves naturais (slug, CNPJ, codigo) e completa o que falta.

Row Level Security: o script define `app.tenant_id` na propria transacao com
`set_config(..., true)` ANTES de qualquer escrita de dado de dominio. E o mesmo
contrato que a aplicacao usa; nada aqui depende de ser superusuario.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import os
import pathlib
import secrets
import sys
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Importacao dos models (mesma estrategia de migrations/env.py)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - caminho feliz
    import ponto_contracts as contrato
except ModuleNotFoundError:  # pragma: no cover - fallback de checkout cru
    _RAIZ = pathlib.Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(_RAIZ / "packages" / "contracts"))
    import models as contrato  # type: ignore[no-redef]


AMBIENTES_PRODUCAO = {"prd", "prod", "producao", "production"}
VARIAVEL_SENHA = "PONTO_SEED_ADMIN_SENHA"


# ===========================================================================
# Catalogo GLOBAL de permissoes
#
# `permissoes` nao tem tenant_id: e o catalogo de recursos e acoes do CODIGO,
# identico em todos os tenants. O conjunto abaixo cobre os recursos previstos
# no OpenAPI da v1. A matriz definitiva de perfil x permissao e responsabilidade
# da Fase 1 (agente A3); aqui existe o suficiente para desenvolver e testar.
# ===========================================================================
LER = "ler"
CRIAR = "criar"
EDITAR = "editar"
EXCLUIR = "excluir"
APROVAR = "aprovar"
EXPORTAR = "exportar"
EXECUTAR = "executar"
ASSINAR = "assinar"
ADMINISTRAR = "administrar"

CRUD = (LER, CRIAR, EDITAR, EXCLUIR)

#: (modulo, recurso, acoes, sensivel, descricao)
CATALOGO_PERMISSOES: tuple[tuple[str, str, tuple[str, ...], bool, str], ...] = (
    # --- identidade e acesso -------------------------------------------------
    ("identidade", "usuarios", CRUD + (ADMINISTRAR,), False, "Usuarios do sistema"),
    ("identidade", "perfis", CRUD, False, "Perfis do RBAC"),
    ("identidade", "permissoes", (LER,), False, "Catalogo de permissoes"),
    ("identidade", "sessoes", (LER, EXCLUIR), False, "Sessoes de acesso"),
    ("identidade", "delegacoes", CRUD, False, "Delegacoes temporarias"),
    # --- organizacao ---------------------------------------------------------
    ("organizacao", "empresas", CRUD, False, "Empresas do tenant"),
    ("organizacao", "unidades", CRUD, False, "Unidades e geocercas"),
    ("organizacao", "departamentos", CRUD, False, "Departamentos"),
    ("organizacao", "centros_custo", CRUD, False, "Centros de custo"),
    ("organizacao", "cargos", CRUD, False, "Cargos"),
    ("organizacao", "redes_permitidas", CRUD, False, "Allowlist CIDR de registro"),
    # --- pessoas -------------------------------------------------------------
    ("pessoas", "colaboradores", CRUD + (EXPORTAR,), True, "Colaboradores"),
    ("pessoas", "contratos", CRUD, True, "Contratos de trabalho"),
    ("pessoas", "vinculos", CRUD, False, "Vinculos empregaticios"),
    ("pessoas", "equipes", CRUD, False, "Equipes"),
    ("pessoas", "documentos", CRUD, True, "Documentos de pessoas e empresas"),
    # --- biometria e dispositivos -------------------------------------------
    ("biometria", "biometrias", CRUD, True, "Credenciais biometricas"),
    ("biometria", "dispositivos", CRUD, False, "Dispositivos e vinculos"),
    ("biometria", "terminais", CRUD + (EXECUTAR,), False, "Coletores e provisionamento"),
    # --- jornada e calendario ------------------------------------------------
    ("jornada", "horarios", CRUD, False, "Gabaritos de horario"),
    ("jornada", "jornadas", CRUD, False, "Regras de jornada"),
    ("jornada", "turnos", CRUD, False, "Turnos"),
    ("jornada", "escalas", CRUD, False, "Escalas ciclicas"),
    ("jornada", "feriados", CRUD, False, "Feriados e conjuntos"),
    ("jornada", "afastamentos", CRUD + (APROVAR,), True, "Afastamentos"),
    # --- marcacao ------------------------------------------------------------
    ("marcacao", "marcacoes", (LER, CRIAR, EXPORTAR), False, "Marcacoes de ponto"),
    ("marcacao", "comprovantes", (LER, EXPORTAR), False, "Comprovantes de registro"),
    ("marcacao", "politicas_registro", (LER, EDITAR), False, "Politica antifraude"),
    # --- tratamento e apuracao ----------------------------------------------
    ("apuracao", "tratamentos", CRUD + (APROVAR,), False, "Tratamentos de jornada"),
    ("apuracao", "apuracoes", (LER, EXECUTAR, EXPORTAR), False, "Apuracao do dia"),
    ("apuracao", "ocorrencias", (LER, EDITAR), False, "Ocorrencias e inconsistencias"),
    # --- banco de horas ------------------------------------------------------
    ("banco_horas", "bh_politicas", CRUD, False, "Politicas de banco de horas"),
    ("banco_horas", "bh_contas", (LER, CRIAR, EDITAR), False, "Contas de banco de horas"),
    ("banco_horas", "bh_lancamentos", (LER, CRIAR, EXPORTAR), False, "Extrato do banco"),
    ("banco_horas", "bh_quitacoes", CRUD + (APROVAR,), False, "Quitacoes de saldo"),
    # --- workflow ------------------------------------------------------------
    ("workflow", "solicitacoes", CRUD + (APROVAR,), False, "Solicitacoes"),
    ("workflow", "aprovacoes", (LER, APROVAR), False, "Etapas de aprovacao"),
    ("workflow", "notificacoes", (LER, CRIAR), False, "Notificacoes"),
    # --- fechamento ----------------------------------------------------------
    ("fechamento", "periodos", CRUD, False, "Periodos de apuracao"),
    ("fechamento", "fechamentos", (LER, CRIAR, EDITAR, EXECUTAR), False, "Fechamento de periodo"),
    ("fechamento", "espelhos", (LER, CRIAR, EXPORTAR, ASSINAR), False, "Espelho de ponto"),
    # --- fiscal --------------------------------------------------------------
    ("fiscal", "afd", (LER, EXECUTAR, EXPORTAR, ASSINAR), False, "Arquivo Fonte de Dados"),
    ("fiscal", "aej", (LER, EXECUTAR, EXPORTAR, ASSINAR), False, "Arquivo Eletronico de Jornada"),
    ("fiscal", "rep_ps", (LER, CRIAR, EDITAR), False, "Instancias de REP-P"),
    # --- integracao ----------------------------------------------------------
    ("integracao", "api_clients", CRUD, False, "Clientes da API publica"),
    ("integracao", "webhooks", CRUD, False, "Webhooks"),
    ("integracao", "integracoes_folha", CRUD + (EXECUTAR,), False, "Exportadores de folha"),
    ("integracao", "importacoes", (LER, CRIAR, EXECUTAR), False, "Importadores"),
    # --- auditoria e LGPD ----------------------------------------------------
    ("auditoria", "auditoria", (LER, EXPORTAR), False, "Trilha de auditoria"),
    ("auditoria", "acessos_sensiveis", (LER, EXPORTAR), True, "Acessos a dado sensivel"),
    ("auditoria", "consentimentos", (LER, CRIAR, EDITAR), True, "Consentimentos LGPD"),
    ("auditoria", "solicitacoes_titular", CRUD, True, "Pedidos de titular de dados"),
    # --- relatorios ----------------------------------------------------------
    ("relatorio", "relatorios", (LER, EXECUTAR, EXPORTAR), False, "Relatorios gerenciais"),
    ("relatorio", "agendamentos", CRUD, False, "Agendamento de relatorios"),
    # --- configuracao --------------------------------------------------------
    ("configuracao", "configuracoes", (LER, EDITAR, ADMINISTRAR), False, "Configuracoes do tenant"),
)


# ===========================================================================
# Perfis de fabrica
# ===========================================================================
#: (codigo, nome, escopo_padrao, somente_leitura, descricao)
PERFIS_FABRICA: tuple[tuple[str, str, str, bool, str], ...] = (
    (
        "super_admin",
        "Super administrador (SEEG)",
        "global",
        False,
        "Suporte da SEEG. Acesso cross-tenant controlado por role de banco; sem acesso a biometria bruta.",
    ),
    (
        "admin_empresa",
        "Administrador da empresa",
        "tenant",
        False,
        "Tudo dentro do tenant.",
    ),
    (
        "rh",
        "Recursos Humanos",
        "empresa",
        False,
        "Cadastros, apuracao, fechamento, relatorios e arquivos fiscais.",
    ),
    (
        "gestor",
        "Gestor",
        "departamento",
        False,
        "Arvore de subordinados: aprovacoes, escalas e relatorios da equipe.",
    ),
    (
        "colaborador",
        "Colaborador",
        "proprio",
        False,
        "Somente o proprio dado: bater ponto, espelho, saldo e solicitacoes.",
    ),
    (
        "auditor",
        "Auditor / Fiscal",
        "tenant",
        True,
        "Somente leitura, incluindo AFD, AEJ e trilha de auditoria.",
    ),
    (
        "integracao",
        "Integracao (maquina)",
        "tenant",
        False,
        "Conta tecnica de integracao, com escopos OAuth granulares.",
    ),
)

#: Modulos que cada perfil enxerga por acao. `"*"` significa todos os modulos.
#: A matriz definitiva sai na Fase 1; esta e a de desenvolvimento.
MATRIZ_PERFIS: dict[str, dict[str, tuple[str, ...]]] = {
    "super_admin": {
        "*": (LER, CRIAR, EDITAR, EXCLUIR, APROVAR, EXPORTAR, EXECUTAR, ASSINAR, ADMINISTRAR)
    },
    "admin_empresa": {
        "*": (LER, CRIAR, EDITAR, EXCLUIR, APROVAR, EXPORTAR, EXECUTAR, ASSINAR, ADMINISTRAR)
    },
    "rh": {
        "organizacao": (LER, CRIAR, EDITAR),
        "pessoas": (LER, CRIAR, EDITAR, EXPORTAR),
        "biometria": (LER, CRIAR, EDITAR),
        "jornada": (LER, CRIAR, EDITAR, APROVAR),
        "marcacao": (LER, EXPORTAR),
        "apuracao": (LER, CRIAR, EDITAR, APROVAR, EXECUTAR, EXPORTAR),
        "banco_horas": (LER, CRIAR, EDITAR, APROVAR, EXPORTAR),
        "workflow": (LER, CRIAR, EDITAR, APROVAR),
        "fechamento": (LER, CRIAR, EDITAR, EXECUTAR, EXPORTAR, ASSINAR),
        "fiscal": (LER, EXECUTAR, EXPORTAR),
        "relatorio": (LER, EXECUTAR, EXPORTAR),
        "auditoria": (LER,),
    },
    "gestor": {
        "pessoas": (LER,),
        "jornada": (LER, CRIAR, EDITAR, APROVAR),
        "marcacao": (LER,),
        "apuracao": (LER, CRIAR, EDITAR, APROVAR),
        "banco_horas": (LER,),
        "workflow": (LER, CRIAR, APROVAR),
        "relatorio": (LER, EXECUTAR, EXPORTAR),
    },
    "colaborador": {
        "marcacao": (LER, CRIAR),
        "apuracao": (LER,),
        "banco_horas": (LER,),
        "workflow": (LER, CRIAR),
        "fechamento": (LER, ASSINAR),
    },
    "auditor": {"*": (LER, EXPORTAR)},
    "integracao": {
        "marcacao": (LER, CRIAR),
        "pessoas": (LER,),
        "apuracao": (LER,),
        "banco_horas": (LER,),
        "relatorio": (LER, EXECUTAR),
    },
}


# ===========================================================================
# Tipos de tratamento de fabrica
# ===========================================================================
#: (codigo, nome, categoria, exige_aprovacao, exige_anexo, retroativo_dias, descricao)
TIPOS_TRATAMENTO: tuple[tuple[str, str, str, bool, bool, int | None, str], ...] = (
    (
        "inclusao_manual",
        "Inclusao manual de marcacao",
        "inclusao_marcacao",
        True,
        False,
        60,
        "Lancamento manual do RH ou do gestor. Aparece no espelho identificado como manual e vai para o AEJ; NUNCA para o AFD.",
    ),
    (
        "desconsideracao",
        "Desconsideracao de marcacao",
        "desconsideracao_marcacao",
        True,
        False,
        60,
        "Ignora uma marcacao na apuracao (batida duplicada, por exemplo). A marcacao permanece intacta no AFD.",
    ),
    (
        "ajuste_intervalo",
        "Ajuste de intervalo",
        "ajuste_intervalo",
        True,
        False,
        60,
        "Corrige o intervalo intrajornada apurado.",
    ),
    (
        "abono_falta",
        "Abono de falta",
        "abono",
        True,
        True,
        90,
        "Abona a falta do dia mediante documento comprobatorio.",
    ),
    (
        "justificativa_atraso",
        "Justificativa de atraso",
        "justificativa",
        True,
        False,
        30,
        "Justifica atraso ou saida antecipada sem abonar automaticamente.",
    ),
    (
        "afastamento_retroativo",
        "Afastamento retroativo",
        "afastamento",
        True,
        True,
        180,
        "Aplica um afastamento sobre periodo ja apurado, disparando reprocessamento.",
    ),
    (
        "compensacao",
        "Compensacao de horas",
        "compensacao",
        True,
        False,
        60,
        "Compensa horas dentro da semana ou do mes, sem passar pelo banco de horas.",
    ),
    (
        "ajuste_saldo_banco",
        "Ajuste de saldo de banco de horas",
        "ajuste_saldo",
        True,
        True,
        365,
        "Ajuste manual de saldo, sempre com motivo e anexo. Gera lancamento proprio no extrato.",
    ),
)


# ===========================================================================
# Tipos de solicitacao de fabrica
# ===========================================================================
#: (codigo, nome, categoria, etapas, prazo_h, escalona_h, anexo, retroativo, tratamento)
TIPOS_SOLICITACAO: tuple[
    tuple[
        str, str, str, list[dict[str, Any]], int | None, int | None, bool, int | None, str | None
    ],
    ...,
] = (
    (
        "ajuste_ponto",
        "Ajuste de ponto",
        "ajuste_ponto",
        [{"etapa": 1, "papel": "gestor"}, {"etapa": 2, "papel": "rh"}],
        48,
        72,
        False,
        30,
        "inclusao_manual",
    ),
    (
        "abono_falta",
        "Abono de falta",
        "abono",
        [{"etapa": 1, "papel": "gestor"}, {"etapa": 2, "papel": "rh"}],
        72,
        120,
        True,
        90,
        "abono_falta",
    ),
    (
        "justificativa",
        "Justificativa de ocorrencia",
        "justificativa",
        [{"etapa": 1, "papel": "gestor"}],
        48,
        72,
        False,
        30,
        "justificativa_atraso",
    ),
    (
        "ferias",
        "Solicitacao de ferias",
        "ferias",
        [{"etapa": 1, "papel": "gestor"}, {"etapa": 2, "papel": "rh"}],
        120,
        168,
        False,
        None,
        None,
    ),
    (
        "folga",
        "Solicitacao de folga",
        "folga",
        [{"etapa": 1, "papel": "gestor"}],
        48,
        72,
        False,
        None,
        None,
    ),
    (
        "compensacao",
        "Compensacao programada",
        "compensacao",
        [{"etapa": 1, "papel": "gestor"}],
        48,
        72,
        False,
        None,
        "compensacao",
    ),
    (
        "afastamento",
        "Comunicacao de afastamento",
        "afastamento",
        [{"etapa": 1, "papel": "rh"}],
        72,
        120,
        True,
        180,
        "afastamento_retroativo",
    ),
    (
        "troca_escala",
        "Troca de escala",
        "troca_escala",
        [{"etapa": 1, "papel": "gestor"}],
        24,
        48,
        False,
        None,
        None,
    ),
    (
        "hora_extra",
        "Autorizacao de hora extra",
        "hora_extra",
        [{"etapa": 1, "papel": "gestor"}],
        24,
        48,
        False,
        None,
        None,
    ),
    (
        "desbloqueio_dispositivo",
        "Desbloqueio ou troca de dispositivo",
        "desbloqueio_dispositivo",
        [{"etapa": 1, "papel": "rh"}],
        24,
        48,
        False,
        None,
        None,
    ),
)


# ===========================================================================
# Feriados nacionais
#
# `ano = NULL` significa que a data se repete todo ano; a coluna `data` guarda
# dia e mes, com ANO_REFERENCIA apenas como portador. Feriados moveis nao
# guardam data: a Fase 3 os calcula a partir da Pascoa do ano de referencia.
# ===========================================================================
ANO_REFERENCIA = 2026

#: (nome, mes, dia, tipo)
FERIADOS_FIXOS: tuple[tuple[str, int, int, str], ...] = (
    ("Confraternizacao Universal", 1, 1, "feriado"),
    ("Tiradentes", 4, 21, "feriado"),
    ("Dia do Trabalho", 5, 1, "feriado"),
    ("Independencia do Brasil", 9, 7, "feriado"),
    ("Nossa Senhora Aparecida", 10, 12, "feriado"),
    ("Finados", 11, 2, "feriado"),
    ("Proclamacao da Republica", 11, 15, "feriado"),
    ("Dia Nacional de Zumbi e da Consciencia Negra", 11, 20, "feriado"),
    ("Natal", 12, 25, "feriado"),
)

#: (nome, regra_movel, offset_dias, tipo)
FERIADOS_MOVEIS: tuple[tuple[str, str, int, str], ...] = (
    ("Carnaval", "carnaval", 0, "ponto_facultativo"),
    ("Quarta-feira de Cinzas", "quarta_cinzas", 0, "ponto_facultativo"),
    ("Sexta-feira Santa", "sexta_santa", 0, "feriado"),
    ("Corpus Christi", "corpus_christi", 0, "ponto_facultativo"),
)


# ===========================================================================
# Utilidades
# ===========================================================================
def _para_driver_sincrono(url: str) -> str:
    """Troca o driver assincrono pelo sincrono equivalente."""
    for assincrono in ("postgresql+asyncpg", "postgresql+psycopg_async", "postgres+asyncpg"):
        if url.startswith(assincrono + "://"):
            return "postgresql+psycopg" + url[len(assincrono) :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def resolve_url(url_argumento: str | None) -> str:
    url = url_argumento or os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit(
            "URL do banco nao definida. Informe --url, DATABASE_URL_SYNC ou DATABASE_URL."
        )
    return _para_driver_sincrono(url)


def gera_hash_senha(senha: str) -> tuple[str, str]:
    """Devolve (hash, algoritmo). Argon2id quando disponivel, scrypt como reserva.

    Os dois algoritmos estao previstos no CHECK de `credenciais.algoritmo`. A
    Fase 1 padroniza em Argon2id; aqui o objetivo e nao depender de biblioteca
    externa para o ambiente de desenvolvimento subir.
    """
    try:  # pragma: no cover - depende do ambiente
        from argon2 import PasswordHasher  # type: ignore[import-not-found]

        return PasswordHasher().hash(senha), "argon2id"
    except ImportError:  # pragma: no cover - reserva da biblioteca padrao
        sal = secrets.token_bytes(16)
        derivado = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2**14, r=8, p=1, dklen=32)
        codificado = "scrypt$n=16384,r=8,p=1${}${}".format(
            base64.b64encode(sal).decode("ascii"),
            base64.b64encode(derivado).decode("ascii"),
        )
        return codificado, "scrypt"


def _obter_ou_criar(
    sessao: Session,
    modelo: type[Any],
    filtros: dict[str, Any],
    valores: dict[str, Any],
) -> tuple[Any, bool]:
    """Busca pela chave natural; cria quando nao existir. Devolve (objeto, criou)."""
    consulta = sa.select(modelo).filter_by(**filtros)
    existente = sessao.scalars(consulta).first()
    if existente is not None:
        return existente, False
    objeto = modelo(**{**filtros, **valores})
    sessao.add(objeto)
    sessao.flush()
    return objeto, True


# ===========================================================================
# Semeadura
# ===========================================================================
class _Secar(Exception):
    """Sinal interno do modo `--secar`: desfaz a transacao ao sair do bloco."""


class Resumo:
    """Contador do que foi criado, para o relatorio final."""

    def __init__(self) -> None:
        self.itens: dict[str, int] = {}

    def soma(self, rotulo: str, quantidade: int = 1) -> None:
        self.itens[rotulo] = self.itens.get(rotulo, 0) + quantidade

    def imprime(self) -> None:
        if not self.itens:
            print("  nada criado - o banco ja estava semeado.")
            return
        for rotulo in sorted(self.itens):
            print(f"  {self.itens[rotulo]:>4}  {rotulo}")


def semeia_permissoes(sessao: Session, resumo: Resumo) -> dict[str, Any]:
    """Catalogo GLOBAL de permissoes. Nao tem tenant_id e nao esta sob RLS."""
    por_codigo: dict[str, Any] = {}
    for modulo, recurso, acoes, sensivel, descricao in CATALOGO_PERMISSOES:
        for acao in acoes:
            codigo = f"{recurso}.{acao}"
            permissao, criou = _obter_ou_criar(
                sessao,
                contrato.Permissao,
                {"codigo": codigo},
                {
                    "recurso": recurso,
                    "acao": acao,
                    "modulo": modulo,
                    "sensivel": sensivel,
                    "descricao": f"{descricao} - {acao}",
                },
            )
            por_codigo[codigo] = permissao
            if criou:
                resumo.soma("permissoes")
    return por_codigo


def semeia_perfis(
    sessao: Session,
    tenant_id: uuid.UUID,
    permissoes: dict[str, Any],
    resumo: Resumo,
) -> dict[str, Any]:
    modulo_por_codigo = {
        f"{recurso}.{acao}": modulo
        for modulo, recurso, acoes, _s, _d in CATALOGO_PERMISSOES
        for acao in acoes
    }

    perfis: dict[str, Any] = {}
    for codigo, nome, escopo, somente_leitura, descricao in PERFIS_FABRICA:
        perfil, criou = _obter_ou_criar(
            sessao,
            contrato.Perfil,
            {"tenant_id": tenant_id, "codigo": codigo},
            {
                "nome": nome,
                "descricao": descricao,
                "sistema": True,
                "escopo_padrao": escopo,
                "somente_leitura": somente_leitura,
            },
        )
        perfis[codigo] = perfil
        if criou:
            resumo.soma("perfis")

        regras = MATRIZ_PERFIS.get(codigo, {})
        for codigo_permissao, permissao in permissoes.items():
            acoes_do_modulo = regras.get("*") or regras.get(modulo_por_codigo[codigo_permissao], ())
            if permissao.acao not in acoes_do_modulo:
                continue
            _, criou_vinculo = _obter_ou_criar(
                sessao,
                contrato.PerfilPermissao,
                {
                    "tenant_id": tenant_id,
                    "perfil_id": perfil.id,
                    "permissao_id": permissao.id,
                },
                {"concedida": True},
            )
            if criou_vinculo:
                resumo.soma("perfil_permissoes")
    return perfis


def semeia_tipos_tratamento(
    sessao: Session, tenant_id: uuid.UUID, resumo: Resumo
) -> dict[str, Any]:
    tipos: dict[str, Any] = {}
    for codigo, nome, categoria, aprovacao, anexo, retroativo, descricao in TIPOS_TRATAMENTO:
        tipo, criou = _obter_ou_criar(
            sessao,
            contrato.TipoTratamento,
            {"tenant_id": tenant_id, "codigo": codigo},
            {
                "nome": nome,
                "descricao": descricao,
                "categoria": categoria,
                "exige_aprovacao": aprovacao,
                "exige_anexo": anexo,
                "exige_motivo": True,
                # afeta_afd e FALSE por CHECK no schema: tratamento nunca entra no AFD.
                "afeta_afd": False,
                "afeta_aej": True,
                "permite_retroativo_dias": retroativo,
            },
        )
        tipos[codigo] = tipo
        if criou:
            resumo.soma("tipos_tratamento")
    return tipos


def semeia_tipos_solicitacao(
    sessao: Session,
    tenant_id: uuid.UUID,
    tipos_tratamento: dict[str, Any],
    resumo: Resumo,
) -> None:
    for (
        codigo,
        nome,
        categoria,
        etapas,
        prazo,
        escalona,
        anexo,
        retroativo,
        tratamento,
    ) in TIPOS_SOLICITACAO:
        tipo_tratamento = tipos_tratamento.get(tratamento) if tratamento else None
        _, criou = _obter_ou_criar(
            sessao,
            contrato.TipoSolicitacao,
            {"tenant_id": tenant_id, "codigo": codigo},
            {
                "nome": nome,
                "descricao": f"Solicitacao de {nome.lower()}.",
                "categoria": categoria,
                "etapas": etapas,
                "prazo_resposta_horas": prazo,
                "escalonar_apos_horas": escalona,
                "exige_anexo": anexo,
                "exige_justificativa": True,
                "permite_retroativo_dias": retroativo,
                "tipo_tratamento_id": tipo_tratamento.id if tipo_tratamento else None,
            },
        )
        if criou:
            resumo.soma("tipos_solicitacao")


def semeia_feriados(
    sessao: Session, tenant_id: uuid.UUID, unidade_id: uuid.UUID, resumo: Resumo
) -> None:
    conjunto, criou = _obter_ou_criar(
        sessao,
        contrato.FeriadoConjunto,
        {"tenant_id": tenant_id, "codigo": "nacional"},
        {
            "nome": "Feriados nacionais",
            "abrangencia": "nacional",
        },
    )
    if criou:
        resumo.soma("feriado_conjuntos")

    for nome, mes, dia, tipo in FERIADOS_FIXOS:
        data = dt.date(ANO_REFERENCIA, mes, dia)
        _, criou_feriado = _obter_ou_criar(
            sessao,
            contrato.Feriado,
            {
                "tenant_id": tenant_id,
                "feriado_conjunto_id": conjunto.id,
                "data": data,
                "nome": nome,
            },
            {
                "tipo": tipo,
                "movel": False,
                "ano": None,  # NULL = repete todo ano
                "integral": True,
            },
        )
        if criou_feriado:
            resumo.soma("feriados (fixos)")

    for nome, regra, deslocamento, tipo in FERIADOS_MOVEIS:
        _, criou_feriado = _obter_ou_criar(
            sessao,
            contrato.Feriado,
            {
                "tenant_id": tenant_id,
                "feriado_conjunto_id": conjunto.id,
                "nome": nome,
                "movel": True,
            },
            {
                "tipo": tipo,
                "regra_movel": regra,
                "offset_dias": deslocamento,
                "integral": True,
            },
        )
        if criou_feriado:
            resumo.soma("feriados (moveis)")

    _, criou_vinculo = _obter_ou_criar(
        sessao,
        contrato.UnidadeFeriadoConjunto,
        {
            "tenant_id": tenant_id,
            "unidade_id": unidade_id,
            "feriado_conjunto_id": conjunto.id,
        },
        {},
    )
    if criou_vinculo:
        resumo.soma("unidade_feriado_conjuntos")


def semeia(
    sessao: Session,
    *,
    slug: str,
    razao_social: str,
    cnpj: str,
    admin_email: str,
    admin_nome: str,
    senha: str,
    resumo: Resumo,
) -> uuid.UUID:
    # --- tenant -------------------------------------------------------------
    # O tenant precisa existir ANTES de app.tenant_id apontar para ele, e a
    # policy de `tenants` compara `id`. Por isso o UUID e escolhido aqui, o
    # contexto e definido, e so entao a linha e inserida.
    existente = sessao.scalars(sa.select(contrato.Tenant).filter_by(slug=slug)).first()
    tenant_id = existente.id if existente else uuid.uuid4()

    sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )

    if existente is None:
        tenant = contrato.Tenant(
            id=tenant_id,
            slug=slug,
            razao_social=razao_social,
            nome_exibicao=razao_social,
            documento=cnpj,
            plano="enterprise",
            status="ativo",
            fuso_horario="America/Sao_Paulo",
            locale="pt-BR",
            data_contratacao=dt.datetime.now(dt.timezone.utc).date(),
        )
        sessao.add(tenant)
        sessao.flush()
        resumo.soma("tenants")

    # --- empresa ------------------------------------------------------------
    empresa, criou = _obter_ou_criar(
        sessao,
        contrato.Empresa,
        {"tenant_id": tenant_id, "cnpj": cnpj},
        {
            "tipo": "matriz",
            "razao_social": razao_social,
            "nome_fantasia": razao_social,
            "municipio": "Goiania",
            "uf": "GO",
            "fuso_horario": "America/Sao_Paulo",
            "ativo": True,
        },
    )
    if criou:
        resumo.soma("empresas")

    # --- unidade ------------------------------------------------------------
    unidade, criou = _obter_ou_criar(
        sessao,
        contrato.Unidade,
        {"tenant_id": tenant_id, "empresa_id": empresa.id, "codigo": "SEDE"},
        {
            "nome": "Sede",
            "tipo": "sede",
            "municipio": "Goiania",
            "uf": "GO",
            "fuso_horario": "America/Sao_Paulo",
            "geocerca_obrigatoria": False,
            "geocerca_tolerancia_metros": 50,
            "ativo": True,
        },
    )
    if criou:
        resumo.soma("unidades")

    # --- RBAC ---------------------------------------------------------------
    permissoes = semeia_permissoes(sessao, resumo)
    perfis = semeia_perfis(sessao, tenant_id, permissoes, resumo)

    # --- usuario administrador ---------------------------------------------
    usuario = sessao.scalars(
        sa.select(contrato.Usuario).filter_by(tenant_id=tenant_id, email=admin_email)
    ).first()
    if usuario is None:
        usuario = contrato.Usuario(
            tenant_id=tenant_id,
            email=admin_email,
            nome_completo=admin_nome,
            tipo="humano",
            status="ativo",
            mfa_obrigatorio=False,
            email_verificado_em=dt.datetime.now(dt.timezone.utc),
        )
        sessao.add(usuario)
        sessao.flush()
        resumo.soma("usuarios")

    hash_senha, algoritmo = gera_hash_senha(senha)
    credencial = sessao.scalars(
        sa.select(contrato.Credencial).filter_by(
            tenant_id=tenant_id, usuario_id=usuario.id, tipo="senha", ativo=True
        )
    ).first()
    if credencial is None:
        sessao.add(
            contrato.Credencial(
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                tipo="senha",
                hash=hash_senha,
                algoritmo=algoritmo,
                trocar_no_proximo_acesso=True,
                ativo=True,
                ultima_troca_em=dt.datetime.now(dt.timezone.utc),
            )
        )
        resumo.soma("credenciais")

    _, criou = _obter_ou_criar(
        sessao,
        contrato.UsuarioPerfil,
        {
            "tenant_id": tenant_id,
            "usuario_id": usuario.id,
            "perfil_id": perfis["admin_empresa"].id,
            "escopo_tipo": "tenant",
        },
        {"incluir_subordinados": True},
    )
    if criou:
        resumo.soma("usuario_perfis")

    # --- catalogos do motor -------------------------------------------------
    tipos_tratamento = semeia_tipos_tratamento(sessao, tenant_id, resumo)
    semeia_tipos_solicitacao(sessao, tenant_id, tipos_tratamento, resumo)
    semeia_feriados(sessao, tenant_id, unidade.id, resumo)

    return tenant_id


# ===========================================================================
# CLI
# ===========================================================================
def monta_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_dev.py",
        description="Semeia os dados minimos de desenvolvimento do Ponto Eletronico.",
    )
    parser.add_argument("--url", help="URL do banco. Sobrepoe DATABASE_URL_SYNC/DATABASE_URL.")
    parser.add_argument("--tenant-slug", default="seeg", help="Slug do tenant (padrao: seeg).")
    parser.add_argument(
        "--razao-social",
        default="SEEG Servicos de Tecnologia da Informacao",
        help="Razao social do tenant e da empresa matriz.",
    )
    parser.add_argument(
        "--cnpj",
        default="60258502000149",
        help="CNPJ da empresa matriz, somente digitos.",
    )
    parser.add_argument(
        "--admin-email", default="admin@seeg.com.br", help="E-mail do usuario administrador."
    )
    parser.add_argument(
        "--admin-nome", default="Administrador SEEG", help="Nome do usuario administrador."
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Permite rodar mesmo quando AMBIENTE indica producao.",
    )
    parser.add_argument(
        "--secar",
        action="store_true",
        help="Faz tudo e desfaz no fim (rollback). Util para validar o script.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = monta_parser().parse_args(argv)

    ambiente = (os.getenv("AMBIENTE") or os.getenv("ENVIRONMENT") or "dev").strip().lower()
    if ambiente in AMBIENTES_PRODUCAO and not args.forcar:
        print(
            f"RECUSADO: AMBIENTE={ambiente!r} indica producao. "
            "Dados de desenvolvimento nao entram em producao. Use --forcar se tem certeza.",
            file=sys.stderr,
        )
        return 2

    senha = os.getenv(VARIAVEL_SENHA)
    if not senha:
        print(
            f"RECUSADO: defina {VARIAVEL_SENHA} com a senha do administrador. "
            "Nao existe senha padrao neste script, de proposito.",
            file=sys.stderr,
        )
        return 2
    if len(senha) < 12:
        print(
            f"RECUSADO: {VARIAVEL_SENHA} precisa ter ao menos 12 caracteres.",
            file=sys.stderr,
        )
        return 2

    url = resolve_url(args.url)
    engine = sa.create_engine(url, future=True)

    resumo = Resumo()
    tenant_id: uuid.UUID | None = None
    try:
        with Session(engine) as sessao, sessao.begin():
            tenant_id = semeia(
                sessao,
                slug=args.tenant_slug,
                razao_social=args.razao_social,
                cnpj=args.cnpj,
                admin_email=args.admin_email,
                admin_nome=args.admin_nome,
                senha=senha,
                resumo=resumo,
            )
            if args.secar:
                # Sai por excecao para que o `with` desfaca tudo: o modo secar
                # existe justamente para provar o script sem sujar o banco.
                raise _Secar
    except _Secar:
        print("MODO SECAR: tudo desfeito no fim (rollback).")
    finally:
        engine.dispose()

    print(f"\nSeed de desenvolvimento concluido. tenant={args.tenant_slug} ({tenant_id})")
    print(f"Administrador: {args.admin_email} (senha lida de {VARIAVEL_SENHA}).")
    print("A credencial nasce com trocar_no_proximo_acesso = TRUE.\n")
    print("Criado nesta execucao:")
    resumo.imprime()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
