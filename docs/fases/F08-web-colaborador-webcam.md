# F08 — Web colaborador e registro por webcam

| | |
|---|---|
| **Onda** | 3 |
| **Agentes** | 3 · **A1** portal do colaborador (sessão/login, espelho de ponto, saldo e extrato de banco de horas, solicitações, comprovantes, perfil, PWA instalável) · **A2** registro por webcam (captura ao vivo, prova de vida com desafio aleatório, detecção de câmera virtual, feedback de confirmação) · **A3** controles de acesso ao registro (allowlist CIDR, fingerprint de dispositivo, reautenticação, mensagens de erro que não vazam a regra) |
| **Duração estimada** | 8 dias |
| **Depende de** | F1 (identidade/RBAC — API real), F5 (ingestão de marcações/NSR — API real), F9a (design system — componentes prontos) |
| **Criticidade** | Alta — é a primeira fase que faz `apps/web` chamar a API de verdade. Erros de fronteira aqui (sessão, allowlist, prova de vida) se propagam para a F9b, que corre em paralelo na mesma onda |
| **Branch** | `f08-web-colaborador-webcam` |

---

## 1. Objetivo

Ao fim desta fase, **um colaborador abre `/eu` no navegador, autentica de verdade contra
`POST /v1/auth/login`, vê seu espelho de ponto e saldo de banco de horas, abre solicitações,
consulta comprovantes e registra o próprio ponto pela webcam — com captura ao vivo (nunca
upload de arquivo), prova de vida por desafio aleatório, detecção de câmera virtual, allowlist de
rede por CIDR, fingerprint de dispositivo e reautenticação quando a política exigir —, tudo contra
os endpoints reais de `POST /v1/marcacoes` e das tags `auth`, `marcacoes`, `comprovantes`,
`solicitacoes`, `banco-horas` já implementadas por fases anteriores**, como um PWA instalável com
Lighthouse ≥ 90 em desempenho e acessibilidade.

**O que esta fase explicitamente não faz:** workflow de aprovação de solicitações (decidir
etapas, delegar, escalonar — isso é da **F10**, que ainda não existe; esta fase só **cria** e
**lista** solicitações, ver §2), dashboards e cadastros de RH/gestor (**F9b**, mesma onda, fase
irmã — não sua), qualquer regra de cálculo de apuração ou banco de horas (**F4**, já concluída —
você só **lê** o resultado), qualquer mudança em `packages/contracts/` ou em
`apps/web/src/componentes/{ui,dominio}/` (**F9a**, congelado — você **consome**), e nenhuma linha
de `apps/api`/`apps/worker` (você não corrige stub de backend nem redecide comportamento de
motor de confiança — ver §2, é achado, não tarefa sua). Se você está prestes a editar um arquivo
em `apps/api`, pare: não é desta fase.

## 2. Contexto mínimo

**O produto, em três frases.** SEEG Ponto é um sistema de ponto eletrônico brasileiro do tipo
**REP-P** (*Registrador Eletrônico de Ponto via Programa*, Portaria MTP 671/2021), SaaS
multiempresa: cada cliente é um **tenant**, com suas empresas, unidades e pessoas. Marcação é o
registro de um instante em que alguém bateu o ponto — **append-only e imutável por exigência
legal**; a única forma de corrigir jornada é o **tratamento**, uma camada separada (F4) que nunca
toca a marcação. Nesta fase você constrói a porta de entrada do **colaborador** (a pessoa, não o
vínculo) pelo navegador: ver os próprios dados e registrar o próprio ponto.

**O estado de `apps/web` hoje — leia antes de escrever qualquer linha.** A Fase 0 entregou o
esqueleto (Next.js 15, App Router, React 19, TypeScript, Tailwind v4, pnpm) e a F9a entregou o
design system inteiro: primitivos (`src/componentes/ui/**`), seis componentes de domínio
(`src/componentes/dominio/**`: `LinhaDoTempoDeMarcacoes`, `CartaoDeSaldoDeBanco`, `GradeDeEscala`,
`SeletorDePeriodo`, `TabelaDeDados`, `Graficos`), tema dois-modos com `data-tema`, Storybook e o
aparato de acessibilidade. As rotas `/` (login), `/eu` (portal do colaborador — **sua**) e
`/painel` (RH/gestor — **F9b**, fase irmã, não sua) hoje são `PlaceholderDeFase`
(`src/componentes/andaime/placeholder-de-fase.tsx`) — leia `src/app/eu/page.tsx` por inteiro
antes de apagá-lo: ele já resume o escopo esperado e cita a invariante legal mais importante do
produto (marcação nunca é editada, só tratamento). O cliente HTTP tipado
(`src/lib/api/cliente.ts`, gerado a partir do `openapi.yaml`) já existe e já injeta
`Idempotency-Key` em toda escrita e `Authorization`/`X-Tenant` a partir de duas funções-gancho —
`definirProvedorDeToken(provedor)` e `definirTenant(tenant)` — mas **nenhuma fase anterior as
chamou de verdade**: são módulo-nível, mutáveis, hoje sempre `undefined`. **Confirmado por
leitura de código, não suposição:** não existe hoje em `apps/web` nenhum hook de sessão, nenhuma
tela de login funcional, nenhum `middleware.ts`, nenhuma persistência de token. **Esta é a
primeira fase que integra `apps/web` de verdade com `POST /v1/auth/login`.** O comentário em
`src/app/page.tsx` e em `src/componentes/provedor-de-consultas.tsx` atribuindo isso à "F1" é texto
remanescente da Fase 0: o escopo real da F1 (`FASES-E-AGENTES.md`, Onda 1) é só `apps/api` —
autenticação, multi-tenancy, RBAC — e nunca tocou `apps/web`. Você não redecide nada da F1 (o
backend de auth já está pronto e testado); você **constrói o lado do cliente que nunca existiu**.

**A F9b (painel RH/gestor) roda em paralelo, na mesma onda, e reusa o login e a sessão desta
fase — decisão já fixada pelo orquestrador, coordenando os dois PCFs.** `docs/fases/
F09b-painel-rh-gestor.md` existe e **não constrói login próprio**: `/painel/layout.tsx` monta o
mesmo `ProvedorDeSessao` de `src/lib/sessao/**` (import direto do módulo desta fase — F9b não cria
um segundo `ProvedorDeSessao` nem uma segunda tela de login) e, sem sessão válida, redireciona
para `/?returnTo=/painel` em vez de ter sua própria rota `/painel/entrar`. Isso existe porque a
primeira versão do PCF de F9b (escrita em paralelo a esta, sem visibilidade da decisão desta fase)
havia projetado sua própria sessão em `sessionStorage` — mecanismo mais fraco (token legível por
qualquer script da página, superfície maior para roubo via XSS) do que o cookie `httpOnly` que
você constrói aqui. O orquestrador decidiu, ao revisar os dois PCFs antes do build, que **existe
um único módulo de sessão no produto, desta fase, e as duas áreas o consomem** — não duas
implementações paralelas de qualidade desigual.

**Contrato fixado da interface exportada por `src/lib/sessao/**` (não mude a forma sem avisar
quem consome — é o mesmo tipo de assinatura fixada que a F4 usou entre agentes):**
```ts
export function ProvedorDeSessao(props: { children: React.ReactNode }): JSX.Element;
export function useSessao(): {
  usuario: { id: string; nome: string; email: string } | null;
  tenant: { slug: string; nomeExibicao: string } | null;
  autenticado: boolean;
  carregando: boolean;
  entrar: (credenciais: { email: string; senha: string; tenant?: string }) => Promise<{ mfaRequerido: boolean }>;
  verificarSegundoFator: (codigo: string) => Promise<void>;
  sair: () => Promise<void>;
};
```
`useSessao()` **não** inclui `permissoes`/`perfis` (isso é `SessaoAtual`, de `GET /v1/auth/sessao`)
— a F9b precisa de RBAC granular por permissão e você não; ela faz sua própria chamada a
`obterSessaoAtual` (TanStack Query) por cima de `autenticado`, sem precisar que este módulo mude.
Você só garante que, uma vez `autenticado === true`, o cliente HTTP (`definirProvedorDeToken`) já
manda `Authorization` em toda chamada — inclusive nas de F9b.

**`/` precisa navegar para `returnTo` depois do login, não sempre para `/eu`** (ver T1): qualquer
área que redirecionar para `/` sem sessão (você mesma, para `/eu`; a F9b, para `/painel`) anexa
`?returnTo=<rota-de-origem>`; seu formulário de login lê esse parâmetro, valida que é um caminho
relativo seguro (começa com exatamente uma `/`, nunca `//` ou uma URL absoluta — proteção contra
*open redirect*) e navega para lá após sucesso; sem o parâmetro (ou inválido), o padrão continua
sendo `/eu`.

Por isso mesmo, esta fase **não toca** `src/componentes/andaime/cabecalho-do-andaime.tsx` nem
`src/app/layout.tsx` (o cabeçalho de navegação "andaime" que hoje lista as três rotas de prova):
decidir a navegação definitiva do produto depois que login, `/eu` **e** `/painel` existirem é
decisão de quando a F9b também tiver rodado, não sua. Sua tela `/eu` ganha sua própria casca de
navegação, aninhada (`src/app/eu/layout.tsx`), sem mexer no cabeçalho global.

