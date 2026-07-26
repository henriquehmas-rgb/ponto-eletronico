"""Importador de colaboradores (T10 do PCF da F2).

`enviar_webhook` e `sincronizar_terminal` (F13 e F6) continuam em
`worker/tarefas/integracoes.py` -- este arquivo e novo, dedicado a
`importar_colaboradores`, e nao duplica aquelas duas tarefas.

**`importar_colaboradores`** processa a planilha CSV/XLSX referenciada por uma
linha de `importacoes` (`tipo = 'colaboradores'`), criada por
`app/importadores/servico.py` (lado API) e enfileirada na fila
`FILA_INTEGRACOES` (ver `worker/filas.py`). E a nona tarefa do worker -- ver a
nota da secao 2 do PCF da F2 sobre a divergencia, ja decidida, entre a
docstring antiga deste pacote e `packages/contracts/events.yaml`.

Layout aceito (cabecalho case-insensitive, primeira linha da planilha):

| Coluna             | Obrigatoria | Observacao                                   |
|--------------------|-------------|-----------------------------------------------|
| `matricula`        | sim         | Unica por tenant+empresa.                     |
| `cpf`               | sim         | Com ou sem mascara; validado por digito verificador. |
| `nome_completo`     | sim         |                                                |
| `empresa_cnpj`      | sim         | Resolve a empresa por CNPJ dentro do tenant.  |
| `data_admissao`     | sim         | `AAAA-MM-DD`.                                  |
| `pis`               | nao         | Validado por digito verificador quando presente. |
| `nome_social`       | nao         |                                                |
| `matricula_esocial` | nao         | Default: a propria `matricula`.               |
| `tipo_contrato`     | nao         | Default `clt`; um dos valores de `contratos.tipo`. |

Cada linha recusada acumula em `importacoes.erros` (`{"linhas": [...]}`) com
`linha`, `campo`, `codigo` (do catalogo) e `mensagem`, **sem abortar o
restante da carga**. Reprocessar o mesmo arquivo atualiza o colaborador
existente (por tenant+empresa+matricula) em vez de duplicar, e nao recria
vinculo/contrato se ja existir um com a mesma `matricula_esocial`.

**Armazenamento de objetos.** `importacoes.conteudo_ref` e documentado no
contrato como a chave do arquivo no MinIO, mas nenhuma fase ate agora
integrou um cliente MinIO real (nem `apps/api`, nem `apps/worker`). Enquanto
isso nao existe, este modulo le o conteudo de um diretorio local configuravel
por `PONTO_ARMAZENAMENTO_DIR` (default: subpasta `ponto-objetos` do temp do
SO) -- documentado em `docs/backlog.md` como pendencia de integracao real de
objeto, a ser resolvida quando um cliente MinIO existir no projeto.

**Publicacao de eventos.** Nao existe barramento de eventos nem tabela de
"outbox" generica disponivel a esta fase (`webhook_entregas` exige um
`webhook_id` de um webhook ja configurado, fora do escopo aqui). Por isso
`publicar_evento` grava o envelope EXATO de `events.yaml` num log estruturado
(`obter_logger`), que e o ponto que a F13 substitui por entrega de verdade
(enfileirar `enviar_webhook` por assinante configurado) sem mudar quem chama.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import openpyxl
import sqlalchemy as sa
from ponto_contracts import Colaborador, Contrato, Empresa, Importacao, Vinculo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from worker.config import obter_configuracao
from worker.log import obter_logger

logger = obter_logger("tarefas.importacoes")

__all__ = [
    "ArquivoNaoEncontrado",
    "LayoutInvalido",
    "construir_envelope_evento",
    "importar_colaboradores",
    "publicar_evento",
    "reiniciar_engine_para_testes",
]

# =============================================================================
# Validadores de documento (duplicados de `apps/api/app/comum/documentos.py`
# de proposito: o worker nao pode importar codigo de `apps/api` -- sao
# imagens Docker separadas, ver `apps/worker/Dockerfile`. Mesmo algoritmo,
# mesma fonte -- Receita Federal / regra do modulo 11. Se o algoritmo mudar,
# muda nos dois lugares; registrado em docs/backlog.md.)
# =============================================================================


def _somente_digitos(valor: str) -> str:
    return "".join(caractere for caractere in valor if caractere.isdigit())


def _sequencia_repetida(digitos: str) -> bool:
    return len(set(digitos)) == 1


def _digito_modulo_11(digitos: str, pesos: list[int]) -> int:
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _cpf_valido(valor: str) -> bool:
    digitos = _somente_digitos(valor)
    if len(digitos) != 11 or _sequencia_repetida(digitos):
        return False
    dv1 = _digito_modulo_11(digitos[:9], list(range(10, 1, -1)))
    dv2 = _digito_modulo_11(digitos[:9] + str(dv1), list(range(11, 1, -1)))
    return digitos[-2:] == f"{dv1}{dv2}"


def _pis_valido(valor: str) -> bool:
    digitos = _somente_digitos(valor)
    if len(digitos) != 11 or _sequencia_repetida(digitos):
        return False
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digito) * peso for digito, peso in zip(digitos[:10], pesos, strict=True))
    resto = soma % 11
    dv = 11 - resto
    if dv >= 10:
        dv = 0
    return digitos[-1] == str(dv)


# =============================================================================
# Armazenamento de objetos (interino -- ver docstring do modulo)
# =============================================================================


class ArquivoNaoEncontrado(RuntimeError):
    """`conteudo_ref` nao existe no armazenamento configurado."""


def _raiz_armazenamento() -> Path:
    bruto = os.environ.get("PONTO_ARMAZENAMENTO_DIR", "")
    if bruto:
        return Path(bruto)
    return Path(tempfile.gettempdir()) / "ponto-objetos"


def _ler_conteudo(conteudo_ref: str) -> bytes:
    if not conteudo_ref:
        raise ArquivoNaoEncontrado("Importacao sem conteudoRef.")
    raiz = _raiz_armazenamento().resolve()
    caminho = (raiz / conteudo_ref).resolve()
    if caminho != raiz and raiz not in caminho.parents:
        raise ArquivoNaoEncontrado("conteudoRef fora do armazenamento configurado.")
    if not caminho.is_file():
        raise ArquivoNaoEncontrado(f"Objeto '{conteudo_ref}' nao encontrado no armazenamento.")
    return caminho.read_bytes()


# =============================================================================
# Sessao de banco (lazy, self-contained -- ver `apps/api/app/db/sessao.py`,
# que este modulo NAO importa pelo mesmo motivo dos validadores acima)
# =============================================================================

_engine: AsyncEngine | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def _fabrica_de_sessoes() -> async_sessionmaker[AsyncSession]:
    global _engine, _fabrica
    if _fabrica is None:
        config = obter_configuracao()
        _engine = create_async_engine(config.database_url, pool_pre_ping=True)
        _fabrica = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _fabrica


async def reiniciar_engine_para_testes() -> None:
    """SOMENTE para teste: descarta a engine cacheada para que a proxima
    chamada crie uma nova, presa ao event loop corrente.

    O processo real do worker vive num unico event loop pelo tempo de vida
    inteiro (natureza do ARQ), entao o cache em modulo-nivel e correto em
    producao. `pytest-asyncio` cria um loop novo por teste
    (`asyncio_default_fixture_loop_scope = "function"`); sem este reset, a
    engine de um teste anterior fica presa a um loop ja fechado e a proxima
    chamada falha com `RuntimeError: Event loop is closed`.
    """
    global _engine, _fabrica
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _fabrica = None


async def _aplicar_tenant(sessao: AsyncSession, tenant_id: str) -> None:
    """`SET LOCAL app.tenant_id` -- ADR-001 consequencia (a): o worker nao tem
    requisicao HTTP e precisa publicar o tenant explicitamente em cada job."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
    )


