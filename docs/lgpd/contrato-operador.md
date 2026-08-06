# Minuta — Contrato de Operador de Dados Pessoais (art. 39, LGPD)

**Versão:** 1.0 · **Data:** 05/08/2026 · **Responsável:** SEEG — arquitetura (F14/A3)
**Status:** minuta técnica, escrita a partir das salvaguardas *de fato* implementadas
no sistema (não é peça jurídica final — revisão do jurídico da SEEG antes de uso
comercial é obrigatória; este documento descreve o que o software garante
tecnicamente, para que a cláusula contratual não prometa mais do que o produto
entrega).

Este documento rege o tratamento de dados pessoais dos colaboradores do
**CONTRATANTE** (controlador) pela **SEEG** (operadora) na prestação do
serviço SEEG Ponto (SaaS multi-tenant de controle de ponto eletrônico,
REP-P, Portaria MTP 671/2021).

---

## 1. Objeto

A SEEG trata dados pessoais dos colaboradores do CONTRATANTE
**exclusivamente** para viabilizar o registro eletrônico de ponto, o cálculo
de jornada e banco de horas, a geração de arquivos fiscais (AFD, AEJ) e os
serviços correlatos contratados (relatórios, workflows de aprovação,
biometria como método de autenticação opcional). Qualquer uso além dessa
finalidade depende de instrução documentada e prévia do CONTRATANTE.

## 2. Natureza, finalidade e categorias de dado tratado

| Categoria | Finalidade | Base legal (do CONTRATANTE) |
|---|---|---|
| Identificação (nome, CPF, matrícula, PIS/NIT) | Identificar o titular da marcação | Obrigação legal (CLT, Portaria 671/2021) |
| Marcação de ponto (data/hora, canal, geolocalização) | Registro e apuração de jornada | Obrigação legal |
| Biometria facial/digital (template cifrado) | Autenticação opcional na marcação | Consentimento específico do titular |
| Documentos (RG, CTPS, atestados, contratos) | Gestão de pessoal | Obrigação legal / execução de contrato |
| Dados de acesso (sessão, IP, user-agent) | Segurança e auditoria | Obrigação legal / legítimo interesse |

A SEEG **não** usa o dado tratado para nenhuma finalidade própria (treino de
modelo, publicidade, venda ou compartilhamento com terceiro não autorizado
pelo CONTRATANTE), exceto suporte técnico e melhoria do próprio serviço, sob
minimização e registro de acesso (§5).

## 3. Salvaguardas técnicas — o que o sistema garante hoje

Esta seção descreve mecanismo **implementado e verificável**, com a
referência de código/decisão que o sustenta — não promessa de roadmap.

### 3.1 Isolamento multi-tenant

Cada CONTRATANTE é um *tenant* isolado por Row Level Security do PostgreSQL
em toda tabela que carrega `tenant_id` — um tenant nunca lê ou grava dado de
outro, nem por consulta direta ao banco, defesa em profundidade além do
filtro de aplicação (`packages/contracts/schema.sql`, auditado em F14/A2).

### 3.2 Biometria — a categoria de maior sensibilidade

- **Cifra em repouso**: AES-256-GCM, chave de dados (DEK) derivada por
  tenant via HKDF-SHA256 a partir de uma chave mestra (KEK) que **vive fora
  do banco de dados** — em `dev`/`hml`, variável de ambiente montada por
  volume; em produção, cofre gerenciado. Um *dump* do banco não contém a
  chave (ADR-006).
- **Autenticação do texto cifrado**: GCM detecta qualquer alteração de um
  byte sequer; os dados associados (AAD) amarram o texto cifrado ao
  `tenant_id` e ao `colaborador_id` — transplantar um template de uma
  pessoa para outra por manipulação direta de banco falha a decifragem.
- **Nunca sai pela API**: nenhum perfil, incluindo suporte SEEG e super
  administrador, lê o vetor em claro por nenhuma rota.
- **Consentimento como pré-condição**: sem `consentimentos` vigente para a
  finalidade específica, o cadastro e o uso do template são recusados
  (`PONTO-LGPD-001`). Revogar o consentimento **dispara expurgo real** do
  template (F14/A3, `app/lgpd/consentimentos.py`), não uma marcação lógica.
- **Fallback sempre disponível**: matrícula+PIN, cartão de proximidade —
  quem recusa biometria registra ponto do mesmo jeito.

### 3.3 Imutabilidade da marcação

A marcação de ponto é append-only, protegida por gatilho de banco que
aborta `UPDATE`/`DELETE`/`TRUNCATE` (`ERRCODE 42501`), hash encadeado por
REP-P e Número Sequencial de Registro sem lacuna (ADR-002). Qualquer
correção de jornada acontece em `tratamentos`, nunca sobre a marcação
original — o AFD deriva exclusivamente do fato registrado.

### 3.4 Registro de acesso a dado sensível

