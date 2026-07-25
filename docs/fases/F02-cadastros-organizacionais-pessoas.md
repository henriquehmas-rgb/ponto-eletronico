# F02 — Cadastros organizacionais e pessoas

| | |
|---|---|
| **Onda** | 1 |
| **Agentes** | 3 · **A1** estrutura organizacional (empresas, unidades, geocerca, allowlist CIDR, departamentos, centros de custo, cargos, equipes) · **A2** pessoas (colaboradores, contratos, vínculos, hierarquia de gestores) · **A3** biometria, dispositivos e importadores |
| **Duração estimada** | 5 dias |
| **Depende de** | F0 (contratos congelados e andaime da API). Roda **em paralelo** com a F1 e usa o *auth stub* descrito na §5 |
| **Criticidade** | Alta — F3, F5, F6, F7, F8 e F9b não têm sobre o que operar sem os cadastros desta fase |
| **Branch** | `f02-cadastros-organizacionais-pessoas` |

---

## 1. Objetivo

Ao fim desta fase, **existe no sistema uma empresa com CNPJ válido, com unidades
que sabem onde ficam (geocerca e faixas de rede autorizadas) e em que fuso
operam, com departamentos, centros de custo, cargos e equipes; existem pessoas
com CPF e PIS validados, seus contratos, seus vínculos de trabalho e sua cadeia
de gestores; existem credenciais biométricas cifradas e dispositivos vinculados;
e uma planilha com 5.000 colaboradores entra pelo importador produzindo um
relatório linha a linha** — com as 58 operações das tags `empresas`, `unidades`,
`organizacao`, `colaboradores`, `contratos`, `biometria` e `dispositivos`
respondendo conforme o `openapi.yaml`, no lugar do `501` de hoje.

## 2. Contexto mínimo

**O produto.** Este é um sistema de ponto eletrônico brasileiro do tipo
**REP-P** — *Registrador Eletrônico de Ponto via Programa*, a modalidade de
software prevista na Portaria MTP 671/2021. É vendido como SaaS: uma instância
atende vários clientes, e cada cliente é um **tenant**. Todo dado que você
escrever carrega `tenant_id` e está sob **Row Level Security** do PostgreSQL: a
aplicação abre cada transação publicando `app.tenant_id`, e sem isso nenhuma
linha é visível. O andaime já faz esse `SET LOCAL` (`apps/api/app/db/sessao.py`);
o endurecimento é da F1, que roda em paralelo. **Você não desabilita RLS e não
"resolve" tenant por conta própria.**

**A cadeia organizacional, de fora para dentro.** Um **tenant** contém uma ou
mais **empresas**. Empresa é pessoa jurídica empregadora: matriz e filiais são
**linhas distintas** ligadas por `empresas.matriz_id`, cada uma com seu CNPJ e
seus próprios arquivos fiscais — a constraint `ck_empresas_matriz` garante que
`tipo = 'matriz'` implica `matriz_id IS NULL` e `tipo = 'filial'` implica o
contrário. Uma empresa tem **unidades** (`unidades`), que são os locais físicos
de trabalho. A unidade é mais importante do que parece: ela carrega o
**`fuso_horario` efetivo da apuração** (o tenant tem um padrão, a unidade
sobrescreve), a **geocerca** e o conjunto de feriados aplicável. Dentro da
empresa existem ainda **departamentos** (hierárquicos, via
`departamento_pai_id`), **centros de custo** (também hierárquicos, para
apropriação de horas), **cargos** (com **CBO** — Classificação Brasileira de
Ocupações, seis dígitos, exigida pelo eSocial — e o *flag* `cargo_confianca`) e
**equipes**, que são agrupamentos operacionais **ortogonais ao departamento**:
uma equipe pode cruzar departamentos, e é ela que sustenta escala e cobertura de
turno mais adiante.

**Geocerca.** `unidades` aceita **duas formas simultâneas**: ponto mais raio
(`geocerca_latitude`, `geocerca_longitude`, `geocerca_raio_metros` — a
constraint `ck_unidades_geocerca_ponto` exige os três juntos ou os três nulos) e
**polígono** em `geocerca_poligono` (JSONB, restrito a objeto por `CHECK`).
Existem ainda `geocerca_obrigatoria` (se falso, a cerca é informativa) e
`geocerca_tolerancia_metros` (padrão 50), que existe porque GPS civil erra. Você
implementa o cadastro **e** a função de pertencimento (o ponto está dentro?),
porque é ela que a F7 e a F8 vão chamar. Ponto fora da cerca responde
`PONTO-GEO-001`; precisão de localização insuficiente responde `PONTO-GEO-002`.
Cuidado com o caso real: polígono que cruza o antimeridiano não ocorre no
Brasil, mas polígono côncavo e polígono com o primeiro ponto repetido no fim
ocorrem — trate os dois.

**Allowlist CIDR.** `redes_permitidas` é a lista de faixas de IP (IPv4 **e**
IPv6, coluna do tipo `CIDR`) a partir das quais é permitido registrar ponto.
Escopo por `empresa_id` obrigatório e, opcionalmente, por `unidade_id` e por
`canal` (`web|mobile|totem|api|terminal`). É tabela filha, e não coluna de
array, porque uma empresa tem múltiplos links (matriz, filial, VPN, 4G
corporativo) e cada faixa precisa de vigência e de escopo próprios. IP de origem
fora da lista responde `PONTO-REDE-001`. Você implementa o **cadastro** e a
função de verificação de pertencimento de IP; **a aplicação da regra no momento
de bater ponto é da F8**.

