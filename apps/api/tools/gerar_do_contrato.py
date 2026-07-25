"""Gera codigo da API a partir de `packages/contracts/` (fonte da verdade).

Tres artefatos sao gerados e VERSIONADOS (nao sao gerados em tempo de build):

1. ``app/core/catalogo_erros.py`` -- espelho de ``errors.yaml``. Permite ao
   tratador de erro saber o status HTTP e o titulo estavel de cada codigo sem
   ler YAML em producao.
2. ``app/schemas/contrato.py`` -- modelos Pydantic v2 de todos os
   ``components.schemas`` do ``openapi.yaml``, com campo em ``snake_case`` e
   ``alias`` em ``camelCase`` (convencao da casa: Python snake, JSON camel).
   Produzido por ``datamodel-code-generator``.
3. ``app/routers/<tag>.py`` -- um modulo por tag do OpenAPI, com uma funcao por
   operacao, assinatura fiel ao contrato (parametros de caminho, de consulta,
   cabecalhos e corpo) e corpo que levanta 501 ``PONTO-INT-005``.

Regenerar (a partir de ``apps/api/``, com o venv ativo)::

    pip install -e .[codegen]
    python tools/gerar_do_contrato.py

O script NAO inventa nada: tudo que ele escreve tem origem rastreavel no
contrato. Se o resultado esta errado, o defeito esta no contrato ou aqui --
nunca se corrige o arquivo gerado a mao (a proxima geracao apaga a correcao).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
from typing import Any

import yaml

RAIZ_API = pathlib.Path(__file__).resolve().parents[1]
RAIZ_MONOREPO = RAIZ_API.parents[1]
CONTRATOS = RAIZ_MONOREPO / "packages" / "contracts"
OPENAPI = CONTRATOS / "openapi.yaml"
ERRORS = CONTRATOS / "errors.yaml"

DIR_APP = RAIZ_API / "app"
DIR_ROUTERS = DIR_APP / "routers"
DIR_SCHEMAS = DIR_APP / "schemas"
DIR_CORE = DIR_APP / "core"

CODIGO_NAO_IMPLEMENTADO = "PONTO-INT-005"

# Tag do OpenAPI -> fase de FASES-E-AGENTES.md que implementa a regra de negocio.
# Aparece no `detail` do 501 e no docstring do modulo: quem chama o endpoint
# descobre sozinho quando a operacao entra.
FASE_POR_TAG: dict[str, str] = {
    "auth": "F1",
    "tenants": "F1",
    "empresas": "F2",
    "unidades": "F2",
    "organizacao": "F2",
    "colaboradores": "F2",
    "contratos": "F2",
    "biometria": "F2",
    "dispositivos": "F2",
    "terminais": "F6",
    "jornadas": "F3",
    "escalas": "F3",
    "feriados": "F3",
    "afastamentos": "F3",
    "marcacoes": "F5",
    "comprovantes": "F5",
    "tratamentos": "F4",
    "apuracoes": "F4",
    "banco-horas": "F4",
    "solicitacoes": "F10",
    "aprovacoes": "F10",
    "fechamentos": "F10",
    "espelhos": "F10",
    "relatorios": "F11",
    "fiscal": "F12",
    "webhooks": "F13",
    "integracoes": "F13",
    "auditoria": "F1",
    "lgpd": "F14",
    "admin": "F1",
}

# Operacoes que a Fase 0 implementa de verdade, por serem infraestrutura e nao
# regra de negocio. Ficam FORA da geracao de stub: o modulo correspondente e
# escrito a mao. Toda excecao aqui precisa de justificativa no README da api.
OPERACOES_IMPLEMENTADAS: set[str] = {"obterSaude"}

METODOS_HTTP = ("get", "post", "put", "patch", "delete", "head", "options")


# ---------------------------------------------------------------------------
# Utilidades de nome
# ---------------------------------------------------------------------------
_RE_CAMEL_1 = re.compile(r"(.)([A-Z][a-z]+)")
_RE_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")


def para_snake(nome: str) -> str:
    """`listarColaboradores` -> `listar_colaboradores`; `X-Tenant` -> `x_tenant`."""
    nome = nome.replace("-", "_").replace(".", "_")
    nome = _RE_CAMEL_1.sub(r"\1_\2", nome)
    nome = _RE_CAMEL_2.sub(r"\1_\2", nome)
    # `X-Tenant` vira `X_Tenant` e depois `X__Tenant`: colapsa a duplicidade.
    return re.sub(r"_+", "_", nome).strip("_").lower()


def modulo_da_tag(tag: str) -> str:
    return tag.replace("-", "_")


def literal(texto: str) -> str:
    """Literal Python de string, com aspas duplas e escape seguro."""
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# Leitura do contrato
# ---------------------------------------------------------------------------
def carregar(caminho: pathlib.Path) -> dict[str, Any]:
    dados: dict[str, Any] = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return dados


def resolver_ref(doc: dict[str, Any], ref: str) -> dict[str, Any]:
    alvo: Any = doc
    for parte in ref.lstrip("#/").split("/"):
        alvo = alvo[parte]
    assert isinstance(alvo, dict)
    return alvo


def nome_do_ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# 1. Catalogo de erros
# ---------------------------------------------------------------------------
def gerar_catalogo_erros() -> pathlib.Path:
    doc = carregar(ERRORS)
    erros: list[dict[str, Any]] = doc["erros"]
    categorias: list[dict[str, Any]] = doc["categorias"]

    linhas: list[str] = []
    linhas.append('"""Espelho de `packages/contracts/errors.yaml`. GERADO -- nao editar.')
    linhas.append("")
    linhas.append("Regerar com `python tools/gerar_do_contrato.py`.")
    linhas.append("")
    linhas.append("O catalogo e a fonte da verdade das falhas da API: o backend responde com o")
    linhas.append("`codigo`, e o web e o mobile traduzem o codigo para a mensagem do usuario.")
    linhas.append("Nenhum servico inventa string de erro nem codigo fora desta tabela.")
    linhas.append('"""')
    linhas.append("")
    linhas.append("# ruff: noqa: E501 - tabela de dados: uma entrada por linha e mais legivel")
    linhas.append("")
    linhas.append("from __future__ import annotations")
    linhas.append("")
    linhas.append("from typing import Final, NamedTuple")
    linhas.append("")
    linhas.append(f"VERSAO_CATALOGO: Final[str] = {literal(str(doc['versao']))}")
    linhas.append(f"MEDIA_TYPE_PROBLEMA: Final[str] = {literal(str(doc['media_type']))}")
    linhas.append(f"PREFIXO_TYPE: Final[str] = {literal(str(doc['prefixo_type']))}")
    linhas.append("")
    linhas.append("")
    linhas.append("class EntradaErro(NamedTuple):")
    linhas.append('    """Uma linha do catalogo de erros."""')
    linhas.append("")
    linhas.append("    codigo: str")
    linhas.append("    categoria: str")
    linhas.append("    http_status: int")
    linhas.append("    titulo: str")
    linhas.append("    retentavel: bool")
    linhas.append("    expoe_regra: bool")
    linhas.append("")
    linhas.append("")
    linhas.append("CATEGORIAS: Final[dict[str, str]] = {")
    for cat in categorias:
        linhas.append(f"    {literal(cat['id'])}: {literal(cat['nome'])},")
    linhas.append("}")
    linhas.append("")
    linhas.append("CATALOGO: Final[dict[str, EntradaErro]] = {")
    for erro in erros:
        linhas.append(
            f"    {literal(erro['codigo'])}: EntradaErro("
            f"{literal(erro['codigo'])}, {literal(erro['categoria'])}, "
            f"{int(erro['http_status'])}, {literal(erro['titulo'])}, "
            f"{bool(erro['retentavel'])}, {bool(erro['expoe_regra'])}),"
        )
    linhas.append("}")
    linhas.append("")
    linhas.append("")
    linhas.append("def entrada(codigo: str) -> EntradaErro:")
    linhas.append('    """Devolve a entrada do catalogo, ou levanta KeyError.')
    linhas.append("")
    linhas.append("    KeyError aqui e proposital: codigo fora do catalogo e defeito de")
    linhas.append("    programacao, nao condicao de execucao. Codigo novo entra por RFC")
    linhas.append("    em errors.yaml e so depois aparece aqui.")
    linhas.append('    """')
    linhas.append("    return CATALOGO[codigo]")
    linhas.append("")

    destino = DIR_CORE / "catalogo_erros.py"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"catalogo de erros: {len(erros)} codigos -> {destino.relative_to(RAIZ_API)}")
    return destino