Toda leitura, exportação, impressão, compartilhamento ou eliminação de dado
das categorias sensíveis (biometria, documento, dado de saúde, remuneração,
geolocalização, foto, CPF) é registrada — quem, quando, de onde, para qual
titular, com qual finalidade e base legal — inclusive o acesso de suporte
da SEEG. O CONTRATANTE pode consultar essa trilha via
`GET /v1/lgpd/acessos-sensiveis`.

### 3.5 Retenção e expurgo

Prazo de guarda por categoria de dado, configurável por tenant
(`politicas_retencao`): marcação retém 5 anos por obrigação legal (nunca
menos, mesmo que uma política seja configurada incorretamente — piso
técnico aplicado no motor de expurgo, F14/A3); demais categorias seguem
prazo próprio, com expurgo automático diário para as categorias já
implementadas (biometria, sessão, notificação — ver RIPD §6 para o estado
completo, incluindo o que ainda não tem automação).

### 3.6 Atendimento a direitos do titular

O CONTRATANTE (ou, quando aplicável, o titular diretamente) pode abrir
pedido de acesso, correção, portabilidade, eliminação, anonimização,
revogação de consentimento, informação sobre compartilhamento ou oposição
via `POST /v1/lgpd/solicitacoes-titular`. Acesso e portabilidade geram
exportação automática dos dados localizáveis do titular; eliminação nunca
apaga marcação (guarda legal) e sempre produz relatório do que foi feito e
do que foi retido, com a base legal citada.

## 4. Obrigações da SEEG (operadora)

1. Tratar o dado pessoal **somente** conforme as instruções documentadas do
   CONTRATANTE (este contrato e a configuração do produto — políticas de
   retenção, perfis de risco antifraude, escopo de biometria).
2. Garantir a confidencialidade dos dados tratados, inclusive após o
   encerramento do contrato, pelo prazo de guarda legal aplicável.
3. Adotar as medidas técnicas e administrativas descritas na §3, mantendo-as
   atualizadas conforme evolução do produto.
4. Comunicar ao CONTRATANTE, em prazo razoável, qualquer incidente de
   segurança que possa acarretar risco ou dano relevante aos titulares.
5. Auxiliar o CONTRATANTE no atendimento a direitos do titular e a
   solicitações da Autoridade Nacional de Proteção de Dados (ANPD).
6. Eliminar ou devolver os dados pessoais ao término da relação contratual,
   ressalvada a guarda legal obrigatória (marcação de ponto, 5 anos), e
   comprovar essa eliminação quando solicitado.
7. Não subcontratar outro operador para tratamento dos dados sem
   autorização específica e prévia do CONTRATANTE.

## 5. Obrigações do CONTRATANTE (controlador)

1. Garantir a base legal do tratamento perante os próprios titulares
   (colaboradores), inclusive a coleta válida do consentimento específico
   para biometria, quando essa modalidade for habilitada.
2. Configurar corretamente as políticas de retenção e os perfis de risco
   antifraude do próprio tenant — o produto oferece o mecanismo, a decisão
   de política é do CONTRATANTE (ADR-008).
3. Designar um encarregado (DPO) e mantê-lo acessível, conforme exigido pela
   LGPD.
4. Não solicitar da SEEG tratamento que extrapole a finalidade deste
   contrato (§1).

## 6. Incidentes de segurança

Em caso de incidente que afete dado pessoal tratado sob este contrato, a
SEEG notifica o CONTRATANTE com informação suficiente para que este cumpra
sua própria obrigação de comunicação à ANPD e aos titulares, quando
aplicável — incluindo, na medida do disponível: natureza dos dados afetados,
titulares afetados, medidas de contenção já adotadas e recomendação de
ação.

## 7. Vigência e eliminação de dados ao término

Encerrado o contrato, a SEEG mantém os dados apenas pelo prazo de guarda
legal obrigatório (marcação de ponto: 5 anos, CLT art. 74) e elimina ou
anonimiza o restante conforme a política de retenção vigente no tenant,
salvo instrução em contrário do CONTRATANTE compatível com a lei.

## 8. Pendências conhecidas (transparência, não promessa cumprida)

Registradas aqui para que este contrato não prometa o que o produto ainda
não entrega — ver `docs/backlog.md` para o detalhe técnico de cada item:

- Sinais antifraude nativos de plataforma móvel (attestation, RASP, mock
  location) dependem do aplicativo móvel (F7), ainda não construído
  (ADR-014) — o registro via web/terminal já é real e não depende disso.
- Mecanismo de IP confiável ponta a ponta (para que `sessoes`/`auditoria`
  gravem o IP real do usuário final, não o do proxy reverso) é trabalho de
  hardening em andamento (F14/A2).
- Expurgo automático de sete categorias de dado do catálogo de retenção
  (`foto_registro`, `documento`, `espelho`, `afd`, `aej`, `log_acesso`,
  `fila_offline`, `relatorio_execucao`) ainda não está implementado —
  reconhecido pelo motor, mas sem ação automática nesta fase.