**Pessoa não é vínculo — e essa distinção é o coração da fase.**
`colaboradores` é a **pessoa**: CPF, PIS/NIT, nome, matrícula interna, endereço,
documentos, `status`. `contratos` é o **instrumento jurídico**: tipo de
contratação (`clt`, `aprendiz`, `estagio`, `temporario`, `intermitente`,
`avulso`, `autonomo`, `pj`, `socio`, `servidor`), regime de jornada, cargo,
salário, carga contratada e a cláusula do **art. 62 da CLT** — a coluna
`controle_jornada` com `dispensa_controle_motivo` restrito a
`art62_i_externo|art62_ii_gestao|art62_iii_teletrabalho`, amarrados por
`ck_contratos_dispensa`: se dispensa o controle, o motivo é obrigatório; se não
dispensa, tem de ser nulo. E `vinculos` é a **relação de trabalho operacional**,
na granularidade que o eSocial e o AEJ exigem: `matricula_esocial` (única por
tenant + empresa), `categoria_esocial`, unidade, departamento, centro de custo,
cargo e `apura_ponto`. **Todo o motor de apuração das fases seguintes pendura em
`vinculo_id`, nunca em `colaborador_id`.** Um contrato origina um vínculo; um
colaborador pode ter vínculos simultâneos em **empresas diferentes** do mesmo
tenant, e a constraint `ex_vinculos_sobreposicao` (`EXCLUDE USING gist`) impede
dois vínculos ativos sobrepostos do mesmo colaborador **na mesma empresa**.
Violá-la é `PONTO-VAL-010` (vigência sobreposta).

**Hierarquia de gestores.** `colaborador_gestores` liga colaborador a gestor com
`tipo` em `imediato|substituto|matricial|rh` e vigência datada. A constraint
`ex_colaborador_gestores_imediato` garante **um único gestor imediato vigente
por colaborador em qualquer data** — é isso que define a árvore de subordinados
que o perfil "gestor" enxerga (a F1 consome isso) e a cadeia de aprovação da
F10. Você precisa também detectar e recusar **ciclo** na hierarquia: A gerencia
B que gerencia A é `PONTO-CONF-003`.

**Validação de documento é sua.** O `schema.sql` tem os domínios `dom_cpf`,
`dom_cnpj`, `dom_pis` e eles validam **apenas o formato** (11, 14 e 11 dígitos,
sem pontuação). O comentário no próprio arquivo é explícito: *"a validação de
dígito verificador (CPF, CNPJ, PIS) é responsabilidade da aplicação (Fase 2)"*.
CPF inválido responde `PONTO-VAL-002`, CNPJ `PONTO-VAL-003`, PIS/NIT
`PONTO-VAL-004`. Guarde sempre **só dígitos**; a máscara é da interface.

**Biometria é dado pessoal sensível, e o ADR-006 é decisão fechada.** Template
facial é dado sensível pelo art. 5º, II da LGPD; diferente de senha, ele não
pode ser trocado. `biometrias` guarda o **ciclo de vida** (modalidade —
`facial|digital|cartao|pin|qrcode` —, `status`, `origem_cadastro`, qualidade,
validação pelo RH, revogação, expiração), com índice único garantindo **uma
credencial ativa por colaborador e modalidade**. `biometria_templates` guarda o
**vetor**, e as regras que você não pode redecidir são: (1) **envelope
encryption** — o vetor é cifrado em **AES-256-GCM** com uma chave de dados por
tenant, cifrada por uma chave mestra que vive **fora do PostgreSQL** (variável
de ambiente montada por volume em dev; cofre em produção); o banco guarda
`template_cifrado`, `iv`, `tag_autenticacao` e `chave_id`, nunca a chave; (2) os
**dados associados (AAD) incluem `tenant_id` e `colaborador_id`**, o que impede
transplantar o template de uma pessoa para outra por `UPDATE` direto; (3)
**versionamento por modelo** (`versao_modelo`, `provedor`, com
`uq_biometria_templates_versao`), para trocar o motor facial sem recadastro
geral; (4) **a imagem crua nunca é persistida**; (5) todo acesso ao template
gera linha em `acessos_dados_sensiveis`. A role `ponto_suporte` (super admin da
SEEG) **não tem `SELECT`** nesta tabela — isso já está no `schema.sql` e não se
mexe. Tentativa de leitura vedada responde `PONTO-LGPD-002`; falta de
consentimento responde `PONTO-LGPD-001` (`biometrias.consentimento_id` aponta
para `consentimentos`, cuja **API** é da F14 — aqui você só respeita a
referência).

**Dispositivo não é terminal.** `dispositivos` é qualquer aparelho capaz de
originar marcação: `terminal`, `celular`, `tablet`, `navegador`, `totem`,
`integracao`. Ele guarda o estado antifraude *conhecido* (`attestation_status`,
`root_detectado`, `emulador_detectado`, `modo_desenvolvedor`, `depuracao_usb`)
— você **cadastra e expõe** esses campos; **quem os avalia é a F14**.
`dispositivo_vinculos` amarra aparelho pessoal a colaborador, com a regra de
negócio **um único dispositivo ativo por colaborador**
(`uq_dispositivo_vinculos_ativo`), e a troca exige aprovação registrada.
Segundo dispositivo ativo responde `PONTO-DISP-006`. Já a tabela **`terminais`**
(o coletor físico Control iD iDFace, com `numero_serie`, modo push, catch-up) e
a tag `terminais` do contrato são da **F6** — não toque. E atenção ao vocabulário
do projeto: **o terminal NÃO é o REP-P**; ele identifica a pessoa e produz um
log de acesso. O REP-P é o nosso software, que atribui o NSR e grava no AFD.

