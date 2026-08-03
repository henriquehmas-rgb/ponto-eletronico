"""Orquestração do importador de AFD de terceiro (F13/A8, T19).

Dois pontos de entrada:

- `resolver_rep_p_alvo` -- síncrona, chamada pelo router (`app.integracoes.
  importadores.servico.criar_importacao`) NA CRIAÇÃO da importação, antes de
  enfileirar. Resolve qual REP-P recebe as marcações importadas e falha
  cedo (`PONTO-REC-001`/`PONTO-VAL-001`) se a empresa não tiver exatamente
  um REP-P ativo e nenhum `parametros.repPId` explícito.
- `processar_arquivo` -- chamada pelo worker
  (`apps/worker/worker/tarefas/integracoes.py::importar_arquivo_generico`).
  Lê o AFD, valida linha a linha, monta e insere as marcações em lote, e
  devolve um resumo para o chamador persistir em `importacoes` e publicar o
  evento `importacao.concluida`. NÃO COMMITA -- quem abre a sessão decide
  quando (mesmo padrão documentado por `app.fiscal.afd.gerador.
  gerar_afd_arquivo`).

## Decisão documentada: `marcacoes.rep_p_id` aponta para o REP-P REAL da
empresa, não para um marcador dedicado

O PCF F13 (critério de aceite 8) autoriza qualquer uma das duas opções,
"desde que `nsr_emissoes` ... nunca ganhe uma linha correspondente". Esta
implementação escolhe o REP-P real, por quatro razões:

1. **O mecanismo de isolamento já é `canal='importacao'` + ausência em
   `nsr_emissoes`, não o `rep_p_id`.** O comentário da própria coluna
   `marcacoes.canal` (schema.sql) diz: "importacao identifica marcacao vinda
   de AFD de terceiro, que usa namespace de NSR proprio" -- não menciona
   REP-P separado. E o gerador de AFD da F12
   (`app.fiscal.afd.gerador._consultar_marcacoes_do_periodo`) já filtra
   `Marcacao.canal != "importacao"` como defesa em profundidade, com o
   comentário explícito "mesmo que hoje nao existam linhas com esse canal"
   -- ou seja, o próprio F12 já antecipava este importador escrevendo no
   MESMO REP-P.
2. **O verificador de continuidade de NSR** (`GET /v1/marcacoes/nsr/
   verificar`, `app.marcacao.dominio.verificacao_nsr`) só lê `nsr_emissoes`
   -- nunca `marcacoes` diretamente para a prova de sequência. Como este
   módulo nunca escreve em `nsr_emissoes`, a marcação importada é invisível
   para aquele verificador **independente** do `rep_p_id` escolhido.
3. **Um REP-P marcador fabricado exigiria dados falsos** em colunas `NOT
   NULL`/`CHECK` de `rep_ps` (`numero_inpi` no formato `^[0-9]+$`,
   `cnpj_desenvolvedor`, `cnpj_empregador`, ...) só para existir, e passaria
   a aparecer em `GET /v1/fiscal/rep-ps` como se fosse um REP-P real da
   empresa -- pior higiene de dado que reaproveitar o REP-P que já existe.
4. `marcacoes.rep_p_id` é `NOT NULL` e `REFERENCES rep_ps(id)`: o REP-P real
   da empresa é a referência mais honesta para "este fato de ponto aconteceu
   nesta empresa", mesmo tendo sido registrado por outro software na época.

## Decisão documentada: fórmula de `crc16`/`hash_registro`/`hash_anterior`

Ver `cadeia.py` -- fórmula própria, deliberadamente distinta da de
`app.marcacao.dominio.nsr` (usada por F5 para as NOSSAS marcações), nas
três dimensões descritas naquele módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import Colaborador, Importacao, Marcacao, RepP, Vinculo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.importadores.afd_terceiro import cadeia
from app.integracoes.importadores.afd_terceiro.leiaute import CampoDhInvalido, parsear_dh
from app.integracoes.importadores.afd_terceiro.parser import (
    ArquivoAfdInvalido,
    RegistroTipo7Bruto,
    ler_arquivo_afd,
)

__all__ = [
    "ArquivoAfdInvalido",
    "ResultadoProcessamento",
    "processar_arquivo",
    "resolver_rep_p_alvo",
]

#: Fuso fixo assumido para marcações importadas: quase todo AFD de REP-P em
#: operação no Brasil está em horário de Brasília, e o Brasil não tem
#: horário de verão desde 2019 (mesma simplificação documentada que F12 usa
#: em `_FUSO_PADRAO`, `app.fiscal.afd.gerador`). `dom_fuso` exige o formato
#: `Regiao/Cidade` (schema.sql linha 106): um offset numérico cru do campo
#: `DH` não seria aceito pela coluna mesmo se quiséssemos gravá-lo.
_FUSO_ASSUMIDO = "America/Sao_Paulo"


# =============================================================================
# Validação de CPF (cópia deliberada do algoritmo já usado por
# `apps/worker/worker/tarefas/importacoes.py`/`apps/api/app/comum/
# documentos.py` -- mesmo algoritmo, mesma fonte (Receita Federal, módulo
# 11); duplicado aqui porque este módulo não deve depender do módulo de
# import de colaboradores de outro agente/fase para uma checagem tão
# pequena, mesmo padrão de duplicação já estabelecido neste projeto entre
# `apps/api` e `apps/worker`.)
# =============================================================================
def _sequencia_repetida(digitos: str) -> bool:
    return len(set(digitos)) == 1


def _digito_modulo_11(digitos: str, pesos: list[int]) -> int:
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or not digitos.isdigit() or _sequencia_repetida(digitos):
        return False
    dv1 = _digito_modulo_11(digitos[:9], list(range(10, 1, -1)))
    dv2 = _digito_modulo_11(digitos[:9] + str(dv1), list(range(11, 1, -1)))
    return digitos[-2:] == f"{dv1}{dv2}"


def _extrair_cpf(campo_12: str) -> str | None:
    """Campo N de 12 posições (docs/leiaute-afd-aej.md, tipos 3/5/7): CPF
    brasileiro tem 11 dígitos, então o campo tem 1 dígito de padding a mais
    -- zero à esquerda, prática de mercado (docs/leiaute-afd-aej.md §6
    regra 7). Os últimos 11 dígitos são o CPF."""
    if not campo_12.isdigit():
        return None
    return campo_12[-11:]


def _erro_linha(numero_linha: int, campo: str, codigo: str, mensagem: str) -> dict[str, Any]:
    return {"linha": numero_linha, "campo": campo, "codigo": codigo, "mensagem": mensagem}


# =============================================================================
# Resolução do REP-P alvo (síncrona, chamada na criação da importação)
# =============================================================================
async def resolver_rep_p_alvo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    rep_p_id_informado: UUID | None,
) -> UUID:
    """Resolve o REP-P que recebe as marcações desta importação. Ver
    docstring do módulo para a decisão sobre por que é o REP-P real, não um
    marcador dedicado."""
    if rep_p_id_informado is not None:
        rep_p = await sessao.get(RepP, rep_p_id_informado)
        if (
            rep_p is None
            or rep_p.tenant_id != tenant_id
            or rep_p.empresa_id != empresa_id
            or rep_p.excluido_em is not None
        ):
            raise ErroDeAplicacao(
                "PONTO-REC-001",
                detalhe="parametros.repPId nao encontrado para esta empresa.",
                contexto_log={"repPId": str(rep_p_id_informado)},
            )
        return rep_p.id

    resultado = await sessao.execute(
        sa.select(RepP.id).where(
            RepP.tenant_id == tenant_id,
            RepP.empresa_id == empresa_id,
            RepP.status == "ativo",
            RepP.excluido_em.is_(None),
        )
    )
    candidatos = resultado.scalars().all()
    if not candidatos:
        raise ErroDeAplicacao(
            "PONTO-REC-001",
            detalhe=(
                "Nenhum REP-P ativo cadastrado para esta empresa. Cadastre um REP-P "
                "antes de importar um AFD de terceiro."
            ),
            contexto_log={"empresaId": str(empresa_id)},
        )
    if len(candidatos) > 1:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=(
                "Mais de um REP-P ativo para esta empresa; informe parametros.repPId "
                "explicitamente para desambiguar."
            ),
            contexto_log={"empresaId": str(empresa_id), "candidatos": len(candidatos)},
        )
    return candidatos[0]


# =============================================================================
# Processamento (worker)
# =============================================================================
@dataclass(slots=True)
class ResultadoProcessamento:
    total_linhas_tipo7: int
    linhas_sucesso: int
    linhas_erro: int
    erros: list[dict[str, Any]] = field(default_factory=list)
    linhas_ignoradas: int = 0


async def _carregar_colaboradores_por_cpf(
    sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID, cpfs: set[str]
) -> dict[str, UUID]:
    if not cpfs:
        return {}
    resultado = await sessao.execute(
        sa.select(Colaborador.cpf, Colaborador.id).where(
            Colaborador.tenant_id == tenant_id,
            Colaborador.empresa_id == empresa_id,
            Colaborador.cpf.in_(cpfs),
            Colaborador.excluido_em.is_(None),
        )
    )
    return dict(resultado.tuples().all())


async def _carregar_vinculos_ativos(
    sessao: AsyncSession, *, tenant_id: UUID, colaborador_ids: set[UUID]
) -> dict[UUID, UUID]:
    """`colaborador_id -> vinculo_id` do vínculo `apura_ponto=true` e
    `status='ativo'` mais recente (por `data_inicio`) de cada colaborador --
    mesmo critério de "vínculo principal ativo" que outras fases já usam
    para associar uma marcação a um vínculo."""
    if not colaborador_ids:
        return {}
    resultado = await sessao.execute(
        sa.select(Vinculo.colaborador_id, Vinculo.id, Vinculo.data_inicio)
        .where(
            Vinculo.tenant_id == tenant_id,
            Vinculo.colaborador_id.in_(colaborador_ids),
            Vinculo.apura_ponto.is_(True),
            Vinculo.status == "ativo",
            Vinculo.excluido_em.is_(None),
        )
        .order_by(Vinculo.colaborador_id, Vinculo.data_inicio.desc())
    )
    mapa: dict[UUID, UUID] = {}
    for colaborador_id, vinculo_id, _data_inicio in resultado.all():
        mapa.setdefault(colaborador_id, vinculo_id)
    return mapa


def _validar_e_montar(
    registro: RegistroTipo7Bruto,
) -> tuple[dict[str, Any], None] | tuple[None, dict[str, Any]]:
    """Valida o CONTEÚDO de um registro tipo 7 já estruturalmente reconhecido
    pelo parser. Devolve `(campos_validos, None)` ou `(None, erro_linha)` --
    NUNCA levanta: uma linha ruim vira item do relatório, não aborta o
    arquivo (mesmo padrão de `worker/tarefas/importacoes.py`, F2)."""
    try:
        nsr_origem = int(registro.nsr_origem_bruto)
    except ValueError:
        return None, _erro_linha(
            registro.numero_linha, "nsr", "PONTO-IMP-003", "NSR do registro nao e numerico."
        )
    if nsr_origem < 1:
        return None, _erro_linha(
            registro.numero_linha, "nsr", "PONTO-IMP-003", "NSR do registro deve ser >= 1."
        )

    cpf = _extrair_cpf(registro.cpf_bruto)
    if cpf is None or not _cpf_valido(cpf):
        return None, _erro_linha(
            registro.numero_linha, "cpf", "PONTO-VAL-002", "CPF invalido no registro importado."
        )

    try:
        datahora_marcacao = parsear_dh(registro.datahora_marcacao_bruta)
    except CampoDhInvalido as exc:
        return None, _erro_linha(
            registro.numero_linha,
            "datahoraMarcacao",
            "PONTO-IMP-003",
            f"Data/hora de marcacao ilegivel: {exc}",
        )
    try:
        datahora_gravacao = parsear_dh(registro.datahora_gravacao_bruta)
    except CampoDhInvalido as exc:
        return None, _erro_linha(
            registro.numero_linha,
            "datahoraGravacao",
            "PONTO-IMP-003",
            f"Data/hora de gravacao ilegivel: {exc}",
        )

    return (
        {
            "nsr_origem": nsr_origem,
            "cpf": cpf,
            "datahora_marcacao": datahora_marcacao,
            "datahora_gravacao": datahora_gravacao,
            "coletada_offline": not registro.online,
            "linha_bruta": registro.linha_bruta,
            "numero_linha": registro.numero_linha,
        },
        None,
    )


async def processar_arquivo(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID,
    rep_p_id: UUID,
    importacao: Importacao,
    conteudo: bytes,
) -> ResultadoProcessamento:
    """Lê `conteudo` (bytes brutos do AFD, como veio do armazenamento de
    objetos), valida e insere as marcações importadas em lote. NÃO commita.

    Falha ESTRUTURAL do arquivo inteiro (`ArquivoAfdInvalido`, ver
    `parser.py`) propaga para o chamador -- quem chama decide como isso vira
    `importacoes.status='falhou'` (o worker, ver `apps/worker/worker/
    tarefas/integracoes.py::importar_arquivo_generico`).
    """
    arquivo = ler_arquivo_afd(conteudo)  # propaga ArquivoAfdInvalido

    validos: list[dict[str, Any]] = []
    erros: list[dict[str, Any]] = []
    for registro in arquivo.registros_tipo7:
        campos, erro = _validar_e_montar(registro)
        if erro is not None:
            erros.append(erro)
        else:
            # `_validar_e_montar` devolve exatamente um dos dois não-None
            # (união discriminada) -- assert de estreitamento de tipo para
            # o mypy, nunca uma checagem de segurança (por isso o noqa).
            assert campos is not None  # noqa: S101
            validos.append(campos)

    cpfs = {c["cpf"] for c in validos}
    colaboradores_por_cpf = await _carregar_colaboradores_por_cpf(
        sessao, tenant_id=tenant_id, empresa_id=empresa_id, cpfs=cpfs
    )
    vinculos_por_colaborador = await _carregar_vinculos_ativos(
        sessao, tenant_id=tenant_id, colaborador_ids=set(colaboradores_por_cpf.values())
    )

    linhas_para_inserir: list[dict[str, Any]] = []
    hash_anterior: str | None = None
    for campos in validos:
        colaborador_id = colaboradores_por_cpf.get(campos["cpf"])
        vinculo_id = (
            vinculos_por_colaborador.get(colaborador_id) if colaborador_id is not None else None
        )

        canonico = cadeia.canonicalizar_registro_importado(
            importacao_id=importacao.id,
            nsr_origem=campos["nsr_origem"],
            cpf=campos["cpf"],
            tipo_registro="7",
            datahora_marcacao=campos["datahora_marcacao"],
            linha_bruta=campos["linha_bruta"],
        )
        hash_registro = cadeia.calcular_hash_importado(canonico, hash_anterior)
        crc16 = cadeia.crc16_do_registro_importado(campos["linha_bruta"])

        linhas_para_inserir.append(
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "rep_p_id": rep_p_id,
                "empresa_id": empresa_id,
                "unidade_id": None,
                "colaborador_id": colaborador_id,
                "vinculo_id": vinculo_id,
                # NUNCA alocado por `app.marcacao.dominio.nsr.alocar_nsr`:
                # este e o NSR HISTORICO do arquivo de origem, nao um valor
                # que participa de `nsr_sequencias`/`nsr_emissoes` (ADR-003
                # item 6, critério de aceite 4/8 do PCF F13).
                "nsr": campos["nsr_origem"],
                "tipo_registro": "7",
                "sentido_informado": None,
                "cpf": campos["cpf"],
                "pis_nit": None,
                "datahora_marcacao": campos["datahora_marcacao"],
                "datahora_gravacao": campos["datahora_gravacao"],
                "datahora_dispositivo": None,
                "fuso_horario": _FUSO_ASSUMIDO,
                "canal": "importacao",
                "dispositivo_id": None,
                "terminal_id": None,
                "external_id": None,
                "log_externo_id": None,
                "idempotency_key": None,
                "origem_importacao_id": importacao.id,
                "crc16": crc16,
                "hash_anterior": hash_anterior,
                "hash_registro": hash_registro,
                # Linha ORIGINAL do arquivo de terceiro (auditoria/proveniencia)
                # -- nunca uma linha que NOS geraríamos no nosso proprio
                # formato de AFD (este importador nao gera AFD).
                "linha_afd": campos["linha_bruta"],
                "coletada_offline": campos["coletada_offline"],
                "criado_por": importacao.criado_por,
            }
        )
        hash_anterior = hash_registro

    if linhas_para_inserir:
        await sessao.execute(sa.insert(Marcacao), linhas_para_inserir)

    return ResultadoProcessamento(
        total_linhas_tipo7=len(arquivo.registros_tipo7),
        linhas_sucesso=len(linhas_para_inserir),
        linhas_erro=len(erros),
        erros=erros,
        linhas_ignoradas=len(arquivo.linhas_ignoradas),
    )