**O endpoint único de registro, e o que ele já aplica de verdade hoje.** Não existe endpoint
separado para "registro por webcam": `POST /v1/marcacoes` (`criarMarcacao`) é
**canal-agnóstico** — terminal, app, navegador e integração chamam exatamente a mesma operação,
com o mesmo corpo `MarcacaoCriar`, diferindo apenas no campo `canal` (aqui, sempre `"web"`).
Confirmado por leitura de `apps/api/app/marcacao/pipeline/ingestao.py` (F5, já concluída e
testada — você não a reescreve, só a consome pela rota HTTP): a função `registrar_marcacao` já
aplica, **de verdade, hoje**, nesta ordem — geocerca (`PONTO-GEO-001/002`, quando a política e
lat/long exigem), **allowlist CIDR** (`PONTO-REDE-001`, via `app.organizacao.redes.ip_autorizado`,
quando `politicas_registro.exige_rede_permitida`), vínculo de dispositivo pessoal (só para
`canal='mobile'`, não afeta você), **reautenticação recente** (`PONTO-AUTH-011`, checando
`sessoes.reautenticado_em` contra uma janela de 15 minutos, **só para `canal='web'`** — isto é
literalmente o requisito "reautenticação para bater ponto" do seu escopo, e o backend já o
impõe) e, por fim, o **score de confiança** (`app.marcacao.confianca.motor.avaliar_confianca`).//
**Achado confirmado, não invenção:** este motor de confiança é hoje um **stub permissivo**,
documentado explicitamente no próprio módulo como pertencente à **F14** (Onda 5, ainda não
executada): ele sempre devolve `score=100`, `classificacao="alta"`, **ignorando** todos os sinais
recebidos em `flagsIntegridade` (incluindo `cameraVirtual`, `mockLocation`, `rootDetectado`
etc.). Na prática, **hoje**, `PONTO-SCORE-001..004` nunca são levantados pelo servidor, **por
desenho desta fase anterior, não por bug seu**. Isso tem uma consequência direta e inevitável
para o critério de aceite "OBS Virtual Camera é detectada e bloqueada": **o bloqueio, hoje, só
pode acontecer no cliente, antes de chamar a API** — ver T8. Você continua enviando o sinal
`flagsIntegridade.cameraVirtual` honesto no corpo (para quando a F14 rodar, o sinal já estar
fluindo), mas não pode depender do servidor para bloquear.

**A allowlist CIDR já é aplicada pelo servidor — você não a reimplementa, só trata o erro.**
`redes_permitidas` (F2) e `ip_autorizado()` (`app/organizacao/redes.py`) já existem, e
`ingestao.py` já os invoca para qualquer canal quando `politicas_registro.exige_rede_permitida`
é verdadeiro, recusando com `PONTO-REDE-001` (403, `expoe_regra: false` — a mensagem ao
colaborador **não** deve citar a faixa CIDR configurada). Um comentário antigo em
`app/organizacao/redes.py` diz "aplicar a regra no momento de bater ponto é da F8" — está
desatualizado: a F5 (posterior a esse comentário) já aplicou. O IP de origem é resolvido no
servidor a partir da requisição HTTP (inclusive atrás de proxy reverso); isso é infraestrutura de
backend, fora do seu ownership. **Sua responsabilidade em relação à allowlist é inteiramente do
lado da exibição do erro** (§9, T13) — não existe, e você não cria, uma segunda fonte de verdade
sobre quais faixas são permitidas.

**Bloqueio de VPN/proxy/ASN de datacenter (`PONTO-REDE-002`) — decisão explícita: não
implementado nesta fase, e aqui está o porquê.** `politicas_registro.bloquear_vpn_proxy` existe
como coluna (default `false`) mas, **confirmado por leitura de `_politica_efetiva` em
`ingestao.py`**, essa coluna nunca é lida para dentro de `_PoliticaEfetiva` — ou seja, **nenhum
código do backend hoje verifica esse sinal**, e não existe em lugar nenhum do repositório uma
consulta de reputação de ASN. `FASES-E-AGENTES.md` já qualifica este item como **"bloqueio
opcional"** no escopo da F8, o que bate com o achado: não há mecanismo servidor para acioná-lo. A
detecção de VPN por JavaScript de navegador é, por natureza, frágil (falsos positivos bloqueiam
VPN corporativa legítima; falsos negativos dão falsa sensação de segurança) — e o próprio
catálogo de erros já resolve o caso legítimo dizendo, em `PONTO-REDE-002.acao_sugerida`, "se a
VPN corporativa for legítima, peça a inclusão da faixa na allowlist" — ou seja, o mecanismo real
pretendido é a allowlist CIDR (que você já tem), não uma heurística de VPN no cliente. **Decisão
fixada por este PCF: você não implementa detecção de VPN/proxy/ASN nesta fase**, nem no cliente
nem propondo mudança de backend. Registre em `docs/backlog.md` (T14) que
`politicas_registro.bloquear_vpn_proxy` está com coluna sem leitor, candidato a RFC quando a F14
(dona de "reputação do aparelho") ou outra fase decidir implementá-lo — **isso não bloqueia seu
critério de aceite**, que fala apenas de allowlist CIDR e câmera virtual.

**Solicitações — o que existe no contrato e o que ainda responde 501.** As tags `solicitacoes` e
`aprovacoes` **têm operações definidas** no `openapi.yaml` (`GET/POST /v1/solicitacoes`,
`GET/POST/{id}/cancelar`, `GET /v1/tipos-solicitacao`, `GET /v1/aprovacoes`,
`POST /v1/aprovacoes/{id}/decidir`) — não é um contrato ausente. Mas, **confirmado lendo
`apps/api/app/routers/solicitacoes.py`**, o router ainda é o *stub* da Fase 0: toda operação
responde `501`/`PONTO-INT-005`, porque implementar o workflow de aprovação (etapas, prazo,
escalonamento, delegação) é escopo da **F10** (Onda 4, ainda não executada). **Decisão fixada por
este PCF:** você constrói a tela de solicitações (listar, abrir uma nova de tipo ajuste de
ponto/abono/férias/folga/compensação) chamando as operações **reais** do contrato — não é
invenção de rota, é o mesmo `criarSolicitacao`/`listarSolicitacoes` que a F10 vai implementar por
trás —, mas a interface **precisa lidar bem com `501` hoje**: mostrar um estado "recurso ainda não
disponível nesta versão" (nunca uma tela quebrada ou um erro genérico), sem impedir a navegação.
No dia em que a F10 substituir o *stub* por comportamento real, **nenhuma linha do seu código
muda** — é exatamente esse o valor de consumir o contrato real desde já. **Achado adicional para
`docs/backlog.md` (T14):** `TipoSolicitacao.exigeAnexo` existe, mas não há, em nenhum lugar do
contrato, operação de upload de arquivo nem campo de referência a anexo em `SolicitacaoCriar` —
não invente um campo dentro de `payload` (que é `additionalProperties: true`, mas isso não
autoriza um protocolo privado não documentado); quando o tipo escolhido exigir anexo, a tela
apenas avisa que anexo ainda não é suportado e permite prosseguir só com a justificativa textual.

**Vocabulário obrigatório — os termos da seção 6 do glossário valem em toda tela, rótulo,
mensagem e nome de variável.** Nunca "batida" (é **marcação**); nunca "editar
marcação"/"corrigir marcação"/"deletar marcação" (é **tratamento**, e você nem chama a API de
tratamento nesta fase — só lê apuração já calculada); nunca "cálculo" solto (é **apuração**);
nunca "funcionário" (é **colaborador**, a pessoa, ou **vínculo**, a relação); nunca "banco
positivo/negativo" (é **saldo credor/saldo devedor** — o `CartaoDeSaldoDeBanco` da F9a já
implementa isso, você só consome); nunca "empresa" para dizer cliente do SaaS (é **tenant**).

**Todo componente novo que você escrever segue as mesmas regras de token da F9a, mesmo que você
não edite os arquivos dela.** Você não toca em `src/componentes/{ui,dominio}/**`, mas os
componentes novos desta fase (tela de login, modal de reautenticação, captura de webcam,
confirmação de registro) **consomem os mesmos tokens semânticos** (`var(--cor-...)`,
`var(--espacamento-...)`, `var(--camada-...)`) e seguem a mesma régua de acessibilidade (alvo de
toque 44×44 px, anel de foco 2 px com deslocamento 2 px, `prefers-reduced-motion`, WCAG 2.2 AA):
nenhum valor literal de cor/espaçamento/raio/sombra/`z-index`, nunca um token primitivo direto.
Isso é responsabilidade sua, verificada por uma cópia própria do teste de varredura da F9a
(§6, T14) sobre os diretórios novos desta fase — a varredura da F9a (`src/testes/design-system/
varredura-de-literais.teste.ts`) só cobre `componentes/ui/**` e não é sua para editar.