# ---------------------------------------------------------------------------
# 2. Modelos Pydantic
# ---------------------------------------------------------------------------
CABECALHO_SCHEMAS = '''"""Modelos Pydantic v2 de `components.schemas`. GERADO -- nao editar.

Regerar com `python tools/gerar_do_contrato.py` (extra `codegen` instalado).

Convencao da casa: atributo Python em `snake_case`, `alias` JSON em `camelCase`.
`populate_by_name=True` permite construir pelos dois nomes; o FastAPI serializa
resposta por alias, entao o corpo que sai do servidor e camelCase, como o
contrato manda.
"""

'''


def gerar_schemas() -> pathlib.Path:
    destino = DIR_SCHEMAS / "contrato.py"
    comando = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(OPENAPI),
        "--input-file-type",
        "openapi",
        "--openapi-scopes",
        "schemas",
        "--output",
        str(destino),
        "--output-model-type",
        "pydantic_v2.BaseModel",
        "--target-python-version",
        "3.12",
        "--snake-case-field",
        "--allow-population-by-field-name",
        "--use-standard-collections",
        "--use-union-operator",
        "--use-schema-description",
        "--use-field-description",
        "--field-constraints",
        "--use-default",
        "--disable-timestamp",
        "--formatters",
        "black",
        "isort",
    ]
    subprocess.run(comando, check=True)  # noqa: S603 - comando montado aqui

    conteudo = destino.read_text(encoding="utf-8")
    # Substitui o cabecalho automatico por um que explica a origem e a convencao,
    # e desliga lint/tipo estrito no arquivo gerado.
    conteudo = re.sub(r"\A# generated by datamodel-codegen:\n(#.*\n)*", "", conteudo)
    conteudo = CABECALHO_SCHEMAS + "# ruff: noqa\n# mypy: disable-error-code=misc\n" + conteudo
    destino.write_text(conteudo, encoding="utf-8")
    print(f"schemas: -> {destino.relative_to(RAIZ_API)}")
    return destino


