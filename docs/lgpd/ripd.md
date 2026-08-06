# Relatório de Impacto à Proteção de Dados Pessoais (RIPD) — SEEG Ponto

**Versão:** 1.0 · **Data:** 05/08/2026 · **Responsável:** SEEG — arquitetura (F14/A3)
**Status:** documento vivo, escrito a partir do que o sistema *de fato* faz na Fase 14
(F1–F6, F8–F13, F9a implementadas; F7 — app mobile — pendente, ver ADR-014). Revisar a
cada fase que altere tratamento de dado pessoal.

---

## 1. Identificação

| Papel | Quem |
|---|---|
| **Controlador** | A empresa cliente (tenant) — decide a finalidade e os meios do tratamento dos dados dos próprios colaboradores. |
| **Operador** | SEEG — trata o dado em nome do controlador, sob as instruções documentadas no [contrato de operador](contrato-operador.md), fornecendo o software SEEG Ponto como SaaS multi-tenant. |
| **Titulares** | Colaboradores do tenant (o público majoritário) e, em menor medida, usuários administrativos (RH, gestores) cujos dados de acesso também são tratados. |
| **Encarregado (DPO)** | A definir por tenant — o produto não impõe um DPO único; cada empresa cliente designa o seu, e o sistema não modela essa figura como entidade própria (registrado como lacuna de produto, não bloqueante). |

## 2. Descrição do tratamento

SEEG Ponto é um sistema de controle de ponto eletrônico (REP-P, Portaria MTP
671/2021). O tratamento nuclear é o **registro de jornada de trabalho**: cada
marcação grava CPF, data/hora, canal e evidências de autenticidade (NSR, hash
encadeado, CRC-16). Ao redor dele, o sistema trata:

| Categoria de dado | Onde vive | Base legal | Observação |
|---|---|---|---|
| Identificação (nome, CPF, matrícula, PIS) | `colaboradores`, `marcacoes` | Obrigação legal (CLT, Portaria 671/2021) | Núcleo do produto; não há opção de não tratar para quem tem vínculo ativo. |
| Marcação de ponto (data/hora, geolocalização quando aplicável, canal) | `marcacoes`, `marcacoes_meta` | Obrigação legal | Append-only, guarda de 5 anos (ADR-002). |
| Biometria facial/digital (template vetorial) | `biometrias`, `biometria_templates` | **Consentimento específico** (ADR-006 regra 7) | Cifrado em repouso (AES-256-GCM, chave fora do banco — ver §4). Nunca sai por API, nem para super admin. Fallback obrigatório (matrícula+PIN, cartão) para quem recusa. |
| Score de confiança / sinais antifraude (dispositivo, geolocalização, prova de vida) | `marcacoes_meta` | Obrigação legal / execução de contrato | Composto no servidor por regra explicável e auditável (ADR-008); não decide sozinho — sinaliza para revisão humana na faixa intermediária. |
| Documentos (RG, CTPS, atestados, contratos) | `documentos` | Obrigação legal / execução de contrato | Metadado + referência no MinIO; conteúdo binário fora do escopo deste RIPD (tratado por controle de acesso do armazenamento de objetos). |
| Dados de acesso (sessão, IP, user-agent) | `sessoes`, `auditoria` | Legítimo interesse / obrigação legal | Necessários para segurança e trilha de auditoria (Portaria 671/2021 exige rastreabilidade). |

**Minimização já aplicada.** A imagem de captura facial nunca é persistida — só
o vetor de características, extraído em memória e descartado (ADR-006 regra
4). O REP-P não registra "sentido" (entrada/saída) na captura — isso é
inferido depois, na apuração, para não gravar dado derivado desnecessário
cedo demais.

**O que ainda depende do app móvel (F7, não construído — ADR-014).** Sinais
nativos de plataforma (attestation Play Integrity/App Attest, RASP,
`Location.isMock`, modo desenvolvedor/ADB) exigem um app real, registrado nas
lojas, para produzir dado verificável. Enquanto F7 não existir, esses sinais
chegam como `nao_aplicavel`/`null` em todo tráfego — nunca simulados. O
tratamento de dado via web/terminal (F6/F8, já em produção) não depende
disso: geolocalização, IP, prova de vida e similaridade facial já são reais
hoje.