def _agora() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


# =============================================================================
# Parsing do arquivo
# =============================================================================


class LayoutInvalido(RuntimeError):
    """Cabecalho ausente, planilha vazia ou coluna obrigatoria faltando."""


COLUNAS_OBRIGATORIAS: frozenset[str] = frozenset(
    {"matricula", "cpf", "nome_completo", "empresa_cnpj", "data_admissao"}
)

_TIPOS_CONTRATO_VALIDOS: frozenset[str] = frozenset(
    {
        "clt",
        "aprendiz",
        "estagio",
        "temporario",
        "intermitente",
        "avulso",
        "autonomo",
        "pj",
        "socio",
        "servidor",
    }
)


def _parsear_csv(conteudo: bytes, *, delimitador: str) -> list[dict[str, str]]:
    texto = conteudo.decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    if leitor.fieldnames is None:
        raise LayoutInvalido("Arquivo CSV vazio ou sem cabecalho.")
    cabecalho = {(nome or "").strip().lower() for nome in leitor.fieldnames}
    faltando = COLUNAS_OBRIGATORIAS - cabecalho
    if faltando:
        raise LayoutInvalido(f"Colunas obrigatorias ausentes no CSV: {sorted(faltando)}.")
    linhas: list[dict[str, str]] = []
    for linha in leitor:
        linhas.append(
            {
                (chave or "").strip().lower(): (valor or "").strip()
                for chave, valor in linha.items()
                if chave
            }
        )
    return linhas