**Importadores.** `POST /v1/colaboradores/importar` recebe CSV ou XLSX e
processa **de forma assíncrona** (resposta `202`), gravando em `importacoes`
(`tipo`, `origem`, `status`, `total_linhas`, `linhas_sucesso`, `linhas_erro`,
`erros` em JSONB e `relatorio_ref` apontando para o objeto no MinIO). A regra é
que **cada linha recusada aparece no relatório com o campo, o código de erro do
catálogo e a mensagem, sem abortar o restante da carga** — carga de 5.000
colaboradores em que a linha 3.117 tem CPF inválido importa 4.999 e reporta uma.
Layout não reconhecido responde `PONTO-IMP-001`; importação já em andamento para
o mesmo alvo, `PONTO-IMP-002`. O `events.yaml` declara
`importacao.concluida` com **`origem: worker`** — ou seja, o processamento roda
no worker (`apps/worker`), não dentro do request. O andaime da Fase 0 criou oito
tarefas de worker e **nenhuma delas é a de importação**: criá-la é entrega desta
fase (§5 e T10).

> **Divergência conhecida, já decidida neste PCF.** A docstring de
> `apps/worker/worker/tarefas/__init__.py` afirma que "as oito tarefas abaixo
> são o conjunto completo previsto para a v1". Isso conflita com
> `packages/contracts/events.yaml`, que declara `importacao.concluida` com
> `origem: worker` — sem tarefa de importação, esse evento **não tem produtor
> possível**. Como `events.yaml` é contrato congelado e o arquivo do worker é
> código de aplicação, prevalece o contrato: **esta fase acrescenta a nona
> tarefa** e atualiza a tabela da docstring junto. Registrado em
> `docs/backlog.md`. Não abra RFC por isso; se encontrar **outra** divergência,
> aí sim.

**A F1 está rodando ao mesmo tempo que você.** Autenticação, RBAC e a resolução
final do tenant são dela. Você codifica contra o módulo
`apps/api/app/core/seguranca.py`, cujas assinaturas estão fixadas na §5 e são
idênticas nos dois PCFs. Enquanto a F1 não preenche os corpos, ele é permissivo
— é o *auth stub* previsto no plano. **Declare `Depends(exigir_permissao("..."))`
em todas as suas rotas mesmo assim**, usando exatamente o `x-permissao` que o
`openapi.yaml` declara para cada operação: quando a F1 ligar a verificação, suas
rotas passam a ser protegidas sem uma linha de mudança.

**Fase 0 é congelada.** `packages/contracts/` não se altera. Se o contrato
estiver errado, o caminho é `docs/rfc/` (protocolo em `docs/rfc/README.md`), não
o contorno silencioso.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia outras fases, não leia o
código da F1.

- `packages/contracts/openapi.yaml` — **apenas** as tags `empresas`, `unidades`,
  `organizacao`, `colaboradores`, `contratos`, `biometria` e `dispositivos` (58
  operações). Leia também, em `components`: `parameters` (`CabecalhoTenant`,
  `CabecalhoRequestId`, `CabecalhoIdempotencia`), `responses`
  (`Erro400`..`Erro429`), o schema `Problema` e os schemas `Importacao` e
  `ImportacaoCriar`.
- `packages/contracts/schema.sql` — seções **3 (ORGANIZACAO)**, **5 (PESSOAS)**
  e **6 (BIOMETRIA E DISPOSITIVOS)**, mais a seção **1** (domínios `dom_cpf`,
  `dom_cnpj`, `dom_pis`, `dom_cep`, `dom_uf`, `dom_ibge`, `dom_cbo`,
  `dom_email`, `dom_sha256`, `dom_fuso`) e a tabela `importacoes` (seção 14).
  Tabelas: `empresas`, `unidades`, `redes_permitidas`, `departamentos`,
  `centros_custo`, `cargos`, `colaboradores`, `contratos`, `vinculos`,
  `colaborador_gestores`, `equipes`, `equipe_membros`, `documentos`,
  `biometrias`, `biometria_templates`, `dispositivos`, `dispositivo_vinculos`,
  `importacoes`.
- `packages/contracts/models/organizacao.py`, `models/pessoas.py`,
  `models/biometria.py` (**exceto** `terminais` e `terminal_saude`, que são da
  F6), `models/integracao.py` (apenas `importacoes`), `models/base.py`,
  `models/mixins.py`, `models/tipos.py`.
- `packages/contracts/errors.yaml` — categorias **VAL** (11 códigos), **CONF**
  (4), **REC** (2), **GEO** (3), **REDE** (2), **DISP** (6), **IMP** (3),
  **LGPD** (4), e os transversais **AUTH-002**, **PERM-001**, **PERM-002**,
  **IDEM-001..003**, **RATE-001**, **INT-001..005**.
- `packages/contracts/events.yaml` — envelope de entrega e os eventos
  `colaborador.admitido`, `colaborador.demitido`, `importacao.concluida`.
- `packages/contracts/glossario.md` — seções **1** e **1.1**; verbetes
  **Allowlist CIDR**, **Biometria / template biométrico**, **Colaborador**,
  **Contrato**, **Coletor**, **Dispositivo**, **Empresa**, **Geocerca**,
  **Matrícula eSocial**, **Tenant**, **Unidade**, **Usuário**, **Vínculo**,
  **Soft delete**; seção **3.1** (subseção `redes_permitidas`); seção **3.2**
  (subseções `contratos` × `vinculos`, `criado_por` e `atualizado_por` sem chave
  estrangeira, referências polimórficas em `anexos`); seção **6 (Termos
  proibidos)**.