## 3. Necessidade e proporcionalidade

O tratamento de identificação e de marcação de ponto é **obrigatório por
lei** (CLT art. 74, Portaria MTP 671/2021) para empresas com mais de 20
empregados, e as demais adotam por escolha de gestão de jornada — em ambos
os casos a finalidade é estrita: comprovar jornada trabalhada, calcular
banco de horas e gerar os arquivos fiscais (AFD/AEJ). Não há uso secundário
(perfilamento, publicidade, venda de dado a terceiro).

A **biometria é a exceção deliberada**: não é obrigatória por lei — é uma
conveniência de autenticação, e por isso exige consentimento específico,
destacado, revogável a qualquer momento, com fallback sempre disponível
(matrícula+PIN, cartão de proximidade). Quem recusa bate ponto do mesmo
jeito. Isso está implementado, não é aspiracional: `app/biometria/servico.py`
recusa o cadastro sem `consentimentos` vigente (`PONTO-LGPD-001`), e
`app/lgpd/consentimentos.py` (F14) implementa a revogação com expurgo real
do template.

O **score de confiança antifraude** (ADR-008) é proporcional por desenho:
nunca bloqueia sozinho por um sinal fraco (só sinal decisivo — mock location
comprovado, assinatura inválida — recusa direto); a faixa intermediária
sinaliza para revisão humana, não decide automaticamente contra o
trabalhador; a mensagem de recusa nunca revela a regra (`expoe_regra: false`
no catálogo de erros), o que impede que o texto do erro vire ferramenta de
calibração de fraude.

## 4. Riscos identificados e medidas de mitigação

| Risco | Impacto | Medida implementada | Onde |
|---|---|---|---|
| Vazamento de banco (dump, réplica esquecida, credencial vazada) expõe biometria | Alto — dado biométrico não pode ser trocado como senha | Envelope encryption AES-256-GCM, chave (KEK) fora do PostgreSQL, DEK derivada por tenant via HKDF-SHA256, AAD amarrado a tenant+colaborador (transplante entre pessoas falha a decifragem) | ADR-006, `app/biometria/cifra.py` |
| Marcação de ponto adulterada/apagada (fraude interna ou externa) | Alto — invalida o AFD, expõe a empresa a passivo trabalhista | Append-only com gatilho de banco (`fn_registro_imutavel`) que aborta UPDATE/DELETE/TRUNCATE, hash encadeado, NSR sem lacuna, role da aplicação sem privilégio de alterar | ADR-002 |
| Acesso indevido a dado sensível por suporte/administração | Médio-alto — biometria, documento, saúde, remuneração, geolocalização | Toda leitura de dado sensível grava `acessos_dados_sensiveis` (quem, quando, de onde, para qual titular, com qual finalidade); mecanismo genérico cobre qualquer permissão marcada `sensivel=true` no catálogo, além de pontos de instrumentação específicos (biometria, documento, folha) | `app/core/seguranca.py::exigir_permissao`, `app/identidade/auditoria/hash_chain.py`, `app/biometria/servico.py` |
| Vazamento cross-tenant (empresa A lê dado da empresa B) | Alto — quebra de confiança multi-tenant, obrigação legal violada para o tenant errado | Row Level Security do PostgreSQL em toda tabela com `tenant_id`, auditado por script (ownership de A2/F14) | `packages/contracts/schema.sql`, revisão de RLS de F14/A2 |
| Retenção além do necessário / falta de expurgo | Médio | Política de retenção por entidade (`politicas_retencao`) com rotina automática (F14/A3, `app/lgpd/expurgo.py`) — biometria, sessão e notificação já têm expurgo real; marcação/auditoria nunca são tocadas antes do prazo legal de 5 anos, e o mecanismo de expurgo pós-prazo (arquivamento de partição) ainda não existe (documentado, não simulado) | §6 abaixo |
| Score antifraude usado como bloqueio arbitrário/discriminatório | Médio | Três faixas configuráveis, nunca binário; explicabilidade obrigatória gravada em `marcacoes_meta`; canal alternativo sempre existe (terminal, totem, registro assistido do RH) | ADR-008 |
| Sinais nativos móveis inexistentes usados para negar direito ao titular | Baixo (mitigado por desenho) | Sinais sem F7 chegam como `nao_aplicavel`, nunca como reprovação forjada — a ausência de sinal não pesa contra o colaborador | ADR-014 |