def _celula_para_texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, dt.datetime):
        return valor.date().isoformat()
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _parsear_xlsx(conteudo: bytes) -> list[dict[str, str]]:
    try:
        pasta = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:
        raise LayoutInvalido(f"Arquivo XLSX ilegivel: {exc}") from exc
    planilha = pasta.worksheets[0]
    linhas_iter = planilha.iter_rows(values_only=True)
    try:
        cabecalho_bruto = next(linhas_iter)
    except StopIteration as exc:
        raise LayoutInvalido("Planilha XLSX vazia.") from exc
    cabecalho = [(str(c).strip().lower() if c is not None else "") for c in cabecalho_bruto]
    faltando = COLUNAS_OBRIGATORIAS - set(cabecalho)
    if faltando:
        raise LayoutInvalido(f"Colunas obrigatorias ausentes na planilha: {sorted(faltando)}.")
    linhas: list[dict[str, str]] = []
    for tupla in linhas_iter:
        if tupla is None or all(v is None for v in tupla):
            continue
        linha = {
            chave: _celula_para_texto(tupla[indice] if indice < len(tupla) else None)
            for indice, chave in enumerate(cabecalho)
            if chave
        }
        linhas.append(linha)
    pasta.close()
    return linhas


def _parsear_arquivo(
    conteudo: bytes, origem: str, parametros: dict[str, Any]
) -> list[dict[str, str]]:
    if origem == "csv":
        delimitador = str(parametros.get("delimitador") or ",")
        return _parsear_csv(conteudo, delimitador=delimitador)
    if origem == "xlsx":
        return _parsear_xlsx(conteudo)
    raise LayoutInvalido(f"Origem '{origem}' nao suportada pelo importador de colaboradores.")


# =============================================================================
# Validacao linha a linha
# =============================================================================


@dataclass(slots=True)
class _LinhaValida:
    numero_linha: int
    matricula: str
    cpf: str
    pis: str | None
    nome_completo: str
    nome_social: str | None
    empresa_id: UUID
    data_admissao: dt.date
    matricula_esocial: str
    tipo_contrato: str


def _erro_linha(linha: int, campo: str, codigo: str, mensagem: str) -> dict[str, Any]:
    return {"linha": linha, "campo": campo, "codigo": codigo, "mensagem": mensagem}


