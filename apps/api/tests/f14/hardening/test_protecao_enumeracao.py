"""A2 -- proteção contra enumeração (PCF F14 §5: "IDs sequenciais expostos,
mensagem de erro que confirma existência de recurso a um não-autorizado").

**Achado (auditoria desta fase, não um bug corrigido -- o sistema já nasceu
protegido nesta frente por decisão de F1).** Duas defesas estruturais já
existem e este arquivo as transforma em gate de regressão:

1. **Nenhum identificador de recurso é sequencial.** Todo `{xxxId}` de path
   no contrato é UUID v4 (128 bits aleatórios, não adivinhável por
   incremento). As únicas exceções são parâmetros que não são identificador
   de recurso sensível: `provedor` (enum fixo de SSO), `chave`
   (configuração, catálogo), `codigo` (catálogo de relatórios). `nsrDe`/
   `nsrAte` (query, `/v1/marcacoes`) SÃO inteiros sequenciais por exigência
   legal da Portaria MTP 671/2021 (NSR precisa ser verificável em faixa) --
   não é uma falha, é o requisito; permanecem atrás de `exigir_permissao`,
   nunca acessíveis sem autenticação.
2. **RLS torna "não existe" e "existe em outro tenant" indistinguíveis.**
   Toda consulta por ID que NÃO filtra `tenant_id` explicitamente (o padrão
   dominante no código -- `app.pessoas.colaboradores.obter_colaborador` é um
   exemplo típico) ainda assim só enxerga linhas do tenant corrente, porque a
   policy `pol_isolamento_tenant` filtra ANTES da aplicação decidir
   "encontrado"/"não encontrado" -- um UUID de outro tenant e um UUID que
   nunca existiu produzem o MESMO `404 PONTO-REC-001`, sem side-channel de
   timing nem de código de erro diferente.

**Achado NÃO corrigido, registrado no backlog (fora do ownership de A2 --
`app/marcacao/**` é território de A1/F5).**
`app.marcacao.comprovantes.consulta.listar_comprovantes_recentes` verifica
existência do colaborador (404 se ausente) ANTES de `exigir_alcance` (403 se
fora do alcance hierárquico do gestor/RH chamador) -- um usuário autenticado
com escopo restrito consegue distinguir "este UUID de colaborador existe
neste tenant, mas fora do meu alcance" (403) de "não existe" (404). É o
único uso de `exigir_alcance` no sistema hoje (`grep -rn exigir_alcance
app/`), então o achado é específico deste ponto, não um padrão espalhado.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_RAIZ_REPO = Path(__file__).resolve().parents[5]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

#: Parâmetros de path que, por desenho, não são identificador UUID de um
#: recurso sensível (ver docstring do módulo, item 1). Lista fechada: um
#: parâmetro novo fora desta lista e sem `format: uuid` reprova o teste --
#: é assim que este arquivo funciona como gate de regressão.
_EXCECOES_PARAMETRO_NAO_UUID = frozenset(
    {
        ("/v1/sso/{provedor}/iniciar", "provedor"),
        ("/v1/sso/{provedor}/callback", "provedor"),
        ("/v1/tenants/{tenantId}/configuracoes/{chave}", "chave"),
        ("/v1/relatorios/{codigo}", "codigo"),
        ("/v1/relatorios/{codigo}/executar", "codigo"),
    }
)

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")


def _parametros_de_path_do_contrato() -> list[tuple[str, str, dict[str, object]]]:
    documento = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    achados: list[tuple[str, str, dict[str, object]]] = []
    for caminho, item in documento["paths"].items():
        parametros_do_path = item.get("parameters", []) or []
        for metodo, operacao in item.items():
            if metodo not in _METODOS or not isinstance(operacao, dict):
                continue
            for parametro in parametros_do_path + (operacao.get("parameters", []) or []):
                if parametro.get("in") != "path":
                    continue
                achados.append(
                    (caminho, parametro.get("name", ""), parametro.get("schema", {}) or {})
                )
    return achados


def test_todo_identificador_de_recurso_no_path_e_uuid_nao_sequencial() -> None:
    """Gate de regressão: nenhum `{xxxId}` de path pode virar inteiro
    sequencial (ou qualquer formato adivinhável) sem uma decisão consciente
    -- adicionar a exceção aqui exige justificar por quê o recurso não é
    sensível a enumeração, mesmo padrão de `_EXCECOES_PARAMETRO_NAO_UUID`."""
    infratores: list[tuple[str, str, dict[str, object]]] = []
    for caminho, nome, schema in _parametros_de_path_do_contrato():
        if (caminho, nome) in _EXCECOES_PARAMETRO_NAO_UUID:
            continue
        if schema.get("format") != "uuid":
            infratores.append((caminho, nome, schema))

    assert infratores == [], (
        "Parametro(s) de path que identificam recurso sem ser UUID (risco de "
        f"enumeracao por ID previsivel): {infratores}. Se for legitimo, "
        "adicione a `_EXCECOES_PARAMETRO_NAO_UUID` com justificativa."
    )


def test_nenhuma_operacao_de_path_com_id_declara_formato_inteiro() -> None:
    """Reforço direto do critério de aceite ("IDs sequenciais expostos"):
    nenhum parâmetro cujo NOME termina em `Id` (convenção do contrato para
    identificador de recurso) pode ser `type: integer`."""
    infratores = [
        (caminho, nome, schema)
        for caminho, nome, schema in _parametros_de_path_do_contrato()
        if nome.endswith("Id") and schema.get("type") == "integer"
    ]
    assert infratores == [], f"Identificador de recurso declarado como inteiro: {infratores}"