## 5. Direitos do titular — implementação real (F14)

`POST /v1/lgpd/solicitacoes-titular` aceita os oito direitos do art. 18 da
LGPD. Comportamento por tipo, testado contra banco real:

- **Acesso / portabilidade**: gera automaticamente um pacote JSON com todos
  os dados do titular localizáveis no sistema (cadastro, vínculos,
  marcações, metadados de biometria — nunca o vetor, consentimentos,
  documentos, solicitações anteriores), grava no armazenamento de objetos e
  devolve a referência em `respostaRef`.
- **Eliminação / anonimização**: elimina de verdade o que a lei permite
  (template biométrico, consentimentos) e **nunca** apaga marcação — produz
  um relatório explícito do que foi feito e do que foi retido, com a base
  legal citada (`PONTO-LGPD-003`), nunca um apagamento silencioso.
- **Revogação de consentimento**: revoga todos os consentimentos vigentes
  do titular e dispara o expurgo real do(s) template(s) biométrico(s)
  associados.
- **Correção / oposição / informação sobre compartilhamento**: registrados
  com protocolo e prazo, aguardando triagem humana — corrigir o quê, ou
  avaliar uma oposição, exige julgamento que uma regra automática não
  deveria fingir ter.

## 6. Retenção e expurgo automático

`politicas_retencao` (por tenant, por entidade) já modela prazo, base legal
e ação (anonimizar/eliminar/arquivar) desde a Fase 0. F14/A3 liga a rotina
automática: uma vez por dia, o *scheduler* enfileira `expurgo_lgpd` para
todo tenant com política vencida; a tarefa aplica a ação real para
`biometria` (template expurgado), `sessao` e `notificacao` (removidas por
coluna de tempo). `marcacao` e `auditoria` **nunca** são tocadas antes do
prazo legal mínimo de 5 anos (1825 dias) — piso aplicado mesmo que a política
esteja configurada com prazo menor — e, mesmo depois do prazo, o motor não
executa ação alguma sobre elas nesta fase: são tabelas append-only com
gatilho de banco que bloqueia UPDATE/DELETE/TRUNCATE (ADR-002); o
procedimento de arquivamento pós-prazo (ex.: drop de partição sob supervisão)
fica como pendência documentada, não uma simulação de sucesso.

Sete entidades do catálogo (`foto_registro`, `documento`, `espelho`, `afd`,
`aej`, `log_acesso`, `fila_offline`, `relatorio_execucao`) são reconhecidas
mas ainda não têm ação automática implementada — o motor devolve o motivo
explícito em vez de um "sucesso" silencioso sobre nada (ver
`docs/backlog.md`, 2026-08-05).

## 7. Conclusão

O tratamento é necessário, proporcional às finalidades declaradas (obrigação
legal para o ponto, consentimento específico para biometria) e tem
salvaguardas técnicas correspondentes ao nível de sensibilidade de cada
categoria de dado — mais rígidas para biometria (cifra com chave externa,
nunca exposta) e marcação (imutabilidade), mais leves para dado
administrativo comum. Os riscos residuais conhecidos (retenção automática
incompleta para sete entidades, sinais antifraude nativo-móveis pendentes de
F7, ausência de mecanismo de IP confiável ponta a ponta — ownership de A2)
estão documentados, não escondidos, e têm dono de fase claro no backlog.

Este RIPD deve ser revisado sempre que uma fase futura alterar categoria de
dado tratada, finalidade ou salvaguarda técnica — em particular quando F7
(app mobile) entregar os sinais nativos hoje pendentes.