**Autenticação/sessão — a arquitetura que esta fase constrói, e por quê.** Não existe ADR sobre
armazenamento de token no frontend; esta fase decide. O `accessToken` (JWT de vida curta) vive
**só em memória**, através da função já pronta `definirProvedorDeToken` de `src/lib/api/cliente.ts`
— nunca em `localStorage`/`sessionStorage` (evita exfiltração por XSS). O `refreshToken` (rotativo,
de uso único — `docs/adr/` não tem ADR dedicado, mas o contrato já documenta o reuso como
revogação de família inteira) vive em cookie **`httpOnly`, `Secure`, `SameSite=Lax`**, porque
JavaScript de página não pode nem deveria lê-lo. Como `Set-Cookie` só é respeitado pelo navegador
quando vem da mesma origem da página, login/refresh/logout **não são chamados direto do
navegador para a origem da API** — passam por três *Route Handlers* Next.js
(`src/app/api/auth/{login,refresh,logout}/route.ts`, mesmo padrão de `src/app/api/health/
route.ts` já existente) que fazem a chamada servidor-a-servidor (`URL_API_INTERNA`) e manipulam o
cookie. `POST /v1/auth/reautenticar`, ao contrário, **não** precisa de proxy: usa o
`accessToken` já em memória via `Authorization: Bearer`, então é uma chamada comum do cliente
`api` existente.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia o código de F1/F2/F3/F4/F5/F6 (só os pontos
citados explicitamente acima, já resumidos), não leia a F9b (não existe PCF dela ainda).

- `packages/contracts/openapi.yaml` — tag **auth** por inteiro (`/v1/auth/login`,
  `/v1/auth/mfa/verificar`, `/v1/auth/refresh`, `/v1/auth/logout`, `/v1/auth/reautenticar`,
  `/v1/auth/sessao`, `/v1/auth/sessoes`, `/v1/auth/senha/recuperar`, `/v1/auth/senha/redefinir`);
  `/v1/tenants/atual` (dados públicos do tenant para a tela de login); tag **marcacoes**: apenas
  `POST /v1/marcacoes` (`criarMarcacao`) e `GET /v1/marcacoes` (`listarMarcacoes`) — leia também o
  bloco `x-vedacao-legal` no fim do path, que documenta por que `PUT`/`PATCH`/`DELETE` não existem
  e nunca existirão; tag **comprovantes** (`GET /v1/comprovantes`, `GET /v1/comprovantes/{id}`);
  tag **solicitacoes** (todas as 5 operações) e **aprovacoes** (`GET /v1/aprovacoes`, somente para
  saber que existe, você não a chama) e `GET /v1/tipos-solicitacao`; tag **banco-horas**:
  `obterExtratoBancoHoras`, `obterSaldoBancoHoras`; tag **apuracoes**: `listarApuracoes`,
  `obterApuracao` (somente leitura); tag **colaboradores**: `obterColaborador` (para a tela de
  perfil); tag **dispositivos**: `listarDispositivos` (para "sessões e dispositivos" no perfil).
  Nos `components`: schemas `LoginRequisicao`, `LoginResposta`, `MfaVerificacaoRequisicao`,
  `RefreshRequisicao`, `LogoutRequisicao`, `ReautenticacaoRequisicao`, `ReautenticacaoResposta`,
  `SessaoAtual`, `Tenant`, `Marcacao`, `MarcacaoCriar`, `MarcacaoCriada`, `Comprovante`,
  `Solicitacao`, `SolicitacaoCriar`, `TipoSolicitacao`, `ListaSolicitacao`, `ApuracaoDia`,
  `SaldoBancoHoras`, `ExtratoBancoHoras`, `Problema`, `ErroCampo`, e os `parameters`
  (`CabecalhoTenant`, `CabecalhoRequestId`, `CabecalhoIdempotencia`, `Cursor`, `Limite`,
  `Ordenar`) e `responses` (`Erro400`..`Erro503`). **Não leia as tags `terminais`, `fiscal`,
  `webhooks`, `admin`, `integracoes`.**
- `packages/contracts/errors.yaml` — categorias **AUTH** (001, 002, 003, 004, 006, 010, 011, 013),
  **SCORE** (001..004), **REDE** (001, 002), **GEO** (001..003), **DISP** (001, 002 — 003/004/005
  são mobile/RASP, leia só para saber que existem e por que não te dizem respeito), **MARC**
  (001..010), **IDEM** (001..003), **VAL** (001, 005, 006, 007, 009, 010, 011), **PERM** (001, 002,
  004, 005), **TEN** (001..004), **RATE** (001), **CONF** (001), **REC** (001), **LGPD** (001).
  Leia o cabeçalho do arquivo (convenções, especialmente `expoe_regra`) com atenção — é a base do
  seu dicionário de mensagens (T13).
- `packages/contracts/events.yaml` — apenas para saber que `marcacao.criada`, `marcacao.suspeita`
  e `comprovante.emitido` são publicados pelo servidor na mesma transação de `criarMarcacao`; você
  não os consome nesta fase (não há canal de push/websocket no escopo), só sabe que existem.
- `packages/contracts/glossario.md` — seções **1**, **1.2 (Imutabilidade)**, verbetes
  **Marcação**, **Tratamento**, **Apuração**, **Banco de horas**, **Crédito**, **Débito**,
  **Escala**, **Colaborador**, **Vínculo**, **Tenant**, **Score de confiança**, **NSR**,
  **Canal**, **Sessão**; seção **6 (Termos proibidos)** por inteiro.
- `FASES-E-AGENTES.md` — seção 1 inteira (protocolo, já lido antes de escrever este PCF — releia
  se tiver dúvida sobre ownership/RFC) e a entrada de **F8** na Onda 3 (já citada acima).
- `apps/web/src/app/eu/page.tsx`, `apps/web/src/app/page.tsx`,
  `apps/web/src/componentes/andaime/placeholder-de-fase.tsx` — o que existe hoje, e por quê (não
  edite `placeholder-de-fase.tsx`, é compartilhado com a F9b via `/painel`).
- `apps/web/src/lib/api/**` (`cliente.ts`, `config.ts`, `erros.ts`, `index.ts`) — o cliente HTTP
  tipado, os ganchos `definirProvedorDeToken`/`definirTenant`, a classe `ErroDaApi`/`Problema`.
  **Você usa este cliente, não cria um segundo.**
- `apps/web/src/app/api/health/route.ts` — o único *Route Handler* já existente; é o padrão de
  forma que os três novos (`auth/login`, `auth/refresh`, `auth/logout`) seguem.
- `apps/web/src/app/layout.tsx`, `apps/web/src/componentes/andaime/cabecalho-do-andaime.tsx` — leia
  para entender o que existe hoje; **não edite nenhum dos dois** (ver §2, coordenação com F9b).
- `apps/web/src/componentes/tema/**`, `apps/web/src/estilos/tokens.gerado.css` (só para saber os
  nomes de variável — não edite, é gerado), `apps/web/src/componentes/dominio/**` (leia as
  assinaturas de *props*, não a implementação, de `LinhaDoTempoDeMarcacoes`, `CartaoDeSaldoDeBanco`,
  `TabelaDeDados`, `SeletorDePeriodo` — você **consome** estes componentes prontos).
- `apps/web/src/testes/design-system/varredura-de-literais.teste.ts` — leia como modelo de forma
  do mecanismo que você replica (T14) para os diretórios novos desta fase.
- `apps/web/package.json`, `apps/web/vitest.config.ts`, `apps/web/eslint.config.mjs`,
  `apps/web/tsconfig.json`, `apps/web/next.config.ts`, `apps/web/.storybook/main.ts` (só para
  confirmar que o glob de *stories* já cobre qualquer `*.stories.tsx` novo, sem precisar editar a
  config).
- `apps/api/app/marcacao/pipeline/ingestao.py` — **leia por inteiro**, é a fonte de verdade de
  tudo que o servidor já aplica em `criarMarcacao` (geocerca, allowlist, dispositivo, reautenticação,
  score). **Não edite este arquivo — é fora do seu ownership (`apps/api` inteiro é congelado para
  esta fase) —, leia só para saber exatamente o que esperar de volta.**
- `apps/api/app/marcacao/confianca/motor.py` — leia a docstring do módulo e o corpo de
  `avaliar_confianca`; é a prova de que o *stub* é permissivo por desenho (F14), não bug.
- `apps/api/app/organizacao/redes.py` — leia a docstring e `ip_autorizado`; é a prova de que a
  allowlist já é aplicada pelo servidor.
- `apps/api/app/routers/solicitacoes.py` — leia só o topo (docstring do módulo); é a prova de que
  o router ainda é *stub* 501.
- `docs/rfc/README.md` e `docs/backlog.md` — protocolo de RFC e onde registrar achados.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- `POST /v1/auth/login`, `POST /v1/auth/mfa/verificar`, `POST /v1/auth/refresh`,
  `POST /v1/auth/logout`, `POST /v1/auth/reautenticar`, `GET /v1/auth/sessao`,
  `GET/DELETE /v1/auth/sessoes{,/{id}}`, `POST /v1/auth/senha/recuperar`,
  `POST /v1/auth/senha/redefinir`, `GET /v1/tenants/atual` — **API real, F1, concluída**.