_ANO_MINIMO = 1900


def _parsear_data_admissao(bruta: str) -> dt.date | None:
    if not bruta:
        return None
    try:
        data = dt.date.fromisoformat(bruta[:10])
    except ValueError:
        return None
    hoje = _agora().date()
    limite_futuro = hoje.replace(year=hoje.year + 1)
    if data.year < _ANO_MINIMO or data > limite_futuro:
        return None
    return data


def _validar_linha(
    bruta: dict[str, str],
    *,
    numero_linha: int,
    empresas_por_cnpj: dict[str, UUID],
    matriculas_vistas: dict[tuple[UUID, str], int],
) -> _LinhaValida | dict[str, Any]:
    matricula = (bruta.get("matricula") or "").strip()
    if not matricula:
        return _erro_linha(numero_linha, "matricula", "PONTO-VAL-001", "Matricula e obrigatoria.")

    cpf_bruto = bruta.get("cpf") or ""
    if not _cpf_valido(cpf_bruto):
        return _erro_linha(numero_linha, "cpf", "PONTO-VAL-002", "CPF invalido.")
    cpf = _somente_digitos(cpf_bruto)

    pis_bruto = (bruta.get("pis") or "").strip()
    pis: str | None = None
    if pis_bruto:
        if not _pis_valido(pis_bruto):
            return _erro_linha(numero_linha, "pis", "PONTO-VAL-004", "PIS/NIT invalido.")
        pis = _somente_digitos(pis_bruto)

    nome_completo = (bruta.get("nome_completo") or "").strip()
    if not nome_completo:
        return _erro_linha(
            numero_linha, "nomeCompleto", "PONTO-VAL-001", "Nome completo e obrigatorio."
        )

    cnpj = _somente_digitos(bruta.get("empresa_cnpj") or "")
    empresa_id = empresas_por_cnpj.get(cnpj)
    if empresa_id is None:
        return _erro_linha(
            numero_linha, "empresaCnpj", "PONTO-REC-001", "Empresa nao encontrada para este CNPJ."
        )

    data_admissao = _parsear_data_admissao((bruta.get("data_admissao") or "").strip())
    if data_admissao is None:
        return _erro_linha(
            numero_linha,
            "dataAdmissao",
            "PONTO-VAL-007",
            "Data de admissao ausente, invalida ou incoerente.",
        )

    chave_matricula = (empresa_id, matricula)
    if chave_matricula in matriculas_vistas:
        primeira = matriculas_vistas[chave_matricula]
        return _erro_linha(
            numero_linha,
            "matricula",
            "PONTO-CONF-001",
            f"Matricula duplicada no arquivo (primeira ocorrencia na linha {primeira}).",
        )
    matriculas_vistas[chave_matricula] = numero_linha

    tipo_contrato = (bruta.get("tipo_contrato") or "").strip().lower() or "clt"
    if tipo_contrato not in _TIPOS_CONTRATO_VALIDOS:
        return _erro_linha(
            numero_linha,
            "tipoContrato",
            "PONTO-VAL-001",
            f"Tipo de contrato invalido: {tipo_contrato!r}.",
        )

    return _LinhaValida(
        numero_linha=numero_linha,
        matricula=matricula,
        cpf=cpf,
        pis=pis,
        nome_completo=nome_completo,
        nome_social=(bruta.get("nome_social") or "").strip() or None,
        empresa_id=empresa_id,
        data_admissao=data_admissao,
        matricula_esocial=(bruta.get("matricula_esocial") or "").strip() or matricula,
        tipo_contrato=tipo_contrato,
    )


# =============================================================================
# Consultas em lote (poucos round-trips: a fixture roda contra a VPS por
# tunel SSH, e 5.000 idas-e-voltas individuais estourariam os 5 minutos do
# criterio de aceite 7. Ver secao 8 do PCF.)
# =============================================================================