# ---------------------------------------------------------------------------
# 3. Routers
# ---------------------------------------------------------------------------
MAPA_FORMATO: dict[tuple[str, str | None], tuple[str, str | None]] = {
    ("string", None): ("str", None),
    ("string", "uuid"): ("UUID", "from uuid import UUID"),
    ("string", "date"): ("date", "from datetime import date"),
    ("string", "date-time"): ("datetime", "from datetime import datetime"),
    ("string", "uri"): ("str", None),
    ("string", "binary"): ("bytes", None),
    ("integer", None): ("int", None),
    ("integer", "int32"): ("int", None),
    ("integer", "int64"): ("int", None),
    ("number", None): ("float", None),
    ("boolean", None): ("bool", None),
}


def tipo_do_schema(doc: dict[str, Any], esquema: dict[str, Any]) -> tuple[str, set[str]]:
    """Traduz um schema de parametro para anotacao Python. Devolve (tipo, imports)."""
    imports: set[str] = set()
    if "$ref" in esquema:
        esquema = resolver_ref(doc, esquema["$ref"])
    tipo = esquema.get("type")
    if isinstance(tipo, list):  # OpenAPI 3.1 aceita lista de tipos
        tipo = next((t for t in tipo if t != "null"), "string")
    formato = esquema.get("format")

    if tipo == "array":
        interno, imports_do_item = tipo_do_schema(doc, esquema.get("items", {"type": "string"}))
        imports |= imports_do_item
        return f"list[{interno}]", imports

    chave = (tipo or "string", formato)
    if chave not in MAPA_FORMATO:
        chave = (tipo or "string", None)
    # Nome proprio para a linha de import: reaproveitar `imports_do_item` aqui
    # trocaria um `set[str]` por um `str | None` e o mypy reprova (com razao).
    anotacao, linha_de_import = MAPA_FORMATO.get(chave, ("str", None))
    if linha_de_import:
        imports.add(linha_de_import)
    return anotacao, imports


class Parametro:
    """Um parametro de operacao ja traduzido para Python."""

    def __init__(
        self,
        *,
        nome_python: str,
        anotacao: str,
        origem: str,
        nome_contrato: str,
        obrigatorio: bool,
        descricao: str,
        padrao: Any,
    ) -> None:
        self.nome_python = nome_python
        self.anotacao = anotacao
        self.origem = origem
        self.nome_contrato = nome_contrato
        self.obrigatorio = obrigatorio
        self.descricao = descricao
        self.padrao = padrao

    def render(self) -> str:
        classe = {"path": "Path", "query": "Query", "header": "Header"}[self.origem]
        argumentos = [f"alias={literal(self.nome_contrato)}"]
        if self.descricao:
            argumentos.append(f"description={literal(self.descricao)}")
        chamada = f"{classe}({', '.join(argumentos)})"
        if self.obrigatorio:
            return f"    {self.nome_python}: Annotated[{self.anotacao}, {chamada}],"
        return f"    {self.nome_python}: Annotated[{self.anotacao} | None, {chamada}] = None,"


