"""Layout de largura fixa do arquivo de movimento (MOV.DP) do Alterdata
Departamento Pessoal, parceiro `alterdata` (F13/A5, T16).

**Fonte primaria, lida nesta sessao de build (03/08/2026)**, alem da
pesquisa de mercado que o PCF ja cita:

- https://ajuda.alterdata.com.br/dpbase/como-importar-arquivo-de-movimento-em-lancamento-por-funcionarios-105422961.html
  ("Como importar arquivo de movimento em Lançamento por funcionários",
  Base de Conhecimento Alterdata Departamento Pessoal) -- tabela completa
  de posicao de campo do arquivo, largura fixa.
- Confirmacao cruzada por busca (03/08/2026): "colunas 62 a 75 ... CNPJ ou
  CPF da Empresa" e "colunas 76 a 86 ... PIS do Funcionario", ambos campos
  OPCIONAIS quando o codigo interno (empresa/funcionario) ja resolve o
  vinculo -- este exportador preenche os dois de qualquer forma (dado ja
  disponivel, sem custo) para maximizar a chance de casar o registro do
  lado do Alterdata.

As posicoes 1-90 abaixo batem, campo a campo, com as que o PCF ja cita em
T16 ("Sequencial 1-6, Codigo Empresa 7-11, datas 12-23, Faltas 24-29,
Horas Trabalhadas 30-35, Codigo Evento 38-40, Valor Evento 41-54, Codigo
Funcionario 55-60, CNPJ/CPF 62-75, PIS 76-86, Departamento 87-90"). A
fonte primaria acrescenta dois campos que o PCF nao detalhou por nome
(Dias Uteis 36-37, Processo 61) e confirma tamanho/decimais de Valor
Evento (14 digitos, 2 casas decimais implicitas -- sem separador). Os
campos 91-128 da mesma pagina (CNPJ da Operadora, Codigo do Plano, Codigo/
CPF do Beneficiario, Forma de Apuracao) sao do modulo de MOVIMENTO DE
BENEFICIOS (plano de saude) da MESMA familia de layout generico
"movimento por funcionario", nao de ponto eletronico -- fora do escopo
deste exportador, que termina na posicao 90 (Departamento), mesmo corte
que o PCF ja fazia.

**O que esta verificado (criterio de aceite 3 da fase, alcancado de
verdade para este parceiro): a POSICAO de cada campo** -- `test_layout.py`
confere cada campo pela posicao exata contra a tabela abaixo, nao so
"arquivo nao quebra".

**O que NAO esta confirmado contra documentacao de negocio do fabricante:
como varias ocorrencias de rubrica por colaborador/dia se combinam em um
unico arquivo de movimento.** A pagina fonte descreve layout de coluna, nao
regra de agregacao por evento/periodo. A decisao desta implementacao --
cada `LinhaApuracaoFolha` (ja granular por vinculo x dia x componente de
apuracao) vira exatamente UM registro de 90 posicoes -- e extrapolacao
documentada, nao confirmada. Mapeamento campo a campo:

- **1-6 Sequencial**: numero sequencial da linha no arquivo (1..N).
- **7-11 Codigo Empresa**: `configuracao.codigoEmpresa`; obrigatorio na
  integracao, sem ele `PONTO-VAL-001`.
- **12-17 Referencia 1 (DDMMAA)**: `linha.data`.
- **18-23 Referencia 2 (DDMMAA)**: `linha.data` -- mesmo dia (registro de
  um unico dia, nao um intervalo; extrapolacao).
- **24-29 Faltas (minutos)**: `linha.minutos` quando `categoria ==
  'falta'`, senao 0.
- **30-35 Horas Trabalhadas**: `linha.minutos_equivalentes` quando
  `categoria != 'falta'`, senao 0 (extrapolacao: fonte nao diz se e
  minutos brutos ou equivalentes).
- **36-37 Dias Uteis**: `01` fixo (extrapolacao: cada registro representa
  um dia).
- **38-40 Codigo Evento**: rubrica resolvida via
  `mapeamento_rubricas[componenteCodigo]`, ou `000` quando nao mapeada;
  precisa ser numerico de ate 3 digitos.
- **41-54 Valor Evento**: horas decimais (`minutos_equivalentes / 60`) com
  2 casas decimais implicitas, sem separador (extrapolacao: fonte
  confirma tamanho/decimais, nao a unidade).
- **55-60 Codigo Funcionario**: `linha.matricula` (precisa ser numerica);
  `PONTO-VAL-001` quando nao e.
- **61 Processo**: espaco em branco (nao modelado neste sistema).
- **62-75 CNPJ ou CPF da Empresa**: `linha.empresa_cnpj` (14 digitos);
  campo opcional na fonte, preenchido mesmo assim.
- **76-86 PIS do Funcionario**: `linha.pis_nit`, ou `0` repetido quando
  ausente.
- **87-90 Departamento do Funcionario**: `linha.departamento_codigo`
  quando numerico, senao `0000` (nosso `departamentos.codigo` e texto
  livre, nem sempre numerico).
"""

from __future__ import annotations

import datetime as dt

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.comum.protocolo import ArquivoFolhaGerado, ContextoExportacaoFolha
from app.integracoes.folha.comum.rubricas import resolver_rubrica

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

_QUEBRA_LINHA = "\r\n"

#: Posicoes 1-indexadas inclusive, exatamente como a fonte documenta.
#: `test_layout.py` confere cada uma contra o registro gerado.
CAMPOS: dict[str, tuple[int, int]] = {
    "sequencial": (1, 6),
    "codigo_empresa": (7, 11),
    "referencia_1": (12, 17),
    "referencia_2": (18, 23),
    "faltas": (24, 29),
    "horas_trabalhadas": (30, 35),
    "dias_uteis": (36, 37),
    "codigo_evento": (38, 40),
    "valor_evento": (41, 54),
    "codigo_funcionario": (55, 60),
    "processo": (61, 61),
    "cnpj_cpf_empresa": (62, 75),
    "pis_funcionario": (76, 86),
    "departamento": (87, 90),
}
TAMANHO_REGISTRO: int = 90