- `docs/adr/ADR-006-criptografia-ciclo-vida-template-biometrico.md` — **decisão
  fechada, não redecidir.**
- `docs/adr/ADR-001-multi-tenancy-row-level-security.md` — só para entender por
  que toda consulta sua já vem filtrada pelo banco e por que você não desabilita
  RLS.
- `apps/api/app/core/erros.py`, `apps/api/app/core/catalogo_erros.py`,
  `apps/api/app/db/sessao.py`, `apps/api/app/schemas/contrato.py` (gerado, só
  para conhecer os modelos Pydantic que suas rotas já declaram).
- `apps/worker/worker/filas.py`, `apps/worker/worker/tarefas/__init__.py` e
  `apps/worker/worker/tarefas/integracoes.py` — o padrão de tarefa que você vai
  seguir na T10.
- `docs/rfc/README.md` e `docs/backlog.md`.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas, índices, constraints e policies criadas por
  `apps/api/migrations/versions/0001_inicial.py`.
- Andaime da API: `app/core/erros.py`, `app/core/catalogo_erros.py` (os 112
  códigos), `app/core/contexto.py`, `app/db/sessao.py`, os modelos Pydantic
  gerados em `app/schemas/contrato.py`.
- Modelos SQLAlchemy do pacote `ponto_contracts`.
- `apps/api/app/core/seguranca.py` — o *auth stub* (§5), substituído pela F1
  sem mudança de assinatura.
- Semeadura de `apps/api/migrations/seed_dev.py` (1 tenant, 1 empresa matriz, 1
  unidade sede com geocerca e fuso). **Você não edita esse arquivo** — massa de
  teste da sua fase vive nas suas *fixtures*.
- `apps/worker/worker/filas.py` (nomes de fila) e o padrão
  `resultado_nao_implementado` das tarefas existentes.

**Produz** — esta fase implementa:

*Endpoints (58 operações; hoje `501`):*

| Tag | Operações |
|---|---|
| `empresas` (5) | `listarEmpresas`, `criarEmpresa`, `obterEmpresa`, `atualizarEmpresa`, `excluirEmpresa` |
| `unidades` (8) | `listarUnidades`, `criarUnidade`, `obterUnidade`, `atualizarUnidade`, `excluirUnidade`, `listarRedesPermitidas`, `criarRedePermitida`, `excluirRedePermitida` |
| `organizacao` (18) | `listarDepartamentos`, `criarDepartamento`, `obterDepartamento`, `atualizarDepartamento`, `excluirDepartamento`, `listarCentrosCusto`, `criarCentroCusto`, `obterCentroCusto`, `atualizarCentroCusto`, `listarCargos`, `criarCargo`, `obterCargo`, `atualizarCargo`, `listarEquipes`, `criarEquipe`, `obterEquipe`, `atualizarEquipe`, `adicionarMembroEquipe` |
| `colaboradores` (8) | `listarColaboradores`, `criarColaborador`, `obterColaborador`, `atualizarColaborador`, `excluirColaborador`, `listarGestoresColaborador`, `definirGestoresColaborador`, `importarColaboradores` |
| `contratos` (8) | `listarContratos`, `criarContrato`, `obterContrato`, `atualizarContrato`, `listarVinculos`, `criarVinculo`, `obterVinculo`, `encerrarVinculo` |
| `biometria` (5) | `listarBiometrias`, `criarBiometria`, `obterBiometria`, `revogarBiometria`, `validarBiometria` |
| `dispositivos` (6) | `listarDispositivos`, `criarDispositivo`, `obterDispositivo`, `atualizarDispositivo`, `excluirDispositivo`, `vincularDispositivo` |

A permissão exigida por operação é o valor de `x-permissao` no `openapi.yaml`
(`empresas.criar`, `unidades.editar`, `colaboradores.ler`, `vinculos.criar`,
`biometrias.aprovar`, `dispositivos.editar`, …). Use exatamente esse valor.

*Tabelas escritas:* `empresas`, `unidades`, `redes_permitidas`,
`departamentos`, `centros_custo`, `cargos`, `colaboradores`, `contratos`,
`vinculos`, `colaborador_gestores`, `equipes`, `equipe_membros`, `documentos`,
`biometrias`, `biometria_templates`, `dispositivos`, `dispositivo_vinculos`,
`importacoes`. Escrita **somente de leitura de referência** em
`acessos_dados_sensiveis` (uma linha por acesso a template biométrico).

*Eventos publicados:* `colaborador.admitido` (em `criarVinculo` e nas linhas de
importação que criam vínculo ativo), `colaborador.demitido` (em
`encerrarVinculo`), `importacao.concluida` (ao fim do processamento, com sucesso
total ou parcial). Publique no barramento interno com o **envelope exato** de
`events.yaml` (`id`, `tipo`, `versao`, `ocorridoEm`, `tenantId`, `dados`). **A
entrega por webhook — assinatura HMAC, retentativa exponencial, DLQ, painel — é
da F13**; aqui basta publicar e provar por teste que o *payload* bate campo a
campo com o declarado.

*Tarefa de worker:* `importar_colaboradores`, na fila `FILA_INTEGRACOES`.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- Tags `auth`, `tenants`, `admin`, `auditoria` e as tabelas `usuarios`,
  `credenciais`, `sessoes`, `refresh_tokens`, `mfa_dispositivos`, `perfis`,
  `permissoes`, `perfil_permissoes`, `usuario_perfis`, `delegacoes`,
  `auditoria`, `api_clients`, `api_keys`, `oauth_tokens` (**F1**, rodando em
  paralelo).
