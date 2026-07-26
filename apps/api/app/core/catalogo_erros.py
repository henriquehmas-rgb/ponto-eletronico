"""Espelho de `packages/contracts/errors.yaml`. GERADO -- nao editar.

Regerar com `python tools/gerar_do_contrato.py`.

O catalogo e a fonte da verdade das falhas da API: o backend responde com o
`codigo`, e o web e o mobile traduzem o codigo para a mensagem do usuario.
Nenhum servico inventa string de erro nem codigo fora desta tabela.
"""

# ruff: noqa: E501 - tabela de dados: uma entrada por linha e mais legivel

from __future__ import annotations

from typing import Final, NamedTuple

VERSAO_CATALOGO: Final[str] = "1.0.0"
MEDIA_TYPE_PROBLEMA: Final[str] = "application/problem+json"
PREFIXO_TYPE: Final[str] = "https://docs.ponto.seeg.com.br/erros/"


class EntradaErro(NamedTuple):
    """Uma linha do catalogo de erros."""

    codigo: str
    categoria: str
    http_status: int
    titulo: str
    retentavel: bool
    expoe_regra: bool


CATEGORIAS: Final[dict[str, str]] = {
    "AUTH": "Autenticacao",
    "PERM": "Autorizacao",
    "VAL": "Validacao",
    "TEN": "Tenant",
    "IDEM": "Idempotencia",
    "CONF": "Conflito",
    "REC": "Recurso",
    "RATE": "Limite de taxa",
    "MARC": "Integridade de marcacao",
    "SCORE": "Score de confianca",
    "REDE": "Rede de origem",
    "GEO": "Geocerca",
    "DISP": "Dispositivo",
    "PER": "Periodo e fechamento",
    "APUR": "Apuracao",
    "BH": "Banco de horas",
    "FISC": "Arquivos fiscais",
    "TERM": "Terminal coletor",
    "LGPD": "LGPD",
    "WEBH": "Webhooks",
    "IMP": "Importacao",
    "INT": "Interno",
}