- `POST /v1/marcacoes` (`criarMarcacao`, canal `web`), `GET /v1/marcacoes` (`listarMarcacoes`) —
  **API real, F5, concluída**, com geocerca/allowlist/reautenticação já aplicados no servidor (§2).
- `GET /v1/comprovantes`, `GET /v1/comprovantes/{id}` — **API real, F5, concluída**.
- `GET /v1/banco-horas/{colaboradorId}/extrato`, `GET /v1/banco-horas/{colaboradorId}/saldo` —
  **API real, F4, concluída**.
- `GET /v1/apuracoes`, `GET /v1/apuracoes/{id}` — **API real, F4, concluída**.
- `GET /v1/colaboradores/{id}`, `GET /v1/dispositivos` — **API real, F2, concluída**.
- `GET/POST /v1/solicitacoes`, `GET /v1/solicitacoes/{id}`,
  `POST /v1/solicitacoes/{id}/cancelar`, `GET /v1/tipos-solicitacao` — **contrato real, handler
  ainda 501 (F10 pendente)** — você chama do mesmo jeito, tratando o 501 com uma UI honesta (§2).
- Design system da F9a: `src/componentes/{ui,dominio}/**`, `src/estilos/tokens.gerado.css`,
  `src/componentes/tema/**` — congelado, só leitura/uso.
- Cliente HTTP: `src/lib/api/**` (`api`, `definirProvedorDeToken`, `definirTenant`, `ErroDaApi`,
  `Problema`, tipos gerados) — você **liga** os ganchos que já existem, não cria um segundo
  cliente.
- `src/app/api/health/route.ts` — padrão de forma para os *Route Handlers* novos.

**Produz** — esta fase implementa:

*Rotas (`apps/web/src/app/**`):*

| Rota | O que faz | Agente |
|---|---|---|
| `/` | Login real (substitui o placeholder da Fase 0) | A1 |
| `/eu` (layout + página) | Casca de navegação do colaborador + espelho do dia/saldo resumido | A1 |
| `/eu/extrato` | Espelho de período + extrato de banco de horas | A1 |
| `/eu/solicitacoes`, `/eu/solicitacoes/nova` | Lista e criação de solicitação | A1 |
| `/eu/comprovantes` | Lista e detalhe de comprovante | A1 |
| `/eu/perfil` | Dados do colaborador, dispositivos, sessões ativas | A1 |
| `/eu/registrar` | Registro de ponto por webcam | A2 |
| `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` | *Route Handlers* que manipulam o cookie `httpOnly` do refresh token | A1 |

*Módulos novos publicados dentro da fase (ver §5 para caminho exato):* módulo de sessão
(`lib/sessao/**`), dicionário de erros e *wrapper* de acesso controlado (`lib/seguranca/**`),
detecção de prova de vida e câmera virtual (`lib/deteccao/**`), componentes novos
(`componentes/sessao/**`, `componentes/seguranca/**`, `componentes/registro-webcam/**`), ganchos
novos em `ganchos/**`.

*PWA:* `manifest.ts` aprofundado, *service worker* novo (via `@serwist/next`), `next.config.ts`
com o *wrapper* do *service worker* (única exceção ao "andaime intocado" da Fase 0, análoga à
exceção pontual que a F04 teve em `schema.sql`).

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- Workflow de aprovação de solicitações (decidir etapa, delegar, escalonar) — **F10**. Você só
  cria e lista; não implementa a máquina de estados.
- Qualquer motor de cálculo, apuração ou banco de horas — **F4**, concluída. Você só lê.
- `/painel` e tudo que é RH/gestor — **F9b**, fase irmã desta mesma onda. Você não escreve lá, e
  não redesenha `cabecalho-do-andaime.tsx` nem `layout.tsx` (ver §2).
- `packages/contracts/**` e `src/componentes/{ui,dominio}/**` — **congelado (F9a)**. Precisa de um
  primitivo novo ou de um token que não existe? É RFC, você não inventa.
- Qualquer arquivo em `apps/api/**` ou `apps/worker/**` — inclusive o *stub* permissivo de
  `avaliar_confianca` e o router 501 de `solicitacoes`. Você não “corrige” nenhum dos dois nesta
  fase; ambos são achados documentados, não tarefas.
- Detecção de VPN/proxy/ASN de datacenter (`PONTO-REDE-002`) — decisão explícita de não
  implementar nesta fase (§2). Registre o achado, não invente heurística.
- App mobile Flutter (**F7**, adiada nesta sessão — não assuma nada sobre ela).
- Biometria facial como **credencial cadastrada** (enrollment, tag `biometrias`) — **F2**,
  concluída. Você não cadastra template facial; a captura da F8 é **prova de presença no momento
  do registro**, não cadastro.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase.

| Agente | Caminhos |
|---|---|
| **A1** (portal do colaborador) | `apps/web/src/app/page.tsx`<br>`apps/web/src/app/eu/layout.tsx`, `apps/web/src/app/eu/page.tsx`, `apps/web/src/app/eu/extrato/**`, `apps/web/src/app/eu/solicitacoes/**`, `apps/web/src/app/eu/comprovantes/**`, `apps/web/src/app/eu/perfil/**`<br>`apps/web/src/app/api/auth/**` (novo)<br>`apps/web/src/app/manifest.ts`<br>`apps/web/src/app/sw.ts` (novo, fonte do *service worker*)<br>`apps/web/next.config.ts` (só o *wrapper* do *service worker* — ver nota abaixo)<br>`apps/web/src/lib/sessao/**` (novo)<br>`apps/web/src/componentes/sessao/**` (novo)<br>`apps/web/src/ganchos/use-sessao.ts`, `use-espelho-de-ponto.ts`, `use-banco-de-horas.ts`, `use-solicitacoes.ts`, `use-tipos-solicitacao.ts`, `use-comprovantes.ts`, `use-perfil.ts` (novos)<br>`apps/web/src/lib/formatacao-f8/**` (novo — ver nota de `formatacao` compartilhada abaixo)<br>`apps/web/src/testes/f8/portal/**` |
| **A2** (registro por webcam) | `apps/web/src/app/eu/registrar/**` (novo)<br>`apps/web/src/componentes/registro-webcam/**` (novo)<br>`apps/web/src/lib/deteccao/**` (novo)<br>`apps/web/src/ganchos/use-captura-webcam.ts`, `use-prova-de-vida.ts` (novos)<br>`apps/web/playwright.config.ts` (novo)<br>`apps/web/e2e/**` (novo)<br>`apps/web/public/mediapipe/**`, `apps/web/public/modelos/**` (novo — assets auto-hospedados, ver T7)<br>`apps/web/src/testes/f8/webcam/**` |
| **A3** (controles de acesso) | `apps/web/src/lib/seguranca/**` (novo)<br>`apps/web/src/componentes/seguranca/**` (novo)<br>`apps/web/src/ganchos/use-reautenticacao.ts` (novo)<br>`apps/web/src/testes/f8/seguranca/**` |

**Compartilhado dentro da fase** (exige combinação entre os três agentes):

| Caminho | Regra |
|---|---|
| `apps/web/package.json` | Cada agente acrescenta suas dependências **em ordem alfabética** dentro de `dependencies`/`devDependencies`, sem reordenar nem remover linha alheia. **A1** adiciona `serwist` (dependency) e `@serwist/next` (devDependency) — PWA — e `react-hook-form` + `zod` (dependency) — formulários com validação e mapeamento de `errosCampo`. **A2** adiciona `@mediapipe/tasks-vision` (dependency) e `@playwright/test` (devDependency) — a `playwright` (browser automation) já existe como devDependency da F9a, mas o executor de testes E2E (`@playwright/test`) ainda não. **A3** não deve precisar de dependência nova; se precisar, mesma regra. Scripts novos (`test:e2e`, por exemplo) vão ao fim do bloco `scripts`, sem tocar nos existentes. Combine quem roda `pnpm install` por último antes de fechar a fase (regenera `pnpm-lock.yaml`). |
| `apps/web/next.config.ts` | Exceção pontual e estreita ao andaime da Fase 0 (mesmo espírito da exceção única que a F04 teve em `schema.sql` para a RFC-013): **só A1** edita, e só para envolver `nextConfig` com `withSerwistInit` (ou equivalente do pacote escolhido). Nenhuma outra opção do arquivo muda. `output: "standalone"` continua — confirme que o plugin escolhido é compatível antes de integrar. |
| `apps/web/src/lib/api/cliente.ts`, `config.ts`, `erros.ts`, `index.ts` | **Nenhum dos três agentes edita.** É o cliente pronto da Fase 0; vocês só **chamam** `definirProvedorDeToken`/`definirTenant` a partir de `lib/sessao/**` (A1). Precisar de uma mudança de forma no cliente é RFC. |
| Formatação de domínio | A F9a já entrega `src/lib/formatacao/**` (minutos → `HH:MM`, CPF/PIS mascarado etc.) — **congelado, você consome, não edita**. Se precisar de uma função nova específica desta fase (por exemplo, formatar protocolo de solicitação), crie em `src/lib/formatacao-f8/**` (seu próprio diretório, novo), nunca dentro do diretório da F9a. |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):