async def _carregar_empresas_por_cnpj(sessao: AsyncSession, tenant_id: UUID) -> dict[str, UUID]:
    resultado = await sessao.execute(
        sa.select(Empresa.cnpj, Empresa.id).where(
            Empresa.tenant_id == tenant_id, Empresa.excluido_em.is_(None)
        )
    )
    return dict(resultado.tuples().all())


async def _carregar_colaboradores_existentes(
    sessao: AsyncSession, tenant_id: UUID, empresa_ids: set[UUID]
) -> tuple[dict[tuple[UUID, str], UUID], dict[tuple[UUID, str], UUID]]:
    if not empresa_ids:
        return {}, {}
    consulta = sa.select(
        Colaborador.id, Colaborador.empresa_id, Colaborador.matricula, Colaborador.cpf
    ).where(
        Colaborador.tenant_id == tenant_id,
        Colaborador.empresa_id.in_(empresa_ids),
        Colaborador.excluido_em.is_(None),
    )
    resultado = await sessao.execute(consulta)
    por_matricula: dict[tuple[UUID, str], UUID] = {}
    por_cpf: dict[tuple[UUID, str], UUID] = {}
    for id_, empresa_id, matricula, cpf in resultado.all():
        por_matricula[(empresa_id, matricula)] = id_
        por_cpf[(empresa_id, cpf)] = id_
    return por_matricula, por_cpf


async def _carregar_matriculas_esocial_existentes(
    sessao: AsyncSession, tenant_id: UUID, empresa_ids: set[UUID]
) -> set[tuple[UUID, str]]:
    if not empresa_ids:
        return set()
    resultado = await sessao.execute(
        sa.select(Vinculo.empresa_id, Vinculo.matricula_esocial).where(
            Vinculo.tenant_id == tenant_id,
            Vinculo.empresa_id.in_(empresa_ids),
            Vinculo.excluido_em.is_(None),
        )
    )
    return set(resultado.tuples().all())


# =============================================================================
# Eventos (ver docstring do modulo sobre a ausencia de barramento real)
# =============================================================================


def construir_envelope_evento(
    *, tipo: str, versao: int, tenant_id: str, empresa_id: str | None, dados: dict[str, Any]
) -> dict[str, Any]:
    agora = _agora().isoformat()
    return {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": versao,
        "ocorridoEm": agora,
        "publicadoEm": agora,
        "tenantId": tenant_id,
        "empresaId": empresa_id,
        "dados": dados,
    }


def publicar_evento(envelope: dict[str, Any]) -> None:
    logger.info("evento publicado", extra={"evento": envelope["tipo"], "envelope": envelope})


# =============================================================================
# Tarefa principal
# =============================================================================

_STATUS_FINAIS = frozenset({"concluido", "concluido_com_erros", "falhou", "cancelado"})

#: `importacoes.status` (schema.sql) -> `importacao.concluida.dados.status`
#: (events.yaml), que usa `concluidoComErros` em vez de `concluido_com_erros`.
_STATUS_PARA_EVENTO: dict[str, str] = {
    "concluido": "concluido",
    "concluido_com_erros": "concluidoComErros",
    "falhou": "falhou",
}


async def _finalizar_com_falha(
    sessao: AsyncSession, importacao: Importacao, *, mensagem: str
) -> None:
    importacao.status = "falhou"
    importacao.concluido_em = _agora()
    importacao.erros = {
        "linhas": [],
        "arquivo": [{"campo": "arquivo", "codigo": "PONTO-IMP-001", "mensagem": mensagem}],
    }
    await sessao.commit()