- Tag `terminais` e tabelas `terminais`, `terminal_saude` (**F6**). O terminal
  aparece aqui apenas como `dispositivos.tipo = 'terminal'`.
- Tag `lgpd` e tabelas `consentimentos`, `politicas_retencao`,
  `solicitacoes_titular` (**F14**). Você respeita
  `biometrias.consentimento_id`; não implementa os endpoints.
- `GET /v1/importacoes` e `POST /v1/importacoes` (`listarImportacoes`,
  `criarImportacao`, em `app/routers/integracoes.py`) e os exportadores de folha
  (**F13**). Seu importador é **só** `POST /v1/colaboradores/importar`.
- Tags `jornadas`, `escalas`, `feriados`, `afastamentos` e as 13 tabelas do
  grupo jornada (**F3**).
- Tudo de marcação, apuração, banco de horas, fechamento, fiscal, relatórios.
- Avaliação antifraude dos campos de `dispositivos` e o score de confiança
  (**F14**). Você cadastra e expõe; não julga.
- Aplicação da geocerca e da allowlist **no momento de bater ponto** (**F7** e
  **F8**). Você entrega o cadastro e a função de pertencimento.
- `packages/contracts/**` — **congelado**.
- `apps/web`, `apps/mobile`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. **F1, F2 e F9a rodam em paralelo**; nenhuma
outra fase escreve aqui, e você não escreve fora daqui.

| Agente | Caminhos |
|---|---|
| **A1** (estrutura) | `apps/api/app/organizacao/**`<br>`apps/api/app/routers/empresas.py`<br>`apps/api/app/routers/unidades.py`<br>`apps/api/app/routers/organizacao.py`<br>`apps/api/tests/f2/conftest.py`<br>`apps/api/tests/f2/organizacao/**` |
| **A2** (pessoas) | `apps/api/app/pessoas/**`<br>`apps/api/app/comum/documentos.py`<br>`apps/api/app/routers/colaboradores.py`<br>`apps/api/app/routers/contratos.py`<br>`apps/api/tests/f2/pessoas/**` |
| **A3** (biometria, dispositivos, importadores) | `apps/api/app/biometria/**`<br>`apps/api/app/importadores/**`<br>`apps/api/app/routers/biometria.py`<br>`apps/api/app/routers/dispositivos.py`<br>`apps/worker/worker/tarefas/importacoes.py`<br>`apps/worker/worker/filas.py`<br>`apps/worker/worker/tarefas/__init__.py`<br>`apps/api/tests/f2/biometria/**`<br>`apps/api/tests/f2/importadores/**` |

**Compartilhado dentro da fase** (exige combinação entre A1, A2 e A3):

| Caminho | Regra |
|---|---|
| `apps/api/app/comum/__init__.py` | Criado por **A2** na T1, só com docstring. Ninguém acrescenta código. |
| `apps/api/app/comum/documentos.py` | **Criado por A2 na T1, antes de qualquer outra tarefa da fase.** Depois disso, só A2 edita. A1 e A3 apenas importam. Assinaturas fixadas abaixo. |
| `apps/api/tests/f2/conftest.py` | Só **A1** edita. É onde nasce a *fixture* de tenant + empresa + unidade usada pelos três agentes. |

Assinaturas fixadas de `apps/api/app/comum/documentos.py` (não mude os nomes; o
corpo é seu):

```python
def somente_digitos(valor: str) -> str: ...
def cpf_valido(valor: str) -> bool: ...
def cnpj_valido(valor: str) -> bool: ...
def pis_valido(valor: str) -> bool: ...
```

**Compartilhado com a F1 — atenção, risco real de colisão:**

| Caminho | Regra de convivência |
|---|---|
| `apps/api/pyproject.toml` | Ambas as fases acrescentam dependências. **Acrescente apenas dentro do seu bloco**, delimitado por `# --- F2 ---` e `# --- fim F2 ---` na lista `dependencies`, criando o bloco no fim da lista se ele não existir. **Nunca reordene, remova ou reformate linha existente, nem toque no bloco da F1.** Antes de acrescentar, confira se a dependência já está declarada em outro bloco — não duplique. Dependências previstas para a F2: `openpyxl` (XLSX) e `cryptography` (AES-256-GCM). |
| `apps/api/app/core/seguranca.py` | **Contrato entre F1 e F2.** Conteúdo literal inicial abaixo, idêntico ao do PCF da F1. Quem chegar primeiro cria o arquivo exatamente assim; **a F2 nunca o altera depois**. A implementação real é da **F1/A3**, que preenche os corpos sem mudar nenhuma assinatura pública. Mudança de assinatura exige RFC. |