| Caminho | Por quê |
|---|---|
| `packages/contracts/**` | Congelado (F9a/F0). |
| `apps/web/src/componentes/{ui,dominio}/**`, `src/componentes/graficos/**` | Congelado (F9a). Precisa de variante nova? É RFC. |
| `apps/web/src/estilos/tokens.gerado.css`, `apps/web/scripts/tokens-para-css.mjs` | Gerado (F0/F9a). |
| `apps/web/src/lib/api/**`, `apps/web/scripts/tipos-da-api.mjs` | Cliente e tipos gerados; vocês consomem via `lib/sessao`/`lib/seguranca`, não editam. |
| `apps/web/src/componentes/tema/**` | Mecanismo de tema da F0/F9a. `data-tema` é a única verdade sobre o tema. |
| `apps/web/src/componentes/andaime/placeholder-de-fase.tsx`, `apps/web/src/app/painel/**` | Compartilhado com a F9b (o placeholder ainda serve `/painel`). Você para de usar o componente em `/eu`, mas não o apaga nem o edita. |
| `apps/web/src/componentes/andaime/cabecalho-do-andaime.tsx`, `apps/web/src/app/layout.tsx` | Navegação global "andaime"; decisão de substituí-la é de quando F8 **e** F9b já tiverem rodado (§2). Sua casca de navegação vive em `src/app/eu/layout.tsx`, aninhada, sem tocar aqui. |
| `apps/web/.storybook/**` | Config da F9a. O glob de *stories* já cobre qualquer `*.stories.tsx` novo em `src/**`; se sua *story* não aparece, é problema do **seu** arquivo, não da config. |
| `apps/web/src/testes/design-system/**`, `apps/web/src/testes/dominio/**`, `apps/web/src/testes/andaime.teste.tsx` | Testes de outras fases; não edite nem duplique — se precisar de varredura equivalente para seus diretórios novos, crie a sua própria em `src/testes/f8/**` (T14). |
| `apps/web/Dockerfile`, `apps/web/postcss.config.mjs`, `apps/web/tsconfig.json` | Andaime da F0. Não deveriam precisar mudar; se precisarem, registre o motivo no relatório. |
| Qualquer arquivo em `apps/api/**`, `apps/worker/**`, `apps/mobile/**`, `apps/device-gw/**`, `apps/facial-svc/**`, `infra/**`, `.github/**` | Fora do produto desta fase por completo. |

## 6. Tarefas (T1..T14)

### T1 — Sessão, login e o *wrapper* de token (A1) — primeira tarefa, bloqueia A2 e A3
**Agente:** A1
**Descrição:** Três *Route Handlers* (`src/app/api/auth/{login,refresh,logout}/route.ts`, mesmo
padrão de forma de `api/health/route.ts`): `login` chama `POST {URL_API_INTERNA}/v1/auth/login`
(e, quando `mfaRequerido`, expõe o fluxo de `POST /v1/auth/mfa/verificar` do mesmo jeito) e, na
resposta `200`, grava `refreshToken` num cookie `httpOnly; Secure; SameSite=Lax; Path=/api/auth`
e devolve ao cliente **apenas** `{ accessToken, expiresIn, usuario, tenant }` (nunca o
refreshToken); `refresh` lê o cookie, chama `POST /v1/auth/refresh`, regrava o cookie rotacionado
e devolve o novo `accessToken`; `logout` lê o cookie, chama `POST /v1/auth/logout` e limpa o
cookie (`Max-Age=0`) mesmo se a chamada upstream falhar. Módulo `src/lib/sessao/**`: um cliente
(`chamarLogin`, `chamarRefresh`, `chamarLogout`) que fala só com os três *Route Handlers* acima
(nunca direto com a origem da API), e um `ProvedorDeSessao` (contexto React) que, ao montar,
tenta silenciosamente `chamarRefresh()` uma vez (sessão sobrevive a F5), chama
`definirProvedorDeToken(() => accessTokenEmMemoria)` e `definirTenant(tenant.slug)` do cliente
existente, e expõe exatamente a interface fixada em §2 (`{ usuario, tenant, autenticado,
carregando, entrar, verificarSegundoFator, sair }`) — **esta forma é contrato para a F9b, não
mude sem avisar**. `src/app/page.tsx`: formulário de login real (`react-hook-form` + `zod`;
e-mail, senha, campo de tenant quando `GET /v1/tenants/atual` não resolve por subdomínio),
tratando `mfaRequerido` com um segundo passo de código TOTP; após sucesso, lê `?returnTo=` da URL
(`useSearchParams`), valida que começa com exatamente uma `/` (nunca `//` nem esquema `http`/
`https` — proteção contra *open redirect*) e navega para lá; sem parâmetro válido, navega para
`/eu`. `src/app/eu/layout.tsx`: guarda de rota (redireciona para `/?returnTo=/eu` quando
`!autenticado` e `!carregando` — o `returnTo` aqui é redundante com o padrão, mas mantém o mesmo
mecanismo uniforme que `/painel`, F9b, usa) e casca de navegação do colaborador (início, extrato,
solicitações, comprovantes, perfil, sair) — **sem tocar** em `cabecalho-do-andaime.tsx`.
**Pronto quando:** login com credencial válida navega para `/eu`; login a partir de
`/?returnTo=/painel` navega para `/painel` após sucesso (teste prova a validação do `returnTo`:
`/painel` aceito, `//evil.com` e `https://evil.com` rejeitados e tratados como ausentes);
recarregar a página em `/eu` mantém a sessão (refresh silencioso); logout limpa o cookie e volta
para `/`; login com senha errada mostra `PONTO-AUTH-001`/`006` mapeado (dicionário provisório até
T13 existir — pode usar `problema.title` como texto temporário, documentado como temporário);
teste (Vitest + Testing Library, mockando os três `route.ts` com MSW ou *handlers* de teste) prova
as afirmações acima sem subir a API real.

### T2 — Ganchos de consulta e painel `/eu` (A1)
**Agente:** A1
**Descrição:** Ganchos TanStack Query em `src/ganchos/`: `use-espelho-de-ponto.ts`
(`GET /v1/marcacoes?colaboradorId=&de=&ate=`), `use-banco-de-horas.ts` (`obterSaldoBancoHoras`,
`obterExtratoBancoHoras`), consumindo `definirTenant`/token já ligados por T1. `src/app/eu/
page.tsx`: painel do dia — `LinhaDoTempoDeMarcacoes` (F9a) com as marcações de hoje,
`CartaoDeSaldoDeBanco` (F9a) com o saldo atual, e um botão de destaque para `/eu/registrar`
(link simples; você não implementa a captura aqui, é A2). Estado vazio (nenhuma marcação hoje),
estado de carregamento (`Skeleton`, F9a) e estado de erro (`ErroDaApi`, mensagem amigável).
**Pronto quando:** *story* ou teste cobre os três estados (vazio, carregado, erro); nenhuma
marcação é inferida como entrada/saída (a linha do tempo só mostra instantes, como a F9a já
implementa); axe sem violação `serious`/`critical` na tela.

### T3 — `/eu/extrato` (A1)
**Agente:** A1
**Descrição:** Espelho de período (usa `SeletorDePeriodo` da F9a) sobre `listarMarcacoes` e
`listarApuracoes` (mostrando `ApuracaoDia` — horas normais, extras, adicional noturno já
calculados pela F4, só leitura), e extrato completo de banco de horas
(`obterExtratoBancoHoras`, paginado via `Cursor`/`Limite` do contrato) usando `TabelaDeDados`
(F9a) para a lista de lançamentos.
**Pronto quando:** troca de período recarrega os dados certos; paginação por cursor funciona
(próxima página, sem duplicar nem pular item); nenhuma coluna mostra "banco positivo/negativo" —
sempre saldo credor/devedor com sinal por forma e cor, herdado do `CartaoDeSaldoDeBanco`.

### T4 — Solicitações e comprovantes (A1)
**Agente:** A1
**Descrição:** `src/app/eu/solicitacoes/page.tsx` (lista, `listarSolicitacoes?minhas=true`) e
`src/app/eu/solicitacoes/nova/page.tsx` (formulário: `GET /v1/tipos-solicitacao` popula o
seletor de categoria — ajuste de ponto, abono, férias, folga, compensação —, campos
`dataReferencia`/`dataInicio`/`dataFim`/`descricao` conforme a categoria, `payload` específico
por categoria documentado no componente; `POST /v1/solicitacoes` com `zod` validando client-side
e mapeando `Problema.errosCampo` de volta aos campos do formulário em caso de `400`/`422`).
**Tratamento explícito do 501:** enquanto o *stub* da F10 não muda, qualquer resposta
`PONTO-INT-005` renderiza um estado "disponível em breve" com o motivo (workflow de aprovação
ainda não implementado), não uma tela de erro genérica nem um formulário que trava. Quando
`tipoSolicitacao.exigeAnexo` é verdadeiro, a tela avisa que anexo não é suportado nesta versão
(ver achado de backlog, §2) e permite prosseguir só com a justificativa. `src/app/eu/
comprovantes/page.tsx` (lista, `listarComprovantes`) e detalhe (`obterComprovante` — número, NSR,
hash, texto do comprovante).
**Pronto quando:** teste prova que submeter com um tipo que exige justificativa e campo vazio
mostra erro de validação **antes** de chamar a API; teste prova que a resposta `501` de
`criarSolicitacao` renderiza o estado "em breve", não uma exceção não tratada; teste prova que a
mesma chamada, mockada para devolver `201` com o schema real de `Solicitacao`, renderiza a
confirmação — provando que o código já está pronto para quando a F10 existir.