CATALOGO: Final[dict[str, EntradaErro]] = {
    "PONTO-AUTH-001": EntradaErro(
        "PONTO-AUTH-001", "AUTH", 401, "Credenciais invalidas", True, False
    ),
    "PONTO-AUTH-002": EntradaErro(
        "PONTO-AUTH-002", "AUTH", 401, "Credencial de acesso ausente", False, True
    ),
    "PONTO-AUTH-003": EntradaErro("PONTO-AUTH-003", "AUTH", 401, "Token expirado", False, True),
    "PONTO-AUTH-004": EntradaErro("PONTO-AUTH-004", "AUTH", 401, "Token invalido", False, False),
    "PONTO-AUTH-005": EntradaErro(
        "PONTO-AUTH-005", "AUTH", 401, "Refresh token ja utilizado", False, True
    ),
    "PONTO-AUTH-006": EntradaErro(
        "PONTO-AUTH-006", "AUTH", 401, "Sessao encerrada ou revogada", False, True
    ),
    "PONTO-AUTH-007": EntradaErro(
        "PONTO-AUTH-007", "AUTH", 401, "Segundo fator obrigatorio", False, True
    ),
    "PONTO-AUTH-008": EntradaErro(
        "PONTO-AUTH-008", "AUTH", 401, "Codigo de segundo fator invalido", True, True
    ),
    "PONTO-AUTH-009": EntradaErro(
        "PONTO-AUTH-009", "AUTH", 423, "Credencial temporariamente bloqueada", True, True
    ),
    "PONTO-AUTH-010": EntradaErro(
        "PONTO-AUTH-010", "AUTH", 401, "Usuario inativo ou bloqueado", False, True
    ),
    "PONTO-AUTH-011": EntradaErro(
        "PONTO-AUTH-011", "AUTH", 401, "Reautenticacao necessaria", False, True
    ),
    "PONTO-AUTH-012": EntradaErro(
        "PONTO-AUTH-012", "AUTH", 401, "Credenciais de cliente OAuth invalidas", False, False
    ),
    "PONTO-AUTH-013": EntradaErro(
        "PONTO-AUTH-013", "AUTH", 401, "Chave de API invalida ou revogada", False, False
    ),
    "PONTO-PERM-001": EntradaErro("PONTO-PERM-001", "PERM", 403, "Permissao ausente", False, True),
    "PONTO-PERM-002": EntradaErro(
        "PONTO-PERM-002", "PERM", 403, "Fora do alcance hierarquico", False, False
    ),
    "PONTO-PERM-003": EntradaErro(
        "PONTO-PERM-003", "PERM", 403, "Escopo OAuth insuficiente", False, True
    ),
    "PONTO-PERM-004": EntradaErro(
        "PONTO-PERM-004", "PERM", 403, "Perfil somente leitura", False, True
    ),
    "PONTO-PERM-005": EntradaErro(
        "PONTO-PERM-005", "PERM", 403, "Delegacao invalida ou expirada", False, True
    ),
    "PONTO-PERM-006": EntradaErro(
        "PONTO-PERM-006", "PERM", 403, "Origem nao permitida para o cliente de API", False, False
    ),
    "PONTO-VAL-001": EntradaErro(
        "PONTO-VAL-001", "VAL", 400, "Corpo da requisicao invalido", False, True
    ),
    "PONTO-VAL-002": EntradaErro("PONTO-VAL-002", "VAL", 422, "CPF invalido", False, True),
    "PONTO-VAL-003": EntradaErro("PONTO-VAL-003", "VAL", 422, "CNPJ invalido", False, True),
    "PONTO-VAL-004": EntradaErro("PONTO-VAL-004", "VAL", 422, "PIS ou NIT invalido", False, True),
    "PONTO-VAL-005": EntradaErro(
        "PONTO-VAL-005", "VAL", 400, "Parametro de consulta invalido", False, True
    ),
    "PONTO-VAL-006": EntradaErro(
        "PONTO-VAL-006", "VAL", 400, "Cursor incompativel com a ordenacao", False, True
    ),
    "PONTO-VAL-007": EntradaErro(
        "PONTO-VAL-007", "VAL", 422, "Intervalo de datas invalido", False, True
    ),
    "PONTO-VAL-008": EntradaErro(
        "PONTO-VAL-008", "VAL", 413, "Arquivo acima do tamanho maximo", False, True
    ),
    "PONTO-VAL-009": EntradaErro(
        "PONTO-VAL-009", "VAL", 415, "Tipo de conteudo nao suportado", False, True
    ),
    "PONTO-VAL-010": EntradaErro("PONTO-VAL-010", "VAL", 422, "Vigencia sobreposta", False, True),
    "PONTO-VAL-011": EntradaErro(
        "PONTO-VAL-011", "VAL", 400, "Cabecalho obrigatorio ausente", False, True
    ),
    "PONTO-TEN-001": EntradaErro("PONTO-TEN-001", "TEN", 404, "Tenant nao encontrado", False, True),
    "PONTO-TEN-002": EntradaErro(
        "PONTO-TEN-002", "TEN", 403, "Tenant divergente do token", False, False
    ),
    "PONTO-TEN-003": EntradaErro(
        "PONTO-TEN-003", "TEN", 403, "Tenant suspenso ou cancelado", False, True
    ),
    "PONTO-TEN-004": EntradaErro(
        "PONTO-TEN-004", "TEN", 403, "Acesso cross-tenant negado", False, False
    ),
    "PONTO-TEN-005": EntradaErro(
        "PONTO-TEN-005", "TEN", 409, "Limite contratual de colaboradores atingido", False, True
    ),
    "PONTO-IDEM-001": EntradaErro(
        "PONTO-IDEM-001", "IDEM", 400, "Idempotency-Key ausente", False, True
    ),
    "PONTO-IDEM-002": EntradaErro(
        "PONTO-IDEM-002",
        "IDEM",
        409,
        "Idempotency-Key reutilizada com corpo diferente",
        False,
        True,
    ),
    "PONTO-IDEM-003": EntradaErro(
        "PONTO-IDEM-003", "IDEM", 409, "Requisicao concorrente em processamento", True, True
    ),
    "PONTO-CONF-001": EntradaErro("PONTO-CONF-001", "CONF", 409, "Registro duplicado", False, True),
    "PONTO-CONF-002": EntradaErro(
        "PONTO-CONF-002", "CONF", 409, "Versao desatualizada", True, True
    ),
    "PONTO-CONF-003": EntradaErro(
        "PONTO-CONF-003", "CONF", 409, "Transicao de estado invalida", False, True
    ),
    "PONTO-CONF-004": EntradaErro(
        "PONTO-CONF-004", "CONF", 409, "Registro com dependentes", False, True
    ),
    "PONTO-REC-001": EntradaErro(
        "PONTO-REC-001", "REC", 404, "Recurso nao encontrado", False, False
    ),
    "PONTO-REC-002": EntradaErro("PONTO-REC-002", "REC", 410, "Artefato expirado", False, True),
    "PONTO-RATE-001": EntradaErro(
        "PONTO-RATE-001", "RATE", 429, "Limite de requisicoes excedido", True, True
    ),
    "PONTO-RATE-002": EntradaErro(
        "PONTO-RATE-002", "RATE", 429, "Limite de registros por colaborador excedido", True, False
    ),
    "PONTO-RATE-003": EntradaErro(
        "PONTO-RATE-003", "RATE", 429, "Limite de geracao de arquivo fiscal excedido", True, True
    ),
    "PONTO-MARC-001": EntradaErro(
        "PONTO-MARC-001", "MARC", 405, "Alteracao de marcacao vedada", False, True
    ),
    "PONTO-MARC-002": EntradaErro(
        "PONTO-MARC-002", "MARC", 405, "Exclusao de marcacao vedada", False, True
    ),
    "PONTO-MARC-003": EntradaErro("PONTO-MARC-003", "MARC", 409, "Marcacao duplicada", False, True),
    "PONTO-MARC-004": EntradaErro(
        "PONTO-MARC-004", "MARC", 422, "Data e hora fora da janela aceitavel", False, True
    ),
    "PONTO-MARC-005": EntradaErro(
        "PONTO-MARC-005", "MARC", 422, "Item offline fora do prazo de sincronizacao", False, True
    ),
    "PONTO-MARC-006": EntradaErro(
        "PONTO-MARC-006", "MARC", 422, "Assinatura do item offline invalida", False, False
    ),
    "PONTO-MARC-007": EntradaErro(
        "PONTO-MARC-007", "MARC", 409, "Contador monotonico reutilizado", False, False
    ),
    "PONTO-MARC-008": EntradaErro("PONTO-MARC-008", "MARC", 409, "Falha ao alocar NSR", True, True),
    "PONTO-MARC-009": EntradaErro(
        "PONTO-MARC-009", "MARC", 422, "Colaborador sem vinculo ativo na data", False, True
    ),
    "PONTO-MARC-010": EntradaErro(
        "PONTO-MARC-010", "MARC", 422, "REP-P nao configurado", False, True
    ),
    "PONTO-SCORE-001": EntradaErro(
        "PONTO-SCORE-001", "SCORE", 403, "Registro reprovado pelo score de confianca", False, False
    ),
    "PONTO-SCORE-002": EntradaErro(
        "PONTO-SCORE-002", "SCORE", 403, "Prova de vida reprovada", True, False
    ),
    "PONTO-SCORE-003": EntradaErro(
        "PONTO-SCORE-003", "SCORE", 403, "Similaridade facial abaixo do limiar", True, False
    ),
    "PONTO-SCORE-004": EntradaErro(
        "PONTO-SCORE-004", "SCORE", 403, "Camera virtual detectada", True, True
    ),
    "PONTO-REDE-001": EntradaErro(
        "PONTO-REDE-001", "REDE", 403, "IP de origem fora da lista permitida", False, False
    ),
    "PONTO-REDE-002": EntradaErro(
        "PONTO-REDE-002", "REDE", 403, "Origem por VPN, proxy ou datacenter bloqueada", True, True
    ),
    "PONTO-GEO-001": EntradaErro(
        "PONTO-GEO-001", "GEO", 403, "Fora da geocerca da unidade", True, False
    ),
    "PONTO-GEO-002": EntradaErro(
        "PONTO-GEO-002", "GEO", 422, "Precisao de localizacao insuficiente", True, True
    ),
    "PONTO-GEO-003": EntradaErro("PONTO-GEO-003", "GEO", 403, "Localizacao simulada", False, True),
    "PONTO-DISP-001": EntradaErro(
        "PONTO-DISP-001", "DISP", 403, "Dispositivo nao vinculado ao colaborador", False, True
    ),
    "PONTO-DISP-002": EntradaErro(
        "PONTO-DISP-002", "DISP", 403, "Dispositivo bloqueado ou revogado", False, True
    ),
    "PONTO-DISP-003": EntradaErro(
        "PONTO-DISP-003", "DISP", 403, "Attestation de plataforma reprovado", True, True
    ),
    "PONTO-DISP-004": EntradaErro(
        "PONTO-DISP-004", "DISP", 403, "Modo desenvolvedor ou depuracao ativos", True, True
    ),
    "PONTO-DISP-005": EntradaErro(
        "PONTO-DISP-005", "DISP", 403, "Ambiente comprometido", False, False
    ),
    "PONTO-DISP-006": EntradaErro(
        "PONTO-DISP-006", "DISP", 409, "Colaborador ja possui dispositivo ativo", False, True
    ),
    "PONTO-PER-001": EntradaErro("PONTO-PER-001", "PER", 409, "Periodo fechado", False, True),
    "PONTO-PER-002": EntradaErro("PONTO-PER-002", "PER", 409, "Periodo ja fechado", False, True),
    "PONTO-PER-003": EntradaErro(
        "PONTO-PER-003", "PER", 422, "Reabertura sem justificativa", False, True
    ),
    "PONTO-PER-004": EntradaErro(
        "PONTO-PER-004", "PER", 409, "Fechamento com pendencias bloqueantes", False, True
    ),
    "PONTO-APUR-001": EntradaErro(
        "PONTO-APUR-001", "APUR", 409, "Recalculo ja em andamento", True, True
    ),
    "PONTO-APUR-002": EntradaErro(
        "PONTO-APUR-002", "APUR", 422, "Jornada nao resolvida para a data", False, True
    ),
    "PONTO-APUR-003": EntradaErro(
        "PONTO-APUR-003", "APUR", 409, "Apuracao travada por fechamento", False, True
    ),
    "PONTO-BH-001": EntradaErro(
        "PONTO-BH-001", "BH", 409, "Teto positivo do banco atingido", False, True
    ),
    "PONTO-BH-002": EntradaErro(
        "PONTO-BH-002", "BH", 409, "Teto negativo do banco atingido", False, True
    ),
    "PONTO-BH-003": EntradaErro(
        "PONTO-BH-003", "BH", 422, "Periodo de compensacao acima do limite legal", False, True
    ),
    "PONTO-BH-004": EntradaErro("PONTO-BH-004", "BH", 409, "Conta de banco encerrada", False, True),
    "PONTO-BH-005": EntradaErro(
        "PONTO-BH-005", "BH", 409, "Saldo insuficiente para a quitacao", False, True
    ),
    "PONTO-BH-006": EntradaErro(
        "PONTO-BH-006", "BH", 422, "Acordo de banco de horas ausente", False, True
    ),
    "PONTO-FISC-001": EntradaErro(
        "PONTO-FISC-001", "FISC", 409, "Lacuna de NSR detectada", False, True
    ),
    "PONTO-FISC-002": EntradaErro(
        "PONTO-FISC-002", "FISC", 409, "Geracao de arquivo fiscal ja em andamento", True, True
    ),
    "PONTO-FISC-003": EntradaErro(
        "PONTO-FISC-003", "FISC", 422, "REP-P sem numero de registro no INPI", False, True
    ),
    "PONTO-FISC-004": EntradaErro(
        "PONTO-FISC-004", "FISC", 424, "Certificado ICP-Brasil indisponivel", True, True
    ),
    "PONTO-FISC-005": EntradaErro(
        "PONTO-FISC-005", "FISC", 422, "Certificado expirado ou revogado", False, True
    ),
    "PONTO-FISC-006": EntradaErro(
        "PONTO-FISC-006", "FISC", 500, "Falha na geracao do arquivo fiscal", True, True
    ),
    "PONTO-FISC-007": EntradaErro(
        "PONTO-FISC-007", "FISC", 409, "Espelho ja assinado", False, True
    ),
    "PONTO-TERM-001": EntradaErro(
        "PONTO-TERM-001", "TERM", 502, "Terminal inacessivel", True, True
    ),
    "PONTO-TERM-002": EntradaErro(
        "PONTO-TERM-002", "TERM", 504, "Tempo esgotado na comunicacao com o terminal", True, True
    ),
    "PONTO-TERM-003": EntradaErro(
        "PONTO-TERM-003", "TERM", 502, "Credenciais do terminal recusadas", False, True
    ),
    "PONTO-TERM-004": EntradaErro(
        "PONTO-TERM-004", "TERM", 409, "Terminal offline, comando enfileirado", False, True
    ),
    "PONTO-TERM-005": EntradaErro(
        "PONTO-TERM-005", "TERM", 502, "Resposta invalida do terminal", True, True
    ),
    "PONTO-LGPD-001": EntradaErro(
        "PONTO-LGPD-001", "LGPD", 403, "Consentimento biometrico ausente ou revogado", False, True
    ),
    "PONTO-LGPD-002": EntradaErro(
        "PONTO-LGPD-002", "LGPD", 403, "Acesso ao template biometrico vedado", False, True
    ),
    "PONTO-LGPD-003": EntradaErro(
        "PONTO-LGPD-003", "LGPD", 409, "Eliminacao vedada por retencao legal", False, True
    ),
    "PONTO-LGPD-004": EntradaErro(
        "PONTO-LGPD-004", "LGPD", 422, "Termo de consentimento desatualizado", False, True
    ),
    "PONTO-WEBH-001": EntradaErro(
        "PONTO-WEBH-001", "WEBH", 422, "URL de webhook invalida", False, True
    ),
    "PONTO-WEBH-002": EntradaErro(
        "PONTO-WEBH-002", "WEBH", 409, "Webhook desabilitado por falhas consecutivas", False, True
    ),
    "PONTO-WEBH-003": EntradaErro(
        "PONTO-WEBH-003", "WEBH", 422, "Evento desconhecido", False, True
    ),
    "PONTO-IMP-001": EntradaErro(
        "PONTO-IMP-001", "IMP", 422, "Layout de arquivo nao reconhecido", False, True
    ),
    "PONTO-IMP-002": EntradaErro(
        "PONTO-IMP-002", "IMP", 409, "Importacao ja em andamento", True, True
    ),
    "PONTO-IMP-003": EntradaErro(
        "PONTO-IMP-003", "IMP", 422, "AFD de terceiro invalido", False, True
    ),
    "PONTO-INT-001": EntradaErro("PONTO-INT-001", "INT", 500, "Erro interno", True, False),
    "PONTO-INT-002": EntradaErro("PONTO-INT-002", "INT", 503, "Servico em manutencao", True, True),
    "PONTO-INT-003": EntradaErro(
        "PONTO-INT-003", "INT", 503, "Dependencia indisponivel", True, True
    ),
    "PONTO-INT-004": EntradaErro(
        "PONTO-INT-004", "INT", 504, "Tempo de processamento esgotado", True, True
    ),
    "PONTO-INT-005": EntradaErro(
        "PONTO-INT-005", "INT", 501, "Operacao ainda nao implementada", False, True
    ),
}


def entrada(codigo: str) -> EntradaErro:
    """Devolve a entrada do catalogo, ou levanta KeyError.

    KeyError aqui e proposital: codigo fora do catalogo e defeito de
    programacao, nao condicao de execucao. Codigo novo entra por RFC
    em errors.yaml e so depois aparece aqui.
    """
    return CATALOGO[codigo]