def resumir(texto: str, limite: int = 110) -> str:
    """Primeira frase util de uma descricao markdown, em uma linha."""
    plano = " ".join(texto.replace("\n", " ").split())
    if len(plano) > limite:
        # Corta na fronteira de palavra: descricao truncada no meio de uma
        # palavra fica ilegivel no Swagger.
        plano = plano[: limite - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return plano


def primeiras_frases(texto: str, maximo: int = 3) -> list[str]:
    """Primeiras frases inteiras de uma descricao markdown, sem truncar palavra."""
    plano = " ".join(texto.replace("\n", " ").split())
    frases = [f.strip() for f in plano.split(". ") if f.strip()]
    return [f.rstrip(".") + "." for f in frases[:maximo]]


def gerar_routers() -> list[pathlib.Path]:
    doc = carregar(OPENAPI)
    descricao_tag = {t["name"]: t.get("description", "") for t in doc.get("tags", [])}

    por_tag: dict[str, list[tuple[str, str, dict[str, Any], list[dict[str, Any]]]]] = {}
    for caminho, item in doc["paths"].items():
        parametros_comuns = item.get("parameters", [])
        for metodo, operacao in item.items():
            if metodo not in METODOS_HTTP:
                continue
            tag = operacao.get("tags", ["admin"])[0]
            por_tag.setdefault(tag, []).append((metodo, caminho, operacao, parametros_comuns))

    escritos: list[pathlib.Path] = []
    total_operacoes = 0
    total_stubs = 0

    for tag in [t["name"] for t in doc["tags"]]:
        operacoes = por_tag.get(tag, [])
        if not operacoes:
            continue
        fase = FASE_POR_TAG.get(tag, "?")
        imports_extra: set[str] = set()
        corpo_modulo: list[str] = []

        for metodo, caminho, operacao, parametros_comuns in operacoes:
            operation_id = operacao["operationId"]
            total_operacoes += 1
            if operation_id in OPERACOES_IMPLEMENTADAS:
                continue
            total_stubs += 1

            # --- parametros -------------------------------------------------
            parametros: list[Parametro] = []
            vistos: set[str] = set()
            for bruto in list(parametros_comuns) + list(operacao.get("parameters", [])):
                definicao = resolver_ref(doc, bruto["$ref"]) if "$ref" in bruto else bruto
                origem = definicao["in"]
                if origem not in ("path", "query", "header"):
                    continue
                nome_contrato = definicao["name"]
                nome_python = para_snake(nome_contrato)
                if nome_python in vistos:
                    continue
                vistos.add(nome_python)
                anotacao, imps = tipo_do_schema(doc, definicao.get("schema", {}))
                imports_extra |= imps
                parametros.append(
                    Parametro(
                        nome_python=nome_python,
                        anotacao=anotacao,
                        origem=origem,
                        nome_contrato=nome_contrato,
                        obrigatorio=bool(definicao.get("required", origem == "path")),
                        descricao=resumir(definicao.get("description", ""), 160),
                        padrao=definicao.get("schema", {}).get("default"),
                    )
                )

            # --- corpo ------------------------------------------------------
            linha_corpo: str | None = None
            requisicao = operacao.get("requestBody")
            if requisicao:
                conteudo = requisicao.get("content", {}).get("application/json", {})
                ref = conteudo.get("schema", {}).get("$ref")
                if ref:
                    linha_corpo = f"    corpo: contrato.{nome_do_ref(ref)},"
                else:
                    linha_corpo = "    corpo: Annotated[dict[str, Any], Body()],"
                    imports_extra.add("from typing import Any")

            # --- resposta ---------------------------------------------------
            codigos_ok = sorted(
                c for c in operacao.get("responses", {}) if c.isdigit() and c.startswith("2")
            )
            status_ok = int(codigos_ok[0]) if codigos_ok else 200
            resposta = operacao["responses"].get(codigos_ok[0]) if codigos_ok else None
            anotacao_retorno = "Response"
            extra_decorador = ["response_class=Response"]
            if resposta:
                conteudo = (resposta.get("content") or {}).get("application/json", {})
                ref = conteudo.get("schema", {}).get("$ref")
                if ref:
                    anotacao_retorno = f"contrato.{nome_do_ref(ref)}"
                    extra_decorador = []

            # --- decorador --------------------------------------------------
            argumentos = [
                literal(caminho),
                f"status_code={status_ok}",
                f"operation_id={literal(operation_id)}",
                f"summary={literal(resumir(operacao.get('summary', operation_id)))}",
                "responses=RESPOSTAS_PADRAO",
                *extra_decorador,
            ]
            corpo_modulo.append(f"@roteador.{metodo}(")
            for argumento in argumentos:
                corpo_modulo.append(f"    {argumento},")
            corpo_modulo.append(")")
            corpo_modulo.append(f"async def {para_snake(operation_id)}(")
            obrigatorios = [p for p in parametros if p.obrigatorio]
            opcionais = [p for p in parametros if not p.obrigatorio]
            for parametro in obrigatorios:
                corpo_modulo.append(parametro.render())
            if linha_corpo:
                corpo_modulo.append(linha_corpo)
            for parametro in opcionais:
                corpo_modulo.append(parametro.render())
            corpo_modulo.append(f") -> {anotacao_retorno}:")
            resumo = resumir(operacao.get("summary", operation_id), 88)
            corpo_modulo.append(f'    """{resumo}')
            corpo_modulo.append("")
            corpo_modulo.append(
                f"    Fase 0 entrega andaime: a implementacao entra na fase {fase}."
            )
            corpo_modulo.append('    """')
            corpo_modulo.append(
                f"    raise NaoImplementado({literal(operation_id)}, fase={literal(fase)})"
            )
            corpo_modulo.append("")
            corpo_modulo.append("")

        if not corpo_modulo:
            continue

        # --- cabecalho do modulo -------------------------------------------
        cabecalho: list[str] = []
        cabecalho.append(f'"""Rotas da tag `{tag}` do contrato. GERADO -- nao editar.')
        cabecalho.append("")
        cabecalho.extend(primeiras_frases(descricao_tag.get(tag, ""), 3))
        cabecalho.append("")
        cabecalho.append(
            f"Regra de negocio destas operacoes entra na fase {fase}. Ate la toda chamada"
        )
        cabecalho.append(f"responde 501 com {CODIGO_NAO_IMPLEMENTADO}. Regerar com")
        cabecalho.append("`python tools/gerar_do_contrato.py`.")
        cabecalho.append('"""')
        cabecalho.append("")
        cabecalho.append("from __future__ import annotations")
        cabecalho.append("")
        cabecalho.append("from typing import Annotated")
        for imp in sorted(imports_extra):
            cabecalho.append(imp)
        cabecalho.append("")
        elementos_fastapi = ["APIRouter", "Header", "Path", "Query", "Response"]
        if any("Body()" in linha for linha in corpo_modulo):
            elementos_fastapi.append("Body")
        cabecalho.append(f"from fastapi import {', '.join(sorted(set(elementos_fastapi)))}")
        cabecalho.append("")
        cabecalho.append("from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado")
        cabecalho.append("from app.schemas import contrato")
        cabecalho.append("")
        cabecalho.append(f"roteador = APIRouter(tags=[{literal(tag)}])")
        cabecalho.append("")
        cabecalho.append("")

        destino = DIR_ROUTERS / f"{modulo_da_tag(tag)}.py"
        destino.write_text("\n".join(cabecalho + corpo_modulo).rstrip() + "\n", encoding="utf-8")
        escritos.append(destino)

    print(
        f"routers: {len(escritos)} modulos, {total_operacoes} operacoes do contrato, "
        f"{total_stubs} stubs 501, "
        f"{len(OPERACOES_IMPLEMENTADAS)} implementada(s) a mao"
    )
    return escritos


def formatar_com_ruff(caminhos: list[pathlib.Path]) -> None:
    """Ordena imports e formata o codigo gerado, para o CI nao reprovar depois.

    Se o ruff nao estiver instalado (extra `codegen` sem o extra `dev`), o passo
    e pulado com aviso -- gerar continua funcionando, so nao sai formatado.
    """
    if not caminhos:
        return
    alvos = [str(c) for c in caminhos]
    try:
        subprocess.run(  # noqa: S603 - comando montado aqui
            [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", *alvos],
            check=False,
        )
        subprocess.run(  # noqa: S603 - comando montado aqui
            [sys.executable, "-m", "ruff", "format", "--quiet", *alvos],
            check=True,
        )
        print(f"ruff: {len(alvos)} arquivo(s) formatado(s)")
    except FileNotFoundError:
        print("ruff ausente: pule a formatacao (pip install -e .[dev])", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sem-schemas", action="store_true", help="pula o datamodel-codegen")
    argumentos = parser.parse_args()

    if not OPENAPI.exists():
        print(f"contrato ausente: {OPENAPI}", file=sys.stderr)
        return 1

    gerados = [gerar_catalogo_erros()]
    if not argumentos.sem_schemas:
        gerar_schemas()  # ja sai formatado pelo black/isort do datamodel-codegen
    gerados += gerar_routers()
    formatar_com_ruff(gerados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