### T5 — Perfil e PWA (A1)
**Agente:** A1
**Descrição:** `src/app/eu/perfil/page.tsx`: dados do colaborador (`obterColaborador`),
dispositivos vinculados (`listarDispositivos`), sessões ativas (`GET /v1/auth/sessoes`) com botão
de revogar (`DELETE /v1/auth/sessoes/{id}`). PWA: aprofundar `manifest.ts` (adicionar
`categories`, confirmar `display`/ícones — já corretos desde a F0); *service worker* via
`@serwist/next` (`src/app/sw.ts`, *precache* dos ativos estáticos e do *shell* de `/eu`,
estratégia *network-first* para chamadas de API, **nunca** cachear `POST /v1/marcacoes` nem
qualquer escrita); `next.config.ts` envolvido com o *wrapper* do plugin (única edição
autorizada neste arquivo, §5).
**Pronto quando:** revogar uma sessão diferente da atual funciona e some da lista; revogar a
sessão atual desloga; `pnpm build` gera o *service worker*; Lighthouse (via `lighthouse-ci` local
ou relatório do Chrome DevTools contra o build de produção) ≥ 90 em Performance e Acessibilidade
para `/` e `/eu` — cole os números reais no relatório.

### T6 — Captura ao vivo via `getUserMedia` (A2) — depende de T1
**Agente:** A2
**Descrição:** `src/componentes/registro-webcam/captura-de-video.tsx`: pede permissão de câmera
(`navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })`), renderiza o `<video>`
ao vivo, trata os três estados de permissão (concedida, negada, indisponível) com mensagem clara
em cada um. **Nunca** existe um `<input type="file">` nem qualquer caminho de upload de imagem
neste componente ou em qualquer tela desta fase — é proibição de produto, não só de código (§9).
`src/ganchos/use-captura-webcam.ts`: encapsula o ciclo de vida da `MediaStream` (abre ao montar,
fecha as *tracks* ao desmontar — vazamento de câmera ligada é falha grave de privacidade).
**Pronto quando:** teste (Playwright, com a *flag* do Chromium `--use-fake-device-for-media-stream`
para simular uma câmera real em CI — ver T9) prova que o vídeo começa a exibir quadros; teste
prova que fechar/navegar para fora da tela libera a câmera (o indicador de gravação do SO
apagaria — em teste, prova-se checando que todas as `track.readyState` viram `"ended"`); busca
estática no código-fonte prova que não existe `<input type="file"` em `src/app/eu/registrar/**`
nem em `src/componentes/registro-webcam/**`.

### T7 — Prova de vida com desafio aleatório (A2)
**Agente:** A2
**Descrição:** Desafio concreto, fixado por este PCF: sorteado entre três opções — "pisque duas
vezes", "vire o rosto para a esquerda", "vire o rosto para a direita" — exibido com um contador
regressivo de **4 segundos** a partir do instante em que aparece na tela. Detecção via
**`@mediapipe/tasks-vision`** (`FaceLandmarker`, executado inteiramente no navegador via WASM —
**auto-hospede o *fileset* WASM e o modelo `face_landmarker.task` em `public/mediapipe/**`/
`public/modelos/**`**, carregado via `FilesetResolver.forVisionTasks(<caminho-local>)`, nunca
apontando para o CDN padrão do Google — mesmo princípio de auto-hospedagem que a F0 já aplicou
às fontes, ver comentário em `layout.tsx`). Carregue o modelo com `import()` dinâmico, só quando
`/eu/registrar` monta (não infla o *bundle* de `/eu`). Critério de aprovação, fixado por este PCF
para que o teste seja determinístico: **piscar** = *Eye Aspect Ratio* (calculado a partir dos
*landmarks* dos olhos) cai abaixo de `0.20` por ≥ 2 quadros consecutivos, contado 2 vezes dentro
da janela; **virar o rosto** = ângulo de guinada (`yaw`, das `facialTransformationMatrixes` do
`FaceLandmarker`) cruza ±15° a partir do neutro, sustentado por ≥ 3 quadros consecutivos, no
sentido pedido. Falhar dentro da janela permite nova tentativa (até 3 no total); na terceira
falha, mostra a mesma orientação de `PONTO-SCORE-002.acao_sugerida` (repita com boa iluminação;
copie o texto do catálogo, não invente um novo) e não insiste — não existe fallback por PIN nesta
fase (isso é escopo do app mobile, F7). `src/lib/deteccao/prova-de-vida.ts`: módulo puro que
recebe uma sequência de resultados de `FaceLandmarker` e devolve `{ aprovado, metodo:
"desafio_ativo", evidencia }` — `evidencia` vira `livenessEvidencia` no corpo de `MarcacaoCriar`.
**Pronto quando:** teste unitário do módulo puro cobre os três desafios com sequências sintéticas
de *landmarks* (fixadas, não capturadas de webcam real) para os casos aprovado, reprovado por
tempo esgotado e reprovado por movimento insuficiente; teste prova que o desafio sorteado muda
entre execuções (não é sempre o mesmo); nenhuma chamada de rede acontece durante a prova de vida
em si (só quando o colaborador confirma o registro, T9).

### T8 — Detecção de câmera virtual (A2)
**Agente:** A2
**Descrição:** `src/lib/deteccao/camera-virtual.ts`, com três sinais documentados (defesa em
profundidade, nenhum sozinho é a prova final):
1. **Rótulo do dispositivo** (sinal primário, alta precisão): `navigator.mediaDevices.
   enumerateDevices()` e compara o `label` de cada `videoinput` (apenas disponível após permissão
   concedida) contra uma lista mantida no próprio módulo, documentada e revisável, de
   substrings conhecidas de câmeras virtuais — no mínimo `"obs virtual camera"`, `"obs-camera"`,
   `"droidcam"`, `"manycam"`, `"snap camera"`, `"camtwist"`, `"xsplit vcam"`, `"iriun"`,
   `"epoccam"` — comparação sem diferenciar maiúsculas/minúsculas.
2. **Capacidades da trilha** (sinal secundário): `MediaStreamTrack.getCapabilities()`/
   `getSettings()` da trilha ativa; sinaliza suspeita quando `frameRate` vem como um valor exato
   fixo sem faixa (`min === max`) fora dos padrões típicos de webcam física (documente os
   padrões considerados normais no módulo, ex. faixas contendo 24/25/30/60).
3. **Repetição de quadro** (sinal secundário, contra vídeo em *loop*): amostra quadros do
   `<video>` em um `<canvas>` a cada ~300 ms por 3 segundos, calcula um hash perceptual simples
   (por exemplo, downscale para 8×8 em tons de cinza e hash de diferença) e sinaliza suspeita se
   o mesmo hash se repete em um período regular.
Qualquer um dos três sinais positivos marca `flagsIntegridade.cameraVirtual = true` **e impede o
envio da marcação no cliente antes de chamar a API** (ver T9 — decisão do §2: o motor de
confiança do servidor é *stub* permissivo hoje, então o bloqueio real só existe aqui). A mensagem
mostrada ao colaborador é copiada verbatim de `PONTO-SCORE-004` (`titulo` +
`acao_sugerida`) — o próprio catálogo já marca este código como `expoe_regra: true`, então dizer
"câmera virtual detectada" ao usuário é a política correta, não vazamento de regra.
**Pronto quando:** teste unitário do sinal 1 cobre pelo menos um rótulo de cada fabricante
listado (casos positivos) e um rótulo de webcam física comum (caso negativo, ex.
"HD WebCam", "FaceTime HD Camera"); teste unitário do sinal 3 prova que uma sequência de quadros
idênticos (sintética) é sinalizada e uma sequência de quadros diferentes não é; teste de
integração (Playwright, ver T9) prova que, com o rótulo de dispositivo simulado como câmera
virtual, `POST /v1/marcacoes` **nunca é chamado** — verificado interceptando a rede, não só a UI.