async def importar_colaboradores(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    importacao_id: str,
) -> dict[str, Any]:
    """Processa `POST /v1/colaboradores/importar`: le o arquivo, valida linha a
    linha SEM abortar a carga por linha ruim, grava o relatorio de erros em
    `importacoes.erros` e publica `importacao.concluida` (e `colaborador.
    admitido` por vinculo ativo criado)."""
    tenant_uuid = UUID(tenant_id)
    importacao_uuid = UUID(importacao_id)
    fabrica = _fabrica_de_sessoes()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        importacao = await sessao.get(Importacao, importacao_uuid)
        if importacao is None:
            logger.warning(
                "importacao nao encontrada",
                extra={"importacaoId": importacao_id, "tenantId": tenant_id},
            )
            return {"implementado": True, "encontrada": False, "importacaoId": importacao_id}
        if importacao.status in _STATUS_FINAIS:
            # Idempotencia entre execucoes: job reenfileirado ou reentrega do
            # ARQ (at-least-once) nao reprocessa uma importacao ja concluida.
            logger.info(
                "importacao ja processada, ignorando reexecucao",
                extra={"importacaoId": importacao_id, "status": importacao.status},
            )
            return {
                "implementado": True,
                "jaProcessada": True,
                "importacaoId": importacao_id,
                "status": importacao.status,
            }
        importacao.status = "processando"
        importacao.iniciado_em = _agora()
        await sessao.commit()

    inicio = time.perf_counter()
    eventos_admissao: list[dict[str, Any]] = []
    envelope_conclusao: dict[str, Any] | None = None

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        importacao = await sessao.get(Importacao, importacao_uuid)
        if importacao is None:  # pragma: no cover - checado acima na mesma transacao logica
            return {"implementado": True, "encontrada": False, "importacaoId": importacao_id}

        try:
            conteudo = _ler_conteudo(importacao.conteudo_ref or "")
        except ArquivoNaoEncontrado as exc:
            await _finalizar_com_falha(sessao, importacao, mensagem=str(exc))
            envelope_conclusao = construir_envelope_evento(
                tipo="importacao.concluida",
                versao=1,
                tenant_id=tenant_id,
                empresa_id=str(importacao.empresa_id) if importacao.empresa_id else None,
                dados={
                    "importacaoId": importacao_id,
                    "tipo": "colaboradores",
                    "status": "falhou",
                    "totalLinhas": 0,
                    "linhasSucesso": 0,
                    "linhasErro": 0,
                    "relatorioDisponivel": False,
                },
            )
            publicar_evento(envelope_conclusao)
            return {"implementado": True, "importacaoId": importacao_id, "status": "falhou"}

        try:
            linhas_brutas = _parsear_arquivo(
                conteudo, importacao.origem, importacao.parametros or {}
            )
        except LayoutInvalido as exc:
            await _finalizar_com_falha(sessao, importacao, mensagem=str(exc))
            envelope_conclusao = construir_envelope_evento(
                tipo="importacao.concluida",
                versao=1,
                tenant_id=tenant_id,
                empresa_id=str(importacao.empresa_id) if importacao.empresa_id else None,
                dados={
                    "importacaoId": importacao_id,
                    "tipo": "colaboradores",
                    "status": "falhou",
                    "totalLinhas": 0,
                    "linhasSucesso": 0,
                    "linhasErro": 0,
                    "relatorioDisponivel": False,
                },
            )
            publicar_evento(envelope_conclusao)
            return {"implementado": True, "importacaoId": importacao_id, "status": "falhou"}

        empresas_por_cnpj = await _carregar_empresas_por_cnpj(sessao, tenant_uuid)

        erros: list[dict[str, Any]] = []
        candidatos: list[_LinhaValida] = []
        matriculas_vistas: dict[tuple[UUID, str], int] = {}
        for numero_linha, bruta in enumerate(linhas_brutas, start=2):
            resultado = _validar_linha(
                bruta,
                numero_linha=numero_linha,
                empresas_por_cnpj=empresas_por_cnpj,
                matriculas_vistas=matriculas_vistas,
            )
            if isinstance(resultado, dict):
                erros.append(resultado)
            else:
                candidatos.append(resultado)

        empresas_usadas = {c.empresa_id for c in candidatos}
        existentes_por_matricula, existentes_por_cpf = await _carregar_colaboradores_existentes(
            sessao, tenant_uuid, empresas_usadas
        )
        vinculos_existentes = await _carregar_matriculas_esocial_existentes(
            sessao, tenant_uuid, empresas_usadas
        )

        novos_colaboradores: list[dict[str, Any]] = []
        atualizacoes_colaborador: list[dict[str, Any]] = []
        novos_contratos: list[dict[str, Any]] = []
        novos_vinculos: list[dict[str, Any]] = []

        for candidato in candidatos:
            chave_matricula = (candidato.empresa_id, candidato.matricula)
            colaborador_existente_id = existentes_por_matricula.get(chave_matricula)
            if colaborador_existente_id is not None:
                # Reprocessamento do mesmo arquivo: atualiza em vez de duplicar.
                # A chave `id` alimenta o "ORM Bulk UPDATE by Primary Key" do
                # SQLAlchemy 2 (abaixo): cada dict com `id` mais as colunas a
                # mudar, sem `.where()` nem `.values()` explicitos.
                atualizacoes_colaborador.append(
                    {
                        "id": colaborador_existente_id,
                        "cpf": candidato.cpf,
                        "pis_nit": candidato.pis,
                        "nome_completo": candidato.nome_completo,
                        "nome_social": candidato.nome_social,
                        "data_admissao": candidato.data_admissao,
                    }
                )
                continue

            chave_cpf = (candidato.empresa_id, candidato.cpf)
            conflito_cpf = existentes_por_cpf.get(chave_cpf)
            if conflito_cpf is not None:
                erros.append(
                    _erro_linha(
                        candidato.numero_linha,
                        "cpf",
                        "PONTO-CONF-001",
                        "CPF ja cadastrado para outra matricula nesta empresa.",
                    )
                )
                continue

            colaborador_id = uuid4()
            novos_colaboradores.append(
                {
                    "id": colaborador_id,
                    "tenant_id": tenant_uuid,
                    "empresa_id": candidato.empresa_id,
                    "matricula": candidato.matricula,
                    "cpf": candidato.cpf,
                    "pis_nit": candidato.pis,
                    "nome_completo": candidato.nome_completo,
                    "nome_social": candidato.nome_social,
                    "status": "ativo",
                    "data_admissao": candidato.data_admissao,
                    "codigo_externo": None,
                }
            )
            existentes_por_matricula[chave_matricula] = colaborador_id
            existentes_por_cpf[chave_cpf] = colaborador_id

            chave_esocial = (candidato.empresa_id, candidato.matricula_esocial)
            if chave_esocial not in vinculos_existentes:
                contrato_id = uuid4()
                novos_contratos.append(
                    {
                        "id": contrato_id,
                        "tenant_id": tenant_uuid,
                        "colaborador_id": colaborador_id,
                        "empresa_id": candidato.empresa_id,
                        "tipo": candidato.tipo_contrato,
                        "regime_jornada": "fixa",
                        "data_inicio": candidato.data_admissao,
                        "controle_jornada": True,
                        "status": "ativo",
                    }
                )
                novos_vinculos.append(
                    {
                        "id": uuid4(),
                        "tenant_id": tenant_uuid,
                        "colaborador_id": colaborador_id,
                        "empresa_id": candidato.empresa_id,
                        "contrato_id": contrato_id,
                        "matricula_esocial": candidato.matricula_esocial,
                        "tipo_vinculo": "empregado",
                        "data_inicio": candidato.data_admissao,
                        "principal": True,
                        "apura_ponto": True,
                        "status": "ativo",
                    }
                )
                vinculos_existentes.add(chave_esocial)
                eventos_admissao.append(
                    construir_envelope_evento(
                        tipo="colaborador.admitido",
                        versao=1,
                        tenant_id=tenant_id,
                        empresa_id=str(candidato.empresa_id),
                        dados={
                            "colaboradorId": str(colaborador_id),
                            "vinculoId": str(novos_vinculos[-1]["id"]),
                            "empresaId": str(candidato.empresa_id),
                            "matricula": candidato.matricula,
                            "matriculaEsocial": candidato.matricula_esocial,
                            "cpf": candidato.cpf,
                            "nomeCompleto": candidato.nome_social or candidato.nome_completo,
                            "dataInicio": candidato.data_admissao.isoformat(),
                            "apuraPonto": True,
                        },
                    )
                )

        if novos_colaboradores:
            await sessao.execute(sa.insert(Colaborador), novos_colaboradores)
        if novos_contratos:
            await sessao.execute(sa.insert(Contrato), novos_contratos)
        if novos_vinculos:
            await sessao.execute(sa.insert(Vinculo), novos_vinculos)
        if atualizacoes_colaborador:
            # UPDATE em lote (um unico `execute()`, parametros repetidos --
            # `executemany` do driver), nao um `await` por colaborador: a
            # fixture roda contra a VPS por tunel SSH, e reprocessar um
            # arquivo em que TODAS as ~5.000 linhas ja existem faria ~5.000
            # idas-e-voltas individuais, estourando o criterio de aceite 7
            # (< 5 min). Mesmo raciocinio do bloco de INSERT acima.
            # "ORM Bulk UPDATE by Primary Key" (SQLAlchemy 2): `sa.update(Colaborador)`
            # sem `.where()` nem `.values()`, com uma lista de dicts contendo
            # `id` mais as colunas a mudar, vira um `executemany` no driver --
            # nao um `await` por colaborador. Sem isto, reprocessar um arquivo
            # em que TODAS as ~5.000 linhas ja existem faria ~5.000
            # idas-e-voltas individuais, estourando o criterio de aceite 7
            # (< 5 min). Mesmo raciocinio do bloco de INSERT acima.
            await sessao.execute(sa.update(Colaborador), atualizacoes_colaborador)

        total_linhas = len(linhas_brutas)
        linhas_erro = len(erros)
        linhas_sucesso = total_linhas - linhas_erro
        importacao.total_linhas = total_linhas
        importacao.linhas_processadas = total_linhas
        importacao.linhas_sucesso = linhas_sucesso
        importacao.linhas_erro = linhas_erro
        importacao.erros = {"linhas": erros} if erros else None
        importacao.status = "concluido" if not erros else "concluido_com_erros"
        importacao.concluido_em = _agora()
        await sessao.commit()

        envelope_conclusao = construir_envelope_evento(
            tipo="importacao.concluida",
            versao=1,
            tenant_id=tenant_id,
            empresa_id=str(importacao.empresa_id) if importacao.empresa_id else None,
            dados={
                "importacaoId": importacao_id,
                "tipo": "colaboradores",
                "status": _STATUS_PARA_EVENTO.get(importacao.status, importacao.status),
                "totalLinhas": total_linhas,
                "linhasSucesso": linhas_sucesso,
                "linhasErro": linhas_erro,
                "relatorioDisponivel": bool(erros),
            },
        )

    duracao_s = time.perf_counter() - inicio
    for evento in eventos_admissao:
        publicar_evento(evento)
    if envelope_conclusao is not None:
        publicar_evento(envelope_conclusao)

    logger.info(
        "importacao de colaboradores concluida",
        extra={
            "importacaoId": importacao_id,
            "totalLinhas": total_linhas,
            "linhasSucesso": linhas_sucesso,
            "linhasErro": linhas_erro,
            "duracaoS": round(duracao_s, 2),
        },
    )

    return {
        "implementado": True,
        "importacaoId": importacao_id,
        "status": importacao.status,
        "totalLinhas": total_linhas,
        "linhasSucesso": linhas_sucesso,
        "linhasErro": linhas_erro,
        "duracaoSegundos": round(duracao_s, 3),
    }