def _campo_numerico(
    valor: str, largura: int, *, nome_campo: str, permite_vazio: bool = False
) -> str:
    """Formata `valor` como campo numerico zero-padded de `largura`
    posicoes. Levanta `PONTO-VAL-001` quando `valor` nao e numerico ou
    excede a largura -- nunca trunca nem inventa digito."""
    limpo = (valor or "").strip()
    if not limpo:
        if permite_vazio:
            return "0".zfill(largura)
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe=f"Layout Alterdata: {nome_campo} ausente."
        )
    if not limpo.isdigit():
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=f"Layout Alterdata: {nome_campo} precisa ser numerico; recebido {valor!r}.",
        )
    if len(limpo) > largura:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=f"Layout Alterdata: {nome_campo} excede {largura} posicoes ({valor!r}).",
        )
    return limpo.zfill(largura)


def _data_ddmmaa(data: dt.date) -> str:
    return data.strftime("%d%m%y")


def _montar_registro(
    *,
    sequencial: int,
    codigo_empresa: str,
    data: dt.date,
    faltas_minutos: int,
    horas_trabalhadas_minutos: int,
    codigo_evento: str | None,
    valor_evento_centesimos_hora: int,
    matricula: str,
    cnpj_cpf_empresa: str,
    pis: str | None,
    departamento_codigo: str | None,
) -> str:
    inicio_evento, fim_evento = CAMPOS["codigo_evento"]
    largura_evento = fim_evento - inicio_evento + 1
    codigo_evento_limpo = (codigo_evento or "").strip()
    evento_formatado = (
        codigo_evento_limpo.zfill(largura_evento)
        if codigo_evento_limpo.isdigit() and len(codigo_evento_limpo) <= largura_evento
        else "0".zfill(largura_evento)
    )

    inicio_dep, fim_dep = CAMPOS["departamento"]
    largura_dep = fim_dep - inicio_dep + 1
    dep_limpo = (departamento_codigo or "").strip()
    departamento_formatado = (
        dep_limpo.zfill(largura_dep)
        if dep_limpo.isdigit() and len(dep_limpo) <= largura_dep
        else "0".zfill(largura_dep)
    )

    partes = [
        str(sequencial).zfill(CAMPOS["sequencial"][1] - CAMPOS["sequencial"][0] + 1),
        _campo_numerico(codigo_empresa, 5, nome_campo="codigoEmpresa"),
        _data_ddmmaa(data),
        _data_ddmmaa(data),
        str(faltas_minutos).zfill(6),
        str(horas_trabalhadas_minutos).zfill(6),
        "01",
        evento_formatado,
        str(valor_evento_centesimos_hora).zfill(14),
        _campo_numerico(matricula, 6, nome_campo="matricula (Codigo Funcionario)"),
        " ",
        _campo_numerico(cnpj_cpf_empresa, 14, nome_campo="CNPJ/CPF da empresa"),
        _campo_numerico(pis or "", 11, nome_campo="PIS", permite_vazio=True),
        departamento_formatado,
    ]
    registro = "".join(partes)
    if len(registro) != TAMANHO_REGISTRO:
        raise AssertionError(
            f"registro Alterdata com {len(registro)} posicoes, esperado {TAMANHO_REGISTRO}."
        )
    return registro


def gerar(contexto: ContextoExportacaoFolha) -> ArquivoFolhaGerado:
    """Gera o arquivo MOV.DP (ver docstring do modulo para o mapeamento
    campo a campo e a fonte)."""
    codigo_empresa = str(contexto.configuracao.get("codigoEmpresa") or "").strip()
    if not codigo_empresa:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                "A integracao Alterdata exige configuracao.codigoEmpresa (codigo numerico de "
                "ate 5 digitos atribuido pelo Alterdata a esta empresa)."
            ),
        )

    registros: list[str] = []
    for indice, linha in enumerate(contexto.linhas, start=1):
        rubrica = linha.rubrica or resolver_rubrica(
            linha.componente_codigo, contexto.mapeamento_rubricas
        )
        faltas = linha.minutos if linha.categoria == "falta" else 0
        horas_trabalhadas = 0 if linha.categoria == "falta" else linha.minutos_equivalentes
        valor_evento = round((linha.minutos_equivalentes / 60) * 100)
        registros.append(
            _montar_registro(
                sequencial=indice,
                codigo_empresa=codigo_empresa,
                data=linha.data,
                faltas_minutos=faltas,
                horas_trabalhadas_minutos=horas_trabalhadas,
                codigo_evento=rubrica,
                valor_evento_centesimos_hora=valor_evento,
                matricula=linha.matricula,
                cnpj_cpf_empresa=linha.empresa_cnpj,
                pis=linha.pis_nit,
                departamento_codigo=linha.departamento_codigo,
            )
        )

    corpo = (_QUEBRA_LINHA.join(registros) + _QUEBRA_LINHA) if registros else ""
    conteudo = corpo.encode("iso-8859-1", errors="replace")
    nome_arquivo = (
        f"integracoes-folha/{contexto.tenant_id}/{contexto.integracao_id}/"
        f"alterdata-{contexto.competencia_folha}-{contexto.processamento_id}.txt"
    )
    return ArquivoFolhaGerado(
        conteudo=conteudo,
        nome_arquivo=nome_arquivo,
        content_type="text/plain; charset=iso-8859-1",
    )