### T9 — Fluxo de registro e feedback de confirmação (A2) — depende de T7, T8, T11, T12
**Agente:** A2
**Descrição:** `src/app/eu/registrar/page.tsx`: orquestra captura (T6) → desafio de prova de vida
(T7) → checagem de câmera virtual (T8) → montagem do corpo `MarcacaoCriar` (`canal: "web"`,
`fotoBase64` do quadro aprovado, `livenessMetodo`, `livenessEvidencia`, `flagsIntegridade`
— mesclando o sinal de câmera virtual (T8) com o *fingerprint* e demais sinais de A3, T11) →
chamada via o *wrapper* de A3 (`comAcessoControlado`, T12/T13), que já trata reautenticação e
mapeia erro. Três desfechos de tela, visualmente distintos e cada um anunciado por
`aria-live="polite"` (nunca atrasado por animação — mesma regra de produto do token de movimento
da F9a): **sucesso** (`revisaoRequerida === false`) mostra número do comprovante, NSR e horário;
**sucesso com revisão** (`revisaoRequerida === true`) mostra a mesma confirmação com uma nota
neutra de que o gestor vai revisar (nunca alarmante — não é erro); **recusado** mostra a mensagem
do dicionário de erros (A3) mapeada do `codigo` do `Problema`. Idempotência: cada tentativa usa
uma nova chamada do cliente `api` (que já gera `Idempotency-Key` nova por chamada, `cliente.ts`
existente) — você não reusa chave manualmente.
**Pronto quando:** fluxo completo (Playwright, câmera fake) prova captura → desafio aprovado →
`POST /v1/marcacoes` com o corpo esperado (schema validado contra `MarcacaoCriar`) → tela de
sucesso; teste prova que reprovar o desafio 3 vezes não chama a API; teste prova que uma resposta
`401 PONTO-AUTH-011` simulada abre o fluxo de reautenticação de A3 e, aprovado, **reenvia a mesma
tentativa automaticamente** sem o colaborador refazer a captura.

### T10 — E2E e histórias do registro por webcam (A2)
**Agente:** A2
**Descrição:** `playwright.config.ts` (novo): projeto Chromium com
`--use-fake-device-for-media-stream` e `--use-fake-ui-for-media-stream` (concede permissão de
câmera sem diálogo em CI) e vídeo fake fornecido via `--use-file-for-fake-video-capture=<arquivo>`
quando o teste precisa de quadros reais (por exemplo, para o hash de repetição de quadro).
`e2e/registro-webcam.spec.ts` cobre os cenários das T6, T8 e T9 de ponta a ponta contra uma API
mockada (nenhum teste E2E desta fase depende do backend real rodando — ele já está coberto pelos
testes de outras fases). *Stories* (`*.stories.tsx`, colocadas junto de cada componente, sem
tocar `.storybook/**`) para os estados **presentacionais** de `registro-webcam/**` (aguardando
permissão, desafio ativo, sucesso, sucesso com revisão, câmera virtual detectada, erro de rede) —
dirigidas por *props* fixas, nunca por captura de câmera real dentro do Storybook.
**Pronto quando:** `pnpm test:e2e` roda os cenários acima em CI sem hardware de câmera real;
`pnpm build-storybook` inclui as novas *stories* sem editar `.storybook/main.ts` (prova de que o
glob já cobre); axe sem violação `serious`/`critical` nas novas *stories*, nos dois temas.

### T11 — Fingerprint de dispositivo (A3) — depende de T1
**Agente:** A3
**Descrição:** `src/lib/seguranca/fingerprint.ts::calcularFingerprint(): Promise<string>` — só
Web Crypto (`crypto.subtle.digest("SHA-256", …)`), sem biblioteca de terceiros: concatena
`navigator.userAgent`, resolução e profundidade de cor da tela, fuso horário
(`Intl.DateTimeFormat().resolvedOptions().timeZone`), `navigator.language`/`languages`,
`navigator.hardwareConcurrency`, e um hash de *canvas rendering* (desenha uma forma fixa
documentada e lê `toDataURL()`); resultado persistido em `localStorage` sob uma chave
documentada (`ponto:fingerprint`) para ser **estável** entre sessões do mesmo navegador — não
recalculado a cada chamada. Usado em dois lugares: `LoginRequisicao.fingerprint` (via T1, ganho
de A1 mas o campo é preenchido chamando a função de A3) e `flagsIntegridade` de `MarcacaoCriar`
(chave `fingerprint`, dentro de `additionalProperties`, T9).
**Pronto quando:** teste prova que duas chamadas seguidas no mesmo ambiente de teste devolvem o
mesmo valor (estabilidade via `localStorage`); teste prova que o valor muda quando um dos
insumos muda (por exemplo, fuso horário simulado diferente); nenhuma biblioteca de
*fingerprinting* de terceiros foi adicionada ao `package.json`.

### T12 — Reautenticação (A3)
**Agente:** A3
**Descrição:** `src/ganchos/use-reautenticacao.ts` + `src/componentes/seguranca/modal-de-
reautenticacao.tsx` (usa o `Dialog` da F9a — consome, não recria o primitivo): formulário de
senha (e código MFA quando `metodosMfa` do login indicar que o usuário tem TOTP ativo — leia de
`SessaoAtual`) que chama `POST /v1/auth/reautenticar` (chamada direta do cliente `api` existente,
sem *Route Handler* — ver §2, não usa o refresh cookie). Devolve uma *promise* que resolve
quando a reautenticação é aceita, para que quem chamou (T9) possa reenviar a operação original.
**Pronto quando:** teste prova que o modal abre automaticamente ao interceptar
`PONTO-AUTH-011`; teste prova que senha incorreta mostra o erro certo (`PONTO-AUTH-001`
reaproveitado da tela de login, mesmo dicionário de T13) sem fechar o modal; teste prova que
reautenticação aceita fecha o modal e resolve a *promise*.

### T13 — Dicionário de erros e `comAcessoControlado` (A3)
**Agente:** A3
**Descrição:** `src/lib/seguranca/dicionario-de-erros.ts`: um mapa `codigo (PONTO-XXX-NNN) →
mensagem em pt-BR`, cobrindo no mínimo todos os códigos listados na §3 (leia `errors.yaml`,
nunca invente texto para um código que não está lá), parafraseando `titulo`/`acao_sugerida` do
catálogo — para os códigos marcados `expoe_regra: false` no catálogo (`PONTO-SCORE-001`,
`PONTO-GEO-001`, `PONTO-REDE-001`, entre outros), a mensagem **nunca** menciona o parâmetro
interno (faixa CIDR, limiar de score, geocerca) mesmo que o `detail` da resposta um dia venha a
incluir algo — trate isso como defesa em profundidade, não confiança cega no servidor. Uma
função de *fallback* devolve uma mensagem genérica para `codigo` ausente do dicionário (nunca
quebra a tela por um código novo do catálogo). `src/lib/seguranca/com-acesso-controlado.ts`:
função de ordem superior `comAcessoControlado(chamada: () => Promise<T>): Promise<T>` que
executa `chamada`, e se o erro for `ErroDaApi` com `codigo === "PONTO-AUTH-011"`, dispara o fluxo
de reautenticação (T12) e, se aprovado, **reexecuta `chamada` uma única vez** (nunca um laço
infinito); qualquer outro erro é relançado como está, para quem chamou decidir a UI usando o
dicionário. T9 (A2) usa esta função para envolver o `POST /v1/marcacoes`.
**Pronto quando:** teste prova que todo `codigo` citado na §3 tem entrada no dicionário (teste
de cobertura, não promessa); teste prova que `comAcessoControlado` reexecuta exatamente uma vez
após reautenticação aceita, e não entra em laço se a segunda tentativa também falhar com
`PONTO-AUTH-011`; teste prova que um erro diferente de `PONTO-AUTH-011` nunca abre o modal de
reautenticação.

### T14 — Varredura de literais, achados de backlog e fechamento (A1, A2, A3)
**Agentes:** A1, A2 e A3
**Descrição:** Réplica do teste de varredura de literais da F9a (mesma técnica de
`varredura-de-literais.teste.ts`, lido em §3 — **arquivo novo**, não edição do original), em
`src/testes/f8/varredura-de-literais.teste.ts`, cobrindo os diretórios novos desta fase:
`src/app/eu/**`, `src/app/page.tsx`, `src/componentes/{sessao,seguranca,registro-webcam}/**`.
Registrar em `docs/backlog.md`, cada um com fase sugerida: (1) `politicas_registro.
bloquear_vpn_proxy` sem leitor no pipeline de `criarMarcacao` (candidato F14 ou RFC dedicada);
(2) ausência de operação de upload de anexo no contrato apesar de `TipoSolicitacao.exigeAnexo`
existir (candidato F10, quando o workflow de solicitações for implementado de verdade); (3) a
navegação global "andaime" (`cabecalho-do-andaime.tsx`) ainda lista as três rotas de prova e
precisa ser substituída pela navegação definitiva do produto assim que F8 e F9b estiverem
concluídas (não é RFC, é lembrete de integração). Rodar todos os comandos da §8 e colar a saída
real no relatório da fase, item a item contra a §7.
**Pronto quando:** os três achados estão em `docs/backlog.md`; a varredura nova passa sem
violação; todos os comandos da §8 verdes com saída colada; `git status --short packages/contracts
apps/web/src/componentes/ui apps/web/src/componentes/dominio` vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Login real funciona**: `POST /v1/auth/login` via os *Route Handlers* de T1, sessão sobrevive
   a recarregar a página, logout limpa o cookie — evidenciado por teste, não por captura de tela.
   `?returnTo=` navega para a rota pedida após login (`/painel` incluso) e rejeita alvo não
   relativo (proteção contra *open redirect*), habilitando a F9b a reusar este login sem recriar
   um segundo mecanismo.