```python
"""Autenticacao e autorizacao da API. CONTRATO ENTRE FASES.

As assinaturas publicas deste modulo estao fixadas nos PCFs da F1 e da F2 e
NAO mudam sem RFC. A implementacao real e da F1 (agente A3). Ate ela existir,
os corpos abaixo sao o "auth stub" com que a F2 trabalha em paralelo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends


@dataclass(frozen=True, slots=True)
class Sujeito:
    """Quem esta chamando. A F1 preenche a partir do JWT validado."""

    usuario_id: UUID | None = None
    tenant_id: UUID | None = None
    email: str = ""
    perfis: tuple[str, ...] = ()
    permissoes: frozenset[str] = frozenset()
    delegacao_id: UUID | None = None
    autenticado: bool = False


async def obter_sujeito() -> Sujeito:
    """Dependencia FastAPI: o sujeito da requisicao corrente."""
    return Sujeito()


def exigir_permissao(codigo: str) -> Callable[..., Awaitable[Sujeito]]:
    """Fabrica de dependencia. `codigo` e o `x-permissao` da operacao."""

    async def _verificar(sujeito: Sujeito = Depends(obter_sujeito)) -> Sujeito:
        # Stub permissivo. A F1 levanta PONTO-PERM-001 quando faltar `codigo`.
        return sujeito

    return _verificar


def exigir_alcance(
    sujeito: Sujeito,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
) -> None:
    """Alcance hierarquico. Stub: nao restringe.

    A F1 levanta PONTO-PERM-002 quando o alvo estiver fora da arvore do gestor.
    """
    return None
```

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**`, `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/erros.py`, `apps/api/app/core/catalogo_erros.py`,
`apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`,
`apps/api/app/main.py`, `apps/api/migrations/**`, `apps/api/tests/test_andaime.py`,
`apps/api/app/routers/{auth,tenants,admin,auditoria,terminais,integracoes,lgpd}.py`,
`.github/workflows/**`, `infra/**`, `Makefile`, `tasks.ps1`, `apps/web/**`.

> **Nenhuma migration nova nesta fase.** `0001_inicial.py` já cria as 92
> tabelas, os 182 índices, os 21 gatilhos, os 11 domínios e as policies de RLS.
> Se você achar que precisa de uma migration, o contrato está errado: abra RFC.

## 6. Tarefas (T1..Tn)

### T1 — Validadores de documento e fixture da fase
**Agentes:** A2 (validadores) e A1 (fixture) — **primeira tarefa, nada começa antes**
**Descrição:** A2 cria `apps/api/app/comum/documentos.py` com as quatro funções
da §5, implementando o dígito verificador de CPF, CNPJ e PIS/PASEP/NIT, e
rejeitando as sequências de dígito repetido (`00000000000`, `11111111111`, …),
que passam na conta e não são documentos válidos. A1 cria
`apps/api/tests/f2/conftest.py` com a *fixture* que sobe PostgreSQL 16, aplica
`alembic upgrade head` e semeia 1 tenant, 1 empresa matriz, 1 filial e 2
unidades (uma com geocerca de ponto+raio, outra com polígono).
**Pronto quando:** teste parametrizado cobre CPF, CNPJ e PIS válidos e
inválidos, incluindo os repetidos, e `pytest apps/api/tests/f2 -q` coleta com a
*fixture* subindo e derrubando o banco.

### T2 — Empresas
**Agente:** A1
**Descrição:** CRUD das 5 operações da tag `empresas`, com validação de CNPJ
(`PONTO-VAL-003`), coerência matriz/filial (`ck_empresas_matriz`), CNPJ único
por tenant (`PONTO-CONF-001`), **soft delete** (`excluido_em`/`excluido_por`) e
recusa de exclusão com dependentes (`PONTO-CONF-004`).
**Pronto quando:** as 5 operações respondem conforme o contrato; teste prova que
filial sem `matriz_id` é recusada e que CNPJ duplicado no mesmo tenant é
`PONTO-CONF-001`.

### T3 — Unidades, geocerca e allowlist CIDR
**Agente:** A1
**Descrição:** CRUD das unidades, incluindo fuso (`dom_fuso`), as duas formas de
geocerca e as três operações de `redes-permitidas`. Implementar duas funções
puras e testáveis: `dentro_da_geocerca(unidade, latitude, longitude, precisao_m)`
— honrando `geocerca_tolerancia_metros` e `geocerca_obrigatoria`, tratando
polígono côncavo e polígono com vértice inicial repetido — e
`ip_autorizado(empresa_id, unidade_id, canal, ip)` sobre `redes_permitidas`,
com IPv4 **e** IPv6.
**Pronto quando:** existe um conjunto de casos de mesa com coordenadas reais
(dentro, fora, na borda, dentro-da-tolerância) e resultado esperado explícito;
teste prova que `2001:db8::/32` é aceito e que IP fora da lista produz
`PONTO-REDE-001`.

### T4 — Departamentos, centros de custo, cargos e equipes
**Agente:** A1
**Descrição:** As 18 operações da tag `organizacao`. Hierarquia de
`departamentos` e `centros_custo` com **detecção de ciclo** (`PONTO-CONF-003`) e
código único por empresa. `cargos` com validação de CBO de 6 dígitos.
`equipes` + `equipe_membros`, com a constraint `EXCLUDE` de participação
sobreposta (`PONTO-VAL-010`).
**Pronto quando:** teste prova que tentar tornar um departamento filho do
próprio neto é recusado, e que adicionar o mesmo colaborador à mesma equipe em
períodos sobrepostos é `PONTO-VAL-010`.

### T5 — Colaboradores
**Agente:** A2
**Descrição:** As 5 operações de CRUD da tag `colaboradores`, com validação de
CPF (`PONTO-VAL-002`) e PIS/NIT (`PONTO-VAL-004`), unicidade de `matricula` e de
`cpf` por tenant+empresa, `nome_social` respeitado em toda exibição, soft delete
e busca por nome usando o índice trigram já criado
(`ix_colaboradores_nome_trgm`). Guardar sempre só dígitos nos documentos.
**Pronto quando:** as operações respondem conforme o contrato; teste prova que
CPF com máscara é aceito na entrada e gravado sem máscara; busca por nome
parcial devolve resultado usando o índice (verifique com `EXPLAIN`).

### T6 — Contratos e vínculos
**Agente:** A2
**Descrição:** As 8 operações da tag `contratos`. Respeitar a distinção
contrato × vínculo (§2). Amarrar `ck_contratos_dispensa` (art. 62 da CLT).
`matricula_esocial` única por tenant+empresa. Sobreposição de vínculo ativo na
mesma empresa recusada com `PONTO-VAL-010`, **e vínculos simultâneos em
empresas diferentes aceitos**. `encerrarVinculo` grava `data_fim`,
`motivo_desligamento` e muda `status` para `encerrado`.
**Pronto quando:** teste prova os dois lados da constraint `EXCLUDE`
(sobreposição na mesma empresa recusada; simultaneidade em empresas diferentes
aceita); e teste prova que `controle_jornada = false` sem
`dispensa_controle_motivo` é recusado.

### T7 — Hierarquia de gestores
**Agente:** A2
**Descrição:** `listarGestoresColaborador` e `definirGestoresColaborador` sobre
`colaborador_gestores`, com vigência datada, **um único gestor imediato vigente
por colaborador** (`ex_colaborador_gestores_imediato`), detecção de ciclo
(`PONTO-CONF-003`) e uma função de árvore `subordinados_de(gestor_id, data)` que
a F1 e a F10 vão consumir.
**Pronto quando:** teste prova que dois gestores imediatos vigentes na mesma
data são recusados; teste prova que A→B→A é recusado; e a função de árvore
devolve o conjunto correto para uma hierarquia de 3 níveis.

### T8 — Eventos de domínio de admissão e desligamento
**Agente:** A2
**Descrição:** Publicar `colaborador.admitido` em `criarVinculo` com status
ativo e `colaborador.demitido` em `encerrarVinculo`, com o **envelope exato** de
`events.yaml` e todos os campos `required` do `payload` preenchidos.
**Pronto quando:** teste valida o corpo publicado contra o `payload` declarado
em `packages/contracts/events.yaml`, campo a campo, incluindo os `required`.

### T9 — Biometria e dispositivos
**Agente:** A3
**Descrição:** As 5 operações de `biometria` e as 6 de `dispositivos`. Cifra do
template em **AES-256-GCM** com envelope, chave mestra fora do banco lida de
variável de ambiente, **AAD contendo `tenant_id` e `colaborador_id`**,
versionamento por `versao_modelo`, **imagem crua nunca persistida**, uma
credencial ativa por colaborador e modalidade, ciclo
`pendente → ativa → revogada|expirada` com `validarBiometria` sendo a aprovação
do RH. Toda leitura de template grava linha em `acessos_dados_sensiveis`.
`vincularDispositivo` respeitando **um dispositivo ativo por colaborador**
(`PONTO-DISP-006`).
> **Nota verificada:** a permissão `biometrias.aprovar`, exigida por
> `validarBiometria`, está entre as **30 permissões que `migrations/seed_dev.py`
> ainda não semeia** (lista em `docs/backlog.md`). Quem completa o catálogo é a
> **F1/A3**, na T8 dela. Declare `Depends(exigir_permissao("biometrias.aprovar"))`
> normalmente: com o *auth stub* permissivo isso não bloqueia você agora, e
> passa a valer sozinho quando a F1 semear a linha.

**Pronto quando:** teste lê `template_cifrado` direto do banco e prova que o
conteúdo é ilegível sem a chave; teste prova que decifrar com AAD de **outro**
colaborador falha (não devolve vetor errado — falha); teste prova que o segundo
vínculo ativo de dispositivo é recusado; e nenhum log contém bytes do template.

### T10 — Importador CSV/XLSX de colaboradores
**Agente:** A3
**Descrição:** `POST /v1/colaboradores/importar` responde `202` e enfileira.
Criar a tarefa `importar_colaboradores` em
`apps/worker/worker/tarefas/importacoes.py`, registrá-la em `TAREFAS` e em
`__all__` de `worker/tarefas/__init__.py`, atualizar a tabela da docstring desse
arquivo (que hoje lista oito tarefas) e mapeá-la para `FILA_INTEGRACOES` em
`FILA_POR_TAREFA`, em `worker/filas.py` — seguindo exatamente o padrão dos
módulos de tarefa já existentes. O processamento grava `importacoes`, valida linha a linha, **não
aborta a carga por causa de uma linha ruim**, acumula os erros em `erros`
(JSONB) com campo, código do catálogo e mensagem, gera o relatório e publica
`importacao.concluida`. Layout desconhecido é `PONTO-IMP-001`; importação já em
andamento é `PONTO-IMP-002`; arquivo acima do limite é `PONTO-VAL-008`; tipo de
conteúdo não suportado é `PONTO-VAL-009`.
**Pronto quando:** um arquivo de **5.000 linhas** com pelo menos 50 linhas
defeituosas distribuídas (CPF inválido, PIS inválido, matrícula duplicada,
empresa inexistente, data incoerente) importa 4.950, reporta 50 com número de
linha e código de erro, e conclui dentro do limite do critério de aceite 7 da
§7. Rodar **duas vezes** o mesmo arquivo não duplica colaborador.

### T11 — Fechamento
**Agente:** A1, A2 e A3
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório
da fase, item a item contra a §7.
**Pronto quando:** todos verdes, com saída colada, e `git status --short packages/contracts`
vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **CRUD completo conforme o OpenAPI**: as 58 operações das 7 tags deixaram de
   responder `501`; `python tools/conferir_rotas.py` continua dizendo
   `Inventario identico ao contrato`.
2. **Validação de CPF, CNPJ e PIS** por dígito verificador, com os códigos
   `PONTO-VAL-002`, `PONTO-VAL-003` e `PONTO-VAL-004`, rejeitando também as
   sequências de dígito repetido.
3. **Geocerca aceita polígono e calcula pertencimento corretamente**, incluindo
   polígono côncavo, ponto exatamente na borda e ponto dentro da tolerância; e
   ponto+raio funciona de forma independente.
4. **Allowlist CIDR aceita IPv4 e IPv6** e a verificação de pertencimento
   respeita o escopo (empresa, unidade opcional, canal opcional).
5. **Template biométrico ilegível sem a chave**: lido direto do banco, o
   conteúdo não revela o vetor; e a decifragem com AAD de outro colaborador
   **falha**, não devolve valor diferente.
6. **Um dispositivo ativo por colaborador** e **uma credencial biométrica ativa
   por colaborador e modalidade** — a segunda tentativa é recusada com o código
   do catálogo.
7. **Importador processa 5.000 colaboradores com relatório de erros linha a
   linha**, sem abortar a carga, com número da linha e código de erro do
   catálogo por linha recusada, e é **idempotente** (reprocessar o mesmo arquivo
   não duplica). Conclui em **menos de 5 minutos** em máquina de
   desenvolvimento; registre o tempo real medido.
8. **Vínculos simultâneos** em empresas diferentes do mesmo tenant são aceitos;
   sobrepostos na mesma empresa são recusados com `PONTO-VAL-010`.
9. **Um único gestor imediato vigente** por colaborador em qualquer data, e
   ciclo na hierarquia é recusado.
10. **Eventos `colaborador.admitido`, `colaborador.demitido` e
    `importacao.concluida`** são publicados com o envelope e o *payload* exatos
    de `events.yaml`, validados campo a campo por teste.
11. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o
    `x-permissao` do contrato — verificável por um teste que percorre o
    `openapi.yaml` e confere rota a rota.
12. **Nenhum segredo versionado**: a chave mestra da biometria vem de variável
    de ambiente; só `infra/.env.example` está no repositório.
13. **Contrato intacto**: `git status --short packages/contracts` vazio.
14. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa
`.\tasks.ps1`; Linux/macOS usa `make`.

Subir o banco:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis
```

```powershell
.\tasks.ps1 up
```

Migrar:

```bash
cd apps/api && alembic upgrade head
```

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
mypy apps packages
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura:

```bash
cd apps/api && pytest tests/f2 -q --cov=app --cov-report=term-missing
```

**Saída esperada:** todos passam; nenhum `skip` nos testes que exigem banco —
teste pulado não conta como verde.

Teste de carga do importador (o critério 7 da §7), com o tempo medido impresso:

```bash
cd apps/api && pytest tests/f2/importadores -q -k "cinco_mil" -s
```

Regressão do andaime da Fase 0 e do worker:

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

```bash
cd apps/worker && python -c "from worker.tarefas import NOMES_DAS_TAREFAS as n; print(len(n)); print(n)"
```

**Saída esperada:** as 8 tarefas do andaime **mais** `importar_colaboradores`
(9), e a importação do pacote sem erro.

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:**
`Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato não foi tocado:

```bash
git status --short packages/contracts
```

**Saída esperada:** nada.

## 9. Proibições

1. **Não edite `packages/contracts/`** — `openapi.yaml`, `schema.sql`,
   `models/`, `errors.yaml`, `events.yaml`, `design-tokens.json`,
   `glossario.md`. Divergência vira RFC em `docs/rfc/`, no formato de
   `docs/rfc/README.md`.
2. **Não crie código de erro novo.** Os 112 códigos de `errors.yaml` são o
   conjunto fechado. Faltou um? RFC.
3. **Não crie migration nova.** `0001_inicial.py` já cria tudo.
4. **Não desabilite RLS**, nem em *fixture* de teste, nem conectando como
   superusuário "para simplificar".
5. **Não implemente autenticação, RBAC, resolução de tenant nem trilha de
   auditoria** — é da **F1**, rodando agora em paralelo. Não edite
   `app/core/middleware.py`, `app/core/seguranca.py`, `app/db/sessao.py`,
   `app/main.py` nem `migrations/seed_dev.py`.
6. **Não altere as assinaturas de `app/core/seguranca.py`**, e não preencha os
   corpos dele: o *stub* permissivo é proposital e a implementação é da F1.
7. **Não toque na tag `terminais` nem nas tabelas `terminais` e
   `terminal_saude`** — F6. Terminal aqui é só
   `dispositivos.tipo = 'terminal'`.
8. **Não implemente `listarImportacoes`/`criarImportacao`** (`/v1/importacoes`,
   em `app/routers/integracoes.py`) nem exportador de folha — **F13**.
9. **Não julgue os sinais antifraude** de `dispositivos` (`attestation_status`,
   `root_detectado`, `modo_desenvolvedor`, …). Cadastre e exponha; a política e
   o score são da **F14**.
10. **Não persista imagem facial crua** em lugar nenhum: nem em banco, nem em
    objeto, nem em log, nem em arquivo temporário que sobreviva à requisição.
    ADR-006 é decisão fechada.
11. **Não devolva template biométrico decifrado** por nenhuma rota da API, nem
    "para depuração". Leitura de template gera linha em
    `acessos_dados_sensiveis`.
12. **Não aborte a importação inteira por causa de uma linha ruim.** O relatório
    linha a linha é o requisito, não um extra.
13. **Não use os termos proibidos** da seção 6 do glossário: é *marcação*
    (nunca "batida"), *tratamento* (nunca "ajuste de marcação"), *colaborador*
    (nunca "funcionário" no código), *coletor* (nunca "relógio de ponto"),
    *tenant* (nunca "empresa" para dizer cliente do SaaS).
14. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída
    real.** "Deve funcionar" não é evidência.