2. **`/eu` mostra dado real**: espelho do dia, saldo de banco de horas e extrato vêm de
   `GET /v1/marcacoes`, `obterSaldoBancoHoras` e `obterExtratoBancoHoras` reais — nenhum dado
   fixo fora do Storybook.
3. **IP fora da allowlist não consegue registrar e recebe mensagem clara**: `PONTO-REDE-001`
   (aplicado pelo servidor, F5) é mapeado pelo dicionário (T13) para uma mensagem que não cita a
   faixa CIDR — evidência: teste com a chamada mockada devolvendo `PONTO-REDE-001`.
4. **Upload de arquivo de imagem é rejeitado**: não existe, em nenhuma tela desta fase,
   `<input type="file">` no caminho de registro de ponto — só captura ao vivo via `getUserMedia`
   (T6). Verificável por busca estática no código-fonte.
5. **OBS Virtual Camera é detectado e bloqueado**: com um rótulo de dispositivo de câmera virtual
   simulado, nenhuma chamada a `POST /v1/marcacoes` acontece (T8/T9), e a mensagem mostrada é a
   de `PONTO-SCORE-004`.
6. **Prova de vida com desafio aleatório funciona**: o desafio muda entre tentativas, o critério
   de aprovação é determinístico e testado (T7), e reprovar 3 vezes não registra o ponto.
7. **Reautenticação para bater ponto funciona ponta a ponta**: interceptar `PONTO-AUTH-011`,
   reautenticar e reenviar a mesma tentativa automaticamente, sem nova captura (T9/T12/T13).
8. **Solicitações usam o contrato real, tolerando o 501 de hoje**: `criarSolicitacao`/
   `listarSolicitacoes` chamados com o schema exato do contrato; resposta `501` de hoje mostra
   estado "em breve", não erro genérico; mockando `201`, a mesma tela confirma o pedido — prova
   de que o código já funciona para quando a F10 existir.
9. **Nenhuma marcação é editada em lugar nenhum da interface**: nenhuma chamada
   `PUT`/`PATCH`/`DELETE` para `/v1/marcacoes/**` existe no código desta fase — verificável por
   busca estática — e nenhum rótulo de tela usa "editar marcação"/"corrigir marcação"/"batida".
10. **PWA instalável com Lighthouse ≥ 90** em Performance e Acessibilidade para `/` e `/eu`,
    número real colado no relatório (T5).
11. **Nenhum valor literal de cor/espaçamento/raio/sombra/`z-index`** nos componentes novos desta
    fase — verificado pela varredura de T14, mecanismo entregue, não promessa.
12. **Vocabulário obrigatório respeitado** em toda tela, rótulo e mensagem — nenhum termo
    proibido da seção 6 do glossário.
13. **`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, `pnpm test:e2e`,
    `pnpm build-storybook` e `pnpm test:storybook` verdes**, e `src/testes/andaime.teste.tsx`
    continua passando.
14. **Contrato e design system intactos**: `git status --short packages/contracts
    apps/web/src/componentes/ui apps/web/src/componentes/dominio` vazio.
15. Três achados de `docs/backlog.md` (T14) registrados, com fase sugerida.
16. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir de `apps/web`, salvo onde indicado. Confira os *scripts* reais em `package.json`
antes de rodar — os que aparecem abaixo já existem hoje, exceto os marcados **(novo)**, que esta
fase acrescenta ao final do bloco `scripts` (T5/T10).

```bash
pnpm install
```

Tokens sincronizados (ninguém desta fase deveria ter tocado o gerado):

```bash
pnpm tokens:check
```

Lint, formatação, tipos, testes e build:

```bash
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build
```

**Saída esperada:** ESLint sem erro; Prettier sem arquivo a formatar; `tsc --noEmit` sem erro;
Vitest com todos os testes passando, **incluindo** `src/testes/andaime.teste.tsx` e os novos
`src/testes/f8/**`; `next build` concluindo (inclusive a geração do *service worker*).

Storybook (novas *stories* desta fase incluídas pelo mesmo glob da F9a, sem editar config):

```bash
pnpm build-storybook
pnpm test:storybook
```

**Saída esperada:** build sem erro; test-runner sem violação `serious`/`critical`, nos dois temas,
incluindo as *stories* novas de `registro-webcam/**`.

E2E (novo — T10, `@playwright/test`):

```bash
pnpm playwright install chromium
pnpm test:e2e
```

**Saída esperada:** todos os cenários de `e2e/registro-webcam.spec.ts` passam, incluindo a prova
de que `POST /v1/marcacoes` nunca é chamado com câmera virtual simulada.

Varredura de literais desta fase, isolada e verbosa:

```bash
pnpm vitest run src/testes/f8/varredura-de-literais.teste.ts --reporter=verbose
```

**Saída esperada:** nenhuma violação nos diretórios novos de F8.

Lighthouse (Performance e Acessibilidade ≥ 90 — cole o número real; use o build de produção,
nunca `pnpm dev`):

```bash
pnpm build && pnpm start &
pnpm dlx lighthouse http://localhost:3000/ --only-categories=performance,accessibility --output=json --output-path=./lighthouse-login.json
pnpm dlx lighthouse http://localhost:3000/eu --only-categories=performance,accessibility --output=json --output-path=./lighthouse-eu.json
```

Contrato e design system intocados (a partir da raiz do repositório):

```bash
git status --short packages/contracts apps/web/src/componentes/ui apps/web/src/componentes/dominio
```

**Saída esperada:** nada.

Regressão do andaime (não pode quebrar):

```bash
pnpm vitest run src/testes/andaime.teste.tsx
```

## 9. Proibições

1. **Não aceite upload de arquivo de imagem em nenhuma tela de registro de ponto.** Só captura ao
   vivo via `getUserMedia`. Nenhum `<input type="file">` no caminho de registro, nem "só para
   teste", nem "só como alternativa quando a câmera falha".
2. **Não edite `packages/contracts/**` nem `apps/web/src/componentes/{ui,dominio}/**`.** Falta um
   primitivo, uma variante ou um token? É RFC — você não inventa, não cria um paralelo.
3. **Não invente endpoint que não existe no contrato.** Em particular, não crie um endpoint de
   upload de anexo para solicitações, não crie um endpoint de decisão de aprovação (isso é
   `aprovacoes`, F10), não crie uma segunda rota de registro de ponto "específica da web" — é
   sempre `POST /v1/marcacoes` com `canal: "web"`.
4. **Não implemente workflow de aprovação de solicitações** (decidir etapa, delegar, escalonar) —
   é da F10. Você cria e lista; a máquina de estados por trás não é sua.
5. **Não implemente detecção de VPN/proxy/ASN de datacenter** (`PONTO-REDE-002`) nesta fase — é
   decisão explícita do §2, com o achado já registrado em `docs/backlog.md` (T14). Não invente uma
   heurística "só para tentar".
6. **Não crie uma segunda fonte de verdade sobre a allowlist CIDR.** A aplicação é 100% do
   servidor (F5, já concluída); sua responsabilidade é só mapear o erro devolvido.
7. **Não "corrija" o motor de confiança do servidor** (`app/marcacao/confianca/motor.py`) nem o
   router de solicitações (`apps/api/app/routers/solicitacoes.py`). Ambos são *stubs*
   intencionais de outras fases (F14, F10); tocar `apps/api/**` está fora do seu ownership por
   completo.
8. **Não use `localStorage`/`sessionStorage` para o `accessToken` ou o `refreshToken`.**
   `accessToken` vive em memória (via `definirProvedorDeToken`); `refreshToken` vive em cookie
   `httpOnly` manipulado só pelos *Route Handlers* de T1.
9. **Não escreva uma segunda casca de navegação global.** `cabecalho-do-andaime.tsx` e
   `src/app/layout.tsx` não mudam nesta fase; sua navegação vive aninhada em
   `src/app/eu/layout.tsx`.
10. **Não use os termos proibidos** da seção 6 do glossário: é *marcação* (nunca "batida"),
    *tratamento* (nunca "editar marcação"), *apuração* (nunca "cálculo"), *colaborador*/*vínculo*
    (nunca "funcionário"), *saldo credor/devedor* (nunca "banco positivo/negativo"), *tenant*
    (nunca "empresa" para dizer cliente do SaaS).
11. **Não deixe a câmera ligada além do necessário.** Toda `MediaStream` obtida por
    `getUserMedia` tem suas trilhas paradas (`track.stop()`) ao sair da tela de registro, com ou
    sem sucesso.
12. **Não mostre o parâmetro interno de um erro `expoe_regra: false`** (faixa CIDR, limiar de
    score, geocerca configurada) em nenhuma mensagem — mesmo que o `detail` da resposta um dia
    venha a incluir algo. O dicionário de T13 é a defesa em profundidade.
13. **Não ignore `prefers-reduced-motion`**, e não deixe nenhuma animação atrasar a confirmação
    de um registro de ponto — mesma regra de produto da F9a, herdada, não redecidida.
14. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real**, em especial o
    número real de Lighthouse (critério 10) e a prova de que `POST /v1/marcacoes` não é chamado
    com câmera virtual detectada (critério 5).
